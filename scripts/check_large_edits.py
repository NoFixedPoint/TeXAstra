"""Large single-file edit benchmark against the real retained compiler."""
import argparse
import json
import statistics
import time
from pathlib import Path

from cpp_client import Client, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='large-edits.json')
    parser.add_argument('--repeats', type=int, default=6)
    parser.add_argument('--assert-target', action='store_true')
    parser.add_argument('--deltas', action='store_true', help='Send VS Code UTF-16 changes after the first buffer')
    args = parser.parse_args()
    project = ROOT/'.work/large-edits'
    project.mkdir(parents=True, exist_ok=True)
    source = '\\documentclass{article}\n\\begin{document}\n'
    for n in range(100):
        source += f'Page{n:03d} alpha. A paragraph with $x+y$.\n\n'
        source += ('% ' + 'source padding ' * 50 + '\n') * 10
        if n < 99:
            source += '\\newpage\n'
    source += '\\end{document}\n'
    (project/'paper.tex').write_text(source, encoding='utf-8')
    report = {'characters': len(source), 'pages': 100, 'deltas': args.deltas, 'samples': []}
    with Client(project, main='paper.tex') as client:
        first = client.request(type='start', page=89)
        assert first.get('ok') and first['pageCount'] == 100, first.get('error')
        previous = source
        for i in range(args.repeats + 1):
            word = 'omega' if i % 2 == 0 else 'alpha'
            changed = source.replace('Page089 alpha', 'Page089 ' + word)
            payload = {'source': changed, 'sourceVersion': i+1}
            if args.deltas and i:
                payload = {'sourceVersion': i+1, 'baseVersion': i, 'baseLength': len(previous),
                           'changes': [{'rangeOffset': previous.index('Page089 ')+8,
                                        'rangeLength': 5, 'text': word}]}
            start = time.perf_counter()
            frame = client.request(type='edit', file='paper.tex', page=89, **payload)
            previous = changed
            wall = (time.perf_counter() - start)*1000
            assert frame.get('ok'), frame.get('error')
            assert 'Page089 ' + word in ''.join(row[0] for row in frame['characterRows'])
            assert frame.get('resumedFrom', 0) >= 89, frame.get('resumedFrom')
            row = {'wallMs': wall, **{k: v for k, v in frame.items()
                                    if k.endswith('Ms') or k in ('outputMode', 'resumedFrom')}}
            print(json.dumps(row), flush=True)
            if i:
                report['samples'].append(row)
    assert (project/'paper.tex').read_text(encoding='utf-8') == source
    report['medianMs'] = statistics.median(row['wallMs'] for row in report['samples'])
    report['passes150ms'] = max(row['wallMs'] for row in report['samples']) < 150
    (ROOT/'results'/args.output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if args.assert_target:
        assert report['passes150ms'], f"Large-file edits exceed 150 ms: median {report['medianMs']:.1f} ms"


if __name__ == '__main__':
    main()
