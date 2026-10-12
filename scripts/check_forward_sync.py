"""Exercise VS Code forward-sync messages in the real shared Chromium viewer."""
import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
report = {'checks': []}
parser = argparse.ArgumentParser()
parser.add_argument('--vsix', type=Path, help='Test the viewer shipped in this VSIX')
args = parser.parse_args()
temporary = None
viewer = ROOT/'webview/index.html'
output = ROOT/'results/forward-sync.json'


def check(name, condition):
    report['checks'].append({'name': name, 'ok': bool(condition)})
    print(name, bool(condition), flush=True)
    assert condition, name


try:
    if args.vsix:
        temporary = tempfile.TemporaryDirectory(prefix='forward-sync-package-', dir=ROOT/'.work')
        with zipfile.ZipFile(args.vsix) as archive:
            for name in ['index.html', 'viewer.js', 'viewer.css']:
                (Path(temporary.name)/name).write_bytes(archive.read('extension/webview/'+name))
        viewer = Path(temporary.name)/'index.html'
        output = ROOT/'results/forward-sync-package.json'
        report['package'] = args.vsix.name
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('window.outbound=[];window.acquireVsCodeApi=()=>({postMessage:m=>outbound.push(m)});')
        page.goto(viewer.as_uri())
        page.wait_for_function('outbound.some(m=>m.type==="ready")')
        frame = {'type': 'frame', 'purpose': 'start', 'page': 0, 'pageCount': 20,
                 'generation': 1, 'revisionId': 1, 'clientId': 1,
                 'width': 600, 'height': 800, 'regions': [], 'characters': [],
                 'image': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5WQAAAAASUVORK5CYII='}
        page.evaluate('f=>receive(f)', frame)
        check('late page has never loaded', page.evaluate('pages.has(19)&&pages.get(19).frame===null'))
        page.evaluate('''()=>{outbound.length=0;window.dispatchEvent(new MessageEvent('message',
            {data:{type:'forward',file:'chapters/late.tex',line:12,column:3}}));}''')
        messages = page.evaluate('outbound.filter(m=>m.requestId?.startsWith("sync-"))')
        report['request'] = messages[-1] if messages else None
        check('VS Code selection requests backend lookup for never-loaded page',
              bool(messages) and messages[-1]['type'] == 'sync-forward')
        region = {'file': 'chapters/late.tex', 'line': 12, 'column': 3,
                  'endLine': 12, 'endColumn': 7, 'start': 120, 'end': 124,
                  'rect': [100, 100, 130, 115], 'page': 19, 'kind': 'token'}
        page.evaluate('m=>receive(m)', {'type': 'sync', 'generation': 1,
                      'requestId': messages[-1]['requestId'], 'location': region})
        request = page.evaluate('outbound.find(m=>m.type==="page"&&m.page===19)')
        check('lookup result requests the late page', request is not None)
        page.evaluate('f=>receive(f)', {**frame, 'purpose': 'page', 'page': 19,
                      'regions': [region], 'requestId': request['requestId']})
        page.wait_for_function('page===19&&pages.get(19).highlight.style.display==="block"')
        check('loaded late page scrolls to the highlighted source', page.evaluate('''()=>{
            const r=pages.get(19).highlight.getBoundingClientRect(),v=$('scroll').getBoundingClientRect();
            return r.top>=v.top&&r.bottom<=v.bottom;
        }'''))
        page.evaluate('''()=>{outbound.length=0;receive({type:'forward',
            file:'chapters/late.tex',line:12,column:4});}''')
        check('already-loaded page highlights without a backend lookup',
              not page.evaluate('outbound.some(m=>m.requestId?.startsWith("sync-"))'))
        page.evaluate('''()=>{markStale();outbound.length=0;receive({type:'forward',
            file:'chapters/other.tex',line:2,column:1});}''')
        check('selection waits while preview is stale', not page.evaluate('outbound.length'))
        page.evaluate('f=>receive(f)', {**frame, 'generation': 2, 'revisionId': 2})
        check('deferred VS Code selection keeps the backend request type', page.evaluate('''
            outbound.some(m=>m.type==='sync-forward'&&m.file==='chapters/other.tex'&&m.line===2&&m.column===1)
        '''))
        check('no browser errors', not errors)
        browser.close()
finally:
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if temporary:
        temporary.cleanup()
