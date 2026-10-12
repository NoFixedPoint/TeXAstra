-- Page commands and resource coverage, captured after real LuaTeX shipout.
-- The PDF drawing language is retained; no layout is reimplemented here.
local M={}
local function quote(s)
  return '"'..tostring(s):gsub('[%z\1-\31\\"]',function(c)
    return string.format('\\u%04x',string.byte(c))
  end)..'"'
end
function M.setup(snapshot)
  local page=0
  local pending=nil
  local coverage={}
  local seen_glyphs={}
  local font_keys={}
  local shipout_us=0
  local function key(id)
    if not font_keys[id] then
      local f=font.getfont(id)
      font_keys[id]=table.concat({id,f.name or '',f.filename or '',f.size or 0,f.encodingbytes or 0},'|')
    end
    return font_keys[id]
  end
  -- This set is captured by the real glyph-output callbacks in provenance.lua.
  function bako_stream_glyph(id,char)
    local seen=seen_glyphs[id]
    if not seen then seen={};seen_glyphs[id]=seen end
    if seen[char] then return end
    seen[char]=true
    local f=font.getfont(id)
    local c=f.characters[char] or {}
    local value=table.concat({key(id),char,c.index or -1,c.tounicode or ''},'|')
    coverage[value]=true
  end
  luatexbase.add_to_callback('pre_shipout_filter',function(box)
    page=page+1;bako_stream_page_count=page;coverage={};seen_glyphs={};shipout_us=snapshot.now();return true
  end,'bako.stream_begin')
  luatexbase.add_to_callback('finish_pdfpage',function(shippingout)
    -- XForms use the same callback. They are resource objects, not pages.
    if shippingout==false or page==0 then return end
    local entries={}
    for value in pairs(coverage) do entries[#entries+1]=quote(value) end
    table.sort(entries)
    local images={}
    if pdf.bakoimageresources then
      for name,info in pairs(pdf.bakoimageresources()) do
        local image=io.open(info.path,'rb')
        if image then
          local bytes=image:read('*a');image:close()
          images[#images+1]=quote(name)..':'..quote(info.path..'|'..info.properties..'|'..info.settings..'|'..md5.sumhexa(bytes))
        end
      end
    end
    table.sort(images)
    local record='{"page":'..(page-1)..',"pageObject":'..pdf.getpageref(page)..
      ',"width":'..(tex.pagewidth/65781.76)..',"height":'..(tex.pageheight/65781.76)..
      ',"coverage":['..table.concat(entries,',')..'],"images":{'..table.concat(images,',')..'}}'
    local bytes=snapshot.page_bytes()
    local f=assert(io.open(string.format('resources-%03d.json',page),'w'))
    f:write(record);f:close()
    if snapshot.is_live()==1 then
      -- Keep every shipped page; the worker selects the requested visible one.
      -- Reflow can ship more than one page from the changed input file.
      pending=pending or {}
      pending[#pending+1]={record,bytes}
    end
  end,'bako.stream_end')
  function bako_publish_page()
    if not pending or #pending==0 then return end
    local records,blocks={},{}
    for _,item in ipairs(pending) do
      records[#records+1]=item[1]:sub(1,-2)..',"byteLength":'..#item[2]..'}'
      blocks[#blocks+1]=item[2]
    end
    pending=nil
    local request_us,fork_us,restore_us,fork_start_us=snapshot.timings()
    local stages=string.format('"compilerStagesMs":{"replaceChild":%.3f,"fork":%.3f,"restore":%.3f,"typeset":%.3f,"shipoutAndPublish":%.3f},',
      (fork_start_us-request_us)/1000,(fork_us-fork_start_us)/1000,(restore_us-fork_us)/1000,(shipout_us-restore_us)/1000,(snapshot.now()-shipout_us)/1000)
    snapshot.publish('{'..stages..'"snapshot":'..snapshot.stats()..',"pages":['..table.concat(records,',')..']}',table.concat(blocks))
  end
end
return M
