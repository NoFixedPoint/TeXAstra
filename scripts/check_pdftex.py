"""Real pdfTeX provenance and retained-state acceptance, against stock pdfTeX."""
import argparse, json, os, subprocess, tempfile
from pathlib import Path
import fitz
from cpp_client import Client, ROOT, linux, disk_path
from check_posix_runtime import pixels

SOURCE = r'''\documentclass{article}
\usepackage{amsmath,tikz}
\newcommand{\swap}[2]{#2 #1}
\newcommand{\store}[1]{\gdef\saved{#1}}
\newcommand{\generated}{Rabbit}
\newsavebox{\savedbox}
\begin{document}
Zebra Quokka office. Zebra
\par\swap{Lion}{Tiger}
\store{Walrus}
\par\saved\quad\generated
\sbox{\savedbox}{Otter}\par\usebox{\savedbox}\quad\usebox{\savedbox}
\par $x+y=\alpha+\frac{a}{b}+\frac cd+z^w_v$
\par\input{included}
\par\hrule width 3cm height 0.5pt
\newpage
Second page. \begin{tikzpicture}\node[rotate=20]{Penguin};\end{tikzpicture}
\end{document}
'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path);parser.add_argument('--output',default='pdftex.json');args=parser.parse_args()
    report={'checks':[]}
    def check(name,ok,**details):
        row=dict(name=name,ok=bool(ok),**details);report['checks'].append(row)
        print(json.dumps(row),flush=True);assert ok,name
    try:
        with tempfile.TemporaryDirectory(prefix='pdftex-',dir=ROOT/'.work') as folder:
            project=Path(folder)
            (project/'main.tex').write_text(SOURCE,encoding='utf-8')
            (project/'included.tex').write_text('Narwhal included.\n',encoding='utf-8')
            with Client(project,runtime=args.runtime,compiler='pdflatex',preview_mode='full') as client:
                frame=client.request(type='start',page=0)
                (ROOT/'.work/pdftex-frame.json').write_text(json.dumps(frame,indent=2))
                environment = json.loads(disk_path(frame['environmentReport']).read_text()) if frame.get('environmentReport') else {}
                check('real pdfTeX provenance enabled',frame.get('sourceSync')=='token-and-macro-origin',
                      error=frame.get('error'), sourceSync=frame.get('sourceSync'),
                      binDirectory=environment.get('binDirectory'),
                      compatible=environment.get('pdftexProvenanceCompatible'),
                      bundledPdftex=environment.get('pdftexProvenanceEngine'))
                rows=frame['regionRows']; fields=frame['regionFields']
                regions=[dict(zip(fields,r)) for r in rows]
                (ROOT/'.work/pdftex-regions.json').write_text(json.dumps(regions,indent=2))
                for word in ['Zebra','Quokka','Lion','Tiger','Walrus','Rabbit','Otter']:
                    pos=SOURCE.index(word)
                    check(word+' source characters',all(any(r['start']==pos+i and r['text']==c for r in regions) for i,c in enumerate(word)))
                pos=SOURCE.index('ffi')
                check('ligature carries complete source span',any(r['start']==pos and r['text']=='ffi' for r in regions))
                check('included file has character origins',any(r['file']=='included.tex' and r['text']=='N' and r['column']==0 for r in regions))
                check('explicit rule retains command origin',any(r['text']==r'\hrule' and r['kind']=='rule-origin' for r in regions))
                second=SOURCE.index('Zebra',SOURCE.index('Zebra')+1)+2
                line=SOURCE[:second].count('\n');column=second-SOURCE.rfind('\n',0,second)-1
                location=client.request(type='sync-forward',file='main.tex',line=line,column=column,page=0)['location']
                check('forward selects the second repeated word character',location and location['start']==second and location['end']==second+1)
                r=location['rect']
                backward=client.request(type='sync-backward',page=0,x=(r[0]+r[2])/2,y=(r[1]+r[3])/2)['location']
                check('reverse returns that same character',backward and backward['start']==second and backward['text']=='b')
                for name in ['x','y','a','b']:
                    pos=SOURCE.index('$x')+1 if name=='x' else SOURCE.index('+y')+1 if name=='y' else SOURCE.index('{a}')+1 if name=='a' else SOURCE.index('{b}')+1
                    check('math '+name+' origin',any(r['start']==pos and r['text']==name for r in regions))
                for name,pattern in [('c','cd'),('d','d+z'),('w','w_v'),('v','v$')]:
                    pos=SOURCE.index(pattern)
                    check('copied math field '+name+' origin',any(r['start']==pos and r['text']==name for r in regions))
                prefix=['wsl','-d','Ubuntu-22.04','--cd',linux(project),'--exec'] if os.name=='nt' else []
                for _ in range(2):
                    result=subprocess.run(prefix+['pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','main.tex'],cwd=project,stdout=subprocess.PIPE)
                    assert result.returncode==0,result.stdout.decode(errors='replace')[-2500:]
                with fitz.open(project/'main.pdf') as pdf:
                    check('stock pdfTeX page count',len(pdf)==frame['pageCount'])
                    for i,page in enumerate(pdf):
                        f=frame if i==0 else client.request(type='page',page=i)
                        check('stock pdfTeX identical pixels page '+str(i+1),pixels(f)==page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).samples)
                for label,changed,expect_resume in [
                    ('late edit',SOURCE.replace('Penguin','Penguins jump'),True),
                    ('earlier edit after late edit',SOURCE.replace('Zebra Quokka','ZQebra Quokka'),True),
                    ('preamble edit',SOURCE.replace('{article}','[12pt]{article}'),False),
                ]:
                    edited=client.request(type='edit',file='main.tex',source=changed,page=1)
                    check(label+' succeeds',edited.get('ok'),error=edited.get('error'))
                    check(label+' checkpoint decision',edited['retainedState']['restored']==expect_resume,state=edited['retainedState'],compileMs=edited['compileMs'])
                    (project/'main.tex').write_text(changed,encoding='utf-8')
                    for _ in range(2):
                        result=subprocess.run(prefix+['pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error','main.tex'],cwd=project,stdout=subprocess.PIPE)
                        assert result.returncode==0,result.stdout.decode(errors='replace')[-2500:]
                    with fitz.open(project/'main.pdf') as pdf:
                        check(label+' page count',len(pdf)==edited['pageCount'])
                        for i,page in enumerate(pdf):
                            f=edited if i==1 else client.request(type='page',page=i)
                            check(label+' identical pixels page '+str(i+1),pixels(f)==page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).samples)
    finally:
        (ROOT/'results'/args.output).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
