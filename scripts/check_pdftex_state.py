"""Adversarial retained pdfTeX: closed writes, failed updates, and read-ahead."""
import json,os,subprocess,tempfile
from pathlib import Path
import fitz
from cpp_client import Client,ROOT,linux
from check_beamer import pixels
from check_citations import disk_path

SOURCE=r'''\documentclass{article}
\newwrite\audit
\begin{document}
\immediate\openout\audit=audit.txt
\immediate\write\audit{Early}
\immediate\closeout\audit
First page. See page \pageref{target}.
\def\future{FutureOriginal}
\newpage
Second page.
\immediate\openout\audit=audit.txt \immediate\write\audit{Late}\immediate\closeout\audit
\newpage
Third page. \future\label{target}
\end{document}
'''

def main():
    report={'checks':[]}
    def check(name,ok,**details):
        row=dict(name=name,ok=bool(ok),**details);report['checks'].append(row);print(json.dumps(row),flush=True);assert ok,name
    try:
        with tempfile.TemporaryDirectory(prefix='pdftex-state-',dir=ROOT/'.work') as folder:
            project=Path(folder);(project/'main.tex').write_text(SOURCE)
            with Client(project,compiler='pdflatex',preview_mode='full') as client:
                frame=client.request(type='start',page=1)
                check('cold state created',frame.get('ok'),error=frame.get('error'))
                session=disk_path(frame['session'])
                prefix=['wsl','-d','Ubuntu-22.04','--cd',linux(project),'--exec'] if os.name=='nt' else []
                def compare(source,edited,label):
                    (project/'main.tex').write_text(source)
                    for _ in range(2):
                        p=subprocess.run(prefix+['pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','main.tex'],cwd=project,stdout=subprocess.PIPE)
                        assert p.returncode==0,p.stdout.decode(errors='replace')[-2000:]
                    with fitz.open(project/'main.pdf') as pdf:
                        check(label+' page count',len(pdf)==edited['pageCount'])
                        for i,page in enumerate(pdf):
                            f=edited if i==edited['page'] else client.request(type='page',page=i)
                            check(label+' exact pixels '+str(i+1),pixels(f)==page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).samples)
                changed=SOURCE.replace('\\immediate\\openout\\audit=audit.txt \\immediate\\write\\audit{Late}\\immediate\\closeout\\audit','Removed later write.')
                edit=client.request(type='edit',file='main.tex',source=changed,page=1)
                check('closed-output edit resumes',edit.get('ok') and edit['retainedState']['restored'],state=edit.get('retainedState'),error=edit.get('error'))
                check('closed output restored to checkpoint contents',(session/'audit.txt').read_text().strip()=='Early')
                compare(changed,edit,'closed output rollback')
                broken=changed.replace('Second page.',r'\UndefinedTestCommand')
                failed=client.request(type='edit',file='main.tex',source=broken,page=1)
                check('compile error reported',not failed.get('ok') and 'Undefined' in failed.get('error',''))
                repaired=changed.replace('Second page.','Second repaired page.')
                recovered=client.request(type='edit',file='main.tex',source=repaired,page=1)
                check('recover from failed retained update',recovered.get('ok') and recovered['retainedState']['restored'],state=recovered.get('retainedState'),error=recovered.get('error'))
                compare(repaired,recovered,'error recovery')
                ahead=repaired.replace('FutureOriginal','FutureChanged')
                edited=client.request(type='edit',file='main.tex',source=ahead,page=2)
                check('read-ahead definition invalidates later states',edited.get('ok') and edited['retainedState']['prefixPages']==0,state=edited.get('retainedState'))
                check('captured definition updated','FutureChanged' in ''.join(r[0] for r in edited['characterRows']))
                compare(ahead,edited,'read frontier')
                reflow=ahead.replace('Third page.',r'Inserted page.\newpage Third page.')
                changed_pages=client.request(type='edit',file='main.tex',source=reflow,page=0)
                check('reference-changing edit converges',changed_pages.get('ok') and not changed_pages['provisional'] and changed_pages['pageCount']==4,passes=changed_pages.get('passes'),pages=changed_pages.get('pageCount'),state=changed_pages.get('retainedState'),provisional=changed_pages.get('provisional'),error=changed_pages.get('error'),text=''.join(r[0] for r in changed_pages.get('characterRows',[])))
                check('reference updated in retained prefix','See page 4' in ''.join(r[0] for r in changed_pages['characterRows']))
                compare(reflow,changed_pages,'cross-reference convergence')
            reading=r'''\documentclass{article}
\newread\testinput
\begin{document}
\openin\testinput=data.tex \read\testinput to\captured \closein\testinput
First page.
\newpage
\captured
\end{document}
'''
            (project/'main.tex').write_text(reading);(project/'data.tex').write_text('ReadOriginal\n')
            with Client(project,compiler='pdflatex',preview_mode='full') as client:
                frame=client.request(type='start',page=1)
                check('read-register fixture compiles',frame.get('ok'))
                updated=client.request(type='edit',file='data.tex',source='ReadChanged\n',page=1)
                check('read-register edits invalidate consumed input',updated.get('ok') and 'ReadChanged' in ''.join(r[0] for r in updated.get('characterRows',[])),state=updated.get('retainedState'),error=updated.get('error'))
    finally:(ROOT/'results/pdftex-state.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
