"""Collect smaller packages using existing release asset names and source links.

Only SOURCE.json and SOURCE.md change in each previously tested VSIX. Every
other file, including executable permissions and signatures, is verified intact.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import zipfile

from package_sources import sha256, verify_sources


def rebind(vsix, output, source, prefix=''):
    metadata = verify_sources(vsix)
    metadata.update(file=source.name, sha256=sha256(source), sizeBytes=source.stat().st_size,
                    prefix=prefix)
    metadata['url'] = (f'https://github.com/NoFixedPoint/TeXAstra/releases/download/'
                       f'v{metadata["version"]}/{source.name}')
    replacements = {
        'extension/SOURCE.json': (json.dumps(metadata, indent=2)+'\n').encode(),
        'extension/SOURCE.md': (
            '# Corresponding source\n\n'
            f'TeXAstra {metadata["version"]} ({metadata["target"]}): '
            f'[{source.name}]({metadata["url"]}).\n\n'
            'The archive contains matching project source, build recipes, licenses,\n'
            'and dependency sources. It is not needed to run the extension.\n'
            + (f'Use the `{prefix}` directory for this platform.\n' if prefix else '')
            + '\nPublish the source archive alongside its VSIX with equivalent access\n'
            'at no additional charge. Preserve both when redistributing this release.\n\n'
            f'SHA-256: `{metadata["sha256"]}`\n').encode(),
    }
    with zipfile.ZipFile(vsix) as original, zipfile.ZipFile(output, 'w') as result:
        for item in original.infolist():
            result.writestr(item, replacements.get(item.filename, original.read(item)))
    with zipfile.ZipFile(vsix) as original, zipfile.ZipFile(output) as result:
        assert result.testzip() is None
        assert original.namelist() == result.namelist()
        for item in original.infolist():
            if item.filename not in replacements:
                assert original.read(item) == result.read(item.filename), item.filename
                assert item.external_attr == result.getinfo(item.filename).external_attr
    assert verify_sources(output) == metadata
    return {'file': output.name, 'sizeBytes': output.stat().st_size, 'sha256': sha256(output),
            'testedVsixSha256': sha256(vsix), 'onlySourceReferencesChanged': True,
            'sourceArchive': metadata}


def combine_sources(packages, destination):
    with zipfile.ZipFile(destination, 'w') as result:
        result.writestr(zipfile.ZipInfo('README.txt'), 'Use wsl/ or win32-x64/ for the corresponding platform.\n'
                        'Each directory includes texastra/ project sources and upstream/ dependencies.\n')
        for target, vsix in packages:
            metadata = verify_sources(vsix)
            with zipfile.ZipFile(vsix.parent/metadata['file']) as source:
                assert source.testzip() is None
                for item in source.infolist():
                    renamed = copy.copy(item)
                    renamed.filename = target+'/'+item.filename
                    result.writestr(renamed, source.read(item))
    with zipfile.ZipFile(destination) as result:
        assert result.testzip() is None
        for target, vsix in packages:
            metadata = verify_sources(vsix)
            with zipfile.ZipFile(vsix.parent/metadata['file']) as source:
                for item in source.infolist():
                    assert source.read(item) == result.read(target+'/'+item.filename)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for target in ('wsl', 'win32-x64', 'darwin-arm64', 'darwin-x64'):
        parser.add_argument('--'+target, type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    packages = [(target, getattr(args, target.replace('-', '_')).resolve())
                for target in ('wsl', 'win32-x64', 'darwin-arm64', 'darwin-x64')]
    for target, vsix in packages:
        metadata = verify_sources(vsix)
        assert metadata['target'] == target and metadata['version'] == '0.1.5'
        assert vsix.parent != output, 'Use a separate release output directory'
    combined = output/'texastra-sources.zip'
    combine_sources(packages[:2], combined)
    names = {'wsl': 'texastra-wsl.vsix', 'win32-x64': 'texastra-windows-x64.vsix',
             'darwin-arm64': 'texastra-macos-arm64.vsix', 'darwin-x64': 'texastra-macos-x64.vsix'}
    report = {'version': '0.1.5', 'packages': []}
    for target, vsix in packages:
        if target.startswith('darwin-'):
            metadata = verify_sources(vsix)
            source = output/f'texastra-{target}-sources.zip'
            shutil.copyfile(vsix.parent/metadata['file'], source)
            prefix = ''
        else:
            source, prefix = combined, target+'/'
        package = output/names[target]
        report['packages'].append(rebind(vsix, package, source, prefix))
        if target.startswith('darwin-'):
            (output/f'SHA256SUMS-{target}').write_text(''.join(
                sha256(path)+'  '+path.name+'\n' for path in (package, source)), encoding='utf-8')
    assets = sorted([output/name for name in names.values()]+[combined]+
                    [output/f'texastra-{target}-sources.zip' for target, _ in packages[2:]])
    (output/'SHA256SUMS').write_text(''.join(sha256(p)+'  '+p.name+'\n' for p in assets), encoding='utf-8')
    (output/'collection.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
