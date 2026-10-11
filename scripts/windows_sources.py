"""Assemble pinned compiler source archives and licenses for the Windows VSIX."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import sys
import zipfile
from build_cpp import fetch
from build_engine import ARCHIVES

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name == 'nt':
        script = subprocess.check_output(['wsl', '-d', 'Ubuntu-22.04', '--exec', 'wslpath', '-a', str(Path(__file__).resolve())], text=True).strip()
        subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--exec', 'python3', script], check=True)
        target = ROOT / 'native/windows-bundle/sources'
        build = ROOT / '.work/windows-cpp'
        source = fetch('https://www.mupdf.com/downloads/archive/mupdf-1.26.12-source.tar.gz',
                       build / 'mupdf-1.26.12-source.tar.gz',
                       '6baf910928f404167ba49be6340195dec340795724722b331f5a2143f5aa0d01')
        shutil.copyfile(source, target / source.name)
        with zipfile.ZipFile(build / 'pymupdf.whl') as archive:
            (target / 'MuPDF-COPYING').write_bytes(archive.read('pymupdf-1.26.7.dist-info/COPYING'))
        for origin, name in [(build / 'libdeflate-1.19.tar.gz', 'libdeflate-1.19.tar.gz'),
                             (build / 'libdeflate-1.19/COPYING', 'libdeflate-COPYING'),
                             (ROOT / '.work/cpp-build/json.hpp', 'json.hpp')]:
            shutil.copyfile(origin, target / name)
        return
    target = ROOT / 'native/windows-bundle/sources'
    target.mkdir(parents=True, exist_ok=True)
    compiler_cache = Path.home() / '.cache/bakoma-engine'
    for name, expected in ARCHIVES.items():
        data = (compiler_cache / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('Compiler source checksum mismatch: ' + name)
        (target / name).write_bytes(data)
    cache = Path.home() / '.cache/bakoma-windows-engine'
    source = cache / 'source'
    # The Ubuntu archive removes bundled libraries. These exact upstream
    # sources supplement it; engine/ and the build recipes are in the VSIX.
    output = target / 'windows-engine-libraries.tar.xz'
    if not output.exists():
        with tarfile.open(output, 'w:xz') as archive:
            for name in ('zlib', 'libpng', 'zziplib', 'graphite2', 'harfbuzz', 'lua53', 'pplib'):
                archive.add(source / 'libs' / name, arcname='libs/' + name)
    shutil.copyfile('/usr/share/common-licenses/GPL-2', target / 'LuaHBTeX-COPYING')
    for directory in (cache / 'toolchain/usr/share/doc').iterdir():
        copyright = directory / 'copyright'
        if copyright.is_file():
            shutil.copyfile(copyright, target / (directory.name + '-COPYRIGHT'))
    print('Prepared Windows compiler source kit', target)


if __name__ == '__main__':
    main()
