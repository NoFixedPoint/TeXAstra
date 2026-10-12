"""Collect the two VSIX files, corresponding sources, and release checksums."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = json.loads((ROOT/'package.json').read_text())['version']
    output = ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    for source, name in [(f'texastra-{version}.vsix', 'texastra-wsl.vsix'),
                         (f'texastra-{version}-win32-x64.vsix', 'texastra-windows-x64.vsix')]:
        shutil.copyfile(output/source, output/name)
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    with zipfile.ZipFile(output/'texastra-sources.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(filter(None, files)):
            archive.write(ROOT/name, 'texastra/'+name)
        for platform, directory in [('wsl', 'native/runtime/sources'),
                                    ('windows-x64', 'native/windows-bundle/sources')]:
            materials = ROOT/directory
            if not (materials/'pymupdf-1.26.7.tar.gz').is_file():
                raise RuntimeError('Run scripts/release_sources.py before collecting releases')
            for path in sorted(materials.rglob('*')):
                if path.is_file():
                    archive.write(path, 'upstream/'+platform+'/'+path.relative_to(materials).as_posix())
    names = ['texastra-wsl.vsix', 'texastra-windows-x64.vsix', 'texastra-sources.zip']
    checksums = ''.join(hashlib.sha256((output/name).read_bytes()).hexdigest()+'  '+name+'\n'
                        for name in names)
    (output/'SHA256SUMS').write_text(checksums)
    print(checksums, end='')


if __name__ == '__main__':
    main()
