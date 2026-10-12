"""Build real pdfTeX with TeXAstra's out-of-band token/node provenance.

Uses the same checksum-pinned, security-patched TeX Live source as build_engine.
The separate build directory does not disturb the LuaHBTeX runtime.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
    args = parser.parse_args()
    if os.name == 'nt':
        def linux(p):
            return subprocess.check_output(['wsl','-d','Ubuntu-22.04','--exec','wslpath','-a',str(p.resolve())],text=True).strip()
        subprocess.run(['wsl','-d','Ubuntu-22.04','--exec','python3',linux(Path(__file__)),'--runtime',linux(args.runtime)],check=True)
        return
    if sys.platform != 'linux':
        raise SystemExit('This pdfTeX retained-state build currently requires Linux/WSL')
    subprocess.run([sys.executable,str(ROOT/'scripts/build_engine.py'),'--source-only'],check=True)
    cache = Path.home()/'.cache/texastra-pdftex'
    source = Path.home()/'.cache/texastra-engine/source'
    build = cache/'build'
    build.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'scripts'))
    from build_engine import FLAGS
    flags = [f for f in FLAGS if 'luahbtex' not in f and 'pdftex' not in f]
    flags += ['--disable-luahbtex','--enable-pdftex']
    signature = '\n'.join(flags)
    marker = build/'.configure-flags'
    if not marker.exists() or marker.read_text()!=signature:
        with (build/'configure.log').open('w') as log:
            subprocess.run([str(source/'configure'),*flags],cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
        marker.write_text(signature)
    jobs = '-j'+str(min(os.cpu_count() or 2,12))
    print('Building pdfTeX; log:',build/'build.log',flush=True)
    with (build/'build.log').open('w') as log:
        # Restore the generated baseline before make, including after a failed
        # patch build. The oracle must never accidentally contain our hooks.
        web=build/'texk/web2c';pristine=cache/'generated'
        if (pristine/'pdftex0.c').exists():
            for name in ['pdftex0.c','pdftexini.c']:
                shutil.copyfile(pristine/name,web/name)
        for target in [['all-local'],['-C','texk/kpathsea'],['-C','texk/ptexenc'],['-C','libs'],['-C','texk','all-local'],['-C','texk/web2c','pdftex']]:
            subprocess.run(['make',jobs,*target],cwd=build,stdout=log,stderr=subprocess.STDOUT,check=True)
        web = build/'texk/web2c'
        pristine = cache/'generated'
        pristine.mkdir(exist_ok=True)
        for name in ['pdftex0.c','pdftexini.c']:
            p=web/name
            if 'texastra_pdftex' not in p.read_text():
                shutil.copyfile(p,pristine/name)
        # A matching unmodified executable is the fidelity oracle.
        runtime=args.runtime.resolve();runtime.mkdir(parents=True,exist_ok=True)
        if 'texastra_pdftex' not in (web/'pdftex0.c').read_text():
            shutil.copyfile(web/'pdftex',runtime/'pdftex-baseline')
            (runtime/'pdftex-baseline').chmod(0o755)
        sys.path.insert(0,str(ROOT/'engine'))
        from pdftex_patch import apply
        apply(web,pristine)
        subprocess.run(['make',jobs,'pdftex'],cwd=web,stdout=log,stderr=subprocess.STDOUT,check=True)
    temporary=runtime/'texastra-pdftex.new'
    shutil.copyfile(web/'pdftex',temporary);temporary.chmod(0o755)
    subprocess.run(['strip','--strip-debug',str(temporary)],check=True)
    os.replace(temporary,runtime/'texastra-pdftex')
    shutil.copyfile(source/'texk/web2c/pdftexdir/COPYINGv2',runtime/'pdfTeX-COPYING')
    from build_engine import ARCHIVES
    report={'upstream':ARCHIVES,'patches':{},'engineSha256':hashlib.sha256((runtime/'texastra-pdftex').read_bytes()).hexdigest()}
    for name in ['engine/pdftex_patch.py','engine/pdftex_provenance.c','engine/pdftex_state.c','scripts/build_pdftex.py']:
        report['patches'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    (runtime/'pdftex-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Built',runtime/'texastra-pdftex',flush=True)

if __name__=='__main__':main()
