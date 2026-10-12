"""Public, reproducible fixture for general-project live and scrolling checks."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def create():
    project=ROOT/'.work/scroll-case';project.mkdir(parents=True,exist_ok=True)
    source=r'''\documentclass{article}
\usepackage{amsmath,graphicx,appendix}
\newcommand{\leaderline}{A\leaders\hbox{.}\hfill B}
\def\d{\mathrm{d}}
\begin{document}
\noindent {\textbf{\huge Title}}

Original paragraph and $x+x+\frac{a}{b}$.
\textbf{JEL:}   O1, O4.
Italic \textit{word}, punctuation and \emph{word}.
Math $\frac{\int_0^1 x\d\mu}{2}$ and $x+\cdots)$.

$$y=x+1$$
where the display must not introduce indentation.

\begin{enumerate}\item Item.\end{enumerate}
\rm

Proof: A separate paragraph.

\leaderline

'''
    source+='\n\n'.join('\\newpage\n'+('Paragraph %d. '%i)*60 for i in range(1,12))
    source+=r'''

\begin{appendices}
\section{Appendix}
\input{parts/table}

After the included table, tokens and $\widetilde F+\widehat x$ still map.

\includegraphics[width=100pt]{plot.pdf}

Text after the imported PDF.
\end{appendices}
\end{document}
'''
    (project/'parts').mkdir(exist_ok=True)
    (project/'parts/table.tex').write_text(r'\begin{tabular}{ll} Included & text \\ Row & two \end{tabular}'+'\n',encoding='utf-8')
    import fitz
    pdf=fitz.open();page=pdf.new_page(width=150,height=70);page.insert_text((10,30),'Imported PDF figure');pdf.save(project/'plot.pdf');pdf.close()
    (project/'paper.tex').write_text(source,encoding='utf-8')
    return project
if __name__=='__main__':print(create())
