"""Prepare matching upstream source and notices for both release variants."""
import hashlib
import json
from pathlib import Path
import shutil

from build_cpp import fetch
from build_engine import ARCHIVES

ROOT = Path(__file__).resolve().parents[1]


def main():
    work = ROOT/'.work/release-sources'
    work.mkdir(parents=True, exist_ok=True)
    mupdf = fetch('https://www.mupdf.com/downloads/archive/mupdf-1.26.12-source.tar.gz',
                  ROOT/'.work/windows-cpp/mupdf-1.26.12-source.tar.gz',
                  '6baf910928f404167ba49be6340195dec340795724722b331f5a2143f5aa0d01')
    pymupdf = fetch('https://files.pythonhosted.org/packages/48/d6/09b28f027b510838559f7748807192149c419b30cb90e6d5f0cf916dc9dc/pymupdf-1.26.7.tar.gz',
                    work/'pymupdf-1.26.7.tar.gz',
                    '71add8bdc8eb1aaa207c69a13400693f06ad9b927bea976f5d5ab9df0bb489c3')
    common = [mupdf, pymupdf, ROOT/'.work/cpp-build/json.hpp']
    linux_sources = ROOT/'native/runtime/sources'
    linux_sources.mkdir(parents=True, exist_ok=True)
    for name in [*ARCHIVES, 'LuaHBTeX-COPYING']:
        shutil.copyfile(ROOT/'native/runtime'/name, linux_sources/name)
    for destination in [ROOT/'native/runtime/sources', ROOT/'native/windows-bundle/sources']:
        destination.mkdir(parents=True, exist_ok=True)
        for source in common:
            shutil.copyfile(source, destination/source.name)
        shutil.copyfile(ROOT/'licenses/AGPL-3.0.txt', destination/'MuPDF-COPYING')
        for source in (ROOT/'licenses').glob('*.txt'):
            shutil.copyfile(source, destination/source.name)
    # Record binary-wheel identities alongside their matching source/build recipes.
    for wheel, destination in [(ROOT/'.work/cpp-build/pymupdf.whl', ROOT/'native/runtime/sources/pymupdf-linux.whl'),
                               (ROOT/'.work/windows-cpp/pymupdf.whl', ROOT/'native/windows-bundle/sources/pymupdf-windows.whl')]:
        # Record artifact identity without redistributing a redundant binary wheel.
        destination.with_suffix('.sha256').write_text(hashlib.sha256(wheel.read_bytes()).hexdigest()+'\n')
    source_files = {}
    for directory in [ROOT/'native/runtime/sources', ROOT/'native/windows-bundle/sources']:
        for file in sorted(directory.iterdir()):
            if file.is_file():
                source_files[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    (work/'manifest.json').write_text(json.dumps(source_files, indent=2)+'\n')
    print('Prepared source materials:', len(source_files))


if __name__ == '__main__':
    main()
