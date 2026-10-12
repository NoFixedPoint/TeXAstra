"""Full differential checks of the persistent C++ backend through its protocol."""
import argparse,base64,json,sys,time,os,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from cpp_client import Client,ROOT
from texastra.converge import full_build
from texastra.engine import render_page
parser=argparse.ArgumentParser()
parser.add_argument('--checkpoint',choices=['fork'],default='fork')
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
args=parser.parse_args()
os.environ['BAKO_CHECKPOINT_MODE']=args.checkpoint

report={'checks':[],'samples':[]};overlays={}
def check(name,ok,**details):
    item=dict(name=name,ok=bool(ok),**details);report['checks'].append(item);print(item,flush=True)
    assert ok,item
def pixels(frame):return fitz.Pixmap(base64.b64decode(frame['image'].split(',',1)[1])).samples
def regions(frame):
    # The engine selects the originating command token for generated content;
    # the retired rewriter selected that command plus its arguments. Compare
    # that agreed fallback by command-token span, keeping exact glyph geometry
    # and exact argument/ordinary-token ranges in the differential oracle.
    result=[]
    for r in frame['regions']:
        # The legacy oracle has glyphs only. Rule navigation is independently
        # checked against engine expressions in check_source_mapping.py.
        if r['kind']=='rule-origin':continue
        end=r['end']
        if r['kind']=='macro-origin':
            command=re.match(r'\\[A-Za-z]+',r['text'])
            if command:end=r['start']+len(command[0])
        result.append((r['file'],r['start'],end,tuple(r['rect'])))
    return result
def expand(frame):
    frame=dict(frame)
    frame['regions']=[dict(zip(frame['regionFields'],r)) for r in frame['regionRows']]
    frame['characters']=[dict(text=r[0],rect=r[1]) for r in frame['characterRows']]
    return frame
def sample(frame):return {k:v for k,v in frame.items() if k.endswith('Ms') or k in ['outputMode','resourceRefresh','resumedFrom']}

try:
    with Client(runtime=args.runtime.resolve()) as client:
        initial=client.request(type='start',page=0);assert initial['ok'],initial
        session=Path('//wsl.localhost/Ubuntu-22.04')/initial['session'].lstrip('/') if sys.platform=='win32' else Path(initial['session'])
        reference,directory,metadata=full_build(ROOT/'corpus',instrument=True);assert reference['ok'],reference
        # Full C++ rendered frames, not merely its PDF seed, are checked on every page.
        with fitz.open(stream=(directory/'main.pdf').read_bytes(),filetype='pdf') as pdf:
            for page in range(100):
                actual=expand(initial if page==0 else client.request(type='page',page=page))
                expected=render_page(directory,page,metadata=metadata,document=pdf)
                check(f'page {page+1} exact RGB pixels',pixels(actual)==pixels(expected))
                check(f'page {page+1} exact source regions',regions(actual)==regions(expected))
                check(f'page {page+1} exact selection text/geometry',actual['characters']==expected['characters'])
        for name,file,before,after,page,mode in [
            ('text-last','pages/page-100.tex','word: alpha.','word: omega.',99,'page-stream'),
            ('math-middle','pages/page-050.tex','x+x+y=','x+x+z=',49,'page-stream'),
            ('rotated-TikZ','pages/page-050.tex','[rotate=15]','[rotate=45]',49,'page-stream'),
            ('colored-TikZ','pages/page-050.tex',r'\draw (0,0)',r'\draw[red] (0,0)',49,'page-stream'),
            ('new-Chinese-glyph','pages/page-050.tex','中文排版','汉文排版',49,'page-stream'),
            ('same-new-glyph-cached','pages/page-050.tex','word: alpha.','word: omega.',49,'page-stream'),
            ('reflow-first','pages/page-001.tex','word: alpha.','word: '+'expanded phrase '*200+'.',0,'page-stream'),
        ]:
            source=overlays.get(file,(ROOT/'corpus'/file).read_text(encoding='utf-8')).replace(before,after);overlays[file]=source
            seed=(session/'main.pdf').read_bytes()
            raw=client.request(type='edit',file=file,source=source,page=page);assert raw['ok'],raw
            actual=expand(raw);report['samples'].append(dict(case=name,**sample(raw)))
            check(name+' output path',raw['outputMode']==mode)
            if mode=='page-stream':
                check(name+' seed unchanged',(session/'main.pdf').read_bytes()==seed)
                check(name+' no finalization',not (session/'completed.json').exists())
            reference,directory,metadata=full_build(ROOT/'corpus',overlays,page,instrument=True);assert reference['ok'],reference
            check(name+' exact RGB pixels',pixels(actual)==pixels(reference))
            if name=='reflow-first':
                # The legacy rewriter leaks the current body's "C" attribute
                # into the output routine's generated page number after reflow.
                # There is no source token for that footer digit. The engine
                # correctly leaves it unmapped; retain the full body oracle.
                cutoff=reference['height']-50
                check('generated footer does not inherit body token',all(r['rect'][1]<cutoff for r in actual['regions']))
                reference['regions']=[r for r in reference['regions'] if r['rect'][1]<cutoff]
            check(name+' exact source regions',regions(actual)==regions(reference))
            check(name+' exact selection layer',actual['characters']==reference['characters'])
            if name=='math-middle':
                failed=client.request(type='edit',file=file,source=source+'\n'+r'\undefinedBrokenCommand',page=page)
                check('invalid input rejected',not failed['ok'])
                recovered=client.request(type='edit',file=file,source=source,page=page)
                check('error recovery',recovered['ok'] and pixels(recovered)==pixels(reference))
        adjacent=client.request(type='page',page=1)
        expected=render_page(directory,1,metadata=metadata)
        check('adjacent reflow pixels',adjacent['ok'] and pixels(adjacent)==pixels(expected))
finally:
    output='cpp-correctness.json'
    (ROOT/'results'/output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Passed',len(report['checks']),'C++ differential checks')
