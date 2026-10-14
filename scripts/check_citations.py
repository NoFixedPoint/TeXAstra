"""Cold citations, selected-compiler pixels, and real SyncTeX/browser navigation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

import fitz
from playwright.sync_api import sync_playwright
from cpp_client import Client, ROOT, linux, disk_path
from check_beamer import next_frame, pixels


def independent_pdf(project, main, environment):
    """Compile original fixture bytes directly, without the controller."""
    native = os.name == 'nt' and os.environ.get('BAKO_CHECKPOINT_MODE') == 'windows'
    prefix = ['wsl', '-d', 'Ubuntu-22.04', '--cd', linux(project), '--exec'] if os.name == 'nt' and not native else []
    extension = '.exe' if native else ''
    bin_dir = environment['binDirectory']
    stem = Path(main).stem
    for tool in ['pdflatex', 'bibtex', 'pdflatex', 'pdflatex']:
        args = ['-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', main] if tool == 'pdflatex' else [stem]
        result = subprocess.run(prefix+[bin_dir+'/'+tool+extension, *args], cwd=project,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert result.returncode == 0, result.stdout.decode(errors='replace')[-3000:]
    return project/(stem+'.pdf')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--output', default='citations-windows.json' if os.environ.get('BAKO_CHECKPOINT_MODE') == 'windows' else 'citations-wsl.json')
    args = parser.parse_args()
    report = {'checks': []}

    def check(name, ok, **details):
        row = dict(name=name, ok=bool(ok), **details)
        report['checks'].append(row)
        print(json.dumps(row), flush=True)
        assert ok, name

    source = r'''\documentclass{beamer}
\usepackage[authoryear]{natbib}
\begin{document}
\begin{frame}{Literature}
\begin{itemize}
\item \citealp{one}. \cite*{one}. \citet*{one}.
\item \citealp*{one}. \citep{one}.
\end{itemize}
\end{frame}
\begin{frame}{Included}
\input{body}
\end{frame}
\bibliographystyle{plainnat}\bibliography{refs}
\end{document}
'''
    bibliography = '@book{one,author={Ada Example and Bob Author and Carol Writer},title={A Study},year={2025},publisher={Press}}'
    try:
        with tempfile.TemporaryDirectory(prefix='citations-', dir=ROOT/'.work') as folder:
            project = Path(folder)
            for file, text in [('main.tex', source), ('refs.bib', bibliography), ('body.tex', 'Zebra included.\n')]:
                (project/file).write_text(text, encoding='utf-8')
            before = {p.name: p.read_bytes() for p in project.iterdir()}
            for compiler in ['lualatex', 'pdflatex']:
                with Client(project, runtime=args.runtime, compiler=compiler,
                            preview_mode='auto' if compiler == 'lualatex' else 'full', sync=False) as client:
                    frame = next_frame(client, type='start', page=0, clientId=1)
                    text = ''.join(row[0] for row in frame['characterRows'])
                    check(compiler+' first displayed slide has resolved citation variants',
                          text.count('Example') == 5 and text.count('2025') == 5 and '?' not in text,
                          text=text, warnings=frame['warnings'], passes=frame['passes'])
                    check(compiler+' no unresolved or false convergence-limit warning',
                          not any(w['code'] in ['unresolved-references', 'convergence-limit'] for w in frame['warnings']))
            with Client(project, runtime=args.runtime, compiler='pdflatex', preview_mode='full', sync=False) as client:
                frame = next_frame(client, type='start', page=0)
                def query(**request):
                    response = client.request(**request)
                    while response.get('type') == 'frame-transport':
                        response = client.responses.get(timeout=120)
                    assert response.get('type') == 'sync', response
                    return response
                precise=frame['sourceSync']=='token-and-macro-origin'
                check('PDFLaTeX mode advertises available source navigation', frame['sourceSync'] in ['synctex','token-and-macro-origin'])
                reference = project/'reference'; reference.mkdir()
                for file, data in before.items(): (reference/file).write_bytes(data)
                environment = json.loads(disk_path(frame['environmentReport']).read_text())
                with fitz.open(independent_pdf(reference, 'main.tex', environment)) as pdf:
                    check('page count equals independent PDFLaTeX', len(pdf) == frame['pageCount'])
                    for page in range(len(pdf)):
                        rendered = frame if page == 0 else next_frame(client, type='page', page=page)
                        check(f'page {page+1} matches independent PDFLaTeX pixels',
                              pixels(rendered) == pdf[page].get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).samples)
                target = query(type='sync-forward', file='body.tex', line=0, column=0, page=1)['location']
                check('included source forward navigation', target and target['page'] == 1 and target['file'] == 'body.tex')
                rendered = next_frame(client, type='page', page=1)
                char = next(r for r in rendered['characterRows'] if r[0] == 'b')[1]
                x, y = (char[0]+char[2])/2, (char[1]+char[3])/2
                location = query(type='sync-backward', page=1, x=x, y=y)['location']
                check('included source reverse navigation', location and location['file'] == 'body.tex' and location['line'] == 0)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    view = browser.new_page(viewport={'width': 1200, 'height': 900})
                    errors = []
                    view.on('pageerror', lambda error: errors.append(str(error)))
                    view.add_init_script('window.outbound=[];window.acquireVsCodeApi=()=>({postMessage:m=>outbound.push(m)});')
                    view.goto((ROOT/'webview/index.html').as_uri())
                    view.wait_for_function('outbound.some(m=>m.type==="ready")')
                    view.evaluate('async f=>{await receive(f);pages.get(1).element.scrollIntoView();outbound.length=0;}',
                                  dict(rendered, type='frame', purpose='start', clientId=1, revisionId=1, generation=1))
                    bounds = view.locator('#paper-2').bounding_box()
                    view.mouse.click(bounds['x']+x/rendered['width']*bounds['width'], bounds['y']+y/rendered['height']*bounds['height'])
                    messages = view.evaluate('outbound.filter(m=>m.type==="sync-backward")')
                    check('browser click resolves through advertised navigation', len(messages) == (0 if precise else 1))
                    response = query(**messages[0]) if messages else query(type='sync-backward',page=1,x=x,y=y)
                    if messages:view.evaluate('m=>receive(m)', response)
                    check('browser sends resolved source navigation', view.evaluate('outbound.some(m=>m.type==="navigate"&&m.file==="body.tex"&&m.line===0)'))
                    view.evaluate('outbound.length=0;markStale()')
                    view.evaluate('m=>receive(m)', response)
                    check('stale SyncTeX response cannot navigate', not view.evaluate('outbound.some(m=>m.type==="navigate")'))
                    check('browser has no errors', not errors)
                    browser.close()
                edit = next_frame(client, type='edit', file='body.tex', source='\nZebra edited.\n', page=1)
                char = next(r for r in edit['characterRows'] if r[0] == 'b')[1]
                location = query(type='sync-backward', page=1, x=(char[0]+char[2])/2, y=(char[1]+char[3])/2)['location']
                check('unsaved edits refresh navigation', location and location['line'] == 1 and (location['text']=='b' if precise else 'edited' in location['text']))
            check('project sources unchanged', all((project/name).read_bytes() == data for name, data in before.items()))
    finally:
        (ROOT/'results'/args.output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
