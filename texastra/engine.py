"""Native LuaLaTeX + source-attribute baseline. Full builds, not incremental."""
from pathlib import Path
import base64
import hashlib
import json
import re
import shutil
import subprocess
import time
import struct
import zlib
try:
    from zlib_ng import zlib_ng as preview_zlib
except ImportError:
    preview_zlib=zlib
import fitz
from .instrument import Instrumenter, RESET

ROOT=Path(__file__).resolve().parents[1]


def preview_png(pixmap):
    """Lossless RGB PNG with unfiltered scanlines, faster for page previews."""
    if pixmap.n!=3 or pixmap.alpha:raise ValueError('Expected an opaque RGB preview')
    pixels=pixmap.samples;stride=pixmap.stride
    rows=b''.join(b'\0'+pixels[i:i+stride] for i in range(0,len(pixels),stride))
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',pixmap.width,pixmap.height,8,2,0,0,0))
            +chunk(b'IDAT',preview_zlib.compress(rows,1))+chunk(b'IEND',b''))

def prepare(project, destination, overlays=None, instrument=True, page_limit=None):
    project=Path(project).resolve(); destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    overlays=overlays or {}
    mapper=Instrumenter()
    sources={}
    for file in sorted(project.rglob('*')):
        if not file.is_file() or any(p.startswith('.') for p in file.relative_to(project).parts): continue
        if file.suffix.lower() not in {'.tex','.sty','.cls','.bib','.png','.jpg','.pdf','.eps'}: continue
        rel=file.relative_to(project).as_posix(); target=destination/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        if file.suffix=='.tex':
            source=overlays.get(rel,file.read_text(encoding='utf-8'))
            sources[rel]=source
            if rel=='main.tex':
                if page_limit is not None:
                    import re
                    source=re.sub(r'\\input\{pages/page-(\d+)\.tex\}',lambda m:m[0] if int(m[1])<=page_limit else '',source)
                if instrument:
                    source=source.replace(r'\begin{document}',r"\directlua{dofile('provenance.lua')}"+'\n'+r'\begin{document}'+RESET)
            elif instrument:
                source=mapper.instrument(source,rel)+RESET
            target.write_text(source,encoding='utf-8')
        else: shutil.copyfile(file,target)
    if instrument: shutil.copyfile(ROOT/'texastra/provenance.lua',destination/'provenance.lua')
    digest=hashlib.sha256(json.dumps(sources,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    metadata=dict(revision=digest,spans=mapper.spans,warnings=mapper.warnings,sources=sources)
    (destination/'source-map.json').write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
    return metadata

def compile_document(directory,passes=1,engine='lualatex',timeout=120):
    start=time.perf_counter(); runs=[]
    for _ in range(passes):
        before=time.perf_counter()
        p=subprocess.run([engine,'-interaction=nonstopmode','-halt-on-error','-no-shell-escape','main.tex'],cwd=directory,
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=timeout)
        runs.append((time.perf_counter()-before)*1000)
        if p.returncode: return dict(ok=False,compileMs=(time.perf_counter()-start)*1000,runs=runs,error=p.stdout[-5000:])
    return dict(ok=True,compileMs=(time.perf_counter()-start)*1000,runs=runs,
                provisional='Rerun to get cross-references right' in p.stdout or 'undefined references' in p.stdout)

def render_page(directory,page=0,scale=1.4,metadata=None,pdf_bytes=None,glyph_ids=None,document=None,page_count=None):
    start=time.perf_counter()
    directory=Path(directory)
    if metadata is None: metadata=json.loads((directory/'source-map.json').read_text(encoding='utf-8'))
    spans=metadata['spans']
    # Open one byte buffer: thousands of tiny PDF reads over the WSL share can
    # otherwise dominate the measurement and obscure actual rendering cost.
    from contextlib import nullcontext
    with (nullcontext(document) if document is not None else fitz.open(stream=pdf_bytes or (directory/'main.pdf').read_bytes(),filetype='pdf')) as doc:
        page=max(0,min(page,len(doc)-1)); p=doc[page]
        opened=time.perf_counter()
        display=p.get_displaylist(annots=False)
        listed=time.perf_counter()
        image=display.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
        rasterized=time.perf_counter()
        regions=[]
        transform=p.transformation_matrix
        stream=b'\n'.join(doc.xref_stream(xref) for xref in p.get_contents())
        identifiers=[int(n) for n in re.findall(rb'/Bako\s*<<\s*/MCID\s+(\d+)\s*>>\s*BDC',stream)]
        if glyph_ids is not None:identifiers=glyph_ids
        elif not identifiers:
            sidecar=directory/f'geometry-{page+1:03d}.jsonl'
            if sidecar.exists():
                lines=sidecar.read_text().splitlines()
                if lines and lines[0].isdigit():identifiers=[int(n) for n in lines]
        mapping_warnings=[]
        if identifiers:
            traces=p.get_texttrace()
            glyphs=[char for trace in traces for char in trace['chars']]
            if len(identifiers)==len(glyphs):
                for identifier,char in zip(identifiers,glyphs):
                    span=spans.get(identifier) or spans.get(str(identifier))
                    if span:regions.append(dict(id=identifier,rect=list(char[3]),**span))
            else:
                mapping_warnings.append(dict(reason='Tagged glyph/renderer sequence mismatch; navigation disabled for this page.',tags=len(identifiers),glyphs=len(glyphs)))
        # Enumerate once. PyMuPDF Link.next repeatedly scans the page's complete
        # annotation list and becomes quadratic for per-glyph link annotations.
        for xref,_,_ in ([] if identifiers else p.annot_xrefs()):
            _,uri=doc.xref_get_key(xref,'A/URI')
            if not uri.startswith('bako:'): continue
            identifier=uri[5:]; span=spans.get(int(identifier)) or spans.get(identifier)
            if span:
                _,raw=doc.xref_get_key(xref,'Rect')
                rectangle=fitz.Rect([float(n) for n in re.findall(r'[-+]?\d*\.?\d+',raw)])*transform
                regions.append(dict(id=int(identifier),rect=list(rectangle),**span))
        # This layer supplies selection text, not source provenance.
        mapped=time.perf_counter()
        chars=[]
        textpage=fitz.TextPage(display.get_textpage(flags=fitz.TEXTFLAGS_RAWDICT))
        for block in textpage.extractRAWDICT()['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    chars.extend(dict(text=c['c'],rect=list(c['bbox'])) for c in span['chars'])
        extracted=time.perf_counter()
        encoded='data:image/png;base64,'+base64.b64encode(preview_png(image)).decode()
        encoded_at=time.perf_counter()
        result=dict(page=page,pageCount=page_count or len(doc),width=p.rect.width,height=p.rect.height,
                    image=encoded,
                    regions=regions,characters=chars,revision=metadata['revision'],warnings=metadata['warnings']+mapping_warnings,
                    renderStagesMs=dict(open=(opened-start)*1000,displayList=(listed-opened)*1000,raster=(rasterized-listed)*1000,
                        origins=(mapped-rasterized)*1000,text=(extracted-mapped)*1000,png=(encoded_at-extracted)*1000),
                    renderMs=(time.perf_counter()-start)*1000)
    return result

def build(project=ROOT/'corpus',directory=ROOT/'.work/native',overlays=None,passes=1,page=0,page_limit=None):
    start=time.perf_counter()
    metadata=prepare(project,directory,overlays,page_limit=page_limit)
    result=compile_document(directory,passes=passes)
    if result['ok']: result.update(render_page(directory,page,metadata=metadata))
    result['pipelineMs']=(time.perf_counter()-start)*1000
    return result
