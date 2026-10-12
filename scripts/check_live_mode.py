"""Compare the live compiler to plain LuaLaTeX on a read-only project."""
import argparse,base64,hashlib,json,time
from pathlib import Path
import fitz
from cpp_client import Client,ROOT
parser=argparse.ArgumentParser()
parser.add_argument('--project',type=Path,required=True)
parser.add_argument('--main',required=True)
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
parser.add_argument('--output',default='live-mode.json')
args=parser.parse_args();args.runtime=args.runtime.resolve()
report={'checks':[],'edits':[]}
def check(name,ok,defer=False,**details):
    value={'name':name,'ok':bool(ok),**details};report['checks'].append(value);print(json.dumps(value),flush=True)
    if not defer:assert ok,name
def require(frame):
    if not frame.get('ok'):raise RuntimeError(frame.get('error'))
    return frame
def pixels(frame):return fitz.Pixmap(base64.b64decode(frame['image'].split(',',1)[1])).samples
def manifest():return {p.relative_to(args.project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in args.project.rglob('*') if p.is_file()}
before=manifest();source=(args.project/args.main).read_text(encoding='utf-8')
try:
    with Client(args.project,args.runtime,args.main) as live,Client(args.project,args.runtime,args.main,preview_mode='full') as plain:
        a=require(live.request(type='start',page=0));b=require(plain.request(type='start',page=0))
        check('page count equals plain LuaLaTeX',a['pageCount']==b['pageCount'],pages=a['pageCount'])
        report['startupMs']=a['pipelineMs'];report['unmappedPages']=[]
        target=None
        for page in range(a['pageCount']):
            actual=a if page==0 else require(live.request(type='page',page=page))
            expected=b if page==0 else require(plain.request(type='page',page=page))
            check(f'page {page+1} exact pixels',pixels(actual)==pixels(expected),defer=True)
            if not actual['regionRows']:report['unmappedPages'].append(page+1)
            spans=[dict(zip(actual['regionFields'],row)) for row in actual['regionRows']]
            check(f'page {page+1} source spans',all(source[s['start']:s['end']]==s['text'] for s in spans if s['file']==args.main))
            if page==a['pageCount']//2:
                target=next((s for s in spans if s['file']==args.main and s['kind']=='token' and s['text'] in ['a','e','x']),None)
        check('all pages match plain LuaLaTeX',all(c['ok'] for c in report['checks']))
        check('body pages have source mappings',not report['unmappedPages'],unmapped=report['unmappedPages'])
        check('middle-page token exists',target is not None)
        location=require(live.request(type='sync-forward',file=args.main,line=target['line'],column=target['column'],page=a['pageCount']//2))['location']
        check('forward token location',location and location['start']==target['start'])
        check('forward navigation prefers the visible occurrence',location['page']==a['pageCount']//2)
        report['targetPage']=location['page']+1
        for n in range(3):
            replacement='x' if n%2==0 else 'a'
            changed=source[:target['start']]+replacement+source[target['end']:]
            actual=require(live.request(type='edit',file=args.main,source=changed,page=location['page']))
            expected=require(plain.request(type='edit',file=args.main,source=changed,page=location['page']))
            check(f'edit {n+1} exact pixels',pixels(actual)==pixels(expected),page=actual['page']+1,expectedPage=expected['page']+1)
            check(f'edit {n+1} retained checkpoint',actual.get('resumedFrom',0)>1 and actual['outputMode']=='page-stream')
            report['edits'].append({k:actual[k] for k in ['pipelineMs','compileMs','resumedFrom','outputMode','compilerStagesMs'] if k in actual})
    with Client(args.project,args.runtime,args.main) as live:
        require(live.request(type='start',page=0))
    with Client(args.project,args.runtime,args.main) as live:
        again=require(live.request(type='start',page=0))
        check('cache reused on reopen',again.get('cacheReused') is True)
    check('original project unchanged',before==manifest(),files=len(before))
finally:
    (ROOT/'results'/args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
