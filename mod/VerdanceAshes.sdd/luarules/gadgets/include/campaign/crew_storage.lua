-- campaign/crew_storage.lua: the company's metal and energy storage caps, re-applied after BAR's own start reset
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_refreshPlayerStorageCaps, tickStorageRefresh
-- Uses: crew, state

-- BAR Team Resourcing (layer 1) SetTeamResource(ms/es) on GameStart wipes the
-- engine sum of storage buildings. Recompute from live player units and restore
-- caps; optionally top up commerce bag metal/energy if an earlier clip ate it.
function VA_refreshPlayerStorageCaps(reason)
  if playerTeamID == nil then return false end
  local unitMs, unitEs = 0, 0
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local defID = Spring.GetUnitDefID(uid)
      local ud = defID and UnitDefs[defID]
      if ud then
        unitMs = unitMs + (tonumber(ud.metalStorage) or 0)
        unitEs = unitEs + (tonumber(ud.energyStorage) or 0)
      end
    end
  end
  local wantM = tonumber(VA_CREW_SELECT and VA_CREW_SELECT.wantMetal) or 0
  local wantE = tonumber(VA_CREW_SELECT and VA_CREW_SELECT.wantEnergy) or 0
  -- Cap = building/com sum (BAR floor 1000). Commerce bag may temporarily lift
  -- the floor so the km$ dump is not clipped before storages finish applying.
  local ms = math.max(1000, unitMs)
  local es = math.max(1000, unitEs)
  if wantM > ms then ms = wantM + 500 end
  if wantE > es then es = wantE + 500 end
  pcall(Spring.SetTeamResource, playerTeamID, "ms", ms)
  pcall(Spring.SetTeamResource, playerTeamID, "es", es)
  local mCur = select(1, Spring.GetTeamResources(playerTeamID, "metal")) or 0
  local eCur = select(1, Spring.GetTeamResources(playerTeamID, "energy")) or 0
  if wantM > 0 and mCur + 1 < wantM then
    pcall(Spring.AddTeamResource, playerTeamID, "metal", wantM - mCur)
  end
  if wantE > 0 and eCur + 1 < wantE then
    pcall(Spring.AddTeamResource, playerTeamID, "energy", wantE - eCur)
  end
  local mNow, mStor = Spring.GetTeamResources(playerTeamID, "metal")
  local eNow, eStor = Spring.GetTeamResources(playerTeamID, "energy")
  Spring.Echo("VA_STORAGE_REFRESH reason=" .. tostring(reason or "")
    .. " ms=" .. tostring(math.floor(tonumber(mStor) or 0))
    .. " es=" .. tostring(math.floor(tonumber(eStor) or 0))
    .. " metal=" .. tostring(math.floor(tonumber(mNow) or 0))
    .. " energy=" .. tostring(math.floor(tonumber(eNow) or 0))
    .. " fromUnits_m=" .. tostring(math.floor(unitMs))
    .. " fromUnits_e=" .. tostring(math.floor(unitEs)))
  return true
end

-- Called by gadget:GameFrame.
function tickStorageRefresh(frame)
  -- Re-apply M/E storage caps after BAR Team Resourcing's GameStart wipe.
  do
    local untilF = VA_CREW_SELECT and tonumber(VA_CREW_SELECT.storageRefreshUntil)
    if untilF and frame >= 1 and frame <= untilF then
      VA_refreshPlayerStorageCaps("frame_" .. tostring(frame))
      if frame >= untilF then
        VA_CREW_SELECT.storageRefreshUntil = nil
        -- Drop temporary commerce floors; ongoing caps come from buildings.
        VA_CREW_SELECT.wantMetal = nil
        VA_CREW_SELECT.wantEnergy = nil
        VA_refreshPlayerStorageCaps("post_commerce_settle")
      end
    end
  end
end
