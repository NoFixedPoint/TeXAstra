"""Run under Linux/WSL. Render events carry extracted-text evidence, not log flushes."""
import json,os,queue,re,shutil,signal,subprocess,sys,threading,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
directory=Path('/tmp/bakoma-texpresso-corpus');directory.mkdir(exist_ok=True)
for source in (root/'corpus').rglob('*.tex'):
    target=directory/source.relative_to(root/'corpus');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
binary=Path('/home/wenlan/.cache/bakoma-revived/texpresso/build/texpresso')
env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software',BAKO_TRACE='1',BAKO_CAPTURE='/tmp/bakoma-texpresso-frame.bmp')
events=queue.Queue();logs=[]
p=subprocess.Popen([str(binary),'-json','-texlive','main.tex'],cwd=directory,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True)
def drain(stream):
    for line in stream:
        logs.append(line)
        if line.startswith('BAKO_FRAME '):
            _,page,ticks,word,pixels=line.split();events.put(dict(page=int(page),word=int(word),pixels=int(pixels),received=time.perf_counter()))
for stream in [p.stdout,p.stderr]:threading.Thread(target=drain,args=(stream,),daemon=True).start()
def send(command):p.stdin.write(json.dumps(command,ensure_ascii=False)+'\n');p.stdin.flush()
def wait_frame(page,word=None,previous=None,timeout=45):
    until=time.perf_counter()+timeout
    while time.perf_counter()<until:
        try:
            event=events.get(timeout=min(.5,until-time.perf_counter()))
            if event['page']==page and (word is None or event['word']==word) and (previous is None or event['pixels']!=previous):return event
        except queue.Empty:
            if p.poll() is not None:break
    raise RuntimeError(f'No correct rendered frame for page {page+1}, word {word}; exit={p.poll()}')
report=dict(candidate='TeXpresso',commit=subprocess.check_output(['git','-C',str(binary.parent.parent),'rev-parse','HEAD'],text=True).strip(),headless=True,measurement='request to changed-pixel SDL render-present; NOT a verified-correct-output latency; includes diagnostic capture, excludes VS Code/compositor',updates=[])
try:
    start=time.perf_counter();frame=wait_frame(0);report['startupMs']=(time.perf_counter()-start)*1000
    time.sleep(3)
    while not events.empty():frame=events.get_nowait()
    for page in [0,49,99]:
        file=f'pages/page-{page+1:03d}.tex';source=(directory/file).read_text()
        if page!=0:
            # Later files have no SyncTeX entries until typeset. Exercise the
            # viewer's demand-driven page advance rather than assuming entries.
            for target in range(frame['page']+1,page+1):
                send(['next-page']);frame=wait_frame(target)
        for edit in range(6):
            while not events.empty():events.get_nowait()
            word=1 if edit%2==0 else 0
            modified=source.replace('word: alpha.','word: omega.' if word else 'word: alpha.')
            previous=frame['pixels'];start=time.perf_counter();send(['open',file,modified]);frame=wait_frame(page,previous=previous)
            record=dict(page=page+1,ms=(frame['received']-start)*1000,correctText=frame['word']==word,pixelHash=frame['pixels'])
            report['updates'].append(record);print(record,flush=True)
except Exception as e:
    report['error']=str(e);print(str(e),flush=True)
finally:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
    (root/'results').mkdir(exist_ok=True)
    (root/'results/texpresso.json').write_text(json.dumps(report,indent=2))
    (root/'.work/texpresso-session.log').write_text(''.join(logs))
    capture=Path('/tmp/bakoma-texpresso-frame.bmp')
    if capture.exists():shutil.copyfile(capture,root/'.work/texpresso-frame.bmp')
