"""Collect the two VSIX files, corresponding sources, and release checksums."""
import hashlib
import json
from pathlib import Path
import shutil
from package_sources import verify_sources

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = json.loads((ROOT/'package.json').read_text())['version']
    output = ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    names = []
    for source, name in [(f'texastra-{version}.vsix', 'texastra-wsl.vsix'),
                         (f'texastra-{version}-win32-x64.vsix', 'texastra-windows-x64.vsix')]:
        sources = verify_sources(output/source)
        shutil.copyfile(output/source, output/name)
        names.extend([name, sources['file']])
    checksums = ''.join(hashlib.sha256((output/name).read_bytes()).hexdigest()+'  '+name+'\n'
                        for name in names)
    (output/'SHA256SUMS').write_text(checksums)
    print(checksums, end='')


if __name__ == '__main__':
    main()
