"""Compare retained included-file edits against complete LuaLaTeX builds."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

import fitz
from cpp_client import Client, ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
args = parser.parse_args()
report = {'checks': [], 'edits': []}


def check(name, ok, **details):
    record = {'name': name, 'ok': bool(ok), **details}
    report['checks'].append(record)
    print(json.dumps(record), flush=True)
    assert ok, name


def require(frame):
    if not frame.get('ok'):
        raise RuntimeError(frame.get('error'))
    return frame


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


project = ROOT/'.work/included-edits'
files = {
    'paper.tex': r'''\documentclass{article}
\usepackage{amsmath}
\input{setup}
\def\chapterfile{chapters/chapter}
\begin{document}
ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz $x+y+z$.

\newpage

Second page, before the chapter.

\newpage

Third page, before the chapter.

\input{parts/definitions}

\newpage

\input{\chapterfile}
Body macro: \bodyword.

\newpage

Repeated: \input{parts/detail}
\input{shared}

\newpage

\include{chapters/included}

Final page, after the chapter. \shared
\end{document}
''',
    'setup.tex': '\\input{shared}\n',
    'shared.tex': '\\def\\shared{Alpha}\n',
    'chapters/chapter.tex': 'Chapter text.\n\\input{parts/detail}\n\nAfter nested input.\n',
    'parts/detail.tex': 'Nested text and $x+y$.\n',
    'parts/definitions.tex': '\\def\\bodyword{Alpha}\n',
    'parts/new detail.tex': 'Additional nested text.\n',
    'chapters/included.tex': 'Included chapter text.\n',
    'unused.tex': 'Unused text.\n',
}
for name, source in files.items():
    path = project/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def manifest():
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


original = manifest()
try:
    with Client(project, args.runtime, 'paper.tex') as live, \
            Client(project, args.runtime, 'paper.tex', preview_mode='full') as plain:
        initial = require(live.request(type='start', page=3))
        expected = require(plain.request(type='start', page=3))
        check('initial exact pixels', pixels(initial) == pixels(expected))
        session = (Path('//wsl.localhost/Ubuntu-22.04')/initial['session'].lstrip('/')
                   if os.name == 'nt' else Path(initial['session']))
        check('preamble dependency recorded', any(json.loads(line) == [0, './shared.tex']
              or (json.loads(line)[0] == 0 and json.loads(line)[1].endswith('/shared.tex'))
              for line in (session/'bako-inputs.jsonl').read_text().splitlines()))

        def compare(name, actual, expected):
            check(name+' exact pixels', pixels(actual) == pixels(expected))
            rows = [dict(zip(actual['regionFields'], row)) for row in actual['regionRows']]
            check(name+' valid source spans', all(
                files[r['file']][r['start']:r['end']] == r['text'] for r in rows))
            body_text = ''.join(row[0] for row in actual['characterRows']).strip()
            check(name+' glyph mapping enabled', (bool(rows) or not body_text or body_text.isdigit())
                  and not actual['warnings'], warnings=actual['warnings'])

        def edit(name, file, source, page, all_pages=False):
            files[file] = source
            actual = require(live.request(type='edit', file=file, source=source, page=page))
            expected = require(plain.request(type='edit', file=file, source=source, page=actual['page']))
            check(name+' retained checkpoint', actual.get('resumedFrom', 0) > 1)
            compare(name, actual, expected)
            report['edits'].append({'name': name, **{key: actual[key] for key in
                ('resumedFrom', 'pipelineMs', 'compileMs', 'outputMode') if key in actual}})
            if all_pages:
                for page in range(expected['pageCount']):
                    a = require(live.request(type='page', page=page))
                    b = require(plain.request(type='page', page=page))
                    compare(name+f' page {page+1}', a, b)
                # A provisional stream can retain the old page count until
                # idle convergence. Check each current page here; the service
                # checks below verify the eventual layout after shrinking.
            return actual

        definitions = edit('body macro dependency', 'parts/definitions.tex', '\\def\\bodyword{Omega}\n', 3)
        check('macro dependency restores before definition, not visible use', definitions['resumedFrom'] == 3)
        chapter = edit('computed chapter input', 'chapters/chapter.tex',
                       files['chapters/chapter.tex'].replace('Chapter', 'Changed chapter'), 3)
        nested = edit('nested repeated input', 'parts/detail.tex', 'Revised nested text and $z+y$.\n', 4,
                      all_pages=True)
        check('repeated input restores before its earliest use',
              nested['resumedFrom'] == chapter['resumedFrom'])
        edit('second nested edit', 'parts/detail.tex', 'Nested again and $x+z$.\n', 3)
        location = require(live.request(type='sync-forward', file='parts/detail.tex',
                                       line=0, column=0, page=3))['location']
        check('included-file forward synchronization', location and location['file'] == 'parts/detail.tex'
              and location['start'] == 0 and location['text'] == 'N')
        edit('include command', 'chapters/included.tex', 'Changed included chapter text.\n', 5,
             all_pages=True)
        edit('introduce nested input', 'chapters/chapter.tex',
             files['chapters/chapter.tex']+'\\input{parts/new detail}\n', 3)
        edit('new nested dependency with spaces', 'parts/new detail.tex', 'New nested text.\n', 3)
        failed = live.request(type='edit', file='parts/detail.tex',
                              source='\\undefinedBrokenCommand\n', page=3)
        check('included syntax error reported', not failed.get('ok'))
        edit('included error recovery', 'parts/detail.tex', files['parts/detail.tex'], 3)
        edit('included reflow', 'parts/detail.tex', 'Expanded paragraph. '*400+'\n', 3, all_pages=True)

        # Returning to an earlier root block must discard dependencies from the
        # abandoned suffix, then discover the remaining occurrence on replay.
        edit('root removes chapter input', 'paper.tex',
             files['paper.tex'].replace('\\input{\\chapterfile}', 'Removed chapter.'), 3,
             all_pages=True)
        later = edit('dependency moved to later occurrence', 'parts/detail.tex', 'Short nested text.\n', 4,
                     all_pages=True)
        check('dependency journal follows rollback', later['resumedFrom'] > nested['resumedFrom'])

        for file, reason in [('shared.tex', 'before body checkpoints'),
                             ('unused.tex', 'no recorded body dependency'),
                             ('local.sty', 'Package or asset edit')]:
            result = live.request(type='edit', file=file, source='% changed\n', page=0)
            check(file+' requires safe session rebuild', not result.get('ok') and reason in result['error'])

    # Exercise the asynchronous service used by VS Code, including automatic
    # fallback and adoption of the converged compiler session.
    with Client(project, args.runtime, 'paper.tex', sync=False) as live, \
            Client(project, args.runtime, 'paper.tex', preview_mode='full') as plain:
        def frame(message=None, **request):
            if message is None:
                message = live.request(**request)
            while (message.get('type') != 'frame' or
                   ('clientId' in request and message.get('clientId') != request['clientId'])):
                if message.get('state') == 'error' or message.get('ok') is False:
                    raise RuntimeError(message.get('error'))
                message = live.responses.get(timeout=120)
            return message

        frame(type='start', page=3, clientId=1)
        require(plain.request(type='start', page=3))
        actual = frame(type='edit', file='parts/detail.tex', source='Service edit.\n', page=3, clientId=2)
        expected = require(plain.request(type='edit', file='parts/detail.tex', source='Service edit.\n', page=3))
        check('service included edit reuses checkpoint', actual.get('resumedFrom', 0) > 1
              and actual['clientId'] == 2 and actual['provisional'])
        check('service included edit exact pixels', pixels(actual) == pixels(expected))
        converged = frame(live.responses.get(timeout=120))
        check('service included edit converges', converged.get('phase') == 'converged'
              and not converged['provisional'] and pixels(converged) == pixels(expected))
        actual = frame(type='edit', file='parts/detail.tex', source='After convergence.\n', page=3, clientId=3)
        expected = require(plain.request(type='edit', file='parts/detail.tex', source='After convergence.\n', page=3))
        check('converged session retains input dependencies', actual.get('resumedFrom', 0) > 1
              and pixels(actual) == pixels(expected))
        actual = frame(type='edit', file='shared.tex', source='\\def\\shared{Omega}\n', page=6, clientId=4)
        expected = require(plain.request(type='edit', file='shared.tex', source='\\def\\shared{Omega}\n', page=6))
        check('service rebuilds preamble dependency', 'resumedFrom' not in actual
              and not actual['provisional'] and actual['compilationMode'] == 'live')
        check('preamble rebuild preserves body overlays', pixels(actual) == pixels(expected))
        body = frame(type='page', page=3, clientId=5)
        expected = require(plain.request(type='page', page=3))
        check('body overlay survives preamble rebuild', pixels(body) == pixels(expected))

        for client_id, source in [(6, 'Expanded paragraph. '*400+'\n'), (7, 'Short paragraph.\n')]:
            actual = frame(type='edit', file='parts/detail.tex', source=source, page=3, clientId=client_id)
            expected = require(plain.request(type='edit', file='parts/detail.tex', source=source, page=3))
            check(f'service reflow {client_id} retained edit', actual.get('resumedFrom', 0) > 1
                  and pixels(actual) == pixels(expected))
            converged = frame(live.responses.get(timeout=120))
            check(f'service reflow {client_id} converged layout', converged.get('phase') == 'converged'
                  and converged['pageCount'] == expected['pageCount'] and pixels(converged) == pixels(expected))
    check('project sources remain unchanged', original == manifest())
finally:
    (ROOT/'results/included-edits.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
