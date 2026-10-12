"""Measure real extension edit events through Chromium paint; editor APIs are mocked.

By default edits live in the test editor buffer and backend cache. Save tests
require an isolated project under .work and restore its source afterward.
Reports contain timings and source hashes, never document contents.
"""
import argparse
import hashlib
import json
import math
import os
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
    parser.add_argument('--burst-edits', type=int, default=0, help='Also run repeats sustained typing bursts')
    parser.add_argument('--interval-ms', type=float, default=35)
    parser.add_argument('--decode-delay-ms', type=float, default=0, help='Controlled slow-viewer experiment; not a natural latency measurement')
    args = parser.parse_args()
    if args.repeats<1 or args.burst_edits<0 or args.interval_ms<=0 or args.decode_delay_ms<0:
        parser.error('Use positive repeats/interval and nonnegative burst/decode settings')
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
              'burstEdits': args.burst_edits, 'intervalMs': args.interval_ms, 'injectedDecodeDelayMs': args.decode_delay_ms,
              'samples': [], 'saveSamples': [], 'bursts': []}
    with (ROOT/'.work/figure-note.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen(['node', str(ROOT/'scripts/extension_benchmark_host.js'), '--project', str(args.project),
                                   '--main', args.main, '--extension', str(args.extension), '--port', str(port),
                                   '--allow-save', 'yes' if args.save_after_edit else 'no'],
                                  cwd=ROOT, stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                if args.decode_delay_ms:
                    page.add_init_script('''{const decode=Image.prototype.decode;
                        Image.prototype.decode=async function(){await decode.call(this);
                        await new Promise(r=>setTimeout(r,%s));};}''' % args.decode_delay_ms)
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
                for burst in range(args.repeats if args.burst_edits else 0):
                    edits=[]
                    for i in range(args.burst_edits):
                        replacement=args.replacement if current==args.token else args.token
                        edits.append({'changes':[{'rangeOffset':utf16(source[:offset]),'rangeLength':utf16(current),'text':replacement}]})
                        current=replacement
                    timing=page.evaluate('''async ({edits,interval})=>{
                        const start=performance.now(),startedAt=Date.now(),sent=[];
                        for(let i=0;i<edits.length;i++){
                            await new Promise(r=>setTimeout(r,Math.max(0,start+i*interval-performance.now())));
                            sent.push(await(await fetch('/edit',{method:'POST',body:JSON.stringify(edits[i])})).json());
                        }
                        return {startedAt,endedAt:Date.now(),sent};
                    }''', {'edits':edits,'interval':args.interval_ms})
                    last=timing['sent'][-1]['clientId']
                    page.wait_for_function('id=>paintHistory.some(p=>p.clientId===id&&!p.stale&&p.visibleMs!==null)',arg=last,timeout=120000)
                    paints=page.evaluate('ids=>paintHistory.filter(p=>ids.includes(p.clientId)&&p.purpose==="edit")',[s['clientId'] for s in timing['sent']])
                    sent_by_id={s['clientId']:s for s in timing['sent']}
                    for paint in paints:
                        paint.setdefault('frameAgeMs',paint['at']-sent_by_id[paint['clientId']]['sentAt'])
                    actual=page.evaluate('pages.get(page).frame.characters.map(c=>c.text).join("")')
                    assert current in actual, 'Final burst text is not visible'
                    interim=[p for p in paints if p['at']<timing['endedAt']]
                    ages=sorted(p['frameAgeMs'] for p in paints)
                    gaps=[b['at']-a['at'] for a,b in zip(paints,paints[1:])]
                    item={'inputs':len(edits),'durationMs':timing['endedAt']-timing['startedAt'],
                          'displayedUpdates':len(paints),'updatesDuringTyping':len(interim),
                          'finalInputDisplayMs':paints[-1]['visibleMs'],
                          'p95FrameAgeMs':ages[math.ceil(.95*len(ages))-1],
                          'maxUpdateIntervalMs':max(gaps) if gaps else None,'paints':paints}
                    report['bursts'].append(item)
                    print('burst',json.dumps({k:v for k,v in item.items() if k!='paints'}),flush=True)
                    assert paints[-1]['clientId']==last and not paints[-1]['stale']
                    if args.burst_edits>=30:assert interim, 'Preview made no progress during sustained typing'
                report['diagnostics']=page.evaluate('async ()=>(await fetch("/diagnostics")).json()')
                assert not errors, errors
                browser.close()
            report['medianDisplayMs'] = statistics.median(s['visibleMs'] for s in report['samples'])
            report['maxDisplayMs'] = max(s['visibleMs'] for s in report['samples'])
            report['checks'] = ['Matching edited note visible', 'Current revision painted', 'No browser errors']
            if report['bursts']:report['checks'].append('Typing bursts make progress and display the final input')
            if not args.save_after_edit:
                assert (args.project/args.main).read_bytes() == original
                report['checks'].append('Original source unchanged')
            if args.assert_stream:
                assert all(s['outputMode'] == 'page-stream' for s in report['samples']), 'Figure edits still finalize the whole document'
            if args.assert_no_save_rebuild:
                assert report['saveSamples'] and all(s['reloadRequests'] == 0 for s in report['saveSamples']), 'Save discards the incremental session'
        except Exception as error:
            report['failure']=str(error)
            raise
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
