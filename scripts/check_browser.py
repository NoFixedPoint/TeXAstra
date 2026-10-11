"""Real Chromium interaction checks against the local prototype server."""
import json,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8766'
report={'url':url,'checks':[]}
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url)
    page.wait_for_function('window.lastPaint && !window.lastPaint.stale && window.lastPaint.clientId===latestClient',timeout=90000)
    def edit(text):page.locator('#source').evaluate('(e,text)=>{e.value=text;const start=text.indexOf("Editable word: ");const end=text.indexOf(".",start);e.setSelectionRange(end,end);e.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText"}));}',text)
    canonical=(ROOT/'corpus/pages/page-001.tex').read_text(encoding='utf-8')
    if page.locator('#source').input_value()!=canonical:
        edit(canonical)
        page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=30000)
    report['initialPaint']=page.evaluate('window.lastPaint')
    report['initialRegions']=page.evaluate('frame.regions.length')
    def reverse(region):
        bounds=page.locator('#paper').bounding_box()
        width,height=page.evaluate('[frame.width,frame.height]')
        rect=region['rect'];x=bounds['x']+(rect[0]+rect[2])/2/width*bounds['width'];y=bounds['y']+(rect[1]+rect[3])/2/height*bounds['height']
        page.mouse.click(x,y)
        page.wait_for_function('(expected)=>document.querySelector("#source").value.substring(document.querySelector("#source").selectionStart,document.querySelector("#source").selectionEnd)===expected',arg=region['text'])
        selection=page.locator('#source').evaluate('(e)=>({start:e.selectionStart,end:e.selectionEnd,text:e.value.slice(e.selectionStart,e.selectionEnd)})')
        assert selection['start']==region['start'],(selection,region)
        return selection
    regions=page.evaluate('frame.regions')
    repeated=[r for r in regions if r['line']==4 and r['text']=='x']
    assert len(repeated)==2
    for region in repeated:
        report['checks'].append(dict(name='reverse repeated math x',region=region,selection=reverse(region)))
    for predicate,label in [
        (lambda r:r['line']==4 and r['text']=='a','fraction numerator'),
        (lambda r:r['line']==4 and r['text']=='1','subscript'),
        (lambda r:r['line']==3 and r['text']=='中','Chinese character'),
        (lambda r:r['line']==12 and r['text']=='x','TikZ math label'),
        (lambda r:r['line']==13 and r['text']=='y','rotated TikZ math label'),
        (lambda r:r['kind']=='macro-origin' and r['text']==r'\fixed','generated macro fallback')
    ]:
        region=next(r for r in regions if predicate(r));report['checks'].append(dict(name=label,selection=reverse(region)))
    target=repeated[1]
    page.locator('#source').evaluate('(e,offset)=>{e.focus();e.setSelectionRange(offset,offset);e.dispatchEvent(new MouseEvent("click",{bubbles:true}));}',target['start'])
    assert f":{target['column']+1}" in page.locator('#location').inner_text()
    report['checks'].append(dict(name='forward math navigation',ok=True))
    selected=page.evaluate('''()=>{const layer=document.querySelector('#text-layer');const range=document.createRange();range.selectNodeContents(layer);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);const text=selection.toString();selection.removeAllRanges();return text;}''')
    assert 'English' in selected and '中文' in selected
    report['checks'].append(dict(name='rendered text selection',ok=True))
    original=page.locator('#source').input_value()
    previous=page.evaluate('window.lastPaint.revision')
    edit(original.replace('word: alpha.','word: omega.'))
    assert page.evaluate('stale')
    page.wait_for_function('(previous)=>window.lastPaint.revision>previous&&!window.lastPaint.stale&&window.lastPaint.clientId===latestClient',arg=previous,timeout=20000)
    report['isolatedEdit']=page.evaluate('window.lastPaint')
    assert page.evaluate('frame.characters.map(c=>c.text).join("").includes("omega")')
    # Sustained input is slower than human key repeat but faster than this
    # prototype's compile/render pipeline, so intermediate progress is required.
    before=page.evaluate('after')
    history_start=page.evaluate('paintHistory.length')
    typing_start=page.evaluate('Date.now()')
    scroll_before=page.locator('#scroll').evaluate('(e)=>e.scrollTop')
    for i in range(20):
        edit(original.replace('word: alpha.',f'word: typed{i:02d}.'))
        page.wait_for_timeout(100)
    during=page.evaluate('window.lastPaint')
    page.wait_for_function('!window.lastPaint.stale&&window.lastPaint.clientId===latestClient',timeout=30000)
    history=page.evaluate('(start)=>paintHistory.slice(start)',history_start)
    typing_end=page.evaluate('Date.now()')
    timestamps=[typing_start]+[p['at'] for p in history]+[typing_end]
    scroll_after=page.locator('#scroll').evaluate('(e)=>e.scrollTop')
    caret_visible=page.locator('#caret').evaluate('(e)=>e.style.display!=="none"')
    report['continuousTyping']=dict(lastFrameDuringTyping=during,lastFrame=page.evaluate('window.lastPaint'),eventBefore=before,eventAfter=page.evaluate('after'),frames=len(history),durationMs=typing_end-typing_start,updatesPerSecond=len(history)*1000/(typing_end-typing_start),longestVisibleFreezeMs=max(b-a for a,b in zip(timestamps,timestamps[1:])),scrollStable=scroll_before==scroll_after,caretRestored=caret_visible)
    assert scroll_before==scroll_after and caret_visible,(scroll_before,scroll_after,caret_visible)
    report['checks'].append(dict(name='typing preserves scroll and restores preview caret',ok=True))
    # Introduce unbalanced math, retain preview, and reject navigation from it.
    valid=page.locator('#source').input_value()
    previous=page.evaluate('window.lastPaint.revision')
    edit(valid.replace(r'\frac{a_{1}+b^{2}}{c+d}',r'\frac{a_{1}+b^{2}}{c+d'))
    page.wait_for_function('document.querySelector("#status").textContent.includes("Compile error")',timeout=20000)
    assert page.evaluate('stale')
    assert page.locator('#image').get_attribute('src').startswith('data:')
    report['checks'].append(dict(name='invalid input retains visibly stale image',ok=True))
    edit(valid)
    page.wait_for_function('(previous)=>window.lastPaint.revision>previous&&!window.lastPaint.stale&&window.lastPaint.clientId===latestClient',arg=previous,timeout=20000)
    page.wait_for_function('frame.phase==="converged"',timeout=60000)
    assert page.evaluate('frame.pageCount')==100
    report['checks'].append(dict(name='automatic full-document convergence',ok=True))
    report['checks'].append(dict(name='recovers after invalid input',ok=True))
    # Convergence must restore compiler checkpoints as well as rendered pages.
    # Previously this first far-page edit replayed nearly the entire document.
    page.evaluate('navigate(99)')
    page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=20000)
    page.evaluate("loadSource('pages/page-100.tex')")
    far_original=page.locator('#source').input_value()
    edit(far_original.replace('word: alpha.','word: checkpoint.'))
    page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=20000)
    report['afterConvergenceEdit']=page.evaluate('lastPaint')
    assert report['afterConvergenceEdit']['resumedFrom']==100,report['afterConvergenceEdit']
    assert report['afterConvergenceEdit']['visibleMs']<500,report['afterConvergenceEdit']
    assert page.evaluate('frame.characters.map(c=>c.text).join("").includes("checkpoint")')
    report['checks'].append(dict(name='idle convergence restores far-page checkpoints',ok=True))
    edit(far_original)
    page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=20000)
    page.screenshot(path=str(ROOT/'results/prototype.png'),full_page=True)
    report['browserErrors']=errors
    assert not errors
    browser.close()
(ROOT/'results/browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))
print(f"Passed {len(report['checks'])} interaction checks")
