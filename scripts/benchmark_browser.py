"""End-to-end samples: source input event through two animation frames."""
import argparse,json,math,sys,statistics
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('url',nargs='?',default='http://127.0.0.1:8769')
parser.add_argument('--pages',type=int,nargs='+',default=[100,50,1])
parser.add_argument('--repeats',type=int,default=6)
parser.add_argument('--output',default='browser-latency.json')
parser.add_argument('--assert-target',action='store_true')
args=parser.parse_args();url=args.url
report={'url':url,'measurement':'source input event to decoded image, text layer, and two requestAnimationFrame callbacks in Chromium','samples':[],'scrolls':[]}
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});page.goto(url)
    page.wait_for_function('window.lastPaint&&!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=90000)
    for number in args.pages:
        page.evaluate('(n)=>navigate(n-1)',number)
        page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=30000)
        page.evaluate('(file)=>loadSource(file)',f'pages/page-{number:03d}.tex')
        original=(ROOT/'corpus'/f'pages/page-{number:03d}.tex').read_text(encoding='utf-8')
        if page.locator('#source').input_value()!=original:
            page.locator('#source').evaluate('(e,text)=>{e.value=text;e.dispatchEvent(new InputEvent("input",{bubbles:true}));}',original)
            page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=30000)
        for kind in ['text','math']:
            for i in range(args.repeats):
                source=original.replace('word: alpha.','word: omega.') if kind=='text' and i%2==0 else original
                if kind=='math' and i%2==0:source=original.replace('x+x+y=','x+x+z=')
                page.locator('#source').evaluate('(e,text)=>{e.value=text;e.dispatchEvent(new InputEvent("input",{bubbles:true}));}',source)
                page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=30000)
                sample=page.evaluate('window.lastPaint');sample.update(case=kind,page=number)
                report['samples'].append(sample);print(kind,number,sample['visibleMs'],flush=True)
    for number in [2,100]:
        page.evaluate('(n)=>navigate(n-1)',number)
        page.wait_for_function('!lastPaint.stale&&lastPaint.clientId===latestClient',timeout=30000)
        report['scrolls'].append(page.evaluate('window.lastPaint'))
    browser.close()
values=sorted(s['visibleMs'] for s in report['samples'])
report['p95Ms']=values[math.ceil(.95*len(values))-1]
report['medianMs']=statistics.median(values)
report['passes150ms']=report['p95Ms']<150
(ROOT/'results'/args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
print('p95',report['p95Ms'],'pass',report['passes150ms'])
if args.assert_target:assert report['passes150ms'],f"p95 {report['p95Ms']} ms exceeds the 150 ms target"
