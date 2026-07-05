#!/usr/bin/env python3
"""Verdance Story Engine v1.

Measured BAR telemetry collapses into abstract campaign state. The abstract state
then advances offscreen and materializes the next mission intent.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


CAMPAIGN_ID = "verdance_ashes"
STATE_SCHEMA = "verdance-campaign-state/1.0"
RESULT_SCHEMA = "verdance-match-result/1.0"
INTENT_SCHEMA = "verdance-mission-intent/1.0"
EVENTS_SCHEMA = "verdance-story-events/1.0"
TELEMETRY_SCHEMA = "bar-zone-telemetry/1.0"

MAP_FAMILIES = {
    "greenest_fields": "economy",
    "eye_of_horus": "tempo",
    "koom_valley": "tempo",
    "tabula": "tempo",
    "ancient_bastion": "siege",
    "the_rock_jungle": "wild",
    "rock_jungle": "wild",
    "all_that_simmers": "wild",
}

MAP_ALIASES = {
    "rock_jungle": "the_rock_jungle",
}

ALPHA_SPINE = [
    ("greenest_fields", "GF_NW_GREEN_START"),
    ("eye_of_horus", "EOH_NW_CRATER_CAMP"),
    ("koom_valley", "KOOM_NW_GREEN_SHELF"),
    ("tabula", "TAB_NW_PLATEAU"),
    ("ancient_bastion", "AB_WESTERN_MUSTER_GROUNDS"),
    ("the_rock_jungle", "RJ_NW_JUNGLE_SHELF"),
    ("all_that_simmers", "ATS_NW_CANOPY_START"),
]

FAMILY_CALIBRATION = {
    "tempo": {
        "presenceDivisor": 6000.0,
        "developedPresence": 24000.0,
        "hazardDivisor": 50000.0,
        "defaultElapsedMinutes": 12.0,
        "simpleGrowthPerMinute": 0.006,
        "defenderGrowthPerMinute": 0.004,
        "hazardGrowthPerMinute": 0.0,
    },
    "economy": {
        "presenceDivisor": 8000.0,
        "developedPresence": 30000.0,
        "hazardDivisor": 50000.0,
        "defaultElapsedMinutes": 12.0,
        "simpleGrowthPerMinute": 0.007,
        "defenderGrowthPerMinute": 0.004,
        "hazardGrowthPerMinute": 0.0,
    },
    "siege": {
        "presenceDivisor": 10000.0,
        "developedPresence": 30000.0,
        "hazardDivisor": 50000.0,
        "defaultElapsedMinutes": 20.0,
        "simpleGrowthPerMinute": 0.005,
        "defenderGrowthPerMinute": 0.008,
        "hazardGrowthPerMinute": 0.0,
    },
    "wild": {
        "presenceDivisor": 6000.0,
        "developedPresence": 26000.0,
        "hazardDivisor": 250000.0,
        "defaultElapsedMinutes": 20.0,
        "simpleGrowthPerMinute": 0.004,
        "defenderGrowthPerMinute": 0.003,
        "hazardGrowthPerMinute": 0.012,
    },
}

TEST_WON_CALIBRATION_REFS = {
    "campaign_ai_packet": "_outbox/20260704_151709_campaign_ai_baseline_packet",
    "authored_long_survey": "reports/map_surveys/authored_long_zone_development_all7.md",
    "notes": [
        "Early active bases: 3000-6000 presence.",
        "Developed sortie-scale bases: 10000-30000 presence.",
        "Wild/hive pressure is separated from normal army value.",
        "Human objectives should be smaller than full AI wipeout thresholds.",
    ],
}


def utc_now() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def load_json(path: Path) -> Any:
    # utf-8-sig tolerates the BOM that PowerShell 5.1 Out-File prepends.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False), encoding="utf-8")


def canonical_map_id(map_id: Optional[str]) -> str:
    if not map_id:
        return "unknown"
    lower = str(map_id).strip().lower()
    return MAP_ALIASES.get(lower, lower)


def map_family(map_id: str) -> str:
    return MAP_FAMILIES.get(canonical_map_id(map_id), "tempo")


def result_key(result: Dict[str, Any]) -> str:
    if result.get("resultKey"):
        return str(result["resultKey"])
    return "{}|{}|{}|{}".format(
        result.get("campaignId", CAMPAIGN_ID),
        result.get("missionId", "va_unknown"),
        int(result.get("missionNumber", 1)),
        result.get("status", "unknown"),
    )


def mission_id(number: int) -> str:
    return "va_{:03d}".format(int(number))


def default_v1_state() -> Dict[str, Any]:
    return {
        "schemaVersion": STATE_SCHEMA,
        "campaignId": CAMPAIGN_ID,
        "missionNumber": 1,
        "currentMissionId": "va_001",
        "pathSignal": "B",
        "campaignClockMinutes": 0.0,
        "graph": {
            "q0_armada_cortex": 0.77,
            "q2_void_structure": 0.15,
            "q6_contested": 0.85,
            "q6_independent": 0.24,
            "q7_resource_scarcity": 0.98,
            "pathSignalA": 0.0,
            "pathSignalB": 0.1,
            "pathSignalC": 0.0,
        },
        "reputation": {
            "armada": 42,
            "cortex": 21,
            "clans": 50,
            "nullmercs": 43,
            "sev": 50,
        },
        "companion": {
            "id": "ketha",
            "name": "Ketha",
            "xp": 0.0,
            "morale": 70,
            "loyalty": 75,
            "stress": 12,
        },
        "history": [],
        "processedResults": {},
        "zoneMemory": {},
        "offscreenActors": {},
        "destroyedObjectives": {},
        "persistentBaseSnapshots": {},
        "hazardState": {},
        "calibrationRefs": copy.deepcopy(TEST_WON_CALIBRATION_REFS),
    }


def migrate_state(raw: Dict[str, Any]) -> Dict[str, Any]:
    if raw.get("schemaVersion") == STATE_SCHEMA:
        state = copy.deepcopy(raw)
    else:
        state = default_v1_state()
        state["campaignId"] = raw.get("campaignId", CAMPAIGN_ID)
        state["missionNumber"] = int(raw.get("missionNumber", 1))
        state["currentMissionId"] = raw.get("currentMissionId", mission_id(state["missionNumber"]))
        state["pathSignal"] = raw.get("pathSignal", "B")
        old_graph = raw.get("graph", {}) or {}
        graph = state["graph"]
        for key, value in old_graph.items():
            target = "q7_resource_scarcity" if key == "q7_scarcity" else key
            graph[target] = float(value)
        state["reputation"].update(raw.get("reputation", {}) or {})
        old_comp = raw.get("companion", {}) or {}
        if old_comp:
            state["companion"].update(old_comp)
            if "displayName" in old_comp and "name" not in old_comp:
                state["companion"]["name"] = old_comp["displayName"]
        state["history"] = list(raw.get("history", []) or [])
        state["legacyState"] = {
            "schemaVersion": raw.get("schemaVersion", "unknown"),
            "migratedAt": utc_now(),
        }

    for key, value in default_v1_state().items():
        if key not in state:
            state[key] = copy.deepcopy(value)
    state["schemaVersion"] = STATE_SCHEMA
    return state


def zone_maps_from_workspace(workspace: Path) -> Dict[str, Dict[str, Any]]:
    zone_dir = workspace / "data" / "zone_maps" / "authored"
    maps: Dict[str, Dict[str, Any]] = {}
    if not zone_dir.exists():
        return maps
    for path in zone_dir.glob("*.json"):
        try:
            data = load_json(path)
        except Exception:
            continue
        mid = canonical_map_id(data.get("mapId"))
        if mid != "unknown":
            maps[mid] = data
    return maps


def ensure_zone_memory(state: Dict[str, Any], workspace: Path) -> None:
    zone_maps = zone_maps_from_workspace(workspace)
    zone_memory = state.setdefault("zoneMemory", {})
    actors = state.setdefault("offscreenActors", {})
    hazard_state = state.setdefault("hazardState", {})
    for map_id, zone_map in zone_maps.items():
        zones = zone_memory.setdefault(map_id, {})
        map_actors = actors.setdefault(map_id, {})
        for zone in zone_map.get("zones", []) or []:
            zone_id = zone.get("zoneId")
            if not zone_id:
                continue
            tags = set(str(t).lower() for t in zone.get("tags", []) or [])
            role = str(zone.get("role", "")).lower()
            if "raptors" in tags or "wilds" in tags or "hive" in role or "raptor" in role:
                actor = "RaptorsAI"
                control = "wild"
            elif "start" in tags and ("legion" in role or "player" in role):
                actor = "Ashwalkers"
                control = "ashwalkers"
            elif "fortress" in tags or "defense" in tags or "bastion" in tags:
                actor = "SimpleDefenderAI"
                control = "armada"
            else:
                actor = "SimpleAI"
                control = "neutral"
            map_actors.setdefault(zone_id, actor)
            if zone_id not in zones:
                zones[zone_id] = blank_zone_memory(map_id, zone_id, zone.get("label", zone_id), control)
            if actor == "RaptorsAI":
                hazard_state.setdefault(map_id, {}).setdefault(zone_id, {
                    "pressure": zones[zone_id]["abstract"].get("hazardPressure", 0.2),
                    "hivesSurviving": True,
                    "lastResetAtMinute": state.get("campaignClockMinutes", 0.0),
                })


def blank_zone_memory(map_id: str, zone_id: str, label: str, control: str) -> Dict[str, Any]:
    return {
        "mapId": map_id,
        "zoneId": zone_id,
        "label": label,
        "lastMeasuredRaw": {},
        "abstract": {
            "baseStrength": 0.0,
            "militaryPressure": 0.0,
            "fortification": 0.0,
            "economyMomentum": 0.0,
            "hazardPressure": 0.0,
            "objectiveDamage": 0.0,
            "control": control,
            "instability": 0.5,
        },
        "lastUpdatedCampaignMinute": 0.0,
        "controllingFaction": control,
        "objectiveState": {},
        "baseSnapshot": {},
        "hazardPressure": 0.0,
        "confidence": "estimated",
    }


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
    side = str(team.get("side", "") or "").lower()
    unit_counts = team.get("unitCountsByDef", {}) or {}
    if is_raptorish(side, unit_counts, zone_id):
        return "wild"
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
        presence = metrics["armyValue"] + metrics["buildPower"] + metrics["defensiveValue"]
        if presence <= 0:
            presence = metrics["totalUnitValue"]
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
    presence_total = totals["armyValue"] + totals["buildPower"] + totals["defensiveValue"]
    if presence_total <= 0:
        presence_total = totals["totalUnitValue"]
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


def actor_for_zone(state: Dict[str, Any], map_id: str, zone_id: str, zone_mem: Dict[str, Any]) -> str:
    actor = state.get("offscreenActors", {}).get(map_id, {}).get(zone_id)
    if actor:
        return actor
    if map_family(map_id) == "wild" and ("HIVE" in zone_id.upper() or "RAPTOR" in zone_id.upper() or zone_mem.get("hazardPressure", 0) > 0):
        return "RaptorsAI"
    control = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control")
    if control == "ashwalkers":
        return "Ashwalkers"
    if map_family(map_id) == "siege":
        return "SimpleDefenderAI"
    return "SimpleAI"


def tick_zone(zone_mem: Dict[str, Any], actor: str, map_id: str, dt_minutes: float, state: Dict[str, Any], active: bool = False) -> None:
    if active:
        return
    family = map_family(map_id)
    calib = FAMILY_CALIBRATION[family]
    abstract = zone_mem.setdefault("abstract", {})
    for key in ("baseStrength", "militaryPressure", "fortification", "economyMomentum", "hazardPressure", "objectiveDamage", "instability"):
        abstract.setdefault(key, 0.0)

    if actor == "RaptorsAI":
        hazard = state.setdefault("hazardState", {}).setdefault(map_id, {}).setdefault(zone_mem["zoneId"], {
            "pressure": abstract.get("hazardPressure", 0.2),
            "hivesSurviving": True,
            "lastResetAtMinute": state.get("campaignClockMinutes", 0.0),
        })
        if hazard.get("hivesSurviving", True):
            abstract["hazardPressure"] = clamp(max(float(hazard.get("pressure", 0.0)), abstract["hazardPressure"]) + calib["hazardGrowthPerMinute"] * dt_minutes)
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
    else:
        growth = calib["simpleGrowthPerMinute"]
        abstract["baseStrength"] = clamp(abstract["baseStrength"] + growth * dt_minutes)
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.005 * dt_minutes)
        abstract["economyMomentum"] = clamp(abstract["economyMomentum"] + 0.0045 * dt_minutes)
        abstract["fortification"] = clamp(abstract["fortification"] + 0.0025 * dt_minutes)
    zone_mem["hazardPressure"] = abstract.get("hazardPressure", 0.0)
    zone_mem["lastUpdatedCampaignMinute"] = float(state.get("campaignClockMinutes", 0.0))
    zone_mem["confidence"] = "estimated" if zone_mem.get("confidence") != "measured" else "measured"
    zone_mem["offscreenEstimate"] = {
        "actor": actor,
        "elapsedMinutes": dt_minutes,
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


def tick_offscreen_zones(state: Dict[str, Any], active_map_id: str, measured_zones: Iterable[str], dt_minutes: float) -> None:
    active_map_id = canonical_map_id(active_map_id)
    measured = set(measured_zones)
    for map_id, zones in state.setdefault("zoneMemory", {}).items():
        for zone_id, zone_mem in zones.items():
            active = (canonical_map_id(map_id) == active_map_id and zone_id in measured)
            actor = actor_for_zone(state, canonical_map_id(map_id), zone_id, zone_mem)
            tick_zone(zone_mem, actor, canonical_map_id(map_id), dt_minutes, state, active=active)


def apply_graph_deltas(state: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> Dict[str, float]:
    status = result.get("status", "unknown")
    extraction = result.get("extractionStatus", "")
    path = result.get("pathSignal") or state.get("pathSignal", "B")
    graph = state.setdefault("graph", {})
    for key, default in default_v1_state()["graph"].items():
        graph.setdefault(key, default)
    deltas: Dict[str, float] = {}

    objective_results = result.get("objectiveResults", []) or []
    completed = any(isinstance(x, dict) and x.get("status") in ("complete", "destroyed") for x in objective_results)
    destroyed = bool(result.get("destroyedObjectiveIds"))
    success = status == "victory" or extraction in ("clean", "success") or completed or destroyed
    failure = status in ("defeat", "failed", "failure")
    partial = status in ("partial", "extracted") and not success

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
        deltas["pathSignal" + path] = 0.08 if success else 0.025

    for key, delta in deltas.items():
        graph[key] = clamp(float(graph.get(key, 0.0) or 0.0) + delta)
    state["pathSignal"] = path
    return deltas


def apply_reputation_companion(state: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> Dict[str, Any]:
    status = result.get("status", "unknown")
    extraction = result.get("extractionStatus", "")
    rep = state.setdefault("reputation", {})
    comp = state.setdefault("companion", {})
    for key, default in default_v1_state()["reputation"].items():
        rep.setdefault(key, default)
    for key, default in default_v1_state()["companion"].items():
        comp.setdefault(key, default)
    clean_extract = extraction in ("clean", "success")
    success = status == "victory" or clean_extract or bool(result.get("destroyedObjectiveIds"))
    if success:
        rep["clans"] = clamp(float(rep.get("clans", 50)) + 2.0, 0, 100)
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 43)) + 1.0, 0, 100)
        comp["xp"] = clamp(float(comp.get("xp", 0)) + 0.04, 0, 99)
        comp["morale"] = clamp(float(comp.get("morale", 70)) + (4 if clean_extract else 2), 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) - (5 if clean_extract else 1), 0, 100)
    elif status in ("defeat", "failed", "failure"):
        rep["clans"] = clamp(float(rep.get("clans", 50)) - 2.0, 0, 100)
        comp["morale"] = clamp(float(comp.get("morale", 70)) - 5, 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 8 + max(0, elapsed - 20) * 0.1, 0, 100)
    else:
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 2, 0, 100)
    return {"reputation": rep, "companion": comp}


def update_destroyed_objectives(state: Dict[str, Any], result: Dict[str, Any]) -> None:
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId"))
    if map_id == "unknown":
        return
    destroyed = state.setdefault("destroyedObjectives", {}).setdefault(map_id, {})
    zone_id = result.get("deploymentZoneId") or "unknown_zone"
    for oid in result.get("destroyedObjectiveIds", []) or []:
        destroyed[str(oid)] = {
            "objectiveId": str(oid),
            "zoneId": zone_id,
            "destroyedAtMinute": state.get("campaignClockMinutes", 0.0),
            "status": "destroyed",
        }


def reset_live_raptors_but_escalate(state: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> None:
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId"))
    if map_family(map_id) != "wild":
        return
    hazard_map = state.setdefault("hazardState", {}).setdefault(map_id, {})
    destroyed = set(result.get("destroyedObjectiveIds", []) or [])
    for zone_id, hazard in hazard_map.items():
        hive_destroyed = any(zone_id.lower() in str(oid).lower() or "hive" in str(oid).lower() for oid in destroyed)
        if hive_destroyed:
            hazard["hivesSurviving"] = False
            hazard["pressure"] = clamp(float(hazard.get("pressure", 0.0)) * 0.55)
        else:
            hazard["pressure"] = clamp(float(hazard.get("pressure", 0.0)) + 0.01 * elapsed)
        hazard["liveUnitsReset"] = True
        hazard["lastResetAtMinute"] = state.get("campaignClockMinutes", 0.0)


def append_history_bead(state: Dict[str, Any], result: Dict[str, Any], elapsed: float, graph_delta: Dict[str, float]) -> Dict[str, Any]:
    bead = {
        "missionId": result.get("missionId", state.get("currentMissionId", "va_unknown")),
        "missionNumber": int(result.get("missionNumber", state.get("missionNumber", 1))),
        "status": result.get("status", "unknown"),
        "mapId": canonical_map_id(result.get("deploymentMapId") or result.get("mapId")),
        "deploymentZoneId": result.get("deploymentZoneId"),
        "extractionStatus": result.get("extractionStatus"),
        "extractionZoneId": result.get("extractionZoneId"),
        "elapsedMinutes": elapsed,
        "pathSignal": result.get("pathSignal") or state.get("pathSignal", "B"),
        "graphDelta": graph_delta,
        "destroyedObjectiveIds": list(result.get("destroyedObjectiveIds", []) or []),
        "storyTags": story_tags_for_result(result, graph_delta),
        "timestamp": utc_now(),
    }
    state.setdefault("history", []).append(bead)
    return bead


def story_tags_for_result(result: Dict[str, Any], graph_delta: Dict[str, float]) -> List[str]:
    tags = [str(result.get("status", "unknown"))]
    if result.get("extractionStatus"):
        tags.append("extract-" + str(result["extractionStatus"]))
    if result.get("destroyedObjectiveIds"):
        tags.append("objective-destroyed")
    if result.get("pathSignal"):
        tags.append("path-" + str(result["pathSignal"]).lower())
    if graph_delta.get("q6_independent", 0) > 0:
        tags.append("ashwalker-gain")
    return tags


def objective_for_map(map_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    mid = canonical_map_id(map_id)
    destroyed = state.get("destroyedObjectives", {}).get(mid, {})
    if mid == "ancient_bastion":
        candidates = [
            ("AB_LRPC_EAST_WING", "Destroy the eastern LRPC"),
            ("AB_OUTER_WALL_NORTH", "Break the northern bastion wing"),
            ("AB_SHIELD_RELAY", "Collapse the shield relay"),
        ]
        for oid, label in candidates:
            if oid not in destroyed:
                return {"id": oid, "kind": "destroy_key_structure", "label": label, "targetZoneId": "AB_EASTERN_BASTION_WALL"}
    if mid == "the_rock_jungle":
        return {"id": "RJ_HIVE_CAUSEWAY", "kind": "hive_clear_or_bypass", "label": "Break a hive or hold a causeway", "targetZoneId": "RJ_CENTRAL_LAGOON_MAZE"}
    if mid == "all_that_simmers":
        return {"id": "ATS_HIVE_OR_FACTION_TARGET", "kind": "choose_target_then_extract", "label": "Choose Armada, Cortex, or hive pressure target", "targetZoneId": "ATS_CENTRAL_HIVE_FLATS"}
    if mid == "greenest_fields":
        return {"id": "GF_SYNTH_ECONOMY_NODE", "kind": "economy_disrupt", "label": "Disrupt the southeast synth economy", "targetZoneId": "GF_SE_SYNTH_START"}
    if mid == "eye_of_horus":
        return {"id": "EOH_CORTEX_DEALER_RELAY", "kind": "strike_relay", "label": "Destroy the Cortex dealer relay", "targetZoneId": "EOH_SE_CORTEX_POCKET"}
    if mid == "koom_valley":
        return {"id": "KOOM_FLUID_SCAR_FOOTHOLD", "kind": "seize_lane", "label": "Seize the Central Fluid Scar", "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR"}
    if mid == "tabula":
        return {"id": "TAB_ROCK_GATE_CONTROL", "kind": "gate_control", "label": "Control a rock gate and extract", "targetZoneId": "TAB_WESTERN_ROCK_GATES"}
    return {"id": mid + "_objective", "kind": "sortie", "label": "Complete local objective", "targetZoneId": None}


def choose_next_map_zone(state: Dict[str, Any]) -> Tuple[str, str]:
    requested = state.get("nextMapOverride")
    if requested:
        return canonical_map_id(requested.get("mapId")), requested.get("deploymentZoneId", "unknown_zone")
    number = int(state.get("missionNumber", 1))
    return ALPHA_SPINE[(number - 1) % len(ALPHA_SPINE)]


def zone_pressure_summary(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    zones = state.get("zoneMemory", {}).get(map_id, {})
    if not zones:
        return {"maxHazard": 0.0, "maxFortification": 0.0, "maxMilitary": 0.0, "zones": []}
    bits = []
    max_hazard = 0.0
    max_fort = 0.0
    max_mil = 0.0
    for zone_id, zone in zones.items():
        abstract = zone.get("abstract", {})
        max_hazard = max(max_hazard, float(abstract.get("hazardPressure", 0.0) or 0.0))
        max_fort = max(max_fort, float(abstract.get("fortification", 0.0) or 0.0))
        max_mil = max(max_mil, float(abstract.get("militaryPressure", 0.0) or 0.0))
        bits.append({
            "zoneId": zone_id,
            "label": zone.get("label", zone_id),
            "control": abstract.get("control", zone.get("controllingFaction")),
            "confidence": zone.get("confidence", "estimated"),
            "expectedPresenceBand": expected_presence_band(map_id, zone),
            "abstract": {
                "baseStrength": round(float(abstract.get("baseStrength", 0.0)), 3),
                "militaryPressure": round(float(abstract.get("militaryPressure", 0.0)), 3),
                "fortification": round(float(abstract.get("fortification", 0.0)), 3),
                "hazardPressure": round(float(abstract.get("hazardPressure", 0.0)), 3),
            },
        })
    bits.sort(key=lambda item: item["expectedPresenceBand"]["center"], reverse=True)
    return {
        "maxHazard": round(max_hazard, 3),
        "maxFortification": round(max_fort, 3),
        "maxMilitary": round(max_mil, 3),
        "zones": bits[:6],
    }


def extraction_zone_for(map_id: str, deployment_zone: str) -> str:
    if map_id == "ancient_bastion":
        return "AB_WESTERN_MUSTER_GROUNDS"
    if map_id == "the_rock_jungle":
        return "RJ_NW_JUNGLE_SHELF"
    if map_id == "all_that_simmers":
        return "ATS_NW_CANOPY_START"
    return deployment_zone


def materialize_next_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    map_id, deploy_zone = choose_next_map_zone(state)
    objective = objective_for_map(map_id, state)
    pressure = zone_pressure_summary(state, map_id)
    zones = state.get("zoneMemory", {}).get(map_id, {})
    rehydrate = []
    for zone_id, zone in zones.items():
        snapshot = zone.get("baseSnapshot")
        if snapshot:
            rehydrate.append({
                "zoneId": zone_id,
                "control": zone.get("controllingFaction"),
                "snapshot": snapshot,
            })
    family = map_family(map_id)
    return {
        "schemaVersion": INTENT_SCHEMA,
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "missionId": state.get("currentMissionId", mission_id(int(state.get("missionNumber", 1)))),
        "missionNumber": int(state.get("missionNumber", 1)),
        "mapId": map_id,
        "deploymentZoneId": deploy_zone,
        "extractionZoneId": extraction_zone_for(map_id, deploy_zone),
        "objective": objective["kind"],
        "objectiveTarget": objective,
        "storyTags": intent_story_tags(map_id, family, pressure),
        "persistentBaseRehydrate": rehydrate,
        "offscreenPressureSummary": pressure,
        "expectedEnemyScale": expected_map_enemy_scale(state, map_id),
        "hazardPolicy": "escalating_reset" if family == "wild" else "none",
        "economy": {
            "difficultyCoefficient": round(1.0 + float(state.get("graph", {}).get("q6_contested", 0.5)) * 0.25, 3),
        },
        "environment": {
            "mapFamily": family,
            "campaignClockMinutes": round(float(state.get("campaignClockMinutes", 0.0)), 2),
        },
        "dialogueHooks": intent_story_tags(map_id, family, pressure),
        "storyReason": story_reason_for_intent(map_id, family, pressure),
    }


def expected_map_enemy_scale(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    zones = state.get("zoneMemory", {}).get(map_id, {})
    bands = [expected_presence_band(map_id, z) for z in zones.values()]
    if not bands:
        return {"low": 3000, "center": 6000, "high": 10000, "basis": "default_no_zone_memory"}
    return {
        "low": int(sum(b["low"] for b in bands)),
        "center": int(sum(b["center"] for b in bands)),
        "high": int(sum(b["high"] for b in bands)),
        "basis": "zone_memory_abstract_state",
    }


def intent_story_tags(map_id: str, family: str, pressure: Dict[str, Any]) -> List[str]:
    tags = [family, map_id]
    if family == "wild":
        tags.append("extract-before-overrun")
    if pressure.get("maxFortification", 0) > 0.55:
        tags.append("fortress-pressure")
    if pressure.get("maxHazard", 0) > 0.5:
        tags.append("hazard-rising")
    return tags


def story_reason_for_intent(map_id: str, family: str, pressure: Dict[str, Any]) -> str:
    if map_id == "ancient_bastion":
        return "Bastion defenses have continued developing offscreen; strike one key wing and extract before counterpressure peaks."
    if family == "wild":
        return "Wild pressure resets live units between sorties, but surviving hives have escalated the zone hazard."
    if family == "economy":
        return "Economy state is the current campaign bottleneck; disrupt or secure converter momentum."
    return "Current graph pressure favors a short objective sortie over full map conquest."


def generate_story_events(state: Dict[str, Any], result: Dict[str, Any], bead: Optional[Dict[str, Any]], processed: bool) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    if not processed:
        events.append({
            "kind": "warning",
            "tags": ["duplicate-result"],
            "text": "Duplicate result skipped; campaign state was not mutated.",
        })
    else:
        tags = bead.get("storyTags", []) if bead else []
        text = "The map gave us a measurement. Now it starts lying again."
        if "objective-destroyed" in tags:
            text = "That target stays gone. The rest of the front will learn around the hole."
        elif any(str(t).startswith("extract-clean") for t in tags):
            text = "Clean exit. That matters more than the scorch marks."
        elif result.get("status") in ("defeat", "failed", "failure"):
            text = "We lost ground, not the thread. But the thread is thinner."
        events.append({
            "kind": "dialogue",
            "speaker": "ketha",
            "tone": "field",
            "text": text,
            "tags": tags,
        })
        events.append({
            "kind": "mission_hook",
            "tags": ["next-intent"],
            "text": "Next mission intent materialized from measured and offscreen campaign state.",
        })
    return {
        "schemaVersion": EVENTS_SCHEMA,
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "generatedAt": utc_now(),
        "events": events,
    }


def process_result(state: Dict[str, Any], result: Dict[str, Any], telemetry: Optional[Dict[str, Any]], workspace: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    state = migrate_state(state)
    ensure_zone_memory(state, workspace)
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or (telemetry or {}).get("map", {}).get("mapId"))
    elapsed = get_elapsed_minutes(result, telemetry, map_id)
    key = result_key(result)
    processed = key not in state.setdefault("processedResults", {})
    if not processed:
        intent = materialize_next_intent(state)
        events = generate_story_events(state, result, None, False)
        return state, {"processed": False, "reason": "duplicate", "resultKey": key}, intent, events

    old_clock = float(state.get("campaignClockMinutes", 0.0) or 0.0)
    state["campaignClockMinutes"] = round(old_clock + elapsed, 4)
    measured_zones = update_measured_zone_memory(state, result, telemetry, workspace)
    graph_delta = apply_graph_deltas(state, result, elapsed)
    apply_reputation_companion(state, result, elapsed)
    update_destroyed_objectives(state, result)
    reset_live_raptors_but_escalate(state, result, elapsed)
    tick_offscreen_zones(state, map_id, measured_zones, elapsed)
    bead = append_history_bead(state, result, elapsed, graph_delta)
    state["processedResults"][key] = {
        "processedAt": bead["timestamp"],
        "beadIndex": len(state["history"]) - 1,
        "elapsedMinutes": elapsed,
    }
    result_number = int(result.get("missionNumber", state.get("missionNumber", 1)))
    state["missionNumber"] = max(int(state.get("missionNumber", 1)) + 1, result_number + 1)
    state["currentMissionId"] = mission_id(state["missionNumber"])
    intent = materialize_next_intent(state)
    events = generate_story_events(state, result, bead, True)
    report = {
        "processed": True,
        "resultKey": key,
        "elapsedMinutes": elapsed,
        "campaignClockMinutes": state["campaignClockMinutes"],
        "measuredZones": measured_zones,
        "graphDelta": graph_delta,
        "bead": bead,
    }
    return state, report, intent, events


def command_advance(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    result_path = Path(args.result) if args.result else workspace / "inbox" / "latest_va_result.json"
    telemetry_path = Path(args.telemetry) if args.telemetry else workspace / "outbox" / "bar_zone_telemetry.latest.json"
    outdir = Path(args.outdir) if args.outdir else workspace / "outbox"
    state_raw = load_json(state_path) if state_path.exists() else default_v1_state()
    result = load_json(result_path)
    telemetry = load_json(telemetry_path) if telemetry_path.exists() else None
    state, report, intent, events = process_result(state_raw, result, telemetry, workspace)

    if args.write_state:
        if state_path.exists() and state_raw.get("schemaVersion") != STATE_SCHEMA:
            backup = state_path.with_suffix(state_path.suffix + ".pre_v1_backup")
            if not backup.exists():
                backup.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
        save_json(state_path, state)
    save_json(outdir / "advance_report.v1.json", report)
    save_json(outdir / "next_mission_intent.json", intent)
    save_json(outdir / "story_events.latest.json", events)
    print(json.dumps(report, indent=2))
    return 0


def command_intent(args: argparse.Namespace) -> int:
    """Materialize next_mission_intent.json from campaign state alone (no result needed)."""
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    outdir = Path(args.outdir) if args.outdir else workspace / "outbox"
    raw = load_json(state_path) if state_path.exists() else default_v1_state()
    state = migrate_state(raw)
    ensure_zone_memory(state, workspace)
    intent = materialize_next_intent(state)
    save_json(outdir / "next_mission_intent.json", intent)
    print(json.dumps({"missionId": intent.get("missionId"), "mapId": intent.get("mapId"), "objective": intent.get("objective")}, indent=2))
    return 0


def command_init_state(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    raw = load_json(state_path) if state_path.exists() else default_v1_state()
    state = migrate_state(raw)
    ensure_zone_memory(state, workspace)
    if args.write_state:
        if state_path.exists() and raw.get("schemaVersion") != STATE_SCHEMA:
            backup = state_path.with_suffix(state_path.suffix + ".pre_v1_backup")
            if not backup.exists():
                backup.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
        save_json(state_path, state)
    print(json.dumps({"schemaVersion": state["schemaVersion"], "zoneMaps": len(state.get("zoneMemory", {})), "writeState": bool(args.write_state)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verdance Story Engine v1")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-state")
    init.add_argument("--workspace", default=str(Path.home() / "Documents" / "BAR_Verdance_Workspace"))
    init.add_argument("--state", default="")
    init.add_argument("--write-state", action="store_true")
    init.set_defaults(func=command_init_state)

    intent = sub.add_parser("intent")
    intent.add_argument("--workspace", default=str(Path.home() / "Documents" / "BAR_Verdance_Workspace"))
    intent.add_argument("--state", default="")
    intent.add_argument("--outdir", default="")
    intent.set_defaults(func=command_intent)

    adv = sub.add_parser("advance")
    adv.add_argument("--workspace", default=str(Path.home() / "Documents" / "BAR_Verdance_Workspace"))
    adv.add_argument("--state", default="")
    adv.add_argument("--result", default="")
    adv.add_argument("--telemetry", default="")
    adv.add_argument("--outdir", default="")
    adv.add_argument("--write-state", action="store_true")
    adv.set_defaults(func=command_advance)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
