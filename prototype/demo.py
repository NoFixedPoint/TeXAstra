"""Local-only interactive demonstration. Never writes edits to source files."""
import argparse,json,mimetypes,threading,time,subprocess
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .engine import ROOT
from .bridge import PreviewService
from .protocol import wire_message
from collections import deque

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--engine',choices=['cpp','stream','snapshot','native'],default='cpp');parser.add_argument('--project',default=str(ROOT/'corpus'));args=parser.parse_args()
    if args.engine=='cpp':
        subprocess.run(['node',str(ROOT/'native/demo.js'),'--port',str(args.port),'--project',str(Path(args.project).resolve())],check=True)
        return
    messages=deque(maxlen=32);event_id=0;lock=threading.Condition();project=Path(args.project).resolve()
    def emit(message):
        nonlocal event_id
        message=wire_message(message)
        with lock:
            event_id+=1;message['event']=event_id;messages.append(message);lock.notify_all()
    service=PreviewService(project,args.engine,emit)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def output(self,status,data,kind='application/json'):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{args.port}',f'localhost:{args.port}'}:return self.output(403,{})
            parsed=urlparse(self.path);params=parse_qs(parsed.query)
            if parsed.path=='/bootstrap':
                with lock:event=event_id
                return self.output(200,dict(event=event))
            if parsed.path=='/events':
                after=int(params.get('after',['0'])[0])
                with lock:
                    lock.wait_for(lambda:event_id>after,timeout=15)
                    data=[m for m in messages if m['event']>after]
                return self.output(200,data)
            if parsed.path=='/source':
                file=params.get('file',['pages/page-001.tex'])[0];path=(project/file).resolve()
                if not path.is_relative_to(project) or not path.is_file():return self.output(404,{'error':'Unknown source'})
                return self.output(200,dict(file=file,source=service.overlays.get(file,path.read_text(encoding='utf-8'))))
            names={'/':'index.html','/viewer.js':'viewer.js','/viewer.css':'viewer.css'}
            if parsed.path not in names:return self.output(404,{})
            file=ROOT/'webview'/names[parsed.path]
            return self.output(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'text/plain')
        def do_POST(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{args.port}',f'localhost:{args.port}'}:return self.output(403,{})
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{args.port}',f'http://localhost:{args.port}'}:return self.output(403,{})
            length=int(self.headers.get('Content-Length',0))
            if length>2_000_000:return self.output(413,{})
            data=json.loads(self.rfile.read(length))
            if self.path=='/action':return self.output(200,dict(revision=service.submit(data)))
            if self.path=='/paint':
                with (ROOT/'.work/browser-paints.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(data)+'\n')
                return self.output(200,{'ok':True})
            return self.output(404,{})
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Prototype: http://127.0.0.1:{args.port} ({args.engine})',flush=True)
    try:server.serve_forever()
    finally:server.server_close();service.close()

if __name__=='__main__':main()
