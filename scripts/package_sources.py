"""Pair a small VSIX with its immutable, separately downloadable source kit."""
import hashlib
import json
from pathlib import Path
import zipfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def is_archive(path):
    return path.name.endswith(('.tar.gz', '.tar.xz', '.tar.bz2', '.tgz', '.zip', '.whl'))


def prepare_sources(stage, runtime, output, version, target):
    """Save project and upstream sources before removing archives from staging."""
    source_zip = output/f'texastra-{version}-{target}-sources.zip'
    materials = runtime/'sources'
    # Older engine builds also put these archives at the runtime root. Verify
    # their source-kit copies before dropping the redundant runtime copies.
    for path in runtime.iterdir():
        if path.is_file() and is_archive(path):
            if not (materials/path.name).is_file() or sha256(path) != sha256(materials/path.name):
                raise RuntimeError('Missing or mismatched source-kit copy: '+path.name)
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob('*')):
            relative = path.relative_to(stage)
            if path.is_file() and relative.parts[:2] != ('native', 'runtime'):
                archive.write(path, 'texastra/'+relative.as_posix())
        for path in sorted(materials.rglob('*')):
            if path.is_file():
                archive.write(path, 'upstream/'+path.relative_to(materials).as_posix(),
                              compress_type=zipfile.ZIP_STORED if is_archive(path) else zipfile.ZIP_DEFLATED)
        for name in ('macos-build.json', 'pdftex-build.json'):
            if (runtime/name).is_file():
                archive.write(runtime/name, 'validation/'+name)
    metadata = {
        'version': version, 'target': target, 'file': source_zip.name,
        'sha256': sha256(source_zip), 'sizeBytes': source_zip.stat().st_size,
        'url': f'https://github.com/NoFixedPoint/TeXAstra/releases/download/v{version}/{source_zip.name}',
    }
    (stage/'SOURCE.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    (stage/'SOURCE.md').write_text(
        '# Corresponding source\n\n'
        f'TeXAstra {version} ({target}): [{source_zip.name}]({metadata["url"]}).\n\n'
        'This separate download contains the matching project source, build recipes,\n'
        'and pinned dependency source archives. It is not needed to run the extension.\n'
        'Publish it alongside the VSIX at the URL above, with equivalent access at no\n'
        'additional charge. Preserve both files when redistributing this release.\n\n'
        f'SHA-256: `{metadata["sha256"]}`\n', encoding='utf-8')
    for path in runtime.rglob('*'):
        if path.is_file() and is_archive(path):
            path.unlink()
    return metadata


def verify_sources(vsix):
    """Reject collecting/testing a VSIX without its exact companion source ZIP."""
    with zipfile.ZipFile(vsix) as archive:
        metadata = json.loads(archive.read('extension/SOURCE.json'))
        manifest = json.loads(archive.read('extension/package.json'))
        if metadata['version'] != manifest['version']:
            raise RuntimeError('Source version does not match VSIX')
        if any(is_archive(Path(name)) for name in archive.namelist()
               if name.startswith('extension/native/runtime/')):
            raise RuntimeError('Build archives leaked into the runtime package')
    name = metadata['file']
    if Path(name).name != name:
        raise RuntimeError('Source archive name must be a filename')
    source = vsix.parent/name
    if not source.is_file() or sha256(source) != metadata['sha256']:
        raise RuntimeError('Missing or modified companion source archive: '+str(source))
    return metadata
