"""Install an isolated, historical TeX Live 2021 for macOS release validation.

Explicit opt-in build/test utility; never called by the extension or runtime.
"""
import argparse
import hashlib
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

REPOSITORY = 'https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2021/tlnet-final'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--engine', type=Path, help='Bundled texastra-luahbtex (defaults to this checkout or installed VSIX)')
    parser.add_argument('--pdftex-engine', type=Path,
                        help='Matching pdfTeX (defaults to texastra-pdftex beside the LuaHBTeX engine)')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('This installer is for macOS build/test machines')
    root = Path(__file__).resolve().parents[1]
    engine = args.engine or root/'native/runtime/texastra-luahbtex'
    if not engine.is_file() and args.engine is None:
        candidates = sorted((Path.home()/'.vscode/extensions').glob('texastra.texastra-*/native/runtime/texastra-luahbtex'))
        if candidates: engine = candidates[-1]
    if not engine.is_file():
        raise SystemExit('Build or install the macOS VSIX first, or supply --engine /absolute/path/to/texastra-luahbtex')
    engine = engine.resolve()
    pdftex = args.pdftex_engine or engine.parent/'texastra-pdftex'
    if not pdftex.is_file():
        raise SystemExit('Build or install the pdfTeX runtime first, or supply --pdftex-engine /absolute/path/to/pdftex')
    pdftex = pdftex.resolve()
    destination = args.destination.resolve()
    if destination.exists():
        raise SystemExit('Choose a new empty destination: '+str(destination))
    work = Path(__file__).resolve().parents[1]/'.work/texlive-installer'
    work.mkdir(parents=True, exist_ok=True)
    archive = work/'install-tl-unx.tar.gz'
    urllib.request.urlretrieve(REPOSITORY+'/'+archive.name, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != 'bc9285e51bf3eec8e928fce78dd146e9418d20b2c3048148cfb28d95f76c4cb5':
        raise RuntimeError('Historical installer checksum mismatch')
    with tarfile.open(archive) as source:
        source.extractall(work, filter='data')
    installer = next(work.glob('install-tl-*/install-tl'))
    profile = work/'macos.profile'
    profile.write_text('\n'.join([
        'selected_scheme scheme-basic', 'binary_universal-darwin 1',
        'TEXDIR '+str(destination), 'TEXMFCONFIG '+str(destination/'texmf-config'),
        'TEXMFVAR '+str(destination/'texmf-var'), 'TEXMFHOME '+str(destination/'texmf-home'),
        'TEXMFLOCAL '+str(destination/'texmf-local'),
        'TEXMFSYSCONFIG '+str(destination/'texmf-config'), 'TEXMFSYSVAR '+str(destination/'texmf-var'),
        'instopt_adjustpath 0', 'tlpdbopt_install_docfiles 0', 'tlpdbopt_install_srcfiles 0',
    ])+'\n')
    subprocess.run(['perl', str(installer), '-profile', str(profile), '-repository', REPOSITORY], check=True)
    binary = destination/'bin/universal-darwin'
    subprocess.run([str(binary/'tlmgr'), 'install', 'pgf', 'booktabs', 'geometry', 'luaotfload', 'luatex', 'luahbtex', 'latex-bin', 'synctex'], check=True)
    # The historical Mac distribution ships 1.13.2. This isolated installation
    # needs the bundled 1.14 engine and matching formats, including full builds.
    shutil.copy2(engine, binary/'luahbtex')
    # The final historical Mac tree ships pdfTeX 1.40.23; provenance uses
    # 1.40.22. Keep the isolated tree and its formats matched to our engine.
    # CI supplies the unmodified build as an independent rendering oracle.
    shutil.copy2(pdftex, binary/'pdftex')
    env = dict(os.environ, PATH=str(binary)+os.pathsep+os.environ.get('PATH', ''))
    env['TEXMFCNF'] = subprocess.check_output([str(binary/'kpsewhich'), '--var-value=TEXMFCNF'], text=True).strip()
    subprocess.run([str(binary/'fmtutil-sys'), '--byengine', 'luahbtex'], env=env, check=True)
    subprocess.run([str(binary/'fmtutil-sys'), '--byengine', 'pdftex'], env=env, check=True)
    print('Set texastra.texBinDirectory to:', binary)


if __name__ == '__main__':
    main()
