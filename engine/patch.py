"""Apply checked provenance and safe-point hooks to the pinned engine tree."""
from pathlib import Path
import shutil,re

def apply(source):
    base=Path(source)/'texk/web2c/luatexdir'
    own=Path(__file__).resolve().parent
    for name in ['origins.h','origins.c','resources.c']:
        if not (base/name).exists() or (base/name).read_bytes()!=(own/name).read_bytes():shutil.copyfile(own/name,base/name)
    def edit(name,old,new,count=1):
        p=base/name;s=p.read_text()
        if new in s:return
        assert s.count(old)==count,(name,old,s.count(old))
        p.write_text(s.replace(old,new))
    edit('tex/textoken.h','#  include "tex/stringpool.h"','#  include "tex/stringpool.h"\n#  include "origins.h"')
    edit('tex/textoken.h','incr(dyn_used); } \\','incr(dyn_used); } bako_token_store(A); \\')
    edit('tex/textoken.c','    token_link(p) = null;\n    /*tex Maintain statistics. */','    token_link(p) = null;\n    bako_token_store(p);\n    /*tex Maintain statistics. */')
    edit('tex/inputstack.h','    int synctex_tag_field;','    int bako_origin_field;\n    int synctex_tag_field;')
    edit('tex/inputstack.c','    istate = token_list;\n    istart = p;\n    token_type = (unsigned char) t;','    istate = token_list;\n    cur_input.bako_origin_field = bako_origin;\n    istart = p;\n    token_type = (unsigned char) t;')
    edit('tex/textoken.c','        /*tex current line not yet finished */\n        do_buffer_to_unichar(cur_chr, iloc);','        /*tex current line not yet finished */\n        bako_scan_begin();\n        do_buffer_to_unichar(cur_chr, iloc);',2)
    edit('tex/textoken.c','    register halfword t = token_info(iloc);','    bako_origin = token_type == macro ? cur_input.bako_origin_field : bako_token_origin(iloc);\n    register halfword t = token_info(iloc);')
    edit('tex/textoken.c','        if (!get_next_file())\n            goto RESTART;','        if (!get_next_file())\n            goto RESTART;\n        bako_scan_end();')
    edit('tex/texfileio.c','    full_source_filename_stack[in_open] = xstrdup(fullnameoffile);','    full_source_filename_stack[in_open] = xstrdup(fullnameoffile);\n    bako_source_open(fullnameoffile);')
    edit('tex/expand.c','void macro_call(void)\n{','void macro_call(void)\n{\n    int bako_call_origin = bako_origin;')
    edit('tex/expand.c','    begin_token_list(ref_count, macro);','    begin_token_list(ref_count, macro);\n    cur_input.bako_origin_field = bako_call_origin;')
    edit('tex/expand.c','    halfword t;\n    /*tex for list manipulation */','    halfword t;\n    int bako_saved_origin;\n    /*tex for list manipulation */')
    edit('tex/expand.c','                    t = cur_tok;\n                    get_token();','                    t = cur_tok;\n                    bako_saved_origin = bako_origin;\n                    get_token();')
    edit('tex/expand.c','                    cur_tok = t;\n                    back_input();','                    cur_tok = t;\n                    bako_origin = bako_saved_origin;\n                    back_input();')
    edit('tex/equivalents.h','typedef struct save_record_ {','typedef struct save_record_ {\n    int bako_origin_field;')
    edit('tex/equivalents.c','        save_value(save_ptr) = t;','        save_value(save_ptr) = t;\n        save_stack[save_ptr].bako_origin_field = bako_origin;')
    edit('tex/equivalents.c','                reinsert_token(a, p);','                int bako_saved_origin = bako_origin;\n                bako_origin = save_stack[save_ptr].bako_origin_field;\n                reinsert_token(a, p);\n                bako_origin = bako_saved_origin;')
    edit('tex/maincontrol.c','    after_token = cur_tok;','    after_token = cur_tok;\n    bako_after_origin = bako_origin;')
    # Only the outer interpreter, between completed commands. Never interrupt
    # argument scanning, an output routine, a box, or recursive local control.
    edit('tex/maincontrol.c',
         '            get_x_token();\n        }\n        /*tex\n            Give diagnostic information',
         '            if (bako_boundary_hook && mode == vmode && !output_active &&\n'
         '                scanner_status == normal && local_level == 0) bako_boundary_hook();\n'
         '            get_x_token();\n        }\n        /*tex\n            Give diagnostic information')
    edit('tex/maincontrol.c','        cur_tok = after_token;','        cur_tok = after_token;\n        bako_origin = bako_after_origin;')
    edit('tex/maincontrol.c','void prefixed_command(void)\n{','void prefixed_command(void)\n{\n    int bako_future_origin = 0;')
    edit('tex/maincontrol.c','                    q = cur_tok;\n                    get_token();','                    q = cur_tok;\n                    bako_future_origin = bako_origin;\n                    get_token();')
    edit('tex/maincontrol.c','                    cur_tok = q;\n                    /*tex','                    cur_tok = q;\n                    bako_origin = bako_future_origin;\n                    /*tex')
    # Preserve origins when the engine copies token list cells directly.
    for p in base.rglob('*.c'):
        s=p.read_text();old=s
        s=re.sub(r'(?m)^(\s*)token_info\((\w+)\) = token_info\((\w+)\);(?! /\* bako \*/)',r'\1token_info(\2) = token_info(\3); /* bako */\1bako_origin_copy(\2, \3);',s)
        s=re.sub(r'((?:fast_)?store_new_token\(token_info\((\w+)\)\);)(?! /\* bako \*/)',r'\1 /* bako */ bako_origin_copy(p, \2);',s)
        if s!=old:p.write_text(s)
    edit('tex/texnodes.c','    subtype(n) = (quarterword) j;\n    return n;','    subtype(n) = (quarterword) j;\n    if (nodetype_has_attributes(i) && bako_attribute >= 0 && bako_origin > 0) set_attribute(n,bako_attribute,bako_origin);\n    return n;')
    edit('tex/texnodes.c','    build_attribute_list(n);\n    /*tex No need','    build_attribute_list(n);\n    if (bako_attribute >= 0 && bako_origin > 0) set_attribute(n,bako_attribute,bako_origin);\n    /*tex No need')
    edit('tex/texmath.c','    type(p) = math_char_node;\n    math_character(p) = mval.character_value;','    type(p) = math_char_node;\n    if (bako_attribute >= 0 && bako_origin > 0) set_attribute(p,bako_attribute,bako_origin);\n    math_character(p) = mval.character_value;')
    p=base/'tex/textoken.c';s=p.read_text()
    if '#include "origins.c"' not in s:p.write_text(s+'\n#include "origins.c"\n')
    p=base/'pdf/pdfgen.c';s=p.read_text()
    if '#include "../resources.c"' not in s:p.write_text(s+'\n#include "../resources.c"\n')

if __name__=='__main__':
    import sys
    apply(sys.argv[1])
