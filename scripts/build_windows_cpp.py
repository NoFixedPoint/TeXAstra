"""Build the native Windows controller/renderer with MSVC."""
import hashlib
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from build_cpp import fetch
from check_windows_checkpoint import toolchain

ROOT = Path(__file__).resolve().parents[1]


def main():
    binary, env, _, _ = toolchain()
    build = ROOT / '.work/windows-cpp'
    runtime = ROOT / 'native/runtime/windows-x64'
    build.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    shared = ROOT / '.work/cpp-build'
    shared.mkdir(parents=True, exist_ok=True)
    fetch('https://cdn.jsdelivr.net/gh/nlohmann/json@v3.12.0/single_include/nlohmann/json.hpp',
          shared / 'json.hpp', 'aaf127c04cb31c406e5b04a63f1ae89369fccde6d8fa7cdda1ed4f32dfc5de63')
    archive = fetch('https://codeload.github.com/ArtifexSoftware/mupdf/tar.gz/refs/tags/1.26.12',
                    shared / 'mupdf-1.26.12.tar.gz', 'e6247e1c6216ca8ec5863848a082ce121773074dfc2f34b0b7c7a4de4ff5172e')
    if not (shared / 'include/mupdf/fitz.h').exists():
        with tarfile.open(archive) as source:
            for item in source:
                parts = Path(item.name).parts[1:]
                if parts and parts[0] == 'include' and item.isfile():
                    target = shared.joinpath(*parts)
                    if not target.resolve().is_relative_to(shared.resolve()):
                        raise RuntimeError('Archive path escapes build')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.extractfile(item).read())
    wheel = fetch('https://files.pythonhosted.org/packages/dd/c3/d0047678146c294469c33bae167c8ace337deafb736b0bf97b9bc481aa65/pymupdf-1.26.7-cp310-abi3-win_amd64.whl',
                  build / 'pymupdf.whl', '425b1befe40d41b72eb0fe211711c7ae334db5eb60307e9dd09066ed060cceba')
    with zipfile.ZipFile(wheel) as source:
        (runtime / 'mupdfcpp64.dll').write_bytes(source.read('pymupdf/mupdfcpp64.dll'))
    exports = subprocess.check_output([str(binary / 'dumpbin.exe'), '/exports', str(runtime / 'mupdfcpp64.dll')], env=env, text=True)
    names = re.findall(r'^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+([A-Za-z_]\w*)\s*$', exports, re.MULTILINE)
    definition = build / 'mupdf.def'
    definition.write_text('LIBRARY mupdfcpp64.dll\nEXPORTS\n' + '\n'.join(names) + '\n')
    subprocess.run([str(binary / 'lib.exe'), '/nologo', '/def:' + str(definition), '/machine:x64',
                    '/out:' + str(build / 'mupdf.lib')], env=env, check=True)
    deflate = fetch('https://codeload.github.com/ebiggers/libdeflate/tar.gz/refs/tags/v1.19', build / 'libdeflate-1.19.tar.gz',
                    '27bf62d71cd64728ff43a9feb92f2ac2f2bf748986d856133cc1e51992428c25')
    deflate_source = build / 'libdeflate-1.19'
    if not deflate_source.exists():
        with tarfile.open(deflate) as source:
            source.extractall(build, filter='data')
    cmake_root = binary.parents[6] / 'Common7/IDE/CommonExtensions/Microsoft/CMake'
    cmake = cmake_root / 'CMake/bin/cmake.exe'
    ninja = cmake_root / 'Ninja/ninja.exe'
    deflate_build = build / 'deflate-build'
    subprocess.run([str(cmake), '-S', str(deflate_source), '-B', str(deflate_build), '-G', 'Ninja',
                    '-DCMAKE_MAKE_PROGRAM=' + str(ninja), '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded', '-DLIBDEFLATE_BUILD_SHARED_LIB=OFF',
                    '-DLIBDEFLATE_BUILD_GZIP=OFF', '-DLIBDEFLATE_BUILD_TESTS=OFF'], env=env, check=True)
    subprocess.run([str(cmake), '--build', str(deflate_build)], env=env, check=True)
    deflate_lib = next(deflate_build.glob('*.lib'))
    manifest = build / 'backend.manifest'
    manifest.write_text('''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
<application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings>
<activeCodePage xmlns="http://schemas.microsoft.com/SMI/2019/WindowsSettings">UTF-8</activeCodePage>
<longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
</windowsSettings></application></assembly>''')
    subprocess.run([str(binary / 'cl.exe'), '/nologo', '/std:c++17', '/EHsc', '/O2', '/MT', '/utf-8',
                    '/D_CRT_SECURE_NO_WARNINGS', '/I' + str(shared), '/I' + str(shared / 'include'),
                    '/I' + str(deflate_source), str(ROOT / 'native/main.cpp'),
                    str(ROOT / 'native/windows/compiler_worker.cpp'), '/Fo' + str(build) + '\\',
                    '/Fe:' + str(runtime / 'texastra-backend.exe'), '/link', '/STACK:8388608',
                    '/MANIFEST:EMBED', '/MANIFESTINPUT:' + str(manifest), str(build / 'mupdf.lib'), str(deflate_lib)],
                   env=env, cwd=build, check=True)
    # The pinned MuPDF wheel uses Microsoft's redistributable C++ runtime.
    redist = binary.parents[5] / 'Redist/MSVC'
    for folder in sorted(redist.glob('*/x64/Microsoft.VC143.CRT'), reverse=True):
        for dll in folder.glob('*.dll'):
            shutil.copyfile(dll, runtime / dll.name)
        break
    print('Built', runtime / 'texastra-backend.exe')
    print('libdeflate SHA256', hashlib.sha256(deflate.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
