"""Revision-aware preview service shared by the demo and the VS Code webview."""
import argparse,json,queue,re,sys,threading,time
from pathlib import Path
from .engine import ROOT,build,render_page

class PreviewService:
    def __init__(self,project,engine='stream',emit=lambda x:None):
        self.project=Path(project).resolve();self.engine_name=engine;self.emit=emit
        self.overlays={};self.engine=None;self.queue=queue.Queue();self.latest=0;self.current=None;self.closed=False
        self.idle_timer=None;self.convergence_thread=None
        self.ready_engine=None;self.state_lock=threading.Lock()
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()

    def submit(self,message):
        if self.idle_timer:self.idle_timer.cancel()
        self.latest+=1;message=dict(message,revision=self.latest,submitted=time.perf_counter())
        self.queue.put(message)
        if message['type']!='close':self.emit(dict(type='status',state='building',revision=self.latest,clientId=message.get('clientId',0)))
        return self.latest

    def _run(self):
        while not self.closed:
            request=self.queue.get()
            if request['type']=='close':break
            # Coalesce queued source states, keeping every file's latest buffer.
            requests=[request]
            while not self.queue.empty():
                following=self.queue.get()
                requests.append(following)
            if any(r['type']=='close' for r in requests):break
            # Only this service thread swaps the active engine, before applying
            # the next edit. A background result never closes an in-use worker.
            with self.state_lock:
                ready=self.ready_engine;self.ready_engine=None
            if ready:
                candidate,overlays=ready
                if overlays==self.overlays:
                    if self.engine:self.engine.close()
                    self.engine=candidate
                else:candidate.close()
            changed=[]
            for r in requests:
                if r['type']=='edit':
                    file=r['file']
                    path=(self.project/file).resolve()
                    if not path.is_relative_to(self.project):continue
                    self.overlays[file]=r['source'];changed.append(file)
            request=requests[-1];page=max(0,int(request.get('page',0)))
            try:
                if self.engine_name in {'snapshot','stream'}:
                    from .snapshot import SnapshotEngine
                    rebuild=self.engine is None or len(set(changed))>1 or any(not re.fullmatch(r'pages/page-\d{3}\.tex',f) for f in changed)
                    if rebuild:
                        if self.engine:self.engine.close()
                        self.engine=SnapshotEngine(self.project,overlays=self.overlays,output='stream' if self.engine_name=='stream' else 'pdf')
                        result=self.engine.start(page)
                    elif changed:
                        file=changed[-1];result=self.engine.update(file,self.overlays[file],page)
                    else:result=self.engine.extend(page)
                else:
                    result=build(self.project,ROOT/'.work/demo-native',overlays=self.overlays,page=page)
                result['revisionId']=request['revision']
                result['clientId']=request.get('clientId',0)
                result['sentAt']=request.get('sentAt')
                result['requestToPayloadMs']=(time.perf_counter()-request['submitted'])*1000
                result['engine']=self.engine_name
                if result['ok']:
                    result['isStale']=request['revision']!=self.latest
                    result['type']='frame';self.current=result;self.emit(result)
                    if self.engine_name in {'snapshot','stream'} and result.get('provisional') and not result['isStale']:
                        overlays=self.overlays.copy()
                        self.idle_timer=threading.Timer(2.0,self._converge,args=(request.copy(),overlays,page))
                        self.idle_timer.daemon=True;self.idle_timer.start()
                elif request['revision']==self.latest:self.emit(dict(type='status',state='error',revision=request['revision'],error=result.get('error','Compile failed')))
            except Exception as exc:
                if request['revision']==self.latest:self.emit(dict(type='status',state='error',revision=request['revision'],error=str(exc)))
        self.closed=True
        if self.engine:self.engine.close()
        with self.state_lock:
            if self.ready_engine:self.ready_engine[0].close();self.ready_engine=None

    def _converge(self,request,overlays,page):
        if self.closed or request['revision']!=self.latest:return
        if self.convergence_thread and self.convergence_thread.is_alive():
            self.idle_timer=threading.Timer(1,self._converge,args=(request,overlays,page));self.idle_timer.daemon=True;self.idle_timer.start();return
        def run():
            from .snapshot import SnapshotEngine
            candidate=None
            try:
                candidate=SnapshotEngine(self.project,overlays=overlays,output='stream' if self.engine_name=='stream' else 'pdf')
                result=candidate.start(page)
                if self.closed or request['revision']!=self.latest:return
                if result['ok']:
                    result.update(type='frame',phase='converged',provisional=False,revisionId=request['revision'],clientId=request.get('clientId',0),sentAt=None,isStale=False,engine=self.engine_name)
                    with self.state_lock:
                        if self.closed or request['revision']!=self.latest:return
                        if self.ready_engine:self.ready_engine[0].close()
                        self.ready_engine=(candidate,overlays);candidate=None
                    self.current=result;self.emit(result)
                else:self.emit(dict(type='status',state='error',revision=request['revision'],error='Full-document convergence failed: '+result['error']))
            except Exception as exc:
                if not self.closed and request['revision']==self.latest:self.emit(dict(type='status',state='error',revision=request['revision'],error='Convergence: '+str(exc)))
            finally:
                if candidate:candidate.close()
        self.convergence_thread=threading.Thread(target=run,daemon=True);self.convergence_thread.start()

    def close(self):
        if self.idle_timer:self.idle_timer.cancel()
        if not self.closed:
            self.queue.put(dict(type='close'));self.thread.join(timeout=15)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',default=str(ROOT/'corpus'));parser.add_argument('--engine',choices=['stream','snapshot','native'],default='stream');args=parser.parse_args()
    lock=threading.Lock()
    from .protocol import wire_message
    def emit(message):
        with lock:print(json.dumps(wire_message(message),ensure_ascii=True,separators=(',',':')),flush=True)
    service=PreviewService(args.project,args.engine,emit)
    try:
        for line in sys.stdin:
            message=json.loads(line)
            if message['type']=='close':break
            service.submit(message)
    finally:service.close()

if __name__=='__main__':main()
