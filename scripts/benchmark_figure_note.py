"""Measure real extension edit events through Chromium paint; editor APIs are mocked.

By default edits live in the test editor buffer and backend cache. Save tests
require an isolated project under .work and restore its source afterward.
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
    parser.add_argument('--save-after-edit', action='store_true', help='Save only an isolated project copy under .work; restore its source afterward')
    parser.add_argument('--assert-no-save-rebuild', action='store_true')
    args = parser.parse_args()
    if args.save_after_edit and not (args.project/args.main).resolve().is_relative_to((ROOT/'.work').resolve()):
        parser.error('Save tests require a source copy under .work')
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
              'samples': [], 'saveSamples': []}
    with (ROOT/'.work/figure-note.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen(['node', str(ROOT/'scripts/extension_benchmark_host.js'), '--project', str(args.project),
                                   '--main', args.main, '--extension', str(args.extension), '--port', str(port),
                                   '--allow-save', 'yes' if args.save_after_edit else 'no'],
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
                    if args.save_after_edit:
                        saved = page.evaluate('async ()=>(await fetch("/save",{method:"POST",body:"{}"})).json()')
                        page.wait_for_timeout(350)
                        requests = page.evaluate('async ()=>(await fetch("/requests")).json()')
                        reloads = [r for r in requests[saved['requestCount']:] if r['type'] == 'reload']
                        save_sample = {'reloadRequests': len(reloads), 'observationMs': 350, 'saveToRebuiltPaintMs': None}
                        if reloads:
                            client = reloads[-1]['clientId']
                            page.wait_for_function('id=>paintHistory.some(p=>p.clientId===id&&!p.stale)', arg=client, timeout=120000)
                            painted = page.evaluate('id=>paintHistory.find(p=>p.clientId===id&&!p.stale)', client)
                            save_sample['saveToRebuiltPaintMs'] = painted['at']-saved['savedAt']
                        report['saveSamples'].append(save_sample)
                        print('save', json.dumps(save_sample), flush=True)
                assert not errors, errors
                browser.close()
            report['medianDisplayMs'] = statistics.median(s['visibleMs'] for s in report['samples'])
            report['maxDisplayMs'] = max(s['visibleMs'] for s in report['samples'])
            report['checks'] = ['Matching edited note visible', 'Current revision painted', 'No browser errors']
            if not args.save_after_edit:
                assert (args.project/args.main).read_bytes() == original
                report['checks'].append('Original source unchanged')
            if args.assert_stream:
                assert all(s['outputMode'] == 'page-stream' for s in report['samples']), 'Figure edits still finalize the whole document'
            if args.assert_no_save_rebuild:
                assert report['saveSamples'] and all(s['reloadRequests'] == 0 for s in report['saveSamples']), 'Save discards the incremental session'
        finally:
            try:
                request = urllib.request.Request(url+'/close', data=b'{}', method='POST')
                urllib.request.urlopen(request, timeout=5).close()
                server.wait(timeout=15)
            except Exception:
                server.terminate()
                server.wait(timeout=15)
            if args.save_after_edit and args.project.resolve().is_relative_to((ROOT/'.work').resolve()):
                (args.project/args.main).write_bytes(original)
                report['savedFixtureRestored'] = (args.project/args.main).read_bytes() == original
            (ROOT/'results'/args.output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
