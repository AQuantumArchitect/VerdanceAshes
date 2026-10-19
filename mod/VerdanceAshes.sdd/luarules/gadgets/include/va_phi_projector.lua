-- Verdance φ projector stub (Stage 2 shadow).
-- Builds a best-effort φ vector in molecule axes from sparse cues.
-- NOT wired into IntentResolver / unit_behavior think loop.
-- Python SSOT + scenarios: tools/phi_projector_v1.py · data/story/phi_features.json

local M = {}

M.AXES = {
  "energy", "offense", "mobility", "sight", "pad",
  "craft", "heat", "fog", "sky", "ledger",
}

-- Sparse cue → axis contributions (subset of phi_features.json).
M.FEATURES = {
  energy_surplus = { energy = 0.85, craft = 0.35, heat = -0.15 },
  energy_drought = { energy = -0.9, heat = 0.35, craft = -0.2 },
  statics_nearby = { pad = 0.45, offense = 0.55, heat = 0.25, mobility = -0.2 },
  open_kite_room = { mobility = 0.8, pad = -0.45, sight = 0.15 },
  jammer_radar = { fog = 0.75, sight = 0.55 },
  heat_ash = { heat = 0.85, offense = 0.35, energy = -0.45 },
  pad_owned = { pad = 0.8, craft = 0.25, mobility = -0.35 },
  threat_envelope = { mobility = 0.45, offense = -0.15, fog = 0.2 },
  craft_opportunity = { craft = 0.8, energy = 0.2, offense = -0.25 },
  siege_line = { offense = 0.55, pad = 0.4, heat = 0.3, mobility = -0.35 },
  scout_screen = { sight = 0.7, fog = 0.45, mobility = 0.25 },
  ledger_pressure = { ledger = 0.7, offense = 0.2 },
}

local function clamp(v, lo, hi)
  v = tonumber(v) or 0
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

function M.zero()
  local phi = {}
  for i = 1, #M.AXES do
    phi[M.AXES[i]] = 0
  end
  return phi
end

--- cues: { featureId = weight, ... }
--- mapPressure: optional { axis = float } slow prior (weight 0.35)
function M.project(cues, mapPressure)
  local phi = M.zero()
  if type(cues) == "table" then
    for fid, w in pairs(cues) do
      w = tonumber(w) or 0
      local feat = M.FEATURES[tostring(fid)]
      if feat and w ~= 0 then
        for axis, av in pairs(feat) do
          if phi[axis] ~= nil then
            phi[axis] = phi[axis] + w * (tonumber(av) or 0)
          end
        end
      end
    end
  end
  if type(mapPressure) == "table" then
    for i = 1, #M.AXES do
      local a = M.AXES[i]
      phi[a] = phi[a] + 0.35 * (tonumber(mapPressure[a]) or 0)
    end
  end
  for i = 1, #M.AXES do
    local a = M.AXES[i]
    phi[a] = clamp(phi[a], -1, 1)
  end
  return phi
end

function M.fit(u, phi)
  local s = 0
  if type(u) ~= "table" or type(phi) ~= "table" then return 0 end
  for i = 1, #M.AXES do
    local a = M.AXES[i]
    s = s + (tonumber(u[a]) or 0) * (tonumber(phi[a]) or 0)
  end
  return s
end

--- Best-effort beliefs → cues. Missing leaves = honest absence.
function M.cuesFromBeliefs(beliefs)
  local cues = {}
  if type(beliefs) ~= "table" then return cues end
  local function val(role)
    local b = beliefs[role]
    if type(b) ~= "table" then return 0.5, 0 end
    return tonumber(b.value or b[1]) or 0.5, tonumber(b.confidence or b[2]) or 0
  end
  local tv, tc = val("threat")
  if tc >= 0.2 and tv >= 0.55 then cues.threat_envelope = tv end
  local pv, pc = val("pain")
  if pc >= 0.2 and pv >= 0.5 then
    cues.threat_envelope = math.max(cues.threat_envelope or 0, pv * 0.7)
  end
  local cv, cc = val("craft")
  if cc >= 0.2 and cv >= 0.45 then cues.craft_opportunity = cv end
  local hv, hc = val("hold")
  if hc >= 0.2 and hv >= 0.5 then cues.pad_owned = hv end
  local prv, prc = val("pressure")
  if prc >= 0.2 and prv >= 0.55 then cues.ledger_pressure = prv * 0.8 end
  return cues
end

return M
