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
    # Keep the next page within prefetch range with the full-width page layout.
    page = browser.new_page(viewport={'width': 900, 'height': 1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.add_init_script('window.outbound=[];window.acquireVsCodeApi=()=>({postMessage:m=>outbound.push(m)});')
    page.goto((ROOT/'webview/index.html').as_uri())
    page.wait_for_function('outbound.some(m=>m.type==="ready")')
    neutral_color = page.locator('#error-title').evaluate('e=>getComputedStyle(e).color')
    check('error header is visible and collapsed on startup', page.locator('#error-title').is_visible() and
          not page.locator('#diagnostics').evaluate('e=>e.open') and neutral_color != 'rgb(165, 45, 45)')
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
          sum(sample['browserStagesMs'].values())-sample['viewerQueueMs']-sample['deliveryMs']-sample['requestToPayloadMs']) < .001)
    page.evaluate('''async ()=>{
        prefetchAfter=performance.now()-1;
        await receive({...testFrame,sentAt:Date.now()-500});
    }''')
    check('slow edit gets a new quiet interval after paint', page.evaluate('prefetchAfter-performance.now()>100'))
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
    page.evaluate('''()=>{
        window.realDecode=Image.prototype.decode;window.decodeReleases=[];
        window.decodeCalls=0;window.activeDecodes=0;window.maxDecodes=0;
        Image.prototype.decode=async function(){
            decodeCalls++;activeDecodes++;maxDecodes=Math.max(maxDecodes,activeDecodes);
            await new Promise(resolve=>decodeReleases.push(resolve));
            try{await realDecode.call(this);}finally{activeDecodes--;}
        };
        window.burstDone=Promise.all(Array.from({length:20},(_,i)=>receive({...testFrame,
            pageCount:1,clientId:50+i,revisionId:50+i,generation:50+i,deliveryId:50+i,
            characters:[{text:String(50+i),rect:[0,0,10,10]}],sentAt:Date.now()})));
        receive({type:'status',state:'building',revision:69,clientId:69});
    }''')
    check('typing burst starts only one image decode', page.evaluate('decodeCalls===1 && queuedFrame.message.clientId===69'))
    check('replaced frames are acknowledged without decoding', page.evaluate('outbound.filter(m=>m.type==="frame-ack"&&m.outcome==="replaced").length===18'))
    check('status delivery stays immediate during slow decode', page.evaluate('latestClient===69 && stale'))
    page.evaluate('decodeReleases.shift()()')
    page.wait_for_function('decodeCalls===2')
    check('active frame paints during typing instead of starving', page.evaluate('lastPaint.clientId===50 && lastPaint.stale && lastPaint.frameAgeMs>=0 && lastPaint.visibleMs===null'))
    page.evaluate('decodeReleases.shift()()')
    page.evaluate('burstDone')
    check('only newest pending frame decodes and final text is installed', page.evaluate('decodeCalls===2 && maxDecodes===1 && lastPaint.clientId===69 && !lastPaint.stale && pages.get(0).layer.textContent==="69"'))
    check('final frame reports queue wait and update interval', page.evaluate('lastPaint.viewerQueueMs>0 && lastPaint.updateIntervalMs>0 && lastPaint.revisionLag===0'))
    page.evaluate('''async()=>{
        Image.prototype.decode=function(){return Promise.reject(new Error('test decode failure'));};
        await receive({...testFrame,clientId:70,revisionId:70,generation:70,deliveryId:70});
        Image.prototype.decode=realDecode;
        await receive({...testFrame,clientId:71,revisionId:71,generation:71,deliveryId:71});
    }''')
    check('decode failure releases delivery and later frames still paint', page.evaluate('outbound.some(m=>m.type==="frame-ack"&&m.deliveryId===70&&m.outcome==="error") && lastPaint.clientId===71'))
    page.evaluate('receive({...testFrame,generation:1,deliveryId:72})')
    check('obsolete generations release delivery without decode', page.evaluate('outbound.some(m=>m.type==="frame-ack"&&m.deliveryId===72&&m.outcome==="discarded")'))
    page.evaluate('receive({type:"status",state:"error",revision:72,clientId:72,error:"Undefined control sequence: <example>"})')
    check('compile error colors header red without expanding', page.locator('#error-title').is_visible() and
          not page.locator('#diagnostics').evaluate('e=>e.open') and
          page.locator('#error-title').evaluate('e=>getComputedStyle(e).color') == 'rgb(165, 45, 45)' and
          page.locator('#error').text_content() == 'Undefined control sequence: <example>' and
          page.locator('#error-title').inner_text() == 'Compile error')
    page.locator('#error-title').click()
    check('user can expand compile error details', page.locator('#error').is_visible() and
          page.locator('#diagnostics').evaluate('e=>e.open'))
    page.evaluate('receive({type:"status",state:"error",revision:72,clientId:72,error:"Undefined control sequence: <updated>"})')
    check('new errors preserve user-expanded panel', page.locator('#diagnostics').evaluate('e=>e.open'))
    page.locator('#error-title').click()
    check('compile error can be collapsed', not page.locator('#diagnostics').evaluate('e=>e.open'))
    page.evaluate('''async()=>{
        await receive({type:'status',state:'building',revision:73,clientId:73});
        await receive({...testFrame,clientId:71,revisionId:71,generation:71});
    }''')
    check('retry and stale frames retain collapsed compile error', page.locator('#diagnostics').is_visible() and
          not page.locator('#diagnostics').evaluate('e=>e.open') and
          'Undefined control sequence' in page.locator('#error').text_content())
    page.locator('#error-title').click()
    page.evaluate('receive({...testFrame,clientId:73,revisionId:73,generation:73,warnings:["Nonfatal warning"]})')
    check('successful compile clears red state and preserves user expansion', page.locator('#error-title').is_visible() and
          page.locator('#diagnostics').evaluate('e=>e.open') and
          page.locator('#error-title').evaluate('e=>getComputedStyle(e).color') == neutral_color and
          page.locator('#error').text_content() == '')
    page.locator('#error-title').click()
    page.evaluate('receive({type:"status",state:"error",revision:74,clientId:74})')
    check('error without details stays collapsed with fallback text', page.locator('#error-title').is_visible() and
          not page.locator('#diagnostics').evaluate('e=>e.open') and bool(page.locator('#error').text_content()))
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
