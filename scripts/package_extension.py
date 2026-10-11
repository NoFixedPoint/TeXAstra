"""Package a tested runtime without interrupting previews using another runtime."""
import argparse, hashlib, json, shutil, subprocess, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
parser.add_argument('--target',choices=['linux-x64','win32-x64'],default='linux-x64')
args=parser.parse_args()
windows=args.target=='win32-x64'
backend='bakoma-backend.exe' if windows else 'bakoma-backend'
if not (args.runtime/backend).is_file():raise SystemExit('Build the selected native runtime before packaging')
if windows and not (args.runtime/'sources/mupdf-1.26.12-source.tar.gz').is_file():
    raise SystemExit('Prepare the Windows source/license kit first: python scripts/windows_sources.py')
if not windows and not (args.runtime/'bakoma-luahbtex').is_file():raise SystemExit('Build the token-origin compiler first: python scripts/build_engine.py')
version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
stage=Path(tempfile.mkdtemp(prefix='package-',dir=ROOT/'.work'))
files=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
for name in set(files):
    if not name or Path(name).parts[0] in {'corpus','results','artifacts'}:continue
    source=ROOT/name
    if not source.is_file():continue
    target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
destination=stage/'native/runtime/windows-x64' if windows else stage/'native/runtime'
shutil.copytree(args.runtime.resolve(),destination,ignore=shutil.ignore_patterns('*.new','bako_internal.so','windows-x64'))
suffix='-win32-x64' if windows else ''
artifact=ROOT/'artifacts'/f'bakoma-revived-prototype-{version}{suffix}.vsix'
subprocess.run([shutil.which('npx.cmd') or shutil.which('npx'),'--yes','@vscode/vsce','package',
    '--allow-missing-repository','--no-rewrite-relative-links','--skip-license','--target',args.target,'--out',str(artifact)],cwd=stage,check=True)
with zipfile.ZipFile(artifact) as archive:
    checked=0
    for name in archive.namelist():
        if name.startswith('extension/') and not name.endswith('/'):
            source=stage/name[len('extension/'):]
            # vsce normalizes the root README/LICENSE filenames in the archive.
            if not source.exists():
                source=next((p for p in stage.iterdir() if p.name.lower()==source.name.lower()),source)
            if source.is_file():
                assert archive.read(name)==source.read_bytes(),name
                checked+=1
    assert json.loads(archive.read('extension/package.json'))['version']==version
    assert 'extension/native/runtime/bako_internal.so' not in archive.namelist()
    if windows:
        binaries=[name for name in archive.namelist() if name.lower().endswith(('.exe','.dll','.so','.lib','.exp','.pdb'))]
        assert binaries==['extension/native/runtime/windows-x64/bakoma-backend.exe'],binaries
    else:assert 'extension/native/runtime/bakoma-luahbtex' in archive.namelist()
report={'version':version,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
    'target':args.target,'verifiedPackagedFiles':checked,'runtimeSha256':hashlib.sha256((args.runtime/backend).read_bytes()).hexdigest()}
if not windows:report['compilerSha256']=hashlib.sha256((args.runtime/'bakoma-luahbtex').read_bytes()).hexdigest()
if windows:report['nativeBinaries']=binaries
if windows:
    standalone=ROOT/'artifacts'/f'bakoma-backend-{version}-win32-x64.exe'
    shutil.copyfile(args.runtime/backend,standalone)
    report['standalone']=standalone.name
(ROOT/'results'/f'package-{version}{suffix}.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
