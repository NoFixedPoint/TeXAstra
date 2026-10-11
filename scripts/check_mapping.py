"""Compare annotated and original outputs using real typesetting and PDF geometry."""
from pathlib import Path
import sys,json,time,base64,io
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prototype.engine import prepare,compile_document,render_page,ROOT
import fitz

limit=int(sys.argv[1]) if len(sys.argv)>1 else 1
root=ROOT/'.work/mapping-check'
report={}
for label,instrument in [('reference',False),('mapped',True)]:
    path=root/label
    metadata=prepare(ROOT/'corpus',path,instrument=instrument,page_limit=limit)
    report[label]=compile_document(path,passes=2)
    print(label,report[label],flush=True)
    if not report[label]['ok']: sys.exit(1)
with fitz.open(root/'reference/main.pdf') as a, fitz.open(root/'mapped/main.pdf') as b:
    report['pageCounts']=[len(a),len(b)]
    report['pixelEqual']=[pa.get_pixmap(annots=False).samples==pb.get_pixmap(annots=False).samples for pa,pb in zip(a,b)]
    report['textEqual']=[pa.get_text()==pb.get_text() for pa,pb in zip(a,b)]
page=render_page(root/'mapped',0)
with fitz.open(root/'mapped/main.pdf') as document:
    pixels=document[0].get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False,annots=False)
    report['previewPngPixelEqual']=Image.open(io.BytesIO(base64.b64decode(page['image'].split(',')[1]))).tobytes()==pixels.samples
report['regions']=len(page['regions']); report['warnings']=page['warnings']
report['sampleMath']=[r for r in page['regions'] if r['line'] in [4,5] and r['text'] in 'xyzab12'][:30]
print(json.dumps(report,indent=2,ensure_ascii=False))
(ROOT/'results').mkdir(exist_ok=True)
(ROOT/'results'/f'mapping-{limit}.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
assert report['pageCounts']==[limit,limit] and all(report['pixelEqual']) and all(report['textEqual'])
assert report['previewPngPixelEqual'] and not report['warnings']
