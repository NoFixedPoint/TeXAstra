"""Differential figure-note edits, resource identity changes, and queued deltas."""
import base64
import json
import time
import fitz
from cpp_client import Client, ROOT

report = {'checks': []}


def check(name, ok):
    report['checks'].append({'name': name, 'ok': bool(ok)})
    print(name, bool(ok), flush=True)
    assert ok, name


def require(frame):
    assert frame.get('ok'), frame.get('error')
    return frame


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


project = ROOT/'.work/figure-resources'
project.mkdir(parents=True, exist_ok=True)
for name, color in [('one', (1, 0, 0)), ('two', (0, 0, 1))]:
    with fitz.open() as pdf:
        page = pdf.new_page(width=80, height=40)
        page.draw_rect(page.rect, color=color, fill=color)
        page.get_pixmap().save(project/(name+'.png'))
        page.get_pixmap().save(project/(name+'.jpg'))
        pdf.save(project/(name+'.pdf'))
source = ('\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n'
          + 'Earlier page.\n\\newpage\n'*4
          + '% Unicode base: café 😀\n'
          + '\\includegraphics[width=100pt]{one.png}\n\n'
          + '{\\footnotesize Note: original figure note.}\n\\newpage\n'
          + 'Later page.\n\\newpage\n'*5+'\\end{document}\n')
(project/'paper.tex').write_text(source, encoding='utf-8')
try:
    with Client(project, main='paper.tex') as live, Client(project, main='paper.tex', preview_mode='full') as plain:
        require(live.request(type='start', page=4))
        require(plain.request(type='start', page=4))

        def compare(label, changed, mode):
            a = require(live.request(type='edit', file='paper.tex', source=changed, page=4))
            b = require(plain.request(type='edit', file='paper.tex', source=changed, page=a['page']))
            check(label+' exact pixels', pixels(a) == pixels(b))
            check(label+' exact selection layer', a['characterRows'] == b['characterRows'])
            check(label+' output path', a['outputMode'] == mode)
            rows = [dict(zip(a['regionFields'], r)) for r in a['regionRows']]
            check(label+' source spans', bool(rows) and all(changed[r['start']:r['end']] == r['text'] for r in rows))
            return a

        changed = source.replace('original figure note', 'updated figure note')
        compare('unchanged PNG note', changed, 'page-stream')
        compare('PNG note insertion', changed.replace('updated', 'a longer updated'), 'page-stream')
        compare('resize retained PNG', changed.replace('width=100pt', 'width=140pt'), 'page-stream')
        compare('font change beside PNG', changed.replace('updated', '\\texttt{updated}'), 'page-stream')
        changed = changed.replace('one.png', 'two.png')
        compare('different image with reused Im name', changed, 'resource-seed')
        compare('note after image replacement', changed.replace('updated', 'revised'), 'page-stream')
        changed = changed.replace('two.png', 'two.jpg')
        compare('switch to JPEG', changed, 'resource-seed')
        compare('unchanged JPEG note', changed.replace('updated', 'revised'), 'page-stream')
        changed = changed.replace('two.jpg', 'two.pdf')
        compare('PDF figure fallback', changed, 'resource-seed')
        compare('PDF note remains conservative', changed.replace('updated', 'revised'), 'resource-seed')

    # Exercise the asynchronous production queue, not just the --sync adapter.
    with Client(project, main='paper.tex', sync=False) as live, Client(project, main='paper.tex', preview_mode='full') as plain:
        def send(message):
            live.process.stdin.write(json.dumps(message, ensure_ascii=False)+'\n')
            live.process.stdin.flush()

        def wait(client):
            while True:
                message = live.responses.get(timeout=120)
                assert not message.get('error'), message.get('error')
                if message.get('type') == 'frame' and message.get('clientId') == client:
                    return require(message)

        send({'type': 'start', 'page': 4, 'clientId': 1})
        wait(1)
        require(plain.request(type='start', page=4))
        changed = source.replace('original', 'starting')
        send({'type': 'edit', 'file': 'paper.tex', 'source': changed, 'sourceVersion': 2, 'page': 4, 'clientId': 2})
        wait(2)
        utf16 = lambda s: len(s.encode('utf-16-le'))//2
        for version in range(3, 13):
            offset = changed.index(' figure note')
            # Two insertions in pre-event coordinates, after and before a non-BMP character.
            changes = [{'rangeOffset': utf16(changed[:offset]), 'rangeLength': 0, 'text': 'x'},
                       {'rangeOffset': utf16(changed[:changed.index('café')]), 'rangeLength': 0, 'text': 'é'}]
            send({'type': 'edit', 'file': 'paper.tex', 'changes': changes, 'baseVersion': version-1,
                  'sourceVersion': version, 'baseLength': utf16(changed), 'page': 4, 'clientId': version})
            changed = changed[:offset]+'x'+changed[offset:]
            changed = changed.replace('café', 'écafé', 1)
        actual = wait(12)
        expected = require(plain.request(type='edit', file='paper.tex', source=changed, page=4))
        check('coalesced Unicode multi-cursor deltas exact pixels', pixels(actual) == pixels(expected))
        check('coalesced deltas keep current revision', not actual['isStale'])
        check('coalesced note stays on page stream', actual['outputMode'] == 'page-stream')
        check('coalesced deltas exact selection layer', actual['characterRows'] == expected['characterRows'])
    check('original fixture unchanged', (project/'paper.tex').read_text(encoding='utf-8') == source)
finally:
    (ROOT/'results/figure-resources.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
