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


def check(runtime, assets):
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
        with Client(project, runtime=runtime, assets=assets, main=main) as live:
            initial = live.request(type='start', page=1)
            assert initial.get('pageCount') == 2, initial
            before = pixels(initial)
            edited = source.replace('clear', 'beautiful')
            actual = live.request(type='edit', file=included, source=edited, page=1)
            assert pixels(actual) != before
            assert actual.get('resumedFrom', 0) > 1, actual.get('resumedFrom')
            with Client(project, runtime=runtime, assets=assets, main=main) as fresh:
                expected = fresh.request(type='start', page=1, overlays={included: edited})
                assert pixels(actual) == pixels(expected), 'included edit differs from fresh compilation'
            failed = live.request(type='edit', file=included, source=edited+'\\undefinedcommand\n', page=1)
            assert not failed.get('ok'), 'invalid TeX unexpectedly compiled'
            recovered = live.request(type='edit', file=included, source=edited, page=1)
            assert pixels(recovered) == pixels(expected), 'error recovery differs from fresh compilation'
        assert (directory/'parts/body.tex').read_text() == source, 'project source was changed'
    return {'ok': True, 'checks': ['long nested path', 'included file checkpoint',
                                  'fresh compile equality', 'syntax error recovery', 'source preservation']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
    parser.add_argument('--assets', type=Path, default=ROOT/'texastra')
    args = parser.parse_args()
    report = check(args.runtime, args.assets)
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/posix-runtime.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
