"""End-to-end token provenance, independent of the retired source rewriter."""
import argparse,base64,json
from pathlib import Path
import fitz
from cpp_client import Client,ROOT
parser=argparse.ArgumentParser()
parser.add_argument('--runtime',type=Path,default=ROOT/'native/runtime')
parser.add_argument('--case')
args=parser.parse_args()
cases={
 'reordered arguments': (r'\def\swap#1#2{#2+#1}\swap{J}{Q}', [('J','J'),('Q','Q')]),
 'delimited argument': (r'\def\take#1!{#1}\take Q!', [('Q','Q')]),
 'nested arguments': (r'\def\outer#1{\textbf{#1}}\outer{Q}', [('Q','Q')]),
 'generated macro': (r'\def\generated{Q}\generated', [('Q',r'\generated')]),
 'math arguments': (r'$\frac{J_2}{Q^3}+\alpha$', [('J','J'),('Q','Q'),('2','2'),('3','3'),('α',r'\alpha')]),
 'unbraced math': (r'$\frac JQ$', [('J','J'),('Q','Q')]),
 'active character': (r'\catcode`\~=13 \def~{Q}~', [('Q','~')]),
 'changed letter catcode': (r'\catcode`\@=11 \def\my@word{Q}\my@word', [('Q',r'\my@word')]),
 'expanded definition': (r'\def\identity#1{#1}\edef\saved{\identity{Q}}\saved', [('Q',r'\saved')]),
 'expandafter argument': (r'\def\identity#1{#1}\expandafter\identity\expandafter{Q}', [('Q','Q')]),
 'conditional argument': (r'\def\choose#1{\ifnum1<2 #1\else J\fi}\choose{Q}', [('Q','Q')]),
 'verbatim': (r'\verb|J_Q|', [('J','J'),('Q','Q')]),
 'token register': (r'\toks0={Q}\the\toks0', [('Q','Q')]),
 'control sequence alias': (r'\def\original{Q}\let\alias\original \alias', [('Q',r'\alias')]),
 'after group': (r'{\aftergroup Q}', [('Q','Q')]),
 'after assignment': (r'\afterassignment Q\count0=1\relax', [('Q','Q')]),
 'future let': (r'\futurelet\next JQ', [('J','J'),('Q','Q')]),
 'stored argument': (r'\def\save#1{\def\saved{#1}}\save{Q}\saved', [('Q','Q')]),
 'stored mixed body': (r'\def\save#1{\def\saved{J#1}}\save{Q}\saved', [('J',r'\saved'),('Q','Q')]),
 'stored expanded argument': (r'\def\save#1{\edef\saved{#1}}\save{Q}\saved', [('Q','Q')]),
}
checks=[]
def check(name,ok):
 checks.append({'name':name,'ok':bool(ok)});print(checks[-1],flush=True);assert ok,name
def require(frame):
 if not frame.get('ok'):raise RuntimeError(frame.get('error'))
 return frame
def pixels(frame):return fitz.Pixmap(base64.b64decode(frame['image'].split(',',1)[1])).samples
try:
 for name,(body,targets) in cases.items():
  if args.case and args.case!=name:continue
  project=ROOT/'.work/token-origins'/name.replace(' ','-');project.mkdir(parents=True,exist_ok=True)
  source='\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n'+body+'\n\nAfter.\n\\end{document}\n'
  (project/'main.tex').write_text(source,encoding='utf-8')
  with Client(project,args.runtime) as live,Client(project,args.runtime,preview_mode='full') as plain:
   actual=require(live.request(type='start',page=0));expected=require(plain.request(type='start',page=0))
   check(name+' exact pixels',pixels(actual)==pixels(expected))
   rows=[dict(zip(actual['regionFields'],row)) for row in actual['regionRows']]
   for glyph,token in targets:
    offset=source.rindex(token,0,source.index('\n\nAfter.'))
    visible=[r[1] for r in actual['characterRows'] if r[0]==glyph]
    mapped=[r for r in rows if r['start']==offset and r['text']==token]
    check(name+' token '+glyph, bool(mapped) and any(abs(r['rect'][0]-box[0])<0.02 and min(r['rect'][3],box[3])>max(r['rect'][1],box[1]) for r in mapped for box in visible))
   check(name+' source ranges',all(source[r['start']:r['end']]==r['text'] for r in rows))
   changed=source.replace('After.','Afterward.')
   a=require(live.request(type='edit',file='main.tex',source=changed,page=0))
   b=require(plain.request(type='edit',file='main.tex',source=changed,page=0))
   check(name+' edit pixels',pixels(a)==pixels(b))
 # A computed input name is handled by TeX, without a literal-input regex.
 project=ROOT/'.work/token-origins/computed-input';project.mkdir(parents=True,exist_ok=True)
 source='\\documentclass{article}\n\\def\\filename{chapter}\n\\begin{document}\n\\input{\\filename}\n\nAfter.\n\\end{document}\n'
 (project/'main.tex').write_text(source,encoding='utf-8')
 (project/'chapter.tex').write_text('Q.\n',encoding='utf-8')
 with Client(project,args.runtime) as live,Client(project,args.runtime,preview_mode='full') as plain:
  a=require(live.request(type='start',page=0));b=require(plain.request(type='start',page=0))
  check('computed input exact pixels',pixels(a)==pixels(b))
  rows=[dict(zip(a['regionFields'],r)) for r in a['regionRows']]
  check('computed input token origin',any(r['file']=='chapter.tex' and r['start']==0 and r['text']=='Q' for r in rows))
  changed=source.replace('After.','Afterward.\n\nJ.')
  a=require(live.request(type='edit',file='main.tex',source=changed,page=0))
  b=require(plain.request(type='edit',file='main.tex',source=changed,page=0))
  check('new paragraph exact pixels',pixels(a)==pixels(b))
  rows=[dict(zip(a['regionFields'],r)) for r in a['regionRows']]
  check('new paragraph token origin',any(r['file']=='main.tex' and r['start']==changed.index('J.') and r['text']=='J' for r in rows))
finally:
 (ROOT/'results/token-origins.json').write_text(json.dumps({'checks':checks},indent=2)+'\n')
