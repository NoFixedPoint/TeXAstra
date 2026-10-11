"""Complete builds with the same Linux engine/packages as the snapshot backend."""
import os,subprocess,time,uuid
from pathlib import Path
from .engine import prepare,render_page

def full_build(project,overlays=None,page=0,instrument=True):
    linux='/tmp/bakoma-full-'+uuid.uuid4().hex[:10]
    directory=Path('//wsl.localhost/Ubuntu-22.04')/linux.lstrip('/') if os.name=='nt' else Path(linux)
    metadata=prepare(project,directory,overlays=overlays,instrument=instrument)
    prefix=['wsl','-d','Ubuntu-22.04','--cd',linux,'--'] if os.name=='nt' else []
    started=time.perf_counter();previous=None;runs=[]
    for run in range(4):
        before=time.perf_counter()
        result=subprocess.run(prefix+['lualatex','-interaction=nonstopmode','-halt-on-error','-no-shell-escape','main.tex'],cwd=None if os.name=='nt' else directory,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',timeout=90)
        runs.append((time.perf_counter()-before)*1000)
        if result.returncode:return dict(ok=False,error=result.stdout[-4000:],runs=runs),directory,metadata
        aux=(directory/'main.aux').read_bytes()
        if previous==aux and 'Rerun to get cross-references right' not in result.stdout:break
        previous=aux
    else:return dict(ok=False,error='Auxiliary state did not converge in four complete passes.',runs=runs),directory,metadata
    frame=render_page(directory,page,metadata=metadata)
    frame.update(ok=True,provisional=False,phase='converged',pipelineMs=(time.perf_counter()-started)*1000,runs=runs)
    return frame,directory,metadata
