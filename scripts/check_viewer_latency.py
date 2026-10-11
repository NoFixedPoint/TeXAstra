"""Browser regressions for edit priority and truthful paint measurements."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
report = {'checks': []}


def check(name, passed):
    report['checks'].append({'name': name, 'ok': bool(passed)})
    assert passed, name
    print(name, flush=True)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.add_init_script('window.outbound=[];window.acquireVsCodeApi=()=>({postMessage:m=>outbound.push(m)});')
    page.goto((ROOT/'webview/index.html').as_uri())
    page.wait_for_function('outbound.some(m=>m.type==="ready")')
    page.evaluate('''async ()=>{
        const canvas=document.createElement('canvas');canvas.width=10;canvas.height=10;
        window.testFrame={type:'frame',purpose:'edit',clientId:1,revisionId:1,generation:1,
            page:0,pageCount:5,width:595,height:842,image:canvas.toDataURL(),
            characters:[],regions:[],pipelineMs:1,requestToPayloadMs:2,sentAt:Date.now()-20};
        await receive({type:'status',state:'building',revision:1,clientId:1});
        // Hold the quiet interval open independently of the test machine's speed.
        prefetchAfter=performance.now()+10000;
        await receive(testFrame);scheduleVisible();await new Promise(requestAnimationFrame);
    }''')
    check('neighbor loading waits during edit activity', page.evaluate('!outbound.some(m=>m.type==="page")'))
    sample = page.evaluate('lastPaint')
    check('paint includes backend and browser stages', sample['purpose'] == 'edit' and
          sample['visibleMs'] > 0 and set(sample['browserStagesMs']) == {'prepare', 'decode', 'install', 'paintWait'})
    check('delivery residual accounts for the measured total', abs(sample['visibleMs']-
          sum(sample['browserStagesMs'].values())-sample['deliveryMs']-sample['requestToPayloadMs']) < .001)
    page.evaluate('navigate(1)')
    check('explicit navigation bypasses the quiet interval', page.evaluate('outbound.some(m=>m.type==="page" && m.page===1)'))
    page.evaluate('''async ()=>{
        const request=outbound.find(m=>m.type==='page' && m.page===1);
        await receive({...testFrame,page:1,purpose:'page',requestId:request.requestId});
        outbound.length=0;prefetchAfter=performance.now()+40;
        scheduleVisible();
    }''')
    page.wait_for_function('outbound.some(m=>m.type==="page" && m.page>1)', timeout=5000)
    check('neighbor loading resumes after the quiet interval', True)
    page.evaluate('''async ()=>{
        await receive({type:'status',state:'building',revision:2,clientId:2});
        const pending=receive({...testFrame,clientId:2,revisionId:2,generation:2,sentAt:Date.now()});
        requestAnimationFrame(()=>receive({type:'status',state:'building',revision:3,clientId:3}));
        await pending;
    }''')
    check('revision superseded during paint is excluded from latency', page.evaluate('lastPaint.clientId===2 && lastPaint.stale && lastPaint.visibleMs===null'))
    page.evaluate('receive({...testFrame,clientId:3,revisionId:3,generation:3,phase:"converged",sentAt:null})')
    check('idle convergence is excluded from edit latency', page.evaluate('lastPaint.phase==="converged" && lastPaint.visibleMs===null'))
    check('no browser errors', not errors)

    # The demo must deliver the newer status while an older frame is painting,
    # just as the VS Code message adapter does. Awaiting receive in the polling
    # loop would incorrectly record the old frame as current first.
    frame = page.evaluate('testFrame')
    events = [{'event': 1, 'type': 'status', 'state': 'building', 'revision': 1, 'clientId': 1},
              {**frame, 'event': 2},
              {'event': 3, 'type': 'status', 'state': 'building', 'revision': 2, 'clientId': 2}]
    demo = browser.new_page(viewport={'width': 1440, 'height': 1000})
    demo.on('pageerror', lambda e: errors.append(str(e)))

    def serve(route):
        path = route.request.url.split('preview.test', 1)[1]
        assets = {'/': ('index.html', 'text/html'), '/viewer.js': ('viewer.js', 'text/javascript'),
                  '/viewer.css': ('viewer.css', 'text/css')}
        if path in assets:
            name, content_type = assets[path]
            route.fulfill(body=(ROOT/'webview'/name).read_bytes(), content_type=content_type)
        elif path == '/bootstrap':
            route.fulfill(json={'event': 0, 'sourceFile': 'paper.tex'})
        elif path.startswith('/source'):
            route.fulfill(json={'file': 'paper.tex', 'source': ''})
        elif path.startswith('/events'):
            route.fulfill(json=events if path.endswith('after=0') else [])
        else:
            route.fulfill(json={})

    demo.route('http://preview.test/**', serve)
    demo.goto('http://preview.test/')
    demo.wait_for_function('window.lastPaint', timeout=5000)
    check('demo delivers newer events without waiting for older paint', demo.evaluate('latestClient===2 && lastPaint.clientId===1 && lastPaint.stale && lastPaint.visibleMs===null'))
    check('demo event dispatch has no browser errors', not errors)
    browser.close()

(ROOT/'results/viewer-latency.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
