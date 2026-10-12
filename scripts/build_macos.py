"""Build a native macOS runtime and its complete dependency source kit."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

from build_cpp import fetch
from build_engine import ARCHIVES

ROOT = Path(__file__).resolve().parents[1]
WHEELS = {
    'arm64': ('72/74/448b6172927c829c6a3fba80078d7b0a016ebbe2c9ee528821f5ea21677a/pymupdf-1.26.7-cp310-abi3-macosx_11_0_arm64.whl',
              '31aa9c8377ea1eea02934b92f4dcf79fb2abba0bf41f8a46d64c3e31546a3c02'),
    'x86_64': ('94/35/cd74cea1787b2247702ef8522186bdef32e9cb30a099e6bb864627ef6045/pymupdf-1.26.7-cp310-abi3-macosx_10_9_x86_64.whl',
               '07085718dfdae5ab83b05eb5eb397f863bcc538fe05135318a01ea353e7a1353'),
}


def run(args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    arch = platform.machine()
    if sys.platform != 'darwin' or arch not in WHEELS:
        raise SystemExit('Run on an Apple Silicon or Intel Mac with native Python 3.11+ and Xcode Command Line Tools.')
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11+ is required')
    # First release deliberately targets the OS used by both CI runners.
    os.environ['MACOSX_DEPLOYMENT_TARGET'] = '15.0'
    os.environ.setdefault('CFLAGS', '-O2 -Wno-error=implicit-function-declaration -Wno-error=incompatible-function-pointer-types')
    os.environ.setdefault('CXXFLAGS', '-O2')
    build = ROOT/'.work'/('macos-'+arch)
    runtime = ROOT/'native/runtime'
    build.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    run([sys.executable, ROOT/'scripts/build_engine.py', '--runtime', runtime])
    header = fetch('https://cdn.jsdelivr.net/gh/nlohmann/json@v3.12.0/single_include/nlohmann/json.hpp',
                   build/'json.hpp', 'aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63')
    mupdf = fetch('https://www.mupdf.com/downloads/archive/mupdf-1.26.12-source.tar.gz',
                  build/'mupdf-1.26.12-source.tar.gz', '6baf910928f404167ba49be6340195dec340795724722b331f5aa0d01')
    deflate = fetch('https://codeload.github.com/ebiggers/libdeflate/tar.gz/refs/tags/v1.19',
                    build/'libdeflate-1.19.tar.gz', '27bf62d71cd64728ff43a9feb92f2ac2f2bf748986d856133cc1e51992428c25')
    for archive in (mupdf, deflate):
        with tarfile.open(archive) as source:
            source.extractall(build, filter='data')
    includes = next(build.glob('mupdf-*/include'))
    deflate_source = build/'libdeflate-1.19'
    run(['cmake', '-S', deflate_source, '-B', build/'deflate-build',
         '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0',
         '-DLIBDEFLATE_BUILD_SHARED_LIB=OFF', '-DLIBDEFLATE_BUILD_GZIP=OFF', '-DLIBDEFLATE_BUILD_TESTS=OFF'])
    run(['cmake', '--build', build/'deflate-build', '--parallel', '3'])
    name, digest = WHEELS[arch]
    wheel = fetch('https://files.pythonhosted.org/packages/'+name, build/'pymupdf.whl', digest)
    with zipfile.ZipFile(wheel) as source:
        names = [n for n in source.namelist() if Path(n).name.startswith('libmupdf.') and n.endswith('.dylib')]
        if len(names) != 1:
            raise RuntimeError('Expected exactly one MuPDF C library: '+str(names))
        library = runtime/Path(names[0]).name
        library.write_bytes(source.read(names[0]))
    run(['install_name_tool', '-id', '@rpath/'+library.name, library])
    run(['clang++', '-std=c++17', '-O2', '-pthread', '-Wall', '-Wextra',
         '-I'+str(build), '-I'+str(includes), '-I'+str(deflate_source), ROOT/'native/main.cpp',
         library, build/'deflate-build/libdeflate.a', '-lz', '-Wl,-rpath,@loader_path',
         '-o', runtime/'texastra-backend'])
    run(['clang', '-O2', '-bundle', '-undefined', 'dynamic_lookup', ROOT/'texastra/snapshot.c',
         '-o', runtime/'bako_snapshot.so'])
    for binary in (library, runtime/'texastra-backend', runtime/'texastra-luahbtex', runtime/'bako_snapshot.so'):
        run(['codesign', '--force', '--sign', '-', binary])
    sources = runtime/'sources'
    sources.mkdir(exist_ok=True)
    pymupdf = fetch('https://files.pythonhosted.org/packages/48/d6/09b28f027b510838559f7748807192149c419b30cb90e6d5f0cf916dc9dc/pymupdf-1.26.7.tar.gz',
                    build/'pymupdf-1.26.7.tar.gz', '71add8bdc8eb1aaa207c69a13400693f06ad9b927bea976f5d5ab9df0bb489c3')
    for source in [mupdf, pymupdf, deflate, header, *[runtime/n for n in ARCHIVES],
                   runtime/'LuaHBTeX-COPYING', *sorted((ROOT/'licenses').glob('*.txt'))]:
        shutil.copyfile(source, sources/source.name)
    shutil.copyfile(ROOT/'licenses/AGPL-3.0.txt', sources/'MuPDF-COPYING')
    (sources/'pymupdf-macos.sha256').write_text(digest+'\n')
    metadata = {'target': 'darwin-arm64' if arch == 'arm64' else 'darwin-x64',
                'minimumMacOS': '15.0', 'architecture': arch, 'signing': 'ad-hoc',
                'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources.iterdir()) if p.is_file()}}
    (runtime/'macos-build.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print('Built', metadata['target'], 'in', runtime)


if __name__ == '__main__':
    main()
