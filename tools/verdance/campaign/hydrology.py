"""Planet hydrology: one body of water shared by seven maps; waterlines, storms, tides and their beats.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, clamp, load_json
from .schema import load_map_pool, map_family

# ---------------------------------------------------------------------------
# Planet hydrology: one body of water, shared by seven maps.
# ---------------------------------------------------------------------------

# The planet's water circulates rather than diffusing. A "move it from the
# fullest basin to the emptiest" rule equalises within two missions and then
# just sloshes between whichever pair is marginally off -- Koom Valley, the map
# this is FOR, never moves at all. A travelling wave instead gives every basin
# its turn to fill and drain, and keeps the total exactly conserved.
#
# Offsets are where each map sits on the current, in circulation turns. Authored,
# not measured: it is the shape of the campaign's weather.
HYDRO_RING = {
    "koom_valley": 0.0,
    "eye_of_horus": 0.20,
    "all_that_simmers": 0.33,
    "ancient_bastion": 0.53,
    "tabula": 0.66,
    "the_rock_jungle": 0.83,
}
# One full circulation every six missions.
HYDRO_PHASE_STEP = 1.0 / 6.0
HYDRO_SCHEMA = "verdance-planet-hydrology/1.0"

# The living world: seasons, temperaments, tides, wind, the player's arc.
# Landed from tools/campaign_flow_matrix_v1.py's already-validated scouting
# pass -- same constants, same formulas, translated onto the live engine's
# own data shapes rather than its offline lattice.
#
# Seasons: the travelling wave above conserves the planet's water, so some
# theatre is always mid-swing -- there is no moment the whole planet is
# calm. This is a slow amplitude envelope around each map's own mid-level,
# so "the world is stable" can be true of the world, not just a theatre.
SEASONS = {"period": 7.0, "depth": 0.6, "offset": 0.0}

# Owner-directed cap: Koom Valley's waterline never rises past this, so its
# flats stay permanent dry ground for infrastructure however the season and
# circulation move. Applied only where a level is read out for a mission --
# never to the conserved simulation itself.
HYDRO_LEVEL_CAP = {"koom_valley": 0.45}

# How hard each faction leans into the swing (Armada, adaptation doctrine)
# versus the still (NullMercs, paid lines). Cortex carries neither gain --
# "they just continue to bunker and scout" -- so its entry never moves with
# the weather's swing, only with the wind's pace (see WIND below).
TEMPERAMENT = {
    "armada":    {"base": 0.35, "swingGain": 1.0, "stillGain": 0.0},
    "nullmercs": {"base": 0.35, "swingGain": 0.0, "stillGain": 1.0},
    "cortex":    {"base": 0.25, "swingGain": 0.0, "stillGain": 0.0},
}

# The raptor bloom: decay * previous + gain * this mission's food (a lagged
# recession plus, once tides are flowing, the same-mission rise -- see
# TIDE["bloomFeed"]).
BLOOM = {"gain": 0.6, "decay": 0.45}

# In-mission tides: a rising waterline arrives as several flood pulses
# spread across the mission rather than one instant step, and a share of
# that same-mission rise feeds the raptor bloom immediately, no lag.
TIDE = {"pulses": 3, "bloomFeed": 0.5}

# Wind paces every offscreen economy -- Armada, NullMercs and Cortex alike --
# between a floor and floor+gain as the season runs from calm to storm.
WIND = {"floor": 0.7, "gain": 0.6}
_WIND_RANGE_RE = re.compile(r"W(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s+avg(\d+(?:\.\d+)?)")


def hydrology_storm_phase(mission_number: int, seasons: Dict[str, float] = SEASONS) -> float:
    """Where the season stands: 0.0 the deep calm, 1.0 the height of the storm."""
    period = float(seasons.get("period", 0.0) or 0.0)
    if period <= 0.0:
        return 0.5
    x = (mission_number - 1) / period + float(seasons.get("offset", 0.0))
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * x)


def hydrology_effective_level(raw_level: float, mission_number: int, map_id: str) -> float:
    """A mission's waterline: the raw circulation, narrowed by the season's
    amplitude envelope around the midline, then capped per map.

    Never written back into the conserved simulation -- only applied where a
    level is being read out for a mission, so swing (measured against the
    true underlying wave) is unaffected."""
    depth = clamp(float(SEASONS.get("depth", 0.0)))
    amp_env = 1.0 - depth * (1.0 - hydrology_storm_phase(mission_number))
    cap = float(HYDRO_LEVEL_CAP.get(map_id, 1.0))
    pivot = 0.5
    return clamp(pivot + amp_env * (raw_level - pivot), 0.0, cap)


def load_map_hydrology(map_id: str, workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Measured flood profile for one map (tools/hydrology_v1.py)."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "hydrology" / f"{map_id}.hydrology.json")
    here = WORKSPACE_ROOT
    paths.append(here / "data" / "hydrology" / f"{map_id}.hydrology.json")
    for path in paths:
        if path.exists():
            try:
                data = load_json(path)
                if isinstance(data, dict) and data.get("levels"):
                    return data
            except Exception:
                continue
    return None


def hydrology_map_ids(workspace: Optional[Path] = None) -> List[str]:
    """Maps with a measured flood profile, in a stable order."""
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "hydrology")
    roots.append(WORKSPACE_ROOT / "data" / "hydrology")
    for root in roots:
        if root.exists():
            found = sorted(p.name.split(".")[0] for p in root.glob("*.hydrology.json"))
            if found:
                return found
    return []


def ensure_planet_hydrology(state: Dict[str, Any],
                            workspace: Optional[Path] = None) -> Dict[str, Any]:
    """The world's water, as a conserved quantity distributed over the maps.

    Each map holds water up to its measured amplitude -- how far its own
    waterline can swing. Greenest Fields is a dry metal-free desert and holds
    none, so the cycle simply never touches it."""
    hydro = state.setdefault("hydrology", {})
    hydro.setdefault("schemaVersion", HYDRO_SCHEMA)
    maps = hydro.setdefault("maps", {})
    for map_id in hydrology_map_ids(workspace):
        profile = load_map_hydrology(map_id, workspace)
        amplitude = float((profile or {}).get("amplitude", 0.0) or 0.0)
        record = maps.setdefault(map_id, {})
        record["amplitude"] = amplitude
        record.setdefault("fill", 0.0)
        if amplitude <= 0.0:
            record["fill"] = 0.0
        record["fill"] = max(0.0, min(amplitude, float(record.get("fill", 0.0) or 0.0)))
        record["level"] = round(record["fill"] / amplitude, 4) if amplitude > 0 else 0.0
        record["basins"] = [b.get("basinId") for b in (profile or {}).get("basins", [])]
    if "planetWater" not in hydro:
        total_capacity = sum(float(m.get("amplitude", 0.0)) for m in maps.values())
        hydro["planetWater"] = round(total_capacity * 0.5, 4)
        # Seed each map's peak swing -- and the swing arriving into mission 1
        # itself -- from a couple of full circulations run before the
        # campaign's own phase=0, the same way an offline arc primes a tail
        # of pre-campaign weather. Without this, mission 1 reads as
        # perfectly still for every map, not because the world just started
        # circulating but because there is nothing yet to compare it to.
        probe = copy.deepcopy(hydro)
        peaks: Dict[str, float] = {}
        deltas_by_i: Dict[int, Dict[str, float]] = {}
        previous: Dict[str, float] = {}
        back_steps = 2
        forward_steps = int(round(2.0 / HYDRO_PHASE_STEP))
        for i in range(-back_steps, forward_steps + 1):
            probe["phase"] = round(i * HYDRO_PHASE_STEP, 6)
            distribute_planet_water(probe)
            row: Dict[str, float] = {}
            for mid, rec in probe.get("maps", {}).items():
                amp = float(rec.get("amplitude", 0.0) or 0.0)
                lvl = float(rec.get("level", 0.0) or 0.0)
                if amp > 1e-9 and mid in previous:
                    signed = (lvl - previous[mid]) / amp
                    row[mid] = signed
                    peaks[mid] = max(peaks.get(mid, 0.0), abs(signed))
                previous[mid] = lvl
            deltas_by_i[i] = row
        for mid, rec in maps.items():
            rec["peakSwing"] = round(peaks.get(mid, 0.0), 4)
            rec["levelDeltaPrevious"] = round(deltas_by_i.get(-back_steps + 1, {}).get(mid, 0.0), 4)
            rec["levelDelta"] = round(deltas_by_i.get(-back_steps + 2, {}).get(mid, 0.0), 4)
    hydro.setdefault("phase", 0.0)
    hydro.setdefault("lastShift", None)
    distribute_planet_water(hydro)
    return hydro


def distribute_planet_water(hydro: Dict[str, Any]) -> Dict[str, Any]:
    """Lay the planet's water out along the circulation at the current phase.

    Weights are a cosine wave running around the ring; the fixed total is split
    between maps in proportion, then clamped to each map's amplitude with the
    overflow passed on, so conservation survives the clamp."""
    maps = hydro.get("maps") or {}
    phase = float(hydro.get("phase", 0.0) or 0.0)
    total = float(hydro.get("planetWater", 0.0) or 0.0)

    weights: Dict[str, float] = {}
    for map_id, record in maps.items():
        amp = float(record.get("amplitude", 0.0) or 0.0)
        if amp <= 0.0:
            record["fill"] = 0.0
            record["level"] = 0.0
            continue
        offset = HYDRO_RING.get(map_id, 0.0)
        swell = 0.5 + 0.5 * math.cos(2.0 * math.pi * (phase - offset))
        weights[map_id] = amp * swell

    remaining = total
    unclamped = dict(weights)
    for _ in range(len(weights) + 1):
        weight_sum = sum(unclamped.values())
        if weight_sum <= 1e-9 or not unclamped:
            break
        spilled = False
        for map_id in list(unclamped):
            amp = float(maps[map_id]["amplitude"])
            share = remaining * (unclamped[map_id] / weight_sum)
            if share > amp:
                maps[map_id]["fill"] = round(amp, 4)
                remaining -= amp
                del unclamped[map_id]
                spilled = True
                break
        if not spilled:
            for map_id, weight in unclamped.items():
                maps[map_id]["fill"] = round(remaining * (weight / weight_sum), 4)
            break

    for record in maps.values():
        amp = float(record.get("amplitude", 0.0) or 0.0)
        record["level"] = round(float(record.get("fill", 0.0)) / amp, 4) if amp > 0 else 0.0
    return hydro


def advance_planet_hydrology(state: Dict[str, Any],
                             workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Turn the circulation one mission further. Total water is conserved.

    Deterministic: the same campaign state always produces the same weather."""
    hydro = ensure_planet_hydrology(state, workspace)
    before = {mid: float(rec.get("fill", 0.0)) for mid, rec in hydro["maps"].items()}
    hydro["phase"] = round(float(hydro.get("phase", 0.0)) + HYDRO_PHASE_STEP, 6)
    distribute_planet_water(hydro)

    deltas = {mid: float(rec.get("fill", 0.0)) - before.get(mid, 0.0)
              for mid, rec in hydro["maps"].items()}
    drained = min(deltas.items(), key=lambda kv: (kv[1], kv[0]))
    filling = max(deltas.items(), key=lambda kv: (kv[1], kv[0]))
    hydro["lastShift"] = {
        "from": drained[0], "to": filling[0],
        "amount": round(max(0.0, filling[1]), 4),
    }
    hydro["planetWater"] = round(sum(float(r.get("fill", 0.0))
                                     for r in hydro["maps"].values()), 4)
    # The swing signal: how far each map's waterline moved this mission,
    # signed and normalized by that map's own amplitude, plus a one-mission
    # lag of the same for the raptor bloom's recession feed. peakSwing only
    # ever grows -- the campaign-start probe seeds it, this is the
    # self-correcting safety net if reality ever exceeds that seed.
    for mid, rec in hydro["maps"].items():
        amp = float(rec.get("amplitude", 0.0) or 0.0)
        signed = (deltas.get(mid, 0.0) / amp) if amp > 1e-9 else 0.0
        rec["levelDeltaPrevious"] = rec.get("levelDelta", 0.0)
        rec["levelDelta"] = round(signed, 4)
        rec["peakSwing"] = round(max(float(rec.get("peakSwing", 0.0) or 0.0),
                                     abs(signed)), 4)
    return hydro


def map_waterline(state: Dict[str, Any], map_id: str,
                  workspace: Optional[Path] = None) -> Dict[str, Any]:
    """The waterline a mission on this map should start at."""
    hydro = ensure_planet_hydrology(state, workspace)
    record = (hydro.get("maps") or {}).get(map_id) or {}
    profile = load_map_hydrology(map_id, workspace)
    mission_number = int(state.get("missionNumber", 1) or 1)
    level = hydrology_effective_level(
        float(record.get("level", 0.0) or 0.0), mission_number, map_id)
    rung = None
    if profile:
        rungs = profile.get("rungs") or []
        if rungs:
            rung = min(rungs, key=lambda r: abs(float(r.get("level", 0.0)) - level))
    # One phase-step ahead, through the same envelope+cap -- the tide's
    # direction and range for this mission's beats (hydrology_beats below),
    # without ever touching the conserved simulation itself.
    probe = copy.deepcopy(hydro)
    probe["phase"] = round(float(hydro.get("phase", 0.0)) + HYDRO_PHASE_STEP, 6)
    distribute_planet_water(probe)
    next_raw = float((probe.get("maps") or {}).get(map_id, {}).get("level", level))
    next_level = hydrology_effective_level(next_raw, mission_number + 1, map_id)
    return {
        "level": round(level, 4),
        "nextLevel": round(next_level, 4),
        "amplitude": round(float(record.get("amplitude", 0.0) or 0.0), 4),
        "elevation": (rung or {}).get("elevation"),
        "terraformDelta": (rung or {}).get("terraformDelta"),
        "areaSubmerged": (rung or {}).get("areaSubmerged"),
        "metalSpotsSubmerged": (rung or {}).get("metalSpotsSubmerged"),
        "basins": list(record.get("basins") or []),
        "phase": int(hydro.get("phase", 0)),
        "lastShift": hydro.get("lastShift"),
    }


# What the hub calls an assault at this waterline, read off the zones that can flood (those
# that are at least half under at the top of the swing): their mean share under water.
ASSAULT_WORDS = ((0.45, "amphibious"), (0.2, "shallows"), (0.0, "dry bed"))


def _share_at(levels: List[float], shares: List[float], level: float) -> float:
    if not levels or not shares:
        return 0.0
    if level <= levels[0]:
        return float(shares[0])
    for i in range(1, len(levels)):
        if level <= levels[i]:
            a, b = float(levels[i - 1]), float(levels[i])
            k = (level - a) / (b - a) if b > a else 0.0
            return float(shares[i - 1]) + k * (float(shares[i]) - float(shares[i - 1]))
    return float(shares[-1])


def waterline_surface(state: Dict[str, Any], map_id: str,
                      workspace: Optional[Path] = None) -> Dict[str, Any]:
    """The next sortie's waterline on one map, for the hub: the level now and next, how much of
    each zone is under, and what that makes an assault (dry bed, shallows, amphibious)."""
    line = map_waterline(state, map_id, workspace)
    profile = load_map_hydrology(map_id, workspace) or {}
    levels = [float(x) for x in profile.get("levels") or []]
    level, nxt = float(line.get("level") or 0.0), float(line.get("nextLevel") or 0.0)
    if float(line.get("amplitude") or 0.0) <= 0.0:
        level = nxt = 0.0                     # a map the cycle never touches
    zones: Dict[str, float] = {}
    floodable: List[float] = []
    for zid, rec in (profile.get("zones") or {}).items():
        shares = [float(x) for x in rec.get("submergedAt") or []]
        now = _share_at(levels, shares, level)
        if now >= 0.02:
            zones[zid] = round(now, 3)
        if shares and max(shares) >= 0.5:
            floodable.append(now)
    if line.get("amplitude", 0) <= 0 and not floodable:
        word = "dry"
    else:
        wet = sum(floodable) / len(floodable) if floodable else 0.0
        word = next(w for cut, w in ASSAULT_WORDS if wet >= cut)
    trend = "rising" if nxt > level + 0.02 else "falling" if nxt < level - 0.02 else "steady"
    return {"level": round(level, 3), "nextLevel": round(nxt, 3), "trend": trend,
            "cap": HYDRO_LEVEL_CAP.get(map_id), "areaSubmerged": line.get("areaSubmerged"),
            "assault": word, "zones": zones}


def hydrology_swing(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, float]:
    """How far each map's waterline moved this mission, 0..1 against that
    map's own peak swing. A map that cannot swing (Greenest Fields, whose
    amplitude is 0) reads 0.0 by construction, never a special case."""
    hydro = ensure_planet_hydrology(state, workspace)
    out: Dict[str, float] = {}
    for map_id, rec in (hydro.get("maps") or {}).items():
        peak = float(rec.get("peakSwing", 0.0) or 0.0)
        raw = abs(float(rec.get("levelDelta", 0.0) or 0.0))
        out[map_id] = clamp(raw / peak) if peak > 1e-9 else 0.0
    return out


def hydrology_activity(state: Dict[str, Any],
                       workspace: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """Each temperamental faction's activity on each map this mission."""
    swing = hydrology_swing(state, workspace)
    return {
        map_id: {
            faction: clamp(float(t.get("base", 0.0))
                           + float(t.get("swingGain", 0.0)) * s
                           + float(t.get("stillGain", 0.0)) * (1.0 - s))
            for faction, t in TEMPERAMENT.items()
        }
        for map_id, s in swing.items()
    }


def hydrology_wind_range(workspace: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """Each map's authored wind range, parsed from the map pool's own
    heuristics string (e.g. "W4-12 avg6e/t") -- the workspace's own reading
    of the real maps' wind, already carried end-to-end into every generated
    mission but never, until now, read numerically."""
    out: Dict[str, Dict[str, float]] = {}
    for map_id, entry in load_map_pool(workspace).items():
        text = str((entry.get("heuristics") or {}).get("wind") or "")
        m = _WIND_RANGE_RE.match(text)
        if m:
            out[map_id] = {"min": float(m.group(1)), "max": float(m.group(2))}
    return out


def hydrology_wind_pace(state: Dict[str, Any],
                        workspace: Optional[Path] = None) -> Dict[str, float]:
    """The pace the wind sets for every offscreen economy this mission,
    per map: each map's own range run from its floor to its ceiling as the
    season moves from calm to storm, normalized against the whole pool's
    combined range so windier maps stay windier at every point in the
    season."""
    ranges = hydrology_wind_range(workspace)
    if not ranges:
        return {}
    lo = min(r["min"] for r in ranges.values())
    hi = max(r["max"] for r in ranges.values())
    span = (hi - lo) or 1.0
    storm = hydrology_storm_phase(int(state.get("missionNumber", 1) or 1))
    out: Dict[str, float] = {}
    for map_id, rng in ranges.items():
        wind_now = rng["min"] + storm * (rng["max"] - rng["min"])
        out[map_id] = float(WIND["floor"]) + float(WIND["gain"]) * clamp((wind_now - lo) / span)
    return out


# A flood is only an event if the player sees it coming. Telegraph first, move
# the water a beat later.
HYDRO_EVENT_MIN_AMPLITUDE = 0.5
HYDRO_EVENT_SWING = 0.45
HYDRO_WARNING_SECONDS = 420
HYDRO_EVENT_SECONDS = 465


def hydrology_beats(waterline: Dict[str, Any], bark) -> List[Dict[str, Any]]:
    """Mid-mission tide, on maps whose water actually swings.

    A rising waterline is realised as several intermittent floods across the
    10-19 minute mark rather than one instant step -- an in-mission
    superposition of where the line stood and where it is going, on the
    real tidal timescale. A falling waterline drains in one beat, as before;
    the recession is what feeds the raptor bloom (update_hydrology_bloom),
    already lagged, so it doesn't also need an in-mission pulse."""
    hydro = waterline or {}
    amplitude = float(hydro.get("amplitude", 0.0) or 0.0)
    level = float(hydro.get("level", 0.0) or 0.0)
    next_level = float(hydro.get("nextLevel", level) or level)
    if amplitude < HYDRO_EVENT_MIN_AMPLITUDE:
        return []
    delta = next_level - level
    if abs(delta) < 0.05:
        return []
    direction = "rising" if delta > 0.0 else "falling"

    warning = bark("bark.hydrology." + direction + "_warning")
    settled = bark("bark.hydrology." + direction)
    out: List[Dict[str, Any]] = []
    if warning:
        out.append({
            "id": "b8_water_warning",
            "trigger": {"type": "time", "seconds": HYDRO_WARNING_SECONDS},
            "actions": [warning, {"type": "sound", "file": "beep6", "volume": 0.8}],
        })
    if direction == "rising":
        pulses = max(1, int(TIDE.get("pulses", 1)))
        start_s, end_s = 600, 1140  # the 10-19 minute mark
        for i in range(pulses):
            frac = (i + 1) / pulses
            actions: List[Dict[str, Any]] = [
                {"type": "hydrology", "to": round(level + frac * delta, 3), "seconds": 25},
            ]
            if i == pulses - 1 and settled:
                actions.append(settled)
            out.append({
                "id": "b9_water_pulse_{0}".format(i + 1),
                "trigger": {"type": "time",
                           "seconds": int(round(start_s + frac * (end_s - start_s)))},
                "actions": actions,
            })
    else:
        actions = [{"type": "hydrology", "to": round(next_level, 3), "seconds": 25}]
        if settled:
            actions.append(settled)
        out.append({
            "id": "b9_water",
            "trigger": {"type": "time", "seconds": HYDRO_EVENT_SECONDS},
            "actions": actions,
        })
    return out


def update_hydrology_bloom(state: Dict[str, Any], map_id: str,
                           workspace: Optional[Path] = None) -> float:
    """The raptor population wave: decay * previous + gain * this mission's
    food -- a lagged recession plus a share of any same-mission tidal rise,
    so a pulse that recedes inside one mission feeds the bloom immediately.

    Lives in its own state key, not hazardState (which is keyed by zone id
    and would corrupt that per-zone loop)."""
    if map_family(map_id) != "wild":
        return 0.0
    hydro = ensure_planet_hydrology(state, workspace)
    rec = (hydro.get("maps") or {}).get(map_id) or {}
    lag_recession = max(0.0, -float(rec.get("levelDeltaPrevious", 0.0) or 0.0))
    same_mission_rise = max(0.0, float(rec.get("levelDelta", 0.0) or 0.0))
    food = lag_recession + float(TIDE["bloomFeed"]) * same_mission_rise
    store = state.setdefault("hydrologyBloom", {}).setdefault(map_id, {"bloom": 0.0})
    previous = float(store.get("bloom", 0.0) or 0.0)
    bloom = clamp(float(BLOOM["decay"]) * previous + float(BLOOM["gain"]) * food, 0.0, 3.0)
    store["bloom"] = round(bloom, 4)
    return store["bloom"]


__all__ = [
    "ASSAULT_WORDS",
    "BLOOM",
    "HYDRO_EVENT_MIN_AMPLITUDE",
    "HYDRO_EVENT_SECONDS",
    "HYDRO_EVENT_SWING",
    "HYDRO_LEVEL_CAP",
    "HYDRO_PHASE_STEP",
    "HYDRO_RING",
    "HYDRO_SCHEMA",
    "HYDRO_WARNING_SECONDS",
    "SEASONS",
    "TEMPERAMENT",
    "TIDE",
    "WIND",
    "_WIND_RANGE_RE",
    "advance_planet_hydrology",
    "distribute_planet_water",
    "ensure_planet_hydrology",
    "hydrology_activity",
    "hydrology_beats",
    "hydrology_effective_level",
    "hydrology_map_ids",
    "hydrology_storm_phase",
    "hydrology_swing",
    "hydrology_wind_pace",
    "hydrology_wind_range",
    "load_map_hydrology",
    "map_waterline",
    "waterline_surface",
    "update_hydrology_bloom",
]
