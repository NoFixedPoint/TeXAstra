"""Build/run the native Windows checkpoint proof with MSVC and static CRT.

This produces a standalone validation executable, not the preview backend.
No WSL, Python runtime, or non-system DLL is required by the resulting EXE.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def toolchain():
    if os.name != 'nt':
        raise SystemExit('This check requires native Windows x64 and Visual Studio C++ tools.')
    import winreg
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / \
        'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output([
        str(vswhere), '-latest', '-products', '*', '-requires',
        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'
    ], text=True).strip()
    if not installation:
        raise SystemExit('Install Visual Studio C++ x64 build tools and a Windows SDK.')
    version_key = lambda path: tuple(int(n) for n in path.name.split('.'))
    msvc = max((Path(installation) / 'VC/Tools/MSVC').iterdir(), key=version_key)
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                       r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
        sdk = Path(winreg.QueryValueEx(key, 'KitsRoot10')[0])
    sdk_include = max((p for p in (sdk / 'Include').iterdir()
                       if (p / 'um/Windows.h').is_file() and
                       (sdk / 'Lib' / p.name / 'um/x64/kernel32.lib').is_file()), key=version_key)
    binary = msvc / 'bin/Hostx64/x64'
    env = os.environ.copy()
    env['PATH'] = os.pathsep.join([str(binary), str(sdk / 'bin' / sdk_include.name / 'x64'), env['PATH']])
    env['INCLUDE'] = os.pathsep.join(str(p) for p in [msvc / 'include', *[
        sdk_include / part for part in ('ucrt', 'shared', 'um')]])
    env['LIB'] = os.pathsep.join(str(p) for p in [msvc / 'lib/x64', *[
        sdk / 'Lib' / sdk_include.name / part / 'x64' for part in ('ucrt', 'um')]])
    # Respect neither injected compiler options nor inherited SDK overrides.
    env.pop('CL', None)
    env.pop('_CL_', None)
    return binary, env, msvc.name, sdk_include.name


def main():
    binary, env, msvc, sdk = toolchain()
    build = ROOT / '.work/windows-checkpoint'
    build.mkdir(parents=True, exist_ok=True)
    exe = build / 'check-checkpoint.exe'
    source = ROOT / 'native/windows/check_checkpoint.cpp'
    subprocess.run([str(binary / 'cl.exe'), '/nologo', '/std:c++17', '/EHsc', '/O2', '/MT',
                    '/W4', '/WX', '/utf-8', str(source), '/Fe:' + str(exe),
                    '/Fo:' + str(build / 'check-checkpoint.obj'), '/link', '/INCREMENTAL:NO'],
                   env=env, cwd=build, check=True)
    report = json.loads(subprocess.check_output([str(exe)], text=True, timeout=120))
    continuation = build / 'check-continuation.exe'
    subprocess.run([str(binary / 'cl.exe'), '/nologo', '/std:c++17', '/EHsc', '/O2', '/MT',
                    '/W4', '/WX', '/utf-8', str(ROOT / 'native/windows/check_continuation.cpp'),
                    '/Fe:' + str(continuation), '/Fo:' + str(build / 'check-continuation.obj'),
                    '/link', '/STACK:8388608'], env=env, cwd=build, check=True)
    report['continuation'] = json.loads(subprocess.check_output([str(continuation)], text=True, timeout=30))
    report['faultIsolation'] = {}
    for mode in ('foreign-thread', 'unrelated', 'execute'):
        result = subprocess.run([str(exe), '--' + mode + '-fault'], capture_output=True, timeout=10)
        status = result.returncode & 0xffffffff
        if status != 0xc0000005:
            raise RuntimeError(f'{mode} fault was not propagated: {status:#x}')
        report['faultIsolation'][mode] = 'access violation propagated'
    dependencies = subprocess.check_output([str(binary / 'dumpbin.exe'), '/DEPENDENTS', str(exe)],
                                           env=env, text=True)
    dlls = sorted(set(re.findall(r'^\s+([\w.-]+\.dll)\s*$', dependencies, re.MULTILINE | re.IGNORECASE)))
    if not dlls or any(dll.lower() != 'kernel32.dll' for dll in dlls):
        raise RuntimeError('Unexpected standalone executable dependencies: ' + repr(dlls))
    cpu = subprocess.check_output(['powershell', '-NoProfile', '-Command',
                                  '(Get-CimInstance Win32_Processor).Name'], text=True).strip()
    report.update(platform=platform.platform(), architecture=platform.machine(), cpu=cpu,
                  msvc=msvc, windowsSDK=sdk, dependentDLLs=dlls,
                  executableSha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
                  sourceSha256={str(path.relative_to(ROOT)).replace('\\', '/'):
                                hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in [source, source.with_name('checkpoint_arena.hpp')]})
    destination = ROOT / 'results/windows-checkpoint.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
