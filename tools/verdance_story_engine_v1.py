#!/usr/bin/env python3
"""Verdance Story Engine v1.

Measured BAR telemetry collapses into abstract campaign state. The abstract state
then advances offscreen and materializes the next mission intent.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
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

# Display metadata for the War Map (Pillar A). Kept in-engine so the front-end
# has names/descriptors without loading the map pool file.
MAP_DISPLAY = {
    "greenest_fields": ("Greenest Fields", "The Synthesized Utopia"),
    "eye_of_horus": ("Eye of Horus", "The Glassed Core"),
    "koom_valley": ("Koom Valley", "The Fluid Scar"),
    "tabula": ("Tabula", "The Tiered Plateau"),
    "ancient_bastion": ("Ancient Bastion", "Taelith-Armada Citadel"),
    "the_rock_jungle": ("The Rock Jungle", "Limestone Spire Labyrinth"),
    "all_that_simmers": ("All That Simmers", "The High-Conflict Swamp"),
}

# Front decay (Pillar A consequence): an Ashwalker-held zone left unvisited while
# a strong Armada/Cortex presence builds on the same map slowly erodes until it
# flips. Erosion only bites once the offscreen war has actually developed enemy
# military pressure, so a fresh campaign never loses ground prematurely.
FRONT_DECAY_MIN_PRESSURE = 0.35   # enemy militaryPressure on the map must exceed this
FRONT_DECAY_RATE = 0.05           # encroachment gained per (pressure * minute)
FRONT_EVENTS_KEEP = 24

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
        "frontEvents": [],
        # Pillar C: the warband the player carries between missions. The
        # commander is a persistent hero that levels; the cadre is the veteran
        # roster (count-by-type) that grows from survivors and attrites on loss.
        "roster": {
            "commander": {
                "name": "Ash-Captain Vane",
                "unitDef": "legcom",
                "level": 1,
                "xp": 0.0,
                "perks": [],
                "scars": [],
            },
            "cadre": {},
            "cadreCap": 12,
        },
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


# The standing conflict of the campaign world: Null Mercs vs Armada. Armada
# holds the defended ground; the Null Mercs keep one foothold per map (first
# authored flank/edge zone); Cortex survives only as accent pockets around
# explicitly Cortex-named zones. The player's clans thread through that war.
NULLMERC_FOOTHOLD_ROLES = (
    "energy_edge", "flank_pocket", "flank_lane", "causeway", "rim_control",
    "secondary_route", "island_chain", "approach_lane", "crossfire_route",
)


def ensure_zone_memory(state: Dict[str, Any], workspace: Path) -> None:
    zone_maps = zone_maps_from_workspace(workspace)
    zone_memory = state.setdefault("zoneMemory", {})
    actors = state.setdefault("offscreenActors", {})
    hazard_state = state.setdefault("hazardState", {})
    for map_id, zone_map in zone_maps.items():
        zones = zone_memory.setdefault(map_id, {})
        map_actors = actors.setdefault(map_id, {})
        merc_assigned = any(
            (z.get("controllingFaction") or z.get("abstract", {}).get("control")) == "nullmercs"
            for z in zones.values()
        )
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
            elif ("cortex" in role or "synth" in role or "synth" in tags
                  or "CORTEX" in str(zone_id).upper() or "SYNTH" in str(zone_id).upper()):
                # Cortex holds its own maps (synth economies, dealer hideouts).
                # It is the accent power and never garrisons alongside Armada.
                actor = "SimpleAI"
                control = "cortex"
            elif "fortress" in tags or "defense" in tags or "bastion" in tags:
                actor = "SimpleDefenderAI"
                control = "armada"
            elif "defender" in role or "armada" in role:
                actor = "SimpleAI"
                control = "armada"
            elif not merc_assigned and any(r in role for r in NULLMERC_FOOTHOLD_ROLES):
                actor = "NullMercsAI"
                control = "nullmercs"
                merc_assigned = True
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
    if control == "nullmercs":
        return "NullMercsAI"
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
    elif actor == "NullMercsAI":
        # Mercs fight Armada for pay: pressure grows fast, roots grow slowly,
        # and a paid line is never a settled one.
        abstract["militaryPressure"] = clamp(abstract["militaryPressure"] + 0.006 * dt_minutes)
        abstract["baseStrength"] = clamp(abstract["baseStrength"] + 0.004 * dt_minutes)
        abstract["economyMomentum"] = clamp(abstract["economyMomentum"] + 0.003 * dt_minutes)
        abstract["instability"] = clamp(max(abstract["instability"], 0.45) + 0.002 * dt_minutes)
        zone_mem["controllingFaction"] = "nullmercs"
        abstract["control"] = "nullmercs"
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
            active = (cmid == active_map_id and zone_id in measured)
            if active:
                zone_mem["encroachment"] = 0.0
                continue
            ctrl = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control")
            if ctrl != "ashwalkers" or not enemy_faction or enemy_pressure < FRONT_DECAY_MIN_PRESSURE:
                continue
            enc = float(zone_mem.get("encroachment", 0.0) or 0.0) + enemy_pressure * rate * dt_minutes
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
        # Mercs respect winners; a lost field costs standing with the Null line.
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 43)) - 1.0, 0, 100)
        comp["morale"] = clamp(float(comp.get("morale", 70)) - 5, 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 8 + max(0, elapsed - 20) * 0.1, 0, 100)
    else:
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 2, 0, 100)
    return {"reputation": rep, "companion": comp}


# Pillar C: commander progression. XP accrues per sortie; each level unlocks one
# perk the compiler/gadget turns into a tangible starting-force bonus.
ROSTER_XP_PER_LEVEL = 100.0
ROSTER_MAX_LEVEL = 5
PERK_LADDER = {
    2: "field_repair",     # extra starting build power
    3: "veteran_cadre",    # +6 cadre cap
    4: "rapid_deploy",     # one bonus starting unit
    5: "ash_resolve",      # tougher commander
}
CADRE_CAP_BASE = 12


def ensure_roster(state: Dict[str, Any]) -> Dict[str, Any]:
    default = default_v1_state()["roster"]
    roster = state.setdefault("roster", copy.deepcopy(default))
    commander = roster.setdefault("commander", {})
    for key, value in default["commander"].items():
        commander.setdefault(key, copy.deepcopy(value))
    roster.setdefault("cadre", {})
    roster.setdefault("cadreCap", CADRE_CAP_BASE)
    return roster


def roster_level_for_xp(xp: float) -> int:
    return int(min(ROSTER_MAX_LEVEL, 1 + int(max(0.0, xp) // ROSTER_XP_PER_LEVEL)))


def commander_cadre_cap(commander: Dict[str, Any]) -> int:
    cap = CADRE_CAP_BASE
    if "veteran_cadre" in (commander.get("perks") or []):
        cap += 6
    return cap


def expire_scars(commander: Dict[str, Any], mission_number: int) -> None:
    kept = []
    for scar in commander.get("scars", []) or []:
        if int(scar.get("untilMission", 0)) > mission_number:
            kept.append(scar)
    commander["scars"] = kept


def update_roster(state: Dict[str, Any], result: Dict[str, Any], success: bool, clean: bool) -> Dict[str, Any]:
    """Grow the warband from survivors, level the commander, scar it on defeat.
    Backward-compatible: a result without playerSurvivors leaves the cadre as-is."""
    roster = ensure_roster(state)
    commander = roster["commander"]
    status = result.get("status", "unknown")
    defeat = status in ("defeat", "failed", "failure")

    # XP: winning teaches most, a rout still teaches something.
    if success:
        gain = 44.0 + (10.0 if clean else 0.0)
    elif defeat:
        gain = 8.0
    else:
        gain = 16.0
    commander["xp"] = round(float(commander.get("xp", 0.0) or 0.0) + gain, 2)
    new_level = roster_level_for_xp(commander["xp"])
    if new_level > int(commander.get("level", 1)):
        for lvl in range(int(commander.get("level", 1)) + 1, new_level + 1):
            perk = PERK_LADDER.get(lvl)
            if perk and perk not in commander.setdefault("perks", []):
                commander["perks"].append(perk)
        commander["level"] = new_level
    roster["cadreCap"] = commander_cadre_cap(commander)

    # Cadre: survivors carry; a defeat routs most of them.
    survivors = result.get("playerSurvivors")
    if isinstance(survivors, dict) and survivors:
        keep_fraction = 0.4 if defeat else 1.0
        carried: Dict[str, int] = {}
        for unit_def, count in survivors.items():
            kept = int(math.floor(float(count) * keep_fraction))
            if kept > 0:
                carried[str(unit_def)] = kept
        roster["cadre"] = trim_cadre(carried, roster["cadreCap"])
    elif defeat and roster.get("cadre"):
        # No survivor report but a defeat: rout the carried cadre by 40%.
        routed = {d: int(math.floor(c * 0.6)) for d, c in roster["cadre"].items()}
        roster["cadre"] = {d: c for d, c in routed.items() if c > 0}

    # Scars: a lost commander limps into the next sortie (perks suppressed then).
    expire_scars(commander, int(state.get("missionNumber", 1)))
    if defeat:
        commander.setdefault("scars", []).append({
            "kind": "wounded",
            "sinceMission": int(state.get("missionNumber", 1)),
            "untilMission": int(state.get("missionNumber", 1)) + 1,
        })
    return roster


def trim_cadre(cadre: Dict[str, int], cap: int) -> Dict[str, int]:
    total = sum(cadre.values())
    if total <= cap:
        return {d: int(c) for d, c in cadre.items() if c > 0}
    # Proportionally scale down to the cap; deterministic order by unit def.
    scale = cap / float(total)
    trimmed: Dict[str, int] = {}
    for unit_def in sorted(cadre):
        kept = int(math.floor(cadre[unit_def] * scale))
        if kept > 0:
            trimmed[unit_def] = kept
    return trimmed


def commander_active_perks(commander: Dict[str, Any]) -> List[str]:
    """Perks in effect this mission — suppressed while the commander is scarred."""
    if commander.get("scars"):
        return []
    return list(commander.get("perks", []) or [])


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


def dominant_faction(control_counts: Dict[str, int]) -> str:
    """The faction that holds a region for War Map coloring: the strict leader
    among real factions (neutral ignored); ties or empty read as 'contested'."""
    factions = {k: v for k, v in control_counts.items() if k and k != "neutral"}
    if not factions:
        return "neutral"
    ranked = sorted(factions.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "contested"
    return ranked[0][0]


def threat_band(center: float) -> str:
    if center < 4000:
        return "light"
    if center < 9000:
        return "standard"
    if center < 16000:
        return "reinforced"
    return "heavy"


def summarize_front(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """A map's strategic picture from zone memory: who holds it, how hot it is,
    and whether clan ground there is eroding."""
    mid = canonical_map_id(map_id)
    zones = state.get("zoneMemory", {}).get(mid, {})
    control_counts: Dict[str, int] = {}
    threat_center = 0.0
    max_encroach = 0.0
    ashwalker_zones = 0
    for zone_mem in zones.values():
        ctrl = zone_mem.get("controllingFaction") or zone_mem.get("abstract", {}).get("control") or "neutral"
        control_counts[ctrl] = control_counts.get(ctrl, 0) + 1
        if ctrl == "ashwalkers":
            ashwalker_zones += 1
            max_encroach = max(max_encroach, float(zone_mem.get("encroachment", 0.0) or 0.0))
        else:
            band = expected_presence_band(mid, zone_mem)
            threat_center = max(threat_center, float(band.get("center", 0.0)))
    # Dominant enemy faction (ignore player/neutral) for "who's pushing here".
    enemy_counts = {k: v for k, v in control_counts.items() if k in ("armada", "cortex", "nullmercs", "wild")}
    dominant_enemy = max(enemy_counts.items(), key=lambda kv: kv[1])[0] if enemy_counts else None
    name, descriptor = MAP_DISPLAY.get(mid, (mid, ""))
    return {
        "mapId": mid,
        "displayName": name,
        "descriptor": descriptor,
        "family": map_family(mid),
        "controlCounts": control_counts,
        "dominantEnemy": dominant_enemy,
        "threatCenter": int(threat_center),
        "threatBand": threat_band(threat_center),
        "ashwalkerZones": ashwalker_zones,
        "maxEncroachment": round(max_encroach, 3),
        "atRisk": max_encroach >= 0.5,
    }


def consequence_note(front: Dict[str, Any]) -> str:
    """One line on what happens if the player ignores this front."""
    if front.get("atRisk"):
        loser = front.get("dominantEnemy") or "the enemy"
        return "Clan ground here is eroding — leave it and {} takes a zone.".format(loser)
    fam = front.get("family")
    if fam == "wild":
        return "Hives keep multiplying — the hazard only grows the longer it waits."
    dom = front.get("dominantEnemy")
    if dom == "armada":
        return "Armada keeps entrenching — every mission skipped means heavier walls."
    if dom == "cortex":
        return "The Cortex works keep humming — their economy compounds untouched."
    if dom == "nullmercs":
        return "The mercs hold, but an unpaid line drifts if you never show."
    return "Pressure keeps building here while your attention is elsewhere."


def enumerate_front_targets(state: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
    """2-4 candidate fronts the player can choose between. The ALPHA_SPINE map
    for the current mission number is always offered (recommended); the rest are
    the most salient alternatives (eroding clan ground first, then hottest)."""
    number = int(state.get("missionNumber", 1))
    spine_map, _ = ALPHA_SPINE[(number - 1) % len(ALPHA_SPINE)]
    limit = max(2, min(limit, len(ALPHA_SPINE)))
    fronts = []
    for map_id, deploy_zone in ALPHA_SPINE:
        front = summarize_front(state, map_id)
        objective = objective_for_map(map_id, state)
        front["deploymentZoneId"] = deploy_zone
        front["objective"] = {"kind": objective.get("kind"), "label": objective.get("label")}
        front["recommended"] = (map_id == spine_map)
        front["consequenceIfIgnored"] = consequence_note(front)
        fronts.append(front)
    spine = [f for f in fronts if f["recommended"]]
    others = [f for f in fronts if not f["recommended"]]
    # Salience: eroding clan ground first, then hottest enemy presence. Stable
    # tie-break on mapId keeps output deterministic for tests.
    others.sort(key=lambda f: (f["atRisk"], f["threatCenter"], f["mapId"]), reverse=True)
    return spine + others[: max(0, limit - len(spine))]


def build_war_map(state: Dict[str, Any]) -> Dict[str, Any]:
    """The strategic snapshot the console renders during the next-ready pause:
    faction control per region, the offered fronts, and recent territory swings."""
    regions = []
    for map_id, _ in ALPHA_SPINE:
        front = summarize_front(state, map_id)
        front["control"] = dominant_faction(front.get("controlCounts", {}))
        regions.append(front)
    return {
        "schemaVersion": "verdance-war-map/1.0",
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "missionNumber": int(state.get("missionNumber", 1)),
        "generatedAt": utc_now(),
        "regions": regions,
        "candidates": enumerate_front_targets(state),
        "frontEvents": list(state.get("frontEvents", []))[-6:],
        "reputation": dict(state.get("reputation", {}) or {}),
        "voidThreat": round(float(state.get("graph", {}).get("q2_void_structure", 0.0) or 0.0), 3),
        "graph": {k: round(float(v), 3) for k, v in (state.get("graph", {}) or {}).items() if isinstance(v, (int, float))},
        "worldReading": world_reading(state.get("graph", {}) or {}),
        "pendingChoice": state.get("nextMapOverride"),
    }


def world_reading(graph: Dict[str, Any]) -> List[str]:
    """Plain-English readout of the quantum graph for the War Map header."""
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)
    q2 = float(graph.get("q2_void_structure", 0.0) or 0.0)
    q6c = float(graph.get("q6_contested", 0.5) or 0.5)
    q6i = float(graph.get("q6_independent", 0.0) or 0.0)
    q7 = float(graph.get("q7_resource_scarcity", 0.0) or 0.0)
    lines = []
    if q0 >= 0.6:
        lines.append("Cortex is ascendant across the front.")
    elif q0 <= 0.4:
        lines.append("Armada holds the upper hand.")
    else:
        lines.append("Armada and Cortex are deadlocked.")
    lines.append(("The line-world is tearing apart." if q6c > 0.7 else "The front is holding, for now.") )
    if q6i >= 0.45:
        lines.append("Ashwalker sovereignty is rising.")
    elif q6i <= 0.2:
        lines.append("The clans are a fringe force.")
    if q7 > 0.85:
        lines.append("Tenebrium is all but gone — scarcity bites.")
    if q2 > 0.5:
        lines.append("The void is bleeding through — verge zones destabilizing.")
    return lines


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


# ---------------------------------------------------------------------------
# Ketha voice: data-driven, deterministic dialogue selection.
# Lines live in data/story/ketha_voice.json so the community can retune the
# voice without touching engine code. Selection is hash-seeded (campaign +
# mission + pool) so the same campaign moment always says the same thing.
# ---------------------------------------------------------------------------

FALLBACK_VOICE = {
    "speaker": "ketha",
    "pools": {
        "debrief.victory": ["Done is done. Mark the map and move."],
        "debrief.partial": ["Not a win. Not a loss. A hinge."],
        "debrief.defeat": ["We lost ground, not the thread. But the thread is thinner."],
    },
    "titles": {},
}

_VOICE_CACHE: Dict[str, Dict[str, Any]] = {}


def load_ketha_voice(workspace: Optional[Path]) -> Dict[str, Any]:
    if workspace is None:
        return FALLBACK_VOICE
    key = str(workspace)
    if key in _VOICE_CACHE:
        return _VOICE_CACHE[key]
    path = Path(workspace) / "data" / "story" / "ketha_voice.json"
    voice = FALLBACK_VOICE
    if path.exists():
        try:
            data = load_json(path)
            if isinstance(data, dict) and isinstance(data.get("pools"), dict):
                voice = data
        except (json.JSONDecodeError, OSError):
            pass
    _VOICE_CACHE[key] = voice
    return voice


def pick_line(voice: Dict[str, Any], pool_key: str, *seed_parts: Any) -> Optional[str]:
    pool = voice.get("pools", {}).get(pool_key) or []
    if not pool:
        return None
    digest = hashlib.sha256("|".join([pool_key] + [str(p) for p in seed_parts]).encode("utf-8")).digest()
    return str(pool[digest[0] % len(pool)])


def pick_title(voice: Dict[str, Any], map_id: str, *seed_parts: Any) -> Optional[str]:
    titles = voice.get("titles", {}).get(map_id) or []
    if not titles:
        return None
    digest = hashlib.sha256("|".join([map_id, "title"] + [str(p) for p in seed_parts]).encode("utf-8")).digest()
    return str(titles[digest[0] % len(titles)])


def result_streak(state: Dict[str, Any]) -> Tuple[str, int]:
    """Return (kind, length) of the trailing victory/defeat streak in history."""
    history = state.get("history", []) or []
    streak_kind = ""
    streak = 0
    for bead in reversed(history):
        status = str(bead.get("status", ""))
        kind = "win" if status == "victory" else ("loss" if status in ("defeat", "failed", "failure") else "")
        if not kind:
            break
        if streak_kind and kind != streak_kind:
            break
        streak_kind = kind
        streak += 1
    return streak_kind, streak


def generate_briefing(state: Dict[str, Any], voice: Dict[str, Any], map_id: str, family: str,
                      objective: Dict[str, Any], pressure: Dict[str, Any]) -> Dict[str, Any]:
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1))
    graph = state.get("graph", {})
    comp = state.get("companion", {})
    lines: List[Dict[str, str]] = []

    def add(pool_key: str, tag: str) -> None:
        text = pick_line(voice, pool_key, *seed)
        if text:
            lines.append({"speaker": voice.get("speaker", "ketha"), "text": text, "tag": tag})

    add("briefing.family." + family, "situation")
    add("briefing.objective." + str(objective.get("kind", "")), "objective")

    # The standing war line: Null Mercs vs Armada is the main conflict, and
    # Ketha reads the mercs by reputation - allied guns or wary neighbors.
    rep = state.get("reputation", {})
    merc_rep = float(rep.get("nullmercs", 43) or 0)
    add("briefing.war.mercs_allied" if merc_rep >= 40 else "briefing.war.mercs_wary", "war")

    # Pillar D: Ketha reacts to the emergent world. A wounded commander and the
    # extremes of the Armada/Cortex axis each earn a line when they hold.
    if (state.get("roster", {}).get("commander", {}) or {}).get("scars"):
        add("briefing.commander.scarred", "warband")
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)
    if q0 >= 0.62:
        add("briefing.world.cortex_ascendant", "world")
    elif q0 <= 0.38:
        add("briefing.world.armada_ascendant", "world")

    # One conditional line: highest-priority campaign pressure wins.
    conditions = [
        (float(comp.get("stress", 0) or 0) >= 40, "briefing.companion.high_stress"),
        (pressure.get("maxHazard", 0) > 0.5, "briefing.hazard.rising"),
        (pressure.get("maxFortification", 0) > 0.55, "briefing.fortress.pressure"),
        (float(graph.get("q7_resource_scarcity", graph.get("q7_scarcity", 0)) or 0) > 0.85, "briefing.graph.scarcity_high"),
        (float(graph.get("q6_contested", 0) or 0) > 0.7, "briefing.graph.contested_high"),
        (float(graph.get("q6_independent", 0) or 0) > 0.45, "briefing.graph.independent_rising"),
        (float(comp.get("morale", 0) or 0) >= 75, "briefing.companion.high_morale"),
    ]
    for triggered, pool_key in conditions:
        if triggered:
            add(pool_key, "pressure")
            break

    add("briefing.path." + str(state.get("pathSignal", "B")), "path")
    return {"lines": lines}


def generate_debrief_candidates(state: Dict[str, Any], voice: Dict[str, Any]) -> Dict[str, str]:
    """Outcome-keyed lines embedded in the mission seed so the in-game HUD can
    react to the terminal state without waiting for campaign advancement."""
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1), "debrief")
    candidates = {}
    for key, pool in [
        ("victory", "debrief.victory"),
        ("victoryClean", "debrief.victory_clean"),
        ("partial", "debrief.partial"),
        ("defeat", "debrief.defeat"),
        ("defeatCommander", "debrief.defeat_commander"),
        ("objectiveDestroyed", "debrief.objective_destroyed"),
    ]:
        text = pick_line(voice, pool, *seed)
        if text:
            candidates[key] = text
    return candidates


def merc_foothold_scale(reputation: float) -> float:
    """How much Null Merc presence stands with you, scaled by standing. Allied
    lines (>=40) field a fuller foothold; wary lines show up thin."""
    if reputation >= 40.0:
        return round(clamp(0.85 + (reputation - 40.0) / 60.0 * 0.5, 0.85, 1.35), 3)
    # Wary lines stay strictly below the allied floor: alliance is a clean step up.
    return round(clamp(0.55 + reputation / 40.0 * 0.25, 0.55, 0.8), 3)


def build_roster_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    roster = ensure_roster(state)
    commander = roster["commander"]
    return {
        "commander": {
            "name": commander.get("name"),
            "unitDef": commander.get("unitDef", "legcom"),
            "level": int(commander.get("level", 1)),
            "xp": round(float(commander.get("xp", 0.0) or 0.0), 1),
            "perks": list(commander.get("perks", []) or []),
            "activePerks": commander_active_perks(commander),
            "scarred": bool(commander.get("scars")),
        },
        "cadre": {str(d): int(c) for d, c in (roster.get("cadre") or {}).items() if c},
        "cadreCap": int(roster.get("cadreCap", CADRE_CAP_BASE)),
        "availableAllies": available_allies(state),
    }


def available_allies(state: Dict[str, Any]) -> List[str]:
    """Who will stand with the clans, read from the graph + reputation. The
    ascendant mortal enemy sheds defectors; a courted merc line shows up."""
    graph = state.get("graph", {}) or {}
    rep = state.get("reputation", {}) or {}
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)
    allies = ["ashwalkers"]
    if float(rep.get("nullmercs", 0) or 0) >= 40:
        allies.append("nullmercs")
    if q0 >= 0.6:
        allies.append("cortex_defectors")
    elif q0 <= 0.4:
        allies.append("armada_deserters")
    return allies


def materialize_next_intent(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    ensure_roster(state)
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
    voice = load_ketha_voice(workspace)
    title = pick_title(voice, map_id, state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1))
    rep = state.get("reputation", {}) or {}
    merc_rep = float(rep.get("nullmercs", 43) or 43)
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
        "title": title,
        "briefing": generate_briefing(state, voice, map_id, family, objective, pressure),
        "debriefCandidates": generate_debrief_candidates(state, voice),
        "storyTags": intent_story_tags(map_id, family, pressure),
        "persistentBaseRehydrate": rehydrate,
        "offscreenPressureSummary": pressure,
        "roster": build_roster_intent(state),
        "worldConflict": {
            "primaryEnemy": "armada",
            "accentFaction": "cortex",
            "nullMercs": {
                "reputation": round(merc_rep, 1),
                "alliedWithPlayer": merc_rep >= 40.0,
                "footholdScale": merc_foothold_scale(merc_rep),
                "footholdZoneIds": [
                    zid for zid, z in zones.items()
                    if (z.get("controllingFaction") or z.get("abstract", {}).get("control")) == "nullmercs"
                ],
            },
        },
        "expectedEnemyScale": expected_map_enemy_scale(state, map_id),
        "hazardPolicy": "escalating_reset" if family == "wild" else "none",
        "economy": {
            "difficultyCoefficient": round(1.0 + float(state.get("graph", {}).get("q6_contested", 0.5)) * 0.25, 3),
            "resourceModifier": round(clamp(1.15 - float(state.get("graph", {}).get("q7_resource_scarcity", 0.0) or 0.0) * 0.35, 0.8, 1.15), 3),
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


def generate_story_events(state: Dict[str, Any], result: Dict[str, Any], bead: Optional[Dict[str, Any]],
                          processed: bool, workspace: Optional[Path] = None) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    if not processed:
        events.append({
            "kind": "warning",
            "tags": ["duplicate-result"],
            "text": "Duplicate result skipped; campaign state was not mutated.",
        })
    else:
        voice = load_ketha_voice(workspace)
        tags = bead.get("storyTags", []) if bead else []
        status = str(result.get("status", "unknown"))
        seed = (state.get("campaignId", CAMPAIGN_ID), result.get("missionId", "va_unknown"), status)

        # Primary debrief line: most specific matching pool wins.
        pool_key = "debrief.victory"
        if status in ("defeat", "failed", "failure"):
            pool_key = "debrief.defeat_commander" if result.get("terminalReason") == "commander_lost" else "debrief.defeat"
        elif status in ("partial", "extracted"):
            pool_key = "debrief.partial"
        elif result.get("destroyedObjectiveIds"):
            pool_key = "debrief.objective_destroyed"
        elif any(str(t).startswith("extract-clean") for t in tags):
            pool_key = "debrief.victory_clean"
        text = pick_line(voice, pool_key, *seed) or "The map gave us a measurement. Now it starts lying again."
        events.append({
            "kind": "dialogue",
            "speaker": voice.get("speaker", "ketha"),
            "tone": "field",
            "text": text,
            "tags": tags,
        })

        # Pillar D: Ketha names the ground the campaign lost to front decay while
        # the player was elsewhere ({zone} interpolated from the latest flip).
        if "territory-lost" in tags:
            lost = [e for e in state.get("frontEvents", []) if e.get("type") == "zone_lost"]
            if lost:
                zone_label = lost[-1].get("label") or lost[-1].get("zoneId") or "a foothold"
                line = pick_line(voice, "debrief.territory_lost", *seed)
                if line:
                    events.append({"kind": "dialogue", "speaker": voice.get("speaker", "ketha"),
                                   "tone": "grim", "text": line.replace("{zone}", str(zone_label)),
                                   "tags": ["territory-lost", str(lost[-1].get("zoneId", ""))]})

        # Streak commentary: the line notices runs of results.
        streak_kind, streak_len = result_streak(state)
        if streak_len >= 3 and streak_kind == "win":
            streak_text = pick_line(voice, "debrief.streak.wins", *seed)
            if streak_text:
                events.append({"kind": "dialogue", "speaker": voice.get("speaker", "ketha"),
                               "tone": "reflective", "text": streak_text, "tags": ["streak", "wins-" + str(streak_len)]})
        elif streak_len >= 2 and streak_kind == "loss":
            streak_text = pick_line(voice, "debrief.streak.losses", *seed)
            if streak_text:
                events.append({"kind": "dialogue", "speaker": voice.get("speaker", "ketha"),
                               "tone": "reflective", "text": streak_text, "tags": ["streak", "losses-" + str(streak_len)]})

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


def process_result(state: Dict[str, Any], result: Dict[str, Any], telemetry: Optional[Dict[str, Any]], workspace: Path, translation: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    state = migrate_state(state)
    ensure_zone_memory(state, workspace)
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or (telemetry or {}).get("map", {}).get("mapId"))
    elapsed = get_elapsed_minutes(result, telemetry, map_id)
    key = result_key(result)
    processed = key not in state.setdefault("processedResults", {})
    if not processed:
        intent = materialize_next_intent(state, workspace)
        events = generate_story_events(state, result, None, False, workspace)
        return state, {"processed": False, "reason": "duplicate", "resultKey": key}, intent, events

    old_clock = float(state.get("campaignClockMinutes", 0.0) or 0.0)
    state["campaignClockMinutes"] = round(old_clock + elapsed, 4)
    measured_zones = update_measured_zone_memory(state, result, telemetry, workspace)
    graph_delta = apply_graph_deltas(state, result, elapsed)
    apply_reputation_companion(state, result, elapsed)
    clean_extract = result.get("extractionStatus", "") in ("clean", "success")
    success = result.get("status") == "victory" or clean_extract or bool(result.get("destroyedObjectiveIds"))
    update_roster(state, result, success, clean_extract)
    # Battle export dictates the graph: collapse the measured world (incl. the
    # carried warband) and, when present, the eigen-decomposed battlefield
    # observable onto the resurrected q-axes.
    spectral = spectral_summary(translation, state) if translation else None
    if spectral:
        state["lastSpectral"] = spectral
    graph_measured = measure_graph_from_world(state, result, spectral)
    update_destroyed_objectives(state, result)
    reset_live_raptors_but_escalate(state, result, elapsed)
    tick_offscreen_zones(state, map_id, measured_zones, elapsed)
    front_flips = apply_front_decay(state, map_id, measured_zones, elapsed)
    bead = append_history_bead(state, result, elapsed, graph_delta)
    if front_flips:
        bead.setdefault("storyTags", []).append("territory-lost")
    state["processedResults"][key] = {
        "processedAt": bead["timestamp"],
        "beadIndex": len(state["history"]) - 1,
        "elapsedMinutes": elapsed,
    }
    result_number = int(result.get("missionNumber", state.get("missionNumber", 1)))
    state["missionNumber"] = max(int(state.get("missionNumber", 1)) + 1, result_number + 1)
    state["currentMissionId"] = mission_id(state["missionNumber"])
    # The map choice is spent once its mission has been played; clear it so the
    # next mission falls back to the spine (or a fresh War Map pick).
    state.pop("nextMapOverride", None)
    intent = materialize_next_intent(state, workspace)
    events = generate_story_events(state, result, bead, True, workspace)
    report = {
        "processed": True,
        "resultKey": key,
        "elapsedMinutes": elapsed,
        "campaignClockMinutes": state["campaignClockMinutes"],
        "measuredZones": measured_zones,
        "graphDelta": graph_delta,
        "graphMeasured": graph_measured,
        "spectral": spectral,
        "bead": bead,
    }
    return state, report, intent, events


def command_advance(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    result_path = Path(args.result) if args.result else workspace / "inbox" / "latest_va_result.json"
    telemetry_path = Path(args.telemetry) if args.telemetry else workspace / "outbox" / "bar_zone_telemetry.latest.json"
    translation_path = Path(args.translation) if getattr(args, "translation", "") else workspace / "inbox" / "latest_va_translation.json"
    outdir = Path(args.outdir) if args.outdir else workspace / "outbox"
    state_raw = load_json(state_path) if state_path.exists() else default_v1_state()
    result = load_json(result_path)
    telemetry = load_json(telemetry_path) if telemetry_path.exists() else None
    translation = load_json(translation_path) if translation_path.exists() else None
    state, report, intent, events = process_result(state_raw, result, telemetry, workspace, translation)

    if args.write_state:
        if state_path.exists() and state_raw.get("schemaVersion") != STATE_SCHEMA:
            backup = state_path.with_suffix(state_path.suffix + ".pre_v1_backup")
            if not backup.exists():
                backup.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
        save_json(state_path, state)
    save_json(outdir / "advance_report.v1.json", report)
    save_json(outdir / "next_mission_intent.json", intent)
    save_json(outdir / "story_events.latest.json", events)
    save_json(outdir / "war_map.json", build_war_map(state))
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
    intent = materialize_next_intent(state, workspace)
    save_json(outdir / "next_mission_intent.json", intent)
    save_json(outdir / "war_map.json", build_war_map(state))
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
    adv.add_argument("--translation", default="")
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
