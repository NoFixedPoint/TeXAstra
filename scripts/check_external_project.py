"""Exercise actual compilers on arbitrary filenames, includes, and unsaved edits.

An optional --project is read only: hashes are checked after compiling a copy.
Only aggregate outcomes are saved, not private source or rendered pages.
"""
import argparse, base64, hashlib, json, os, queue, subprocess, threading, time
from pathlib import Path
import fitz

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
parser.add_argument('--project',type=Path)
parser.add_argument('--main',default='main.tex')
parser.add_argument('--output',default='external-projects.json')
args=parser.parse_args()
report={'checks':[]}
def check(name,ok,**details):
    item=dict(name=name,ok=bool(ok),**details);report['checks'].append(item)
    print(json.dumps(item),flush=True)
    assert ok,name
def linux(p):
    p=p.resolve()
    return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:] if os.name=='nt' else str(p)
class Client:
    def __init__(self,project,main,compiler='xelatex',sync=True,checkpoint='fork',mode='full'):
        prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
        self.p=subprocess.Popen(prefix+[linux(args.runtime/'bakoma-backend'),'--project',linux(project),
            '--assets',linux(ROOT/'prototype'),'--main',main,'--preview-mode',mode,'--compiler',compiler,'--checkpoint',checkpoint]+(['--sync'] if sync else []),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
        self.q=queue.Queue()
        def read():
            for line in self.p.stdout:self.q.put(json.loads(line))
            self.q.put({'ok':False,'error':'Backend ended'})
        threading.Thread(target=read,daemon=True).start()
    def send(self,**request):
        self.p.stdin.write(json.dumps(request,ensure_ascii=False)+'\n');self.p.stdin.flush()
    def request(self,**request):
        self.send(**request)
        return self.q.get(timeout=180)
    def close(self):
        self.send(type='close');self.p.stdin.close();self.p.wait(timeout=15)
    def __enter__(self):return self
    def __exit__(self,*a):self.close()
def text(frame):return ''.join(row[0] for row in frame['characterRows'])
def manifest(project):
    return {p.relative_to(project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in project.rglob('*') if p.is_file()}
def require(frame):
    if not frame.get('ok'):raise RuntimeError(frame.get('error',str(frame)))
    return frame
try:
    project=ROOT/'.work/external project with spaces';project.mkdir(parents=True,exist_ok=True)
    (project/'parts').mkdir(exist_ok=True)
    main='paper with spaces.tex'
    source=r'''\documentclass{article}
\usepackage{amsmath,graphicx}
\newcommand{\custom}[1]{\textbf{#1}}
\begin{document}
\custom{Original} $x^2+\frac{1}{y}$
\input{parts/chapter}
\newpage Second page.
\end{document}
'''
    (project/main).write_text(source,encoding='utf-8')
    (project/'parts/chapter.tex').write_text('Included content.',encoding='utf-8')
    before=manifest(project)
    for compiler in ['xelatex','pdflatex','lualatex']:
        with Client(project,main,compiler) as client:
            initial=require(client.request(type='start',page=0))
            check(compiler+' initial custom filename',initial['pageCount']==2 and 'Original' in text(initial)
                and initial['outputMode']=='full-build' and initial['regionRows']==[] and not initial['warnings'])
            edited=require(client.request(type='edit',file=main,source=source.replace('Original','Changed'),page=0))
            check(compiler+' unsaved root edit','Changed' in text(edited))
            included=require(client.request(type='edit',file='parts/chapter.tex',source='Replacement chapter.',page=0))
            check(compiler+' include edit and retained root overlay','Replacement' in text(included) and 'Changed' in text(included))
            last=require(client.request(type='page',page=100))
            check(compiler+' page clamp',last['page']==1 and 'Second page' in text(last))
            failed=client.request(type='edit',file=main,source=source.replace('Original',r'\undefinedBrokenCommand'),page=0)
            check(compiler+' reports compile failure',not failed['ok'])
            stale=client.request(type='page',page=1)
            check(compiler+' rejects stale page navigation',not stale['ok'])
            restored=require(client.request(type='edit',file=main,source=source,page=0))
            check(compiler+' recovery preserves include overlay','Original' in text(restored) and 'Replacement' in text(restored))
    with Client(project,main,sync=False) as client:
        client.send(type='start',page=0,clientId=1,overlays={main:source.replace('Original','StartupOverlay')})
        while True:
            frame=client.q.get(timeout=180)
            if frame.get('state')=='error':raise RuntimeError(frame['error'])
            if frame.get('type')=='frame':break
        check('VS Code protocol applies initial unsaved buffers','StartupOverlay' in text(frame) and frame['clientId']==1)
    check('fixture source tree untouched',before==manifest(project))
    for checkpoint in ['fork']:
        with Client(ROOT/'corpus','main.tex','lualatex',checkpoint=checkpoint,mode='auto') as client:
            initial=require(client.request(type='start',page=0))
            check(checkpoint+' corpus retains source mapping',bool(initial['regionRows']) and initial['outputMode']!='full-build')
            file='pages/page-100.tex'
            changed=(ROOT/'corpus'/file).read_text(encoding='utf-8').replace('word: alpha.','word: omega.')
            edited=require(client.request(type='edit',file=file,source=changed,page=99))
            check(checkpoint+' corpus retains page-stream edits',edited['outputMode']=='page-stream' and bool(edited['regionRows']))
    if args.project:
        before=manifest(args.project)
        with Client(args.project,args.main) as client:
            start=time.monotonic();initial=require(client.request(type='start',page=0))
            check('user project XeLaTeX compiles',initial['pageCount']>0,pages=initial['pageCount'],elapsedSeconds=round(time.monotonic()-start,2))
            last=require(client.request(type='page',page=initial['pageCount']-1))
            check('user project last page renders',last['page']==initial['pageCount']-1 and len(last['image'])>100)
        check('user project source tree untouched',before==manifest(args.project),files=len(before))
finally:
    (ROOT/'results'/args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
