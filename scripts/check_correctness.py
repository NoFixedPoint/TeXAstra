"""Check checkpoint output against full builds with identical Linux TeX packages."""
from pathlib import Path
import json,sys
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prototype.snapshot import SnapshotEngine
from prototype.converge import full_build
from prototype.engine import ROOT

report={'sameEngine':'Linux LuaHBTeX / same installed packages and fonts','checks':[]}
overlays={}
with SnapshotEngine() as engine:
    initial=engine.start();assert initial['ok'],initial
    cases=[
        ('math-middle','pages/page-050.tex','x+x+y=','x+x+z=',49),
        ('tikz-transform','pages/page-050.tex','[rotate=15]','[rotate=45]',49),
        ('reflow-first','pages/page-001.tex','word: alpha.','word: '+'expanded phrase '*200+'.',0),
    ]
    for name,file,before,after,page in cases:
        source=overlays.get(file,(ROOT/'corpus'/file).read_text(encoding='utf-8')).replace(before,after)
        overlays[file]=source
        incremental=engine.update(file,source,page);assert incremental['ok'],incremental
        reference,directory,_=full_build(ROOT/'corpus',overlays,page,instrument=False);assert reference['ok'],reference
        with fitz.open(stream=(engine.directory/'main.pdf').read_bytes(),filetype='pdf') as a,fitz.open(stream=(directory/'main.pdf').read_bytes(),filetype='pdf') as b:
            equal=[a[i].get_pixmap(annots=False).samples==b[i].get_pixmap(annots=False).samples for i in range(len(a))]
            item=dict(name=name,incrementalPages=len(a),referencePages=len(b),equalPages=sum(equal),visiblePageEqual=equal[page],allAvailablePagesEqual=all(equal),pipelineMs=incremental['pipelineMs'])
            report['checks'].append(item);print(item,flush=True)
        if name=='math-middle':
            failed=engine.update(file,source+'\n'+r'\undefinedBrokenCommand',page)
            assert not failed['ok'],failed
            recovered=engine.update(file,source,page)
            assert recovered['ok'],recovered
            with fitz.open(stream=(engine.directory/'main.pdf').read_bytes(),filetype='pdf') as a,fitz.open(stream=(directory/'main.pdf').read_bytes(),filetype='pdf') as b:
                equal=all(a[i].get_pixmap(annots=False).samples==b[i].get_pixmap(annots=False).samples for i in range(len(a)))
            report['checks'].append(dict(name='fatal error restores deleted PDF prefix at page 50',ok=equal))
    # A global definition edit explicitly takes the full rebuild path.
    main=(ROOT/'corpus/main.tex').read_text(encoding='utf-8').replace(r'\newcommand{\globalword}{global}',r'\newcommand{\globalword}{changed everywhere}')
    denied=engine.update('main.tex',main,0)
    report['checks'].append(dict(name='preamble refuses unsafe checkpoint reuse',ok=not denied['ok']))
    overlays['main.tex']=main
with SnapshotEngine(overlays=overlays) as engine:
    result=engine.start();assert result['ok'],result
    # Reflow may move the first invocation off physical page one.
    with fitz.open(stream=(engine.directory/'main.pdf').read_bytes(),filetype='pdf') as document:
        text=' '.join(' '.join(p.get_text().split()) for p in document)
    report['checks'].append(dict(name='preamble rebuild',ok=text.count('changed everywhere')==100))
(ROOT/'results/correctness.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
assert all(c.get('allAvailablePagesEqual',c.get('ok',False)) for c in report['checks'])
