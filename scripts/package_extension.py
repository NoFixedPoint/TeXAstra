"""Package a tested runtime without interrupting previews using another runtime."""
import argparse, hashlib, json, shutil, subprocess, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
args=parser.parse_args()
version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
stage=Path(tempfile.mkdtemp(prefix='package-',dir=ROOT/'.work'))
files=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
for name in set(files):
    if not name or Path(name).parts[0] in {'corpus','results','artifacts'}:continue
    source=ROOT/name
    if not source.is_file():continue
    target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
shutil.copytree(args.runtime.resolve(),stage/'native/runtime',ignore=shutil.ignore_patterns('*.new'))
artifact=ROOT/'artifacts'/f'bakoma-revived-prototype-{version}.vsix'
subprocess.run([shutil.which('npx.cmd') or shutil.which('npx'),'--yes','@vscode/vsce','package',
    '--allow-missing-repository','--no-rewrite-relative-links','--skip-license','--out',str(artifact)],cwd=stage,check=True)
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
report={'version':version,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
    'verifiedPackagedFiles':checked,'runtimeSha256':hashlib.sha256((args.runtime/'bakoma-backend').read_bytes()).hexdigest()}
(ROOT/'results'/f'package-{version}.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
