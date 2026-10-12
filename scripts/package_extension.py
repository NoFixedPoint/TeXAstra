"""Package a tested runtime without interrupting document sessions using another runtime."""
import argparse, hashlib, json, shutil, subprocess, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
for directory in ('.work','results','artifacts'):(ROOT/directory).mkdir(exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
parser.add_argument('--target',choices=['wsl','linux-x64','win32-x64','darwin-x64','darwin-arm64'],default='wsl',
                    help='wsl produces a VSIX installable in Windows VS Code with the bundled Linux runtime')
args=parser.parse_args()
windows=args.target=='win32-x64'
mac=args.target.startswith('darwin-')
if mac:
    metadata=json.loads((args.runtime/'macos-build.json').read_text())
    if metadata['target']!=args.target:raise SystemExit('Runtime architecture does not match requested VSIX target')
    unexpected=list(args.runtime.glob('libmupdf.so*'))+list(args.runtime.glob('*.exe'))+list(args.runtime.glob('*.dll'))
    if unexpected:raise SystemExit('Mixed-platform runtime directory; build macOS in a fresh checkout: '+str(unexpected))
backend='texastra-backend.exe' if windows else 'texastra-backend'
if not (args.runtime/backend).is_file():raise SystemExit('Build the selected native runtime before packaging')
for required in ['mupdf-1.26.12-source.tar.gz', 'pymupdf-1.26.7.tar.gz',
                 'AGPL-3.0.txt', 'GPL-3.0.txt',
                 'texlive-bin_2021.20210626.59705.orig.tar.xz',
                 'texlive-bin_2021.20210626.59705-1ubuntu0.3.debian.tar.xz']:
    if not (args.runtime/'sources'/required).is_file():
        raise SystemExit('Missing release source/license material: '+required+
                         '. Run scripts/release_sources.py after the platform source-kit build.')
if not windows and not (args.runtime/'texastra-luahbtex').is_file():raise SystemExit('Build the token-origin compiler first: python scripts/build_engine.py')
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
shutil.copytree(args.runtime.resolve(),destination,ignore=shutil.ignore_patterns('*.new','bako_internal.so','windows-x64','bakoma-*'))
manifest=json.loads((stage/'package.json').read_text(encoding='utf-8'))
runtime_setting=manifest['contributes']['configuration']['properties']['texastra.runtimeMode']
runtime_setting['default']='native' if windows or mac else 'wsl'
if windows:runtime_setting['description']='Windows: use the bundled native Windows backend by default. WSL requires a separately installed Linux runtime. Reopen the document after changing.'
(stage/'package.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
suffix='' if args.target=='wsl' else '-'+args.target
artifact=ROOT/'artifacts'/f'texastra-{version}{suffix}.vsix'
target_args=[] if args.target=='wsl' else ['--target',args.target]
subprocess.run([shutil.which('npx.cmd') or shutil.which('npx'),'--yes','@vscode/vsce@4.0.0','package',
    '--no-rewrite-relative-links',*target_args,'--out',str(artifact)],cwd=stage,check=True)
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
    assert not any('bakoma' in name.lower() or '/prototype/' in name for name in archive.namelist())
    assert not any(name.startswith('extension/docs/') for name in archive.namelist())
    assert json.loads(archive.read('extension/package.json'))['contributes']['configuration']['properties']['texastra.runtimeMode']['default']==('native' if windows or mac else 'wsl')
    if args.target=='wsl':assert b'TargetPlatform=' not in archive.read('extension.vsixmanifest')
    assert 'extension/native/runtime/bako_internal.so' not in archive.namelist()
    if windows:
        binaries=[name for name in archive.namelist() if name.lower().endswith(('.exe','.dll','.so','.lib','.exp','.pdb'))]
        assert binaries==['extension/native/runtime/windows-x64/texastra-backend.exe'],binaries
    else:
        assert 'extension/native/runtime/texastra-luahbtex' in archive.namelist()
        assert not any(name.endswith(('.exe','.dll')) for name in archive.namelist())
report={'version':version,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
    'target':args.target,'defaultRuntimeMode':runtime_setting['default'],'verifiedPackagedFiles':checked,'runtimeSha256':hashlib.sha256((args.runtime/backend).read_bytes()).hexdigest()}
if not windows:report['compilerSha256']=hashlib.sha256((args.runtime/'texastra-luahbtex').read_bytes()).hexdigest()
if windows:report['nativeBinaries']=binaries
if windows:
    standalone=ROOT/'artifacts'/f'texastra-backend-{version}-win32-x64.exe'
    shutil.copyfile(args.runtime/backend,standalone)
    report['standalone']=standalone.name
(ROOT/'results'/f'package-{version}{suffix}.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
