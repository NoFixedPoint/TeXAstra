"""Windows auxiliary tools, assets, cache isolation, and asynchronous recovery."""
import json
import os
import time
from pathlib import Path
import tempfile
import fitz
from cpp_client import Client, ROOT


def main():
    os.environ['BAKO_CHECKPOINT_MODE'] = 'windows'
    report = {'checks': []}
    def check(name, condition):
        report['checks'].append(dict(name=name, ok=bool(condition)))
        print(name, bool(condition), flush=True)
        assert condition, name
    def frame(client, **request):
        message = client.request(**request) if request else client.responses.get(timeout=120)
        while message.get('type') != 'frame':
            assert message.get('state') != 'error' and message.get('ok', True), message
            message = client.responses.get(timeout=120)
        return message
    def text(result):
        return ''.join(row[0] for row in result['characterRows'])
    def calls(result, tool):
        return [item for item in result.get('buildTools', []) if item['tool'] == tool and not item['reused']]
    with tempfile.TemporaryDirectory(prefix='native projects 测试 ', dir=ROOT / '.work') as folder:
        root = Path(folder)
        try:
            for tool in ['bibtex', 'biber', 'makeindex']:
                project = root / tool
                project.mkdir()
                preamble = ''
                body = 'A citation \\cite{entry}.'
                ending = '\\bibliographystyle{plain}\\bibliography{refs}'
                if tool == 'biber':
                    preamble = '\\usepackage[backend=biber]{biblatex}\\addbibresource{refs.bib}'
                    ending = '\\printbibliography'
                if tool == 'makeindex':
                    preamble = '\\usepackage{makeidx}\\makeindex'
                    body = 'An index entry.\\index{Windows}'
                    ending = '\\printindex'
                    # Force a cold content-addressed tool cache on repeated runs.
                    (project / 'main.ist').write_text('% acceptance ' + str(time.time_ns()) + '\n')
                source = '\\documentclass{article}\n' + preamble + '\n\\begin{document}\n' + body + '\n\\newpage\n\\input{body}\n' + ending + '\n\\end{document}\n'
                (project / 'main.tex').write_text(source)
                (project / 'body.tex').write_text('Native text.\n')
                (project / 'refs.bib').write_text('@book{entry,author={Ada Example},title={Native Study ' + str(time.time_ns()) + '},year={2025},publisher={Example}}\n')
                before = {p.name: p.read_bytes() for p in project.iterdir()}
                with Client(project, sync=False) as client:
                    result = frame(client, type='start', page=0, clientId=1)
                    check(tool + ' runs and converges', bool(calls(result, tool)) and not result['provisional'])
                    output = text(result)
                    for page in range(1, result['pageCount']):
                        output += text(frame(client, type='page', page=page))
                    check(tool + ' output appears', ('Index' if tool == 'makeindex' else 'Native Study') in output)
                    changed = frame(client, type='edit', page=1, file='body.tex', source='Updated native text.\n', clientId=2)
                    check(tool + ' edit is incremental', changed.get('snapshot', {}).get('mode') == 'windows' and changed['provisional'])
                    done = frame(client)
                    check(tool + ' idle convergence reuses tool result', done.get('phase') == 'converged' and not calls(done, tool))
                check(tool + ' leaves project untouched', before == {p.name: p.read_bytes() for p in project.iterdir()})
            project = root / 'assets'
            (project / 'paper').mkdir(parents=True)
            (project / 'figures').mkdir()
            pdf = fitz.open(); page = pdf.new_page(width=100, height=100)
            page.draw_rect(fitz.Rect(10, 10, 90, 90), color=(1, 0, 0), fill=(0, 0, 1))
            pdf.save(project / 'figures/chart.pdf'); pdf.close()
            source = '\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\nImage before text.\\includegraphics{../figures/chart.pdf}\n\\newpage\n\\input{body}\n\\end{document}\n'
            (project / 'paper/main.tex').write_text(source)
            (project / 'paper/body.tex').write_text('Native body.\n')
            with Client(project, main='paper/main.tex') as first, Client(project, main='paper/main.tex') as second:
                a = first.request(type='start', page=0); b = second.request(type='start', page=0)
                check('nested project and PDF image', a.get('ok') and b.get('ok') and a['pageCount'] == 2)
                check('concurrent previews isolate cache', a['session'] != b['session'])
            with Client(project, main='paper/main.tex', sync=False) as client:
                frame(client, type='start', page=1, clientId=1)
                client.request(type='edit', file='paper/body.tex', source='\\directlua{os.exit(7)}\n', page=1, clientId=2)
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    message = client.responses.get(timeout=30)
                    if message.get('state') == 'error': break
                check('abrupt compiler exit reports error', message.get('state') == 'error')
                fixed = frame(client, type='edit', file='paper/body.tex', source='Recovered native body.\n', page=1, clientId=3)
                check('abrupt exit recovers on next edit', 'Recovered' in text(fixed))
                # Begin a non-terminating compile, then close while it is active.
                client.request(type='edit', file='paper/body.tex', source='\\directlua{while true do end}\n', page=1, clientId=4)
                time.sleep(.2)
                started = time.monotonic(); client.close()
                check('shutdown cancels compiler tree', time.monotonic() - started < 5)
        finally:
            (ROOT / 'results/windows-projects.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
