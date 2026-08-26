local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Capability Probe",
    desc = "WO-043: one-shot probe of io write + Spring.Reload availability (logs only)",
    author = "Head Hancho",
    date = "2026-07-25",
    license = "GPL v2 or later",
    layer = -1,
    enabled = true,
  }
end

-- Unsynced-only probe: do not affect gameplay.
if gadgetHandler:IsSyncedCode() then
  return
end

local probed = false

local function probe()
  if probed then return end
  probed = true
  local mo = Spring.GetModOptions and Spring.GetModOptions() or {}
  if mo.va_headless_autostart then
    Spring.Echo("VA_PROBE skip headless")
    return
  end

  local hasIo = (io ~= nil and type(io.open) == "function")
  local hasOs = (os ~= nil)
  local hasReload = (Spring.Reload ~= nil and type(Spring.Reload) == "function")
  local writeOk = false
  local writePath = nil
  local readBackOk = false
  if hasIo then
    for _, p in ipairs({
      "LuaUI/Config/verdance_probe_write.txt",
      "verdance_probe_write.txt",
      "LuaUI/Config/verdance_capability.json",
    }) do
      local f = io.open(p, "w")
      if f then
        local stamp = tostring(Spring.GetGameFrame() or 0)
        f:write("verdance_probe_ok frame=" .. stamp .. "\n")
        f:close()
        writeOk = true
        writePath = p
        local r = io.open(p, "r")
        if r then
          local body = r:read("*a") or ""
          r:close()
          readBackOk = body:find("verdance_probe_ok", 1, true) ~= nil
        end
        break
      end
    end
  end

  local engine = tostring(Engine and Engine.version or Game and Game.version or "?")
  Spring.Echo("VA_PROBE_IO has_io=" .. tostring(hasIo) .. " write_ok=" .. tostring(writeOk) .. " read_back=" .. tostring(readBackOk) .. " path=" .. tostring(writePath or ""))
  Spring.Echo("VA_PROBE_OS has_os=" .. tostring(hasOs))
  Spring.Echo("VA_PROBE_RELOAD has_reload=" .. tostring(hasReload))
  Spring.Echo("VA_PROBE_ENGINE version=" .. engine)
  -- Structured one-liner for session host / capability matrix harvest.
  Spring.Echo("VA_CAPABILITY {io=" .. tostring(hasIo)
    .. ",write=" .. tostring(writeOk)
    .. ",read_back=" .. tostring(readBackOk)
    .. ",reload=" .. tostring(hasReload)
    .. ",os=" .. tostring(hasOs)
    .. ",engine=" .. engine
    .. ",path=" .. tostring(writePath or "")
    .. "}")
  -- Do NOT call Spring.Reload here — log capability only (Mode B gated).
  Spring.Echo("VA_PROBE_DONE")
end

function gadget:GameFrame(frame)
  if frame == 45 then
    probe()
  end
end
