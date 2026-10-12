"""Differential checks for font bundles, rollback, retained pages and fallback."""
import base64
import hashlib
import json
import sys
from pathlib import Path

import fitz
from cpp_client import Client, ROOT

report = {'checks': [], 'edits': []}


def check(name, ok, **details):
    report['checks'].append({'name': name, 'ok': bool(ok), **details})
    print(name, bool(ok), flush=True)
    assert ok, name


def require(frame):
    assert frame.get('ok'), frame.get('error')
    return frame


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def rows(frame):
    return [dict(zip(frame['regionFields'], row)) for row in frame['regionRows']]


def manifest(project):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in project.iterdir() if p.is_file()}


project = ROOT/'.work/font-resources'
project.mkdir(parents=True, exist_ok=True)
preamble = ('\\documentclass{article}\n\\usepackage{fontspec,amsmath,graphicx}\n'
            '\\newfontfamily\\demott{DejaVu Sans}\n\\font\\classic=cmr10\n'
            '\\setlength{\\textheight}{320pt}\n')
sources = {'paper.tex': preamble+'\\begin{document}\n\\input{chapter}\n\\end{document}\n',
           'chapter.tex': ''.join('\\textbf{Marker%03d} '%i+
                                 ('A paragraph with ordinary words, café and $x+y+\\alpha$. '*5)+'\n\n'
                                 for i in range(72))}
original = sources['chapter.tex']
for name, text in sources.items():
    (project/name).write_text(text, encoding='utf-8')
with fitz.open() as pdf:
    page = pdf.new_page(width=40, height=20)
    page.draw_rect(fitz.Rect(0, 0, 40, 20), color=(1, 0, 0), fill=(1, 0, 0))
    pdf.save(project/'figure.pdf')
before = manifest(project)
try:
    with Client(project, main='paper.tex') as live, Client(project, main='paper.tex', preview_mode='full') as plain:
        first = require(live.request(type='start', page=0))
        require(plain.request(type='start', page=0))
        session = Path('//wsl.localhost/Ubuntu-22.04')/first['session'].lstrip('/') if sys.platform == 'win32' else Path(first['session'])
        target = original.index('Marker060')
        location = require(live.request(type='sync-forward', file='chapter.tex', line=original[:target].count('\n'), column=8, page=10))['location']
        target_page = location['page']
        check('fixture has a long suffix beyond edited page', target_page < first['pageCount']-1)
        first_pixels, first_rows = pixels(first), first['regionRows']

        def edit(name, changed, refresh=True, fallback=False, seed_stable=True):
            seed = (session/'main.pdf').read_bytes() if seed_stable and not fallback else None
            sources['chapter.tex'] = changed
            actual = require(live.request(type='edit', file='chapter.tex', source=changed, page=target_page))
            expected = require(plain.request(type='edit', file='chapter.tex', source=changed, page=actual['page']))
            check(name+' exact pixels', pixels(actual) == pixels(expected))
            check(name+' exact selection layer', actual['characterRows'] == expected['characterRows'])
            check(name+' source spans', bool(actual['regionRows']) and not actual['warnings'] and
                  all(sources[r['file']][r['start']:r['end']] == r['text'] for r in rows(actual)))
            check(name+' output path', actual['outputMode'] == ('resource-seed' if fallback else 'page-stream'))
            if not fallback:
                if seed_stable:
                    check(name+' seed unchanged', (session/'main.pdf').read_bytes() == seed)
                check(name+' document still unfinished', not (session/'completed.json').exists())
                if refresh:
                    check(name+' font bundle used', actual.get('fontResourceBytes', 0) > 0 and actual.get('fontRefreshMs', 0) > 0)
            report['edits'].append({'name': name, **{k: v for k, v in actual.items()
                                    if k.endswith('Ms') or k in ('fontResourceBytes', 'resourceRefresh', 'outputMode')}})
            return actual

        changed = original.replace('\\textbf{Marker060}', '\\texttt{Marker909}')
        edit('new OpenType font', changed)
        unchanged = require(live.request(type='page', page=0))
        check('font import preserves earlier page pixels and spans', pixels(unchanged) == first_pixels and unchanged['regionRows'] == first_rows)
        changed = changed.replace('Marker909', 'Marker929')
        edit('new glyph in imported subset', changed)
        # Same glyph set, changed positions: the imported font is reusable.
        changed = changed.replace('Marker929', 'Marker299')
        reused = edit('reuse imported glyphs', changed, refresh=False)
        check('known glyphs need no second bundle', 'fontResourceBytes' not in reused)
        # Reuse a new font ID for a different font after rollback.
        edit('rollback to different font', original.replace('\\textbf{Marker060}', '\\textsf{Marker909}'))
        edit('TrueType and new Unicode glyphs', original.replace('\\textbf{Marker060}', '{\\demott Marker909 ŻΩЖ}'))
        edit('Type1 font', original.replace('\\textbf{Marker060}', '{\\classic Marker909 Z}'))
        # Aliases at different sizes share one engine resource and must merge marks.
        edit('font size aliases', original.replace('\\textbf{Marker060}', '{\\ttfamily Marker909} {\\fontsize{14}{16}\\selectfont\\ttfamily ZQ}'))
        # An earlier rollback must not leave the later page with the wrong font.
        changed = original.replace('\\textbf{Marker060}', '\\texttt{Marker909}').replace('Marker000', 'Marker900')
        # Checkpoint 1 predates opening PDF output; its ordinary replay rewrites
        # the on-disk prefix. This is distinct from the isolated font exporter.
        edit('earlier rollback with later font', changed, refresh=False, seed_stable=False)
        expected = require(plain.request(type='page', page=0))
        actual = require(live.request(type='page', page=0))
        check('earlier edited page remains exact', pixels(actual) == pixels(expected))
        # Subsequent page queries can need font bundles from another checkpoint.
        for page in range(target_page, first['pageCount']):
            actual = require(live.request(type='page', page=page))
            expected = require(plain.request(type='page', page=page))
            check(f'suffix page {page+1} pixels after font imports', pixels(actual) == pixels(expected))
        broken = changed.replace('Marker909', '\\undefinedBrokenCommand')
        failure = live.request(type='edit', file='chapter.tex', source=broken, page=target_page)
        check('invalid source still reports error', not failure.get('ok'))
        edit('recovery after font import', changed, refresh=False, seed_stable=False)
        rejected = edit('unsupported font attributes fallback', original.replace('\\textbf{Marker060}',
                        '{\\pdfextension fontattr\\classic{/BakoTest true}\\classic Marker909}'), fallback=True)
        check('rejected font bundle resumes normal finalization', 'unsupported' in rejected.get('resourceRefresh', '').lower())
        edit('external graphics fallback', original.replace('\\textbf{Marker060}', '\\includegraphics{figure.pdf} Marker909'), fallback=True)
    check('original source and asset files untouched', manifest(project) == before)

    # Two buffered pages use one new font. Importing the second page must not
    # mark the first page's older font dictionary as having the new resources.
    multi = ROOT/'.work/font-resources-multiple'
    multi.mkdir(parents=True, exist_ok=True)
    body = '\n\\newpage\n'.join('Page '+str(i)+' original text.\n' for i in range(1, 7))
    root = preamble+'\\begin{document}\n\\input{chapter}\n\\end{document}\n'
    (multi/'paper.tex').write_text(root, encoding='utf-8')
    (multi/'chapter.tex').write_text(body, encoding='utf-8')
    with Client(multi, main='paper.tex') as live, Client(multi, main='paper.tex', preview_mode='full') as plain:
        require(live.request(type='start', page=0))
        require(plain.request(type='start', page=0))
        changed = body.replace('Page 2 original text.', '\\texttt{Page 2 new Z.}').replace('Page 3 original text.', '\\texttt{Page 3 new Q.}')
        a = require(live.request(type='edit', file='chapter.tex', source=changed, page=2))
        b = require(plain.request(type='edit', file='chapter.tex', source=changed, page=2))
        check('later buffered page imports new font', a.get('fontResourceBytes', 0) > 0 and pixels(a) == pixels(b))
        a = require(live.request(type='page', page=1))
        b = require(plain.request(type='page', page=1))
        check('earlier buffered page gets its own font dictionary', a.get('fontResourceBytes', 0) > 0 and pixels(a) == pixels(b))
        for number in [0, 2, 3, 5, 1]:
            a = require(live.request(type='page', page=number))
            b = require(plain.request(type='page', page=number))
            check(f'font imports preserve page {number+1}', pixels(a) == pixels(b))
finally:
    (ROOT/'results/font-resources.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
