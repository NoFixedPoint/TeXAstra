-- Install before the preamble so a file read there can never reuse a body
-- checkpoint. Keep the journal open: fork restore truncates it to the saved
-- position along with TeX's other outputs, discarding abandoned dependencies.
local journal=assert(io.open('bako-inputs.jsonl','w'))
bako_input_block=0
local function quote(value)
  return '"'..value:gsub('[%z\1-\31\\"]',function(c)
    return string.format('\\u%04x',string.byte(c))
  end)..'"'
end
luatexbase.add_to_callback('open_read_file',function(name)
  local f=io.open(name,'r')
  if not f then return nil end
  journal:write('[',bako_input_block,',',quote(name),']\n')
  journal:flush()
  return {reader=function() return f:read('*l') end,close=function() f:close() end}
end,'bako.buffered_input')
