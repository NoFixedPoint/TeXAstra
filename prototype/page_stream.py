"""Persistent page renderer. Complete PDF is only the cold resource seed.

Live updates replace one drawing stream in MuPDF's retained document without
serializing or reopening a PDF. Unknown glyph/resources force a seed refresh.
"""
import base64
import re
import fitz
from .engine import render_page


class ResourceMiss(Exception):
    pass


class PageRenderer:
    def __init__(self):
        self.document=None
        self.coverage=set()

    def seed(self,data,coverage):
        self.close()
        self.document=fitz.open(stream=data,filetype='pdf')
        self.coverage=set(coverage)

    def update(self,buffer):
        if not set(buffer['coverage']).issubset(self.coverage):
            raise ResourceMiss('New font or glyph requires a resource refresh')
        page=buffer['page']
        if page>=len(self.document):raise ResourceMiss('New physical page requires a resource refresh')
        p=self.document[page]
        if abs(p.rect.width-buffer['width'])>.01 or abs(p.rect.height-buffer['height'])>.01:
            raise ResourceMiss('Changed page dimensions require a resource refresh')
        content=base64.b64decode(buffer['contentBase64'],validate=True)
        # Resource-bearing drawing operations need a complete dependency graph.
        # Never guess that a reused XObject/ExtGState number means the same data.
        if re.search(rb'/(?:[^\s/]+)\s+(?:Do|gs|sh|CS|cs)\b|\b(?:SCN|scn)\b',content):
            raise ResourceMiss('External graphics resource requires a refresh')
        required=set(re.findall(rb'/([^\s/]+)\s+[-+.\d]+\s+Tf\b',content))
        present={f[4].encode() for f in p.get_fonts()}
        if not required.issubset(present):raise ResourceMiss('Page font dictionary changed')
        streams=p.get_contents()
        if len(streams)!=1:raise ResourceMiss('Expected one page drawing stream')
        self.document.update_stream(streams[0],content,compress=False)
        self.document.reload_page(p)

    def render(self,directory,page,metadata,ids,page_count=None):
        return render_page(directory,page,metadata=metadata,glyph_ids=ids,
                           document=self.document,page_count=page_count)

    def close(self):
        if self.document is not None:self.document.close();self.document=None
