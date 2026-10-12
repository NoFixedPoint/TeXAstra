"""Compare live edits after preamble PDF initialization with complete builds."""
import argparse
import base64
import hashlib
import json
import tempfile
from pathlib import Path
import fitz
from cpp_client import Client, ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
parser.add_argument('--assets', type=Path, default=ROOT/'prototype')
parser.add_argument('--output', help='Report filename in results/')
parser.add_argument('--case', choices=['hyperref', 'early-object', 'ordinary'])
parser.add_argument('--project', type=Path)
parser.add_argument('--main', default='main.tex')
parser.add_argument('--page', type=int, default=0, help='Zero-based page for an external project')
args = parser.parse_args()
report = {'checks': []}


def check(name, passed):
    report['checks'].append({'name': name, 'ok': bool(passed)})
    print(name, bool(passed), flush=True)
    assert passed, name


def require(frame):
    assert frame.get('ok'), frame.get('error')
    return frame


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def fixture(project, preamble):
    source = ('\\documentclass{article}\n'+preamble+'\n\\begin{document}\n\n'
              'First page.\n\n\\newpage\n\nOriginal text.\n\nMore text.\n\n'
              '\\newpage\n\n\\input{chapter}\n\\end{document}\n')
    (project/'main.tex').write_text(source, encoding='utf-8')
    (project/'chapter.tex').write_text('Included original text.\n\nMore text.\n', encoding='utf-8')
    return source


try:
    if args.project:
        source = (args.project/args.main).read_text(encoding='utf-8')
        before = hashlib.sha256((args.project/args.main).read_bytes()).hexdigest()
        with Client(args.project, args.runtime, main=args.main, assets=args.assets) as live:
            initial = require(live.request(type='start', page=args.page))
            regions = [dict(zip(initial['regionFields'], row)) for row in initial['regionRows']]
            target = next(r for r in regions if r['file'] == args.main and r['kind'] == 'token'
                          and r['text'] in ['a', 'e'] and source[r['start']:r['end']] == r['text'])
            for index, letter in enumerate(['x', target['text'], 'x']):
                changed = source[:target['start']]+letter+source[target['end']:]
                result = live.request(type='edit', file=args.main, source=changed, page=args.page)
                check(f'external project edit {index+1} compiles: '+str(result.get('error', 'ok')), result.get('ok'))
                report.setdefault('edits', []).append({k: result[k] for k in
                    ['outputMode', 'resumedFrom', 'resourceRefresh', 'pipelineMs'] if k in result})
                check(f'external project edit {index+1} reuses a checkpoint', result.get('resumedFrom', 0) > 1)
                check(f'external project edit {index+1} retains source mapping', bool(result['regionRows']))
        check('external source unchanged', before == hashlib.sha256((args.project/args.main).read_bytes()).hexdigest())
    else:
        cases = {'hyperref': '\\usepackage{hyperref}',
                 'early-object': "\\directlua{pdf.immediateobj('<< /Type /Example >>')}",
                 'ordinary': ''}
        for name, preamble in cases.items():
            if args.case and args.case != name:
                continue
            with tempfile.TemporaryDirectory(prefix='preamble-stream-', dir=ROOT/'.work') as folder:
                project = Path(folder)
                source = fixture(project, preamble)
                with Client(project, args.runtime, assets=args.assets) as live, Client(project, args.runtime, preview_mode='full', assets=args.assets) as full:
                    initial = require(live.request(type='start', page=1))
                    baseline = require(full.request(type='start', page=1))
                    check(name+' initial pixels match full build', pixels(initial) == pixels(baseline))
                    edits = [('main.tex', source.replace('Original', 'Changed'), 1),
                             ('main.tex', source.replace('Original', 'Updated'), 1),
                             ('chapter.tex', 'Included changed text.\n\nMore text.\n', 2)]
                    for index, (file, text, page) in enumerate(edits):
                        actual = live.request(type='edit', file=file, source=text, page=page)
                        check(f'{name} edit {index+1} compiles: '+str(actual.get('error', 'ok')), actual.get('ok'))
                        expected = require(full.request(type='edit', file=file, source=text, page=page))
                        check(f'{name} edit {index+1} streams without full export', actual['outputMode'] == 'page-stream')
                        check(f'{name} edit {index+1} pixels match full build', pixels(actual) == pixels(expected))
                        check(f'{name} edit {index+1} selection matches full build', actual['characterRows'] == expected['characterRows'])
                        check(f'{name} edit {index+1} retains token mapping', bool(actual['regionRows']))
                    invalid = live.request(type='edit', file='main.tex', page=1,
                                           source=source.replace('Original', r'\undefinedBrokenCommand'))
                    check(name+' real TeX error is still rejected', not invalid.get('ok') and 'TeX' in invalid.get('error', ''))
                    recovered = require(live.request(type='edit', file='main.tex', page=1,
                                                    source=source.replace('Original', 'Updated')))
                    expected = require(full.request(type='page', page=1))
                    check(name+' valid edit recovers after an error', pixels(recovered) == pixels(expected))
finally:
    suffix = '-external' if args.project else ''
    output = args.output or f'preamble-stream{suffix}.json'
    (ROOT/'results'/output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
