"""Compare conditional blocks and unbraced math fields with plain LuaLaTeX."""
import argparse, base64, json
from pathlib import Path
import fitz
from cpp_client import Client, ROOT

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, default=ROOT/'native/runtime')
parser.add_argument('--case')
args = parser.parse_args()
cases = {
    'false across paragraphs': '\\iffalse\nHidden.\n\nStill hidden.\n\\fi',
    'nested branches': '\\iftrue\nShown.\n\n\\iffalse Hidden.\\else Visible branch.\\fi\n\\else Hidden.\\fi',
    'numeric operands': '\\ifnum 1<2\nShown.\n\nStill shown.\\else Hidden.\\fi',
    'skipped unbalanced braces': '\\iffalse\n{ Hidden.\n\nStill hidden.\\fi',
    'comments and escaped controls': '\\iffalse\nHidden. % \\fi\n\nHidden \\\\iftrue.\\fi',
    'unbraced accent chain': '\\begin{align}\n\\d\\bar\\Theta\n\\end{align}',
    'unbraced fraction exponent': '$(x)^\\frac{1}{2}$',
    'nested math accents': '$\\hat\\bar\\Theta$',
    'redefined accent without argument': '$\\frac{\\d}{\\d\\theta}$',
    'redefined accent before script': '$\\d^2$',
    'unbraced bold math': '$\\pmb g + \\pmb g\x27$',
    'delimited macro with nested dollars': '\\eq$ x=\\underbrace{1}_{\\text{value $x_i$}} $',
    'starred citation': 'See \\citealp*{example}.',
    'symbol before delimited equation': 'A $\\nu$,\n\\eq$ x=1 $\nwhere x is a value.',
    'virtual fonts and missing glyphs': 'Efficient ffi office. Missing \u2019. $\\theta \\ne \\nu$.',
}
checks = []
def check(name, ok):
    checks.append({'name': name, 'ok': bool(ok)})
    print(json.dumps(checks[-1]), flush=True)
    assert ok, name
def require(frame):
    if not frame.get('ok'): raise RuntimeError(frame.get('error'))
    return frame
def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples
try:
    for name, body in cases.items():
        if args.case and name!=args.case: continue
        project = ROOT/'.work/live-syntax'/name.replace(' ', '-')
        project.mkdir(parents=True, exist_ok=True)
        fonts = '\\usepackage[T1]{fontenc}\\usepackage{mathpazo}\n' if name=='virtual fonts and missing glyphs' else ''
        source = '\\documentclass{article}\n'+fonts+'\\usepackage{amsmath,natbib}\n\\def\\d{\\mathrm{d}}\n\\def\\eq$#1${\\begin{align*}#1\\end{align*}}\n\\begin{document}\nBefore.\n\n'+body+'\n\nAfter.\n\\end{document}\n'
        (project/'main.tex').write_text(source, encoding='utf-8')
        with Client(project, args.runtime, preview_mode='full') as plain, Client(project, args.runtime) as live:
            expected = require(plain.request(type='start', page=0))
            actual = live.request(type='start', page=0)
            check(name+' compiles', actual.get('ok'))
            check(name+' exact pixels', pixels(actual)==pixels(expected))
            spans = [dict(zip(actual['regionFields'], row)) for row in actual['regionRows']]
            check(name+' preserves outside token mapping', any(s['kind']=='token' and s['text']=='A' for s in spans))
            anchor = next(s for s in spans if s['start']==source.index('After.'))['rect']
            character = next(row[1] for row in reversed(actual['characterRows']) if row[0]=='A')
            check(name+' maps the correct visible glyph', abs(anchor[0]-character[0])<0.02 and min(anchor[3],character[3])>max(anchor[1],character[1]))
            edited = source.replace('After.', 'Afterward.')
            actual = require(live.request(type='edit', file='main.tex', source=edited, page=0))
            expected = require(plain.request(type='edit', file='main.tex', source=edited, page=0))
            check(name+' live edit exact pixels', pixels(actual)==pixels(expected))
finally:
    (ROOT/'results/live-syntax.json').write_text(json.dumps({'checks':checks}, indent=2)+'\n')
