"""Exercise fork checkpoints, nested includes, long paths and error recovery."""
import argparse
import base64
import json
from pathlib import Path
import tempfile

import fitz
from cpp_client import Client, ROOT


def pixels(frame):
    assert frame.get('ok'), frame.get('error')
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def check(runtime, assets, compiler='lualatex'):
    (ROOT/'.work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='posix project ', dir=ROOT/'.work') as folder:
        project = Path(folder)
        relative = Path('nested-'+('long-'*24))/'paper'
        directory = project/relative
        (directory/'parts').mkdir(parents=True)
        main = (relative/'main.tex').as_posix()
        included = (relative/'parts/body.tex').as_posix()
        source = 'The result is clear. $x^2 + y^2 = z^2$\n'
        (directory/'main.tex').write_text(
            '\\documentclass{article}\n\\begin{document}\n'
            'First page.\\newpage\n\\input{parts/body.tex}\n\\end{document}\n')
        (directory/'parts/body.tex').write_text(source)
        options = dict(runtime=runtime, assets=assets, main=main, compiler=compiler,
                       preview_mode='full' if compiler == 'pdflatex' else 'auto')
        with Client(project, **options) as live:
            initial = live.request(type='start', page=1)
            assert initial.get('pageCount') == 2, initial
            before = pixels(initial)
            if compiler == 'pdflatex':
                assert initial.get('sourceSync') == 'token-and-macro-origin', initial.get('sourceSync')
                column = source.index('clear')+1
                location = live.request(type='sync-forward', file=included, line=0, column=column, page=1)['location']
                assert location and location['start'] == column and location['end'] == column+1, location
                rect = location['rect']
                reverse = live.request(type='sync-backward', page=1,
                                       x=(rect[0]+rect[2])/2, y=(rect[1]+rect[3])/2)['location']
                assert reverse and reverse['file'] == included and reverse['start'] == column, reverse
            edited = source.replace('clear', 'beautiful')
            actual = live.request(type='edit', file=included, source=edited, page=1)
            assert pixels(actual) != before
            if compiler == 'pdflatex':
                assert actual.get('retainedState', {}).get('restored'), actual.get('retainedState')
            else:
                assert actual.get('resumedFrom', 0) > 1, actual.get('resumedFrom')
            with Client(project, **options) as fresh:
                expected = fresh.request(type='start', page=1, overlays={included: edited})
                assert pixels(actual) == pixels(expected), 'included edit differs from fresh compilation'
            failed = live.request(type='edit', file=included, source=edited+'\\undefinedcommand\n', page=1)
            assert not failed.get('ok'), 'invalid TeX unexpectedly compiled'
            recovered = live.request(type='edit', file=included, source=edited, page=1)
            assert pixels(recovered) == pixels(expected), 'error recovery differs from fresh compilation'
            if compiler == 'pdflatex':
                assert recovered.get('retainedState', {}).get('restored'), recovered.get('retainedState')
        assert (directory/'parts/body.tex').read_text() == source, 'project source was changed'
    checks = ['long nested path', 'included file checkpoint', 'fresh compile equality',
              'syntax error recovery', 'source preservation']
    if compiler == 'pdflatex':
        checks += ['forward character navigation', 'reverse character navigation', 'retained error recovery']
    return {'ok': True, 'compiler': compiler, 'checks': checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
    parser.add_argument('--assets', type=Path, default=ROOT/'texastra')
    parser.add_argument('--compiler', choices=['lualatex', 'pdflatex'], default='lualatex')
    args = parser.parse_args()
    report = check(args.runtime, args.assets, args.compiler)
    (ROOT/'results').mkdir(exist_ok=True)
    name = 'posix-runtime-pdftex.json' if args.compiler == 'pdflatex' else 'posix-runtime.json'
    (ROOT/'results'/name).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
