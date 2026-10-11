"""Cross-build the patched compiler as a native Windows x64 executable.

WSL is a build tool only. The resulting PE executable does not use WSL/MSYS/Cygwin.
Dependencies are installed in an isolated user cache, without changing apt state.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name == 'nt':
        script = subprocess.check_output(['wsl', '-d', 'Ubuntu-22.04', '--exec',
                                          'wslpath', '-a', str(Path(__file__).resolve())], text=True).strip()
        subprocess.run(['wsl', '-d', 'Ubuntu-22.04', '--exec', 'python3', script], check=True)
        return
    cache = Path.home() / '.cache/bakoma-windows-engine'
    packages = cache / 'packages'
    toolchain = cache / 'toolchain'
    source = cache / 'source'
    build = cache / 'build'
    for directory in (packages, toolchain, build):
        directory.mkdir(parents=True, exist_ok=True)
    if not (toolchain / 'usr/bin/x86_64-w64-mingw32-g++-posix').exists():
        names = ['binutils-mingw-w64-x86-64', 'mingw-w64-common', 'mingw-w64-x86-64-dev',
                 'gcc-mingw-w64-base', 'gcc-mingw-w64-x86-64-posix',
                 'gcc-mingw-w64-x86-64-posix-runtime', 'g++-mingw-w64-x86-64-posix']
        subprocess.run(['apt-get', 'download', *names], cwd=packages, check=True)
        for package in packages.glob('*.deb'):
            subprocess.run(['dpkg-deb', '-x', str(package), str(toolchain)], check=True)
    env = os.environ.copy()
    env['PATH'] = str(toolchain / 'usr/bin') + ':' + env['PATH']
    env['CC'] = str(toolchain / 'usr/bin/x86_64-w64-mingw32-gcc-posix')
    env['CXX'] = str(toolchain / 'usr/bin/x86_64-w64-mingw32-g++-posix')
    env['BUILDCC'] = 'gcc'
    env['BUILDCXX'] = 'g++'
    original = Path.home() / '.cache/bakoma-engine/source'
    if not source.exists():
        if not original.exists():
            subprocess.run([sys.executable, str(ROOT / 'scripts/build_engine.py'), '--source-only'], check=True)
        shutil.copytree(original, source, symlinks=True)
    # Ubuntu omits dependency source trees from its repacked archive. Recover
    # the missing libraries from the exact upstream SVN revision (r59705).
    upstream = cache / 'upstream-r59705.tar.gz'
    if not upstream.exists():
        print('Downloading matching upstream dependency sources', flush=True)
        urllib.request.urlretrieve('https://codeload.github.com/TeX-Live/texlive-source/tar.gz/'
                                   '7652969578ab227a3ae1774f0530f175e4a5abe2', upstream)
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != 'd759b7f1ec7f70bd48d0c2479046b7dab87c41f9a0d2d642e6d5900b73ab2856':
        raise RuntimeError('Upstream dependency source checksum mismatch')
    if not (source / '.bako-bundled-libraries').exists():
        existing = {p.name for p in (source / 'libs').iterdir()}
        with tarfile.open(upstream) as archive:
            for member in archive:
                parts = Path(member.name).parts[1:]
                if len(parts) < 2 or parts[0] != 'libs' or parts[1] in existing:
                    continue
                target = source.joinpath(*parts)
                if not target.resolve().is_relative_to(source.resolve()):
                    raise RuntimeError('Archive path escapes source')
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
                    target.chmod(member.mode)
                elif member.issym():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(member.linkname)
        (source / '.bako-bundled-libraries').write_text(hashlib.sha256(upstream.read_bytes()).hexdigest())
    sys.path.insert(0, str(ROOT / 'engine'))
    from patch import apply
    apply(source)
    # MinGW supplies _fullpath rather than POSIX realpath.
    origins = source / 'texk/web2c/luatexdir/origins.c'
    content = origins.read_text()
    content = '#ifdef _WIN32\n#define realpath(p,b) _fullpath(b,p,0)\n#endif\n' + content
    origins.write_text(content)
    sys.path.insert(0, str(ROOT / 'scripts'))
    from build_engine import FLAGS
    flags = [flag for flag in FLAGS if not flag.startswith('--with-system-')]
    flags += ['--host=x86_64-w64-mingw32', '--build=x86_64-pc-linux-gnu',
              '--disable-dvi2tty', '--disable-texdoctk', '--without-x',
              'CFLAGS=-O2 -g', 'CXXFLAGS=-O2 -g', 'LDFLAGS=-static -Wl,--stack,0x800000']
    signature = '\n'.join(flags)
    stamp = build / '.bako-configure'
    if not stamp.exists() or stamp.read_text() != signature:
        print('Configuring native Windows compiler:', build / 'configure.log', flush=True)
        with (build / 'configure.log').open('w') as log:
            subprocess.run([str(source / 'configure'), *flags], cwd=build, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        stamp.write_text(signature)
    print('Building native Windows compiler:', build / 'build.log', flush=True)
    with (build / 'build.log').open('w') as log:
        jobs = '-j12'
        library_flags = [
            'HARFBUZZ_INCLUDES=-I' + str(source / 'libs/harfbuzz/harfbuzz-src/src') +
            ' -I' + str(build / 'libs/harfbuzz'),
            'HARFBUZZ_LIBS=' + str(build / 'libs/harfbuzz/libharfbuzz.a'),
            'GRAPHITE2_INCLUDES=-I' + str(source / 'libs/graphite2/graphite2-src/include'),
            'GRAPHITE2_LIBS=' + str(build / 'libs/graphite2/libgraphite2.a'),
            'ZZIPLIB_LIBS=' + str(build / 'libs/zziplib/libzzip.a'),
        ]
        for command in [['make', 'all-local'], ['make', '-C', 'texk/kpathsea', jobs],
                        ['make', '-C', 'texk/ptexenc', jobs],
                        ['make', '-C', 'libs', jobs,
                         'CONF_SUBDIRS=zlib libpng zziplib graphite2 harfbuzz lua53 pplib',
                         'MAKE_SUBDIRS=zlib libpng zziplib graphite2 harfbuzz lua53 pplib'],
                        ['make', '-C', 'texk', jobs, 'all-local'],
                        ['make', '-C', 'texk/web2c', jobs, 'luahbtex.exe']]:
            subprocess.run(command + library_flags, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    runtime = ROOT / 'native/runtime/windows-x64'
    runtime.mkdir(parents=True, exist_ok=True)
    web2c = build / 'texk/web2c'
    objects = ['luatexdir/luahbtex-luatex.o', 'mplibdir/luahbtex-lmplib.o']
    libraries = ['libluahbtexspecific.a', 'libluatex.a', 'libff.a', 'libluamisc.a',
                 'libluasocket.a', 'libluaffi.a', 'libluaharfbuzz.a', 'libmplibcore.a',
                 'lib/lib.a', 'libmputil.a', 'libunilib.a', 'libmd5.a',
                 str(build / 'texk/kpathsea/.libs/libkpathsea.a')]
    for directory, archive in [('lua53', '.libs/libtexlua53.a'), ('zziplib', 'libzzip.a'),
                               ('libpng', 'libpng.a'), ('harfbuzz', 'libharfbuzz.a'),
                               ('graphite2', 'libgraphite2.a'), ('pplib', 'libpplib.a'),
                               ('zlib', 'libz.a')]:
        libraries.append(str(build / 'libs' / directory / archive))
    common_link = [env['CXX'], '-static', '-static-libgcc', '-static-libstdc++',
                   '-Wl,--stack,0x800000', *objects, '-Wl,--start-group', *libraries,
                   '-Wl,--end-group', '-lwsock32', '-lws2_32']
    subprocess.run([*common_link, '-o', str(runtime / 'bakoma-luahbtex.exe')], cwd=web2c, env=env, check=True)
    host_symbols = ['malloc', 'realloc', 'free', 'open', 'close', 'checkpoint', 'live',
                    'publish', 'park', 'now', 'stats', 'timings', 'io']
    host_def = build / 'host.def'
    host_def.write_text('LIBRARY bakoma-backend.exe\nEXPORTS\n' +
                        '\n'.join('bako_host_' + name for name in host_symbols) + '\n')
    host_lib = build / 'libbakoma-host.a'
    subprocess.run([str(toolchain / 'usr/bin/x86_64-w64-mingw32-dlltool'), '-d', str(host_def),
                    '-l', str(host_lib)], env=env, check=True)
    bridge = build / 'windows_bridge.o'
    subprocess.run([env['CC'], '-O2', '-g', '-I' + str(source / 'libs/lua53/lua53-src/src'),
                    '-c', str(ROOT / 'engine/windows_bridge.c'), '-o', str(bridge)], env=env, check=True)
    exports = build / 'engine.def'
    exports.write_text('EXPORTS\nbako_engine_main=main\n')
    wrapped = ['malloc', 'calloc', 'realloc', 'free', 'strdup', '_strdup', 'fopen', 'fclose', '_fullpath', 'fread', 'fwrite', '_read', '_write']
    wrapped += ['__imp_' + name for name in wrapped if name != 'strdup']
    wrapped += ['read', 'write']
    subprocess.run([*common_link, '-shared', str(bridge), str(host_lib), str(exports),
                    *['-Wl,--wrap=' + name for name in wrapped],
                    '-o', str(runtime / 'bakoma-engine.dll')], cwd=web2c, env=env, check=True)
    for name in ('bakoma-engine.dll', 'bakoma-luahbtex.exe'):
        subprocess.run([str(toolchain / 'usr/bin/x86_64-w64-mingw32-strip'), str(runtime / name)], env=env, check=True)
    print('Built', runtime / 'bakoma-luahbtex.exe', flush=True)


if __name__ == '__main__':
    main()
