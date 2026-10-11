"""Differential checks across the real stream/compiler/renderer interface."""
from pathlib import Path
import base64,json,sys,time
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prototype.snapshot import SnapshotEngine
from prototype.converge import full_build
from prototype.engine import ROOT

report={'checks':[],'samples':[]}
overlays={}
def pixels(image):return fitz.Pixmap(base64.b64decode(image.split(',',1)[1])).samples
def brief(r):return {k:v for k,v in r.items() if k not in {'image','regions','characters','warnings'}}
def check(name,condition,**data):
    item=dict(name=name,ok=bool(condition),**data);report['checks'].append(item);print(item,flush=True)
    assert condition,item

with SnapshotEngine(output='stream') as engine:
    print(engine.directory,flush=True)
    initial=engine.start();assert initial['ok'],initial
    reference,directory,_=full_build(ROOT/'corpus',instrument=False)
    assert reference['ok'],reference
    with fitz.open(stream=(directory/'main.pdf').read_bytes(),filetype='pdf') as ref:
        equal=[engine.renderer.document[i].get_pixmap(annots=False).samples==ref[i].get_pixmap(annots=False).samples for i in range(len(ref))]
        check('all 100 initial pages match uninstrumented full build',len(equal)==100 and all(equal),pages=sum(equal))
    for name,file,before,after,page,mode in [
        ('text-last','pages/page-100.tex','word: alpha.','word: omega.',99,'page-stream'),
        ('math-middle','pages/page-050.tex','x+x+y=','x+x+z=',49,'page-stream'),
        ('rotated-TikZ','pages/page-050.tex','[rotate=15]','[rotate=45]',49,'page-stream'),
        ('new-Chinese-glyph','pages/page-050.tex','中文排版','汉文排版',49,'resource-seed'),
        ('same-new-glyph-cached','pages/page-050.tex','word: alpha.','word: omega.',49,'page-stream'),
        ('reflow-first','pages/page-001.tex','word: alpha.','word: '+'expanded phrase '*200+'.',0,'page-stream'),
    ]:
        source=overlays.get(file,(ROOT/'corpus'/file).read_text(encoding='utf-8')).replace(before,after)
        overlays[file]=source
        seed_before=(engine.directory/'main.pdf').read_bytes()
        result=engine.update(file,source,page);assert result['ok'],result
        report['samples'].append(dict(case=name,**brief(result)))
        check(name+' uses expected output path',result['outputMode']==mode,mode=result['outputMode'])
        if mode=='page-stream':
            check(name+' leaves seed PDF untouched',(engine.directory/'main.pdf').read_bytes()==seed_before)
            check(name+' skips document finalization',not (engine.directory/'completed.json').exists())
        reference,directory,metadata=full_build(ROOT/'corpus',overlays,page,instrument=True)
        assert reference['ok'],reference
        check(name+' exact rendered pixels',pixels(result['image'])==pixels(reference['image']))
        actual=[(r['file'],r['start'],r['end'],r['rect']) for r in result['regions']]
        expected=[(r['file'],r['start'],r['end'],r['rect']) for r in reference['regions']]
        check(name+' exact source regions',actual==expected,count=len(actual))
        if name=='math-middle':
            failed=engine.update(file,source+'\n'+r'\undefinedBrokenCommand',page)
            check('invalid input is rejected',not failed['ok'])
            recovered=engine.update(file,source,page)
            check('error recovery uses correct memory output',recovered['ok'] and pixels(recovered['image'])==pixels(reference['image']))
    adjacent=engine.extend(1)
    check('adjacent page after reflow',adjacent['ok'])
    with fitz.open(stream=(directory/'main.pdf').read_bytes(),filetype='pdf') as ref:
        expected=ref[1].get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False,annots=False).samples
        check('adjacent reflow pixels',pixels(adjacent['image'])==expected)
(ROOT/'results/page-stream-correctness.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Passed',len(report['checks']),'checks',flush=True)
