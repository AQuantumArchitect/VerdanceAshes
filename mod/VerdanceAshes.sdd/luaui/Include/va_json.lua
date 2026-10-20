-- Tiny JSON decoder for Verdance widgets (gadgets are the only JSON authors).
local J = {}

function J.decode(str)
  if type(str) ~= "string" or str == "" then return nil end
  local pos = 1
  local n = #str
  local function ws() pos = str:find("%S", pos) or (n + 1) end
  local parseValue
  local function parseString()
    pos = pos + 1
    local out = {}
    while pos <= n do
      local c = str:sub(pos, pos)
      if c == '"' then pos = pos + 1; return table.concat(out) end
      if c == "\\" then
        local e = str:sub(pos + 1, pos + 1)
        if e == "n" then out[#out + 1] = "\n"
        elseif e == "t" then out[#out + 1] = "\t"
        elseif e == "u" then out[#out + 1] = "?"; pos = pos + 4
        else out[#out + 1] = e end
        pos = pos + 2
      else
        out[#out + 1] = c; pos = pos + 1
      end
    end
    return table.concat(out)
  end
  local function parseNumber()
    local s, e = str:find("^-?%d+%.?%d*[eE]?[-+]?%d*", pos)
    if not s then error("bad number") end
    local v = tonumber(str:sub(s, e)); pos = e + 1; return v
  end
  parseValue = function()
    ws()
    local c = str:sub(pos, pos)
    if c == "{" then
      pos = pos + 1; local t = {}
      ws(); if str:sub(pos, pos) == "}" then pos = pos + 1; return t end
      while true do
        ws(); local k = parseString(); ws(); pos = pos + 1
        t[k] = parseValue(); ws()
        local d = str:sub(pos, pos); pos = pos + 1
        if d == "}" then return t end
        if d ~= "," then error("bad object") end
      end
    elseif c == "[" then
      pos = pos + 1; local t = {}
      ws(); if str:sub(pos, pos) == "]" then pos = pos + 1; return t end
      while true do
        t[#t + 1] = parseValue(); ws()
        local d = str:sub(pos, pos); pos = pos + 1
        if d == "]" then return t end
        if d ~= "," then error("bad array") end
      end
    elseif c == '"' then return parseString()
    elseif str:sub(pos, pos + 3) == "true" then pos = pos + 4; return true
    elseif str:sub(pos, pos + 4) == "false" then pos = pos + 5; return false
    elseif str:sub(pos, pos + 3) == "null" then pos = pos + 4; return nil
    else return parseNumber() end
  end
  local ok, v = pcall(parseValue)
  if ok then return v end
  return nil
end

return J
