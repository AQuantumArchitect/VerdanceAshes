"""Measurement: BAR telemetry collapses into zone memory; offscreen ticks, front decay, the player's regression arc, graph deltas and the spectral read of the battlefield.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from verdance.common import canonical_map_id, clamp, utc_now
from .schema import (
    BP_PER_TNB,
    FAMILY_CALIBRATION,
    FRONT_DECAY_MIN_PRESSURE,
    FRONT_DECAY_RATE,
    FRONT_EVENTS_KEEP,
    TELEMETRY_SCHEMA,
    TIME_BAND_FAR_RATE,
    TIME_BAND_LIVE_RATE,
    TIME_BAND_NEAR_RATE,
    blank_zone_memory,
    default_v1_state,
    map_family,
)
from .hydrology import hydrology_activity, hydrology_wind_pace
from .zones import canonical_zone_id

def get_elapsed_minutes(result: Dict[str, Any], telemetry: Optional[Dict[str, Any]], map_id: str) -> float:
    if result.get("elapsedMinutes") is not None:
        return max(0.1, float(result["elapsedMinutes"]))
    if telemetry and telemetry.get("seconds") is not None:
        return max(0.1, float(telemetry["seconds"]) / 60.0)
    family = map_family(map_id)
    return FAMILY_CALIBRATION[family]["defaultElapsedMinutes"]


def iter_zone_entries(telemetry: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    zones = telemetry.get("zones", {})
    if isinstance(zones, dict):
        for zone_id, zone in zones.items():
            if isinstance(zone, dict):
                yield str(zone.get("zoneId", zone_id)), zone
    elif isinstance(zones, list):
        for zone in zones:
            if isinstance(zone, dict):
                yield str(zone.get("zoneId", "unknown_zone")), zone


def iter_zone_team_entries(zone: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    teams = zone.get("teams", {})
    if isinstance(teams, dict):
        for team in teams.values():
            if isinstance(team, dict):
                yield team
    elif isinstance(teams, list):
        for team in teams:
            if isinstance(team, dict):
                yield team


def sum_metrics(metrics: Dict[str, Any]) -> Dict[str, float]:
    return {
        "armyValue": float(metrics.get("armyValue", 0) or 0),
        "buildPower": float(metrics.get("buildPower", 0) or 0),
        "defensiveValue": float(metrics.get("defensiveValue", 0) or 0),
        "totalUnitValue": float(metrics.get("totalUnitValue", 0) or 0),
        "metalIncome": float(metrics.get("metalIncome", 0) or 0),
        "energyIncome": float(metrics.get("energyIncome", 0) or 0),
        "unitCount": float(metrics.get("unitCount", 0) or 0),
        "combatUnitCount": float(metrics.get("combatUnitCount", 0) or 0),
        "builderUnitCount": float(metrics.get("builderUnitCount", 0) or 0),
        "structureCount": float(metrics.get("structureCount", 0) or 0),
    }


def is_raptorish(side: str, unit_counts: Dict[str, Any], zone_id: str) -> bool:
    side_l = side.lower()
    if "raptor" in side_l or "wild" in side_l:
        return True
    if "HIVE" in zone_id.upper() or "RAPTOR" in zone_id.upper():
        return True
    for name in unit_counts:
        lower = str(name).lower()
        if "raptor" in lower or "hive" in lower:
            return True
    return False


def faction_from_team(team: Dict[str, Any], zone_id: str) -> str:
    # Explicit faction tag wins: the mission seed labels Null Merc and Cortex
    # contractor teams whose start-script side (chassis) would misclassify.
    explicit = str(team.get("faction", "") or "").lower()
    if explicit in ("armada", "cortex", "ashwalkers", "nullmercs", "wild", "neutral"):
        return explicit
    side = str(team.get("side", "") or "").lower()
    unit_counts = team.get("unitCountsByDef", {}) or {}
    if is_raptorish(side, unit_counts, zone_id):
        return "wild"
    if "merc" in side or "null" in side:
        return "nullmercs"
    if "legion" in side or "clan" in side:
        return "ashwalkers"
    if "armada" in side or side == "arm":
        return "armada"
    if "cortex" in side or side == "cor":
        return "cortex"
    return side or "neutral"


def aggregate_zone(zone_id: str, zone: Dict[str, Any]) -> Dict[str, Any]:
    totals = {
        "armyValue": 0.0,
        "buildPower": 0.0,
        "defensiveValue": 0.0,
        "totalUnitValue": 0.0,
        "metalIncome": 0.0,
        "energyIncome": 0.0,
        "unitCount": 0.0,
        "combatUnitCount": 0.0,
        "builderUnitCount": 0.0,
        "structureCount": 0.0,
    }
    faction_presence: Dict[str, float] = {}
    team_snapshots: List[Dict[str, Any]] = []
    has_wild = False
    for team in iter_zone_team_entries(zone):
        metrics = sum_metrics(team.get("metrics", {}) or {})
        unit_counts = dict(team.get("unitCountsByDef", {}) or {})
        faction = faction_from_team(team, zone_id)
        if faction == "wild":
            has_wild = True
        # Territory ownership = defensive value only. Army/build stay on
        # metrics for pressure/economy abstracts; they do not buy the flag.
        presence = metrics["defensiveValue"]
        if presence > 0:
            faction_presence[faction] = faction_presence.get(faction, 0.0) + presence
        for key in totals:
            totals[key] += metrics[key]
        team_snapshots.append({
            "teamId": team.get("teamId"),
            "allyTeamId": team.get("allyTeamId"),
            "side": team.get("side", ""),
            "faction": faction,
            "metrics": metrics,
            "unitCountsByDef": unit_counts,
        })
    controlling = "neutral"
    if faction_presence:
        controlling = max(faction_presence.items(), key=lambda kv: kv[1])[0]
    # Presence for fortification/hazard scaling still tracks DV stack total.
    presence_total = totals["defensiveValue"]
    return {
        "metrics": totals,
        "presence": presence_total,
        "factionPresence": faction_presence,
        "controllingFaction": controlling,
        "teamSnapshots": team_snapshots,
        "hasWild": has_wild,
    }


def abstract_from_raw(map_id: str, zone_id: str, raw: Dict[str, Any], previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    family = map_family(map_id)
    calib = FAMILY_CALIBRATION[family]
    metrics = raw["metrics"]
    presence_div = calib["presenceDivisor"]
    developed = calib["developedPresence"]
    hazard_div = calib["hazardDivisor"]
    faction_count = len([v for v in raw.get("factionPresence", {}).values() if v > 0])
    is_hazard = raw.get("hasWild") or family == "wild" and ("HIVE" in zone_id.upper() or "RAPTOR" in zone_id.upper())
    economy_score = metrics["metalIncome"] * 400.0 + metrics["energyIncome"] * 5.0 + metrics["buildPower"]
    abstract = {
        "baseStrength": clamp((metrics["totalUnitValue"] + metrics["buildPower"]) / developed),
        "militaryPressure": clamp(metrics["armyValue"] / presence_div),
        "fortification": clamp(metrics["defensiveValue"] / presence_div),
        "economyMomentum": clamp(economy_score / developed),
        "hazardPressure": clamp(raw["presence"] / hazard_div) if is_hazard else 0.0,
        "objectiveDamage": 0.0,
        "control": raw["controllingFaction"],
        "instability": clamp(0.35 + 0.15 * max(0, faction_count - 1) + raw["presence"] / (developed * 3.0)),
    }
    if previous:
        abstract["objectiveDamage"] = float(previous.get("abstract", {}).get("objectiveDamage", 0.0) or 0.0)
    return abstract


def apply_objective_results(zone_mem: Dict[str, Any], result: Dict[str, Any]) -> None:
    destroyed = set(result.get("destroyedObjectiveIds", []) or [])
    objective_results = result.get("objectiveResults", []) or []
    objective_state = zone_mem.setdefault("objectiveState", {})
    for item in objective_results:
        if not isinstance(item, dict):
            continue
        oid = item.get("objectiveId") or item.get("id")
        if not oid:
            continue
        objective_state[str(oid)] = {
            "status": item.get("status", "unknown"),
            "damage": float(item.get("damage", 1.0 if item.get("status") in ("destroyed", "complete") else 0.0) or 0.0),
            "updatedAt": utc_now(),
        }
        if item.get("status") in ("destroyed", "complete"):
            destroyed.add(str(oid))
    for oid in destroyed:
        objective_state[str(oid)] = {
            "status": "destroyed",
            "damage": 1.0,
            "updatedAt": utc_now(),
        }
    if objective_state:
        damage_values = [float(v.get("damage", 0.0) or 0.0) for v in objective_state.values()]
        zone_mem["abstract"]["objectiveDamage"] = clamp(sum(damage_values) / max(1, len(damage_values)))


def store_base_snapshot(zone_mem: Dict[str, Any], raw: Dict[str, Any], result: Dict[str, Any]) -> None:
    explicit = result.get("baseSnapshot")
    if explicit:
        zone_mem["baseSnapshot"] = explicit
        return
    snapshots = []
    for team in raw.get("teamSnapshots", []) or []:
        faction = team.get("faction")
        if faction == "wild":
            continue
        metrics = team.get("metrics", {})
        unit_counts = team.get("unitCountsByDef", {}) or {}
        important_units = {
            key: value for key, value in unit_counts.items()
            if value and (metrics.get("structureCount", 0) > 0 or metrics.get("builderUnitCount", 0) > 0 or metrics.get("totalUnitValue", 0) > 0)
        }
        if important_units:
            snapshots.append({
                "teamId": team.get("teamId"),
                "faction": faction,
                "side": team.get("side", ""),
                "metrics": metrics,
                "unitCountsByDef": important_units,
            })
    if snapshots:
        zone_mem["baseSnapshot"] = {
            "snapshotId": "snapshot-{}-{}".format(zone_mem["zoneId"], int(zone_mem.get("lastUpdatedCampaignMinute", 0))),
            "capturedAt": utc_now(),
            "teams": snapshots,
            "rehydrationMode": "approximate",
        }


def update_measured_zone_memory(state: Dict[str, Any], result: Dict[str, Any], telemetry: Optional[Dict[str, Any]], workspace: Path) -> List[str]:
    if not telemetry:
        return []
    if telemetry.get("schemaVersion") != TELEMETRY_SCHEMA:
        raise ValueError("Unexpected telemetry schema: {}".format(telemetry.get("schemaVersion")))
    map_obj = telemetry.get("map", {}) or {}
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or map_obj.get("mapId"))
    state.setdefault("zoneMemory", {}).setdefault(map_id, {})
    measured_zone_ids = []
    for zone_id, zone in iter_zone_entries(telemetry):
        raw = aggregate_zone(zone_id, zone)
        label = zone.get("label", zone_id)
        existing = state["zoneMemory"][map_id].get(zone_id)
        zone_mem = existing or blank_zone_memory(map_id, zone_id, label, raw["controllingFaction"])
        zone_mem["label"] = label
        zone_mem["lastMeasuredRaw"] = {
            "capturedAt": utc_now(),
            "telemetryExportId": telemetry.get("exportId"),
            "matchId": telemetry.get("matchId"),
            "frame": telemetry.get("frame"),
            "presence": raw["presence"],
            "metrics": raw["metrics"],
            "factionPresence": raw["factionPresence"],
        }
        zone_mem["abstract"] = abstract_from_raw(map_id, zone_id, raw, zone_mem)
        zone_mem["controllingFaction"] = zone_mem["abstract"]["control"]
        zone_mem["lastUpdatedCampaignMinute"] = float(state.get("campaignClockMinutes", 0.0))
        zone_mem["hazardPressure"] = zone_mem["abstract"]["hazardPressure"]
        zone_mem["confidence"] = "measured"
        apply_objective_results(zone_mem, result)
        store_base_snapshot(zone_mem, raw, result)
        state["zoneMemory"][map_id][zone_id] = zone_mem
        measured_zone_ids.append(zone_id)
    return measured_zone_ids


def apply_zone_dv(state: Dict[str, Any], result: Dict[str, Any], workspace: Optional[Path] = None) -> List[str]:
    """Presence is defensive value. The gadget reports, per zone, the metal standing in each
    faction's armed structures at the end (result.zoneDv); whoever has the most holds the zone.
    Only zones it reports change hands: a zone with nothing standing is left as it was believed."""
    dv = result.get("zoneDv")
    if not isinstance(dv, dict) or not dv:
        return []
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or "")
    if not map_id:
        return []
    memory = state.setdefault("zoneMemory", {}).setdefault(map_id, {})
    changed = []
    for zone_id, row in dv.items():
        if not isinstance(row, dict):
            continue
        vals = {str(f): float(v or 0) for f, v in row.items()}
        leader, best = max(vals.items(), key=lambda kv: kv[1]) if vals else (None, 0.0)
        if not leader or best <= 0:
            continue
        zid = str(canonical_zone_id(zone_id, workspace) or zone_id)
        before = (memory.get(zid) or {}).get("controllingFaction")
        zone_mem = memory.get(zid) or blank_zone_memory(map_id, zid, zid, leader)
        if before != leader:
            changed.append(zid)
        zone_mem["controllingFaction"] = leader
        zone_mem.setdefault("abstract", {})["control"] = leader
        zone_mem["dv"] = {f: round(v) for f, v in vals.items()}
        memory[zid] = zone_mem
    return changed


def actor_for_zone(state: Dict[str, Any], map_id: str, zone_id: str, zone_mem: Dict[str, Any]) -> str:
    actor = state.get("offscreenActors", {}).get(map_id, {}).get(zone_id)
    if actor:
        return actor
    if map_family(map_id) == "wild" and ("HIVE" in zone_id.upper() or "RAPTOR" in zone_id.upper() or zone_mem.get("hazardPressure", 0) > 0):
        return "RaptorsAI"
    control = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control")
    if control == "ashwalkers":
        return "Ashwalkers"
    if control == "nullmercs":
        return "NullMercsAI"
    if map_family(map_id) == "siege":
        return "SimpleDefenderAI"
    return "SimpleAI"


def offscreen_time_band(
    map_id: str,
    zone_id: str,
    active_map_id: str,
    measured_zones: Iterable[str],
) -> Tuple[str, float]:
    """Return (band_name, rate) for multi-rate offscreen clock.

    live  0.0  — measured on focus map (BAR telemetry is truth)
    near  0.5  — other zones on the focus map
    far   0.25 — all other theaters
    """
    mid = canonical_map_id(map_id)
    active = canonical_map_id(active_map_id)
    measured = set(measured_zones)
    if mid == active and zone_id in measured:
        return "live", TIME_BAND_LIVE_RATE
    if mid == active:
        return "near", TIME_BAND_NEAR_RATE
    return "far", TIME_BAND_FAR_RATE


def bp_access(state: Dict[str, Any]) -> Dict[str, Any]:
    """Concurrent build-power ceiling from Tenebrium access (bank + invested).

    maxPlayerBuildPower = BP_PER_TNB * accessTnb.
    Bank 0 and no living invested stakes => no new build-power units.
    """
    commerce = state.get("commerce") or {}
    bank = int(commerce.get("tenebrium") or 0)
    invested = 0
    # Optional campaign-side stamp of living BP stakes (mission gadget tracks live).
    for rec in (commerce.get("bpInvested") or []) if isinstance(commerce.get("bpInvested"), list) else []:
        if isinstance(rec, dict):
            invested += int(rec.get("tenebrium") or rec.get("amount") or 0)
        else:
            try:
                invested += int(rec)
            except (TypeError, ValueError):
                pass
    if isinstance(commerce.get("bpInvestedTotal"), (int, float)):
        invested = max(invested, int(commerce.get("bpInvestedTotal") or 0))
    access = max(0, bank + invested)
    max_bp = int(BP_PER_TNB * access)
    return {
        "accessTnb": access,
        "bankTnb": bank,
        "investedTnb": invested,
        "bpPerTnb": BP_PER_TNB,
        "maxPlayerBuildPower": max_bp,
        "newBuildersAllowed": access > 0,
        "note": "Concurrent BP ceiling = 150 * (bank + invested). Bank 0 blocks new fabricators.",
    }


def tick_zone(
    zone_mem: Dict[str, Any],
    actor: str,
    map_id: str,
    dt_minutes: float,
    state: Dict[str, Any],
    active: bool = False,
    time_band: str = "far",
    time_rate: float = 1.0,
    activity: Optional[Dict[str, float]] = None,
    bloom: float = 0.0,
) -> None:
    if active or dt_minutes <= 0:
        zone_mem["offscreenEstimate"] = {
            "actor": actor,
            "elapsedMinutes": 0.0,
            "timeBand": time_band if active else time_band,
            "timeRate": 0.0 if active else float(time_rate),
            "expectedPresenceBand": expected_presence_band(map_id, zone_mem),
            "updatedAt": utc_now(),
        }
        if active:
            return
        if dt_minutes <= 0:
            return
    family = map_family(map_id)
    calib = FAMILY_CALIBRATION[family]
    abstract = zone_mem.setdefault("abstract", {})
    for key in ("baseStrength", "militaryPressure", "fortification", "economyMomentum", "hazardPressure", "objectiveDamage", "instability"):
        abstract.setdefault(key, 0.0)

    if actor == "RaptorsAI":
        zid = zone_mem.get("zoneId") or ""
        hazard = state.setdefault("hazardState", {}).setdefault(map_id, {}).setdefault(zid, {
            "pressure": abstract.get("hazardPressure", 0.2),
            "hivesSurviving": True,
            "lastResetAtMinute": state.get("campaignClockMinutes", 0.0),
        })
        if hazard.get("hivesSurviving", True):
            abstract["hazardPressure"] = clamp(max(float(hazard.get("pressure", 0.0)), abstract["hazardPressure"]) + calib["hazardGrowthPerMinute"] * (1.0 + bloom) * dt_minutes)
        else:
            abstract["hazardPressure"] = clamp(abstract["hazardPressure"] + 0.003 * dt_minutes)
        hazard["pressure"] = abstract["hazardPressure"]
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.004 * dt_minutes)
        abstract["instability"] = clamp(max(abstract["instability"], 0.55) + 0.003 * dt_minutes)
        zone_mem["controllingFaction"] = "wild"
        abstract["control"] = "wild"
    elif actor == "SimpleDefenderAI":
        abstract["fortification"] = clamp(abstract["fortification"] + calib["defenderGrowthPerMinute"] * dt_minutes)
        abstract["baseStrength"] = clamp(abstract["baseStrength"] + 0.005 * dt_minutes)
        abstract["economyMomentum"] = clamp(abstract["economyMomentum"] + 0.003 * dt_minutes)
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.0035 * dt_minutes)
    elif actor == "Ashwalkers":
        graph = state.get("graph", {})
        boost = 0.0015 + 0.002 * float(graph.get("q6_independent", 0.25))
        abstract["baseStrength"] = clamp(abstract["baseStrength"] + boost * dt_minutes)
        abstract["economyMomentum"] = clamp(abstract["economyMomentum"] + 0.002 * dt_minutes)
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.0018 * dt_minutes)
        abstract["instability"] = clamp(abstract["instability"] - 0.001 * dt_minutes)
    elif actor == "NullMercsAI":
        # Mercs fight Armada for pay: pressure grows fast, roots grow slowly,
        # and a paid line is never a settled one. Paid lines are written
        # when the ground holds still -- activity carries that temperament.
        mnm = (activity.get("nullmercs", 1.0) if activity else 1.0)
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.006 * mnm * dt_minutes)
        abstract["baseStrength"] = clamp(abstract["baseStrength"] + 0.004 * mnm * dt_minutes)
        abstract["economyMomentum"] = clamp(abstract["economyMomentum"] + 0.003 * mnm * dt_minutes)
        abstract["instability"] = clamp(max(abstract["instability"], 0.45) + 0.002 * dt_minutes)
        zone_mem["controllingFaction"] = "nullmercs"
        abstract["control"] = "nullmercs"
    else:
        growth = calib["simpleGrowthPerMinute"]
        # Armada and Cortex share this branch. Armada's adaptation doctrine
        # rides the swing; Cortex bunkers and scouts -- its entry in
        # `activity` never carries swing, only the wind's pace, so it paces
        # with the weather without ever reacting to it.
        control = abstract.get("control") or zone_mem.get("controllingFaction") or "neutral"
        mult = (activity.get(control, 1.0) if activity and control in ("armada", "cortex") else 1.0)
        abstract["baseStrength"] = clamp(abstract["baseStrength"] + growth * mult * dt_minutes)
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.005 * mult * dt_minutes)
        abstract["economyMomentum"] = clamp(abstract["economyMomentum"] + 0.0045 * mult * dt_minutes)
        abstract["fortification"] = clamp(abstract["fortification"] + 0.0025 * mult * dt_minutes)
    zone_mem["hazardPressure"] = abstract.get("hazardPressure", 0.0)
    zone_mem["lastUpdatedCampaignMinute"] = float(state.get("campaignClockMinutes", 0.0))
    zone_mem["confidence"] = "estimated" if zone_mem.get("confidence") != "measured" else "measured"
    zone_mem["offscreenEstimate"] = {
        "actor": actor,
        "elapsedMinutes": round(float(dt_minutes), 4),
        "timeBand": time_band,
        "timeRate": float(time_rate),
        "expectedPresenceBand": expected_presence_band(map_id, zone_mem),
        "updatedAt": utc_now(),
    }


def expected_presence_band(map_id: str, zone_mem: Dict[str, Any]) -> Dict[str, int]:
    family = map_family(map_id)
    abstract = zone_mem.get("abstract", {})
    developed = FAMILY_CALIBRATION[family]["developedPresence"]
    pressure = max(
        float(abstract.get("baseStrength", 0.0) or 0.0),
        float(abstract.get("militaryPressure", 0.0) or 0.0),
        float(abstract.get("fortification", 0.0) or 0.0),
    )
    center = max(0.0, pressure * developed)
    if family == "wild":
        center = max(center, float(abstract.get("hazardPressure", 0.0) or 0.0) * FAMILY_CALIBRATION[family]["hazardDivisor"])
    return {
        "low": int(max(0, center * 0.65)),
        "center": int(center),
        "high": int(center * 1.35 + 1),
    }


def tick_offscreen_zones(state: Dict[str, Any], active_map_id: str, measured_zones: Iterable[str],
                         dt_minutes: float, workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Advance abstract zones with multi-rate bands. Returns band summary."""
    active_map_id = canonical_map_id(active_map_id)
    measured = set(measured_zones)
    band_counts = {"live": 0, "near": 0, "far": 0}
    activity_by_map = hydrology_activity(state, workspace)
    wind_by_map = hydrology_wind_pace(state, workspace)
    combined_activity = {
        map_id: {faction: value * wind_by_map.get(map_id, 1.0)
                 for faction, value in factions.items()}
        for map_id, factions in activity_by_map.items()
    }
    bloom_by_map = {map_id: float((rec or {}).get("bloom", 0.0))
                    for map_id, rec in (state.get("hydrologyBloom") or {}).items()}
    for map_id, zones in state.setdefault("zoneMemory", {}).items():
        for zone_id, zone_mem in zones.items():
            if not isinstance(zone_mem, dict):
                continue
            zone_mem.setdefault("zoneId", zone_id)
            band, rate = offscreen_time_band(map_id, zone_id, active_map_id, measured)
            band_counts[band] = band_counts.get(band, 0) + 1
            cmid = canonical_map_id(map_id)
            actor = actor_for_zone(state, cmid, zone_id, zone_mem)
            active = band == "live"
            tick_zone(
                zone_mem,
                actor,
                cmid,
                float(dt_minutes) * float(rate),
                state,
                active=active,
                time_band=band,
                time_rate=rate,
                activity=combined_activity.get(cmid),
                bloom=bloom_by_map.get(cmid, 0.0),
            )
    summary = {
        "bands": band_counts,
        "elapsedMinutes": float(dt_minutes),
        "rates": {
            "live": TIME_BAND_LIVE_RATE,
            "near": TIME_BAND_NEAR_RATE,
            "far": TIME_BAND_FAR_RATE,
        },
    }
    state["lastOffscreenTick"] = summary
    return summary


def record_front_event(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    events = state.setdefault("frontEvents", [])
    event = dict(event)
    event.setdefault("atMinute", round(float(state.get("campaignClockMinutes", 0.0)), 2))
    event.setdefault("missionNumber", int(state.get("missionNumber", 1)))
    event.setdefault("at", utc_now())
    events.append(event)
    if len(events) > FRONT_EVENTS_KEEP:
        del events[:-FRONT_EVENTS_KEEP]


def apply_front_decay(state: Dict[str, Any], active_map_id: str, measured_zones: Iterable[str], dt_minutes: float) -> List[Dict[str, Any]]:
    """Neglected Ashwalker ground erodes toward the strongest Armada/Cortex
    presence on the same map; visiting a zone resets its encroachment. The graph
    steers it: a more contested world (q6_contested) erodes faster, and which
    mortal enemy takes the ground is biased by who is ascendant (q0). Returns
    the flip events so callers can surface them."""
    active_map_id = canonical_map_id(active_map_id)
    measured = set(measured_zones)
    graph = state.get("graph", {}) or {}
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)      # 0=Armada, 1=Cortex ascendant
    q6c = float(graph.get("q6_contested", 0.5) or 0.5)
    rate = FRONT_DECAY_RATE * (0.6 + q6c)                       # contested world bites harder
    flips: List[Dict[str, Any]] = []
    for map_id, zones in state.get("zoneMemory", {}).items():
        cmid = canonical_map_id(map_id)
        # Strongest Armada and Cortex presence on this map, tracked separately so
        # the ascendant faction (q0) can claim contested ground.
        pressure = {"armada": 0.0, "cortex": 0.0}
        for z in zones.values():
            ctrl = z.get("controllingFaction") or z.get("abstract", {}).get("control")
            if ctrl in pressure:
                pressure[ctrl] = max(pressure[ctrl], float(z.get("abstract", {}).get("militaryPressure", 0.0) or 0.0))
        enemy_faction, enemy_pressure = None, 0.0
        both = pressure["armada"] >= FRONT_DECAY_MIN_PRESSURE and pressure["cortex"] >= FRONT_DECAY_MIN_PRESSURE
        if both and q0 >= 0.55:
            enemy_faction, enemy_pressure = "cortex", pressure["cortex"]
        elif both and q0 <= 0.45:
            enemy_faction, enemy_pressure = "armada", pressure["armada"]
        else:
            enemy_faction = "cortex" if pressure["cortex"] > pressure["armada"] else "armada"
            enemy_pressure = pressure[enemy_faction]
        for zone_id, zone_mem in zones.items():
            band, band_rate = offscreen_time_band(cmid, zone_id, active_map_id, measured)
            if band == "live":
                zone_mem["encroachment"] = 0.0
                continue
            ctrl = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control")
            if ctrl != "ashwalkers" or not enemy_faction or enemy_pressure < FRONT_DECAY_MIN_PRESSURE:
                continue
            # Multi-rate: far theaters encroach slower than unvisited focus zones.
            enc = float(zone_mem.get("encroachment", 0.0) or 0.0) + enemy_pressure * rate * dt_minutes * float(band_rate)
            if enc >= 1.0:
                zone_mem["encroachment"] = 0.0
                zone_mem["controllingFaction"] = enemy_faction
                zone_mem.setdefault("abstract", {})["control"] = enemy_faction
                flip = {
                    "type": "zone_lost",
                    "mapId": cmid,
                    "zoneId": zone_id,
                    "label": zone_mem.get("label", zone_id),
                    "toFaction": enemy_faction,
                }
                record_front_event(state, flip)
                flips.append(flip)
            else:
                zone_mem["encroachment"] = round(enc, 4)
    return flips


def apply_player_regression(state: Dict[str, Any], active_map_id: str,
                            measured_zones: Iterable[str], dt_minutes: float,
                            workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The Ashwalkers stop being a raiding party for a while: during missions
    REGRESSION_START-REGRESSION_END, held ground on OTHER maps softens
    toward whichever of Armada/NullMercs is locally more active. Paced by
    the same far/near/live time bands apply_front_decay uses, and kept on
    its own accumulator (regressionPressure, never encroachment) so the two
    mechanisms can never fight over the same counter on the same zone."""
    mission_number = int(state.get("missionNumber", 1) or 1)
    if not (REGRESSION_START <= mission_number <= REGRESSION_END):
        return []
    active_map_id = canonical_map_id(active_map_id)
    measured = set(measured_zones)
    activity_by_map = hydrology_activity(state, workspace)
    flips: List[Dict[str, Any]] = []
    for map_id, zones in state.get("zoneMemory", {}).items():
        cmid = canonical_map_id(map_id)
        if cmid == active_map_id:
            continue
        act = activity_by_map.get(cmid, {})
        armada_act = float(act.get("armada", 0.35))
        merc_act = float(act.get("nullmercs", 0.35))
        best_faction = "armada" if armada_act >= merc_act else "nullmercs"
        best_activity = max(armada_act, merc_act)
        for zone_id, zone_mem in zones.items():
            ctrl = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control")
            if ctrl != "ashwalkers":
                continue
            band, band_rate = offscreen_time_band(cmid, zone_id, active_map_id, measured)
            enc = (float(zone_mem.get("regressionPressure", 0.0) or 0.0)
                   + REGRESSION_PRESSURE * best_activity * dt_minutes * float(band_rate))
            if enc >= 1.0:
                zone_mem["regressionPressure"] = 0.0
                zone_mem["controllingFaction"] = best_faction
                zone_mem.setdefault("abstract", {})["control"] = best_faction
                flip = {
                    "type": "zone_regressed",
                    "mapId": cmid,
                    "zoneId": zone_id,
                    "label": zone_mem.get("label", zone_id),
                    "toFaction": best_faction,
                }
                record_front_event(state, flip)
                flips.append(flip)
            else:
                zone_mem["regressionPressure"] = round(enc, 4)
    return flips


def apply_graph_deltas(state: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> Dict[str, float]:
    status = result.get("status", "unknown")
    extraction = result.get("extractionStatus", "")
    path = result.get("pathSignal") or state.get("pathSignal", "B")
    graph = state.setdefault("graph", {})
    for key, default in default_v1_state()["graph"].items():
        graph.setdefault(key, default)
    deltas: Dict[str, float] = {}

    # Credit-table aligned: victory full win, partial hinge, defeat loss.
    # Do not promote partial via destroyedObjectiveIds soup.
    verdict = result.get("verdict") or status
    success = verdict in ("victory", "victoryClean") or status == "victory"
    failure = verdict in ("defeat", "failed", "failure") or status in ("defeat", "failed", "failure")
    partial = verdict in ("partial", "extracted") or status in ("partial", "extracted")

    if success:
        deltas["q6_contested"] = -0.025
        deltas["q6_independent"] = 0.035 if path == "B" else 0.015
    elif partial:
        deltas["q6_contested"] = 0.005
        deltas["q6_independent"] = 0.01 if path == "B" else 0.0
    elif failure:
        deltas["q6_contested"] = 0.04
        deltas["q6_independent"] = -0.025
    else:
        deltas["q6_contested"] = 0.01

    if elapsed > 20:
        deltas["q2_void_structure"] = 0.005
    if path in ("A", "B", "C"):
        deltas["pathSignal" + path] = 0.08 if success else (0.04 if partial else 0.025)

    for key, delta in deltas.items():
        graph[key] = clamp(float(graph.get(key, 0.0) or 0.0) + delta)
    state["pathSignal"] = path
    return deltas


# The graph is a low-pass measurement of the world: one mission eases each
# resurrected axis a quarter of the way toward what the battle export shows.
GRAPH_MEASURE_EASE = 0.25


def world_faction_masses(state: Dict[str, Any]) -> Tuple[Dict[str, float], List[float], List[float], List[float], set]:
    """Measured 'mass' each faction holds across the known world, read from the
    zoneMemory abstract state left by the battle export. A zone's mass is its
    dominant pressure dimension; also returns economy/hazard/instability samples."""
    masses: Dict[str, float] = {}
    eco_vals: List[float] = []
    hazard_vals: List[float] = []
    instab_vals: List[float] = []
    active: set = set()
    for _map_id, zones in state.get("zoneMemory", {}).items():
        for zone_mem in zones.values():
            ab = zone_mem.get("abstract", {}) or {}
            mass = max(
                float(ab.get("baseStrength", 0.0) or 0.0),
                float(ab.get("militaryPressure", 0.0) or 0.0),
                float(ab.get("fortification", 0.0) or 0.0),
            )
            ctrl = zone_mem.get("controllingFaction") or ab.get("control") or "neutral"
            masses[ctrl] = masses.get(ctrl, 0.0) + mass
            if mass > 0.02 and ctrl != "neutral":
                active.add(ctrl)
            eco_vals.append(float(ab.get("economyMomentum", 0.0) or 0.0))
            hazard_vals.append(float(ab.get("hazardPressure", 0.0) or 0.0))
            instab_vals.append(float(ab.get("instability", 0.5) or 0.5))
    return masses, eco_vals, hazard_vals, instab_vals, active


def roster_clan_mass(state: Dict[str, Any]) -> float:
    """The carried warband read as clan military mass in the world (synced,
    bottom-up: the survivors the player keeps ARE the clans' power projection)."""
    roster = state.get("roster", {}) or {}
    cadre = roster.get("cadre", {}) or {}
    n = sum(int(v) for v in cadre.values() if v)
    lvl = int((roster.get("commander") or {}).get("level", 1) or 1)
    return clamp(n * 0.02 + (lvl - 1) * 0.03, 0.0, 0.6)


# ---------------------------------------------------------------------------
# Level 2: the measurement loop. The gadget already builds a Hermitian observable
# of the battlefield (VA_TRANSLATION_PACKET). Here we eigen-decompose it (pure
# stdlib Jacobi) and project the dominant mode onto the q-axes, so the graph is a
# genuine spectral measurement of what was fought, not just a proxy.
# ---------------------------------------------------------------------------

def jacobi_eigen(mat: List[List[float]], max_sweeps: int = 60, tol: float = 1e-12) -> Tuple[List[float], List[List[float]]]:
    """Eigenvalues and eigenvectors of a small real-symmetric matrix via cyclic
    Jacobi rotations (no numpy). Returns (eigenvalues, eigenvectors) where
    eigenvectors[k] is the column vector for eigenvalues[k]. Deterministic."""
    n = len(mat)
    a = [[float(mat[i][j]) for j in range(n)] for i in range(n)]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = sum(a[i][j] * a[i][j] for i in range(n) for j in range(i + 1, n))
        if off <= tol:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-18:
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
                sign = 1.0 if theta >= 0 else -1.0
                t = sign / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    eigenvalues = [a[i][i] for i in range(n)]
    eigenvectors = [[v[i][k] for i in range(n)] for k in range(n)]
    return eigenvalues, eigenvectors


def reconstruct_hermitian(packet: Dict[str, Any]) -> Tuple[Optional[List[List[float]]], List[str]]:
    """Rebuild the (N+1)x(N+1) Hermitian matrix from a VA_TRANSLATION_PACKET:
    node densities on the diagonal, entanglement couplings off-diagonal, plus the
    hydrology anchor row/col. Returns (matrix, zoneIds); (None, []) if empty."""
    nodes = packet.get("nodes", []) or []
    n = len(nodes)
    if n == 0:
        return None, []
    size = n + 1
    h = [[0.0] * size for _ in range(size)]
    ids: List[str] = []
    for i, nd in enumerate(nodes):
        h[i][i] = float(nd.get("density", 0.0) or 0.0)
        hc = float(nd.get("hydroCoupling", 0.0) or 0.0)
        h[i][n] = hc
        h[n][i] = hc
        ids.append(str(nd.get("zoneId", "")))
    hydro = (packet.get("global", {}) or {}).get("hydrology", {}) or {}
    h[n][n] = float(hydro.get("saturation", 0.0) or 0.0)
    for ent in packet.get("entanglements", []) or []:
        zids = ent.get("zoneIds") or []
        if len(zids) == 2 and str(zids[0]) in ids and str(zids[1]) in ids:
            i = ids.index(str(zids[0]))
            j = ids.index(str(zids[1]))
            c = float(ent.get("coupling", 0.0) or 0.0)
            h[i][j] = c
            h[j][i] = c
    return h, ids


def _stdev(values: List[float]) -> float:
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))


def spectral_summary(packet: Dict[str, Any], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Eigen-decompose the battlefield observable and read its dominant mode:
    total energy (trace), participation (how many zones the principal mode spans =
    entanglement breadth), spectral spread (disorder), and the mode's weight on
    each faction's zones."""
    h, ids = reconstruct_hermitian(packet)
    if not h:
        return None
    n = len(ids)
    vals, vecs = jacobi_eigen(h)
    dom = max(range(len(vals)), key=lambda k: vals[k])
    lam = vals[dom]
    vec = vecs[dom]
    zone_w = [vec[i] * vec[i] for i in range(n)]
    total_w = sum(zone_w) or 1e-9
    zone_w = [w / total_w for w in zone_w]
    denom = sum(w * w for w in zone_w) or 1e-9
    part_ratio = (sum(zone_w) ** 2) / denom  # in [1, n]
    participation = clamp((part_ratio - 1.0) / max(1.0, n - 1)) if n > 1 else 0.0
    ctrl_by_zone: Dict[str, str] = {}
    for _m, zones in state.get("zoneMemory", {}).items():
        for zid, zm in zones.items():
            ctrl_by_zone[zid] = zm.get("controllingFaction") or zm.get("abstract", {}).get("control") or "neutral"
    fac: Dict[str, float] = {}
    for i, zid in enumerate(ids):
        f = ctrl_by_zone.get(zid, "neutral")
        fac[f] = fac.get(f, 0.0) + zone_w[i]
    return {
        "dominantEigenvalue": round(lam, 4),
        "energy": round(sum(vals), 4),
        "participation": round(participation, 4),
        "spread": round(clamp(_stdev(vals)), 4),
        "factionWeights": {k: round(v, 4) for k, v in fac.items()},
        "zones": n,
    }


def measure_graph_from_world(state: Dict[str, Any], result: Dict[str, Any], spectral: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Battle export -> graph (the 'collapse' the docstring promises). Eases the
    resurrected axes (q0/q2/q7) toward what the world now measures. When a spectral
    summary of the battlefield observable is present (Level 2), it is blended in as
    a sharper measurement of the active battle. The warband props up clan
    sovereignty (q6_independent) as a non-punishing floor; q6_contested stays on
    its proven outcome heuristic."""
    graph = state.setdefault("graph", {})
    for key, default in default_v1_state()["graph"].items():
        graph.setdefault(key, default)
    masses, eco_vals, hazard_vals, instab_vals, active = world_faction_masses(state)
    clan_mass = masses.get("ashwalkers", 0.0) + roster_clan_mass(state)
    total = sum(masses.values()) + roster_clan_mass(state)
    targets: Dict[str, float] = {}
    armada = masses.get("armada", 0.0)
    cortex = masses.get("cortex", 0.0)
    if armada + cortex > 1e-6:
        targets["q0_armada_cortex"] = clamp(cortex / (armada + cortex))
    if eco_vals:
        targets["q7_resource_scarcity"] = clamp(1.0 - sum(eco_vals) / len(eco_vals))
    # WO-043c: Q7 is the Tenebrium scarcity qubit. Blend live campaign stock
    # (commerce bag + sortie bank) so a dry merc band reads as crisis-scarce.
    commerce = state.get("commerce") or {}
    try:
        tnb_stock = float(commerce.get("tenebrium") or 0)
    except (TypeError, ValueError):
        tnb_stock = 0.0
    try:
        tnb_bank = float((result or {}).get("tenebriumBank") or 0)
    except (TypeError, ValueError):
        tnb_bank = 0.0
    stock = max(tnb_stock, tnb_bank)
    # 0 stock → scarcity ~1.0; 10+ liquid → strong abundance pull.
    tnb_scarce = clamp(1.0 - min(1.0, stock / 10.0))
    if "q7_resource_scarcity" in targets:
        targets["q7_resource_scarcity"] = clamp(0.55 * targets["q7_resource_scarcity"] + 0.45 * tnb_scarce)
    else:
        targets["q7_resource_scarcity"] = tnb_scarce
    # Armada crisis pressure: continent of decoy farmers — keep scarcity elevated.
    if (result or {}).get("armadaTenebriumCrisis") or (state.get("worldFlags") or {}).get("armadaTenebriumCrisis", True):
        targets["q7_resource_scarcity"] = clamp(max(targets["q7_resource_scarcity"], 0.72))
    if instab_vals:
        mean_haz = (sum(hazard_vals) / len(hazard_vals)) if hazard_vals else 0.0
        spread = clamp((len(active) - 1) / 4.0)
        targets["q2_void_structure"] = clamp(0.10 + 0.5 * mean_haz + 0.25 * spread)

    # Level 2: blend the spectral measurement of the battlefield observable into
    # the same axes as a sharper, half-weighted signal (never drives alone).
    spectral_floor_ind = 0.0
    if spectral:
        fw = spectral.get("factionWeights", {}) or {}
        s_arm = float(fw.get("armada", 0.0) or 0.0)
        s_cor = float(fw.get("cortex", 0.0) or 0.0)
        if s_arm + s_cor > 1e-6:
            s_q0 = clamp(s_cor / (s_arm + s_cor))
            targets["q0_armada_cortex"] = 0.5 * targets.get("q0_armada_cortex", s_q0) + 0.5 * s_q0
        s_q2 = clamp(float(spectral.get("spread", 0.0) or 0.0))
        targets["q2_void_structure"] = 0.5 * targets.get("q2_void_structure", s_q2) + 0.5 * s_q2
        spectral_floor_ind = clamp(float(fw.get("ashwalkers", 0.0) or 0.0) * 0.5, 0.0, 0.35)

    measured: Dict[str, Any] = {}
    for key, target in targets.items():
        cur = float(graph.get(key, 0.0) or 0.0)
        graph[key] = round(clamp(cur + (target - cur) * GRAPH_MEASURE_EASE), 4)
        measured[key] = {"target": round(target, 4), "value": graph[key]}
    # Warband floor on clan sovereignty (never drags q6_independent DOWN), plus a
    # spectral floor from the dominant mode's Ashwalker weight. Both monotonic.
    floor = round(max(clamp(clan_mass * 0.5, 0.0, 0.35), spectral_floor_ind), 4)
    if floor > float(graph.get("q6_independent", 0.0) or 0.0):
        graph["q6_independent"] = floor
        measured["q6_independent"] = {"floor": floor, "value": floor}
    return measured

# The player's raid-to-factories transition: ground on other maps softens
# during the window, and (see capture_node_claims.claim_rate_mult) the
# claim that follows presses harder than baseline once it closes.
REGRESSION_START, REGRESSION_END, REGRESSION_PRESSURE = 4, 6, 0.12


__all__ = [
    "GRAPH_MEASURE_EASE",
    "REGRESSION_END",
    "REGRESSION_PRESSURE",
    "REGRESSION_START",
    "_stdev",
    "abstract_from_raw",
    "actor_for_zone",
    "aggregate_zone",
    "apply_front_decay",
    "apply_graph_deltas",
    "apply_objective_results",
    "apply_player_regression",
    "bp_access",
    "expected_presence_band",
    "faction_from_team",
    "get_elapsed_minutes",
    "is_raptorish",
    "iter_zone_entries",
    "iter_zone_team_entries",
    "jacobi_eigen",
    "measure_graph_from_world",
    "offscreen_time_band",
    "reconstruct_hermitian",
    "record_front_event",
    "roster_clan_mass",
    "spectral_summary",
    "store_base_snapshot",
    "sum_metrics",
    "tick_offscreen_zones",
    "tick_zone",
    "update_measured_zone_memory",
    "world_faction_masses",
]
