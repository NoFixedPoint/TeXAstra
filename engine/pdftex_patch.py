"""Checked instrumentation of Web2C's generated pdfTeX (pinned TL2021).

Keep WEB, memoryword, format files, font metrics and layout algorithms intact.
Only scanner/node metadata and PDF marked-content annotations are added.
"""
from pathlib import Path
import re, shutil

def apply(web, pristine):
    own=Path(__file__).resolve().parent
    s=(pristine/'pdftex0.c').read_text()
    def edit(old,new,count=1):
        nonlocal s
        assert s.count(old)==count,(old,s.count(old),count)
        s=s.replace(old,new)
    def function(name,fn):
        nonlocal s
        m=re.search(r'\n(?:z)?'+name+r' \(',s)
        assert m,name
        end=s.index('\n} ',m.start())+3
        old=s[m.start():end];new=fn(old)
        assert new!=old,('No instrumentation applied',name)
        s=s[:m.start()]+new+s[end:]
    edit('#define EXTERN extern','#define _GNU_SOURCE 1\n#define EXTERN extern')
    edit('#include "pdftexd.h"','#include "pdftexd.h"\n#include "texastra_pdftex.c"')
    function('getavail',lambda x:x.replace('  Result = p ;','  ta_store(p, ta_origin);\n  Result = p ;'))
    function('endfilereading',lambda x:x.replace('  endfilereading_regmem ',
        '  endfilereading_regmem \n  if(ta_state_enabled) ta_read_frontiers();'))
    function('readtoks',lambda x:x.replace('readtoks_regmem ',
        'readtoks_regmem \n  ta_read_register(n);'))
    function('getnode',lambda x:x.replace('  return Result ;','  ta_store(Result, ta_origin);\n  return Result ;'))
    edit('      k = curinput .locfield ;\n      curchr = readbuffer ( k ) ;',
         '      ta_scan_begin();\n      k = curinput .locfield ;\n      curchr = readbuffer ( k ) ;')
    function('getnext',lambda x:x.replace('  lab20: curcs = 0 ;','  lab20: ta_scanning = NULL; curcs = 0 ;').replace(
        '    t = mem [curinput .locfield ].hh .v.LH ;',
        '    ta_origin = ta_get(curinput.locfield);\n    if (ta_enabled && !ta_origin.id) ta_origin = ta_call[inputptr];\n    t = mem [curinput .locfield ].hh .v.LH ;').replace(
        '\n} ','\n  ta_scan_end();\n} '))
    function('begintokenlist',lambda x:x.replace('  curinput .statefield = 0 ;',
        '  ta_init(); if (ta_enabled) ta_call[inputptr] = ta_origin;\n  curinput .statefield = 0 ;'))
    function('macrocall',lambda x:x.replace('  halfword r', '  ta_span ta_invocation = ta_origin;\n  halfword r',1).replace(
        '  begintokenlist ( refcount , 5 ) ;',
        '  begintokenlist ( refcount , 5 ) ;\n  if (ta_enabled) ta_call[inputptr] = ta_invocation;'))
    # Inline allocations bypass getavail; every scanner token assignment must
    # replace the old provenance of a recycled memory cell.
    s,n=re.subn(r'(mem \[(\w+) \]\.hh \.v.LH = curtok ;)',r'{ \1 ta_store(\2, ta_origin); }',s)
    assert n>=8,n
    s,n=re.subn(r'(mem \[(\w+) \]\.hh \.v.LH = mem \[(\w+) \]\.hh \.v.LH ;)',r'{ \1 ta_store(\2, ta_get(\3)); }',s)
    assert n>=2,n
    # Math field and multiword node copies must carry their parallel metadata,
    # including cleanbox's temporary noads and script fields.
    def copy_word(m):
        if m[2].strip()=='memtop - 12':return m[0]
        return '{ '+m[1]+' ta_store('+m[2]+', ta_get('+m[3]+')); }'
    s,n=re.subn(r'(mem \[([^\[\]]+)\]= mem \[([^\[\]]+)\];)',copy_word,s)
    assert n>=15,n
    edit('  mem [ligstack ].hh.b0 = mainf ;','  ta_store(ligstack, ta_origin);\n  mem [ligstack ].hh.b0 = mainf ;',2)
    function('copynodelist',lambda x:x.replace('    mem [q ].hh .v.RH = r ;','    ta_store(r, ta_get(p));\n    mem [q ].hh .v.RH = r ;'))
    function('newligature',lambda x:x.replace('  Result = p ;','  ta_store(p, ta_ligature(q));\n  Result = p ;'))
    # Hyphenation rebuilds words after scanning has reached the paragraph end.
    # Seed each new character from its original letter, including ligature
    # components and the initial list used by boundary ligatures.
    def reconstitute_origins(x):
        for old,new in [
            ('\tmem [t ].hh .v.RH = getavail () ;',
             '\tta_origin = ta_get(p);\n\tmem [t ].hh .v.RH = getavail () ;'),
            ('    mem [t ].hh .v.RH = getavail () ;',
             '    ta_origin = ta_hyphen_origins[j];\n    mem [t ].hh .v.RH = getavail () ;'),
            ('\t\t    p = getavail () ;',
             '\t\t    ta_origin = ta_hyphen_origins[j + 1];\n\t\t    p = getavail () ;'),
            ('\t\t    mem [t ].hh .v.RH = getavail () ;',
             '\t\t    ta_origin = ta_hyphen_origins[j + 1];\n\t\t    mem [t ].hh .v.RH = getavail () ;'),
        ]:
            # Anchor indentation: the two appended-letter sites share a suffix.
            old='\n'+old;new='\n'+new
            assert x.count(old)==1,(old,x.count(old))
            x=x.replace(old,new)
        return x
    function('reconstitute',reconstitute_origins)
    def hyphenate_origins(x):
        assert x.count('return ;')==2
        return x.replace('hyphenate_regmem ',
            'hyphenate_regmem \n  ta_span ta_saved_origin = ta_origin;').replace(
            'return ;','{ ta_origin = ta_saved_origin; return ; }').replace(
            '\n} ','\n  ta_origin = ta_saved_origin;\n} ')
    function('hyphenate',hyphenate_origins)
    # The output routine synthesizes a character node for a ligature.
    edit('mem [memtop - 12 ]= mem [p + 1 ];','ta_store(memtop - 12, ta_get(p));\n\tmem [memtop - 12 ]= mem [p + 1 ];',4)
    # Do not reset pdfTeX's text matrix, TJ accumulator, or width rounding.
    # Close/reopen only the syntax of the current TJ array around one glyph.
    function('pdfhlistout',lambda x:x.replace('    do {\n\tf = mem [p ].hh.b0 ;',
        '    do {\n        ta_drawing = ta_get(p);\n\tf = mem [p ].hh.b0 ;'))
    function('pdfprintchar',lambda x:x.replace('  pdfprintchar_regmem ',
        '  pdfprintchar_regmem \n  ta_glyph_begin();').replace('\n} ','\n  ta_glyph_end();\n} '))
    function('newrule',lambda x:x.replace('  Result = p ;','  ta_store(p, (ta_span){0,0});\n  Result = p ;'))
    function('scanrulespec',lambda x:x.replace('  halfword q', '  ta_span ta_rule_origin=ta_origin;\n  halfword q',1).replace(
        '  Result = q ;','  ta_store(q, ta_rule_origin);\n  Result = q ;'))
    for name in ['pdfhlistout','pdfvlistout']:
        function(name,lambda x:x.replace('pdfsetrule ( curh , curv , rulewd , ruleht ) ;',
            'ta_drawing=ta_get(p);\n      pdfsetrule ( curh , curv , rulewd , ruleht ) ;'))
    function('pdfsetrule',lambda x:x.replace('  pdfendtext () ;','  pdfendtext () ;\n  ta_rule_begin();').replace(
        '\n} ','\n  if(ta_enabled) ta_pdf_raw("EMC\\n");\n} '))
    # Math fields carry origins independently of noad construction/scanning.
    function('scanmath',lambda x:x.replace('  mem [p ].hh .v.RH = 1 ;',
        '  ta_store(p, ta_origin);\n  mem [p ].hh .v.RH = 1 ;'))
    # Glyph-producing noad conversion happens long after source scanning.
    function('setmathchar',lambda x:x.replace('    mem [p + 1 ].hh .v.RH = 1 ;',
        '    ta_store(p + 1, ta_origin);\n    mem [p + 1 ].hh .v.RH = 1 ;'))
    function('fetch',lambda x:x.replace('  fetch_regmem ',
        '  fetch_regmem \n  ta_origin = ta_get(a);'))
    for name in ['pdftex_provenance.c','pdftex_state.c']:
        if (own/name).exists():shutil.copyfile(own/name,web/('texastra_pdftex.c' if name=='pdftex_provenance.c' else name))
    (web/'pdftex0.c').write_text(s)
    # Record letters before hyphenate frees their nodes. Ligatures contribute
    # the spans of their component list, not the whole ligature's merged span.
    s=(pristine/'pdftexini.c').read_text()
    edit('#include "pdftexd.h"',
         '#include "pdftexd.h"\nextern void ta_hyphen_letter(int, int);')
    edit('hu [hn ]= c ;','hu [hn ]= c ; ta_hyphen_letter(hn, s);')
    edit('hu [j ]= c ;','hu [j ]= c ; ta_hyphen_letter(j, q);')
    (web/'pdftexini.c').write_text(s)
