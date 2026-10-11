"""POSIX driver. Execute inside WSL; commands/results use JSON lines.

Only session-generated outputs are checkpointed. The driver never edits originals.
"""
import base64,json,os,re,signal,socket,subprocess,sys,time
from pathlib import Path

SESSION=Path(sys.argv[1]).resolve()
SESSION.mkdir(parents=True,exist_ok=True)
os.chdir(SESSION)
process=None
stream_mode=len(sys.argv)>2 and sys.argv[2]=='stream'
listener=None
page_cache={}
seed_pdf=None
if stream_mode:
    os.environ['BAKO_PAGE_STREAM']='1'
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    listener.bind(str(SESSION/'pages.sock'));listener.listen(4);listener.setblocking(False)

def emit(value): print(json.dumps(value),flush=True)
def kill_pid(pid):
    try:
        os.kill(int(pid),signal.SIGTERM)
        os.kill(int(pid),signal.SIGCONT)
    except (ProcessLookupError,ValueError): pass

def cleanup_after(index):
    active=SESSION/'active.pid'
    if active.exists(): kill_pid(active.read_text())
    for file in SESSION.glob('cp-*.pid'):
        n=int(file.stem[3:])
        if n>index:
            kill_pid(file.read_text());file.unlink(missing_ok=True)
            file.with_suffix('.sock').unlink(missing_ok=True)

def receive_pages():
    if listener is None:return None
    try:client,_=listener.accept()
    except BlockingIOError:return None
    with client:
        client.settimeout(10)
        with client.makefile('rb') as data:
            meta_size,byte_size=map(int,data.readline(100).split())
            if not (0<meta_size<8_000_000 and 0<byte_size<64_000_000):raise ValueError('Invalid page message size')
            metadata=json.loads(data.read(meta_size));raw=data.read(byte_size)
            if len(raw)!=byte_size:raise ValueError('Truncated page message')
    offset=0
    for page in metadata['pages']:
        size=page.pop('byteLength');chunk=raw[offset:offset+size];offset+=size
        # Compression is explicitly off for live page commands. A page flush
        # ends with its stream and indirect length, before the page dictionary.
        headers=list(re.finditer(rb'(?:^|\n)\d+ 0 obj\s*<<(?:(?!endobj).)*?>>\s*stream\r?\n',chunk,re.S))
        if not headers:raise ValueError('No drawing stream header in page buffer')
        header=headers[-1]
        length=re.search(rb'/Length\s+(\d+)\s*(?:>>|/)',header[0])
        if not length or b'/Filter' in header[0]:raise ValueError('Expected uncompressed, explicitly sized page commands')
        end=header.end()+int(length[1])
        if end>len(chunk) or not chunk[end:].lstrip().startswith(b'endstream'):raise ValueError('Incomplete page command stream')
        page['contentBase64']=base64.b64encode(chunk[header.end():end]).decode('ascii')
        sidecar=SESSION/f"geometry-{page['page']+1:03d}.jsonl"
        page['glyphIds']=[int(line) for line in sidecar.read_text().splitlines()]
        page_cache[page['page']]=page
    if offset!=len(raw):raise ValueError('Page buffer lengths disagree')
    # SIGCONT must not race the sender's SIGSTOP on a resource miss.
    pid=int((SESSION/'active.pid').read_text())
    for _ in range(1000):
        if Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].startswith('T'):break
        time.sleep(.001)
    else:raise RuntimeError('Page sender did not suspend')
    return dict(streamed=True,complete=False,compilerStagesMs=metadata.get('compilerStagesMs',{}))

def wait_done(timeout=90,allow_stream=False):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        if allow_stream:
            frame=receive_pages()
            if frame:return frame
        marker=SESSION/'completed.json'
        if marker.exists():
            # stop_run precedes process exit; wait until PDF trailer is written.
            try:
                data=(SESSION/'main.pdf').read_bytes()
                if b'%%EOF' in data[-100:]: return json.loads(marker.read_text())
            except (OSError,json.JSONDecodeError): pass
        if time.monotonic()-start>.25:
            active=SESSION/'active.pid'
            if active.exists():
                pid=active.read_text().strip()
                if not pid.isdigit():continue
                state=Path('/proc')/pid/'stat'
                dead=not state.exists()
                if not dead:
                    try:dead=state.read_text().rsplit(') ',1)[1].startswith('Z')
                    except (OSError,IndexError):dead=True
                if dead:
                    log=(SESSION/'engine-output.log').read_text(errors='replace')
                    raise RuntimeError('TeX compilation failed: '+log[-3000:])
        time.sleep(.002)
    log=(SESSION/'engine-output.log').read_text(errors='replace')
    raise RuntimeError('engine timeout: '+log[-2500:])

try:
    for line in sys.stdin:
        request=json.loads(line);started=time.perf_counter()
        try:
            kind=request['type']
            if kind=='start':
                out=open(SESSION/'engine-output.log','w')
                # Seed auxiliary data with a complete pass before retaining
                # checkpoints. Cold-start cost is reported separately.
                prime=subprocess.run(['lualatex','--shell-escape','-interaction=nonstopmode','-halt-on-error','main.tex'],env=dict(os.environ,BAKO_SNAPSHOT_DISABLE='1'),stdout=out,stderr=subprocess.STDOUT,timeout=90)
                if prime.returncode:raise RuntimeError('Initial full pass failed: '+(SESSION/'engine-output.log').read_text(errors='replace')[-3000:])
                # Retain checkpoints from a pass whose auxiliary input agrees
                # with its output. The background builder can then hand over
                # both converged pages and usable downstream compiler state.
                for attempt in range(3):
                    previous=(SESSION/'main.aux').read_bytes()
                    (SESSION/'completed.json').unlink(missing_ok=True)
                    process=subprocess.Popen(['lualatex','--shell-escape','-interaction=nonstopmode','-halt-on-error','main.tex'],stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
                    result=wait_done()
                    if previous==(SESSION/'main.aux').read_bytes():
                        result['converged']=True
                        break
                    cleanup_after(0)
                else:raise RuntimeError('Auxiliary state did not converge in four complete passes.')
            elif kind=='resume':
                for file,content in request.get('updates',{}).items():
                    target_file=(SESSION/file).resolve()
                    if not target_file.is_relative_to(SESSION):raise ValueError('Source path escapes session')
                    target_file.write_text(content,encoding='utf-8')
                target=request['page'];available=sorted(int(p.stem[3:]) for p in SESSION.glob('cp-*.pid'))
                index=max(n for n in available if n<=request.get('invalidateFrom',target))
                cleanup_after(index)
                for cached in list(page_cache):
                    if cached>=index-1:del page_cache[cached]
                (SESSION/'completed.json').unlink(missing_ok=True)
                sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                sock.connect(str(SESSION/f'cp-{index:03d}.sock'))
                sock.sendall(str(target).encode());sock.close()
                resumed=time.perf_counter()
                result=wait_done(allow_stream=stream_mode);result['resumedFrom']=index
                result['prepareMs']=(resumed-started)*1000
                result['compileMs']=(time.perf_counter()-resumed)*1000
            elif kind=='finish':
                os.kill(int((SESSION/'active.pid').read_text()),signal.SIGCONT)
                result=wait_done()
            elif kind=='close': break
            elif kind=='page':result=dict(complete=True,streamed=request.get('viewPage',0) in page_cache)
            else: raise ValueError('unknown request type')
            view=request.get('viewPage',0)
            if result.get('streamed'):
                if view not in page_cache:raise ValueError('Requested page not produced; full refresh required')
                result['pageBuffer']=page_cache[view]
                result['availablePages']=sorted(page_cache)
            else:
                seed_pdf=(SESSION/'main.pdf').read_bytes()
                result['pdfBase64']=base64.b64encode(seed_pdf).decode('ascii')
                sidecar=SESSION/f"geometry-{view+1:03d}.jsonl"
                result['glyphIds']=[int(line) for line in sidecar.read_text().splitlines()] if sidecar.exists() else []
                if stream_mode:
                    result['resourceCoverage']=sorted({value for f in SESSION.glob('resources-*.json') if int(f.stem.split('-')[1])<=result.get('compiledPages',10000) for value in json.loads(f.read_text())['coverage']})
            emit(dict(ok=True,engineMs=(time.perf_counter()-started)*1000,**result))
        except Exception as e:
            # LuaTeX unlinks its output pathname after some fatal errors even
            # when the live descriptor is a memfd. Keep the last complete seed.
            if stream_mode and seed_pdf is not None and not (SESSION/'main.pdf').exists():
                (SESSION/'main.pdf').write_bytes(seed_pdf)
            emit(dict(ok=False,error=str(e),engineMs=(time.perf_counter()-started)*1000))
finally:
    if listener:listener.close()
    cleanup_after(0)
    if process:
        try: os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError: pass
