"""Exercise compiler/Lua state, output rewind and rollback without child forks."""
import base64,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from cpp_client import Client,ROOT
from prototype.converge import full_build

os.environ['BAKO_CHECKPOINT_MODE']='internal'
fixture=ROOT/'.work/internal-state-fixture'
(fixture/'pages').mkdir(parents=True,exist_ok=True)
main=(ROOT/'corpus/main.tex').read_text(encoding='utf8')
main=main[:main.index(r'\input{pages/page-003.tex}')]+r'\end{document}'+'\n'
main=main.replace(r'\newcommand{\fixed}{x+y}',r'''
\newcount\probeCount
\newwrite\probeFile
\immediate\openout\probeFile=probe.txt
\directlua{os.remove('append.txt');appendProbe=assert(io.open('append.txt','a+'))}
\newcommand{\mutatestate}{\global\advance\probeCount by 1\relax
  \directlua{probe=(probe or 0)+1;collectgarbage('collect');appendProbe:seek('set',0);appendProbe:write('entry:',probe,string.char(10));appendProbe:flush()}
  \immediate\write\probeFile{count:\the\probeCount}}
\newcommand{\fixed}{\number\probeCount+\directlua{tex.sprint(probe or 0)}}
\newcommand{\hardexit}{\directlua{os.exit(7)}}
''')
(fixture/'main.tex').write_text(main,encoding='utf8')
original={}
for n in [1,2]:
    file=f'pages/page-{n:03d}.tex'
    original[file]='\\mutatestate\n'+(ROOT/'corpus'/file).read_text(encoding='utf8')
    (fixture/file).write_text(original[file],encoding='utf8')
report={'checks':[],'samples':[]}
def check(name,ok,**details):
    item=dict(name=name,ok=bool(ok),**details);report['checks'].append(item)
    print(item,flush=True);assert ok,item
def pixels(frame):return fitz.Pixmap(base64.b64decode(frame['image'].split(',',1)[1])).samples
def local(path):return Path('//wsl.localhost/Ubuntu-22.04')/path.lstrip('/') if os.name=='nt' else Path(path)
try:
    with Client(fixture) as c:
        initial=c.request(type='start',page=1);check('initial two-page state fixture',initial['ok'],error=initial.get('error'))
        session=local(initial['session']);pid=int((session/'active.pid').read_text())
        check('one retained compiler, no checkpoint children',not local(f'/proc/{pid}/task/{pid}/children').read_text().strip())
        check('internal snapshot records',len(list(session.glob('cp-*.snap')))==2 and not list(session.glob('cp-*.pid')))
        journal=None
        for i in range(20):
            file='pages/page-002.tex';source=original[file].replace('word: alpha.','word: omega.' if i%2==0 else 'word: alpha.')
            r=c.request(type='edit',file=file,source=source,page=1)
            check(f'repeated rollback {i+1}',r['ok'],error=r.get('error'))
            s=r['snapshot'];check(f'same compiler PID {i+1}',s['mode']=='internal' and s['pid']==pid and r['compilerStagesMs']['fork']==0)
            check(f'TeX output file rewind {i+1}',(session/'probe.txt').read_text().splitlines()==['count:1','count:2'])
            check(f'Lua append descriptor semantics {i+1}',(session/'append.txt').read_text().splitlines()==['entry:1','entry:2'])
            if journal is None:journal=s['undoBytes']
            check(f'bounded undo storage {i+1}',s['undoBytes']==journal)
            if i==19:check('Lua GC and TeX register rollback pixels',pixels(r)==pixels(initial))
            report['samples'].append({k:r[k] for k in ['pipelineMs','compilerStagesMs','snapshot']})
        for suffix,label in [('\n\\undefinedBrokenCommand','TeX error'),('\n\\hardexit','Lua os.exit')]:
            started=time.perf_counter();failed=c.request(type='edit',file=file,source=original[file]+suffix,page=1)
            duration=time.perf_counter()-started
            check(label+' promptly reported',not failed['ok'] and duration<3,seconds=duration)
            r=c.request(type='edit',file=file,source=original[file],page=1)
            check(label+' restored same compiler',r['ok'] and r['snapshot']['pid']==pid,error=r.get('error'))
            check(label+' restored state and pixels',pixels(r)==pixels(initial))
        first='pages/page-001.tex';overlay={first:'\\mutatestate\n'+original[first]}
        r=c.request(type='edit',file=first,source=overlay[first],page=1)
        check('earlier edit invalidates and rebuilds later snapshot',r['ok'] and r['resumedFrom']==1,error=r.get('error'))
        check('earlier edit rewinds output before replay',(session/'probe.txt').read_text().splitlines()==['count:1','count:2','count:3'])
        reference,_,_=full_build(fixture,overlay,1,instrument=True)
        check('earlier edit matches complete-build state and pixels',reference['ok'] and pixels(r)==pixels(reference))
        for i in range(4):
            r=c.request(type='edit',file=file,source=original[file],page=1)
            check(f'rebuilt checkpoint retains upstream TeX and Lua state {i+1}',r['ok'] and r['resumedFrom']==2 and pixels(r)==pixels(reference))
        check('still no checkpoint children',not local(f'/proc/{pid}/task/{pid}/children').read_text().strip())
finally:
    (ROOT/'results/internal-state-correctness.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('Passed',len(report['checks']),'internal snapshot checks',flush=True)
