"""Compile/edit a UTF-8 project alongside an unrelated legacy-encoded draft.

Optional --project/--main checks an existing project read-only; only aggregate
results are recorded, never private sources or rendered pages.
"""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from cpp_client import Client, ROOT


def manifest(project):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path)
    parser.add_argument('--main', default='main.tex')
    parser.add_argument('--runtime', type=Path)
    args = parser.parse_args()
    report = {'checks': []}

    def check(name, condition):
        report['checks'].append({'name': name, 'ok': bool(condition)})
        print(name, bool(condition), flush=True)
        assert condition, name

    def require(frame):
        assert frame.get('ok'), frame.get('error')
        return frame

    def text(frame):
        return ''.join(row[0] for row in frame['characterRows'])

    (ROOT / '.work').mkdir(exist_ok=True)
    (ROOT / 'results').mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='source-encoding-', dir=ROOT / '.work') as folder:
            project = Path(folder)
            source = '\\documentclass{article}\n\\begin{document}\nCurrent document.\n\\end{document}\n'
            (project / 'main.tex').write_text(source, encoding='utf-8')
            (project / 'old.tex').write_bytes(b'% legacy draft\n\xff\n')
            before = manifest(project)
            with Client(project, runtime=args.runtime) as client:
                frame = require(client.request(type='start', page=0))
                check('unrelated non-UTF-8 draft does not block preview',
                      'Current document.' in text(frame) and bool(frame['regionRows']))
                frame = require(client.request(type='edit', file='main.tex',
                                               source=source.replace('Current', 'Updated'), page=0))
                check('edits remain rendered and mapped',
                      'Updated document.' in text(frame) and bool(frame['regionRows']))
            check('fixture files unchanged', before == manifest(project))
        if args.project:
            before = manifest(args.project)
            try:
                with Client(args.project.resolve(), runtime=args.runtime, main=args.main) as client:
                    frame = require(client.request(type='start', page=0))
                    count = frame['pageCount']
                    check('existing project compiles', count > 0)
                    for page in range(count):
                        if page:
                            frame = require(client.request(type='page', page=page))
                        check(f'existing project page {page + 1} renders and maps',
                              len(frame['image']) > 100 and bool(frame['regionRows']))
            finally:
                check('existing project files unchanged', before == manifest(args.project))
    finally:
        (ROOT / 'results/source-encoding.json').write_text(
            json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
