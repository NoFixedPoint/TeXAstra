"""Generate a deterministic 100-page acceptance corpus, without generated artifacts."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def generate(root=ROOT / 'corpus', pages=100):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'pages').mkdir(exist_ok=True)
    preamble = r'''\documentclass[10pt]{article}
\usepackage[a4paper,margin=22mm]{geometry}
\usepackage{fontspec}
\usepackage[fontset=fandol]{ctex}
\usepackage{amsmath,amssymb}
\usepackage{tikz}
\usetikzlibrary{calc}
\newcommand{\pair}[1]{#1+#1}
\newcommand{\fixed}{x+y}
\newcommand{\globalword}{global}
\setlength{\parindent}{0pt}
\begin{document}
'''
    (root / 'main.tex').write_text(preamble + '\n'.join(
        rf'\input{{pages/page-{i:03d}.tex}}' for i in range(1, pages+1)
    ) + '\n\\end{document}\n', encoding='utf-8')
    scenarios = []
    for i in range(1, pages+1):
        content = rf'''\section*{{Acceptance page {i}}}
\label{{page:{i}}}
English text repeats: repeat repeat repeat. Editable word: alpha.
Chinese text: 中文排版测试，数学与文字同步。\par
Shared source line: $x+x+y=\frac{{a_{{1}}+b^{{2}}}}{{c+d}}+\alpha+\sum_{{j=1}}^{{n}}j$.
Nested math: $\frac{{x+\frac{{a}}{{b}}}}{{y_{{2}}}}$; macro argument: $\pair{{z}}$; generated macro: $\fixed$.
\begin{{align*}}
 f(x)&=x^{{2}}+2x+1\\
 g(x)&=\int_{{0}}^{{1}} t^{{2}}\,dt
\end{{align*}}
\begin{{tikzpicture}}
\draw (0,0) -- (5,0);
\node at (1,0.5) {{Label $x_{{1}}$}};
\node[rotate=15] at (3,1) {{Label $y^{{2}}$}};
\end{{tikzpicture}}
\par Cross-reference: page \pageref{{page:1}}. Macro: \globalword.
'''
        content += '\n'.join(
            f'Paragraph {j}: A stable reference sentence with repeated words and enough material to exercise paragraph layout. '
            'Changes to line breaking must preserve the complete-build result.\\par'
            for j in range(1,9)
        )
        if i != pages:
            content += '\n\\newpage\n'
        (root / 'pages' / f'page-{i:03d}.tex').write_text(content, encoding='utf-8')
        if i in {1, pages//2, pages}:
            for name, before, after in [
                ('text', 'word: alpha.', 'word: omega.'),
                ('math', 'x+x+y=', 'x+x+z='),
                ('tikz', '(1,0.5)', '(1.5,0.7)'),
                ('invalid', r'\frac{a_{1}+b^{2}}{c+d}', r'\frac{a_{1}+b^{2}}{c+d'),
                ('reflow', 'Editable word: alpha.', 'Editable word: ' + 'expanded phrase ' * 80 + '.'),
            ]:
                scenarios.append(dict(name=f'{name}-{i:03d}', file=f'pages/page-{i:03d}.tex', before=before, after=after))
    scenarios.append(dict(name='global-macro', file='main.tex', before=r'\newcommand{\globalword}{global}', after=r'\newcommand{\globalword}{changed everywhere}'))
    (root / 'scenarios.json').write_text(json.dumps(scenarios, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Generated {pages} source pages in {root}')

if __name__ == '__main__':
    generate()
