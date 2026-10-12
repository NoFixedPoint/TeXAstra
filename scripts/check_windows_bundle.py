"""Validate the one-file runtime without WSL/Python/runtime DLLs on its PATH."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from check_windows_checkpoint import toolchain

ROOT = Path(__file__).resolve().parents[1]


def main():
    binary, build_env, _, _ = toolchain()
    source = ROOT / 'native/windows-bundle/texastra-backend.exe'
    imports = subprocess.check_output([str(binary / 'dumpbin.exe'), '/DEPENDENTS', str(source)], env=build_env, text=True)
    dlls = sorted(set(re.findall(r'^\s+([\w.-]+\.dll)\s*$', imports, re.MULTILINE | re.IGNORECASE)))
    assert {name.lower() for name in dlls} <= {'kernel32.dll', 'bcrypt.dll'}, dlls
    original = json.loads(subprocess.check_output([str(source), '--environment'], encoding='utf-8'))
    assert original['ok'], original
    with tempfile.TemporaryDirectory(prefix='one file 测试 ', dir=ROOT / '.work') as folder:
        root = Path(folder)
        executable = root / 'texastra-backend.exe'
        shutil.copyfile(source, executable)
        project = root / 'project'
        project.mkdir()
        source_text = '\\documentclass{article}\n\\begin{document}\nFirst native page.\n\\newpage\nSecond native page.\n\\end{document}\n'
        (project / 'main.tex').write_text(source_text)
        env = dict(os.environ, LOCALAPPDATA=str(root / 'cache'),
                   PATH=original['binDirectory'] + ';' + os.environ['SystemRoot'] + '/System32')
        for name in list(env):
            if name.startswith('BAKO_'): env.pop(name)
        report = json.loads(subprocess.check_output([str(executable), '--environment', '--tex-bin', original['binDirectory']], env=env, encoding='utf-8', timeout=90))
        assert report['ok'], report
        directories = list((root / 'cache/texastra/runtime').iterdir())
        assert len(directories) == 1
        module = directories[0] / 'texastra-engine.dll'
        expected = hashlib.sha256(module.read_bytes()).hexdigest()
        module.write_bytes(b'damaged extraction')
        # A second invocation must detect and replace a damaged cached module.
        process = subprocess.Popen([str(executable), '--project', str(project), '--sync'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', env=env)
        requests = [dict(type='start', page=1), dict(type='edit', page=1, file='main.tex',
                    source=source_text.replace('Second', 'Edited')), dict(type='close')]
        stdout, stderr = process.communicate(''.join(json.dumps(r) + '\n' for r in requests), timeout=120)
        assert process.returncode == 0, stderr
        frames = [json.loads(line) for line in stdout.splitlines()]
        assert len(frames) == 2 and all(frame.get('ok') for frame in frames), frames
        assert frames[1]['snapshot']['mode'] == 'windows' and frames[1]['outputMode'] == 'page-stream'
        assert hashlib.sha256(module.read_bytes()).hexdigest() == expected
        result = {'ok': True, 'standaloneHelperAssets': True, 'restrictedPath': True,
                  'unicodeExecutablePath': True, 'cachedModuleRepair': True,
                  'incrementalEdit': True, 'dependentDLLs': dlls,
                  'binaryBytes': source.stat().st_size, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        (ROOT / 'results/windows-bundle.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
