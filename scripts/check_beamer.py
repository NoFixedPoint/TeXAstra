"""Real Beamer compilation, itemize click targets, edits and startup passes."""
import argparse
import base64
import json
import os
import tempfile
import time
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright
from cpp_client import Client, ROOT


def require(result):
    assert result.get('ok'), result.get('error', result)
    return result


def next_frame(client, **request):
    result = client.request(**request) if request else client.responses.get(timeout=120)
    while result.get('type') != 'frame':
        assert result.get('state') != 'error' and result.get('ok', True), result
        result = client.responses.get(timeout=120)
    return require(result)


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--startup-only', action='store_true')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--output', default='beamer-windows.json' if os.environ.get('BAKO_CHECKPOINT_MODE') == 'windows' else 'beamer-wsl.json')
    args = parser.parse_args()
    report = {'checks': []}

    def check(name, condition, **details):
        entry = dict(name=name, ok=bool(condition), **details)
        report['checks'].append(entry)
        print(json.dumps(entry), flush=True)
        assert condition, name

    source = r'''\documentclass{beamer}
\begin{document}
\begin{frame}{Title}
\begin{itemize}
\item Zebra first.
\begin{itemize}
\item Quokka nested.
\end{itemize}
\item<2-> Jaguar overlay $x+\alpha$.
\end{itemize}
\end{frame}
\begin{frame}{Later}
\input{body}
\end{frame}
\end{document}
'''
    body = '\\begin{itemize}\n\\item Walrus included.\n\\end{itemize}\n'
    try:
        with tempfile.TemporaryDirectory(prefix='beamer-', dir=ROOT/'.work') as folder:
            project = Path(folder)
            (project/'main.tex').write_text(source, encoding='utf-8')
            (project/'body.tex').write_text(body, encoding='utf-8')
            # New project path guarantees a cold cache. A first preview needs
            # one complete pass; auxiliary convergence happens after delivery.
            with Client(project, runtime=args.runtime, sync=False) as client:
                started = time.monotonic()
                first = next_frame(client, type='start', page=0, clientId=1)
                check('cold opening delivers the first pass', first['passes'] == 1,
                      passes=first['passes'], elapsedMs=(time.monotonic()-started)*1000)
                check('cold opening has usable text and mappings', bool(first['regionRows']) and
                      'Zebra' in ''.join(r[0] for r in first['characterRows']))
                edit = next_frame(client, type='edit', file='main.tex',
                                  source=source.replace('Zebra first.', 'Zebra fresh.'), page=0, clientId=2)
                check('editing before idle convergence retains checkpoints', edit.get('resumedFrom', 0) > 0 and
                      edit['provisional'] and 'fresh' in ''.join(r[0] for r in edit['characterRows']))
                final = next_frame(client)
                check('idle convergence completes the edited revision', final.get('phase') == 'converged' and
                      final['clientId'] == 2 and not final['provisional'] and final['pageCount'] == 3 and
                      'fresh' in ''.join(r[0] for r in final['characterRows']))
            if args.startup_only:
                return
            with Client(project, runtime=args.runtime) as live, Client(project, runtime=args.runtime, preview_mode='full') as plain:
                actual = require(live.request(type='start', page=0))
                expected = require(plain.request(type='start', page=0))
                check('overlay page count matches plain compiler', actual['pageCount'] == expected['pageCount'] == 3)
                frames = []
                for page in range(3):
                    a = actual if page == 0 else require(live.request(type='page', page=page))
                    b = expected if page == 0 else require(plain.request(type='page', page=page))
                    check(f'page {page+1} exact pixels', pixels(a) == pixels(b))
                    frames.append(a)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    view = browser.new_page(viewport={'width': 1200, 'height': 900})
                    errors = []
                    view.on('pageerror', lambda error: errors.append(str(error)))
                    view.add_init_script('window.outbound=[];window.acquireVsCodeApi=()=>({postMessage:m=>outbound.push(m)});')
                    view.goto((ROOT/'webview/index.html').as_uri())
                    view.wait_for_function('outbound.some(m=>m.type==="ready")')

                    def click_token(frame, filename, contents, word):
                        offset = contents.index(word)
                        rows = [dict(zip(frame['regionFields'], r)) for r in frame['regionRows']]
                        target = next((r for r in rows if r['file'] == filename and r['start'] == offset and r['text'] == word[0]), None)
                        check(word+' exact token target', target is not None)
                        message = dict(frame, type='frame', purpose='start', clientId=1, revisionId=1, generation=1)
                        view.evaluate('async f=>{await receive(f);pages.get(f.page).element.scrollIntoView();await new Promise(requestAnimationFrame);outbound.length=0;}', message)
                        bounds = view.locator('#paper' if frame['page'] == 0 else '#paper-'+str(frame['page']+1)).bounding_box()
                        width, height = view.evaluate('n=>[pages.get(n).width,pages.get(n).height]', frame['page'])
                        rect = target['rect']
                        view.mouse.click(bounds['x']+(rect[0]+rect[2])/2/width*bounds['width'],
                                         bounds['y']+(rect[1]+rect[3])/2/height*bounds['height'])
                        sent = view.evaluate('outbound.filter(m=>m.type==="navigate")')
                        check(word+' browser click navigates', bool(sent) and sent[-1]['file'] == filename and sent[-1]['start'] == offset)

                    click_token(frames[0], 'main.tex', source, 'Zebra')
                    click_token(frames[0], 'main.tex', source, 'Quokka')
                    click_token(frames[1], 'main.tex', source, 'Jaguar')
                    click_token(frames[2], 'body.tex', body, 'Walrus')
                    changed = source.replace('Zebra first.', 'Zebra changed and longer.')
                    edited = require(live.request(type='edit', file='main.tex', source=changed, page=0))
                    reference = require(plain.request(type='edit', file='main.tex', source=changed, page=0))
                    check('item edit exact pixels', pixels(edited) == pixels(reference))
                    click_token(edited, 'main.tex', changed, 'Quokka')
                    check('browser has no errors', not errors)
                    browser.close()
            check('source files untouched', (project/'main.tex').read_text() == source and (project/'body.tex').read_text() == body)
    finally:
        (ROOT/'results'/args.output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
