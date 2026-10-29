"""Collect one validated macOS VSIX, corresponding sources and checksums."""
import hashlib
import json
from pathlib import Path
import shutil
from package_sources import verify_sources

ROOT = Path(__file__).resolve().parents[1]


def main():
    metadata = json.loads((ROOT/'native/runtime/macos-build.json').read_text())
    target = metadata['target']
    version = json.loads((ROOT/'package.json').read_text())['version']
    report = json.loads((ROOT/f'results/release-packages-{target}.json').read_text())
    original = ROOT/f'artifacts/texastra-{version}-{target}.vsix'
    assert report['version'] == version
    assert report['packages'][0]['sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
    sources = verify_sources(original)
    output = ROOT/'artifacts'/target
    output.mkdir(exist_ok=True)
    vsix = output/('texastra-macos-'+target.removeprefix('darwin-')+'.vsix')
    shutil.copyfile(original, vsix)
    source_zip = output/sources['file']
    shutil.copyfile(original.parent/sources['file'], source_zip)
    validation = output/'validation'
    validation.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'native/runtime/macos-build.json', validation/'macos-build.json')
    shutil.copyfile(ROOT/'native/runtime/pdftex-build.json', validation/'pdftex-build.json')
    for name in ['macos-runtime.json', 'macos-setup-native.json', 'pdftex.json', 'pdftex-hyphenation.json', 'pdftex-state.json', f'release-packages-{target}.json', f'package-{version}-{target}.json']:
        shutil.copyfile(ROOT/'results'/name, validation/name)
    sums = ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in [vsix, source_zip])
    (output/('SHA256SUMS-'+target)).write_text(sums)
    print(sums)


if __name__ == '__main__':
    main()
