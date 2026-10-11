-- Instrument final glyphs after TeX has performed shaping and math layout.
-- Source identifiers come from the explicitly limited source instrumenter.
local aid=luatexbase.new_attribute('bako_source')
tex.sprint('\\attributedef\\bakoattr='..aid..' ')
local glyph, hlist, vlist = node.id('glyph'), node.id('hlist'), node.id('vlist')
local page_number=0
local geometry=nil
local records={}
local mode=os.getenv('BAKO_GEOMETRY') or 'sidecar'
function bako_record(source,width,height,depth)
  if mode=='sidecar' then geometry:write(source,'\n');return end
  local x,y=pdf.getpos()
  local a,b,c,d,e,f=pdf.getmatrix()
  geometry:write(string.format('{"id":%d,"x":%d,"y":%d,"w":%d,"h":%d,"d":%d,"matrix":[%.10g,%.10g,%.10g,%.10g,%.10g,%.10g]}\n',source,x,y,width,height,depth,a,b,c,d,e,f))
end
local function annotate(head)
  for n in node.traverse(head) do
    if n.id == glyph then
      local source=node.has_attribute(n,aid) or 0
      if mode=='sidecar' then
        local late=node.new('whatsit','late_lua')
        -- Execute a closure at actual shipout; avoid parsing Lua source and
        -- invoking buffered file IO separately for every glyph.
        local font_id,char=n.font,n.char
        late.data=function()
          records[#records+1]=source
          if bako_stream_glyph then bako_stream_glyph(font_id,char) end
        end
        head=node.insert_before(head,n,late)
      end
      if mode=='tagged' then
        local first=node.new('whatsit','pdf_literal');first.mode=2
        first.data='/Bako << /MCID '..source..' >> BDC'
        local last=node.new('whatsit','pdf_literal');last.mode=2;last.data='EMC'
        head=node.insert_before(head,n,first);head=node.insert_after(head,n,last)
      end
      if source and source>0 then
        if mode=='both' then
        local late=node.new('whatsit','late_lua')
        late.data=string.format('bako_record(%d,%d,%d,%d)',source,n.width,n.height,n.depth)
        head=node.insert_before(head,n,late)
        local a=node.new('whatsit','pdf_annot')
        a.width=n.width; a.height=n.height; a.depth=n.depth
        a.data='/Subtype /Link /Border [0 0 0] /A << /S /URI /URI (bako:'..source..') >>'
        head=node.insert_before(head,n,a)
        end
      end
    elseif (n.id == hlist or n.id == vlist) and n.head then
      n.head=annotate(n.head)
    elseif n.id==node.id('disc') then
      if n.pre then n.pre=annotate(n.pre) end
      if n.post then n.post=annotate(n.post) end
      if n.replace then n.replace=annotate(n.replace) end
    end
  end
  return head
end
luatexbase.add_to_callback('pre_shipout_filter',function(box)
  page_number=page_number+1
  if mode~='tagged' then geometry=assert(io.open(string.format('geometry-%03d.jsonl',page_number),'w'));records={} end
  annotate(box)
  return true
end,'bako.provenance')
luatexbase.add_to_callback('finish_pdfpage',function()
  if geometry then
    if mode=='sidecar' and #records>0 then geometry:write(table.concat(records,'\n'),'\n') end
    geometry:close();geometry=nil
  end
end,'bako.geometry')
