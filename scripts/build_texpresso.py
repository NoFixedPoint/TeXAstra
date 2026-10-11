"""Build a pinned independent TeXpresso checkout under WSL; leave existing installs alone."""
from pathlib import Path
import subprocess
import re

BASE='/home/wenlan/.cache/bakoma-revived/texpresso'
UNC=Path(r'\\wsl.localhost\Ubuntu-22.04\home\wenlan\.cache\bakoma-revived\texpresso')
for path in (UNC/'src').rglob('*.c'):
    source=path.read_text()
    source=source.replace('#include <mupdf/fitz/buffer.h>','#include <mupdf/fitz.h>')
    if any(s in source for s in ['fz_malloc_struct_array','fz_irect_width','fz_irect_height']) and '#include "fz_util.h"' not in source:
        index=source.index('#include ')
        source=source[:index]+'#include "fz_util.h"\n'+source[index:]
    if '#include "fz_util.h"' in source:
        source=source.replace('#include "fz_util.h"','#include <mupdf/fitz.h>\n#include "fz_util.h"')
    source=re.sub(r'(#include <mupdf/fitz.h>\n)+', '#include <mupdf/fitz.h>\n',source)
    path.write_text(source)
main=UNC/'src/frontend/main.c'
source=main.read_text()
if 'BAKO_FRAME' not in source:
    source=source.replace('static void render(fz_context *ctx, ui_state *ui)', 'static int bako_word = -1;\nstatic void render(fz_context *ctx, ui_state *ui)')
    source=source.replace('SDL_RenderPresent(ui->sdl_renderer);','SDL_RenderPresent(ui->sdl_renderer);\n  if(getenv("BAKO_TRACE")){fprintf(stderr,"BAKO_FRAME %d %u %d\\n",ui->page,SDL_GetTicks(),bako_word);fflush(stderr);}')
    source=source.replace('txp_renderer_set_contents(ps->ctx, ui->doc_renderer, dl);',r'''
  txp_renderer_set_contents(ps->ctx, ui->doc_renderer, dl);
  if(getenv("BAKO_TRACE") && dl){
    fz_stext_page *text=fz_new_stext_page_from_display_list(ps->ctx,dl,NULL);
    fz_buffer *buffer=fz_new_buffer_from_stext_page(ps->ctx,text);
    unsigned char *data=NULL;size_t size=fz_buffer_storage(ps->ctx,buffer,&data);
    bako_word=-1;
    for(size_t i=0;i+5<=size;i++){
      if(!memcmp(data+i,"alpha",5))bako_word=0;
      if(!memcmp(data+i,"omega",5))bako_word=1;
    }
    fz_drop_buffer(ps->ctx,buffer);fz_drop_stext_page(ps->ctx,text);
  }
''')
    main.write_text(source)
source=main.read_text()
if 'BAKO_PIXELS' not in source:
    source=source.replace('SDL_RenderPresent(ui->sdl_renderer);',r'''
  unsigned int bako_hash=2166136261u; /* BAKO_PIXELS */
  if(getenv("BAKO_TRACE")){
    int w,h;SDL_GetRendererOutputSize(ui->sdl_renderer,&w,&h);
    SDL_Surface *capture=SDL_CreateRGBSurfaceWithFormat(0,w,h,32,SDL_PIXELFORMAT_RGBA32);
    if(capture){
      SDL_RenderReadPixels(ui->sdl_renderer,NULL,SDL_PIXELFORMAT_RGBA32,capture->pixels,capture->pitch);
      unsigned char *pixels=capture->pixels;
      for(int i=0;i<capture->pitch*h;i++)bako_hash=(bako_hash^pixels[i])*16777619u;
      if(getenv("BAKO_CAPTURE"))SDL_SaveBMP(capture,getenv("BAKO_CAPTURE"));
      SDL_FreeSurface(capture);
    }
  }
  SDL_RenderPresent(ui->sdl_renderer);
''')
    source=source.replace('"BAKO_FRAME %d %u %d\\n",ui->page,SDL_GetTicks(),bako_word','"BAKO_FRAME %d %u %d %u\\n",ui->page,SDL_GetTicks(),bako_word,bako_hash')
    main.write_text(source)
p=subprocess.run(['wsl','-d','Ubuntu-22.04','--','bash','-lc',f'cd {BASE} && make -j4 all > build-session.log 2>&1'])
print('build exit',p.returncode)
if p.returncode:
    lines=(UNC/'build-session.log').read_text().splitlines()
    print('\n'.join(line for line in lines if 'error:' in line or 'undefined reference' in line or 'Error' in line)[-6000:])
