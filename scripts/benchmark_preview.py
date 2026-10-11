"""Isolated real-browser latency benchmark for the production C++ preview path.

Creates its own project and loopback server; never edits the corpus or user files.
Measures input-handler entry through decoded image, text layer, and two rAFs.
"""
import argparse
import hashlib
import json
import math
import os
import platform
import socket
import statistics
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def summary(values):
    values = sorted(values)
    return {'count': len(values), 'medianMs': statistics.median(values),
            'p95Ms': values[math.ceil(.95*len(values))-1], 'maxMs': values[-1]}


def run(args):
    project = ROOT/'.work/preview-benchmark'
    project.mkdir(parents=True, exist_ok=True)
    sources = {
        'paper.tex': ('\\documentclass{article}\n\\usepackage{amsmath}\n'
                      '\\setlength{\\textheight}{320pt}\n\\begin{document}\n'
                      'Root marker alpha. 0123456789 omega.\n\\newpage\n'
                      '\\input{chapter}\n\\end{document}\n'),
        'chapter.tex': ''.join('\\textbf{Marker%03d} '%i +
                             ('A paragraph with ordinary words, café and $x+y+\\alpha$. '*5) + '\n\n'
                             for i in range(72))}
    for name, source in sources.items():
        (project/name).write_text(source, encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    report = {
        'recordedAt': datetime.now(timezone.utc).isoformat(),
        'measurement': 'Browser input handler to image decode, text-layer installation and two animation frames; not physical display latency or the VS Code host.',
        'deliveryMs': 'Residual: total minus backend request-to-payload and browser stages; includes request/response transport, serialization and adapter scheduling.',
        'platform': platform.platform(), 'processor': platform.processor(), 'repeats': args.repeats,
        'burstEdits': args.burst_edits, 'burstIntervalMs': args.interval_ms,
        'targetMs': 150, 'samples': [], 'bursts': [], 'checks': [],
        'sourceSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [ROOT/'webview/viewer.js', ROOT/'native/main.cpp', ROOT/'native/renderer.hpp',
                                   ROOT/'native/compiler.hpp', ROOT/'prototype/snapshot.c', ROOT/'engine/resources.c',
                                   ROOT/'native/runtime/bako_snapshot.so',
                                   ROOT/'native/runtime/bakoma-backend', ROOT/'native/runtime/bakoma-luahbtex']}}
    output = ROOT/'results'/args.output
    log = (project/'server.log').open('w', encoding='utf-8')
    server = subprocess.Popen(['node', 'native/demo.js', '--port', str(port), '--project', str(project),
                               '--main', 'paper.tex'], cwd=ROOT, stdout=log, stderr=log,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        deadline = time.monotonic()+30
        while True:
            try:
                with urllib.request.urlopen(url+'/bootstrap', timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline or server.poll() is not None:
                    raise RuntimeError('Demo failed to start; see '+str(project/'server.log'))
                time.sleep(.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            report['chromium'] = browser.version
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url)
            page.wait_for_function('window.lastPaint && !lastPaint.stale', timeout=120000)

            def wait_paint(client):
                page.wait_for_function('''id=>paintHistory.some(p=>p.clientId===id && p.purpose==='edit' &&
                    !p.stale && p.visibleMs!==null)''', arg=client, timeout=120000)
                return page.evaluate('id=>paintHistory.find(p=>p.clientId===id && p.purpose==="edit" && !p.stale && p.visibleMs!==null)', client)

            def settle():
                page.wait_for_function('!stale && pendingPages.size===0 && pages.get(page)?.frame?.generation===generation', timeout=120000)

            def reset():
                client = page.evaluate('sources=>{markStale();send({type:"start",overlays:sources,page:0});return latestClient;}', sources)
                page.wait_for_function('id=>lastPaint.clientId===id && !lastPaint.stale && lastPaint.purpose==="start"', arg=client, timeout=120000)
                settle()

            def select(name, token):
                source = sources[name]
                page.evaluate('value=>{file=value.name;$("file").value=file;$("source").value=value.source;}', {'name': name, 'source': source})
                offset = source.index(token)
                location = {'file': name, 'line': source[:offset].count('\n'),
                            'column': offset-source.rfind('\n', 0, offset)-1}
                page.evaluate('location=>forward(location)', location)
                page.wait_for_function('!pendingHighlight && [...pages.values()].some(p=>p.highlight.style.display==="block")', timeout=120000)
                settle()
                return page.evaluate('page')

            def edit(source, token):
                return page.locator('#source').evaluate('''(e,{source,token})=>{
                    e.value=source;const at=source.indexOf(token);e.setSelectionRange(at,at);
                    e.dispatchEvent(new InputEvent('input',{bubbles:true}));return latestClient;
                }''', {'source': source, 'token': token})

            def record(case, sample, token):
                # A fresh matching revision must actually contain the edited text.
                actual = page.evaluate('pages.get(page).frame.characters.map(c=>c.text).join("")')
                assert token in actual, (case, token, actual)
                assert sample['visibleMs'] >= 0 and sample['compilationMode'] == 'live', sample
                report['samples'].append({'case': case, **sample})
                print(case, round(sample['visibleMs'], 1), sample.get('outputMode'), flush=True)

            reset()
            select('paper.tex', 'Root marker')
            # One excluded warmup; then every measured edit changes the source.
            wait_paint(edit(sources['paper.tex'].replace('marker alpha', 'marker omega'), 'Root marker'))
            for i in range(args.repeats):
                word = 'alpha' if i % 2 == 0 else 'omega'
                sample = wait_paint(edit(sources['paper.tex'].replace('marker alpha', 'marker '+word), 'Root marker'))
                record('root', sample, 'Root marker '+word)

            reset()
            target_page = select('chapter.tex', 'Marker060')
            report['chapterPage'] = target_page+1
            wait_paint(edit(sources['chapter.tex'].replace('Marker060', 'Marker909'), 'Marker909'))
            for i in range(args.repeats):
                token = 'Marker060' if i % 2 == 0 else 'Marker909'
                sample = wait_paint(edit(sources['chapter.tex'].replace('Marker060', token), token))
                assert sample.get('resumedFrom', 0) >= target_page-1, sample
                record('late-chapter', sample, token)

            for i in range(args.repeats):
                start = page.evaluate('paintHistory.length')
                # Real input events on browser timers; no Playwright round trip per keystroke.
                events = page.evaluate('''async ({source,count,interval,burst})=>{
                    const events=[],e=$('source');
                    for(let i=0;i<count;i++){
                        const token='Marker'+String(100+(burst*count+i)%800);
                        e.value=source.replace('Marker060',token);const at=e.value.indexOf(token);e.setSelectionRange(at,at);
                        const atMs=performance.now();e.dispatchEvent(new InputEvent('input',{bubbles:true}));
                        events.push({clientId:latestClient,atMs,token});
                        if(i+1<count)await new Promise(resolve=>setTimeout(resolve,interval));
                    }return events;
                }''', {'source': sources['chapter.tex'], 'count': args.burst_edits,
                       'interval': args.interval_ms, 'burst': i})
                sample = wait_paint(events[-1]['clientId'])
                record('typing-final', sample, events[-1]['token'])
                paints = page.evaluate('start=>paintHistory.slice(start)', start)
                visible = {p['clientId'] for p in paints if p['visibleMs'] is not None and not p['stale']}
                report['bursts'].append({'events': events, 'paintedInputs': sum(e['clientId'] in visible for e in events),
                                         'supersededInputs': sum(e['clientId'] not in visible for e in events),
                                         'paints': paints, 'burstToFinalMs': sample['visibleMs']+events[-1]['atMs']-events[0]['atMs']})
                settle()

            # Reset the resource seed every time, so every sample adds an unseen font.
            for _ in range(args.repeats):
                reset()
                select('chapter.tex', 'Marker060')
                source = sources['chapter.tex'].replace('\\textbf{Marker060}', '\\texttt{Marker909}')
                sample = wait_paint(edit(source, 'Marker909'))
                assert sample.get('outputMode') == 'page-stream' and sample.get('fontResourceBytes', 0) > 0, sample
                record('new-font', sample, 'Marker909')

            assert not errors, errors
            assert all((project/name).read_text(encoding='utf-8') == source for name, source in sources.items())
            report['checks'] = ['Matching current edit is painted with expected text',
                                'Late chapter reuses nearby checkpoint', 'New font exercises resource refresh',
                                'Typing bursts report superseded inputs separately', 'No browser errors', 'Project sources unchanged']
            browser.close()
        report['cases'] = {}
        for case in dict.fromkeys(s['case'] for s in report['samples']):
            samples = [s for s in report['samples'] if s['case'] == case]
            result = summary([s['visibleMs'] for s in samples])
            result['passes150ms'] = result['p95Ms'] < 150
            result['stages'] = {key: summary([s[key] for s in samples if s.get(key) is not None])
                                for key in ['pipelineMs', 'queueMs', 'requestToPayloadMs', 'deliveryMs', 'compileMs', 'renderMs', 'resourceRefreshMs', 'fontRefreshMs']
                                if any(s.get(key) is not None for s in samples)}
            result['browserStages'] = {key: summary([s['browserStagesMs'][key] for s in samples])
                                       for key in ['prepare', 'decode', 'install', 'paintWait']}
            report['cases'][case] = result
        report['passes150ms'] = all(c['passes150ms'] for c in report['cases'].values())
        print(json.dumps(report['cases'], indent=2), flush=True)
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        try:
            req = urllib.request.Request(url+'/action', data=b'{"type":"close"}', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5):
                pass
            time.sleep(1)
        except OSError:
            pass
        server.terminate()
        server.wait(timeout=15)
        log.close()
    if args.assert_target:
        assert report['passes150ms'], 'One or more scenario p95 values exceed 150 ms; see '+str(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--burst-edits', type=int, default=8)
    parser.add_argument('--interval-ms', type=float, default=35)
    parser.add_argument('--output', default='preview-latency.json')
    parser.add_argument('--assert-target', action='store_true')
    args = parser.parse_args()
    if args.repeats < 2 or args.burst_edits < 2 or args.interval_ms <= 0:
        parser.error('Use at least two repeats and burst edits, and a positive interval.')
    run(args)
