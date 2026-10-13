"""Restore a Mac runtime from a pinned legacy VSIX containing its source kit."""
import argparse
from pathlib import Path
import zipfile

from package_sources import sha256


def restore(vsix, digest, destination):
    if sha256(vsix) != digest:
        raise RuntimeError('Published VSIX checksum mismatch')
    destination = destination.resolve()
    if destination.exists():
        raise RuntimeError('Restore into a fresh runtime directory')
    prefix = 'extension/native/runtime/'
    with zipfile.ZipFile(vsix) as archive:
        assert archive.testzip() is None
        for item in archive.infolist():
            if not item.filename.startswith(prefix) or item.is_dir():
                continue
            path = destination/item.filename[len(prefix):]
            if not path.resolve().is_relative_to(destination):
                raise RuntimeError('Archive path escapes runtime directory')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(item))
            if item.external_attr >> 16 & 0o111:
                path.chmod(0o755)
    assert (destination/'macos-build.json').is_file()
    assert (destination/'texastra-backend').is_file()
    assert (destination/'sources/pymupdf-1.26.7.tar.gz').is_file(), 'Use the original full-source VSIX'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vsix', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--destination', type=Path, default=Path('native/runtime'))
    args = parser.parse_args()
    restore(args.vsix, args.sha256, args.destination)
