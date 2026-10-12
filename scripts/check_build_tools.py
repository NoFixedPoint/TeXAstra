"""Real BibTeX/Biber/MakeIndex builds, invalidation, idle adoption, and failures."""
import base64
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import fitz
from cpp_client import Client, ROOT, linux

report = {'checks': [],
          'runtimeSha256': hashlib.sha256((ROOT/'native/runtime/texastra-backend').read_bytes()).hexdigest(),
          'sourceHashes': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                           for name in ['native/build_tools.hpp', 'native/compiler.hpp', 'native/main.cpp']}}
root = ROOT/'.work/build tools'
root.mkdir(parents=True, exist_ok=True)


def check(name, ok):
    report['checks'].append({'name': name, 'ok': bool(ok)})
    print(name, bool(ok), flush=True)
    assert ok, name


def require(frame):
    assert frame.get('ok'), frame.get('error', frame)
    return frame


def text(frame):
    return ''.join(row[0] for row in frame['characterRows'])


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def manifest(project):
    return {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()}


def frame(client, **request):
    message = client.request(**request) if request else client.responses.get(timeout=120)
    while message.get('type') != 'frame':
        assert message.get('state') != 'error' and message.get('ok', True), message
        message = client.responses.get(timeout=120)
    return require(message)


def runs(result, tool):
    return [e for e in result.get('buildTools', []) if e['tool'] == tool and not e['reused']]


def pages(client, first):
    return [first] + [require(client.request(type='page', page=n)) for n in range(1, first['pageCount'])]


try:
    # Unique database bytes guarantee a cold auxiliary cache on each invocation.
    unique = str(time.time_ns())
    bib = '@book{alpha,author={Ada Example},title={Alpha Study '+unique+'},year={2020},publisher={Example Press}}\n'
    bib += '@book{beta,author={Bea Example},title={Beta Study},year={2021},publisher={Example Press}}\n'
    sources = {
        'bibtex': r'''\documentclass{article}
\begin{document}
Before citation \cite{alpha}. See Section~\ref{sec:tail}.
\newpage
\section{Tail}\label{sec:tail}
\input{parts/citation}
\bibliographystyle{plain}\bibliography{refs}
\end{document}
''',
        'biber': r'''\documentclass{article}
\usepackage[backend=biber]{biblatex}\addbibresource{refs.bib}
\begin{document}
Before citation \cite{alpha}.
\newpage
\input{parts/citation}\printbibliography
\end{document}
''',
        'index': r'''\documentclass{article}
\usepackage{makeidx}\makeindex
\begin{document}
Before index.\index{Alpha}
\newpage
\input{parts/citation}\index{Beta}\printindex
\end{document}
'''
    }
    for name, source in sources.items():
        project = root/name
        (project/'parts').mkdir(parents=True, exist_ok=True)
        (project/'paper.tex').write_text(source, encoding='utf-8')
        (project/'refs.bib').write_text(bib, encoding='utf-8')
        (project/'parts/citation.tex').write_text('Included text.\n', encoding='utf-8')
        if name == 'index':
            # The source's style works even when the live engine uses jobname main.
            style = 'heading_prefix "\\\\textbf{"\nheading_suffix "}\\\\nopagebreak\\n"\nheadings_flag 1\n% '+unique+'\n'
            (project/'main.ist').unlink(missing_ok=True)
            (project/'paper.ist').write_text(style, encoding='utf-8')
        before = manifest(project)
        tool = {'bibtex': 'bibtex', 'biber': 'biber', 'index': 'makeindex'}[name]
        with Client(project, main='paper.tex') as live, Client(project, main='paper.tex', preview_mode='full') as plain:
            initial = require(live.request(type='start', page=0))
            reference = require(plain.request(type='start', page=0))
            check(name+' invokes distribution tool', len(runs(initial, tool)) == 1)
            check(name+' converges within six passes', not initial['provisional'] and initial['passes'] <= 6)
            check(name+' no unresolved references', not initial['warnings'])
            actual_pages, expected_pages = pages(live, initial), pages(plain, reference)
            check(name+' full-build page count', len(actual_pages) == len(expected_pages))
            for n, (a, b) in enumerate(zip(actual_pages, expected_pages)):
                check(name+f' page {n+1} exact pixels', pixels(a) == pixels(b))
                check(name+f' page {n+1} exact selection', text(a) == text(b))
            content = ''.join(text(p) for p in actual_pages)
            check(name+' generated output appears', ('Alpha Study' if name!='index' else 'Index') in content)
        with Client(project, main='paper.tex') as live:
            reopened = require(live.request(type='start', page=0))
            check(name+' reopen skips auxiliary executable', not runs(reopened, tool))
            check(name+' reopen converged', not reopened['provisional'])
        # Actual asynchronous service: retained edit first, then background build
        # and fresh checkpoints; the auxiliary content cache survives new sessions.
        with Client(project, main='paper.tex', sync=False) as live:
            frame(live, type='start', page=1, clientId=1)
            edit = frame(live, type='edit', file='parts/citation.tex', source='Changed ordinary text.\n', page=1, clientId=2)
            check(name+' text edit reuses checkpoint', edit.get('resumedFrom', 0)>0 and edit['provisional'])
            check(name+' edit path runs no tools', not edit.get('buildTools'))
            done = frame(live)
            check(name+' idle worker converges', done.get('phase')=='converged' and not done['provisional'])
            check(name+' unchanged tool inputs reused across worker', not runs(done, tool))
            if name != 'index':
                changed = bib.replace('Alpha Study', 'Updated Study')
                update = frame(live, type='edit', file='refs.bib', source=changed, page=1, clientId=3)
                check(name+' unsaved bibliography reruns tool', len(runs(update, tool))==1)
                check(name+' unsaved bibliography visible', 'Updated Study' in text(update))
                cite = frame(live, type='edit', file='parts/citation.tex', source=r'Changed citation \cite{beta}.', page=1, clientId=4)
                check(name+' citation edit still incremental', cite['provisional'])
                cited = frame(live)
                check(name+' changed citation reruns tool', len(runs(cited, tool))==1)
                check(name+' changed citation converges', not cited['warnings'] and 'Beta Study' in text(cited))
                frame(live, type='edit', file='parts/citation.tex', source=r'Missing citation \cite{nonexistent}.', page=1, clientId=5)
                missing_cite=frame(live)
                check(name+' missing citation remains diagnostic', any(w.get('code')=='unresolved-references' for w in missing_cite['warnings']))
            else:
                frame(live, type='edit', file='parts/citation.tex', source=r'New entry.\index{Gamma}', page=1, clientId=3)
                indexed = frame(live)
                check('new index entry reruns makeindex', len(runs(indexed, tool))==1)
                last = frame(live, type='page', page=indexed['pageCount']-1)
                check('new index entry visible', 'Gamma' in text(last))
                restyled=frame(live,type='edit',file='paper.ist',source='preamble "\\\\begin{theindex} CustomStyle\\n"\n% '+unique+'\n',page=2,clientId=4)
                check('index style edit reruns makeindex',len(runs(restyled,tool))==1)
                check('index style output visible','CustomStyle' in text(restyled))
        check(name+' source directory unchanged', manifest(project)==before)
    # Undefined references are stable auxiliary state, but must stay visible.
    project=root/'unresolved'; project.mkdir(exist_ok=True)
    (project/'paper.tex').write_text(r'\documentclass{article}\begin{document}See \ref{missing}.\end{document}')
    with Client(project, main='paper.tex') as live:
        result=require(live.request(type='start',page=0))
        check('undefined reference diagnostic', any(w.get('code')=='unresolved-references' for w in result['warnings']))
    # Tool errors do not publish a success manifest or mutate the original tree.
    project=root/'badbib'; project.mkdir(exist_ok=True)
    (project/'paper.tex').write_text(sources['bibtex'].replace('\\input{parts/citation}', ''))
    (project/'refs.bib').write_text('@book{alpha, title={Unclosed\n')
    with Client(project, main='paper.tex') as live:
        failed=live.request(type='start',page=0)
        check('BibTeX failure includes actionable tool output', not failed['ok'] and 'bibtex failed' in failed['error'])
    (project/'refs.bib').write_text(bib)
    with Client(project, main='paper.tex') as live:
        recovered=require(live.request(type='start',page=0))
        check('tool failure recovers after repair', not recovered['provisional'] and not recovered['warnings'])
    # Missing executable is distinct from a failed tool or missing database.
    empty=root/'empty-path'; empty.mkdir(exist_ok=True)
    prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
    for tool in ['kpsewhich','lualatex']:
        (empty/tool).write_text('#!/bin/sh\nexec /usr/bin/'+tool+' "$@"\n',encoding='utf-8',newline='\n')
        subprocess.run(prefix+['chmod','+x',linux(empty/tool)],check=True)
    with Client(project, main='paper.tex', tex_bin=linux(empty)) as live:
        missing=live.request(type='start',page=0)
        check('missing tool names external distribution remedy', not missing['ok'] and
              "'bibtex' is missing" in missing['error'] and 'external LaTeX distribution' in missing['error'])
    (project/'paper.tex').write_text(sources['bibtex'].replace('\\input{parts/citation}', '').replace('{refs}', '{absent}'))
    with Client(project, main='paper.tex') as live:
        missing=live.request(type='start',page=0)
        check('missing database names required input',not missing['ok'] and 'absent.bib' in missing['error'])
    # Included .aux files carry citations and must participate in the parent job.
    project=root/'included-aux'; project.mkdir(exist_ok=True)
    (project/'paper.tex').write_text(sources['bibtex'].replace('\\input{parts/citation}', '\\include{chapter}'))
    (project/'chapter.tex').write_text(r'Included citation \cite{beta}.')
    (project/'refs.bib').write_text(bib)
    with Client(project,main='paper.tex') as live:
        initial=require(live.request(type='start',page=0))
        check('included auxiliary citations resolved',not initial['warnings'] and
              'Beta Study' in ''.join(text(p) for p in pages(live,initial)))
    # A changing label must stop after the declared pass budget, remain
    # provisional, and never be reported as a successful converged build.
    project=root/'unstable'; project.mkdir(exist_ok=True)
    (project/'paper.tex').write_text(r'''\documentclass{article}
\makeatletter
\AtEndDocument{\immediate\write\@auxout{\string\newlabel{changing}{{\directlua{tex.sprint(tostring(os.clock()))}}{1}}}}
\makeatother
\begin{document}Unstable auxiliary state.\end{document}
''')
    with Client(project, main='paper.tex') as live:
        limited=require(live.request(type='start',page=0))
        check('changing auxiliary data bounded to six passes', limited['passes']==6 and limited['provisional'])
        check('convergence limit diagnostic', any(w.get('code')=='convergence-limit' for w in limited['warnings']))
        changed=live.request(type='edit',file='paper.tex',source=r'\documentclass{article}\begin{document}Repaired.\end{document}',page=0)
        check('limited build rejects stale checkpoint reuse',not changed['ok'] and 'complete rebuild' in changed['error'])
    # A deliberately slow replacement tool proves shutdown cancels the process
    # group rather than leaving the idle builder blocked on the child.
    project=root/'cancel'; project.mkdir(exist_ok=True)
    (project/'paper.tex').write_text(sources['bibtex'].replace('\\input{parts/citation}', ''))
    (project/'refs.bib').write_text(bib+'% cancellation\n')
    binpath=root/'slow-bin'; binpath.mkdir(exist_ok=True)
    for tool in ['kpsewhich','lualatex']:
        (binpath/tool).write_text('#!/bin/sh\nexec /usr/bin/'+tool+' "$@"\n',encoding='utf-8',newline='\n')
        subprocess.run(prefix+['chmod','+x',linux(binpath/tool)],check=True)
    marker=root/'tool-running'
    marker.unlink(missing_ok=True)
    (binpath/'bibtex').write_text('#!/bin/sh\nprintf running > "'+linux(marker)+'"\n/bin/sleep 90\n',encoding='utf-8',newline='\n')
    prefix=['wsl','-d','Ubuntu-22.04','--exec'] if os.name=='nt' else []
    subprocess.run(prefix+['chmod','+x',linux(binpath/'bibtex')],check=True)
    live=Client(project,main='paper.tex',sync=False,tex_bin=linux(binpath))
    try:
        live.request(type='start',page=0,clientId=1)
        deadline=time.monotonic()+30
        while not marker.exists() and time.monotonic()<deadline: time.sleep(.05)
        check('auxiliary tool cancellation fixture started',marker.exists())
        started=time.monotonic(); live.close()
        check('shutdown cancels running auxiliary tool',time.monotonic()-started<5)
    finally:
        live.close()
finally:
    (ROOT/'results/build-tools.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
