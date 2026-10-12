"""Actual native Windows compiler -> shared Chromium viewer acceptance check."""
import argparse
import json
import math
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from generate_corpus import generate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT / 'native/windows-bundle')
    args = parser.parse_args()
    report = {'checks': [], 'samples': [], 'runtime': str(args.runtime)}
    def check(name, condition):
        report['checks'].append(dict(name=name, ok=bool(condition)))
        print(name, bool(condition), flush=True)
        assert condition, name
    with tempfile.TemporaryDirectory(prefix='windows browser ', dir=ROOT / '.work') as folder:
        project = Path(folder)
        generate(project, pages=100)
        log = (ROOT / '.work/windows-browser.log').open('w', encoding='utf-8')
        server = subprocess.Popen(['node', str(ROOT / 'native/demo.js'), '--project', str(project),
                                   '--runtime', str(args.runtime), '--port', '8778'],
                                  cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                for attempt in range(30):
                    try:
                        page.goto('http://127.0.0.1:8778')
                        break
                    except Exception:
                        if attempt == 29: raise
                        time.sleep(.1)
                page.wait_for_function('window.lastPaint&&!lastPaint.stale&&lastPaint.clientId===latestClient', timeout=120000)
                check('native Chinese/math/TikZ document loads', page.evaluate('frame.pageCount===100 && frame.characters.map(c=>c.text).join("").includes("中文")'))
                check('native environment reaches viewer', page.evaluate('typeof frame.image==="string" && frame.regions.length>100'))
                region = page.evaluate('frame.regions.find(r=>r.text==="中")')
                page.evaluate('r=>{const e=document.querySelector("#source");e.focus();e.setSelectionRange(r.start,r.start);e.dispatchEvent(new MouseEvent("click",{bubbles:true}));}', region)
                check('forward source highlight', page.locator('#caret').evaluate('e=>e.style.display!=="none"'))
                bounds = page.locator('#paper').bounding_box()
                width, height = page.evaluate('[frame.width,frame.height]')
                rect = region['rect']
                page.mouse.click(bounds['x'] + (rect[0] + rect[2]) / 2 / width * bounds['width'],
                                 bounds['y'] + (rect[1] + rect[3]) / 2 / height * bounds['height'])
                page.wait_for_function('document.querySelector("#source").value.slice(source.selectionStart,source.selectionEnd)==="中"')
                check('reverse Chinese source selection', True)
                def edit(text):
                    page.locator('#source').evaluate('(e,text)=>{e.value=text;e.dispatchEvent(new InputEvent("input",{bubbles:true}));}', text)
                def painted():
                    page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient', timeout=60000)
                for number in [100, 50, 1]:
                    page.evaluate('n=>navigate(n-1)', number)
                    painted()
                    name = f'pages/page-{number:03}.tex'
                    page.evaluate('name=>loadSource(name)', name)
                    original = (project / name).read_text(encoding='utf-8')
                    for index in range(6):
                        text = original.replace('word: alpha.', 'word: omega.') if index % 2 == 0 else original
                        edit(text); painted()
                        sample = page.evaluate('lastPaint')
                        check(f'page {number} edit {index} streams', sample['outputMode'] == 'page-stream' and sample['resumedFrom'] > 0)
                        sample['pageNumber'] = number
                        report['samples'].append(sample)
                valid = page.locator('#source').input_value()
                edit(valid.replace(r'\frac{a_{1}+b^{2}}{c+d}', r'\frac{a_{1}+b^{2}}{c+d'))
                page.wait_for_function('document.querySelector("#status").textContent.includes("Compile error")', timeout=30000)
                check('error keeps visibly stale preview', page.evaluate('stale && document.querySelector("#image").src.startsWith("data:")'))
                edit(valid); painted()
                check('browser recovers after invalid TeX', True)
                page.wait_for_function('frame.phase==="converged"', timeout=120000)
                check('idle convergence restores whole document', page.evaluate('frame.pageCount===100'))
                check('no browser errors', not errors)
                values = sorted(s['visibleMs'] for s in report['samples'])
                report['latency'] = {'medianMs': statistics.median(values), 'p95Ms': values[math.ceil(.95 * len(values)) - 1]}
                print(report['latency'], flush=True)
                page.screenshot(path=str(ROOT / 'results/windows-preview.png'))
                browser.close()
        finally:
            # Close via the document protocol before stopping the owned HTTP adapter.
            import urllib.request
            try:
                urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8778/action',
                    data=b'{"type":"close"}', headers={'Content-Type': 'application/json'}), timeout=5).close()
            except Exception:
                pass
            server.terminate(); server.wait(timeout=10); log.close()
            (ROOT / 'results/windows-browser.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
