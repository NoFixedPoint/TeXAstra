-- General projects checkpoint at engine safe points; the comparison corpus
-- retains its explicit page-file boundaries.
local snapshot=assert(package.loadlib('./bako_snapshot.so','luaopen_bako_snapshot'))()
local general=os.getenv('BAKO_LIVE_DOCUMENT')=='1'
local limit=general and 10000 or 100
local resumed,shipped,finished=0,0,0
local stream=os.getenv('BAKO_PAGE_STREAM')=='1'
if stream then
  assert(status.luatex_version==114,'Page-stream adapter requires LuaTeX 1.14')
  pdf.setcompresslevel(0);pdf.setobjcompresslevel(0)
  dofile('page_stream.lua').setup(snapshot)
end
function bako_checkpoint(index)
  if stream and index>limit then bako_publish_page() end
  if not os.getenv('BAKO_SNAPSHOT_DISABLE') then limit=snapshot.checkpoint(index) end
  resumed=snapshot.now()
  if index>limit then tex.sprint('\\end{document}') end
end
local checkpoint_page=-1
function bako_live_begin()
  bako_input_block=1
  snapshot.refresh_sources()
  snapshot.enable_boundaries()
end
function bako_live_end() snapshot.disable_boundaries() end
function bako_boundary()
  local shipped=bako_stream_page_count or 0
  if stream and snapshot.is_live()==1 and shipped>=limit then bako_publish_page() end
  -- One checkpoint per physical page, between commands in outer vertical
  -- mode. The engine supplies these boundaries inside included files too.
  if shipped~=checkpoint_page and not os.getenv('BAKO_SNAPSHOT_DISABLE') then
    local index=shipped+1
    local f=assert(io.open(string.format('cp-%03d.meta',index),'w'))
    f:write(bako_input_metadata(shipped));f:close()
    limit=snapshot.checkpoint(index)
    bako_reload_inputs()
    if snapshot.is_live()==1 then
      bako_reload_sources()
      snapshot.refresh_sources()
    end
    checkpoint_page=shipped
  end
end
luatexbase.add_to_callback('pre_shipout_filter',function(box) shipped=snapshot.now();return true end,'bako.timing')
luatexbase.add_to_callback('finish_pdffile',function()
  if stream then bako_publish_page() end
  finished=snapshot.now()
end,'bako.pdf_timing')
-- General projects install this reader before packages, with an input journal.
if not general then luatexbase.add_to_callback('open_read_file',function(name)
  local index=tonumber(name:match('page%-(%d+)%.tex$'))
  if not general and index and index>limit then return {reader=function() return nil end,close=function() end} end
  local f=io.open(name,'r')
  if not f then return nil end
  return {reader=function() return f:read('*l') end,close=function() f:close() end}
end,'bako.buffered_input') end
luatexbase.add_to_callback(stream and 'wrapup_run' or 'stop_run',function()
  if stream and finished==0 then
    local f=assert(io.open('failed.json','w'))
    f:write('{"failed":true}');f:close()
    snapshot.park()
    return
  end
  if stream then snapshot.export_pdf() end
  local f=assert(io.open('completed.json','w'))
  f:write('{"limit":'..limit..',"compiledPages":'..(bako_stream_page_count or 0)..',"complete":true,"lastCheckpointUs":'..resumed..',"lastShipoutUs":'..shipped..',"pdfFinishedUs":'..finished..',"stoppedUs":'..snapshot.now()..'}')
  f:close()
  snapshot.park()
end,'bako.completed')
