"""Real Chromium checks for the shared continuous viewer and live protocol."""
import json,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
report={'checks':[]}
def check(name,ok):
    report['checks'].append({'name':name,'ok':bool(ok)});print(name,ok,flush=True);assert ok,name
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(sys.argv[1]);page.wait_for_function('window.lastPaint && !stale',timeout=120000)
    count=page.evaluate('documentCount');check('all page placeholders exist',page.locator('.paper').count()==count and count>5)
    revision=page.evaluate('latestRequest')
    page.locator('#scroll').evaluate('(e)=>e.scrollTop=e.scrollHeight/2')
    page.wait_for_function('page>0 && pages.get(page)?.frame?.generation===generation && pendingPages.size===0',timeout=30000)
    check('wheel/scroll loads middle pages',page.evaluate('page>0 && page<documentCount-1'))
    check('scroll queries preserve source revision',page.evaluate('latestRequest')==revision)
    check('decoded pages are bounded',page.evaluate('[...pages.values()].filter(p=>p.frame).length')<=9)
    # Resolve a source position on an unloaded page through compiler metadata.
    source=page.locator('#source').input_value();offset=source.index('Original paragraph')
    line=source[:offset].count('\n');column=offset-source.rfind('\n',0,offset)-1
    page.evaluate('(l)=>forward(l)',{'file':'paper.tex','line':line,'column':column})
    page.wait_for_function('page===0 && pages.get(0)?.highlight.style.display==="block"',timeout=30000)
    check('forward navigation fetches and scrolls to unloaded page',True)
    region=page.evaluate('pages.get(0).frame.regions.find(r=>r.line===%d && r.column===%d)'%(line,column))
    box=page.locator('#paper').bounding_box();w,h=page.evaluate('[pages.get(0).width,pages.get(0).height]')
    r=region['rect'];page.mouse.click(box['x']+(r[0]+r[2])/2/w*box['width'],box['y']+(r[1]+r[3])/2/h*box['height'])
    page.wait_for_function('(s)=>$("source").selectionStart===s',arg=region['start'])
    check('reverse navigation selects exact source token',page.locator('#source').evaluate('(e)=>e.value.slice(e.selectionStart,e.selectionEnd)')==region['text'])
    previous=page.evaluate('latestRequest')
    page.locator('#source').evaluate('(e,s)=>{e.value=s;e.setSelectionRange(s.indexOf("Updated"),s.indexOf("Updated"));e.dispatchEvent(new InputEvent("input",{bubbles:true}));}',source.replace('Original paragraph','Updated paragraph'))
    page.wait_for_function('(r)=>lastPaint.revision>r && !lastPaint.stale && lastPaint.clientId===latestClient',arg=previous,timeout=30000)
    check('unsaved edit updates live output',page.evaluate('pages.get(0).frame.characters.map(c=>c.text).join("").includes("Updated")'))
    report['edit']=page.evaluate('lastPaint')
    # Scroll during the idle rebuild; its completion must not reset the viewport.
    page.evaluate('navigate(documentCount-1)')
    page.wait_for_function('pages.get(documentCount-1)?.frame?.generation===generation',timeout=30000)
    page.wait_for_function('lastPaint && !stale && [...pages.values()].some(p=>p.frame?.phase==="converged")',timeout=120000)
    page.wait_for_function('pages.get(page)?.frame?.generation===generation',timeout=30000)
    check('convergence preserves scrolled viewport',page.evaluate('page===documentCount-1'))
    # An included file resumes a retained checkpoint in the live session.
    previous=page.evaluate('latestRequest')
    page.evaluate('''()=>{markStale();send({type:'edit',file:'parts/table.tex',source:'Changed include. $x+x$',page});}''')
    page.wait_for_function('(r)=>lastPaint.revision>r && !stale && lastPaint.clientId===latestClient',arg=previous,timeout=30000)
    check('included-file edit stays in live compilation',page.evaluate('lastPaint.compilationMode==="live" && pages.get(page).frame.characters.map(c=>c.text).join("").includes("Changed include")'))
    check('included-file edit reuses a retained checkpoint',page.evaluate('lastPaint.resumedFrom>1'))
    # Invalid source retains the last image but cannot navigate using old spans.
    valid=page.locator('#source').input_value();previous=page.evaluate('latestRequest')
    page.locator('#source').evaluate('(e,s)=>{e.value=s;e.dispatchEvent(new InputEvent("input",{bubbles:true}));}',valid.replace('Updated paragraph',r'\undefinedBrokenCommand'))
    page.wait_for_function('$("status").textContent.includes("Compile error")',timeout=30000)
    check('compile error retains a stale image',page.evaluate('stale && !!document.querySelector(".page-image[src]")'))
    page.locator('#source').evaluate('(e,s)=>{e.value=s;e.dispatchEvent(new InputEvent("input",{bubbles:true}));}',valid)
    page.wait_for_function('(r)=>lastPaint.revision>r && !stale && lastPaint.clientId===latestClient',arg=previous,timeout=30000)
    check('recovers from invalid source',True)
    check('no browser errors',not errors)
    browser.close()
(ROOT/'results/scrolling.json').write_text(json.dumps(report,indent=2)+'\n')
