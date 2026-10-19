local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Tnb Build Cost",
    desc = "Show Tenebrium stake on build cards above metal/energy (hide when 0)",
    author = "Verdance",
    date = "2026-09-07",
    license = "GPL v2 or later",
    layer = 5,
    enabled = true,
  }
end

--[[
  Uses BAR gridmenu/buildmenu setCostOverride `above` line (patched in BAR.sdd).
  Only units with Tnb cost > 0 get an override; zero-cost units keep stock M/E.
]]

local TnbCosts = nil
local applied = {}
local lastApplyFrame = -99999
local APPLY_PERIOD = 90 -- re-bind periodically in case menus reload

local function loadCosts()
  if TnbCosts then return TnbCosts end
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_tnb_costs.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaUI/Include/va_tnb_costs.lua")
  end
  if ok and type(mod) == "table" then
    TnbCosts = mod
  else
    TnbCosts = {
      costOf = function() return 0 end,
      COLOR = "\255\200\160\255",
      COLOR_DISABLED = "\255\120\100\140",
    }
  end
  return TnbCosts
end

local function costDataFor(cost)
  local C = loadCosts()
  return {
    -- `above` = Tnb line drawn above metal/energy (BAR cost-override extension).
    above = {
      value = cost,
      color = C.COLOR or "\255\200\160\255",
      colorDisabled = C.COLOR_DISABLED or "\255\120\100\140",
    },
    -- Leave top/bottom unset so metal + energy stay stock.
  }
end

local function applyAll(force)
  local C = loadCosts()
  if not UnitDefs then return 0 end
  local grid = WG and WG["gridmenu"]
  local build = WG and WG["buildmenu"]
  if not ((grid and grid.setCostOverride) or (build and build.setCostOverride)) then
    return 0
  end

  local n = 0
  for unitDefID, ud in pairs(UnitDefs) do
    if ud then
      local cost = math.floor(tonumber(C.costOf(unitDefID)) or 0)
      if cost > 0 then
        if force or applied[unitDefID] ~= cost then
          local data = costDataFor(cost)
          if grid and grid.setCostOverride then
            pcall(grid.setCostOverride, unitDefID, data)
          end
          if build and build.setCostOverride then
            pcall(build.setCostOverride, unitDefID, data)
          end
          applied[unitDefID] = cost
        end
        n = n + 1
      elseif applied[unitDefID] then
        -- Cost became 0 — clear so we don't leave a stale Tnb line.
        if grid and grid.clearCostOverrides then
          pcall(grid.clearCostOverrides, unitDefID)
        end
        if build and build.clearCostOverrides then
          pcall(build.clearCostOverrides, unitDefID)
        end
        applied[unitDefID] = nil
      end
    end
  end

  -- Expose lookup for gui_info / other widgets.
  WG = WG or {}
  WG["verdance_tnb"] = WG["verdance_tnb"] or {}
  WG["verdance_tnb"].costOf = function(unitDefID)
    return math.floor(tonumber(C.costOf(unitDefID)) or 0)
  end
  WG["verdance_tnb"].color = C.COLOR
  return n
end

function widget:Initialize()
  loadCosts()
  local n = applyAll(true)
  Spring.Echo("VA_TNB_BUILDCOST_ARMED overrides=" .. tostring(n)
    .. " (above metal/energy; 0 hidden)")
end

function widget:Shutdown()
  local grid = WG and WG["gridmenu"]
  local build = WG and WG["buildmenu"]
  if grid and grid.clearCostOverrides then pcall(grid.clearCostOverrides) end
  if build and build.clearCostOverrides then pcall(build.clearCostOverrides) end
  if WG and WG["verdance_tnb"] then
    WG["verdance_tnb"].costOf = nil
  end
  applied = {}
end

function widget:GameStart()
  applyAll(true)
end

function widget:GameFrame(frame)
  if frame - lastApplyFrame < APPLY_PERIOD then return end
  lastApplyFrame = frame
  -- Menus may init late; re-apply cheaply (skips unchanged).
  applyAll(false)
end
