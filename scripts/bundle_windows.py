"""Embed the native compiler and renderer into one relocatable Windows EXE."""
import hashlib
import struct
import shutil
import subprocess
import zlib
from pathlib import Path
from check_windows_checkpoint import toolchain

ROOT = Path(__file__).resolve().parents[1]


def main():
    binary, env, _, _ = toolchain()
    build = ROOT / '.work/windows-cpp'
    runtime = ROOT / 'native/runtime/windows-x64'
    output = ROOT / 'native/windows-bundle'
    output.mkdir(parents=True, exist_ok=True)
    names = ['bakoma-backend.exe', 'bakoma-engine.dll', 'mupdfcpp64.dll',
             'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll']
    files = {name: runtime / name for name in names}
    for name in ('snapshot.lua', 'inputs.lua', 'provenance.lua', 'page_stream.lua'):
        files[name] = ROOT / 'prototype' / name
    payload = bytearray(b'BAKOWIN1' + struct.pack('<I', len(files)))
    for name, path in files.items():
        data = path.read_bytes()
        compressed = zlib.compress(data, 9)
        encoded = name.encode('ascii')
        payload += struct.pack('<III', len(encoded), len(data), len(compressed))
        payload += hashlib.sha256(data).digest() + encoded + compressed
    (build / 'payload.bin').write_bytes(payload)
    identity = hashlib.sha256(payload).hexdigest()
    (build / 'payload_identity.hpp').write_text('#define BAKO_PAYLOAD_SHA256 "' + identity + '"\n')
    (build / 'payload.rc').write_text('101 RCDATA "payload.bin"\n')
    subprocess.run([shutil.which('rc.exe', path=env['PATH']), '/nologo', 'payload.rc'], cwd=build, env=env, check=True)
    subprocess.run([str(binary / 'cl.exe'), '/nologo', '/std:c++17', '/EHsc', '/O2', '/MT', '/utf-8',
                    '/D_CRT_SECURE_NO_WARNINGS', '/I' + str(build), '/I' + str(build / 'libdeflate-1.19'),
                    str(ROOT / 'native/windows/bootstrap.cpp'), '/Fo' + str(build / 'bootstrap.obj'),
                    '/Fe:' + str(output / 'bakoma-backend.exe'), '/link',
                    str(build / 'payload.res'), str(build / 'deflate-build/deflatestatic.lib'), 'bcrypt.lib',
                    '/MANIFEST:EMBED', '/MANIFESTINPUT:' + str(build / 'backend.manifest')],
                   cwd=build, env=env, check=True)
    print('Bundled', output / 'bakoma-backend.exe', 'payload', identity)


if __name__ == '__main__':
    main()
