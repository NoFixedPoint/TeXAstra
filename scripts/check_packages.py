"""Real TeX recovery against an isolated, deterministic package-manager fixture.

Runs on Linux/WSL; never installs into the host distribution or uses the network.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from cpp_client import Client, ROOT, linux

if os.name == 'nt':
    raise SystemExit(subprocess.call(['wsl', '-d', 'Ubuntu-22.04', '--exec', 'python3', linux(Path(__file__))]))

checks = []


def check(name, condition):
    print(name, bool(condition), flush=True)
    checks.append({'name': name, 'ok': bool(condition)})
    assert condition, name


source = '\\documentclass{article}\n\\begin{document}Unsaved content.\\end{document}\n'


class Fixture:
    def __init__(self, root, name, mode='success'):
        self.root = root / name
        self.bin = self.root / 'bin'
        self.project = self.root / 'project'
        self.user = self.root / 'user'
        for directory in [self.bin, self.project, self.user, self.root / 'tlpkg']:
            directory.mkdir(parents=True)
        (self.root / 'tlpkg/texlive.tlpdb').touch()
        (self.root / 'texmf-dist').symlink_to('/usr/share/texlive/texmf-dist')
        (self.project / 'main.tex').write_text(source)
        for tool in ['lualatex', 'pdflatex', 'xelatex', 'bibtex', 'biber', 'makeindex']:
            (self.bin / tool).symlink_to('/usr/bin/' + tool)
        self.script('kpsewhich', '''import os,sys
if sys.argv[1:] == ['--var-value=TEXMFROOT']: print(root)
else: os.execv('/usr/bin/kpsewhich', ['kpsewhich'] + sys.argv[1:])
''')
        self.script('tlmgr', '''import json,sys,time
args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as out: out.write(json.dumps(args)+'\\n')
mode=(root/'mode').read_text()
if args[0]=='search':
    name=args[-1][1:-1].replace('\\\\','')
    if mode=='none': sys.exit(0)
    print('fixture-provider:')
    print('    texmf-dist/tex/latex/fixture/'+name)
    print('    ')
    print('documentation-only:')
    print('    texmf-dist/doc/latex/fixture/'+name)
    if mode=='ambiguous':
        print('another-provider:')
        print('    texmf-dist/tex/latex/fixture/'+name)
    (root/'missing').write_text(name)
elif args[0]=='install':
    if mode=='denied': sys.exit('Permission denied (fixture)')
    if mode=='slow': time.sleep(60)
    name=(root/'missing').read_text()
    target=root/'user/tex/latex/fixture'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    content='\\\\ProvidesPackage{'+target.stem+'}\\n'
    if mode=='chain' and name=='texastrafirst.sty': content+='\\\\RequirePackage{texastrasecond}\\n'
    if mode=='repeat': content+='\\\\errmessage{LaTeX Error: File `'+name+"' not found}\\n"
    if mode!='unresolved': target.write_text(content)
else: sys.exit('Unexpected manager action')
''')
        (self.root / 'mode').write_text(mode)
        self.env = {'TEXMFHOME': str(self.user), 'XDG_CACHE_HOME': str(self.root / 'cache')}

    def script(self, name, body):
        target = self.bin / name
        target.write_text('#!/usr/bin/python3\nfrom pathlib import Path\nroot=Path(' + repr(str(self.root)) + ')\n' + body)
        target.chmod(0o755)

    def calls(self):
        file = self.root / 'calls.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def client(self, **kwargs):
        return Client(project=self.project, tex_bin=self.bin, environment=self.env, **kwargs)


with tempfile.TemporaryDirectory(prefix='texastra-package-test-') as name:
    root = Path(name)
    for compiler, preview in [('lualatex', 'auto'), ('pdflatex', 'full')]:
        fixture = Fixture(root, compiler, 'chain')
        overlay = source.replace('\\begin{document}', '\\usepackage{texastrafirst}\n\\begin{document}')
        with fixture.client(compiler=compiler, preview_mode=preview) as client:
            result = client.request(type='start', overlays={'main.tex': overlay})
            check(compiler + ' installs transitive packages and compiles', result.get('ok'))
            calls = fixture.calls()
            check(compiler + ' exact file lookup and provider mapping', calls[0] == ['search', '--global', '--file', '/texastrafirst\\.sty$'] and calls[1] == ['install', 'fixture-provider'] and len(calls) == 4)
            report = json.loads(Path(result.get('environmentReport', str(Path(result['session']) / 'bako-environment.json'))).read_text())
            check(compiler + ' records package installation and resolution', len(report['packageInstallations']) == 2 and all(Path(x['resolved']).is_file() for x in report['packageInstallations']))
            check(compiler + ' preserves project source', (fixture.project / 'main.tex').read_text() == source)
            edited = overlay.replace('texastrafirst', 'texastrathird').replace('Unsaved content.', 'Edited unsaved content.')
            # Sync clients report RebuildRequired directly for preamble edits;
            # start with overlays also exercises a fresh compile in this session.
            result = client.request(type='start', overlays={'main.tex': edited})
            check(compiler + ' recovers another missing package in same session', result.get('ok') and len(fixture.calls()) == 6)
            check(compiler + ' package change discards reusable state', not result.get('cacheReused', False))

    for mode, message in [('none', 'No package provides'), ('ambiguous', 'Multiple packages'), ('denied', 'Permission denied'), ('unresolved', 'package manager'), ('repeat', 'repeated missing file')]:
        fixture = Fixture(root, mode, mode)
        with fixture.client() as client:
            result = client.request(type='start', overlays={'main.tex': source.replace('\\begin{document}', '\\usepackage{texastramissing}\n\\begin{document}')})
            check(mode + ' has actionable failure', not result.get('ok') and message.lower() in result.get('error', '').lower())
            check(mode + ' bounds install attempts', sum(call[0] == 'install' for call in fixture.calls()) <= 1)
            result = client.request(type='start', overlays={'main.tex': source})
            check(mode + ' can recover after source correction', result.get('ok'))

    fixture = Fixture(root, 'local')
    for missing in ['chapters/absent.tex', 'figure.pdf']:
        with fixture.client() as client:
            result = client.request(type='start', overlays={'main.tex': source.replace('\\begin{document}', '\\input{' + missing + '}\n\\begin{document}')})
            check('project asset ' + missing + ' is not installed', not result.get('ok') and not fixture.calls())

    fixture = Fixture(root, 'os-managed')
    (fixture.root / 'tlpkg/texlive.tlpdb').unlink()
    with fixture.client() as client:
        result = client.request(type='start', overlays={'main.tex': source.replace('\\begin{document}', '\\usepackage{texastramissing}\n\\begin{document}')})
        check('OS-owned installation uses OS remedy', 'OS package manager' in result.get('error', '') and not fixture.calls())

    fixture = Fixture(root, 'disabled')
    with fixture.client(auto_install_packages=False) as client:
        result = client.request(type='start', overlays={'main.tex': source.replace('\\begin{document}', '\\usepackage{texastramissing}\n\\begin{document}')})
        check('disabled automatic installation never invokes manager', not result.get('ok') and not fixture.calls() and 'texastramissing.sty' in result.get('error', ''))

    # Exercise the production asynchronous edit path, including status output.
    fixture = Fixture(root, 'live-edit')
    with fixture.client(sync=False) as client:
        client.process.stdin.write(json.dumps({'type': 'start', 'clientId': 1}) + '\n'); client.process.stdin.flush()
        while True:
            frame = client.responses.get(timeout=120)
            if frame.get('type') == 'frame': break
            assert frame.get('state') != 'error', frame
        edit = source.replace('\\begin{document}', '\\usepackage{texastraedit}\n\\begin{document}')
        client.process.stdin.write(json.dumps({'type': 'edit', 'file': 'main.tex', 'source': edit, 'clientId': 2}) + '\n'); client.process.stdin.flush()
        messages = []
        while True:
            frame = client.responses.get(timeout=120)
            if frame.get('message'): messages.append(frame['message'])
            if frame.get('type') == 'frame' and frame.get('clientId') == 2: break
            assert frame.get('state') != 'error', frame
        check('unsaved edit installs package and renders automatically', frame.get('ok') and len(fixture.calls()) == 2)
        check('installation progress is visible', any('Installing' in m for m in messages) and any('rebuilding' in m for m in messages))

    fixture = Fixture(root, 'cancel', 'slow')
    with fixture.client(sync=False) as client:
        overlay = source.replace('\\begin{document}', '\\usepackage{texastracancel}\n\\begin{document}')
        client.process.stdin.write(json.dumps({'type': 'start', 'overlays': {'main.tex': overlay}}) + '\n'); client.process.stdin.flush()
        deadline = time.monotonic() + 90
        while len(fixture.calls()) < 2:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        started = time.monotonic()
        client.close()
        check('close cancels active package manager', time.monotonic() - started < 10)

report = {'ok': True, 'checks': checks, 'scope': 'Real Linux/WSL TeX compilation; isolated fake tlmgr, no network or system package changes.'}
(ROOT / 'results/packages.json').write_text(json.dumps(report, indent=2) + '\n')
