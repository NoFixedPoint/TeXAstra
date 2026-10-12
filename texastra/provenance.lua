-- Instrument final glyphs after TeX has performed shaping and math layout.
-- Production identifiers come from LuaHBTeX's token scanner and expansion.
local aid=luatexbase.new_attribute('bako_source')
local origins=nil
function bako_reload_sources()
  if not origins then return end
  local manifest=assert(io.open('bako-sources.tsv','r'))
  for row in manifest:lines() do
    local slot,path=row:match('^(%d+)\t(.+)$')
    assert(slot and path,'Invalid source manifest')
    origins.source_register(path,tonumber(slot))
  end
  manifest:close()
end
local manifest=io.open('bako-sources.tsv','r')
if manifest then
  manifest:close()
  local native=os.getenv('BAKO_ENGINE_MODULE')
  origins=assert(package.loadlib(native or './bako_snapshot.so',native and 'luaopen_bako_native' or 'luaopen_bako_snapshot'))()
  origins.source_enable(aid)
  bako_reload_sources()
end
tex.sprint('\\attributedef\\bakoattr='..aid..' ')
-- A brace-delimited setter does not consume source whitespace following it.
tex.sprint('\\protected\\def\\bakoSet#1{\\bakoattr=#1\\relax}')
local source_stack={}
function bako_push_source() source_stack[#source_stack+1]=tex.getattribute(aid) end
function bako_pop_source()
  tex.setattribute(aid,table.remove(source_stack))
end
local glyph, hlist, vlist = node.id('glyph'), node.id('hlist'), node.id('vlist')
local page_number=0
local geometry=nil
local records={}
local rule_records={}
local mode=os.getenv('BAKO_GEOMETRY') or 'sidecar'
local source_markers=os.getenv('BAKO_SOURCE_MARKERS')=='1'
-- TeX virtual characters can draw several physical glyphs (for example a
-- Palatino ffi made from f + fi). Missing characters draw none. The renderer
-- trace follows those physical draws, not the number of TeX glyph nodes.
local font_counts, virtual_fonts = {}, {}
local function virtual_font(name,size)
  local key=name..':'..tostring(size)
  if virtual_fonts[key]==nil then virtual_fonts[key]=font.read_vf(name,size) or false end
  return virtual_fonts[key]
end
local function physical_count(f,char,depth)
  if not f or depth>16 then return 1 end
  local character=f.characters[char]
  if not character then return 0 end
  if not character.commands and f.type=='unknown' then
    local vf=virtual_font(f.name,f.size)
    if vf then return physical_count(vf,char,depth+1) end
  end
  if not character.commands then return 1 end
  local selected,count=1,0
  for _,command in ipairs(character.commands) do
    local op=command[1]
    if op=='font' or op=='slot' then selected=command[2] end
    if op=='char' or op=='slot' then
      local sub=f.fonts and f.fonts[selected]
      local child=sub and (sub.id and font.getfont(sub.id) or virtual_font(sub.name,sub.size))
      count=count+(child and physical_count(child,command[op=='slot' and 3 or 2],depth+1) or 1)
    end
  end
  return count
end
local function glyph_count(id,char)
  local counts=font_counts[id]
  if not counts then counts={};font_counts[id]=counts end
  if counts[char]==nil then counts[char]=physical_count(font.getfont(id),char,0) end
  return counts[char]
end
local function mark(head,n,source,kind,count)
  -- Private engine mode preserves both Tm and cumulative TJ rounding.
  local first=node.new('whatsit','pdf_literal');first.mode=6
  first.data=string.format('/BakoSource << /V 1 /ID %d /N %d /Kind /%s >> BDC',source,count,kind)
  local last=node.new('whatsit','pdf_literal');last.mode=6;last.data='EMC'
  head=node.insert_before(head,n,first);head=node.insert_after(head,n,last)
  return head
end
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
      if source<0 then source=0 end
      if source_markers then head=mark(head,n,source,'Glyph',glyph_count(n.font,n.char)) end
      if mode=='sidecar' then
        local late=node.new('whatsit','late_lua')
        -- Execute a closure at actual shipout; avoid parsing Lua source and
        -- invoking buffered file IO separately for every glyph.
        local font_id,char=n.font,n.char
        late.data=function()
          for _=1,glyph_count(font_id,char) do records[#records+1]=source end
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
    elseif source_markers and n.id==node.id('rule') and n.subtype~=1 and n.subtype~=2 then
      -- Image/form rules have no TeX expression provenance. Ordinary rules,
      -- including math fraction/overbar rules, inherit the engine attribute.
      local source=node.has_attribute(n,aid) or 0
      if source>0 then
        head=mark(head,n,source,'Rule',0)
        rule_records[#rule_records+1]=source
      end
    elseif (n.id == hlist or n.id == vlist) and n.head then
      n.head=annotate(n.head)
    elseif n.id==node.id('glue') and n.leader then
      -- Leaders (for example contents-page dots) ship the same box repeatedly.
      -- Record their glyphs on each actual output, just like ordinary boxes.
      annotate(n.leader)
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
  if mode~='tagged' then geometry=assert(io.open(string.format('geometry-%03d.jsonl',page_number),'w'));records={};rule_records={} end
  annotate(box)
  return true
end,'bako.provenance')
luatexbase.add_to_callback('finish_pdfpage',function()
  if geometry then
    if mode=='sidecar' and #records>0 then geometry:write(table.concat(records,'\n'),'\n') end
    if origins then
      local out=assert(io.open(string.format('origins-%03d.txt',page_number),'w'))
      local seen={}
      for _,id in ipairs(records) do
        if id>0 and not seen[id] then
          seen[id]=true;out:write(id,' ',origins.source_length(id),'\n')
        end
      end
      for _,id in ipairs(rule_records) do
        if not seen[id] then seen[id]=true;out:write(id,' ',origins.source_length(id),'\n') end
      end
      out:close()
    end
    geometry:close();geometry=nil
  end
end,'bako.geometry')
