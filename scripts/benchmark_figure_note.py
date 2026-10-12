"""Measure real extension edit events through Chromium paint; editor APIs are mocked.

The project is read only: edits live in the test editor buffer and backend cache.
Reports contain timings and source hashes, never document contents.
"""
import argparse
import hashlib
import json
import socket
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--main', required=True)
    parser.add_argument('--token', required=True)
    parser.add_argument('--replacement', required=True)
    parser.add_argument('--extension', type=Path, default=ROOT)
    parser.add_argument('--repeats', type=int, default=6)
    parser.add_argument('--output', default='figure-note.json')
    parser.add_argument('--assert-stream', action='store_true')
    args = parser.parse_args()
    original = (args.project/args.main).read_bytes()
    source = original.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    offset = source.index(args.token)
    utf16 = lambda s: len(s.encode('utf-16-le'))//2
    location = {'file': args.main, 'line': source[:offset].count('\n'),
                'column': utf16(source[source.rfind('\n', 0, offset)+1:offset])}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    report = {'measurement': 'Real extension document-change callback to Chromium image decode, text layer and two animation frames; mocked VS Code APIs and HTTP webview bridge.',
              'sourceSha256': hashlib.sha256(original).hexdigest(), 'sourceBytes': len(original),
              'extensionVersion': json.loads((args.extension/'package.json').read_text())['version'],
              'runtimeSha256': {name: hashlib.sha256((args.extension/name).read_bytes()).hexdigest()
                                for name in ['native/runtime/bakoma-backend', 'native/runtime/bakoma-luahbtex',
                                             'native/runtime/bako_snapshot.so', 'webview/viewer.js', 'extension/extension.js']},
              'samples': []}
    with (ROOT/'.work/figure-note.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen(['node', str(ROOT/'scripts/extension_benchmark_host.js'), '--project', str(args.project),
                                   '--main', args.main, '--extension', str(args.extension), '--port', str(port)],
                                  cwd=ROOT, stdout=log, stderr=log)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.add_init_script('''window.acquireVsCodeApi=()=>({postMessage:m=>fetch('/action',{
                    method:'POST',body:JSON.stringify(m)})});
                    new EventSource('/events').onmessage=e=>window.dispatchEvent(new MessageEvent('message',{data:JSON.parse(e.data)}));''')
                for attempt in range(100):
                    try:
                        page.goto(url)
                        break
                    except Exception:
                        if attempt == 99:
                            raise
                        time.sleep(.1)
                page.wait_for_function('window.lastPaint&&!stale', timeout=120000)
                report['pages'] = page.evaluate('documentCount')
                page.evaluate('l=>receive({type:"forward",...l})', location)
                page.wait_for_function('!pendingHighlight&&[...pages.values()].some(p=>p.highlight.style.display==="block")', timeout=30000)
                report['editedPage'] = page.evaluate('page+1')
                current = args.token
                for i in range(args.repeats+1):
                    replacement = args.replacement if i % 2 == 0 else args.token
                    edit = {'changes': [{'rangeOffset': utf16(source[:offset]), 'rangeLength': utf16(current), 'text': replacement}]}
                    sent = page.evaluate('async data=>(await fetch("/edit",{method:"POST",body:JSON.stringify(data)})).json()', edit)
                    page.wait_for_function('id=>paintHistory.some(p=>p.clientId===id&&p.purpose==="edit"&&!p.stale&&p.visibleMs!==null)', arg=sent['clientId'], timeout=120000)
                    sample = page.evaluate('id=>paintHistory.find(p=>p.clientId===id&&p.purpose==="edit"&&!p.stale&&p.visibleMs!==null)', sent['clientId'])
                    actual = page.evaluate('pages.get(page).frame.characters.map(c=>c.text).join("")')
                    assert replacement in actual, 'The edited figure note is not visible'
                    sample.update(sent)
                    print(json.dumps(sample), flush=True)
                    if i:
                        report['samples'].append(sample)
                    else:
                        report['firstEdit'] = sample
                    current = replacement
                assert not errors, errors
                browser.close()
            report['medianDisplayMs'] = statistics.median(s['visibleMs'] for s in report['samples'])
            report['maxDisplayMs'] = max(s['visibleMs'] for s in report['samples'])
            report['checks'] = ['Matching edited note visible', 'Current revision painted', 'No browser errors', 'Original source unchanged']
            assert (args.project/args.main).read_bytes() == original
            if args.assert_stream:
                assert all(s['outputMode'] == 'page-stream' for s in report['samples']), 'Figure edits still finalize the whole document'
        finally:
            (ROOT/'results'/args.output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            try:
                request = urllib.request.Request(url+'/close', data=b'{}', method='POST')
                urllib.request.urlopen(request, timeout=5).close()
                server.wait(timeout=15)
            except Exception:
                server.terminate()
                server.wait(timeout=15)


if __name__ == '__main__':
    main()
