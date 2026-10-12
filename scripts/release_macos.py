"""Collect one validated macOS VSIX, corresponding sources and checksums."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    metadata = json.loads((ROOT/'native/runtime/macos-build.json').read_text())
    target = metadata['target']
    version = json.loads((ROOT/'package.json').read_text())['version']
    report = json.loads((ROOT/f'results/release-packages-{target}.json').read_text())
    original = ROOT/f'artifacts/texastra-{version}-{target}.vsix'
    assert report['version'] == version
    assert report['packages'][0]['sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
    output = ROOT/'artifacts'/target
    output.mkdir(exist_ok=True)
    vsix = output/('texastra-macos-'+target.removeprefix('darwin-')+'.vsix')
    shutil.copyfile(original, vsix)
    source_zip = output/f'texastra-{target}-sources.zip'
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(filter(None, files)):
            archive.write(ROOT/name, 'texastra/'+name)
        for path in sorted((ROOT/'native/runtime/sources').iterdir()):
            if path.is_file():
                archive.write(path, 'upstream/'+path.name)
        archive.write(ROOT/'native/runtime/macos-build.json', 'validation/macos-build.json')
        for name in ['macos-runtime.json', f'release-packages-{target}.json', f'package-{version}-{target}.json']:
            archive.write(ROOT/'results'/name, 'validation/'+name)
    sums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in [vsix, source_zip])
    (output/('SHA256SUMS-'+target)).write_text(sums)
    print(sums)


if __name__ == '__main__':
    main()
