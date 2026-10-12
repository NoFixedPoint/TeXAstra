"""Shared project assets, isolated builds, reloads and nested source identities."""
import base64
import hashlib
import json

import fitz
from cpp_client import Client, ROOT

report = {'checks': []}
project = ROOT/'.work/shared asset project'
main = 'paper with spaces/paper.tex'
source = r'''\documentclass{article}
\usepackage{graphicx}
\usepackage{../shared/local}
\graphicspath{{../figures/}}
\begin{document}
Opening page. \localword\par
\includegraphics[width=50pt]{chart.png}
\newpage
\input{../shared/body}
\cite{alpha}\bibliographystyle{plain}\bibliography{../shared/refs}
\end{document}
'''
body = 'Shared chapter text.\\par\n'
bib = '@book{alpha,author={Ada Example},title={Shared Study},year={2020},publisher={Example}}\n'


def check(name, ok):
    report['checks'].append({'name': name, 'ok': bool(ok)})
    print(name, bool(ok), flush=True)
    assert ok, name


def require(result):
    assert result.get('ok'), result.get('error', result)
    return result


def frame(client, **request):
    result = client.request(**request)
    while result.get('type') != 'frame':
        assert result.get('state') != 'error' and result.get('ok', True), result
        result = client.responses.get(timeout=120)
    return require(result)


def text(result):
    return ''.join(r[0] for r in result['characterRows'])


def pixels(result):
    return fitz.Pixmap(base64.b64decode(result['image'].split(',', 1)[1])).samples


def image(color):
    pdf = fitz.open()
    page = pdf.new_page(width=40, height=30)
    page.draw_rect(page.rect, color=color, fill=color)
    page.get_pixmap().save(project/'figures/chart.png')
    pdf.close()


def manifest():
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


try:
    for name in ['paper with spaces', 'shared', 'figures']:
        (project/name).mkdir(parents=True, exist_ok=True)
    (project/main).write_text(source, encoding='utf-8')
    (project/'shared/body.tex').write_text(body, encoding='utf-8')
    (project/'shared/refs.bib').write_text(bib, encoding='utf-8')
    (project/'shared/local.sty').write_text(r'\newcommand{\localword}{LocalStyle}', encoding='utf-8')
    image((1, 0, 0))
    before = manifest()
    with Client(project, main=main) as live, Client(project, main=main, preview_mode='full') as plain:
        a = require(live.request(type='start'))
        b = require(plain.request(type='start'))
        check('nested main compiles and converges', a['pageCount'] == b['pageCount'] == 2 and not a['provisional'])
        check('sibling image and local style exact pixels', pixels(a) == pixels(b) and 'LocalStyle' in text(a))
        a2 = require(live.request(type='page', page=1))
        b2 = require(plain.request(type='page', page=1))
        check('sibling bibliography exact pixels and selection', pixels(a2) == pixels(b2) and text(a2) == text(b2) and 'Shared Study' in text(a2))
        check('sibling source navigation uses project-relative identity', any(row[2] == 'shared/body.tex' for row in a2['regionRows']))
        check('nested root source navigation uses project-relative identity', any(row[2] == main for row in a['regionRows']))
        changed = body.replace('Shared chapter', 'Edited chapter')
        edited = require(live.request(type='edit', file='shared/body.tex', source=changed, page=1))
        expected = require(plain.request(type='edit', file='shared/body.tex', source=changed, page=1))
        check('sibling chapter edit restores checkpoint', edited['provisional'] and 'Edited chapter' in text(edited))
        check('sibling chapter edit matches full build', pixels(edited) == pixels(expected))
        forward = require(live.request(type='sync-forward', file='shared/body.tex', line=0, column=3, page=1))
        check('sibling forward navigation', forward['location']['file'] == 'shared/body.tex')
    check('initial builds leave source project untouched', manifest() == before)
    alias_source = source.replace('../shared/body', '../shared/../shared/./body')
    with Client(project, main=main) as live:
        alias = require(live.request(type='start', overlays={main: alias_source}, page=1))
        check('path aliases retain canonical token origins', any(row[2] == 'shared/body.tex' for row in alias['regionRows']))
    with Client(project, main=main) as live:
        initial = require(live.request(type='start'))
        # The prior unsaved edit was never persisted; this reopening must use disk.
        second = require(live.request(type='page', page=1))
        check('reopen uses saved sibling source', 'Shared chapter' in text(second) and 'Edited chapter' not in text(second))
    with Client(project, main=main) as live:
        reopened = require(live.request(type='start'))
        check('unchanged nested project reuses startup cache', reopened['cacheReused'])
    # Actual asynchronous service, same reload protocol sent by the file watcher.
    with Client(project, main=main, sync=False) as live:
        initial = frame(live, type='start', overlays={main: source.replace('Opening', 'Unsaved')})
        image((0, 0, 1))
        before = manifest()
        refreshed = frame(live, type='reload', overlays={main: source.replace('Opening', 'Unsaved')})
        check('saved binary change replaces pixels and invalidates cache', pixels(initial) != pixels(refreshed) and not refreshed['cacheReused'])
        check('disk refresh preserves unsaved root', 'Unsaved' in text(refreshed))
        check('binary reload leaves source project untouched', manifest() == before)
        # Once a buffer is saved/closed, its old overlay must not mask disk edits.
        (project/main).write_text(source.replace('Opening', 'Saved'), encoding='utf-8')
        saved = frame(live, type='reload', overlays={})
        check('reload discards obsolete saved overlays', 'Saved' in text(saved) and 'Unsaved' not in text(saved))
        (project/'shared/local.sty').write_text(r'\newcommand{\localword}{RevisedStyle}', encoding='utf-8')
        styled = frame(live, type='reload', overlays={})
        check('saved sibling style invalidates checkpoints', 'RevisedStyle' in text(styled) and not styled['cacheReused'])
        (project/'shared/refs.bib').write_text(bib.replace('Shared Study', 'Revised Study'), encoding='utf-8')
        refs = frame(live, type='reload', overlays={}, page=1)
        check('saved sibling bibliography reruns tool', 'Revised Study' in text(refs))
        dirty = frame(live, type='edit', file='shared/refs.bib', source=bib.replace('Shared Study', 'Unsaved Study'), page=1)
        check('unsaved sibling bibliography reruns tool', 'Unsaved Study' in text(dirty))
        (project/'shared/body.tex').unlink()
        result = live.request(type='reload', overlays={}, page=1)
        while result.get('state') != 'error':
            assert result.get('type') != 'frame', 'Deleted input must not reuse a stale copy'
            result = live.responses.get(timeout=120)
        check('deleted sibling input reports error', 'body' in result['error'])
        (project/'shared/body.tex').write_text('Recreated chapter.\\par\n', encoding='utf-8')
        before = manifest()
        recovered = frame(live, type='reload', overlays={}, page=1)
        check('created sibling input recovers', 'Recreated chapter' in text(recovered))
        new_source = source.replace(r'\input{../shared/body}', r'\input{../shared/new}')
        created = frame(live, type='reload', overlays={main: new_source, 'shared/new.tex': 'New unsaved file.\\par\n'}, page=1)
        check('new unsaved sibling file resolves', 'New unsaved' in text(created) and not (project/'shared/new.tex').exists())
        added = frame(live, type='edit', file='shared/another.tex', source='Another unsaved chapter.', page=1)
        check('new editor file rebuilds without missing-file error', 'New unsaved' in text(added) and not added['provisional'])
    check('reloads and overlays preserve source project', manifest() == before)
    # Deep paths must not overflow the backend's Unix socket address buffer.
    deep = 'nested-'+'x'*75
    (project/deep).mkdir(exist_ok=True)
    (project/deep/'paper.tex').write_text('\\documentclass{article}\n\\begin{document}\nDeep text.\\par\n\\end{document}\n', encoding='utf-8')
    with Client(project, main=deep+'/paper.tex') as live:
        require(live.request(type='start'))
        edited = require(live.request(type='edit', file=deep+'/paper.tex', source=(project/deep/'paper.tex').read_text().replace('Deep text', 'Deep edit')))
        check('deep paths support compiler and checkpoint sockets', 'Deep edit' in text(edited))
    for invalid in ['../escape.tex', '/tmp/escape.tex']:
        with Client(project, main=invalid) as live:
            result = live.request(type='start')
            check('reject main outside root '+invalid, not result.get('ok') and ('project' in result['error'] or 'relative' in result['error']))
finally:
    report['runtimeSha256'] = hashlib.sha256((ROOT/'native/runtime/texastra-backend').read_bytes()).hexdigest()
    (ROOT/'results/project-assets.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
