-- Include every line delivered to TeX, even argument/macro read-ahead. EOF
-- consumes one extra position so appending invalidates an observed file end.
local journal=assert(io.open('bako-inputs.jsonl','w'))
local active,positions={},{}
bako_input_block=0 -- preamble/body phase in the open journal
local function quote(value)
  return '"'..value:gsub('[%z\1-\31\\"]',function(c)
    return string.format('\\u%04x',string.byte(c))
  end)..'"'
end
function bako_input_metadata(shipped)
  local rows={}
  for name,position in pairs(positions) do
    rows[#rows+1]='['..quote(name)..','..position..']'
  end
  table.sort(rows)
  return '{"kind":"engine","shipped":'..shipped..',"inputs":['..table.concat(rows,',')..']}'
end
function bako_reload_inputs()
  -- Descriptor restore alone retains stale stdio read-ahead. Reopen Lua
  -- readers at logical positions, leaving TeX's unchanged line intact.
  for state in pairs(active) do
    state.handle:close()
    state.handle=assert(io.open(state.name,'rb'))
    state.size=assert(state.handle:seek('end'))
    assert(state.handle:seek('set',state.position))
  end
end
luatexbase.add_to_callback('open_read_file',function(name)
  local f=io.open(name,'rb')
  if not f then return nil end
  local state={name=name,handle=f,size=assert(f:seek('end')),position=0}
  assert(f:seek('set',0))
  active[state]=true
  positions[name]=positions[name] or 0
  journal:write('[',bako_input_block,',',quote(name),']\n')
  journal:flush()
  return {reader=function()
    local value=state.handle:read('*l')
    state.position=math.min(state.size,state.position+(value and #value+1 or 0))
    local consumed=value and state.position or state.size+1
    positions[name]=math.max(positions[name],consumed)
    return value
  end,close=function() active[state]=nil;state.handle:close() end}
end,'bako.buffered_input')
