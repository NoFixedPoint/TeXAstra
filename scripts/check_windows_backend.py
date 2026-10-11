"""Native Windows differential, recovery, resource and latency validation.

Uses isolated projects; does not edit the repository corpus or installed formats.
The oracle is a fresh complete compilation by the same patched compiler.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
import fitz
from cpp_client import Client, ROOT


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT / 'native/runtime/windows-x64')
    parser.add_argument('--pages', type=int, default=100)
    parser.add_argument('--report', type=Path, default=ROOT / 'results/windows-backend.json')
    args = parser.parse_args()
    os.environ['BAKO_CHECKPOINT_MODE'] = 'windows'
    report = {'platform': 'win32-x64', 'pages': args.pages, 'checks': [], 'samples': []}
    def check(name, condition, **details):
        item = dict(name=name, ok=bool(condition), **details)
        report['checks'].append(item)
        print(json.dumps(item), flush=True)
        assert condition, item
    with tempfile.TemporaryDirectory(prefix='native project 测试 ', dir=ROOT / '.work') as location:
        project = Path(location)
        source = '\\documentclass{article}\n\\usepackage{amsmath,tikz}\n\\begin{document}\n'
        sources = {}
        for index in range(args.pages):
            name = f'page-{index + 1:03}.tex'
            source += '\\input{' + name + '}\n' + ('\\newpage\n' if index + 1 < args.pages else '')
            sources[name] = ('Page ' + str(index + 1) + ' alpha. $x+x+y=\\frac{a}{b}$.\n'
                             '\\begin{tikzpicture}\\draw[rotate=15] (0,0) -- (1,1);\\end{tikzpicture}\n')
        source += '\\end{document}\n'
        (project / 'main.tex').write_text(source, encoding='utf-8')
        for name, data in sources.items():
            (project / name).write_text(data, encoding='utf-8')
        overlays = {}
        def oracle(page):
            with Client(project=project, runtime=args.runtime) as fresh:
                result = fresh.request(type='start', page=page, overlays=overlays)
                assert result.get('ok'), result
                return result
        try:
            with Client(project=project, runtime=args.runtime) as client:
                initial = client.request(type='start', page=0)
                check('native complete document', initial.get('ok') and initial.get('pageCount') == args.pages)
                session = Path(initial['session'])
                check('Windows session path', session.is_dir() and str(session).startswith(os.environ['LOCALAPPDATA']))
                pid = None
                middle = args.pages // 2
                cases = [
                    ('late text', args.pages - 1, 'alpha', 'alpha alpha'),
                    ('middle math', middle, 'x+x+y', 'x+x+z'),
                    ('rotated TikZ', middle, 'rotate=15', 'rotate=45'),
                    ('new font glyph', middle, 'alpha', 'Zebra'),
                    ('first-page reflow', 0, 'alpha', 'expanded phrase ' * 200),
                ]
                for label, page, before, after in cases:
                    name = f'page-{page + 1:03}.tex'
                    text = overlays.get(name, sources[name]).replace(before, after)
                    overlays[name] = text
                    started = time.perf_counter()
                    actual = client.request(type='edit', page=page, file=name, source=text)
                    elapsed = (time.perf_counter() - started) * 1000
                    check(label + ' streams checkpoint output', actual.get('ok') and actual.get('outputMode') == 'page-stream', error=actual.get('error'))
                    current_pid = actual['snapshot']['pid']
                    if pid is None:
                        pid = current_pid
                    check(label + ' retains compiler process', current_pid == pid and actual['snapshot']['mode'] == 'windows')
                    if page:
                        check(label + ' skips earlier pages', actual['resumedFrom'] >= page)
                    report['samples'].append(dict(case=label, roundTripMs=elapsed, **{k: v for k, v in actual.items() if k.endswith('Ms') or k in ('resumedFrom', 'fontResourceBytes')}))
                    expected = oracle(page)
                    check(label + ' exact pixels', pixels(actual) == pixels(expected))
                    check(label + ' exact selection', actual['characterRows'] == expected['characterRows'])
                    # Origin IDs are session-local; compare source spans and geometry.
                    check(label + ' exact source mapping', [r[1:] for r in actual['regionRows']] == [r[1:] for r in expected['regionRows']])
                    if label == 'middle math':
                        failed = client.request(type='edit', page=page, file=name, source='\\undefinedBrokenCommand\n' + text)
                        check('invalid TeX reports error', not failed.get('ok') and 'failed' in failed.get('error', '').lower())
                        recovered = client.request(type='edit', page=page, file=name, source=text)
                        check('checkpoint recovery after TeX error', recovered.get('ok') and pixels(recovered) == pixels(expected))
                # Repeated edits measure the retained process after resource refresh.
                name = 'page-001.tex'
                for iteration in range(20):
                    text = overlays[name] + ('\n' if iteration % 2 else '\n\n')
                    started = time.perf_counter()
                    frame = client.request(type='edit', page=0, file=name, source=text)
                    ms = (time.perf_counter() - started) * 1000
                    check('repeat edit ' + str(iteration), frame.get('ok') and frame.get('snapshot', {}).get('pid') == pid)
                    report['samples'].append(dict(case='repeated early edit', roundTripMs=ms, pipelineMs=frame['pipelineMs']))
                samples = [v['roundTripMs'] for v in report['samples'] if v['case'] == 'repeated early edit']
                report['latency'] = {'medianMs': statistics.median(samples), 'p95Ms': sorted(samples)[18]}
                print(json.dumps(report['latency']), flush=True)
                location = client.request(type='sync-forward', file='page-001.tex', line=0, column=1, page=0)
                check('forward source navigation', location.get('ok') and location.get('location') is not None)
        finally:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
