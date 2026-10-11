"""Windows-to-WSL adapter for the POSIX LuaTeX checkpoint experiment."""
import base64,hashlib,json,os,queue,re,shutil,subprocess,threading,time,uuid
from pathlib import Path
from .engine import ROOT,prepare,render_page
from .instrument import Instrumenter,RESET

class SnapshotEngine:
    def __init__(self,project=ROOT/'corpus',distro='Ubuntu-22.04',overlays=None,output='pdf'):
        self.project=Path(project).resolve();self.distro=distro
        if output not in {'pdf','stream'}:raise ValueError('Unknown output mode')
        self.output=output;self.renderer=None;self.available_pages=set()
        if output=='stream':
            from .page_stream import PageRenderer
            self.renderer=PageRenderer()
        self.linux='/tmp/bakoma-revived-'+uuid.uuid4().hex[:10]
        self.command_prefix=['wsl','-d',distro,'--'] if os.name=='nt' else []
        self.directory=Path(f'//wsl.localhost/{distro}')/self.linux.lstrip('/') if os.name=='nt' else Path(self.linux)
        self.directory.mkdir(parents=True)
        self.metadata=prepare(project,self.directory,overlays=overlays)
        self.mapper=Instrumenter()
        files=sorted({v['file'] for v in self.metadata['spans'].values()})
        self.mapper.file_slots={f:i+1 for i,f in enumerate(files)}
        self.mapper.spans=self.metadata['spans']
        for identifier,span in self.mapper.spans.items():self.mapper.file_ids.setdefault(span['file'],[]).append(identifier)
        shutil.copyfile(ROOT/'prototype/snapshot.lua',self.directory/'snapshot.lua')
        shutil.copyfile(ROOT/'prototype/snapshot.c',self.directory/'snapshot.c')
        shutil.copyfile(ROOT/'prototype/page_stream.lua',self.directory/'page_stream.lua')
        subprocess.run(self.command_prefix+['gcc','-O2','-fPIC','-shared','-o',self.linux+'/bako_snapshot.so',self.linux+'/snapshot.c'],check=True,capture_output=True)
        self._root_source()
        shutil.copyfile(ROOT/'scripts/snapshot_worker.py',self.directory/'worker.py')
        self.process=subprocess.Popen(self.command_prefix+['python3',self.linux+'/worker.py',self.linux,output],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        self.responses=queue.Queue()
        self.pdf_page_count=0;self.pdf_revision=None;self.converged=False
        def consume():
            for line in self.process.stdout:
                try:self.responses.put(json.loads(line))
                except json.JSONDecodeError:pass
        threading.Thread(target=consume,daemon=True).start()

    def _root_source(self):
        path=self.directory/'main.tex';source=path.read_text(encoding='utf-8')
        source=source.replace(r'\begin{document}',r"\directlua{dofile('snapshot.lua')}"+'\n'+r'\begin{document}')
        # Retain lazy font/math/TikZ and PDF font-resource initialization in the
        # first checkpoint. The unused form is written immediately, never placed
        # on a page. It uses only the controlled corpus's known constructs;
        # it is not a claim that arbitrary user macros are safe to pre-execute.
        warm=r'''\begingroup\setbox0=\vbox{\hsize=\textwidth
{\Large\bfseries Acceptance}\par English 中文排版
$x+\frac{a_{1}+b^{2}}{c+d}+\alpha+\sum_{j=1}^{n}j+\int_{0}^{1}t^{2}\,dt$
\begin{tikzpicture}\draw (0,0)--(1,0);\node[rotate=15] at (0,0) {Label $x_{1}$};\end{tikzpicture}
}\immediate\saveboxresource0\endgroup
'''
        source=source.replace(r'\begin{document}',r'\begin{document}'+'\n'+warm)
        source=re.sub(r'\\input\{pages/page-(\d+)\.tex\}',lambda m:rf'\directlua{{bako_checkpoint({int(m[1])})}}'+m[0],source)
        path.write_text(source,encoding='utf-8')

    def request(self,message,timeout=100):
        self.process.stdin.write(json.dumps(message)+'\n');self.process.stdin.flush()
        return self.responses.get(timeout=timeout)

    def start(self,page=0):
        start=time.perf_counter();result=self.request(dict(type='start',viewPage=page))
        if result['ok']: self._render(result,page)
        self.converged=result.get('converged',False)
        result['pipelineMs']=(time.perf_counter()-start)*1000
        return result

    def update(self,file,source,page):
        start=time.perf_counter()
        self.converged=False
        if not re.fullmatch(r'pages/page-\d{3}\.tex',file):
            return dict(ok=False,error='This checkpoint experiment requires a full restart for preamble or structural edits.')
        self.metadata['sources'][file]=source
        rewritten=self.mapper.instrument(source,file)+RESET
        self.metadata['spans']=self.mapper.spans
        self.metadata['warnings']=self.mapper.warnings
        self.metadata['revision']=hashlib.sha256(json.dumps(self.metadata['sources'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        mapped=time.perf_counter()
        invalidated=int(re.search(r'(\d+)\.tex',file)[1])-1
        self.available_pages={n for n in self.available_pages if n<invalidated}
        result=self.request(dict(type='resume',page=page+1,viewPage=page,updates={file:rewritten},invalidateFrom=int(re.search(r'(\d+)\.tex',file)[1])))
        received=time.perf_counter()
        if result['ok']:self._render(result,page)
        result['mapMs']=(mapped-start)*1000
        result['roundtripMs']=(received-mapped)*1000
        result['pipelineMs']=(time.perf_counter()-start)*1000
        result['provisional']=True
        return result

    def extend(self,page):
        start=time.perf_counter()
        if page in self.available_pages:
            if self.renderer and page not in getattr(self,'streamed_pages',set()):
                result=dict(ok=True,outputMode='retained-page')
                # Cached pages before the invalidated input retain their old IDs.
                result.update(self.renderer.render(self.directory,page,self.metadata,self.page_ids.get(page,[])))
                result['pipelineMs']=(time.perf_counter()-start)*1000
                return result
            result=self.request(dict(type='page',viewPage=page))
        else:result=self.request(dict(type='resume',page=page+1,viewPage=page,invalidateFrom=page+1))
        if result['ok']:self._render(result,page)
        result['pipelineMs']=(time.perf_counter()-start)*1000;result['provisional']=not self.converged
        return result

    def _render(self,result,page):
        if self.renderer:
            from .page_stream import ResourceMiss
            buffer=result.pop('pageBuffer',None)
            if buffer:
                try:self.renderer.update(buffer)
                except ResourceMiss as exc:
                    refreshed=self.request(dict(type='finish',viewPage=page))
                    if not refreshed['ok']:raise RuntimeError(refreshed['error'])
                    result.update(refreshed,resourceRefresh=str(exc))
                    result['resourceCoverage']=list(set(result.get('resourceCoverage',[]))|set(buffer['coverage']))
                else:
                    ids=buffer['glyphIds'];self.page_ids[page]=ids
                    produced=result.pop('availablePages',[page])
                    self.streamed_pages.update(produced);self.available_pages.update(produced)
                    result.update(self.renderer.render(self.directory,page,self.metadata,ids))
                    result['outputMode']='page-stream';result['pageBytes']=len(base64.b64decode(buffer['contentBase64']))
                    self.pdf_revision=self.metadata['revision']
                    return
            data=base64.b64decode(result.pop('pdfBase64'))
            identifiers=result.pop('glyphIds')
            self.renderer.seed(data,result.pop('resourceCoverage'))
            self.streamed_pages=set();self.page_ids={page:identifiers}
            # Retain sidecar IDs for cached page navigation, never match strings.
            for sidecar in self.directory.glob('geometry-*.jsonl'):
                n=int(sidecar.stem.split('-')[1])-1
                if n<len(self.renderer.document):self.page_ids[n]=[int(v) for v in sidecar.read_text().splitlines()]
            result.update(self.renderer.render(self.directory,page,self.metadata,identifiers))
            result['outputMode']='resource-seed'
            self.available_pages=set(range(result['pageCount']))
            self.pdf_page_count=result['pageCount'];self.pdf_revision=self.metadata['revision']
            return
        data=base64.b64decode(result.pop('pdfBase64'))
        identifiers=result.pop('glyphIds')
        result.update(render_page(self.directory,page,metadata=self.metadata,pdf_bytes=data,glyph_ids=identifiers))
        self.pdf_page_count=result['pageCount'];self.pdf_revision=self.metadata['revision']
        self.available_pages=set(range(result['pageCount']))

    def close(self):
        if self.renderer:self.renderer.close()
        if self.process.poll() is None:
            try:
                self.process.stdin.write('{"type":"close"}\n');self.process.stdin.flush()
                self.process.wait(timeout=10)
            except (BrokenPipeError,subprocess.TimeoutExpired):self.process.kill()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
