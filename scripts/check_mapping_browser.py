"""Real Chromium clicks on compiler-produced rules and unmapped regions.

Run check_source_mapping.py first to generate the differential test frames.
The VS Code message transport is mocked; layout, hit testing and clicks are real.
"""
import json
from playwright.sync_api import sync_playwright
from cpp_client import ROOT

frames = json.loads((ROOT/'.work/source-mapping/frames.json').read_text(encoding='utf-8'))
report = {'checks': []}


def check(name, ok):
    report['checks'].append({'name': name, 'ok': bool(ok)})
    print(name, bool(ok), flush=True)
    assert ok, name


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.add_init_script('window.outbound=[];window.acquireVsCodeApi=()=>({postMessage:m=>outbound.push(m)});')
        page.goto((ROOT/'webview/index.html').as_uri())
        page.wait_for_function('outbound.some(m=>m.type==="ready")')
        revision = 0

        def install(name):
            global revision
            revision += 1
            frame = {**frames[name], 'type': 'frame', 'purpose': 'start', 'clientId': revision,
                     'revisionId': revision, 'generation': revision, 'page': 2, 'pageCount': 5}
            page.evaluate('''async f=>{await receive(f);pages.get(2).element.scrollIntoView();
                await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);outbound.length=0;}''', frame)
            return frame

        def click(rect):
            bounds = page.locator('#paper-3').bounding_box()
            width, height = page.evaluate('[pages.get(2).width,pages.get(2).height]')
            page.mouse.click(bounds['x']+(rect[0]+rect[2])/2/width*bounds['width'],
                             bounds['y']+(rect[1]+rect[3])/2/height*bounds['height'])

        for name in ['complex math', 'transformed text and rules', 'rollback after faulty markers']:
            frame = install(name)
            rules = [dict(zip(frame['regionFields'], row)) for row in frame['regionRows'] if row[10] == 'rule-origin']
            check(name+' provides rule targets', bool(rules))
            for index, rule in enumerate(rules):
                page.evaluate('outbound.length=0')
                click(rule['rect'])
                sent = page.evaluate('outbound.filter(m=>m.type==="navigate")')
                check(name+f' rule {index+1} click selects expression', bool(sent) and
                      sent[-1]['file'] == rule['file'] and sent[-1]['start'] == rule['start'] and sent[-1]['end'] == rule['end'])
            check(name+' rule remains outside selectable text', page.locator('#text-layer').count() == 1 and
                  page.evaluate('pages.get(2).layer.children.length===pages.get(2).frame.characters.length'))
            if name == 'transformed text and rules':
                rule = rules[0]
                check('rotated rule uses its quadrilateral for hit testing', page.evaluate('''r=>
                    [[r.rect[0],r.rect[1]],[r.rect[2],r.rect[3]]].some(([x,y])=>!regionHit(r,x,y))''', rule))
                glyph = next(dict(zip(frame['regionFields'], r)) for r in frame['regionRows'] if r[9] == 'J')
                page.evaluate('outbound.length=0');click(glyph['rect'])
                check('rotated rule does not steal numerator clicks', page.evaluate(
                    'outbound.some(m=>m.type==="navigate"&&m.text==="J")'))

        for name, reason, explanation in [('localized count', 'glyph-count-mismatch', 'differs'),
                                          ('localized unknown', 'unknown-source', 'no longer available'),
                                          ('localized untagged', 'untagged-content', 'no source marker'),
                                          ('Lua glyph without origin', 'missing-origin', 'did not retain'),
                                          ('imported PDF', 'external-content', 'imported PDF')]:
            frame = install(name)
            region = next(r for r in frame['unmappedRegions'] if r['reason'] == reason)
            click(region['rect'])
            check(name+' click explains missing navigation', explanation in page.locator('#location').inner_text())
            check(name+' click does not navigate elsewhere', not page.evaluate('outbound.some(m=>m.type==="navigate")'))
            good = next(dict(zip(frame['regionFields'], r)) for r in frame['regionRows'] if r[9] == 'Q' or r[9] == 'J')
            click(good['rect'])
            check(name+' nearby text still navigates', page.evaluate('outbound.some(m=>m.type==="navigate")'))

        page.evaluate('outbound.length=0;markStale()')
        click(good['rect'])
        check('stale mapping cannot navigate', not page.evaluate('outbound.some(m=>m.type==="navigate")'))
        check('no browser errors', not errors)
        browser.close()
finally:
    (ROOT/'results/mapping-browser.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
