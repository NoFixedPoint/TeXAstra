"""Forward sync to never-loaded late pages using WSL and the real Chromium viewer."""
import json
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = {'runtime': 'wsl', 'checks': []}

    def check(name, condition):
        report['checks'].append({'name': name, 'ok': bool(condition)})
        print(name, bool(condition), flush=True)
        assert condition, name

    with tempfile.TemporaryDirectory(prefix='forward-sync-', dir=ROOT/'.work') as folder:
        project = Path(folder)
        (project/'chapters').mkdir()
        source = '\\documentclass{article}\n\\begin{document}\n'
        for number in range(1, 30):
            source += f'Root page {number}. Token for forward synchronization.\n\\newpage\n'
        source += '\\input{chapters/late}\n\\end{document}\n'
        included = 'Late included chapter. Target token on the final page.\n'
        (project/'paper.tex').write_text(source, encoding='utf-8')
        (project/'chapters/late.tex').write_text(included, encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        with (ROOT/'.work/forward-sync-live.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen(['node', str(ROOT/'native/demo.js'), '--project', str(project),
                                       '--main', 'paper.tex', '--runtime-mode', 'wsl', '--port', str(port)],
                                      cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    errors, requests = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: requests.append(request.post_data_json)
                            if request.url == url+'/action' else None)
                    for attempt in range(50):
                        try:
                            page.goto(url)
                            break
                        except Exception:
                            if attempt == 49:
                                raise
                            time.sleep(.1)
                    page.wait_for_function('window.lastPaint&&!stale', timeout=120000)
                    check('30-page document loads on WSL', page.evaluate('documentCount===30'))
                    revision = page.evaluate('latestRequest')

                    def sync(file, text, token, destination):
                        offset = text.index(token)
                        line = text[:offset].count('\n')
                        column = offset-text.rfind('\n', 0, offset)-1
                        check(f'page {destination+1} has never loaded', page.evaluate(
                            'n=>pages.get(n).frame===null', destination))
                        # Preserve the actual VS Code message envelope. Calling
                        # forward({file,line,column}) alone missed the original bug.
                        page.evaluate('m=>receive(m)', {'type': 'forward', 'file': file,
                                                      'line': line, 'column': column})
                        page.wait_for_function('''n=>page===n&&pages.get(n).frame?.generation===generation
                            &&pages.get(n).highlight.style.display==='block' ''', arg=destination, timeout=15000)
                        check(f'page {destination+1} loads, scrolls and highlights the exact token', page.evaluate('''l=>{
                            const p=pages.get(l.page),r=p.highlight.getBoundingClientRect(),v=$('scroll').getBoundingClientRect();
                            return p.frame.regions.some(r=>containsSource(r,l))&&r.top>=v.top&&r.bottom<=v.bottom
                                &&$('location').textContent.startsWith(`${l.file}:${l.line+1}:${l.column+1}`);
                        }''', {'file': file, 'line': line, 'column': column, 'page': destination}))

                    sync('paper.tex', source, 'Root page 20.', 19)
                    sync('chapters/late.tex', included, 'Target token', 29)
                    check('forward synchronization preserves source revision', page.evaluate('latestRequest') == revision)
                    check('both selections reach backend as sync-forward',
                          len([r for r in requests if r['type'] == 'sync-forward']) == 2)
                    check('no browser errors', not errors)
                    browser.close()
            finally:
                try:
                    urllib.request.urlopen(urllib.request.Request(url+'/action', data=b'{"type":"close"}',
                        headers={'Content-Type': 'application/json'}), timeout=5).close()
                except Exception:
                    pass
                server.terminate()
                server.wait(timeout=10)
                (ROOT/'results/forward-sync-live.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
