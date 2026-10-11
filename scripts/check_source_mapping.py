"""Differential navigation regressions, including localized provenance faults."""
import base64
import json
from pathlib import Path

import fitz
from cpp_client import Client, ROOT

report = {'checks': []}


def check(name, ok):
    report['checks'].append({'name': name, 'ok': bool(ok)})
    print(name, bool(ok), flush=True)
    assert ok, name


def require(frame):
    assert frame.get('ok'), frame.get('error')
    return frame


def pixels(frame):
    return fitz.Pixmap(base64.b64decode(frame['image'].split(',', 1)[1])).samples


def rows(frame):
    return [dict(zip(frame['regionFields'], row)) for row in frame['regionRows']]


project = ROOT/'.work/source-mapping'
project.mkdir(parents=True, exist_ok=True)
root = (r'\documentclass{article}' '\n' r'\usepackage{amsmath,graphicx,tikz}' '\n'
        r'\begin{document}' '\n' r'\input{chapter}' '\n' r'\end{document}' '\n')
prefix = 'First page.\n\\newpage\nSecond page.\n\\newpage\n'
suffix = '\n\nAfterguard.\n\\newpage\nFourth page.\n\\newpage\nLast page.\n'
original = prefix+'Beforeguard. Baseline.\n'+suffix
(project/'paper.tex').write_text(root, encoding='utf-8')
(project/'chapter.tex').write_text(original, encoding='utf-8')
with fitz.open() as pdf:
    page = pdf.new_page(width=160, height=30)
    page.insert_text((5, 18), 'Imported figure text')
    pdf.save(project/'figure.pdf')

# Runs after production pre_shipout_filter. A single corrupted output marker
# simulates unsupported node manipulation without damaging TeX's visible output.
(project/'fault.lua').write_text('''
local function visit(head)
  for n in node.traverse(head) do
    if n.id==node.id('whatsit') and n.subtype==node.subtype('pdf_literal') and
       n.data and remove_end and n.data=='EMC' then n.data='';remove_end=false
    elseif n.id==node.id('whatsit') and n.subtype==node.subtype('pdf_literal') and
       n.data and n.data:find('/BakoSource',1,true) and not injected then
      local id=tonumber(n.data:match('/ID (%d+)'))
      if id and id>0 then
        if mapping_fault=='count' then n.data=n.data:gsub('/N 1','/N 2')
        elseif mapping_fault=='unknown' then n.data=n.data:gsub('/ID %d+','/ID 2146000999')
        elseif mapping_fault=='missing' then n.data=n.data:gsub('/ID %d+','/ID 0')
        elseif mapping_fault=='untagged' then n.data='';remove_end=true end
        injected=true
      end
    elseif (n.id==node.id('hlist') or n.id==node.id('vlist')) and n.head then visit(n.head) end
  end
end
luatexbase.add_to_callback('pre_shipout_filter',function(box)
  if mapping_fault then injected=false;visit(box) end
  return true
end,'test.mapping_fault')
''', encoding='utf-8')

frames = {}
try:
    with Client(project, main='paper.tex') as live, Client(project, main='paper.tex', preview_mode='full') as plain:
        initial = require(live.request(type='start', page=2))
        require(plain.request(type='start', page=2))

        def run(name, body, targets=(), rules=(), fault=None):
            changed = prefix+'Beforeguard.\n'+body+suffix
            a = require(live.request(type='edit', file='chapter.tex', source=changed, page=2))
            b = require(plain.request(type='edit', file='chapter.tex', source=changed, page=2))
            check(name+' exact pixels', pixels(a) == pixels(b))
            check(name+' exact selectable text', a['characterRows'] == b['characterRows'])
            mapped = rows(a)
            check(name+' correct source slices', bool(mapped) and all(
                changed[r['start']:r['end']] == r['text'] for r in mapped if r['file'] == 'chapter.tex'))
            check(name+' suffix remains navigable', any(r['start'] == changed.index('Afterguard.') for r in mapped))
            for token in targets:
                offset = changed.rindex(token, 0, changed.index('Afterguard.'))
                matches = [r for r in mapped if r['start'] == offset and r['text'] == token]
                check(name+' token '+token, bool(matches))
                line, column = changed[:offset].count('\n'), offset-changed.rfind('\n', 0, offset)-1
                found = require(live.request(type='sync-forward', file='chapter.tex', line=line, column=column, page=2))['location']
                check(name+' forward '+token, found and found['page'] == 2 and found['start'] == offset)
            for token in rules:
                candidates = [r for r in mapped if r['kind'] == 'rule-origin' and r['text'] == token]
                check(name+' rule '+token, bool(candidates) and all(r['rect'][2] > r['rect'][0] and r['rect'][3] > r['rect'][1] for r in candidates))
            if not fault:
                check(name+' no mapping warnings', not a['warnings'])
            frames[name] = a
            return a, changed

        run('nested reordered macros', r'\def\inner#1#2{#2+#1}\def\outer#1#2{\textbf{\inner{#1}{#2}}}\outer{J}{Q}', ['J', 'Q'])
        ligatures, text = run('ligatures', r'office affinity ffi fl. \textbf{efficient}', ['o', 'e'])
        check('ffi ligature keeps its leading token', any(r['start'] == text.index('office')+1 and r['text'] == 'f' for r in rows(ligatures)))
        virtual, text = run('virtual font ligatures', r'\font\virtual=pplr7t at 10pt {\virtual office ffi}', ['o'])
        start = text.index('office')+1
        check('virtual ligature maps multiple physical glyphs to one token', sum(r['start'] == start for r in rows(virtual)) > 1)
        run('discretionary hyphen', r'\parbox{25pt}{hy\-phen\-ation}', [r'\-', 'h'])
        hyphens, _ = run('automatic hyphenation', r'\parbox{40pt}{extraordinary internationalization representation}', ['e'])
        check('automatic hyphenation fixture actually breaks words', any(ch[0] == '-' for ch in hyphens['characterRows']))
        run('complex math', r'$\frac{J_2}{\frac{Q^3}{x}}+\sqrt{z}+\overline{y}+\underline{w}$',
            ['J', 'Q', r'\frac', r'\overline', r'\underline'], [r'\frac', r'\sqrt', r'\overline', r'\underline'])
        run('generated fraction', r'\def\fraction{\frac{J}{Q}}$\fraction$', [r'\fraction'], [r'\fraction'])
        run('transformed text and rules', r'\rotatebox{25}{\scalebox{1.3}{$\frac{J}{Q}$}} '
            r'\begin{tikzpicture}\node[rotate=35,text=red]{office};\end{tikzpicture}', ['J', 'Q'], [r'\frac'])
        imported, _ = run('imported PDF', r'\includegraphics{figure.pdf} Caption J.', ['J'])
        check('imported PDF diagnoses its own glyphs', any(r['reason'] == 'external-content' for r in imported['unmappedRegions']))
        lua, _ = run('Lua glyph without origin', r"J \directlua{local g=node.new('glyph');g.font=font.current();g.char=90;"
                     r"local aid=luatexbase.attributes.bako_source;if aid then node.set_attribute(g,aid,0) end;node.write(g)} Q.", ['J', 'Q'])
        visible = [box for ch, box in lua['characterRows'] if ch == 'Z']
        check('Lua glyph explains missing origin at its position', any(
            r['reason'] == 'missing-origin' and abs(r['rect'][0]-box[0]) < .02
            for r in lua['unmappedRegions'] for box in visible))

        for fault, reason in [('count', 'glyph-count-mismatch'), ('unknown', 'unknown-source'),
                              ('missing', 'missing-origin'), ('untagged', 'untagged-content')]:
            a, changed = run('localized '+fault, r"\directlua{mapping_fault='"+fault+r"';dofile('fault.lua')} J Q.", ['J', 'Q'], fault=fault)
            check(fault+' diagnostic', any(r['reason'] == reason for r in a['unmappedRegions']))
            # The first glyph of page three is deliberately corrupted; all
            # following glyphs retain their independent source alignment.
            check(fault+' corrupted glyph excluded', not any(r['start'] == changed.index('Beforeguard.') for r in rows(a)))
            check(fault+' neighboring glyph preserved', any(r['start'] == changed.index('Beforeguard.')+1 for r in rows(a)))
            if fault in ('count', 'unknown'):
                check(fault+' warning is local', any(w.get('code') == reason for w in a['warnings']))

        # Returning to clean state exercises earlier fork rollback: callback
        # registrations and corrupt markers from the edited suffix must vanish.
        a, changed = run('rollback after faulty markers', r'$\frac{J}{Q}$ Clean again.', ['J', 'Q', r'\frac'], [r'\frac'])
        check('rollback reused checkpoint', a.get('resumedFrom', 0) > 1)
        check('rollback clears fault diagnostics', not any(r['reason'] in ('glyph-count-mismatch', 'unknown-source') for r in a['unmappedRegions']))
        earlier = changed.replace('First page.', 'Earlier changed page.')
        a = require(live.request(type='edit', file='chapter.tex', source=earlier, page=2))
        b = require(plain.request(type='edit', file='chapter.tex', source=earlier, page=2))
        check('earlier rollback exact pixels and rules', pixels(a) == pixels(b) and any(r['kind'] == 'rule-origin' for r in rows(a)))
        check('earlier rollback offsets refreshed', all(earlier[r['start']:r['end']] == r['text'] for r in rows(a) if r['file'] == 'chapter.tex'))
        for number in (0, 1, 3, 4, 2):
            a = require(live.request(type='page', page=number)); b = require(plain.request(type='page', page=number))
            check(f'page {number+1} navigation after rollback', pixels(a) == pixels(b) and bool(a['regionRows']) and not a['warnings'])

    check('project sources untouched', (project/'chapter.tex').read_text(encoding='utf-8') == original and
          (project/'paper.tex').read_text(encoding='utf-8') == root)
finally:
    (ROOT/'results/source-mapping.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (project/'frames.json').write_text(json.dumps(frames), encoding='utf-8')
