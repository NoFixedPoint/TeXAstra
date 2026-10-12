"""Engine safe points: nearby chapter rollback and conservative read-ahead."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

import fitz
from cpp_client import Client, ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
args = parser.parse_args()
report = {'checks': [], 'edits': []}


def check(name, ok, **details):
    row = {'name': name, 'ok': bool(ok), **details}
    report['checks'].append(row)
    print(json.dumps(row), flush=True)
    assert ok, name


def require(frame):
    if not frame.get('ok'):
        raise RuntimeError(frame.get('error'))
    return frame


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def regions(frame):
    return [dict(zip(frame['regionFields'], row)) for row in frame['regionRows']]


def manifest(project):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


def write_project(name, sources):
    project = ROOT/'.work/engine-checkpoints'/name
    for file, source in sources.items():
        target = project/file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')
    return project


preamble = ('\\documentclass{article}\n\\usepackage{amsmath}\n'
            '\\setlength{\\textheight}{320pt}\n'
            '\\long\\def\\Wrap#1{#1}\n')
paragraphs = ['\\textbf{Marker%03d} '%i +
              ('A paragraph with ordinary words, café and $x+y+\\alpha$. '*5) + '\n\n'
              for i in range(72)]
try:
    sources = {'paper.tex': preamble+'\\begin{document}\n\\input{chapter}\n\\end{document}\n',
               'chapter.tex': ''.join(paragraphs)}
    project = write_project('long-chapter', sources)
    before = manifest(project)
    with Client(project, args.runtime, 'paper.tex') as live, \
            Client(project, args.runtime, 'paper.tex', preview_mode='full') as plain:
        first = require(live.request(type='start', page=0))
        expected = require(plain.request(type='start', page=0))
        check('long chapter exact first page', pixels(first) == pixels(expected))
        check('long chapter spans many pages', first['pageCount'] >= 10, pages=first['pageCount'])
        original_first_regions = first['regionRows']
        unchanged = require(live.request(type='edit', file='chapter.tex', source=sources['chapter.tex'], page=0))
        check('unchanged input preserves viewport', unchanged['page'] == 0 and pixels(unchanged) == pixels(first))
        target = sources['chapter.tex'].index('Marker060')
        location = require(live.request(type='sync-forward', file='chapter.tex',
                                       line=sources['chapter.tex'][:target].count('\n'),
                                       column=len('\\textbf{'), page=first['pageCount']-1))['location']
        check('late chapter forward mapping', location is not None)
        target_page = location['page']

        def edit(name, file, source, page=target_page, nearby=True):
            sources[file] = source
            actual = require(live.request(type='edit', file=file, source=source, page=page))
            expected = require(plain.request(type='edit', file=file, source=source, page=actual['page']))
            check(name+' exact pixels', pixels(actual) == pixels(expected))
            check(name+' source spans', all(sources[r['file']][r['start']:r['end']] == r['text']
                                           for r in regions(actual)))
            check(name+' navigation enabled', bool(actual['regionRows']) and not actual['warnings'])
            if nearby:
                check(name+' nearby checkpoint', actual.get('resumedFrom', 0) >= target_page-1,
                      checkpoint=actual.get('resumedFrom'), targetPage=target_page+1)
            report['edits'].append({'name': name, **{key: actual[key] for key in
                ('resumedFrom', 'pipelineMs', 'compileMs', 'outputMode') if key in actual}})
            return actual

        token_edit = edit('late chapter token', 'chapter.tex', sources['chapter.tex'].replace('Marker060', 'Marker909'))
        check('late token edit streams without resource export', token_edit['outputMode'] == 'page-stream')
        retained = require(live.request(type='page', page=0))
        check('unchanged earlier command spans retained', retained['regionRows'] == original_first_regions)
        edit('late chapter insertion', 'chapter.tex', sources['chapter.tex'].replace('Marker909', 'Marker909 more words'))
        edit('late chapter new paragraphs', 'chapter.tex', sources['chapter.tex'].replace(
            '\\textbf{Marker061}', 'Inserted paragraph.\n\n\\textbf{Marker061}'))
        # Restore the original prefix while preserving the newer source length
        # and origins in the active input stack across repeated rollback.
        edit('late chapter second edit', 'chapter.tex', sources['chapter.tex'].replace('Marker909 more words', 'Marker060'))
        failure = live.request(type='edit', file='chapter.tex', source=sources['chapter.tex'].replace(
            'Marker060', '\\undefinedBrokenCommand'), page=target_page)
        check('late included error reported', not failure.get('ok'))
        edit('late included error recovery', 'chapter.tex', sources['chapter.tex'])
        appended = edit('append after observed EOF', 'chapter.tex', sources['chapter.tex']+
                        '\\newpage\nAppended content.\n', page=first['pageCount']-1)
        # Requesting a later page replays the suffix with the append in place.
        last = require(plain.request(type='page', page=10000))
        actual = require(live.request(type='page', page=last['page']))
        check('appended page visible', pixels(actual) == pixels(last)
              and 'Appended' in ''.join(row[0] for row in actual['characterRows']))
        edit('root suffix retains chapter edits', 'paper.tex', sources['paper.tex'].replace(
            '\\end{document}', 'Root suffix.\n\\end{document}'), page=last['page'])
        for page in range(last['page']+1):
            a = require(live.request(type='page', page=page))
            b = require(plain.request(type='page', page=page))
            check(f'edited chapter page {page+1} exact pixels', pixels(a) == pixels(b))
            check(f'edited chapter page {page+1} source spans', bool(a['regionRows']) and all(
                sources[r['file']][r['start']:r['end']] == r['text'] for r in regions(a)))
    check('long chapter original files untouched', manifest(project) == before)

    # The full argument is scanned before its first paragraph is typeset.
    # Later output checkpoints must not be used for an edit in that argument.
    sources = {'paper.tex': preamble+'\\begin{document}\nBefore.\n\n\\input{chapter}\n\\end{document}\n',
               'chapter.tex': '\\Wrap{'+''.join(paragraphs[:36])+'}\n'}
    project = write_project('read-ahead', sources)
    with Client(project, args.runtime, 'paper.tex') as live, \
            Client(project, args.runtime, 'paper.tex', preview_mode='full') as plain:
        first = require(live.request(type='start', page=0))
        require(plain.request(type='start', page=0))
        changed = sources['chapter.tex'].replace('Marker030', 'MarkerXYZ')
        a = require(live.request(type='edit', file='chapter.tex', source=changed, page=first['pageCount']-2))
        b = require(plain.request(type='edit', file='chapter.tex', source=changed, page=a['page']))
        check('macro read-ahead uses earlier checkpoint', a.get('resumedFrom') == 1,
              checkpoint=a.get('resumedFrom'), pages=first['pageCount'])
        check('macro read-ahead edit exact pixels', pixels(a) == pixels(b))

    # No literal document-boundary parser or fixed paragraph driver remains.
    source = (preamble+'\\def\\startdoc{\\begin{document}}\n\\startdoc\n'+
              '\\relax\n\n'*2100+'Beyond the former limit.\n\\end{document}\n')
    project = write_project('unbounded-root', {'paper.tex': source})
    with Client(project, args.runtime, 'paper.tex') as live, \
            Client(project, args.runtime, 'paper.tex', preview_mode='full') as plain:
        a = require(live.request(type='start', page=0))
        b = require(plain.request(type='start', page=0))
        check('computed begin and over 2048 paragraphs exact pixels', pixels(a) == pixels(b))
        changed = source.replace('Beyond the former limit.', 'Changed beyond the former limit.')
        a = require(live.request(type='edit', file='paper.tex', source=changed, page=0))
        b = require(plain.request(type='edit', file='paper.tex', source=changed, page=0))
        check('over 2048 paragraphs live edit', pixels(a) == pixels(b) and a.get('resumedFrom') == 1)
finally:
    (ROOT/'results/engine-checkpoints.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
