"""Check whether token attributes survive text, math, and TikZ rendering."""
from pathlib import Path
import subprocess
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.work'/'attribute-spike'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'probe.lua').write_text(r'''
local aid=luatexbase.new_attribute('bako_source')
tex.sprint('\\chardef\\bakoattr='..aid..' ')
local report={}
local function walk(head)
 for n in node.traverse(head) do
  if n.id==node.id('glyph') then
   local src=node.has_attribute(n,aid) or -1
   report[#report+1]=string.format('{"char":%d,"source":%d}',n.char,src)
   if src>0 then
    local a=node.new('whatsit','pdf_annot')
    a.width=n.width; a.height=n.height; a.depth=n.depth
    a.data='/Subtype /Link /Border [0 0 0] /A << /S /URI /URI (bako:'..src..') >>'
    head=node.insert_before(head,n,a)
   end
  elseif n.id==node.id('hlist') or n.id==node.id('vlist') then
   if n.head then n.head=walk(n.head) end
  end
 end
 return head
end
luatexbase.add_to_callback('pre_shipout_filter', function(box) walk(box); return true end,'bako.probe')
luatexbase.add_to_callback('stop_run',function()
 local f=assert(io.open('glyphs.json','w'));f:write('['..table.concat(report,',')..']');f:close()
end,'bako.report')
''',encoding='utf-8')
(OUT/'probe.tex').write_text(r'''\documentclass{article}
\usepackage{amsmath,tikz}
\directlua{dofile('probe.lua')}
\begin{document}
\attribute\bakoattr=1 h\attribute\bakoattr=2 e\attribute\bakoattr=3 l\attribute\bakoattr=4 l\attribute\bakoattr=5 o
$\attribute\bakoattr=10 x+\attribute\bakoattr=11 x+\frac{\attribute\bakoattr=12 a}{\attribute\bakoattr=13 b_{\attribute\bakoattr=14 2}}+\attribute\bakoattr=15 \alpha$
\begin{tikzpicture}\node[rotate=15] at (0,0) {\attribute\bakoattr=20 A\attribute\bakoattr=21 B $\attribute\bakoattr=22 x$};\end{tikzpicture}
\end{document}
''',encoding='utf-8')
p=subprocess.run(['lualatex','-interaction=nonstopmode','-halt-on-error','probe.tex'],cwd=OUT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
print(p.stdout[-4000:]); print('exit',p.returncode)
if (OUT/'glyphs.json').exists(): print((OUT/'glyphs.json').read_text())
