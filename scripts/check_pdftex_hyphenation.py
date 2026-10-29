"""Exercise real pdfTeX word reconstruction and compare against stock layout."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import fitz

from cpp_client import Client, ROOT, disk_path, linux


PARAGRAPH = ('representation information office difficult efficient\n' * 2).rstrip()
CASES = [
    ('minimal', '', 'a information', False),
    ('narrow paragraph', r'\hsize=110pt', PARAGRAPH, True),
    ('hyphenation exceptions', r'\hsize=40pt\hyphenation{in-for-ma-tion}',
     'a information information information information', True),
    ('no patterns', r'\language=255', 'a information xyzzy', False),
    ('no break points', '', 'a xyzzy', False),
]


def strip_origins(stream):
    # Undo precisely the TJ splits inserted by ta_glyph_begin/end. Do not
    # normalize positioning, whitespace, or any other PDF operators.
    stream = re.sub(
        rb'\)\]TJ\n/BakoSource << /V 1 /ID \d+ /N 1 /Kind /Glyph /Length \d+ >> BDC\n\[\(',
        b'', stream)
    return stream.replace(b')]TJ\nEMC\n[(', b'')


def compile_reference(project, engine, marked=False):
    prefix = ['wsl', '-d', 'Ubuntu-22.04', '--cd', linux(project), '--exec'] if os.name == 'nt' else []
    environment = ['env']
    for variable in ['TEXMFCNF', 'TEXMFROOT']:
        value = subprocess.check_output(prefix+['kpsewhich', '--var-value='+variable], text=True).strip()
        environment.append(variable+'='+value)
    if marked:
        environment.append('TEXASTRA_PDFTEX_SOURCES='+linux(project/'sources.tsv'))
    result = subprocess.run(prefix+environment+[
        linux(engine), '--progname=pdflatex', '--fmt=pdflatex',
        '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', 'main.tex',
    ], cwd=project, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, result.stdout.decode(errors='replace')[-3000:]
    return fitz.open(project/'main.pdf')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
    parser.add_argument('--original-engine', type=Path,
                        help='Optional pre-fix patched binary for additional fidelity comparison')
    parser.add_argument('--output', default='pdftex-hyphenation.json')
    args = parser.parse_args()
    report = {'checks': []}

    def check(name, ok, **details):
        row = dict(name=name, ok=bool(ok), **details)
        report['checks'].append(row)
        print(json.dumps(row), flush=True)

    (ROOT/'.work').mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='pdftex-hyphenation-', dir=ROOT/'.work') as folder:
            project = Path(folder)
            for label, settings, body, breaks in CASES:
                source = ('\\documentclass{article}\n\\pagestyle{empty}\n'
                          '\\begin{document}\n\\pretolerance=-1\n'+settings+
                          '\n\\noindent\n'+body+'\n\\par\n\\end{document}\n')
                (project/'main.tex').write_text(source, encoding='utf-8')
                (project/'sources.tsv').write_text('1\t'+linux(project/'main.tex')+'\n', encoding='utf-8')
                with Client(project, runtime=args.runtime, compiler='pdflatex', preview_mode='full') as client:
                    frame = client.request(type='start', page=0)
                    assert frame.get('sourceSync') == 'token-and-macro-origin', frame.get('error')
                    regions = [dict(zip(frame['regionFields'], r)) for r in frame['regionRows']]
                    start = source.index(body)
                    end = start+len(body)
                    missing = [i for i in range(start, end) if source[i].isalpha() and not any(
                        r['file'] == 'main.tex' and r['start'] <= i < r['end']
                        and start <= r['start'] < r['end'] <= end for r in regions)]
                    wrong = [r for r in regions if not (start <= r['start'] < r['end'] <= end)]
                    check(label+' letter origins', not missing and not wrong,
                          glyphs=len(regions), wrongOrigins=len(wrong), missingLetters=len(missing))
                    if label == 'narrow paragraph':
                        ffi = source.index('ffi')
                        check('rebuilt ligature span', any(
                            r['start'] == ffi and r['end'] == ffi+3 for r in regions))
                        # The second repeated word must navigate to its own occurrence.
                        pos = source.index('representation', start+1)+4
                        response = client.request(type='sync-forward', file='main.tex',
                                                  line=source[:pos].count('\n'),
                                                  column=pos-source.rfind('\n', 0, pos)-1, page=0)
                        location = response.get('location')
                        check('rebuilt character forward navigation', location and location['start'] == pos)
                        if location:
                            rect = location['rect']
                            reverse = client.request(type='sync-backward', page=0,
                                                     x=(rect[0]+rect[2])/2, y=(rect[1]+rect[3])/2)
                            check('rebuilt character reverse navigation',
                                  reverse.get('location', {}).get('start') == pos)
                    pdf_bytes = (disk_path(frame['session'])/'main.pdf').read_bytes()
                with fitz.open(stream=pdf_bytes, filetype='pdf') as actual:
                    check(label+' automatic hyphenation exercised',
                          not breaks or any('-\n' in p.get_text() for p in actual))
                    engines = [('stock', args.runtime/'pdftex-baseline', False)]
                    if args.original_engine:
                        engines.append(('original patched', args.original_engine, True))
                    for oracle, engine, marked in engines:
                        with compile_reference(project, engine, marked) as expected:
                            check(label+' '+oracle+' page count', len(actual) == len(expected))
                            for i, (a, b) in enumerate(zip(actual, expected)):
                                check(label+' '+oracle+' text '+str(i+1), a.get_text() == b.get_text())
                                check(label+' '+oracle+' pixels '+str(i+1),
                                      a.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).samples ==
                                      b.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False).samples)
                                check(label+' '+oracle+' content stream '+str(i+1),
                                      strip_origins(a.read_contents()) == strip_origins(b.read_contents()))
    finally:
        (ROOT/'results').mkdir(exist_ok=True)
        (ROOT/'results'/args.output).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    assert all(row['ok'] for row in report['checks']), 'pdfTeX hyphenation regression failed'


if __name__ == '__main__':
    main()
