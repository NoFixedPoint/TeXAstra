"""Real renderer regression: content updates must retain caches without stale pixels."""
import base64,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
from prototype.engine import ROOT,preview_png
from prototype.page_stream import PageRenderer

with fitz.open() as source:
    page=source.new_page(width=240,height=180)
    page.insert_text((20,40),'Cache: repeated text 123',fontsize=12)
    page.draw_rect(fitz.Rect(20,60,180,90),color=(1,0,0),fill=(0,.5,1))
    source[0].clean_contents()
    seed=source.tobytes()
    content=source.xref_stream(source[0].get_contents()[0])
metadata=dict(spans={},revision='renderer-regression',warnings=[])
checks=[]
renderer=PageRenderer()
renderer.seed(seed,[])
try:
    for shift in [0,7,-3,0,11]:
        changed=f'q 1 0 0 1 {shift} 0 cm\n'.encode()+content+b'\nQ'
        renderer.update(dict(page=0,width=240,height=180,coverage=[],contentBase64=base64.b64encode(changed).decode()))
        result=renderer.render('.',0,metadata,[])
        with fitz.open(stream=seed,filetype='pdf') as reference:
            reference.update_stream(reference[0].get_contents()[0],changed,compress=False)
            pixels=reference[0].get_pixmap(matrix=fitz.Matrix(1.4,1.4),annots=False)
            assert fitz.Pixmap(base64.b64decode(result['image'].split(',')[1])).samples==pixels.samples
            expected=[dict(text=c['c'],rect=list(c['bbox'])) for block in reference[0].get_text('rawdict')['blocks'] for line in block.get('lines',[]) for span in line['spans'] for c in span['chars']]
            assert result['characters']==expected
        checks.append(dict(shift=shift,ok=True))
    # Both the accelerated and stdlib fallback paths preserve RGB values.
    import prototype.engine as engine
    accelerated=engine.preview_zlib
    try:
        for codec in [accelerated,engine.zlib]:
            engine.preview_zlib=codec
            assert fitz.Pixmap(preview_png(pixels)).samples==pixels.samples
            checks.append(dict(codec=codec.__name__,ok=True))
    finally:engine.preview_zlib=accelerated
finally:renderer.close()
(ROOT/'results/renderer-correctness.json').write_text(json.dumps({'checks':checks},indent=2),encoding='utf-8')
print('Passed',len(checks),'renderer checks')
