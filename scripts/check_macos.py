"""Audit a built Mac runtime before packaging: architecture, signatures, dylibs."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'darwin':
        raise SystemExit('This check must run on macOS')
    runtime = ROOT/'native/runtime'
    metadata = json.loads((runtime/'macos-build.json').read_text())
    arch = platform.machine()
    assert metadata['architecture'] == arch, metadata
    pdftex = json.loads((runtime/'pdftex-build.json').read_text())
    assert pdftex['platform'] == 'darwin' and pdftex['architecture'] == arch, pdftex
    assert pdftex['engineSha256'] == hashlib.sha256((runtime/'texastra-pdftex').read_bytes()).hexdigest()
    assert (runtime/'pdfTeX-COPYING').is_file()
    binaries = [runtime/n for n in ['texastra-backend', 'texastra-luahbtex', 'texastra-pdftex', 'bako_snapshot.so']]
    binaries += list(runtime.glob('*.dylib'))
    assert len(binaries) == 5, binaries
    dependencies = {}
    for binary in binaries:
        architectures = subprocess.check_output(['lipo', '-archs', binary], text=True).split()
        assert architectures == [arch], (binary, architectures)
        subprocess.run(['codesign', '--verify', '--strict', binary], check=True)
        output = subprocess.check_output(['otool', '-L', binary], text=True)
        dependencies[binary.name] = []
        for line in output.splitlines()[1:]:
            dependency = line.strip().split(' (')[0]
            dependencies[binary.name].append(dependency)
            if dependency.startswith(('/usr/lib/', '/System/Library/')):
                continue
            assert dependency.startswith(('@rpath/', '@loader_path/')), (binary, dependency)
            assert (runtime/dependency.split('/', 1)[1]).is_file(), dependency
    report = {'ok': True, 'target': metadata['target'], 'minimumMacOS': metadata['minimumMacOS'],
              'testedMacOS': platform.mac_ver()[0], 'dependencies': dependencies,
              'pdftexSha256': pdftex['engineSha256']}
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/macos-runtime.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
