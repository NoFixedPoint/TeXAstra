"""Read-only user-project pdfTeX validation, including an unsaved title edit."""
import argparse, hashlib, json, shutil, tempfile
from pathlib import Path
import fitz
from cpp_client import Client, ROOT
from check_beamer import pixels
from check_citations import independent_pdf, disk_path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('project',type=Path);parser.add_argument('main')
    parser.add_argument('--edit-title');parser.add_argument('--page',type=int,default=0)
    parser.add_argument('--output',default='pdftex-project.json')
    parser.add_argument('--runtime',type=Path)
    args=parser.parse_args();report={'checks':[]}
    def manifest():return {p.relative_to(args.project).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in args.project.rglob('*') if p.is_file()}
    before=manifest()
    def check(name,ok,**details):
        row=dict(name=name,ok=bool(ok),**details);report['checks'].append(row);print(json.dumps(row),flush=True);assert ok,name
    try:
        with tempfile.TemporaryDirectory(prefix='pdftex-project-',dir=ROOT/'.work') as folder:
            reference=Path(folder);shutil.copytree(args.project,reference,dirs_exist_ok=True)
            with Client(args.project,runtime=args.runtime,main=args.main,compiler='pdflatex',preview_mode='full') as client:
                frame=client.request(type='start',page=args.page)
                check('initial compilation succeeds',frame.get('ok'),error=frame.get('error'),compileMs=frame.get('compileMs'))
                environment=json.loads(disk_path(frame['environmentReport']).read_text())
                def compare(label,frame):
                    with fitz.open(independent_pdf(reference,args.main,environment)) as pdf:
                        check(label+' page count',len(pdf)==frame['pageCount'],pages=len(pdf))
                        for i,page in enumerate(pdf):
                            f=frame if i==frame['page'] else client.request(type='page',page=i)
                            check(label+' exact PDFLaTeX pixels page '+str(i+1),pixels(f)==page.get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).samples)
                            if 'Literature' in ''.join(r[0] for r in f['characterRows']):
                                check(label+' Literature has token origins',bool(f['regionRows']))
                compare('initial',frame)
                if args.edit_title:
                    path=reference/args.main;source=path.read_text(encoding='utf-8')
                    assert args.edit_title in source
                    changed=source.replace(args.edit_title,args.edit_title+' (updated)',1)
                    edited=client.request(type='edit',file=args.main,source=changed,page=args.page)
                    check('retained edit succeeds',edited.get('ok'),error=edited.get('error'))
                    check('retained compiler state restored',edited['retainedState']['restored'],state=edited['retainedState'],compileMs=edited['compileMs'])
                    path.write_text(changed,encoding='utf-8');compare('edited',edited)
    finally:
        check('all original project files unchanged',manifest()==before,files=len(before))
        (ROOT/'results'/args.output).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
