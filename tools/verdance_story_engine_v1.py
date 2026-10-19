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
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from commerce_delivery_v1 import delivery_eta, make_pending_delivery, resolve_listing_delivery
except ImportError:  # pragma: no cover
    from tools.commerce_delivery_v1 import (  # type: ignore
        delivery_eta,
        make_pending_delivery,
        resolve_listing_delivery,
    )


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

# Deploy pads are quiet rim (or migrate to quiet rim). Never midfield unowned ground.
# Greenest: north desert (GF_NE_PLATEAU) is the standard shell-free infil/exfil.
ALPHA_SPINE = [
    ("greenest_fields", "GF_NE_PLATEAU"),
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

# Multi-rate offscreen clock (v0.8.4): live BAR is truth on measured zones;
# unmeasured focus zones tick at NEAR rate; other maps at FAR rate.
TIME_BAND_LIVE_RATE = 0.0
TIME_BAND_NEAR_RATE = 0.5
TIME_BAND_FAR_RATE = 0.25

# Concurrent build-power ceiling from Tenebrium access (bank + invested stakes).
BP_PER_TNB = 150

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
    # Preserve the pre-narrative save on its first write. Projection alone does
    # not migrate files or create backups.
    if path.name == "campaign_state.json" and path.exists() and isinstance(obj, dict) and obj.get("narrative"):
        previous = path.read_bytes()
        if not json.loads(previous.decode("utf-8-sig")).get("narrative"):
            backup = path.parent / "backups" / "pre_narrative"
            backup.mkdir(parents=True, exist_ok=True)
            import hashlib
            (backup / (hashlib.sha256(previous).hexdigest()[:16] + ".json")).write_bytes(previous)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False), encoding="utf-8")


def canonical_map_id(map_id: Optional[str]) -> str:
    if not map_id:
        return "unknown"
    lower = str(map_id).strip().lower()
    return MAP_ALIASES.get(lower, lower)


def map_family(map_id: str) -> str:
    return MAP_FAMILIES.get(canonical_map_id(map_id), "tempo")


# ---------------------------------------------------------------------------
# Crafted map pool (data/map_pool/seven_maps.json): the authored per-map faction
# infrastructure (campaignForces) + economy heuristics. This is the crafted
# world the owner designed - Greenest Fields as an Armada solar/wind utopia, a
# touch of Null Merc, no Cortex - and the mission generator now reads it instead
# of guessing faction from zone names.
# ---------------------------------------------------------------------------

_MAP_POOL_CACHE: Dict[str, Dict[str, Any]] = {}

# campaignForces uses a compact composition grammar: a space-separated list of
# <letter><count> tokens. M=mex, So=solar, Wi=wind, D=defense. "So6 Wi4 D2"
# means 6 solar, 4 wind, 2 defense.
_INFRA_TOKENS = {"M": "mex", "So": "solar", "Wi": "wind", "D": "defense"}


def parse_campaign_forces(spec: Optional[str]) -> Dict[str, int]:
    """Parse a compact 'So6 Wi4 D2' composition string into a count dict."""
    counts = {"mex": 0, "solar": 0, "wind": 0, "defense": 0}
    if not spec:
        return counts
    for token in str(spec).split():
        for prefix, key in _INFRA_TOKENS.items():
            if token.startswith(prefix) and token[len(prefix):].isdigit():
                counts[key] = int(token[len(prefix):])
                break
    return counts


def load_map_pool(workspace: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Map id -> crafted pool entry. Cached per workspace; empty if unavailable."""
    if workspace is None:
        return {}
    key = str(workspace)
    if key in _MAP_POOL_CACHE:
        return _MAP_POOL_CACHE[key]
    path = Path(workspace) / "data" / "map_pool" / "seven_maps.json"
    pool: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        try:
            data = load_json(path)
            for entry in data.get("maps", []) if isinstance(data, dict) else []:
                mid = canonical_map_id(entry.get("id"))
                pool[mid] = entry
        except (json.JSONDecodeError, OSError):
            pass
    _MAP_POOL_CACHE[key] = pool
    return pool


def zone_infrastructure_for(map_id: str, workspace: Optional[Path]) -> Dict[str, Any]:
    """The crafted faction infrastructure + economy heuristics for a map, shaped
    for the compiler: per-faction parsed composition plus the raw strings so the
    generator (and a future visualizer) can render the authored world."""
    mid = canonical_map_id(map_id)
    entry = load_map_pool(workspace).get(mid, {})
    forces = entry.get("campaignForces", {}) or {}
    parsed = {
        "armada": parse_campaign_forces(forces.get("ARM")),
        "nullmercs": parse_campaign_forces(forces.get("NMC")),
        "cortex": parse_campaign_forces(forces.get("COR")),
    }
    # The map's primary defending faction: whoever holds authored economy here.
    if parsed["cortex"] and any(parsed["cortex"].values()) and not any(parsed["armada"].values()):
        primary = "cortex"
    elif any(parsed["armada"].values()):
        primary = "armada"
    else:
        primary = "armada"
    return {
        "descriptor": entry.get("descriptor"),
        "heuristics": entry.get("heuristics", {}),
        "campaignForces": forces,
        "parsed": parsed,
        "primaryFaction": primary,
    }


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
        # v0.8.3: Armada cold; Cortex wants customers (~70). Live saves not rewritten.
        "reputation": {
            "armada": 18,
            "cortex": 70,
            "nullmercs": 48.0,
            "sev": 50,
        },
        # Ashwalker home territory — Rock Jungle PvE (raids elsewhere harvest Tnb).
        "sessionHomeMap": "the_rock_jungle",
        "sessionMode": "same_map",
        "homeCamp": {
            "level": 0,
            "mapId": "the_rock_jungle",
            "label": "Jungle shelf camp",
        },
        "flags": {
            "homeClearReady": False,
            "homeCleared": False,
        },
        "characters": {
            # Sheet xp stays small so ensure_roster does not scale Pavise into L4 (Hardened = BAR ~0.45).
            "pavise": { "id": "pavise", "name": "Pavise", "faction": "ashwalkers", "unitDef": "armwar", "xp": 40, "player": True, "home": None, "status": "active", "wounds": 0, "scars": [] },
            "vane": { "id": "vane", "name": "Ash-Captain Vane", "faction": "ashwalkers", "unitDef": "legcen", "xp": 1480, "player": False, "home": None, "status": "locked", "wounds": 0, "scars": [] },
            "ketha": { "id": "ketha", "name": "Ketha", "faction": "ashwalkers", "unitDef": "legrezbot", "xp": 1120, "player": True, "home": None, "status": "active", "wounds": 0, "scars": [] },
            "anselm": { "id": "anselm", "name": "Broker Anselm Rue", "faction": "nullmercs", "unitDef": "legcen", "xp": 1900, "player": False, "home": ["greenest_fields", "GF_CENTRAL_OPEN_GRASSLAND"], "status": "active", "wounds": 0, "scars": [] },
            "grath": { "id": "grath", "name": "Grath Arrears", "faction": "nullmercs", "unitDef": "legkark", "xp": 2400, "player": False, "home": ["koom_valley", "KOOM_WEST_RIDGE_POCKET"], "status": "active", "wounds": 0, "scars": [] },
            "halq": { "id": "halq", "name": "Sisu Halq", "faction": "nullmercs", "unitDef": "legbal", "xp": 1350, "player": False, "home": ["the_rock_jungle", "RJ_WESTERN_CAUSEWAY"], "status": "active", "wounds": 0, "scars": [] },
            "brask": { "id": "brask", "name": "Line-Captain Odell Brask", "faction": "armada", "unitDef": "armcom", "xp": 1600, "player": False, "home": ["greenest_fields", "GF_SE_ENERGY_WORKS"], "status": "active", "wounds": 0, "scars": [] },
            "solvang": { "id": "solvang", "name": "Warden-Marshal Teir Solvang", "faction": "armada", "unitDef": "armcom", "xp": 3100, "player": False, "home": ["ancient_bastion", "AB_EASTERN_BASTION_WALL"], "status": "active", "wounds": 0, "scars": [] },
            "voren": { "id": "voren", "name": "Bastion-Keeper Ilsa Voren", "faction": "armada", "unitDef": "armcom", "xp": 2050, "player": False, "home": ["tabula", "TAB_SE_PLATEAU"], "status": "active", "wounds": 0, "scars": [] },
            "ixt": { "id": "ixt", "name": "Dealer-Prime Ixt", "faction": "cortex", "unitDef": "corcom", "xp": 2600, "player": False, "home": ["eye_of_horus", "EOH_SE_CORTEX_POCKET"], "status": "active", "wounds": 0, "scars": [] },
            "calder": { "id": "calder", "name": "Synthwright Calder Nyx", "faction": "cortex", "unitDef": "corcom", "xp": 1750, "player": False, "home": ["greenest_fields", "GF_SE_SYNTH_START"], "status": "active", "wounds": 0, "scars": [] }
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
        # commander record is the command walker (levels, perks); the cadre is
        # the veteran roster (count-by-type); heroes are the named Fire-Emblem
        # roster - they deploy as marked units, leave rescuable wrecks, and a
        # destroyed wreck is permadeath (mission restart if missionCritical).
        "roster": {
            "commander": {
                "name": "Ashwalker Commander",
                # The suit they used to wear. Scrap until a story beat sets unlocked.
                # Mission number never fields it. Level and perks wait on the ledger.
                "unitDef": "legcom",
                "level": 1,
                "xp": 0.0,
                "perks": [],
                "scars": [],
                "unlocked": False,
            },
            "cadre": {},
            "cadreCap": 12,
            "heroes": [
                {
                    "heroId": "pavise",
                    "name": "Pavise",
                    # Solo Centurion left hand (armwar) — war buddy, Hardened BAR XP, HP aura.
                    "unitDef": "armwar",
                    "missionCritical": False,
                    "status": "active",
                    "xp": 0.45,
                    "campaignXp": 40.0,
                    "peakBarXp": 0.45,
                    "timesWounded": 0,
                },
                {
                    "heroId": "ketha",
                    "name": "Ketha",
                    # Ketha is the named field medic / rez-bot hero.
                    "unitDef": "legrezbot",
                    "missionCritical": False,
                    "status": "active",
                    "xp": 0.05,
                    "campaignXp": 0.0,
                    "peakBarXp": 0.05,
                    "timesWounded": 0,
                },
            ],
        },
        "processedResults": {},
        "zoneMemory": {},
        "offscreenActors": {},
        "destroyedObjectives": {},
        "persistentBaseSnapshots": {},
        "playerFootprints": {},
        "hazardState": {},
        "calibrationRefs": copy.deepcopy(TEST_WON_CALIBRATION_REFS),
        # Operator progression dial (cracked_farm = farm XP, heroes go super late).
        "progression": {
            "mode": "cracked_farm",
            "difficultyDial": 1.0,
            "xpMultiplier": 1.0,
            "farmSortiesEnabled": True,
            "xpPersistOnDeath": True,
        },
        # WO-043/metal: broker commerce — Tenebrium (build floor), campaign
        # metal in 1km$ units (floor(endMetal/1000)), purchasable packs / fabs.
        # Fresh bag seeded from commerce_catalog (7km$ + 3 Tnb); hireTnb spends Tnb.
        "commerce": {
            "tenebrium": 3,
            "metalK": 7,
            "owned": {},
            "upgrades": {},
            "ledger": [],
        },
        # Fire Emblem company: sealed on hub preamble (pick 3 packs). Unpicked
        # band heroes live in fieldPool until wreck/rez or sortie recruit.
        "company": {
            "sealed": False,
            "core": ["pavise", "ketha"],
            "band": [],
            "joinedLater": [],
            "sealedAt": None,
            "seatCap": 3,
        },
        "fieldPool": {},
        # Demo: "*" = full catalog on preamble. Later: explicit heroId list.
        "unlockPool": ["*"],
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
    # Company ensure (incl. legacy auto-seal) is NOT done here — it mutates
    # mid-run state. Callers that need a seal (hub rebuild, Drop gate, first
    # apply of a result) invoke ensure_company explicitly.
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


def get_character_rank(xp: float | int) -> str:
    val = int(xp)
    if val >= 3000:
        return "Marshal"
    elif val >= 2200:
        return "Warden"
    elif val >= 1500:
        return "Captain"
    elif val >= 800:
        return "Proven"
    return "Runner"


# Faction rep starts (v0.8.3). Cortex dealers want customers; Armada is cold.
REP_START_ARMADA = 18.0
REP_START_CORTEX = 70.0
REP_START_NULLMERCS = 48.0

# Crater / Cortex gear destruction — rapid plunge (they want customers until you bomb them).
CORTEX_CRATER_MAPS = frozenset({"eye_of_horus", "eyeofhorus"})
CORTEX_GRUDGE_VICTORY = -18.0
CORTEX_GRUDGE_PARTIAL = -10.0
CORTEX_GRUDGE_DEFEAT_DAMAGE = -4.0
ARMADA_RAID_HIT = -3.0  # modest when raiding Armada eco


def _result_destroyed_any(result: Dict[str, Any]) -> bool:
    destroyed = result.get("destroyedObjectiveIds") or result.get("destroyedObjectives") or []
    if destroyed:
        return True
    for item in result.get("objectiveResults") or []:
        if isinstance(item, dict) and item.get("status") in ("complete", "destroyed"):
            return True
    if float(result.get("objectiveDamage") or 0) > 0.15:
        return True
    if result.get("zoneFlipped") or result.get("nodeClaimed"):
        return True
    return False


def apply_reputation_companion(state: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> Dict[str, Any]:
    status = result.get("status", "unknown")
    extraction = result.get("extractionStatus", "")
    rep = state.setdefault("reputation", {})
    comp = state.setdefault("companion", {})
    if "clans" in rep:
        rep["nullmercs"] = clamp((float(rep.pop("clans")) + float(rep.get("nullmercs", 44.0))) / 2.0, 0, 100)
    for key, default in default_v1_state()["reputation"].items():
        rep.setdefault(key, default)
    for key, default in default_v1_state()["companion"].items():
        comp.setdefault(key, default)
    clean_extract = extraction in ("clean", "success") or bool(result.get("cleanExtract"))
    # Credit-table aligned: full victory only for big rep bump; partial is hinge.
    verdict = result.get("verdict") or status
    if verdict in ("victory", "victoryClean") or status == "victory":
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 48.0)) + 3.0, 0, 100)
        comp["xp"] = clamp(float(comp.get("xp", 0)) + 0.04, 0, 99)
        comp["morale"] = clamp(float(comp.get("morale", 70)) + (4 if clean_extract else 2), 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) - (5 if clean_extract else 1), 0, 100)
    elif verdict in ("partial", "extracted") or status in ("partial", "extracted"):
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 48.0)) + 1.0, 0, 100)
        comp["xp"] = clamp(float(comp.get("xp", 0)) + 0.015, 0, 99)
        comp["morale"] = clamp(float(comp.get("morale", 70)) + 1, 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 1, 0, 100)
    elif verdict in ("defeat", "failed", "failure") or status in ("defeat", "failed", "failure"):
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 48.0)) - 3.0, 0, 100)
        comp["morale"] = clamp(float(comp.get("morale", 70)) - 5, 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 8 + max(0, elapsed - 20) * 0.1, 0, 100)
    elif verdict == "abandon":
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 3, 0, 100)
    else:
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 2, 0, 100)

    # Explicit plan repDelta (hub / stamp).
    for faction, delta in (result.get("repDelta") or {}).items():
        try:
            rep[str(faction)] = clamp(float(rep.get(faction, 50.0)) + float(delta), 0, 100)
        except (TypeError, ValueError):
            pass

    map_id = str(result.get("mapId") or result.get("map") or "").lower().replace(" ", "_")
    against = str(result.get("against") or result.get("enemyFaction") or "").lower()
    destroyed = _result_destroyed_any(result)
    is_victory = verdict in ("victory", "victoryClean") or status == "victory"
    is_partial = verdict in ("partial", "extracted") or status in ("partial", "extracted")
    is_defeat = verdict in ("defeat", "failed", "failure") or status in ("defeat", "failed", "failure")

    # Cortex crater grudge — blow up their stuff, customers become enemies fast.
    cortex_theater = map_id in CORTEX_CRATER_MAPS or "cortex" in against or against == "cor"
    if cortex_theater and destroyed:
        if is_victory:
            hit = CORTEX_GRUDGE_VICTORY
        elif is_partial:
            hit = CORTEX_GRUDGE_PARTIAL
        elif is_defeat:
            hit = CORTEX_GRUDGE_DEFEAT_DAMAGE
        else:
            hit = CORTEX_GRUDGE_PARTIAL * 0.5
        rep["cortex"] = clamp(float(rep.get("cortex", REP_START_CORTEX)) + hit, 0, 100)

    # Modest Armada cool-off when you raid their eco works.
    if against == "armada" and destroyed and (is_victory or is_partial):
        rep["armada"] = clamp(float(rep.get("armada", REP_START_ARMADA)) + ARMADA_RAID_HIT, 0, 100)

    return {"reputation": rep, "companion": comp}


HOME_MAP_ID = "the_rock_jungle"
HOME_CLEAR_TNB_MIN = 3
HOME_CLEAR_CAMP_MIN = 1
HOME_KEY_ZONES = (
    "TRJ_C_SPILLWAY",
    "TRJ_C_INNER_SPILLWAY",
    "TRJ_NW_GATE",
    "TRJ_SE_GATE",
    # legacy aliases (pre-TRJ remap) — kept so old states still evaluate
    "RJ_CENTRAL_LAGOON_MAZE",
    "RJ_NW_JUNGLE_SHELF",
    "RJ_SE_JUNGLE_SHELF",
)
HOME_BUILD_TNB_COST = 1
HOME_BUILD_METAL_K_COST = 1
METAL_UNIT = 1000  # 1km$ = 1000 BAR metal


def ensure_home_camp(state: Dict[str, Any]) -> Dict[str, Any]:
    camp = state.setdefault("homeCamp", {})
    if not isinstance(camp, dict):
        camp = {}
        state["homeCamp"] = camp
    camp.setdefault("level", 0)
    camp.setdefault("mapId", HOME_MAP_ID)
    camp.setdefault("label", "Jungle shelf camp")
    flags = state.setdefault("flags", {})
    if not isinstance(flags, dict):
        flags = {}
        state["flags"] = flags
    flags.setdefault("homeClearReady", False)
    flags.setdefault("homeCleared", False)
    state.setdefault("sessionHomeMap", HOME_MAP_ID)
    state.setdefault("sessionMode", "same_map")
    return camp


_ZONE_MIGRATION_CACHE: Dict[str, Dict[str, str]] = {}
_ZONE_VALID_CACHE: Dict[str, set] = {}


def load_zone_migration(workspace: Optional[Path] = None) -> Dict[str, str]:
    """old zone id -> the zone that inherited it, from the last re-cut."""
    key = str(workspace or "")
    if key in _ZONE_MIGRATION_CACHE:
        return _ZONE_MIGRATION_CACHE[key]
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "zone_maps" / "authored")
    roots.append(Path(__file__).resolve().parent.parent / "data" / "zone_maps" / "authored")
    mapping: Dict[str, str] = {}
    for root in roots:
        path = root / "zone_id_migration.json"
        if not path.exists():
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        table = (data or {}).get("zones") if isinstance(data, dict) else None
        if isinstance(table, dict):
            mapping.update({str(k): str(v) for k, v in table.items() if v})
        if mapping:
            break
    _ZONE_MIGRATION_CACHE[key] = mapping
    return mapping


def valid_zone_ids(workspace: Optional[Path] = None) -> set:
    """Every zone id that currently exists, across all maps."""
    key = str(workspace or "")
    if key in _ZONE_VALID_CACHE:
        return _ZONE_VALID_CACHE[key]
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "zone_maps" / "authored")
    roots.append(Path(__file__).resolve().parent.parent / "data" / "zone_maps" / "authored")
    ids: set = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.zone_map.json")):
            try:
                data = load_json(path)
            except Exception:
                continue
            for zone in (data or {}).get("zones") or []:
                ids.add(str(zone.get("zoneId")))
        if ids:
            break
    _ZONE_VALID_CACHE[key] = ids
    return ids


def canonical_zone_id(zone_id: Any, workspace: Optional[Path] = None) -> Any:
    """Translate a retired zone id forward.

    Authored content -- default deploy zones, world character homes, the act-3
    finale objectives -- names zones directly, and a re-cut retires those names.
    Rather than hand-editing every constant on every re-cut, stale ids are
    translated through the migration map at the point of use."""
    if not isinstance(zone_id, str) or not zone_id:
        return zone_id
    valid = valid_zone_ids(workspace)
    if not valid or zone_id in valid:
        return zone_id
    mapping = load_zone_migration(workspace)
    direct = mapping.get(zone_id)
    if direct:
        return direct
    # Prose carries zone ids too ("Deploy RJ_CENTRAL_LAGOON_MAZE"), and a
    # briefing naming a zone that no longer exists reads as a bug to the player.
    if len(zone_id) > 12 and "_" in zone_id:
        replaced = zone_id
        for old_id, new_id in mapping.items():
            if old_id in replaced:
                replaced = replaced.replace(old_id, new_id)
        if replaced != zone_id:
            return replaced
    return zone_id


def canonicalize_zone_ids(node: Any, workspace: Optional[Path] = None) -> Any:
    """Translate every retired zone id anywhere in a structure."""
    if isinstance(node, str):
        return canonical_zone_id(node, workspace)
    if isinstance(node, list):
        return [canonicalize_zone_ids(item, workspace) for item in node]
    if isinstance(node, dict):
        return {key: canonicalize_zone_ids(value, workspace) for key, value in node.items()}
    return node


def _zone_control(state: Dict[str, Any], map_id: str, zone_id: str) -> str:
    zm = (state.get("zoneMemory") or {}).get(map_id) or {}
    z = zm.get(zone_id) or zm.get(load_zone_migration().get(zone_id, "")) or {}
    return str(
        z.get("controllingFaction")
        or (z.get("abstract") or {}).get("control")
        or "unknown"
    ).lower()


def evaluate_home_clear(state: Dict[str, Any], result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Update homeClearReady / homeCleared from camp, Tnb, and Rock Jungle control."""
    ensure_home_camp(state)
    flags = state["flags"]
    camp = state["homeCamp"]
    commerce = state.get("commerce") or {}
    tnb = int(commerce.get("tenebrium") or 0)
    level = int(camp.get("level") or 0)
    ready = tnb >= HOME_CLEAR_TNB_MIN or level >= HOME_CLEAR_CAMP_MIN
    flags["homeClearReady"] = bool(ready) and not bool(flags.get("homeCleared"))

    playerish = {"ashwalkers", "nullmercs", "legion"}
    key_held = sum(1 for zid in HOME_KEY_ZONES if _zone_control(state, HOME_MAP_ID, zid) in playerish)
    center = _zone_control(state, HOME_MAP_ID, "TRJ_C_SPILLWAY")
    if not center or center == "unknown":
        center = _zone_control(state, HOME_MAP_ID, "RJ_CENTRAL_LAGOON_MAZE")
    map_id = str((result or {}).get("mapId") or "").lower().replace(" ", "_")
    verdict = str((result or {}).get("verdict") or (result or {}).get("status") or "")
    home_win = (
        map_id in (HOME_MAP_ID, "rock_jungle")
        and verdict in ("victory", "victoryClean")
        and (center in playerish or key_held >= 2)
        and ready
    )
    if home_win or (center in playerish and key_held >= 2 and ready and level >= 2):
        flags["homeCleared"] = True
        flags["homeClearReady"] = False
    return {
        "homeClearReady": flags.get("homeClearReady"),
        "homeCleared": flags.get("homeCleared"),
        "keyHeld": key_held,
        "centerControl": center,
        "tenebrium": tnb,
        "campLevel": level,
    }


def apply_home_build(state: Dict[str, Any], workspace: Path | None = None) -> Dict[str, Any]:
    """Spend Tnb + 1km$ metal to raise the Rock Jungle camp (hub-only)."""
    ensure_home_camp(state)
    commerce = ensure_commerce(state, workspace)
    tnb = int(commerce.get("tenebrium") or 0)
    metal_k = int(commerce.get("metalK") or 0)
    if tnb < HOME_BUILD_TNB_COST:
        return {
            "ok": False,
            "error": f"need {HOME_BUILD_TNB_COST} Tenebrium (have {tnb}) — raid to print, then build home",
        }
    if metal_k < HOME_BUILD_METAL_K_COST:
        return {
            "ok": False,
            "error": f"need {HOME_BUILD_METAL_K_COST}×1km$ metal (have {metal_k})",
        }
    commerce["tenebrium"] = tnb - HOME_BUILD_TNB_COST
    commerce["metalK"] = metal_k - HOME_BUILD_METAL_K_COST
    camp = state["homeCamp"]
    camp["level"] = int(camp.get("level") or 0) + 1
    camp["lastBuiltAt"] = utc_now()
    # Light kit hook: mark an owned "camp_bp" stub for deploy kit flavor.
    owned = commerce.setdefault("owned", {})
    prev = owned.get("home_camp_bp") or {}
    owned["home_camp_bp"] = {
        "kind": "home_camp",
        "label": f"Jungle camp L{camp['level']}",
        "qty": int(prev.get("qty") or 0) + 1,
        "builds": True,
        "mapId": HOME_MAP_ID,
    }
    evaluate_home_clear(state)
    if workspace is not None:
        try:
            save_json(Path(workspace) / "state" / "campaign_state.json", state)
        except Exception:
            pass
    return {
        "ok": True,
        "homeCamp": camp,
        "tenebrium": commerce["tenebrium"],
        "metalK": commerce["metalK"],
        "flags": dict(state.get("flags") or {}),
    }


# Pillar C: commander progression. XP accrues per sortie; each level unlocks one
# perk the compiler/gadget turns into a tangible starting-force bonus.
# Cracked-farm mode stretches the ladder so late-campaign heroes feel absurd.
ROSTER_XP_PER_LEVEL = 80.0
ROSTER_MAX_LEVEL = 8
PERK_LADDER = {
    2: "field_repair",     # extra starting build power
    3: "veteran_cadre",    # +6 cadre cap
    4: "rapid_deploy",     # one bonus starting unit
    5: "ash_resolve",      # tougher commander
    6: "blood_tempo",      # extra metal/energy on deploy
    7: "named_guard",      # tougher hero HP floor
    8: "cracked_core",     # commander + heroes start highly experienced
}
CADRE_CAP_BASE = 12

# Named-hero campaign XP (integer ladder). Never decreases on death — scars and
# status may, but the blood learned stays on the character sheet.
HERO_CAMPAIGN_XP_PER_LEVEL = 100.0
HERO_MAX_LEVEL = 12
# BAR unit experience floors by hero level (engine combat bonuses scale with this).
# Level 1 ~ green, level 6 solid vet, level 12 endgame cracked.
HERO_BAR_XP_PER_LEVEL = 0.55
HERO_BAR_XP_BASE = 0.15


def ensure_progression(state: Dict[str, Any]) -> Dict[str, Any]:
    """Operator-facing progression + difficulty dial.

    mode:
      - cracked_farm (default): farm XP, heroes snowball hard, death keeps XP
      - standard: modest gains, still XP-persist-on-death
    difficultyDial: explicit 0.75–1.25 multiplier (clarity over hidden graph).
    xpMultiplier: extra farm rate without touching enemy scale.
    """
    prog = state.setdefault("progression", {})
    if not isinstance(prog, dict):
        prog = {}
        state["progression"] = prog
    prog.setdefault("mode", "cracked_farm")
    prog.setdefault("difficultyDial", 1.0)
    prog.setdefault("xpMultiplier", 1.0)
    prog.setdefault("farmSortiesEnabled", True)
    prog.setdefault("xpPersistOnDeath", True)  # always honored; flag is documentary
    # Soft clamp so bad saves cannot invent absurd dials.
    try:
        prog["difficultyDial"] = float(clamp(float(prog.get("difficultyDial", 1.0)), 0.7, 1.35))
    except (TypeError, ValueError):
        prog["difficultyDial"] = 1.0
    try:
        prog["xpMultiplier"] = float(clamp(float(prog.get("xpMultiplier", 1.0)), 0.5, 3.0))
    except (TypeError, ValueError):
        prog["xpMultiplier"] = 1.0
    if str(prog.get("mode", "")).lower() not in ("cracked_farm", "standard"):
        prog["mode"] = "cracked_farm"
    return prog


def hero_level_from_campaign_xp(campaign_xp: float) -> int:
    return int(min(HERO_MAX_LEVEL, 1 + int(max(0.0, float(campaign_xp or 0.0)) // HERO_CAMPAIGN_XP_PER_LEVEL)))


def bar_unit_xp_from_campaign(campaign_xp: float, peak_bar_xp: float = 0.0) -> float:
    """Map campaign ladder → BAR SetUnitExperience value (power fantasy)."""
    level = hero_level_from_campaign_xp(campaign_xp)
    from_level = HERO_BAR_XP_BASE + (level - 1) * HERO_BAR_XP_PER_LEVEL
    return round(max(float(peak_bar_xp or 0.0), from_level), 4)


def hero_hp_mult_from_level(level: int, critical: bool, wounded: bool) -> float:
    base = 1.45 if critical else 1.35
    scaled = base * (1.0 + max(0, int(level) - 1) * 0.085)
    if wounded:
        scaled *= 0.82
    return round(min(2.75, scaled), 3)


def hero_rank_label(level: int) -> str:
    # L3–L4 used to say "Blooded" — read as wounded. "Proven" is the career rung.
    if level >= 11:
        return "Cracked"
    if level >= 9:
        return "Legend"
    if level >= 7:
        return "Marshal"
    if level >= 5:
        return "Captain"
    if level >= 3:
        return "Proven"
    return "Runner"


def normalize_hero_rank_label(rank: Any) -> str:
    """Map legacy display ranks onto the current ladder."""
    r = str(rank or "").strip()
    if not r:
        return "Runner"
    low = r.lower()
    if low in ("blooded", "bloodied"):
        return "Proven"
    if low == "green":
        return "Runner"
    return r


def load_commerce_catalog(workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Broker catalog: Tenebrium, loan packs, fab streams, faction constructors."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "commerce" / "commerce_catalog.json")
    here = Path(__file__).resolve().parent.parent
    paths.append(here / "data" / "commerce" / "commerce_catalog.json")
    for path in paths:
        if path.exists():
            try:
                data = load_json(path)
                if isinstance(data, dict) and data.get("listings"):
                    return data
            except Exception:
                continue
    return {
        "schemaVersion": "verdance-commerce-catalog/1.0",
        "resource": {
            "id": "tenebrium",
            "startingBalance": {"ashwalkers": 3, "nullmercs": 3},
            "buildFloor": 1,
        },
        "metal": {"startingBalanceK": 7, "unitMetal": 1000},
        "listings": {},
        "sortieRewards": {},
    }


def listing_metal_cost_k(listing: Dict[str, Any]) -> int:
    """Prefer metalCostK; fall back to retired creditCost for one-release compat."""
    if listing.get("metalCostK") is not None:
        return int(listing.get("metalCostK") or 0)
    return int(listing.get("creditCost") or 0)


def _catalog_starting_tenebrium(catalog: Optional[Dict[str, Any]] = None) -> int:
    """Player starting Tnb from catalog (ashwalkers / nullmercs / startingBalancePlayer)."""
    cat = catalog or {}
    resource = cat.get("resource") or {}
    starting = resource.get("startingBalance") or {}
    if "startingBalancePlayer" in resource:
        return max(0, int(resource.get("startingBalancePlayer") or 0))
    for key in ("ashwalkers", "nullmercs", "player"):
        if key in starting:
            return max(0, int(starting.get(key) or 0))
    return 0


# Soft cap on extracted mobile army value carried into the next Drop (metal).
ARMY_BUDGET_SOFT_CAP = 18000
# Convert budget → deploy escorts (approx metal cost per chassis).
ARMY_BUDGET_ESCORTS = (
    ("legcen", 160, 20),   # Phobos swarm — cheap mobile mass
    ("legkark", 520, 4),   # Karkinos — mid punch
    ("legshot", 280, 6),   # Shotgun — close riot
)


def apply_army_budget_from_result(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Bank living mobile armyValue into commerce.armyBudget on extract/homecoming.

    Structures stay on playerFootprints (map-local). This bag is the cross-map
    "leave with a bigger army" carry — spent into deploy escorts on the next Drop.
    """
    commerce = ensure_commerce(state, workspace)
    commerce.setdefault("armyBudget", 0)

    def _army_from(obj: Any) -> float:
        if not isinstance(obj, dict):
            return 0.0
        try:
            return float((obj.get("metrics") or {}).get("armyValue") or obj.get("armyValue") or 0)
        except (TypeError, ValueError):
            return 0.0

    army = _army_from(result)
    # Prefer player team bucket from result / embedded telemetry.
    candidates: List[Any] = []
    for key in ("teams", "teamMetrics"):
        raw = result.get(key)
        if isinstance(raw, list):
            candidates.extend(raw)
        elif isinstance(raw, dict):
            candidates.extend(raw.values())
    tel = result.get("telemetry") if isinstance(result.get("telemetry"), dict) else {}
    for key in ("teams", "teamMetrics"):
        raw = tel.get(key)
        if isinstance(raw, list):
            candidates.extend(raw)
        elif isinstance(raw, dict):
            candidates.extend(raw.values())
    player_tid = result.get("playerTeamId")
    if player_tid is None:
        player_tid = tel.get("playerTeamId")
    for bucket in candidates:
        if not isinstance(bucket, dict):
            continue
        tid = bucket.get("teamId")
        fac = str(bucket.get("faction") or "").lower()
        is_player = (
            tid == player_tid
            or tid in (0, "0")
            or fac in ("ashwalkers", "player")
        )
        if is_player:
            val = _army_from(bucket)
            if val > 0:
                army = val
                break
    if army <= 0:
        return {"armyBudget": int(commerce.get("armyBudget") or 0), "gained": 0}
    prev = int(commerce.get("armyBudget") or 0)
    room = max(0, ARMY_BUDGET_SOFT_CAP - prev)
    # Soft diminishing once past half the cap.
    gained = int(round(army))
    if prev >= ARMY_BUDGET_SOFT_CAP // 2:
        gained = int(round(gained * 0.55))
    gained = max(0, min(room, gained))
    commerce["armyBudget"] = prev + gained
    if gained:
        commerce.setdefault("ledger", []).append({
            "op": "army_budget_bank",
            "gained": gained,
            "armyValue": int(round(army)),
            "armyBudget": commerce["armyBudget"],
            "at": utc_now(),
        })
    return {
        "armyBudget": int(commerce["armyBudget"]),
        "gained": gained,
        "armyValue": int(round(army)),
    }


def spend_army_budget_into_deploy(
    commerce: Dict[str, Any],
    deploy: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Convert armyBudget into t=0 combat escort packages; consume the bag."""
    budget = int(commerce.get("armyBudget") or 0)
    if budget <= 0:
        return {"spent": 0, "units": 0, "remaining": 0}
    spent = 0
    units = 0
    remaining = budget
    for unit_def, cost, cap in ARMY_BUDGET_ESCORTS:
        if remaining < cost or cap <= 0:
            continue
        count = min(cap, remaining // cost)
        if count <= 0:
            continue
        deploy.append({
            "listingId": f"army_bank_{unit_def}",
            "kind": "package",
            "unitDef": unit_def,
            "count": int(count),
            "healthFrac": 1.0,
            "loan": False,
            "packageTag": "army_budget",
            "label": f"Exfil army · {unit_def}",
        })
        take = int(count * cost)
        spent += take
        units += int(count)
        remaining -= take
    # Leftover metal under cheapest chassis → field seed bump handled by caller.
    commerce["armyBudget"] = int(remaining)
    if spent:
        commerce.setdefault("ledger", []).append({
            "op": "army_budget_spend",
            "spent": spent,
            "units": units,
            "remaining": int(remaining),
            "at": utc_now(),
        })
    return {"spent": spent, "units": units, "remaining": int(remaining)}


def default_commerce_state(catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cat = catalog or {}
    metal_meta = cat.get("metal") or {}
    metal0 = int(metal_meta.get("startingBalanceK", 7) or 0)
    tnb0 = _catalog_starting_tenebrium(cat)
    return {
        "tenebrium": tnb0,
        "metalK": metal0,
        "armyBudget": 0,
        "owned": {},
        "upgrades": {},
        "ledger": [],
    }


def commerce_dest_map_id(state: Dict[str, Any], workspace: Optional[Path] = None) -> str:
    """Best-effort destination map for shop ETA / pending deliveries."""
    def _ok(mid: Optional[str]) -> str:
        if not mid:
            return ""
        # story-engine canonical_map_id(None) returns "unknown" — treat as empty.
        raw = str(mid).strip()
        if not raw or raw.lower() in ("unknown", "none", "null"):
            return ""
        out = canonical_map_id(raw)
        if not out or out == "unknown":
            return ""
        return out

    for key in ("plannedMapId", "activeMapId", "sessionHomeMap"):
        mid = _ok(state.get(key))
        if mid:
            return mid
    # Hub deploy stamp / plan if present beside workspace.
    root = Path(workspace) if workspace is not None else Path(__file__).resolve().parent.parent
    for rel in (
        Path("outbox") / "hub_deploy_stamp.latest.json",
        Path("outbox") / "hub_deploy_plan.latest.json",
    ):
        path = root / rel
        if not path.exists():
            continue
        try:
            data = load_json(path)
            if isinstance(data, dict):
                mid = _ok(
                    data.get("mapId")
                    or data.get("deploymentMapId")
                    or (data.get("plan") or {}).get("mapId")
                )
                if mid:
                    return mid
        except Exception:
            continue
    return "greenest_fields"


def ensure_commerce(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Ensure commerce bag; migrate scrap→metalK; retire loans.

    Buy-everything rule: do not auto-grant combat packs. ``starterOwned`` is
    retired (Punch must be purchased). Legacy loan Punch still converts to a
    one-salvo owned package so old saves are not soft-locked.
    """
    catalog = load_commerce_catalog(workspace)
    commerce = state.setdefault("commerce", default_commerce_state(catalog))
    if "tenebrium" not in commerce:
        commerce["tenebrium"] = _catalog_starting_tenebrium(catalog)
    # Migrate retired scrap credits → campaign metal (1km$). scrap÷10 ≈ old pack scale.
    # Live playtest make-good (+9km$ for ~9k end metal never exported) only on scrap migrate.
    if "metalK" not in commerce:
        old_scrap = int(commerce.get("credits") or 0)
        metal_meta = catalog.get("metal") or {}
        start_k = int(metal_meta.get("startingBalanceK", 7) or 0)
        migrated_from_scrap = "credits" in commerce
        commerce["metalK"] = max(start_k, old_scrap // 10) if old_scrap else start_k
        ledger = commerce.setdefault("ledger", [])
        ledger.append({
            "op": "migrate_scrap_to_metal",
            "oldCredits": old_scrap,
            "metalK": commerce["metalK"],
            "at": utc_now(),
        })
        if migrated_from_scrap:
            commerce["metalK"] = int(commerce.get("metalK") or 0) + 9
            ledger.append({
                "op": "metal_playtest_credit",
                "metalK": 9,
                "note": "Make-good for ~9k end metal lost before metalStored export",
                "at": utc_now(),
            })
            flags = state.setdefault("flags", {})
            if isinstance(flags, dict):
                flags["metalPlaytestCreditApplied"] = True
    commerce.pop("credits", None)
    commerce.setdefault("owned", {})
    commerce.setdefault("upgrades", {})
    commerce.setdefault("ledger", [])
    commerce.setdefault("pendingDeliveries", [])
    commerce.setdefault("armyBudget", 0)
    owned = commerce["owned"]
    listings = catalog.get("listings") or {}

    # Retire Punch-of-Thugs loan: convert to one free non-loan purchase salvo.
    punch = owned.get("punch_of_thugs")
    punch_listing = listings.get("punch_of_thugs") if isinstance(listings.get("punch_of_thugs"), dict) else {}
    if isinstance(punch, dict) and (
        punch.get("loan") or str(punch.get("kind") or "") == "loan_package"
    ):
        owned["punch_of_thugs"] = {
            "qty": max(1, int(punch.get("qty") or 1)),
            "loan": False,
            "unitDef": punch_listing.get("unitDef") or punch.get("unitDef") or "corthud",
            "loanCount": None,
            "loanHealthBaseline": None,
            "spawnHealthFracMin": punch_listing.get("spawnHealthFracMin", 0.85),
            "spawnHealthFracMax": punch_listing.get("spawnHealthFracMax", 1.0),
            "acquiredAtMission": int(punch.get("acquiredAtMission") or state.get("missionNumber", 1) or 1),
            "source": "loan_retire_grant",
            "kind": "purchase_package",
            "count": int(punch_listing.get("count") or 7),
            "delivery": dict(punch_listing.get("delivery") or {}),
        }
        commerce.setdefault("ledger", []).append({
            "op": "loan_retire",
            "listingId": "punch_of_thugs",
            "note": "Punch is now a pawn-launcher purchase (7 Thugs). Prior loan converted to one free salvo.",
            "at": utc_now(),
        })

    for lid, listing in listings.items():
        if not isinstance(listing, dict):
            continue
        if not listing.get("starterOwned"):
            continue
        if lid in owned:
            continue
        owned[lid] = {
            "qty": 1,
            "loan": bool(listing.get("loan")),
            "unitDef": listing.get("unitDef"),
            "loanCount": int(listing.get("count") or 0) if listing.get("loan") else None,
            "loanHealthBaseline": (
                round(
                    (float(listing.get("spawnHealthFracMin") or 0.4)
                     + float(listing.get("spawnHealthFracMax") or 0.5)) * 0.5,
                    3,
                )
                if listing.get("loan")
                else None
            ),
            "spawnHealthFracMin": listing.get("spawnHealthFracMin"),
            "spawnHealthFracMax": listing.get("spawnHealthFracMax"),
            "acquiredAtMission": int(state.get("missionNumber", 1) or 1),
            "source": "starter",
            "kind": listing.get("kind") or "purchase_package",
            "count": listing.get("count"),
            "delivery": dict(listing.get("delivery") or {}),
        }
        commerce.setdefault("ledger", []).append({
            "op": "starter_grant",
            "listingId": lid,
            "at": utc_now(),
        })
    return commerce


def commerce_arc_number(state: Dict[str, Any]) -> int:
    n = int(state.get("missionNumber", 1) or 1)
    if n <= 5:
        return 1
    if n <= 10:
        return 2
    return 3


def listing_available(
    listing_id: str,
    listing: Dict[str, Any],
    state: Dict[str, Any],
    commerce: Dict[str, Any],
) -> Tuple[bool, str]:
    if not listing:
        return False, "unknown listing"
    owned = commerce.get("owned") or {}
    upgrades = commerce.get("upgrades") or {}
    kind = str(listing.get("kind") or "")
    if kind == "printer_upgrade" and listing_id in upgrades:
        return False, "upgrade already installed"
    if kind in ("unit_printer", "loan_package") and listing_id in owned:
        return False, "already owned"
    if kind == "hero_contract":
        hid = str(listing.get("heroId") or "")
        heroes = ((state.get("roster") or {}).get("heroes") or [])
        for h in heroes:
            if isinstance(h, dict) and str(h.get("heroId")) == hid and str(h.get("status")) != "locked":
                return False, f"hero {hid} already on the company"
        if listing_id in owned:
            return False, "contract already signed"
    if listing.get("starterOwned") and listing.get("loan") and listing_id in owned:
        return False, "already owned (starter loan)"
    req = listing.get("requires")
    if req and req not in owned:
        return False, f"requires {req}"
    arc_min = int(listing.get("arcMin") or 1)
    if commerce_arc_number(state) < arc_min:
        return False, f"arc {arc_min}+ only"
    rep = state.get("reputation") or {}
    for faction, need in (listing.get("repMin") or {}).items():
        have = float(rep.get(faction, 0) or 0)
        if have < float(need):
            return False, f"need {faction} rep >= {need} (have {have:.0f})"
    tcost = int(listing.get("tenebriumCost") or 0)
    if listing.get("builds") and tcost < 1:
        tcost = 1
    mcost = listing_metal_cost_k(listing)
    if int(commerce.get("tenebrium") or 0) < tcost:
        return False, f"need {tcost} Tenebrium (have {commerce.get('tenebrium', 0)})"
    if int(commerce.get("metalK") or 0) < mcost:
        return False, f"need {mcost}×1km$ metal (have {commerce.get('metalK', 0)})"
    return True, "ok"


def purchase_listing(
    state: Dict[str, Any],
    listing_id: str,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Buy/install a catalog listing. Mutates state commerce. Returns receipt."""
    catalog = load_commerce_catalog(workspace)
    commerce = ensure_commerce(state, workspace)
    listing = (catalog.get("listings") or {}).get(listing_id)
    if not isinstance(listing, dict):
        return {"ok": False, "error": "unknown listing", "listingId": listing_id}
    ok, reason = listing_available(listing_id, listing, state, commerce)
    if not ok:
        return {"ok": False, "error": reason, "listingId": listing_id}
    tcost = int(listing.get("tenebriumCost") or 0)
    if listing.get("builds") and tcost < 1:
        tcost = 1
    mcost = listing_metal_cost_k(listing)
    commerce["tenebrium"] = int(commerce.get("tenebrium") or 0) - tcost
    commerce["metalK"] = int(commerce.get("metalK") or 0) - mcost
    kind = str(listing.get("kind") or "purchase_package")
    if kind == "hero_contract":
        roster = ensure_roster(state)
        heroes = roster.setdefault("heroes", [])
        hid = str(listing.get("heroId") or "hero")
        existing = next((h for h in heroes if isinstance(h, dict) and str(h.get("heroId")) == hid), None)
        hero_rec = {
            "heroId": hid,
            "name": str(listing.get("heroName") or hid.title()),
            "unitDef": str(listing.get("unitDef") or "legscout"),
            "missionCritical": False,
            "status": "active",
            "xp": 0.15,
            "timesWounded": 0,
            "campaignXp": 0.0,
            "peakBarXp": 0.15,
            "level": 1,
            "rank": "Runner",
            "trait": str(listing.get("trait") or "wheelie_mentor"),
            "traits": ["wheelie_mentor", "scout_tech"],
            "unlock": {"listingId": listing_id, "rep": "nullmercs"},
        }
        if existing:
            existing.update({k: v for k, v in hero_rec.items() if k != "heroId"})
            existing["status"] = "active"
        else:
            heroes.append(hero_rec)
        chars = state.setdefault("characters", {})
        if hid not in chars:
            chars[hid] = {
                "id": hid,
                "name": hero_rec["name"],
                "faction": "nullmercs",
                "unitDef": hero_rec["unitDef"],
                "xp": 0,
                "player": True,
                "home": None,
                "status": "active",
                "wounds": 0,
                "scars": [],
            }
        else:
            chars[hid]["player"] = True
            chars[hid]["status"] = "active"
        commerce.setdefault("owned", {})[listing_id] = {
            "qty": 1,
            "kind": "hero_contract",
            "heroId": hid,
            "acquiredAtMission": int(state.get("missionNumber", 1) or 1),
            "source": "purchase",
        }
    elif kind == "printer_upgrade":
        commerce.setdefault("upgrades", {})[listing_id] = {
            "installedAtMission": int(state.get("missionNumber", 1) or 1),
            "requires": listing.get("requires"),
            "metalIncomeBonus": listing.get("metalIncomeBonus"),
            "energyIncomeBonus": listing.get("energyIncomeBonus"),
            "nanoDef": listing.get("nanoDef"),
            "nanoCount": listing.get("nanoCount"),
        }
    else:
        prev = (commerce.get("owned") or {}).get(listing_id) or {}
        qty = int(prev.get("qty") or 0) + 1 if kind == "purchase_package" else 1
        delivery = resolve_listing_delivery(listing, listing_id, workspace)
        dest = commerce_dest_map_id(state, workspace)
        eta = delivery_eta(
            listing=listing,
            listing_id=listing_id,
            dest_map_id=dest,
            workspace=workspace,
        )
        commerce.setdefault("owned", {})[listing_id] = {
            "qty": qty,
            "loan": bool(listing.get("loan")),
            "unitDef": listing.get("unitDef") or listing.get("factoryDef"),
            "loanCount": int(listing.get("count") or 0) if listing.get("loan") else None,
            "loanHealthBaseline": (
                round(
                    (float(listing.get("spawnHealthFracMin") or 0.4)
                     + float(listing.get("spawnHealthFracMax") or 0.5)) * 0.5,
                    3,
                )
                if listing.get("loan")
                else None
            ),
            "acquiredAtMission": int(state.get("missionNumber", 1) or 1),
            "source": "purchase",
            "kind": kind,
            "product": listing.get("product"),
            "factoryDef": listing.get("factoryDef"),
            "seedCount": listing.get("seedCount"),
            "metalIncome": listing.get("metalIncome"),
            "energyIncome": listing.get("energyIncome"),
            "count": listing.get("count"),
            "spawnHealthFracMin": listing.get("spawnHealthFracMin"),
            "spawnHealthFracMax": listing.get("spawnHealthFracMax"),
            "delivery": delivery,
            "lastEta": {
                "etaSeconds": eta.get("etaSeconds"),
                "etaText": eta.get("etaText"),
                "summary": eta.get("summary"),
                "destMapId": eta.get("destMapId"),
            },
        }
        # Deferred combat packs become pending deliveries (arrive mid-sortie).
        if kind == "purchase_package" and delivery.get("deferred"):
            pending = make_pending_delivery(
                listing_id=listing_id,
                listing=listing,
                dest_map_id=dest,
                qty=1,
                workspace=workspace,
                mission_number=int(state.get("missionNumber", 1) or 1),
            )
            if pending:
                # Unique id per purchase event.
                pending["id"] = f"pd_{listing_id}_{int(state.get('missionNumber', 1) or 1)}_{qty}_{len(commerce.get('pendingDeliveries') or [])}"
                commerce.setdefault("pendingDeliveries", []).append(pending)
    commerce.setdefault("ledger", []).append({
        "op": "purchase",
        "listingId": listing_id,
        "tenebriumCost": tcost,
        "metalCostK": mcost,
        "at": utc_now(),
        "missionNumber": int(state.get("missionNumber", 1) or 1),
    })
    receipt = {
        "ok": True,
        "listingId": listing_id,
        "tenebriumCost": tcost,
        "metalCostK": mcost,
        "tenebriumLeft": commerce["tenebrium"],
        "metalKLeft": commerce["metalK"],
    }
    if kind == "purchase_package":
        eta = delivery_eta(
            listing=listing,
            listing_id=listing_id,
            dest_map_id=commerce_dest_map_id(state, workspace),
            workspace=workspace,
        )
        receipt["delivery"] = {
            "mode": eta.get("mode"),
            "etaSeconds": eta.get("etaSeconds"),
            "etaText": eta.get("etaText"),
            "summary": eta.get("summary"),
            "sourceLabel": eta.get("sourceLabel"),
            "routeLabels": eta.get("routeLabels"),
            "deferred": bool(eta.get("deferred")),
        }
    return receipt


def build_commerce_intent(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Serialize commerce bag + shop shelf + deploy specs for the mission compiler.

    map_web packs go to pendingDeliveries (mid-sortie arrival).
    pawn_launcher / constructors / fabs go to deploy (t=0 kit).
    """
    catalog = load_commerce_catalog(workspace)
    commerce = ensure_commerce(state, workspace)
    listings = catalog.get("listings") or {}
    owned = commerce.get("owned") or {}
    upgrades = commerce.get("upgrades") or {}
    dest = commerce_dest_map_id(state, workspace)
    shop: List[Dict[str, Any]] = []
    for lid, listing in listings.items():
        if not isinstance(listing, dict):
            continue
        ok, reason = listing_available(lid, listing, state, commerce)
        tcost = int(listing.get("tenebriumCost") or 0)
        if listing.get("builds") and tcost < 1:
            tcost = 1
        eta = delivery_eta(
            listing=listing,
            listing_id=lid,
            dest_map_id=dest,
            workspace=workspace,
        )
        shop.append({
            "id": lid,
            "label": listing.get("label") or lid,
            "blurb": listing.get("blurb") or "",
            "kind": listing.get("kind"),
            "tenebriumCost": tcost,
            "metalCostK": listing_metal_cost_k(listing),
            "builds": bool(listing.get("builds")),
            "available": ok,
            "blockedReason": None if ok else reason,
            "repMin": listing.get("repMin") or {},
            "arcMin": int(listing.get("arcMin") or 1),
            "tags": list(listing.get("tags") or []),
            "count": listing.get("count") or listing.get("seedCount"),
            "delivery": {
                "mode": eta.get("mode"),
                "deferred": bool(eta.get("deferred")),
                "sourceLabel": eta.get("sourceLabel"),
                "sourceBlurb": eta.get("sourceBlurb"),
                "etaSeconds": eta.get("etaSeconds"),
                "etaText": eta.get("etaText"),
                "summary": eta.get("summary"),
                "routeLabels": eta.get("routeLabels"),
                "travelMinutes": eta.get("travelMinutes"),
                "landNear": eta.get("landNear"),
            },
        })
    deploy: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    # Carry explicit pending queue first.
    for item in commerce.get("pendingDeliveries") or []:
        if isinstance(item, dict) and str(item.get("status") or "in_transit") == "in_transit":
            pending.append(copy.deepcopy(item))

    pending_listing_ids = {str(p.get("listingId")) for p in pending}

    for lid, rec in owned.items():
        if not isinstance(rec, dict):
            continue
        listing = listings.get(lid) or {}
        kind = str(rec.get("kind") or listing.get("kind") or "purchase_package")
        delivery = resolve_listing_delivery(listing, lid, workspace)
        deferred = bool(delivery.get("deferred")) and kind == "purchase_package"

        if kind in ("loan_package", "purchase_package") or (
            listing.get("unitDef") and kind not in ("unit_printer", "constructor", "hero_contract")
        ):
            unit_def = rec.get("unitDef") or listing.get("unitDef")
            count = int(rec.get("loanCount") or rec.get("count") or listing.get("count") or 0)
            qty = int(rec.get("qty") or 1)
            if kind == "purchase_package":
                count = int(listing.get("count") or count or 0) * max(1, qty)
            if unit_def and count > 0:
                hmin = float(rec.get("spawnHealthFracMin") or listing.get("spawnHealthFracMin") or 1.0)
                hmax = float(rec.get("spawnHealthFracMax") or listing.get("spawnHealthFracMax") or 1.0)
                hfrac = round((hmin + hmax) * 0.5, 3)
                if deferred:
                    # Synthesize pending from owned if purchase did not queue yet
                    # (e.g. migrated crash/punch from older saves).
                    if lid not in pending_listing_ids:
                        syn = make_pending_delivery(
                            listing_id=lid,
                            listing=listing or {
                                "unitDef": unit_def,
                                "count": int(listing.get("count") or count // max(1, qty)),
                                "spawnHealthFracMin": hmin,
                                "spawnHealthFracMax": hmax,
                                "label": listing.get("label") or lid,
                                "delivery": delivery,
                            },
                            dest_map_id=dest,
                            qty=qty,
                            workspace=workspace,
                            mission_number=int(state.get("missionNumber", 1) or 1),
                        )
                        if syn:
                            syn["count"] = count
                            pending.append(syn)
                            pending_listing_ids.add(lid)
                else:
                    deploy.append({
                        "listingId": lid,
                        "kind": "package",
                        "unitDef": unit_def,
                        "count": count,
                        "healthFrac": hfrac,
                        "healthFracMin": hmin,
                        "healthFracMax": hmax,
                        "loan": bool(rec.get("loan") or listing.get("loan")),
                        "packageTag": lid,
                        "label": listing.get("label") or lid,
                    })
        if kind == "unit_printer" or listing.get("factoryDef"):
            metal = float(rec.get("metalIncome") or listing.get("metalIncome") or 8)
            energy = float(rec.get("energyIncome") or listing.get("energyIncome") or 40)
            for _uid, up in upgrades.items():
                if not isinstance(up, dict):
                    continue
                if up.get("requires") and up.get("requires") != lid:
                    continue
                metal += float(up.get("metalIncomeBonus") or 0)
                energy += float(up.get("energyIncomeBonus") or 0)
            deploy.append({
                "listingId": lid,
                "kind": "unit_printer",
                "factoryDef": rec.get("factoryDef") or listing.get("factoryDef") or "corlab",
                "product": rec.get("product") or listing.get("product") or "corak",
                "seedCount": int(rec.get("seedCount") or listing.get("seedCount") or 4),
                "metalIncome": metal,
                "energyIncome": energy,
                "label": listing.get("label") or lid,
            })
            for uid, up in upgrades.items():
                if not isinstance(up, dict):
                    continue
                if up.get("requires") and up.get("requires") != lid:
                    continue
                nano = up.get("nanoDef") or "cornanotc"
                ncount = int(up.get("nanoCount") or 0)
                if ncount > 0:
                    deploy.append({
                        "listingId": uid,
                        "kind": "nano",
                        "unitDef": nano,
                        "count": ncount,
                        "label": "Fab build power",
                    })
        if kind == "constructor" or listing.get("kind") == "constructor":
            unit_def = rec.get("unitDef") or listing.get("unitDef")
            count = int(rec.get("count") or listing.get("count") or 1) * int(rec.get("qty") or 1)
            if unit_def and count > 0:
                deploy.append({
                    "listingId": lid,
                    "kind": "constructor",
                    "unitDef": unit_def,
                    "count": count,
                    "label": listing.get("label") or lid,
                })
    access = bp_access(state)
    # Keep bag queue aligned with what the compiler will seed.
    commerce["pendingDeliveries"] = copy.deepcopy(pending)
    # Preview escorts from armyBudget without consuming — commit_deploy spends once.
    army_budget = int(commerce.get("armyBudget") or 0)
    army_preview: List[Dict[str, Any]] = []
    if army_budget > 0:
        preview_bag = {"armyBudget": army_budget, "ledger": []}
        spend_army_budget_into_deploy(preview_bag, army_preview)
        for row in army_preview:
            deploy.append(copy.deepcopy(row))
    metal_meta = catalog.get("metal") or {}
    # Operating allotment only — campaign metalK stays home and export ADDs.
    field_start_k = int(metal_meta.get("fieldStartMetalK") or 1)
    if field_start_k < 0:
        field_start_k = 0
    leftover_preview = max(0, army_budget - sum(
        int(r.get("count") or 0) * next(
            (c for d, c, _cap in ARMY_BUDGET_ESCORTS if d == r.get("unitDef")),
            0,
        )
        for r in army_preview
    ))
    unit_metal = int(metal_meta.get("unitMetal") or METAL_UNIT or 1000)
    if leftover_preview >= unit_metal:
        field_start_k += leftover_preview // unit_metal
    field_start_e = int(metal_meta.get("fieldStartEnergy") or 3000)
    if field_start_e < 0:
        field_start_e = 0
    return {
        "tenebrium": int(commerce.get("tenebrium") or 0),
        "metalK": int(commerce.get("metalK") or 0),
        "armyBudget": army_budget,
        "armyBudgetUnits": sum(int(r.get("count") or 0) for r in army_preview),
        # Explicit: bag does not enter BAR; gadget reads these for field seed.
        "metalKBrought": 0,
        "fieldStartMetalK": field_start_k,
        "metalKFieldStart": field_start_k,
        "fieldStartEnergy": field_start_e,
        "resourceLabel": ((catalog.get("resource") or {}).get("label") or "Tenebrium"),
        "metalLabel": metal_meta.get("label") or "Metal",
        "metalShortLabel": metal_meta.get("shortLabel") or "1km$",
        "metalUnit": int(metal_meta.get("unitMetal") or METAL_UNIT),
        "buildFloor": int((catalog.get("resource") or {}).get("buildFloor") or 1),
        "bpAccess": access,
        "owned": copy.deepcopy(owned),
        "upgrades": copy.deepcopy(upgrades),
        "shop": shop,
        "deploy": deploy,
        "pendingDeliveries": pending,
        "destMapId": dest,
        "arc": commerce_arc_number(state),
        "notes": (
            "Tenebrium is black-hole metal (scarce since the Generic Disaster). "
            "Anything that builds costs ≥1. Concurrent BP ceiling = 150 × access Tnb. "
            "Campaign metal bag stays home; sortie export floor(endMetal/1000) ADDS "
            "to faction 1km$ (fieldStart netted out). Living Tnb build-stakes refund on exfil. "
            "Combat packs ship via map-web / pawn launcher with field ETAs."
        ),
    }


def _is_hv_unit_def(def_name: str, *, adjacent: bool = False) -> bool:
    n = str(def_name or "").lower()
    if not n:
        return False
    if any(tok in n for tok in ("fus", "fusion", "afus", "cafus")):
        return True
    if adjacent and any(tok in n for tok in ("beamer", "annihilator", "cordoom")):
        return True
    return False


def apply_shell_scars(state: Dict[str, Any], result: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Merge living-shell damage into campaign scar ledger (occupation model lock).

    Scars persist per map; wrath is never recorded here. Re-entry templates should
    subtract these units / raise damageFrac on matching pocket/zone.
    """
    mid = canonical_map_id(map_id)
    if not mid:
        return {"applied": 0}
    ledger = state.setdefault("shellScars", {})
    bucket = ledger.setdefault(mid, {"units": [], "byZone": {}, "updatedAt": None})
    incoming = result.get("shellScars")
    if not isinstance(incoming, list):
        incoming = []
    # Also accept destroyedObjectives as soft scars on target zone.
    target = result.get("targetZoneId")
    applied = 0
    for item in incoming:
        if not isinstance(item, dict):
            continue
        defn = item.get("unitDefName")
        hv = bool(item.get("highValue")) or _is_hv_unit_def(str(defn or ""), adjacent=True)
        rec = {
            "zoneId": item.get("zoneId") or target,
            "pocketId": item.get("pocketId"),
            "unitDefName": defn,
            "destroyed": bool(item.get("destroyed", True)),
            "damageFrac": float(item.get("damageFrac") or 1.0),
            "highValue": hv,
            "at": utc_now(),
            "resultKey": result.get("resultKey"),
        }
        bucket["units"].append(rec)
        zid = str(rec.get("zoneId") or "")
        if zid:
            z = bucket["byZone"].setdefault(zid, {"destroyedCount": 0, "damageSum": 0.0})
            if rec["destroyed"]:
                z["destroyedCount"] = int(z.get("destroyedCount") or 0) + 1
            z["damageSum"] = float(z.get("damageSum") or 0.0) + float(rec["damageFrac"])
            # Mirror into zoneMemory abstract scar pressure.
            zm = (state.get("zoneMemory") or {}).get(mid, {}).get(zid)
            if isinstance(zm, dict):
                absr = zm.setdefault("abstract", {})
                absr["shellScar"] = round(min(1.0, float(absr.get("shellScar") or 0.0) + 0.15), 4)
        applied += 1
    # Cap unit list growth
    if len(bucket.get("units") or []) > 400:
        bucket["units"] = bucket["units"][-300:]
    bucket["updatedAt"] = utc_now()
    return {"applied": applied, "mapId": mid}


_CENTER_SNAP_OFFSETS = (0.007, 0.021)
_CENTER_SNAP_TOL = 0.002


def _authored_map_size(map_id: str) -> Optional[Tuple[float, float]]:
    """Spring elmo size of an authored map, or None when the baseline is missing."""
    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "scenarios"
        / "authored"
        / f"{map_id}.authored_baseline.json"
    )
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    mp = data.get("map") if isinstance(data, dict) else None
    if not isinstance(mp, dict):
        return None
    try:
        sx = float(mp.get("sizeX") or 0)
        sz = float(mp.get("sizeZ") or 0)
    except (TypeError, ValueError):
        return None
    if sx < 512 or sz < 512:
        return None
    return sx, sz


def _center_snap_hit(v: float, size: float) -> bool:
    if size < 512 or v < 1.5:
        return False
    d = abs(v / size - 0.5)
    return any(abs(d - off) < _CENTER_SNAP_TOL for off in _CENTER_SNAP_OFFSETS)


def _is_center_snap_artifact(x: float, z: float, size: Optional[Tuple[float, float]]) -> bool:
    """True when both axes sit on the old four-point map-center lattice.

    shellCoord used to treat elmos as broken normalized coords and park every
    pad on 0.5 ± 0.007 and ± 0.021. Those points are not where the player built.
    """
    if not size:
        return False
    return _center_snap_hit(x, size[0]) and _center_snap_hit(z, size[1])


def apply_player_footprint(state: Dict[str, Any], result: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Persist player-built structures so the next Drop rehydrates them.

    Living-shell occupation stays on the scar/heldInstall path. This is the
    single concrete SoT for company-built pads (labs, solars, LLTs, factories).
    Last extract wins per map — no merge with approximate baseSnapshot counts.

    Absent key = keep prior bag (truncated/legacy results must not wipe pads).
    Explicit [] = intentional clear.
    Units parked on the old map-center lattice (0.5 ± 0.007 / ± 0.021 on both
    axes) are a teleport artifact. A result that contains any of those points
    keeps this map's real pads and drops the lattice, instead of last-extract
    wins. A clean result still replaces the bag.
    """
    mid = canonical_map_id(map_id)
    if not mid:
        return {"kept": 0}
    footprints = state.setdefault("playerFootprints", {})
    has_key = ("playerFootprint" in result) or ("zoneFootprint" in result)
    if not has_key:
        prior = ((footprints.get(mid) or {}).get("units") or [])
        return {"kept": len(prior) if isinstance(prior, list) else 0, "skipped": "absent", "mapId": mid}
    incoming = result.get("playerFootprint")
    if not isinstance(incoming, list):
        incoming = result.get("zoneFootprint") if isinstance(result.get("zoneFootprint"), list) else []
    units: List[Dict[str, Any]] = []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        defn = str(item.get("unitDefName") or item.get("def") or "").strip()
        if not defn:
            continue
        try:
            x = float(item.get("x") or 0)
            z = float(item.get("z") or 0)
        except (TypeError, ValueError):
            continue
        try:
            facing = int(item.get("facing") or 0)
        except (TypeError, ValueError):
            facing = 0
        try:
            hp = float(item.get("hpFrac") or 1.0)
        except (TypeError, ValueError):
            hp = 1.0
        units.append({
            "unitDefName": defn,
            "x": x,
            "z": z,
            "facing": facing,
            "hpFrac": max(0.05, min(1.0, hp)),
            "zoneId": str(item.get("zoneId") or result.get("deploymentZoneId") or ""),
            "owner": "player",
            "role": str(item.get("role") or "player_footprint"),
        })
        if len(units) >= 64:
            break
    size = _authored_map_size(mid)
    prior_bag = footprints.get(mid) if isinstance(footprints.get(mid), dict) else {}
    prior_units = prior_bag.get("units") if isinstance(prior_bag.get("units"), list) else []

    def _without_lattice(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        kept_rows: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                rx = float(row.get("x") or 0)
                rz = float(row.get("z") or 0)
            except (TypeError, ValueError):
                continue
            if _is_center_snap_artifact(rx, rz, size):
                continue
            kept_rows.append(row)
        return kept_rows

    lattice_hits = sum(
        1
        for row in units
        if _is_center_snap_artifact(float(row["x"]), float(row["z"]), size)
    )
    # A center-snap extract is the teleported pile. Keep the pads that were
    # actually built on this map, and do not let an all-lattice list wipe them.
    # A clean extract (no lattice signature) still replaces the bag, so
    # buildings the player destroyed stay gone.
    if lattice_hits:
        merged = _without_lattice(prior_units)
        for row in _without_lattice(units):
            defn = str(row.get("unitDefName") or "")
            rx = float(row["x"])
            rz = float(row["z"])
            duplicate = False
            for old in merged:
                if str(old.get("unitDefName") or "") != defn:
                    continue
                try:
                    ox = float(old.get("x") or 0)
                    oz = float(old.get("z") or 0)
                except (TypeError, ValueError):
                    continue
                if abs(ox - rx) <= 80 and abs(oz - rz) <= 80:
                    duplicate = True
                    break
            if not duplicate:
                merged.append(row)
        if not merged and prior_units:
            return {
                "kept": len(prior_units),
                "skipped": "center_snap_kept_prior",
                "latticeHits": lattice_hits,
                "mapId": mid,
            }
        units = merged[:64]
    footprints[mid] = {
        "mapId": mid,
        "updatedAt": utc_now(),
        "resultKey": result.get("resultKey"),
        "deploymentZoneId": result.get("deploymentZoneId"),
        "units": units,
    }
    report: Dict[str, Any] = {"kept": len(units), "mapId": mid}
    if lattice_hits:
        report["latticeHits"] = lattice_hits
        report["merged"] = True
    return report


def apply_surviving_installs(state: Dict[str, Any], result: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Persist standing fusion vaults so they remain when the player returns.

    Contested vaults stay enemy-owned. Player-owned / held vaults schedule a
    defend threat — aggression that would wipe the pad becomes a defend sortie
    instead of a silent offscreen delete.
    """
    mid = canonical_map_id(map_id)
    if not mid:
        return {"kept": 0}
    incoming = result.get("survivingInstalls") or result.get("survivingInstallations") or []
    if not isinstance(incoming, list):
        incoming = []
    held = state.setdefault("heldInstallations", {})
    map_held = held.setdefault(mid, {})
    if not isinstance(map_held, dict):
        map_held = {}
        held[mid] = map_held
    kept = 0
    threats = 0
    standing_pockets = set()
    for item in incoming:
        if not isinstance(item, dict):
            continue
        pocket = str(item.get("pocketId") or "")
        if not pocket:
            continue
        standing_pockets.add(pocket)
        owner = str(item.get("owner") or "enemy")
        zone = str(item.get("zoneId") or "")
        # Zone flip this sortie upgrades contested prize → company held.
        flipped = bool(result.get("zoneFlipped"))
        target = str(result.get("targetZoneId") or "")
        if flipped and zone and zone == target:
            owner = "player"
        rec = {
            "pocketId": pocket,
            "zoneId": zone,
            "installationId": str(item.get("installationId") or f"{mid}::{pocket}"),
            "owner": owner,
            "status": "standing",
            "highValue": True,
            "units": item.get("units") if isinstance(item.get("units"), list) else [],
            "updatedAt": utc_now(),
            "resultKey": result.get("resultKey"),
        }
        if owner == "player":
            # Justified aggression: next hub pass can offer defend_install.
            pending = state.setdefault("pendingDefendThreats", {})
            map_threats = pending.setdefault(mid, {})
            if not isinstance(map_threats, dict):
                map_threats = {}
                pending[mid] = map_threats
            map_threats[pocket] = {
                "pocketId": pocket,
                "zoneId": zone,
                "installationId": rec["installationId"],
                "reason": "territory_aggression",
                "scheduledAt": utc_now(),
                "severity": "defend_install",
            }
            threats += 1
        map_held[pocket] = rec
        kept += 1
    # Mark held installs absent from this snapshot as destroyed if we fought
    # their zone hard (scar ledger killed the vault).
    scars = ((state.get("shellScars") or {}).get(mid) or {}).get("units") or []
    dead_hv: set[str] = set()
    adjacent_hits: Dict[str, int] = {}
    for s in scars:
        if not isinstance(s, dict) or not s.get("destroyed"):
            continue
        defn = str(s.get("unitDefName") or "")
        pid = str(s.get("pocketId") or "")
        if not pid:
            continue
        if _is_hv_unit_def(defn, adjacent=False) or s.get("highValue"):
            if _is_hv_unit_def(defn, adjacent=False):
                dead_hv.add(pid)
            else:
                adjacent_hits[pid] = adjacent_hits.get(pid, 0) + 1
        elif _is_hv_unit_def(defn, adjacent=True):
            adjacent_hits[pid] = adjacent_hits.get(pid, 0) + 1
    for pid, hits in adjacent_hits.items():
        if hits >= 3:
            dead_hv.add(pid)
    # Completed bonus_fus_* secondaries are hard vault-death witnesses.
    secs = result.get("secondaryResults") or []
    if isinstance(secs, list):
        for sr in secs:
            if not isinstance(sr, dict):
                continue
            sid = str(sr.get("id") or sr.get("objectiveId") or "")
            if not sid.startswith("bonus_fus_"):
                continue
            done = bool(sr.get("completed")) or int(sr.get("destroyed") or sr.get("destroyedCount") or 0) > 0
            if not done:
                continue
            pid = str(sr.get("pocketId") or sid.replace("bonus_fus_", "", 1))
            if pid:
                dead_hv.add(pid)
    for pid in dead_hv:
        rec = map_held.get(pid) if isinstance(map_held.get(pid), dict) else {
            "pocketId": pid,
            "zoneId": "",
            "installationId": f"{mid}::{pid}",
            "owner": "enemy",
            "highValue": True,
        }
        rec["status"] = "destroyed"
        rec["destroyedAt"] = utc_now()
        rec["highValue"] = True
        map_held[pid] = rec
        pending = (state.get("pendingDefendThreats") or {}).get(mid) or {}
        if isinstance(pending, dict):
            pending.pop(pid, None)
    for pid, rec in list(map_held.items()):
        if not isinstance(rec, dict):
            continue
        if pid in dead_hv:
            continue
        if pid not in standing_pockets and str(rec.get("status") or "") == "standing":
            # Still believed standing if we simply weren't on that pad this sortie.
            pass
    return {"kept": kept, "threats": threats, "mapId": mid, "destroyedHv": sorted(dead_hv)}


def apply_abstract_regrow(state: Dict[str, Any], map_id: str, elapsed_minutes: float) -> Dict[str, Any]:
    """Partial heal of shell scars between sorties (campaign-time regrow pressure).

    Capture holds under live regrow; offline, scars slowly recover so re-entry
    is not permanent empty grass. Delegates to capture_node_claims when present.
    """
    try:
        import capture_node_claims as cnc  # type: ignore

        return cnc.apply_abstract_regrow(state, map_id, elapsed_minutes)
    except Exception:
        # Lightweight inline fallback (same shape).
        mid = canonical_map_id(map_id)
        if not mid or elapsed_minutes <= 0:
            return {"regrown": 0, "mapId": mid}
        hours = float(elapsed_minutes) / 60.0
        heal = min(0.85, 0.12 * hours)
        ledger = (state.get("shellScars") or {}).get(mid) or {}
        by_zone = ledger.get("byZone") or {}
        n = 0
        for zid, z in list(by_zone.items()):
            if not isinstance(z, dict):
                continue
            dmg = float(z.get("damageSum") or 0.0)
            if dmg <= 0:
                continue
            z["damageSum"] = round(max(0.0, dmg * (1.0 - heal)), 4)
            dc = int(z.get("destroyedCount") or 0)
            z["destroyedCount"] = max(0, int(round(dc * (1.0 - heal * 0.5))))
            n += 1
            zm = (state.get("zoneMemory") or {}).get(mid, {}).get(zid)
            if isinstance(zm, dict):
                absr = zm.setdefault("abstract", {})
                scar = float(absr.get("shellScar") or 0.0)
                absr["shellScar"] = round(max(0.0, scar * (1.0 - heal)), 4)
                absr["regrowPressure"] = round(min(1.0, heal + scar * 0.3), 4)
        return {"regrown": n, "mapId": mid, "heal": round(heal, 4)}


def ensure_faction_banks(state: Dict[str, Any]) -> Dict[str, Any]:
    """World paint: per-faction Tenebrium banks (Armada crisis = 0)."""
    flags = state.setdefault("worldFlags", {})
    flags.setdefault("armadaTenebriumCrisis", True)
    banks = state.setdefault("factionBanks", {})
    banks.setdefault("armada", 0 if flags.get("armadaTenebriumCrisis", True) else 3)
    banks.setdefault("cortex", int(banks.get("cortex", 2) or 2))
    banks.setdefault("nullmercs", int((state.get("commerce") or {}).get("tenebrium") or 0))
    banks.setdefault("ashwalkers", int((state.get("commerce") or {}).get("tenebrium") or 0))
    if flags.get("armadaTenebriumCrisis", True):
        banks["armada"] = 0
    return banks


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

# The player's raid-to-factories transition: ground on other maps softens
# during the window, and (see capture_node_claims.claim_rate_mult) the
# claim that follows presses harder than baseline once it closes.
REGRESSION_START, REGRESSION_END, REGRESSION_PRESSURE = 4, 6, 0.12


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
    here = Path(__file__).resolve().parent.parent
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
    roots.append(Path(__file__).resolve().parent.parent / "data" / "hydrology")
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


def settle_commerce_after_sortie(
    state: Dict[str, Any],
    result: Dict[str, Any],
    success: bool,
    clean: bool,
    zone_flipped: bool,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Award Tenebrium + bank end-metal as 1km$; settle loan packages."""
    catalog = load_commerce_catalog(workspace)
    commerce = ensure_commerce(state, workspace)
    ensure_faction_banks(state)
    rewards = catalog.get("sortieRewards") or {}
    rng_seed = hashlib.md5(
        f"{result.get('resultKey')}|{state.get('missionNumber')}|commerce".encode("utf-8")
    ).hexdigest()

    def _roll(tag: str) -> float:
        h = hashlib.md5(f"{rng_seed}|{tag}".encode("utf-8")).hexdigest()
        return int(h[:8], 16) / float(0xFFFFFFFF)

    gained_t = 0
    gained_k = 0
    notes: List[str] = []

    def _award_range(spec: Any, tag: str) -> int:
        if not isinstance(spec, dict) or not spec:
            return 0
        chance = float(spec.get("chance", 1.0) or 1.0)
        if _roll(tag + ":p") > chance:
            return 0
        lo = int(spec.get("min", 0) or 0)
        hi = int(spec.get("max", lo) or lo)
        if hi < lo:
            hi = lo
        if lo == hi:
            return lo
        span = hi - lo + 1
        return lo + int(_roll(tag + ":v") * span) % span

    # Capture / freeTnbMint=false: no free Tnb rolls (reclaim bank only).
    free_tnb = True
    try:
        from capture_node_claims import free_tnb_mint_allowed  # type: ignore

        free_tnb = free_tnb_mint_allowed(result)
    except Exception:
        if (
            result.get("freeTnbMint") is False
            or result.get("nodeClaimed")
            or result.get("captureMode") in (True, "clear_hold_shell")
        ):
            free_tnb = False

    if success:
        if free_tnb:
            gained_t += _award_range(rewards.get("tenebriumOnVictory") or {}, "tv")
    # Zone flip: catalog default chance=0; hard-block when free mint disallowed.
    if zone_flipped and free_tnb:
        flip_t = _award_range(rewards.get("tenebriumOnZoneFlip") or {"min": 0, "max": 0, "chance": 0}, "tz")
        if flip_t > 0:
            notes.append(f"zone-flip Tnb roll={flip_t} (prefer reclaim; free mint discouraged)")
        gained_t += flip_t
    if clean and free_tnb:
        gained_t += _award_range(rewards.get("tenebriumOnCleanExtract") or {}, "tc")
    if not free_tnb:
        notes.append("node claim: no free Tnb mint (reclaim bank only)")

    # Campaign metal export: floor(end stockpile / 1000). Prefer metalKExtracted.
    # Bag stays HOME — export ADDS to faction totals (never replaces the bag).
    metal_unit = int(((catalog.get("metal") or {}).get("unitMetal")) or METAL_UNIT)
    try:
        metal_stored = float(result.get("metalStored"))
    except (TypeError, ValueError):
        metal_stored = -1.0
    try:
        metal_k_field = int(float(result.get("metalKExtracted")))
    except (TypeError, ValueError):
        metal_k_field = -1
    if metal_k_field >= 0:
        raw_export_k = metal_k_field
    elif metal_stored >= 0:
        raw_export_k = int(math.floor(metal_stored / float(metal_unit)))
    else:
        raw_export_k = 0
    try:
        metal_k_brought = int(float(result.get("metalKBrought")))
    except (TypeError, ValueError):
        metal_k_brought = -1  # unknown / legacy result
    try:
        metal_k_field_start = int(float(result.get("metalKFieldStart") or 0))
    except (TypeError, ValueError):
        metal_k_field_start = 0
    if metal_k_field_start < 0:
        metal_k_field_start = 0

    # WO-043c: end-of-sortie bank is authoritative liquid stock.
    # Lua refunds living build-stakes into bank on exfil before writing this.
    try:
        loot_field = int(float(result.get("tenebriumLooted") or 0))
    except (TypeError, ValueError):
        loot_field = 0
    try:
        bank_end = int(float(result.get("tenebriumBank") or -1))
    except (TypeError, ValueError):
        bank_end = -1
    try:
        spent_field = int(float(result.get("tenebriumSpent") or 0))
    except (TypeError, ValueError):
        spent_field = 0
    try:
        lost_field = int(float(result.get("tenebriumLost") or 0))
    except (TypeError, ValueError):
        lost_field = 0
    try:
        living_stakes = int(float(result.get("tenebriumLivingStakes") or result.get("tenebriumInvested") or 0))
    except (TypeError, ValueError):
        living_stakes = 0

    if bank_end >= 0:
        # Live bank (incl. exfil stake refund) is authoritative; awards stack on top.
        prev = int(commerce.get("tenebrium") or 0)
        award_extra = gained_t  # victory / flip / extract rolls already in gained_t
        commerce["tenebrium"] = bank_end + award_extra
        if bank_end != prev:
            notes.append(f"Tenebrium bank {prev} → {bank_end} (field)")
        if award_extra:
            notes.append(f"+{award_extra} Tenebrium (sortie awards)")
        if loot_field:
            notes.append(f"reclaimed {loot_field} Tnb from wrecks/shards")
        if living_stakes:
            notes.append(f"exfil refunded {living_stakes} Tnb from living builds")
        if spent_field:
            notes.append(f"spent {spent_field} Tnb on build-power units (net after exfil refund)")
        if lost_field:
            notes.append(f"lost {lost_field} Tnb (wrecks vaporized)")
        gained_t = award_extra + max(0, bank_end - prev)
    else:
        if loot_field > 0:
            gained_t += loot_field
            notes.append(f"+{loot_field} Tenebrium (reclaim loot)")
        if living_stakes > 0:
            gained_t += living_stakes
            notes.append(f"+{living_stakes} Tenebrium (exfil living-stake refund)")
        commerce["tenebrium"] = int(commerce.get("tenebrium") or 0) + gained_t
        if gained_t and loot_field <= 0 and living_stakes <= 0:
            notes.append(f"+{gained_t} Tenebrium")
        elif gained_t and (loot_field > 0 or living_stakes > 0) and gained_t > (loot_field + living_stakes):
            notes.append(f"+{gained_t - loot_field - living_stakes} Tenebrium (sortie awards)")

    # Metal: ADD export to faction bag. Never replace.
    # - New path (metalKBrought==0): bag stayed home; ADD max(0, export - fieldStart).
    # - Legacy path (metalKBrought>0): bag was dumped onto map; ADD net delta
    #   (export - brought) so spending bag metal still reduces the bag.
    prev_metal_k = int(commerce.get("metalK") or 0)
    if metal_k_field >= 0 or metal_stored >= 0 or raw_export_k:
        if metal_k_brought > 0:
            delta_k = int(raw_export_k) - metal_k_brought
            commerce["metalK"] = max(0, prev_metal_k + delta_k)
            mode = "legacy_delta"
        else:
            # Net out operating field seed so unused allotment does not inflate bag.
            export_k = max(0, int(raw_export_k) - metal_k_field_start)
            delta_k = export_k
            commerce["metalK"] = prev_metal_k + export_k
            mode = "add"
        if delta_k != 0:
            sign = "+" if delta_k > 0 else ""
            notes.append(
                f"{sign}{delta_k}×1km$ metal ({mode}; export={raw_export_k} "
                f"fieldStart={metal_k_field_start} brought={metal_k_brought if metal_k_brought >= 0 else '?'}; "
                f"bag {prev_metal_k}→{commerce['metalK']})"
            )
            commerce.setdefault("ledger", []).append({
                "op": "metal_export_add" if mode == "add" else "metal_field_settle",
                "metalK": commerce["metalK"],
                "prevMetalK": prev_metal_k,
                "metalKExtracted": int(raw_export_k),
                "metalKFieldStart": metal_k_field_start,
                "metalKBrought": metal_k_brought if metal_k_brought >= 0 else None,
                "metalStored": int(metal_stored) if metal_stored >= 0 else None,
                "deltaK": delta_k,
                "mode": mode,
                "at": utc_now(),
            })
        gained_k = delta_k
    elif raw_export_k:
        commerce["metalK"] = prev_metal_k + raw_export_k
        notes.append(f"+{raw_export_k}×1km$ metal (end stock {int(metal_stored) if metal_stored >= 0 else '?'})")
        commerce.setdefault("ledger", []).append({
            "op": "metal_bank",
            "metalK": raw_export_k,
            "metalStored": metal_stored if metal_stored >= 0 else None,
            "at": utc_now(),
            "missionNumber": int(state.get("missionNumber", 1) or 1),
        })
        gained_k = raw_export_k
    # Persistent world flag: Armada Tenebrium crisis (spent on decoy farms).
    state.setdefault("worldFlags", {})["armadaTenebriumCrisis"] = True
    if result.get("armadaTenebriumCrisis") is False:
        state["worldFlags"]["armadaTenebriumCrisis"] = False

    survivors = result.get("playerSurvivors") if isinstance(result.get("playerSurvivors"), dict) else {}
    # loanUnitHp: unitDef -> { count, avgHpFrac, minHpFrac } (result contract v2)
    loan_hp = result.get("loanUnitHp") if isinstance(result.get("loanUnitHp"), dict) else {}
    listings = catalog.get("listings") or {}
    rep = state.setdefault("reputation", {})
    for lid, rec in list((commerce.get("owned") or {}).items()):
        if not isinstance(rec, dict) or not rec.get("loan"):
            continue
        listing = listings.get(lid) or {}
        unit_def = str(rec.get("unitDef") or listing.get("unitDef") or "")
        loan_n = int(rec.get("loanCount") or listing.get("count") or 0)
        if not unit_def or loan_n <= 0:
            continue
        alive = int(float(survivors.get(unit_def) or 0))
        # Loaned quality: default smoking packs ship ~0.4 avg HP; "better shape"
        # means count OK and avgHpFrac improved (or unknown HP → count-only legacy).
        loaned_frac = float(rec.get("healthFrac") or listing.get("healthFrac") or 0.42)
        hp_info = loan_hp.get(unit_def) if isinstance(loan_hp.get(unit_def), dict) else {}
        avg_hp = hp_info.get("avgHpFrac")
        quality_ok = True
        if avg_hp is not None:
            try:
                quality_ok = float(avg_hp) >= min(0.95, loaned_frac + 0.08)
            except (TypeError, ValueError):
                quality_ok = True
        count_ok = alive >= loan_n
        returned_well = success and count_ok and quality_ok
        if returned_well:
            bonus = rewards.get("loanReturnBonus") or {}
            k_bonus = int(bonus.get("metalK") if bonus.get("metalK") is not None else bonus.get("credits") or 0)
            # Legacy scrap tip (±25) → clamp to ±1 km$ if still using credits key.
            if bonus.get("metalK") is None and abs(k_bonus) > 5:
                k_bonus = 1 if k_bonus > 0 else -1
            r_bonus = float(bonus.get("nullmercRep") or 0)
            commerce["metalK"] = int(commerce.get("metalK") or 0) + k_bonus
            gained_k += k_bonus
            if r_bonus:
                rep["nullmercs"] = round(float(rep.get("nullmercs") or 0) + r_bonus, 2)
            if float(bonus.get("tenebriumChance") or 0) > 0 and _roll(f"loan:{lid}") < float(bonus["tenebriumChance"]):
                commerce["tenebrium"] = int(commerce.get("tenebrium") or 0) + 1
                gained_t += 1
                notes.append(f"loan {lid}: broker tips 1 Tenebrium")
            shape = f"avgHp={avg_hp}" if avg_hp is not None else "count-only"
            notes.append(f"loan {lid}: returned {alive}/{loan_n} in better shape ({shape})")
            commerce.setdefault("ledger", []).append({
                "op": "loan_return_ok",
                "listingId": lid,
                "alive": alive,
                "loanCount": loan_n,
                "avgHpFrac": avg_hp,
                "at": utc_now(),
            })
        elif (not success) or alive < max(1, int(math.ceil(loan_n * 0.5))) or (success and count_ok and not quality_ok):
            pen = rewards.get("loanBreachPenalty") or {}
            # Soft quality miss: half penalty if count ok but still smoking.
            soft = success and count_ok and not quality_ok
            k_pen = int(pen.get("metalK") if pen.get("metalK") is not None else pen.get("credits") or 0)
            if pen.get("metalK") is None and abs(k_pen) > 5:
                k_pen = -1 if k_pen < 0 else 1
            r_pen = float(pen.get("nullmercRep") or 0)
            if soft:
                k_pen = int(math.floor(k_pen * 0.5)) if k_pen else 0
                r_pen = r_pen * 0.5
                notes.append(f"loan {lid}: quality miss ({alive}/{loan_n}, avgHp={avg_hp})")
            else:
                notes.append(f"loan {lid}: breach ({alive}/{loan_n} returned)")
            commerce["metalK"] = max(0, int(commerce.get("metalK") or 0) + k_pen)
            gained_k += k_pen
            if r_pen:
                rep["nullmercs"] = round(float(rep.get("nullmercs") or 0) + r_pen, 2)
            commerce.setdefault("ledger", []).append({
                "op": "loan_return_quality_miss" if soft else "loan_return_breach",
                "listingId": lid,
                "alive": alive,
                "loanCount": loan_n,
                "avgHpFrac": avg_hp,
                "at": utc_now(),
            })

    commerce.setdefault("ledger", []).append({
        "op": "sortie_settle",
        "tenebriumGained": gained_t,
        "metalKGained": gained_k,
        "success": success,
        "zoneFlipped": zone_flipped,
        "at": utc_now(),
        "missionNumber": int(state.get("missionNumber", 1) or 1),
    })
    if len(commerce.get("ledger") or []) > 80:
        commerce["ledger"] = commerce["ledger"][-60:]
    # Cross-map army carry: bank living mobile armyValue into armyBudget.
    army_bank = apply_army_budget_from_result(state, result, workspace=workspace)
    if army_bank.get("gained"):
        notes.append(
            f"+{army_bank['gained']} army bank (field armyValue={army_bank.get('armyValue', 0)}; "
            f"bag={army_bank.get('armyBudget', 0)})"
        )

    # Keep faction bank mirror for null/ash in sync with commerce bag.
    banks = ensure_faction_banks(state)
    banks["nullmercs"] = int(commerce.get("tenebrium") or 0)
    banks["ashwalkers"] = int(commerce.get("tenebrium") or 0)
    return {
        "tenebrium": commerce["tenebrium"],
        "metalK": commerce["metalK"],
        "armyBudget": int(commerce.get("armyBudget") or 0),
        "armyBudgetGained": int(army_bank.get("gained") or 0),
        "gainedTenebrium": gained_t,
        "gainedMetalK": gained_k,
        "notes": notes,
        "factionBanks": banks,
    }


def ensure_roster(state: Dict[str, Any]) -> Dict[str, Any]:
    default = default_v1_state()["roster"]
    roster = state.setdefault("roster", copy.deepcopy(default))
    commander = roster.setdefault("commander", {})
    for key, value in default["commander"].items():
        commander.setdefault(key, copy.deepcopy(value))
    roster.setdefault("cadre", {})
    roster.setdefault("cadreCap", CADRE_CAP_BASE)
    roster.setdefault("cadreXp", {})
    heroes = roster.setdefault("heroes", [])
    known = {str(h.get("heroId")) for h in heroes if isinstance(h, dict)}
    for hero in default["heroes"]:
        if hero["heroId"] not in known:
            heroes.append(copy.deepcopy(hero))
            known.add(str(hero["heroId"]))
    # Drop 3 Wave 2: authored roster heroes join locked; recruitment beats
    # (apply_recruitment_beats) unlock them when their moment lands.
    authored_rows = [h for h in load_hero_roster() if isinstance(h, dict) and h.get("heroId")]
    authored = {str(h.get("heroId")): h for h in authored_rows}
    for hero in authored_rows:
        hid = str(hero.get("heroId"))
        if hid and hid not in known:
            rec = copy.deepcopy(hero)
            rec.setdefault("status", "locked")
            heroes.append(rec)
            known.add(hid)
    # Drop scrapped locked heroes that left the authored catalog (e.g. mirren).
    # Keep anyone still active / wounded / dead on the company roll.
    if authored:
        kept = []
        for hero in heroes:
            if not isinstance(hero, dict):
                continue
            hid = str(hero.get("heroId") or "")
            st = str(hero.get("status") or "").lower()
            if hid in authored or st in ("active", "wounded", "dead", "lost"):
                kept.append(hero)
        heroes[:] = kept
        known = {str(h.get("heroId")) for h in heroes if isinstance(h, dict)}
    # Seed campaignXp from any existing character sheet (legacy integer XP).
    # Also refresh display names / chassis from the authored catalog so the
    # webGUI never keeps leftovers like "Grath Unpaid".
    chars = state.get("characters") or {}
    for hero in heroes:
        if not isinstance(hero, dict):
            continue
        for key, value in {"status": "active", "xp": 0.0, "campaignXp": 0.0,
                           "timesWounded": 0, "missionCritical": False,
                           "peakBarXp": 0.0}.items():
            hero.setdefault(key, value)
        hid = str(hero.get("heroId") or "")
        src = authored.get(hid)
        if isinstance(src, dict):
            if src.get("name"):
                hero["name"] = src["name"]
            if src.get("unitDef"):
                hero["unitDef"] = src["unitDef"]
            if src.get("fiction") and not hero.get("fiction"):
                hero["fiction"] = src.get("fiction")
        c = chars.get(hid) if isinstance(chars, dict) else None
        if isinstance(c, dict):
            if isinstance(src, dict) and src.get("name"):
                c["name"] = src["name"]
            if isinstance(src, dict) and src.get("unitDef"):
                c["unitDef"] = src["unitDef"]
            if float(hero.get("campaignXp") or 0) <= 0:
                # Character sheet used big integers (e.g. 1480); scale into ladder.
                sheet = float(c.get("xp") or 0)
                if sheet >= 50:
                    hero["campaignXp"] = round(sheet * 0.08, 2)  # 1480 → ~118 (L2)
                elif sheet > 0:
                    hero["campaignXp"] = sheet
        # Floor BAR xp from campaign ladder so new saves feel proven, not empty.
        camp = float(hero.get("campaignXp") or 0.0)
        peak = max(float(hero.get("peakBarXp") or 0.0), float(hero.get("xp") or 0.0))
        hero["peakBarXp"] = peak
        hero["xp"] = bar_unit_xp_from_campaign(camp, peak)
        hero["level"] = hero_level_from_campaign_xp(camp)
        hero["rank"] = normalize_hero_rank_label(hero_rank_label(int(hero["level"])))
    # Soft auto-unlock: high Null Merc rep can free Spoke without broker coins
    # (broker listing still works; this is the reputation path).
    maybe_unlock_wheelie_hero(state)
    ensure_progression(state)
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


def _sortie_xp_gains(state: Dict[str, Any], result: Dict[str, Any], success: bool, clean: bool) -> Dict[str, float]:
    """Commander + hero campaign XP for this sortie (mode-aware, farm-boosted)."""
    prog = ensure_progression(state)
    cracked = str(prog.get("mode", "cracked_farm")).lower() == "cracked_farm"
    mult = float(prog.get("xpMultiplier", 1.0) or 1.0)
    farm = bool(result.get("farmSortie")) or "farm" in (result.get("storyTags") or [])
    # Base gains: cracked_farm is generous so end-of-campaign heroes are monsters.
    if success:
        cmd = 52.0 + (12.0 if clean else 0.0)
        hero = 70.0 if cracked else 38.0
        if clean:
            hero += 12.0
    elif result.get("status") in ("defeat", "failed", "failure"):
        cmd = 14.0 if cracked else 8.0
        hero = 28.0 if cracked else 12.0  # death still teaches; XP never wiped
    else:
        cmd = 22.0 if cracked else 16.0
        hero = 40.0 if cracked else 20.0
    if farm:
        hero *= 1.85
        cmd *= 1.35
    return {
        "commander": round(cmd * mult, 2),
        "hero": round(hero * mult, 2),
    }


def update_roster(state: Dict[str, Any], result: Dict[str, Any], success: bool, clean: bool) -> Dict[str, Any]:
    """Grow the warband from survivors, level the commander, scar it on defeat.
    Backward-compatible: a result without playerSurvivors leaves the cadre as-is.

    XP rule (operator request 2026-07): campaign XP and peak BAR experience
    NEVER reset on death. Death/wound changes status only; the ladder stays.
    """
    roster = ensure_roster(state)
    commander = roster["commander"]
    status = result.get("status", "unknown")
    defeat = status in ("defeat", "failed", "failure")
    gains = _sortie_xp_gains(state, result, success, clean)

    # The command ledger grows only while the walker is on the field.
    if commander.get("unlocked") is True:
        commander["xp"] = round(float(commander.get("xp", 0.0) or 0.0) + gains["commander"], 2)
        new_level = roster_level_for_xp(commander["xp"])
        if new_level > int(commander.get("level", 1)):
            for lvl in range(int(commander.get("level", 1)) + 1, new_level + 1):
                perk = PERK_LADDER.get(lvl)
                if perk and perk not in commander.setdefault("perks", []):
                    commander["perks"].append(perk)
            commander["level"] = new_level
    # Cap = perk base + act-2 grant bonus (earned specials never squeeze T1 vets).
    roster["cadreCap"] = commander_cadre_cap(commander) + grant_cap_bonus(roster)

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

    # Veteran XP bank by unitDef — majority retain between drops.
    # Named heroes already track peakBarXp; this covers packs / escorts / cadre.
    _merge_cadre_xp(roster, result, defeat=defeat)

    # Scars: a lost commander limps into the next sortie (perks suppressed then).
    expire_scars(commander, int(state.get("missionNumber", 1)))
    if defeat:
        commander.setdefault("scars", []).append({
            "kind": "wounded",
            "sinceMission": int(state.get("missionNumber", 1)),
            "untilMission": int(state.get("missionNumber", 1)) + 1,
        })

    # Named heroes: Fire Emblem status from gadget heroResults / namedOutcomes.
    # WO-008: dead means dead (status), but XP is permanent.
    for hero in roster.get("heroes", []) or []:
        if isinstance(hero, dict) and hero.get("status") == "wounded":
            hero["status"] = "active"

    hero_results = result.get("heroResults") if isinstance(result.get("heroResults"), dict) else {}
    named_outcomes = result.get("namedOutcomes")
    by_named = {}
    if isinstance(named_outcomes, list) and named_outcomes:
        by_named = {str(o.get("charId")): o for o in named_outcomes if isinstance(o, dict)}

    for hero in roster.get("heroes", []) or []:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("heroId") or "")
        # --- status from named outcomes or heroResults ---
        if hid in by_named:
            res = str(by_named[hid].get("outcome", ""))
            if res == "dead":
                hero["status"] = "dead"
            elif res in ("recovered", "wounded"):
                hero["status"] = "wounded"
                hero["timesWounded"] = int(hero.get("timesWounded", 0) or 0) + 1
            elif res == "survived":
                hero["status"] = "active"
        elif hid in hero_results:
            hr = hero_results[hid]
            if isinstance(hr, dict):
                hr_status = str(hr.get("status", ""))
                if hr_status == "dead":
                    hero["status"] = "dead"
                elif hr_status == "wounded":
                    hero["status"] = "wounded"
                    hero["timesWounded"] = int(hero.get("timesWounded", 0) or 0) + 1
                elif hr_status == "survived":
                    hero["status"] = "active"

        # --- XP: always grow for heroes that appeared in the result; never drop ---
        deployed = hid in by_named or hid in hero_results or not (by_named or hero_results)
        camp_gain = 0.0
        if deployed:
            prev_camp = float(hero.get("campaignXp") or 0.0)
            # Survivors/wounded get full gain; dead still bank a partial (they fought).
            if hero.get("status") == "dead":
                camp_gain = gains["hero"] * 0.65
            elif hero.get("status") == "wounded":
                camp_gain = gains["hero"] * 0.9
            else:
                camp_gain = gains["hero"]
            hero["campaignXp"] = round(prev_camp + camp_gain, 2)

        peak = max(float(hero.get("peakBarXp") or 0.0), float(hero.get("xp") or 0.0))
        hr = hero_results.get(hid) if isinstance(hero_results.get(hid), dict) else None
        if hr is not None and hr.get("xp") is not None:
            try:
                peak = max(peak, float(hr.get("xp") or 0.0))
            except (TypeError, ValueError):
                pass
        hero["peakBarXp"] = peak
        # Floor BAR combat XP from campaign ladder (cracked heroes by late game).
        hero["xp"] = bar_unit_xp_from_campaign(float(hero.get("campaignXp") or 0.0), peak)
        hero["level"] = hero_level_from_campaign_xp(float(hero.get("campaignXp") or 0.0))
        hero["rank"] = normalize_hero_rank_label(hero_rank_label(int(hero["level"])))
        # Last sortie XP readout for debrief clarity.
        hero["lastSortieXpGain"] = round(camp_gain, 2)

    # Legacy saves: "Blooded" read as wounded — coerce on every homecoming.
    for hero in roster.get("heroes", []) or []:
        if isinstance(hero, dict) and hero.get("rank") is not None:
            hero["rank"] = normalize_hero_rank_label(hero.get("rank"))

    return roster


# Majority retain: packs / escorts keep most of their field XP across drops.
# Heroes already use peakBarXp (100%); cadre uses this keep fraction.
CADRE_XP_KEEP_FRAC = 0.85
CADRE_XP_DEFEAT_FRAC = 0.55


def _merge_cadre_xp(roster: Dict[str, Any], result: Dict[str, Any], *, defeat: bool = False) -> None:
    """Bank per-def combat + craft XP from the match into roster.cadreXp.

    Shape: { unitDef: { xp, craftXp, peakXp, peakCraftXp } }
    xp / craftXp are the *seed* values for the next drop (majority retain).
    """
    detail = result.get("playerSurvivorXp")
    if not isinstance(detail, dict) or not detail:
        return
    keep = CADRE_XP_DEFEAT_FRAC if defeat else CADRE_XP_KEEP_FRAC
    bank = roster.setdefault("cadreXp", {})
    if not isinstance(bank, dict):
        bank = {}
        roster["cadreXp"] = bank
    for unit_def, bag in detail.items():
        if not isinstance(bag, dict):
            continue
        def_name = str(unit_def)
        try:
            peak = float(bag.get("peakXp") or 0.0)
            avg = float(bag.get("avgXp") or 0.0)
            peak_craft = float(bag.get("peakCraftXp") or 0.0)
            avg_craft = float(bag.get("avgCraftXp") or 0.0)
        except (TypeError, ValueError):
            continue
        # Seed from avg (majority of the company), never below prior bank,
        # never above peak. Keep fraction applied to the new field reading.
        field_seed = max(avg, peak * 0.75) * keep
        field_craft = max(avg_craft, peak_craft * 0.75) * keep
        prev = bank.get(def_name) if isinstance(bank.get(def_name), dict) else {}
        prev_xp = float(prev.get("xp") or 0.0)
        prev_craft = float(prev.get("craftXp") or 0.0)
        prev_peak = float(prev.get("peakXp") or 0.0)
        prev_peak_craft = float(prev.get("peakCraftXp") or 0.0)
        bank[def_name] = {
            "xp": round(max(prev_xp * 0.5, field_seed), 4),
            "craftXp": round(max(prev_craft * 0.5, field_craft), 4),
            "peakXp": round(max(prev_peak, peak), 4),
            "peakCraftXp": round(max(prev_peak_craft, peak_craft), 4),
            "avgXp": round(avg, 4),
            "avgCraftXp": round(avg_craft, 4),
        }


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


def reset_live_raptors_but_escalate(state: Dict[str, Any], result: Dict[str, Any], elapsed: float,
                                    workspace: Optional[Path] = None) -> None:
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId"))
    if map_family(map_id) != "wild":
        return
    bloom = update_hydrology_bloom(state, map_id, workspace)
    hazard_map = state.setdefault("hazardState", {}).setdefault(map_id, {})
    destroyed = set(result.get("destroyedObjectiveIds", []) or [])
    for zone_id, hazard in hazard_map.items():
        hive_destroyed = any(zone_id.lower() in str(oid).lower() or "hive" in str(oid).lower() for oid in destroyed)
        if hive_destroyed:
            hazard["hivesSurviving"] = False
            hazard["pressure"] = clamp(float(hazard.get("pressure", 0.0)) * 0.55)
        else:
            hazard["pressure"] = clamp(float(hazard.get("pressure", 0.0)) + 0.01 * elapsed * (1.0 + bloom))
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
        # Drop 4: the kind played, so the quest board can avoid repeating it.
        "objectiveKind": (
            result.get("objectiveArchetype")
            or ((result.get("objectiveTarget") or {}).get("kind")
                if isinstance(result.get("objectiveTarget"), dict) else None)
            or next((str(o.get("kind")) for o in (result.get("objectiveResults") or [])
                     if isinstance(o, dict) and o.get("kind")), None)
        ),
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


def objective_for_map(map_id: str, state: Dict[str, Any],
                      workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Fallback objective for a map, with its target zone id translated forward.

    Every targetZoneId below was authored against a pre-migration zone cut and
    all seven are now retired -- AB_LRPC_EAST_WING, RJ_CENTRAL_LAGOON_MAZE,
    ATS_CENTRAL_HIVE_FLATS, GF_SE_ENERGY_WORKS, EOH_SE_CORTEX_POCKET,
    KOOM_CENTRAL_FLUID_SCAR, TAB_WESTERN_ROCK_GATES. Rather than hand-edit the
    constants on every re-cut (which is what let them go stale in the first
    place), they are translated at the point of use through the same migration
    map canonical_zone_id already reads.

    This path only fires when generate_mode_a_sortie finds no legal contract,
    so it will not show up in an early mission and will show up in a late one.
    """
    raw = _objective_for_map_raw(map_id, state)
    target = raw.get("targetZoneId")
    if target:
        raw["targetZoneId"] = canonical_zone_id(target, workspace)
    return raw


def _objective_for_map_raw(map_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
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
        return {"id": "GF_ARMADA_ENERGY_WORKS", "kind": "eco_raid", "label": "Raid the Armada energy works", "targetZoneId": "GF_SE_ENERGY_WORKS", "enemyFaction": "armada"}
    if mid == "eye_of_horus":
        return {"id": "EOH_CORTEX_DEALER_RELAY", "kind": "strike_relay", "label": "Destroy the Cortex dealer relay", "targetZoneId": "EOH_SE_CORTEX_POCKET", "enemyFaction": "cortex"}
    if mid == "koom_valley":
        return {"id": "KOOM_FLUID_SCAR_FOOTHOLD", "kind": "seize_lane", "label": "Seize the Central Fluid Scar", "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR"}
    if mid == "tabula":
        return {"id": "TAB_ROCK_GATE_CONTROL", "kind": "gate_control", "label": "Control a rock gate and extract", "targetZoneId": "TAB_WESTERN_ROCK_GATES"}
    return {"id": mid + "_objective", "kind": "sortie", "label": "Complete local objective", "targetZoneId": None}


def choose_next_map_zone(state: Dict[str, Any],
                         workspace: Optional[Path] = None) -> Tuple[str, str]:
    """Map and deployment zone for the next mission, zone id translated forward.

    ALPHA_SPINE may still name legacy ids that migrate forward
    (EOH_NW_CRATER_CAMP, KOOM_NW_GREEN_SHELF, …). It is the deployment-zone
    source for every mission whose intent does not specify one.
    nextMapOverride is authored too, so it goes through the same translation
    rather than being trusted.
    """
    requested = state.get("nextMapOverride")
    if requested:
        return (canonical_map_id(requested.get("mapId")),
                canonical_zone_id(requested.get("deploymentZoneId", "unknown_zone"), workspace))
    # Mission number is the act clock. Geography is the collapse, then the
    # landing a heading extract already wrote. ALPHA_SPINE is not a map picker.
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import wet_reach_v1 as _wet  # type: ignore

        arrival = _wet._arrival(state)
        if arrival and arrival.get("mapId") and arrival.get("zoneId"):
            return (
                canonical_map_id(arrival.get("mapId")),
                canonical_zone_id(arrival.get("zoneId"), workspace),
            )
        if workspace is not None:
            collapsed = _wet.collapse_sorties(state, Path(workspace))
            cards = collapsed.get("cards") or []
            if cards:
                effect = cards[0].get("effect") or {}
                return (
                    canonical_map_id(effect.get("mapId")),
                    canonical_zone_id(effect.get("infilZoneId") or "TRJ_NW_OUTER_MUSTER", workspace),
                )
    except Exception:
        pass
    return "the_rock_jungle", canonical_zone_id("TRJ_NW_OUTER_MUSTER", workspace)


# ---------------------------------------------------------------------------
# Act structure (story pacing only — NOT a build lock):
#   Acts still label chapters / finales. Fabrication is unconstrained BAR;
#   Tenebrium + concurrent BP ceiling is the only build-power gate.
#   (Retired Drop-2 techPolicy scaffolding that blocked T2 / structures.)
# ---------------------------------------------------------------------------

ACT1_END_MISSION = 5
ACT2_END_MISSION = 10

ACT_NAMES = {1: "ground_control", 2: "constrained_rts", 3: "unbound_finale"}
ACT_LABELS = {
    1: "Act I — Opening Front: full fab; Tnb gates constructors",
    2: "Act II — Mid Front: full fab; Tnb gates constructors",
    3: "Act III — The Finale: full unconstrained war, massive starts",
}

# Path-keyed finales on the three designated maps (owner map-pool decision):
# ancient_bastion = overthrow (A), all_that_simmers = sovereignty (B),
# the_rock_jungle = spire jump (C).
FINALE_PLANS = {
    "A": {
        "pathKey": "A",
        "kind": "overthrow",
        "mapId": "ancient_bastion",
        "deploymentZoneId": "AB_WESTERN_MUSTER_GROUNDS",
        "title": "Finale — Overthrow",
        "objective": {
            "id": "FINALE_OVERTHROW",
            "kind": "destroy_key_structure",
            "label": "Overthrow — break the Bastion citadel guns and its command post",
            "targetZoneId": "AB_EASTERN_BASTION_WALL",
            "enemyFaction": "armada",
        },
    },
    "B": {
        "pathKey": "B",
        "kind": "sovereignty",
        "mapId": "all_that_simmers",
        "deploymentZoneId": "ATS_NW_CANOPY_START",
        "title": "Finale — Sovereignty",
        "objective": {
            "id": "FINALE_SOVEREIGNTY",
            "kind": "destroy_key_structure",
            "label": "Sovereignty — break both empires' command posts on the simmering ground",
            "targetZoneId": "ATS_NE_ARMADA_RIDGE",
            "enemyFaction": "armada",
        },
    },
    "C": {
        "pathKey": "C",
        "kind": "spire_jump",
        "mapId": "the_rock_jungle",
        "deploymentZoneId": "RJ_NW_JUNGLE_SHELF",
        "title": "Finale — Spire Jump",
        "objective": {
            "id": "FINALE_SPIRE_JUMP",
            "kind": "hive_clear_or_bypass",
            "label": "Spire Jump — burn the hive heart and take the spires",
            "targetZoneId": "RJ_CENTRAL_LAGOON_MAZE",
            "enemyFaction": "wild",
        },
    },
}


def act_for_mission(mission_number: int) -> int:
    n = int(mission_number or 1)
    if n <= ACT1_END_MISSION:
        return 1
    if n <= ACT2_END_MISSION:
        return 2
    return 3


def act_profile_for_state(state: Dict[str, Any]) -> Dict[str, Any]:
    n = int(state.get("missionNumber", 1) or 1)
    act = act_for_mission(n)
    return {
        "act": act,
        "name": ACT_NAMES[act],
        "label": ACT_LABELS[act],
        "missionNumber": n,
        "act1EndMission": ACT1_END_MISSION,
        "act2EndMission": ACT2_END_MISSION,
    }


def tech_policy_for_act(act: int) -> Dict[str, Any]:
    """Fabrication policy for the mission seed (informational).

    Emergent play: no Act tech gate. buildTech=3 / buildStructures=True always.
    Live enforcement is Tenebrium only (allowCreate costOf + concurrent BP cap).
    Act number still labels story chapter; it does not lock fabs.
    """
    a = int(act or 1)
    if a <= 1:
        mode = "ground_control"
    elif a == 2:
        mode = "constrained_rts"
    else:
        mode = "unbound"
    return {
        "act": max(1, a),
        "mode": mode,
        "buildTech": 3,
        "buildStructures": True,
        "gateEnabled": False,
        "note": "Unconstrained fab. Constructors / BP still cost Tnb (ceil(bp/150)).",
    }


# ---------------------------------------------------------------------------
# Drop 3 Wave 2: the hero roster arc.
#   - data/story/hero_roster.json ships the authored named heroes, locked.
#   - Recruitment beats unlock them when their moment lands (mission victory,
#     objective kind, reputation, act reached) — the Spoke pattern generalized.
#   - Act-2 victories grant earned T2/T3 units into the cadre: the mechanical
#     heart of "your veterans ARE your tech".
# ---------------------------------------------------------------------------

_HERO_ROSTER_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def load_hero_roster(workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Authored named-hero roster. Heroes ship status=locked with a `recruit`
    spec; apply_recruitment_beats activates them mid-campaign."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "story" / "hero_roster.json")
    here = Path(__file__).resolve().parent.parent
    paths.append(here / "data" / "story" / "hero_roster.json")
    for path in paths:
        key = str(path)
        if key in _HERO_ROSTER_CACHE:
            return _HERO_ROSTER_CACHE[key]
        if path.exists():
            try:
                data = load_json(path)
                heroes = data.get("heroes") if isinstance(data, dict) else None
                if isinstance(heroes, list):
                    out = [h for h in heroes if isinstance(h, dict) and h.get("heroId")]
                    _HERO_ROSTER_CACHE[key] = out
                    return out
            except Exception:
                pass
    return []


def apply_recruitment_beats(
    state: Dict[str, Any],
    result: Dict[str, Any],
    full_success: bool,
    completed_mission: int,
) -> List[Dict[str, Any]]:
    """Unlock authored heroes whose recruitment moment just landed.

    Runs once per processed result (duplicates are filtered upstream by the
    resultKey ledger). Returns the join records for debrief/report surfacing
    and stamps state.recentHeroJoins so the NEXT briefing can nod at them.
    """
    roster = state.get("roster") or {}
    rep = state.get("reputation") or {}
    obj_kind = str(
        result.get("objectiveArchetype")
        or ((result.get("objectiveTarget") or {}).get("kind")
            if isinstance(result.get("objectiveTarget"), dict) else "")
        or ""
    )
    joined: List[Dict[str, Any]] = []
    for hero in roster.get("heroes") or []:
        if not isinstance(hero, dict) or str(hero.get("status")) != "locked":
            continue
        spec = hero.get("recruit")
        if not isinstance(spec, dict):
            continue
        kind = str(spec.get("type") or "")
        met = False
        if kind == "mission_victory":
            met = full_success and completed_mission >= int(spec.get("mission") or 1)
        elif kind == "objective_kind":
            kinds = [str(k) for k in (spec.get("kinds") or ([spec.get("kind")] if spec.get("kind") else []))]
            met = full_success and obj_kind in kinds
            if met and spec.get("act"):
                met = act_for_mission(completed_mission) == int(spec["act"])
        elif kind == "rep":
            met = float(rep.get(str(spec.get("faction") or ""), 0) or 0) >= float(spec.get("min") or 0)
        elif kind == "act_reached":
            met = act_for_mission(int(state.get("missionNumber", 1) or 1)) >= int(spec.get("act") or 1)
        if not met:
            continue
        hero["status"] = "active"
        hero["joinedAtMission"] = int(completed_mission)
        hid = str(hero.get("heroId") or "")
        name = str(hero.get("name") or hid.title())
        joined.append({"heroId": hid, "name": name, "unitDef": str(hero.get("unitDef") or "")})
        # Character sheet: existing world characters (Grath, Halq) flip to
        # player=True; fresh recruits get a new sheet.
        chars = state.setdefault("characters", {})
        sheet = chars.get(hid)
        if isinstance(sheet, dict):
            sheet["player"] = True
            if sheet.get("status") != "dead":
                sheet["status"] = "active"
        else:
            chars[hid] = {
                "id": hid, "name": name, "faction": "ashwalkers",
                "unitDef": str(hero.get("unitDef") or ""), "xp": 0,
                "player": True, "home": None, "status": "active",
                "wounds": 0, "scars": [],
            }
    if joined:
        state["recentHeroJoins"] = {
            "missionNumber": int(state.get("missionNumber", 1) or 1),
            "heroIds": [j["heroId"] for j in joined],
            "names": [j["name"] for j in joined],
        }
    return joined


# Act-2 earned specials: victory grants keyed by the mission just won. Verified
# Legion defs only. Grants land in roster.cadre (they persist, fight, and die
# through the normal survivor pipeline) and are ledgered in roster.grants.
ACT2_REWARD_TABLE = {
    6: {"units": {"legshot": 2}, "label": "Riot walkers — a brace of Ephyras"},
    7: {"units": {"legamph": 2}, "label": "Amphibious heat-ray pair for the crossings"},
    8: {"units": {"legbart": 2}, "label": "Napalm barrage engines — the ash spreads"},
    9: {"units": {"leginc": 2}, "label": "Sustained heat-ray pair — the kiln walks"},
    10: {"units": {"legkeres": 1}, "label": "A Keres. The finale wants an answer."},
}
GRANT_CAP_BONUS_MAX = 8


def grant_cap_bonus(roster: Dict[str, Any]) -> int:
    """Granted specials travel as cadre; each raises the cadre cap so rewards
    never squeeze out the T1 veterans (bonus clamped)."""
    total = 0
    for g in roster.get("grants") or []:
        if isinstance(g, dict):
            total += sum(int(c or 0) for c in (g.get("units") or {}).values())
    return min(GRANT_CAP_BONUS_MAX, total)


def apply_act_rewards(
    state: Dict[str, Any], completed_mission: int, full_success: bool
) -> Optional[Dict[str, Any]]:
    """Grant the act-2 earned-tech reward for a full-success mission."""
    if not full_success or act_for_mission(completed_mission) != 2:
        return None
    reward = ACT2_REWARD_TABLE.get(int(completed_mission))
    if not reward:
        return None
    roster = ensure_roster(state)
    grants = roster.setdefault("grants", [])
    for g in grants:
        if isinstance(g, dict) and int(g.get("mission", -1)) == int(completed_mission):
            return None  # belt + braces on top of the resultKey ledger
    cadre = roster.setdefault("cadre", {})
    for unit_def, count in reward["units"].items():
        cadre[unit_def] = int(cadre.get(unit_def, 0) or 0) + int(count)
    rec = {
        "mission": int(completed_mission),
        "units": dict(reward["units"]),
        "label": reward["label"],
        "at": utc_now(),
    }
    grants.append(rec)
    roster["cadreCap"] = commander_cadre_cap(roster.get("commander") or {}) + grant_cap_bonus(roster)
    return rec


def finale_path_for_state(state: Dict[str, Any]) -> str:
    """The path whose signal leads decides which finale fires; the current
    pathSignal letter breaks ties (deterministic)."""
    graph = state.get("graph", {}) or {}
    current = str(state.get("pathSignal") or "B")
    if current not in FINALE_PLANS:
        current = "B"
    signals = {
        "A": float(graph.get("pathSignalA", 0.0) or 0.0),
        "B": float(graph.get("pathSignalB", 0.0) or 0.0),
        "C": float(graph.get("pathSignalC", 0.0) or 0.0),
    }
    best = max(signals.values())
    leaders = sorted(k for k, v in signals.items() if v >= best - 1e-9)
    if current in leaders:
        return current
    return leaders[0]


def finale_plan_for_state(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if act_for_mission(int(state.get("missionNumber", 1) or 1)) < 3:
        return None
    path = finale_path_for_state(state)
    plan = copy.deepcopy(FINALE_PLANS[path])
    plan["massiveStart"] = True
    plan["pathSignals"] = {
        k: round(float((state.get("graph", {}) or {}).get("pathSignal" + k, 0.0) or 0.0), 3)
        for k in ("A", "B", "C")
    }
    return plan


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


def enumerate_front_targets(state: Dict[str, Any], limit: int = 3,
                            workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The collapsed doors, lean first. Mission number does not pick a map."""
    limit = max(1, min(int(limit or 3), 4))
    cards: List[Dict[str, Any]] = []
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import wet_reach_v1 as _wet  # type: ignore

        root = workspace or Path(__file__).resolve().parents[1]
        cards = list((_wet.collapse_sorties(state, root).get("cards")) or [])
    except Exception:
        cards = []
    seen: List[str] = []
    fronts = []
    lean_map = None
    for card in cards:
        effect = card.get("effect") or {}
        map_id = canonical_map_id(effect.get("mapId"))
        if not map_id or map_id in seen:
            continue
        seen.append(map_id)
        if card.get("recommended") and lean_map is None:
            lean_map = map_id
        front = summarize_front(state, map_id)
        front["deploymentZoneId"] = effect.get("infilZoneId")
        front["objective"] = {
            "kind": effect.get("contractKind"),
            "label": card.get("label"),
        }
        front["recommended"] = bool(card.get("recommended"))
        front["consequenceIfIgnored"] = consequence_note(front)
        fronts.append(front)
        if len(fronts) >= limit:
            break
    if lean_map is None and fronts:
        fronts[0]["recommended"] = True
    return fronts


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


def zone_center_norm(zone: Dict[str, Any]) -> Tuple[float, float]:
    # Schema 2.0 zones carry a measured anchor: buildable, dry, flat ground the
    # bots actually used. A rect centre can easily be cliff or open water, so
    # the anchor wins whenever one exists.
    anchor = zone.get("anchor") or {}
    if anchor.get("x") is not None and anchor.get("z") is not None:
        return (float(anchor["x"]), float(anchor["z"]))
    bounds = zone.get("bounds", {}) or {}
    return (
        (float(bounds.get("xMin", 0.0)) + float(bounds.get("xMax", 1.0))) / 2.0,
        (float(bounds.get("zMin", 0.0)) + float(bounds.get("zMax", 1.0))) / 2.0,
    )


def _load_map_adjacency(workspace: Optional[Path], map_id: str) -> Dict[str, List[str]]:
    """Same-map adjacency for kernel walks (extract, promote, contracts).

    Prefers data/zone_maps/world_zone_graph.v1.json; falls back to legacy
    zone_adjacency.json via tools/world_zone_graph.py.
    """
    if workspace is None:
        return {}
    try:
        # Ensure tools/ is importable when this file is executed as a script.
        _tools_dir = Path(__file__).resolve().parent
        if str(_tools_dir) not in sys.path:
            sys.path.insert(0, str(_tools_dir))
        from world_zone_graph import load_map_adjacency as _wzg_load_map_adjacency

        return _wzg_load_map_adjacency(Path(workspace), map_id, kinds=("same_map",))
    except Exception:
        pass
    path = Path(workspace) / "data" / "zone_maps" / "authored" / "zone_adjacency.json"
    if not path.exists():
        return {}
    try:
        data = load_json(path)
    except Exception:
        return {}
    block = data.get(canonical_map_id(map_id)) or {}
    return {str(k): [str(x) for x in (v or [])] for k, v in block.items()}


def extraction_zone_for(map_id: str, deployment_zone: str,
                        workspace: Optional[Path] = None,
                        target_zone: Optional[str] = None,
                        mission_number: Optional[int] = None,
                        adjacency_mode: Optional[str] = None,
                        state: Optional[Dict[str, Any]] = None) -> str:
    """Pick extraction LZ.

    Legal pads only: quiet rim OR Ashwalker-majority base. Prefer the deploy
    pad when it is already legal (open-area stack for exfil). WO-039 adjacency
    modes still prefer neighbors of the target, filtered to legal pads.
    """
    try:
        import landing_zones_v1 as _lz
    except ImportError:  # pragma: no cover
        _lz = None  # type: ignore

    legacy = {
        "ancient_bastion": "AB_WESTERN_MUSTER_GROUNDS",
        "the_rock_jungle": "RJ_NW_JUNGLE_SHELF",
        "all_that_simmers": "ATS_NW_CANOPY_START",
    }
    mode = adjacency_mode
    if mode is None and mission_number is not None:
        mode = "required" if int(mission_number) <= 3 else "preferred" if int(mission_number) <= 6 else "forward"
    mode = mode or "forward"

    adj = _load_map_adjacency(workspace, map_id)
    target_nbrs = list(adj.get(str(target_zone), []) or []) if target_zone else []

    zones_by_id: Dict[str, Any] = {}
    if workspace is not None:
        zone_map_early = zone_maps_from_workspace(Path(workspace)).get(canonical_map_id(map_id))
        if zone_map_early:
            zones_by_id = {
                str(z.get("zoneId")): z
                for z in zone_map_early.get("zones", []) or []
                if z.get("zoneId")
            }

    def _rim_score(zone: Dict[str, Any]) -> float:
        if _lz is not None:
            return _lz.edge_score(zone.get("bounds") or {})
        b = zone.get("bounds") or {}
        try:
            xmin = float(b.get("xMin", 0) or 0)
            xmax = float(b.get("xMax", 1) or 1)
            zmin = float(b.get("zMin", 0) or 0)
            zmax = float(b.get("zMax", 1) or 1)
        except (TypeError, ValueError):
            return 0.5
        cx = (xmin + xmax) * 0.5
        cz = (zmin + zmax) * 0.5
        return min(cx, 1.0 - cx, cz, 1.0 - cz)

    def _is_legal(zid: str) -> bool:
        zone = zones_by_id.get(zid) or {}
        bounds = zone.get("bounds") if isinstance(zone.get("bounds"), dict) else None
        if _lz is None:
            return bool(bounds) and _rim_score(zone) <= 0.28
        return _lz.is_legal_landing(
            state,
            canonical_map_id(map_id),
            zid,
            bounds,
            tags=list(zone.get("tags") or []),
            role=str(zone.get("role") or ""),
        )

    # Prefer returning to the deploy pad when it is already a legal open LZ.
    if deployment_zone and _is_legal(str(deployment_zone)):
        if mode == "forward":
            pass  # still allow a forward quiet rim below
        else:
            return str(deployment_zone)

    # Adjacent / preferred: stay local, legal pads only.
    if mode in ("required", "preferred") and target_zone and target_nbrs:
        pool = [z for z in target_nbrs if z not in (deployment_zone, target_zone)]
        legal_pool = [z for z in pool if _is_legal(z)]
        if legal_pool:
            return legal_pool[0]
        if deployment_zone and deployment_zone in target_nbrs and _is_legal(str(deployment_zone)):
            return str(deployment_zone)
        # No legal neighbor: fall back to deploy if legal, else legacy.
        if deployment_zone and _is_legal(str(deployment_zone)):
            return str(deployment_zone)
        return legacy.get(canonical_map_id(map_id), deployment_zone)

    if workspace is not None and zones_by_id:
        deploy = zones_by_id.get(deployment_zone)
        target = zones_by_id.get(target_zone) if target_zone else None
        if deploy:
            dx, dz = zone_center_norm(deploy)
            tx, tz = zone_center_norm(target) if target else (dx + 0.35, dz + 0.35)
            ax, az = tx - dx, tz - dz
            alen = (ax * ax + az * az) ** 0.5 or 1.0
            ax, az = ax / alen, az / alen
            min_dist = 0.14
            candidates = []
            for zid in sorted(zones_by_id):
                if zid in (deployment_zone, target_zone):
                    continue
                if not _is_legal(zid):
                    continue
                zone = zones_by_id[zid]
                tags = set(str(t).lower() for t in zone.get("tags", []) or [])
                role = str(zone.get("role", "")).lower()
                if "hive" in role or "raptor" in role or "raptors" in tags or "wilds" in tags:
                    continue
                cx, cz = zone_center_norm(zone)
                dist = ((cx - dx) ** 2 + (cz - dz) ** 2) ** 0.5
                forward = (cx - dx) * ax + (cz - dz) * az
                candidates.append((zid, dist, forward, _rim_score(zone)))
            if candidates:
                far = [c for c in candidates if c[1] >= min_dist]
                pool = far or candidates
                pool.sort(key=lambda c: (c[2] + 0.5 * c[1], -c[3]), reverse=True)
                best = pool[0][0]
                if best != deployment_zone:
                    return best
    if deployment_zone and _is_legal(str(deployment_zone)):
        return str(deployment_zone)
    return legacy.get(canonical_map_id(map_id), deployment_zone)


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


def workspace_hint(voice: Dict[str, Any]) -> Optional[Path]:
    """The voice cache is keyed by workspace; recover it so briefing can find outbox."""
    for key, cached in _VOICE_CACHE.items():
        if cached is voice:
            return Path(key)
    return None


def _occasions_briefing_lines(state: Dict[str, Any], workspace: Optional[Path]) -> List[Dict[str, str]]:
    """Briefing lines from outbox/occasions.latest.json when it matches this mission."""
    if workspace is None:
        return []
    path = Path(workspace) / "outbox" / "occasions.latest.json"
    if not path.exists():
        return []
    try:
        occ = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if int(occ.get("missionNumber") or -1) != int(state.get("missionNumber", 1) or 1):
        return []
    out: List[Dict[str, str]] = []
    for row in occ.get("briefing") or []:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        out.append({"speaker": str(row.get("speaker") or "ketha"), "text": text,
                    "tag": "readings:" + str(row.get("eventClass") or row.get("kind") or "line")})
    return out[:5]


def generate_briefing(state: Dict[str, Any], voice: Dict[str, Any], map_id: str, family: str,
                      objective: Dict[str, Any], pressure: Dict[str, Any],
                      esc_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1))
    graph = state.get("graph", {})
    comp = state.get("companion", {})
    lines: List[Dict[str, str]] = []

    def add(pool_key: str, tag: str) -> None:
        text = pick_line(voice, pool_key, *seed)
        if text:
            lines.append({"speaker": voice.get("speaker", "ketha"), "text": text, "tag": tag})

    add("briefing.family." + family, "situation")
    # Drop 2: the act is the campaign's chapter voice (ground control /
    # constrained front / finale) — one line, right after the situation.
    mission_num = int(state.get("missionNumber", 1) or 1)
    add("briefing.act." + ACT_NAMES[act_for_mission(mission_num)], "act")
    # Hot raid doctrine: camp not raised yet → Ketha pushes Tnb + extract + home.
    camp = state.get("homeCamp") or {}
    tnb_bank = int((state.get("commerce") or {}).get("tenebrium") or 0)
    if int(camp.get("level") or 0) <= 0 and map_id != str(camp.get("mapId") or "the_rock_jungle"):
        add("briefing.extract_priority", "extract")
    elif tnb_bank < 3 and map_id in ("greenest_fields", "all_that_simmers", "tabula"):
        add("briefing.extract_priority", "extract")
    # Drop 3: finales speak in their path's voice; a fresh recruit gets a nod.
    if act_for_mission(mission_num) >= 3:
        plan = finale_plan_for_state(state)
        if plan:
            add("briefing.finale." + str(plan.get("kind")), "finale")
    joins = state.get("recentHeroJoins") or {}
    if isinstance(joins, dict) and joins.get("names") and int(joins.get("missionNumber") or -1) == mission_num:
        add("briefing.hero_joined", "warband")
    add("briefing.objective." + str(objective.get("kind", "")), "objective")
    # Drop 4: escalation texture — strong objectives and secondary marks each
    # get Ketha's read (raze/purge override the usual "one clean strike" tone).
    esc = esc_plan or {}
    strength = str(esc.get("objectiveStrength") or "")
    if strength in ("raze", "purge"):
        add("briefing." + strength, "escalation")
    esc_secs = esc.get("secondaries") or []
    if any(s.get("required") for s in esc_secs):
        add("briefing.secondary_required", "escalation")
    elif esc_secs:
        add("briefing.secondary_bonus", "escalation")

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

    # Readings layer: if the occasions face for this mission exists, the cast's
    # briefing lines (attractor opener + fired event classes) replace the
    # level-triggered pressure line below, which otherwise repeats while an axis
    # stays pinned. Crossings are event classes now, not levels.
    occ_lines = _occasions_briefing_lines(state, workspace_hint(voice))
    if occ_lines:
        # The cast now covers the standing-war read and the new-recruit nod.
        lines[:] = [l for l in lines if l.get("tag") not in ("war", "warband")]
        lines.extend(occ_lines)
        add("briefing.path." + str(state.get("pathSignal", "B")), "path")
        return {"lines": lines}

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
        ("defeatHero", "debrief.hero_lost"),
        ("objectiveDestroyed", "debrief.objective_destroyed"),
    ]:
        text = pick_line(voice, pool, *seed)
        if text:
            candidates[key] = text
    return candidates


def generate_beats(state: Dict[str, Any], voice: Dict[str, Any], family: str,
                   objective: Dict[str, Any],
                   waterline: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """The mission's WC3-style beat script: deterministic per campaign moment,
    authored from the same voice pools as briefings. Markers for objective and
    extraction are placed by the HUD from gadget rules params, so beats carry
    the voice, the mid-fight complication, and the hero moments."""
    seed = (state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1), "beats")
    target_zone = objective.get("targetZoneId")
    beats: List[Dict[str, Any]] = []

    def bark(pool_key: str) -> Optional[Dict[str, Any]]:
        line = pick_line(voice, pool_key, *seed)
        if not line:
            return None
        return {"type": "bark", "speaker": "Ketha", "text": line, "seconds": 7}

    opening = bark("bark.opening." + family)
    if opening:
        beats.append({"id": "b1_move_out", "trigger": {"type": "time", "seconds": 50},
                      "actions": [opening]})
    if target_zone:
        contact = bark("bark.contact." + family)
        if contact:
            beats.append({"id": "b2_contact", "trigger": {"type": "zone_entered", "zoneId": target_zone},
                          "actions": [contact, {"type": "sound", "file": "beep6", "volume": 0.7}]})
    midfight = bark("bark.midfight")
    if midfight:
        beats.append({"id": "b3_midfight", "trigger": {"type": "objective_progress", "atLeast": 0.5},
                      "actions": [midfight]})
    wave_line = bark("bark.wave_warning")
    if wave_line:
        beats.append({"id": "b4_wave", "trigger": {"type": "wave_spawned", "index": 1},
                      "actions": [wave_line]})
    extract_line = bark("bark.extract_order")
    if extract_line:
        beats.append({"id": "b5_run_home", "trigger": {"type": "objective_complete"},
                      "actions": [extract_line]})
    hero_down = bark("bark.hero_down")
    if hero_down:
        beats.append({"id": "b6_hero_down", "trigger": {"type": "hero_down"},
                      "actions": [hero_down]})
    hero_back = bark("bark.hero_recovered")
    if hero_back:
        beats.append({"id": "b7_hero_back", "trigger": {"type": "hero_recovered"},
                      "actions": [hero_back]})
    beats.extend(hydrology_beats(waterline or {}, bark))
    return beats


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


def merc_foothold_scale(reputation: float) -> float:
    """How much Null Merc presence stands with you, scaled by standing. Allied
    lines (>=40) field a fuller foothold; wary lines show up thin."""
    if reputation >= 40.0:
        return round(clamp(0.85 + (reputation - 40.0) / 60.0 * 0.5, 0.85, 1.35), 3)
    # Wary lines stay strictly below the allied floor: alliance is a clean step up.
    return round(clamp(0.55 + reputation / 40.0 * 0.25, 0.55, 0.8), 3)


WHEELIE_HERO_REP_UNLOCK = 55.0  # Null Merc standing to auto-sign Spoke


def maybe_unlock_wheelie_hero(state: Dict[str, Any]) -> bool:
    """Unlock Spoke (wheelie mentor) when Null Merc rep is high enough.

    Not a default ace — scout tech specialist whose trait banks XP from
    every Wheelie (legscout) that dies and stamps that floor on new mints.
    """
    rep = float((state.get("reputation") or {}).get("nullmercs") or 0)
    if rep < WHEELIE_HERO_REP_UNLOCK:
        return False
    roster = state.setdefault("roster", {})
    heroes = roster.setdefault("heroes", [])
    for h in heroes:
        if isinstance(h, dict) and str(h.get("heroId")) == "spoke":
            if str(h.get("status")) == "locked":
                h["status"] = "active"
                return True
            return False
    heroes.append({
        "heroId": "spoke",
        "name": "Spoke",
        "unitDef": "legscout",
        "missionCritical": False,
        "status": "active",
        "xp": 0.15,
        "timesWounded": 0,
        "campaignXp": 0.0,
        "peakBarXp": 0.15,
        "level": 1,
        "rank": "Runner",
        "trait": "wheelie_mentor",
        "traits": ["wheelie_mentor", "scout_tech"],
        "unlock": {"path": "nullmercs_rep", "repMin": WHEELIE_HERO_REP_UNLOCK},
    })
    chars = state.setdefault("characters", {})
    chars.setdefault("spoke", {
        "id": "spoke",
        "name": "Spoke",
        "faction": "nullmercs",
        "unitDef": "legscout",
        "xp": 0,
        "player": True,
        "home": None,
        "status": "active",
        "wounds": 0,
        "scars": [],
    })
    return True


def hero_intent_entries(roster: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The named heroes who deploy this mission: everyone not dead. Wounded
    heroes field at reduced toughness so last sortie's cost is felt.
    Cracked-farm levels scale HP + BAR experience so late heroes feel broken."""
    entries = []
    for hero in roster.get("heroes", []) or []:
        if not isinstance(hero, dict):
            continue
        st = str(hero.get("status") or "active")
        if st in ("dead", "locked"):
            continue
        wounded = st == "wounded"
        camp = float(hero.get("campaignXp") or 0.0)
        level = int(hero.get("level") or hero_level_from_campaign_xp(camp))
        critical = bool(hero.get("missionCritical"))
        peak = max(float(hero.get("peakBarXp") or 0.0), float(hero.get("xp") or 0.0))
        bar_xp = bar_unit_xp_from_campaign(camp, peak)
        trait = str(hero.get("trait") or "")
        traits = list(hero.get("traits") or [])
        if trait and trait not in traits:
            traits.append(trait)
        entries.append({
            "heroId": str(hero.get("heroId")),
            "name": str(hero.get("name", hero.get("heroId"))),
            "unitDef": str(hero.get("unitDef", "legcen")),
            "missionCritical": critical,
            "wounded": wounded,
            "level": level,
            "rank": normalize_hero_rank_label(hero.get("rank") or hero_rank_label(level)),
            "campaignXp": round(camp, 2),
            "hpMult": hero_hp_mult_from_level(level, critical, wounded),
            "xp": bar_xp,
            "trait": trait or None,
            "traits": traits,
        })
    return entries


def commander_is_unlocked(state: Dict[str, Any]) -> bool:
    """The walker fields only when a story beat has set this. Level does not count."""
    roster = state.get("roster") if isinstance(state, dict) else None
    commander = roster.get("commander") if isinstance(roster, dict) else None
    return isinstance(commander, dict) and commander.get("unlocked") is True


def grant_commander(state: Dict[str, Any], reason: str) -> bool:
    """Story grant. Idempotent. Mission number is not a reason."""
    commander = ensure_roster(state)["commander"]
    if commander.get("unlocked") is True:
        return False
    commander["unlocked"] = True
    commander["unlockedBy"] = str(reason or "story")[:80]
    commander["unlockedAt"] = utc_now()
    return True


def scrap_commander(state: Dict[str, Any], reason: str) -> bool:
    """The walker is scrap again. Level and perks stay on the ledger."""
    commander = ensure_roster(state)["commander"]
    if commander.get("unlocked") is not True:
        return False
    commander["unlocked"] = False
    commander["scrappedBy"] = str(reason or "lost")[:80]
    commander["scrappedAt"] = utc_now()
    return True


def load_commander_beats(workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """data/story/commander_unlock.json beats. The examples key is not loaded."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "story" / "commander_unlock.json")
    paths.append(Path(__file__).resolve().parent.parent / "data" / "story" / "commander_unlock.json")
    for path in paths:
        if not path.exists():
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        beats = data.get("beats") if isinstance(data, dict) else None
        if isinstance(beats, list):
            return [b for b in beats if isinstance(b, dict) and b.get("when")]
    return []


def _commander_beat_met(beat: Dict[str, Any], state: Dict[str, Any], result: Dict[str, Any], joined_ids: set) -> bool:
    kind = str(beat.get("when") or "")
    if kind == "hero_joined":
        return str(beat.get("heroId") or "") in joined_ids
    if kind == "story_tag":
        want = str(beat.get("tag") or "")
        tags = [str(t) for t in (result.get("storyTags") or [])]
        sortie = result.get("sortie") if isinstance(result.get("sortie"), dict) else {}
        tags.extend(str(t) for t in (sortie.get("storyTags") or []))
        return bool(want) and want in tags
    if kind == "flag":
        flags = state.get("flags") if isinstance(state.get("flags"), dict) else {}
        return bool(flags.get(str(beat.get("flag") or "")))
    return False


def apply_commander_story(
    state: Dict[str, Any],
    result: Dict[str, Any],
    joined: Optional[List[Any]] = None,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Field or scrap the command walker from the story, never from the sortie clock.

    A loss scraps it and does not also grant on that same result. While it is
    scrap, a result tag, a hero with grantsCommander, or a beat in
    data/story/commander_unlock.json can rebuild it.
    """
    result = result if isinstance(result, dict) else {}
    reason = str(result.get("terminalReason") or "")
    if reason == "commander_lost":
        if scrap_commander(state, "commander_lost"):
            return {"event": "scrapped", "reason": "commander_lost"}
        return {"event": "scrap", "reason": "commander_lost"}
    if commander_is_unlocked(state):
        return {"event": "fielded"}
    tags = [str(t) for t in (result.get("storyTags") or [])]
    sortie = result.get("sortie") if isinstance(result.get("sortie"), dict) else {}
    tags.extend(str(t) for t in (sortie.get("storyTags") or []))
    if result.get("unlockCommander") is True or "commander_unlocked" in tags:
        grant_commander(state, "result")
        return {"event": "unlocked", "reason": "result"}
    joined_ids: set = set()
    for item in joined or []:
        if isinstance(item, dict) and item.get("heroId"):
            joined_ids.add(str(item["heroId"]))
        elif isinstance(item, str) and item:
            joined_ids.add(item)
    roster = ensure_roster(state)
    for hero in roster.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("heroId") or "")
        if hid in joined_ids and hero.get("grantsCommander") is True:
            grant_commander(state, "hero:" + hid)
            return {"event": "unlocked", "reason": "hero:" + hid}
    for beat in load_commander_beats(workspace):
        if _commander_beat_met(beat, state, result, joined_ids):
            why = str(beat.get("id") or beat.get("when") or "beat")
            grant_commander(state, why)
            return {"event": "unlocked", "reason": why}
    return {"event": "scrap"}


def build_roster_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    roster = ensure_roster(state)
    commander = roster["commander"]
    prog = ensure_progression(state)
    return {
        "commander": {
            "name": commander.get("name"),
            "unitDef": commander.get("unitDef", "legcom"),
            "level": int(commander.get("level", 1)),
            "xp": round(float(commander.get("xp", 0.0) or 0.0), 1),
            "perks": list(commander.get("perks", []) or []),
            "activePerks": commander_active_perks(commander),
            "scarred": bool(commander.get("scars")),
            "unlocked": commander.get("unlocked") is True,
        },
        "cadre": {str(d): int(c) for d, c in (roster.get("cadre") or {}).items() if c},
        "cadreCap": int(roster.get("cadreCap", CADRE_CAP_BASE)),
        "cadreXp": {
            str(d): {
                "xp": round(float((bag or {}).get("xp") or 0.0), 4),
                "craftXp": round(float((bag or {}).get("craftXp") or 0.0), 4),
                "peakXp": round(float((bag or {}).get("peakXp") or 0.0), 4),
                "peakCraftXp": round(float((bag or {}).get("peakCraftXp") or 0.0), 4),
                "avgXp": round(float((bag or {}).get("avgXp") or 0.0), 4),
                "avgCraftXp": round(float((bag or {}).get("avgCraftXp") or 0.0), 4),
            }
            for d, bag in (roster.get("cadreXp") or {}).items()
            if isinstance(bag, dict) and (
                float(bag.get("xp") or 0) > 0
                or float(bag.get("craftXp") or 0) > 0
                or float(bag.get("peakXp") or 0) > 0
            )
        },
        "heroes": hero_intent_entries(roster),
        "availableAllies": available_allies(state),
        "progression": {
            "mode": prog.get("mode"),
            "difficultyDial": prog.get("difficultyDial"),
            "xpMultiplier": prog.get("xpMultiplier"),
            "farmSortiesEnabled": bool(prog.get("farmSortiesEnabled")),
            "xpPersistOnDeath": True,
        },
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


def load_sortie_order(workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """WO-003 / WO-042 / contract v2: accepted contract.

    Preference order:
      1) outbox/next_sortie_choice.json (in-engine debrief pick)
      2) outbox/next_sortie_order.json (legal VA-SORTIE/1 or tools)
      3) outbox/quest_batch.latest.json top candidate (Mode A graph walk)
    """
    if workspace is None:
        return None
    for name in ("next_sortie_choice.json", "next_sortie_order.json"):
        path = Path(workspace) / "outbox" / name
        if not path.exists():
            continue
        try:
            order = load_json(path)
        except Exception:
            continue
        if not isinstance(order, dict):
            continue
        # Provenance must survive contract v2 normalize — hub stamps and opening
        # flags are how materialize decides who wins the drop.
        provenance = {
            "source": order.get("source"),
            "derived": order.get("derived"),
            "openingMission": order.get("openingMission"),
            "openingDoctrine": order.get("openingDoctrine"),
            "openingForce": order.get("openingForce"),
            "fromDebrief": order.get("fromDebrief"),
            "debriefPick": order.get("debriefPick"),
            "hubChoiceId": order.get("hubChoiceId") or order.get("choiceId"),
        }
        # Normalize via contract v2 when available.
        try:
            if str(_tools_dir := Path(__file__).resolve().parent) not in sys.path:
                sys.path.insert(0, str(_tools_dir))
            from contract_v2 import normalize_sortie, sortie_v2_to_v1_order

            order = sortie_v2_to_v1_order(normalize_sortie(order))
        except Exception:
            if order.get("targetZoneId") and not order.get("mapId") and order.get("map"):
                order["mapId"] = order["map"]
        for key, val in provenance.items():
            if val is not None and (order.get(key) is None or key in ("source", "derived", "openingMission")):
                order[key] = val
        if not order.get("mapId") or not order.get("targetZoneId"):
            continue
        if not order.get("patron"):
            order["patron"] = "nullmercs"
        if not order.get("objectiveArchetype") and order.get("kind"):
            order["objectiveArchetype"] = order["kind"]
        order.setdefault("sessionMode", "same_map")
        order.setdefault("occupationModel", "living_shell")
        return order
    return None


def apply_sealed_company_to_packet(
    packet: Dict[str, Any],
    state: Dict[str, Any],
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Keep the hub dropping list as the only spawn list.

    A non-empty ``crewBand`` is the packs on this drop. An empty list on a hub
    stamp (``source=hub_deploy_plan``) means core only. Opening orders and
    stamps that never named a list still receive the full living company.
    """
    if not isinstance(packet, dict) or not isinstance(state, dict):
        return packet
    try:
        from company_v1 import (  # type: ignore
            company_deploy_aces,
            company_deploy_band,
            ensure_company,
            sortie_roster,
        )
    except Exception:
        try:
            from tools.company_v1 import (  # type: ignore
                company_deploy_aces,
                company_deploy_band,
                ensure_company,
                sortie_roster,
            )
        except Exception:
            return packet
    try:
        ensure_company(state, workspace)
    except Exception:
        pass
    company = state.get("company") or {}
    if not company.get("sealed"):
        return packet
    explicit = packet.get("crewBand")
    source = str(packet.get("source") or "")
    sheet = isinstance(explicit, list) and (
        len(explicit) > 0 or source == "hub_deploy_plan"
    )
    if sheet:
        # sortie_roster: core always, requested packs only, unknown ids dropped.
        band, aces = sortie_roster(state, [str(x) for x in explicit if x])
        packet["crewBand"] = list(band)
        packet["deployAces"] = list(aces)
    else:
        band = company_deploy_band(state)
        aces = company_deploy_aces(state)
        if band:
            packet["crewBand"] = list(band)
        if aces:
            packet["deployAces"] = list(aces)
    # Prefer call-ins already stamped on the packet (commit_deploy); else peek state.
    if not packet.get("missionCallIns"):
        try:
            from company_v1 import peek_mission_call_ins  # type: ignore

            calls = peek_mission_call_ins(state)
            if calls:
                packet["missionCallIns"] = list(calls)
        except Exception:
            pass
    return packet


def opening_sortie_order(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Return the authored alpha opening for a genuinely fresh campaign.

    The C&C board can leave a stamped contract in the outbox between sessions.
    That is useful after mission one, but it must not be allowed to replace the
    story's deliberate opening raid. An explicit non-Jungle session home or a
    non-empty history means the player has already chosen a different flow.

    Fresh campaigns own no ground, so the opening enters from the standard
    shell-free north desert rim (`GF_NE_PLATEAU`), hits the southeast decoy
    plateau, and extracts back to that same open pad — a stack left there
    becomes the first Ashwalker sortie origin for later raids. NW muster is
    the alternate quiet rim (also kept clear of living-shell eco).
    """
    if int(state.get("missionNumber", 1) or 1) != 1:
        return None
    if state.get("history"):
        return None
    home = canonical_map_id(state.get("sessionHomeMap") or state.get("homeMapId") or "")
    if home and home != "the_rock_jungle":
        return None
    # Mission one locks map/objective. Sealed company band still drops via
    # apply_sealed_company_to_packet so hub muster matches BAR.
    deploy_aces = ["pavise", "ketha"]
    # Standard safe GF infil/exfil: north desert (shell-free). NW muster backup.
    rim_pad = "GF_NE_PLATEAU"
    if workspace is not None:
        try:
            import landing_zones_v1 as _lz

            zmap = zone_maps_from_workspace(Path(workspace)).get("greenest_fields") or {}
            zones = list(zmap.get("zones") or [])
            adj = _load_map_adjacency(workspace, "greenest_fields")
            picked = _lz.pick_quiet_rim_pad(
                "greenest_fields",
                state=state,
                zones=zones,
                adjacency=adj,
                preferred=["GF_NE_PLATEAU", "GF_NW_MUSTER", "GF_SW_MUSTER"],
            )
            if picked:
                rim_pad = picked
        except Exception:
            pass
    order = {
        "schemaVersion": "verdance-sortie-order/1.0",
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "mapId": "greenest_fields",
        "targetZoneId": "GF_SE_PLATEAU",
        "deploymentZoneId": rim_pad,
        "extractionZoneId": rim_pad,
        "fromZoneIds": [rim_pad],
        "captureZoneIds": ["GF_SE_PLATEAU"],
        "secondaryCaptureZoneIds": [],
        "hubChoiceId": "c_raid_tnb_greenest_fields",
        "deployAces": deploy_aces,
        "crewBand": [],
        "patron": "nullmercs",
        "against": "armada",
        "objectiveArchetype": "eco_raid",
        "difficulty": 1,
        "targetDuration": "8min",
        "contractXp": 180,
        "pathSignal": state.get("pathSignal", "B"),
        "sessionMode": "reload_travel",
        "occupationModel": "living_shell",
        "source": "opening_mission",
        "openingMission": True,
        "openingDoctrine": "decoy_raid",
        "openingForce": {
            "mercenaryPackage": "punch_of_thugs",
            "mercenaryLabel": "Mercenary Punch of Thugs",
            "thugs": 6,
            "karkinos": 2,
            "rezBots": 6,
        },
        "label": "Raid Greenest Fields for Tenebrium",
        "hubBlurb": (
            "Jump the Fields first: land the quiet north desert rim, break Armada decoy farms "
            "on the southeast plateau for Tenebrium, then extract back to that open pad. "
            "A stack left on exfil becomes your first Fields foothold."
        ),
        "notes": (
            "Opening Tnb raid from shell-free north desert (standard safe infil/exfil). "
            "Hit Armada decoy commanders with Thugs and Legion Karkinos. "
            "Home is the Rock Jungle — this sortie funds that base."
        ),
    }
    apply_sealed_company_to_packet(order, state, workspace)
    return order


def opening_hub_choice(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Project the canonical opening order as the hub's single deploy choice."""
    order = opening_sortie_order(state, workspace)
    if not order:
        return None
    effect = copy.deepcopy(order)
    effect["contractKind"] = effect.get("objectiveArchetype") or "eco_raid"
    effect["preferredDeployZoneId"] = order["deploymentZoneId"]
    effect["preferredCaptureZoneId"] = order["targetZoneId"]
    effect["preferredExtractionZoneId"] = order["extractionZoneId"]
    return {
        "id": order["hubChoiceId"],
        "label": order.get("label") or "Raid Greenest Fields for Tenebrium",
        "blurb": order.get("hubBlurb") or order.get("notes") or "Hit the marked objective, then extract.",
        "kind": "deploy",
        "recommended": True,
        "effect": effect,
        "journey": "tnb_raid",
    }


def _session_home_map(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[str]:
    """Mode A: prefer campaign session home, then open contract / last history."""
    # Campaign truth first — set by process_result after each sortie (Mode A lock).
    home = state.get("sessionHomeMap") or state.get("homeMapId")
    if home:
        mid = canonical_map_id(home)
        if mid:
            return mid
    if workspace is not None:
        for name in ("next_sortie_choice.json", "next_sortie_order.json", "next_mission_intent.json"):
            p = Path(workspace) / "outbox" / name
            if not p.exists():
                continue
            try:
                data = load_json(p)
            except Exception:
                continue
            mid = canonical_map_id(data.get("mapId") or data.get("map"))
            if mid:
                return mid
    hist = state.get("history") or []
    if hist and isinstance(hist[-1], dict):
        mid = canonical_map_id(hist[-1].get("mapId"))
        if mid:
            return mid
    return None


def _is_hub_stamped_sortie(order: Dict[str, Any]) -> bool:
    """True when the order was written by stamp_deploy_plan / hub C&C board.

    Authored opening_mission also carries hubChoiceId — that must NOT count as
    a player theater seal, or the opening would lock out real hub stamps.
    """
    if not isinstance(order, dict):
        return False
    source = str(order.get("source") or "")
    if source in ("opening_mission", "opening", "authored_opening"):
        return False
    if order.get("openingMission"):
        return False
    derived = order.get("derived") if isinstance(order.get("derived"), dict) else {}
    derived_src = str(derived.get("source") or "")
    if source in ("hub_deploy_plan", "hub_stamp", "stamp_deploy_plan_v1"):
        return True
    if derived_src in ("hub_deploy_plan", "hub_stamp"):
        return True
    # Explicit hub board fields without a debrief/player/opening source → hub.
    if order.get("hubChoiceId") and source not in (
        "debrief",
        "va_next_sortie_choice",
        "player_pick",
        "mode_a_quest",
        "quest_generator",
        "opening_mission",
        "opening",
        "authored_opening",
        "",
    ):
        return True
    return False


def _is_player_debrief_sortie(order: Dict[str, Any]) -> bool:
    if not isinstance(order, dict):
        return False
    source = str(order.get("source") or "")
    if source in ("debrief", "va_next_sortie_choice", "player_pick", "in_engine_debrief"):
        return True
    if order.get("fromDebrief") or order.get("debriefPick"):
        return True
    return False


def consume_played_hub_sorties(
    workspace: Optional[Path],
    result: Dict[str, Any],
    map_id: Optional[str],
) -> Dict[str, Any]:
    """After a sortie resolves, drop spent hub stamps so Mode A can walk the next node.

    Keeps in-engine debrief picks (1/2/3). Archives hub-stamped orders that
    match the map just played so materialize_next_intent does not re-issue the
    same C&C board forever.
    """
    report: Dict[str, Any] = {"cleared": [], "kept": [], "archived": []}
    if workspace is None:
        return report
    outbox = Path(workspace) / "outbox"
    played_map = canonical_map_id(map_id or result.get("mapId") or result.get("deploymentMapId"))
    played_target = result.get("targetZoneId") or (
        (result.get("objectiveTarget") or {}).get("targetZoneId") if isinstance(result.get("objectiveTarget"), dict) else None
    )
    for name in ("next_sortie_choice.json", "next_sortie_order.json"):
        path = outbox / name
        if not path.is_file():
            continue
        try:
            order = load_json(path)
        except Exception:
            continue
        if not isinstance(order, dict):
            continue
        if _is_player_debrief_sortie(order):
            report["kept"].append({"file": name, "reason": "debrief_pick"})
            continue
        order_map = canonical_map_id(order.get("mapId") or order.get("map"))
        order_target = order.get("targetZoneId")
        same_map = bool(played_map and order_map and order_map == played_map)
        same_target = bool(played_target and order_target and order_target == played_target)
        # Consume hub stamps on the map just played; also any explicit hubChoice board.
        # Drop 4 bug fix: ALSO consume Mode A auto-picks on the played map.
        # materialize_next_intent persists its graph-walk pick to
        # next_sortie_order.json; leaving it there made every later mission
        # reload the SAME contract (same kind, same zone — even after that
        # zone flipped to the player), overriding the quest board forever.
        hub_stamped = _is_hub_stamped_sortie(order)
        if hub_stamped and (same_map or same_target or order.get("hubChoiceId")):
            try:
                archive = outbox / f"{path.stem}.last.json"
                save_json(archive, {**order, "consumedAt": utc_now(), "consumedReason": "played_hub_sortie"})
                path.unlink(missing_ok=True)  # type: ignore[call-arg]
                report["cleared"].append(name)
                report["archived"].append(str(archive.name))
            except Exception as e:  # noqa: BLE001
                report.setdefault("errors", []).append(f"{name}: {e}")
        elif (not hub_stamped) and (same_map or same_target):
            try:
                archive = outbox / f"{path.stem}.last.json"
                save_json(archive, {**order, "consumedAt": utc_now(), "consumedReason": "played_mode_a_sortie"})
                path.unlink(missing_ok=True)  # type: ignore[call-arg]
                report["cleared"].append(name)
                report["archived"].append(str(archive.name))
            except Exception as e:  # noqa: BLE001
                report.setdefault("errors", []).append(f"{name}: {e}")
        else:
            report["kept"].append({
                "file": name,
                "reason": "not_hub_or_other_map",
                "mapId": order_map,
                "hub": hub_stamped,
            })
    return report


def generate_mode_a_sortie(state: Dict[str, Any], workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Build a same-map legal sortie from world_zone_graph quest walk."""
    if workspace is None:
        return None
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        from quest_generator_v1 import generate_quests, write_quest_batch
    except Exception:
        return None
    home = _session_home_map(state, workspace)
    cands = generate_quests(
        Path(workspace),
        state,
        map_id=home,
        patron="nullmercs",
        limit=6,
    )
    try:
        write_quest_batch(Path(workspace), cands)
    except Exception:
        pass
    if not cands:
        return None
    pick = dict(cands[0])
    pick["valid"] = True
    pick["sessionMode"] = "same_map"
    pick["occupationModel"] = "living_shell"
    pick["source"] = "mode_a_quest"
    pick.pop("score", None)
    pick.pop("graphEdgeKind", None)
    # Keep human label for hub open-node paint when quest_batch is read
    if not pick.get("label"):
        pick.pop("label", None)
    return pick


def objective_from_sortie(order: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Build objectiveTarget from a validated sortie order (contract)."""
    zone_id = order["targetZoneId"]
    map_id = order["mapId"]
    archetype = order.get("objectiveArchetype") or "gate_control"
    against = order.get("against") or "neutral"
    label = str(order.get("label") or f"Contract: {archetype} on {zone_id}")
    zones = (state.get("zoneMemory") or {}).get(map_id, {}) or {}
    zm = zones.get(zone_id) or {}
    if zm.get("label") and not order.get("label"):
        label = f"{archetype}: {zm.get('label')}"
    obj = {
        "id": zone_id,
        "kind": archetype,
        "label": label,
        "targetZoneId": zone_id,
        "enemyFaction": against,
        "patron": order.get("patron"),
        "fromZoneIds": list(order.get("fromZoneIds") or []),
        "contractXp": order.get("contractXp"),
        "difficulty": order.get("difficulty"),
        "namedDefender": order.get("namedDefender"),
    }
    # Hub capture contracts: clear living-shell pocket + hold under regrow.
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        from capture_node_claims import stamp_objective_capture  # type: ignore

        obj = stamp_objective_capture(obj, order)
    except Exception:
        if archetype in ("seize_lane", "gate_control", "hold_plateau"):
            obj["captureMode"] = "clear_hold_shell"
            obj["freeTnbMint"] = False
            obj["description"] = f"Clear pocket + hold under regrow to claim {zone_id}"
    return obj


def build_escalation_plan(state: Dict[str, Any], map_id: str, objective: Dict[str, Any],
                          finale_plan: Optional[Dict[str, Any]],
                          workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Drop 4: the authored escalation for this mission — scale window,
    objective strength (surgical/raze/purge), waves override, and secondary
    objectives resolved to real zones off the quest board (always distinct
    from the primary target). Compiler and gadget both honor this stamp."""
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import escalation_ladder_v1 as ladder
    except Exception:
        return None
    mission_num = int(state.get("missionNumber", 1) or 1)
    plan = ladder.plan_for_mission(mission_num, bool(finale_plan), workspace)
    specs = list(plan.get("secondaries") or [])
    resolved: List[Dict[str, Any]] = []
    if specs and not finale_plan:
        primary = str(objective.get("targetZoneId") or "")
        taken = {primary}
        try:
            import quest_generator_v1 as qg
            ws = Path(workspace) if workspace else Path(__file__).resolve().parents[1]
            cands = qg.generate_quests(ws, state, map_id=map_id, limit=8)
        except Exception:
            cands = []
        for spec in specs:
            zone = None
            label = ""
            for cand in cands:
                zid = str(cand.get("targetZoneId") or "")
                if zid and zid not in taken:
                    zone, label = zid, str(cand.get("label") or zid)
                    break
            if not zone:
                # Not enough distinct zones on this board — drop the spec
                # rather than doubling up on the primary.
                continue
            taken.add(zone)
            resolved.append({
                "id": "sec_" + zone.lower(),
                "zoneId": zone,
                "label": label,
                "required": bool(spec.get("required")),
            })
    return {
        "missionNumber": mission_num,
        "scaleWindow": list(plan.get("scaleWindow") or []),
        "objectiveStrength": str(plan.get("objectiveStrength") or "surgical"),
        "wavesMode": plan.get("wavesMode"),
        "secondaries": resolved,
    }


def materialize_next_intent(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    ensure_roster(state)
    ensure_commerce(state, workspace)
    ensure_faction_banks(state)
    # Drop 2: acts shape the mission. Act 3 IS the path-keyed finale — it
    # overrides contracts, Mode A walks, and the spine outright.
    act_info = act_profile_for_state(state)
    finale_plan = finale_plan_for_state(state)
    # Preference: hub C&C stamp / debrief pick beat the authored opening.
    # Opening only fills a fresh campaign when the player has not sealed a
    # theater-board drop (otherwise center raids get stomped by SE plateau).
    standing = None if finale_plan else load_sortie_order(workspace)
    hub_sealed = bool(standing and _is_hub_stamped_sortie(standing))
    debrief_sealed = bool(standing and _is_player_debrief_sortie(standing))
    opening = None
    if not finale_plan and not hub_sealed and not debrief_sealed:
        opening = opening_sortie_order(state, workspace)
    sortie = opening if opening else (None if finale_plan else standing)
    if opening and workspace is not None:
        # Keep the compiler-facing order files in lockstep with the intent. Do
        # not overwrite a hub stamp or in-engine debrief pick.
        outbox = Path(workspace) / "outbox"
        for name in ("next_sortie_choice.json", "next_sortie_order.json"):
            path = outbox / name
            try:
                existing = load_json(path) if path.exists() else None
                if existing and (
                    _is_player_debrief_sortie(existing) or _is_hub_stamped_sortie(existing)
                ):
                    continue
                outbox.mkdir(parents=True, exist_ok=True)
                save_json(path, opening)
            except Exception:
                pass
    # Drop 4 bug fix: a standing order aimed at ground the patron already
    # holds is spent (stale from a previous mission) — discard it and let
    # Mode A walk the quest board fresh instead of re-issuing it forever.
    # Hub C&C stamps are exempt: the player just clicked that wound on purpose
    # (home probe / own-base contracts are valid).
    if (
        sortie
        and sortie.get("mapId")
        and sortie.get("targetZoneId")
        and not _is_hub_stamped_sortie(sortie)
    ):
        _s_map = canonical_map_id(sortie["mapId"])
        _zm = ((state.get("zoneMemory") or {}).get(_s_map) or {}).get(str(sortie["targetZoneId"])) or {}
        _ctrl = _zm.get("controllingFaction") or (_zm.get("abstract") or {}).get("control") or "neutral"
        _bloc = "nullmercs" if _ctrl in ("nullmercs", "ashwalkers") else _ctrl
        _patron = sortie.get("patron") or "nullmercs"
        _patron = "nullmercs" if _patron in ("nullmercs", "ashwalkers") else _patron
        if _bloc == _patron:
            sortie = None
    # Mode A kernel: if no explicit order, walk same-map graph for a legal contract.
    if not sortie and not finale_plan:
        sortie = generate_mode_a_sortie(state, workspace) or {}
        if sortie:
            # Persist so compiler / validator see the same pick.
            try:
                if workspace is not None:
                    outp = Path(workspace) / "outbox" / "next_sortie_order.json"
                    outp.parent.mkdir(parents=True, exist_ok=True)
                    save_json(outp, sortie)
            except Exception:
                pass
    if finale_plan:
        map_id = finale_plan["mapId"]
        deploy_zone = finale_plan["deploymentZoneId"]
        objective = copy.deepcopy(finale_plan["objective"])
        contract_active = False
        sortie = {}
    elif sortie and sortie.get("mapId") and sortie.get("targetZoneId"):
        map_id = canonical_map_id(sortie["mapId"])
        # Mode A: refuse accidental map hops when a session home map is set.
        # Explicit hub theater stamps are intentional travel — never rewrite them
        # back onto sessionHomeMap (that is what swapped Rock Jungle → Greenest).
        home = _session_home_map(state, workspace)
        if (
            home
            and map_id != home
            and (sortie.get("sessionMode") or "same_map") == "same_map"
            and not _is_hub_stamped_sortie(sortie)
        ):
            # Re-roll quests locked to home map.
            alt = generate_mode_a_sortie(
                {**state, "history": (state.get("history") or []) + [{"mapId": home}]},
                workspace,
            )
            if alt and canonical_map_id(alt.get("mapId")) == home:
                sortie = alt
                map_id = home
        from_zones = list(sortie.get("fromZoneIds") or [])
        # Hub C&C board may stamp deploymentZoneId explicitly (G2 glue).
        deploy_zone = (
            sortie.get("deploymentZoneId")
            or (from_zones[0] if from_zones else None)
        )
        if not deploy_zone:
            # Fall back to first zone held by patron bloc on this map.
            patron = sortie.get("patron")
            patron_bloc = "nullmercs" if patron in ("nullmercs", "ashwalkers") else patron
            zones_on_map = (state.get("zoneMemory") or {}).get(map_id, {}) or {}
            for zid, zm in zones_on_map.items():
                ctrl = zm.get("controllingFaction") or (zm.get("abstract") or {}).get("control")
                bloc = "nullmercs" if ctrl in ("nullmercs", "ashwalkers") else ctrl
                if bloc == patron_bloc:
                    deploy_zone = zid
                    break
        if not deploy_zone:
            # Stay on map: first zoneMemory key or graph deploy-eligible.
            zones_on_map = (state.get("zoneMemory") or {}).get(map_id, {}) or {}
            deploy_zone = next(iter(zones_on_map.keys()), None)
            if not deploy_zone:
                _, deploy_zone = choose_next_map_zone(state, workspace)
                map_id = canonical_map_id(sortie["mapId"])
        objective = objective_from_sortie(sortie, state)
        # Multi-capture from hub board (arc 2+): primary stays targetZoneId.
        caps = list(sortie.get("captureZoneIds") or [])
        secondary = list(
            sortie.get("secondaryCaptureZoneIds")
            or (caps[1:] if len(caps) > 1 else [])
        )
        if secondary:
            objective["secondaryCaptureZoneIds"] = secondary
            objective["captureZoneIds"] = caps if caps else (
                [objective.get("targetZoneId")] + secondary
            )
        contract_active = True
    else:
        map_id, deploy_zone = choose_next_map_zone(state, workspace)
        objective = objective_for_map(map_id, state, workspace)
        contract_active = False
        sortie = {}

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
    if (sortie or {}).get("openingMission"):
        title = "Opening Raid - Greenest Fields Decoy Farms" if title else None
    elif contract_active:
        title = f"Contract — {objective.get('label') or objective.get('targetZoneId')}"
    if finale_plan:
        title = finale_plan["title"]
    rep = state.get("reputation", {}) or {}
    merc_rep = float(rep.get("nullmercs", 43) or 43)
    mission_num = int(state.get("missionNumber", 1) or 1)
    esc_plan = build_escalation_plan(state, map_id, objective, finale_plan, workspace)
    adj_mode = "required" if mission_num <= 3 else ("preferred" if mission_num <= 6 else "forward")
    # Hub extract mark wins when stamped on the sortie order.
    if finale_plan:
        # Finales have no extraction: the closing battle is won on the field
        # (gadget: objective complete with no extraction rect => victory).
        extraction_zone = None
    elif (sortie or {}).get("extractionZoneId"):
        extraction_zone = sortie.get("extractionZoneId")
    else:
        extraction_zone = extraction_zone_for(
            map_id, deploy_zone, workspace, objective.get("targetZoneId"),
            mission_number=mission_num, adjacency_mode=adj_mode, state=state,
        )
    # Carry sandbox flavor from debrief pick into intent.
    flavor = (sortie or {}).get("flavor")
    against = (sortie or {}).get("against") or objective.get("enemyFaction") or "armada"
    patron = (sortie or {}).get("patron") or objective.get("patron") or "nullmercs"
    quantum_state = None
    if workspace is not None:
        try:
            from quantum_campaign_state_v1 import bootstrap as _bootstrap_quantum

            quantum_state = _bootstrap_quantum(state, Path(workspace))
        except Exception:
            quantum_state = None
    intent = {
        "schemaVersion": INTENT_SCHEMA,
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "missionId": state.get("currentMissionId", mission_id(int(state.get("missionNumber", 1)))),
        "missionNumber": int(state.get("missionNumber", 1)),
        "act": act_info,
        "techPolicy": tech_policy_for_act(act_info["act"]),
        "finale": finale_plan,
        "mapId": map_id,
        "deploymentZoneId": deploy_zone,
        "extractionZoneId": extraction_zone,
        "objective": objective["kind"],
        "objectiveTarget": objective,
        "patron": patron,
        "targetZoneId": objective.get("targetZoneId"),
        "fromZoneIds": list(objective.get("fromZoneIds") or (sortie or {}).get("fromZoneIds") or []),
        "contractXp": objective.get("contractXp") or (sortie or {}).get("contractXp"),
        "contractDifficulty": objective.get("difficulty") or (sortie or {}).get("difficulty"),
        "namedDefender": objective.get("namedDefender") or (sortie or {}).get("namedDefender"),
        "openingMission": bool((sortie or {}).get("openingMission")),
        "openingDoctrine": (sortie or {}).get("openingDoctrine"),
        "openingForce": copy.deepcopy((sortie or {}).get("openingForce")),
        "sessionMode": (sortie or {}).get("sessionMode") or "same_map",
        "occupationModel": (sortie or {}).get("occupationModel") or "living_shell",
        "captureMode": (
            (sortie or {}).get("captureMode")
            or (objective.get("captureMode") if isinstance(objective, dict) else None)
        ),
        "freeTnbMint": False if (
            (sortie or {}).get("captureMode")
            or (isinstance(objective, dict) and objective.get("captureMode"))
        ) else None,
        "shellScars": ((state.get("shellScars") or {}).get(map_id) or {}),
        # The waterline this mission inherits from the planet's water cycle.
        "hydrology": map_waterline(state, map_id, workspace),
        "factionBanks": ensure_faction_banks(state),
        "enemyInfrastructure": zone_infrastructure_for(map_id, workspace),
        "title": title,
        "escalationPlan": esc_plan,
        "briefing": generate_briefing(state, voice, map_id, family, objective, pressure, esc_plan),
        "debriefCandidates": generate_debrief_candidates(state, voice),
        "beats": generate_beats(state, voice, family, objective,
                                map_waterline(state, map_id, workspace)),
        "persistentBaseRehydrate": rehydrate,
        "offscreenPressureSummary": pressure,
        "roster": build_roster_intent(state),
        "commerce": build_commerce_intent(state, workspace),
        "worldConflict": {
            # Keep wild as wild — Rock Jungle founding must not rewrite to Armada.
            "primaryEnemy": against if against else "armada",
            "accentFaction": (
                None if against in ("wild", "neutral")
                else ("cortex" if against != "cortex" else "armada")
            ),
            "patron": patron,
            "armadaTenebriumCrisis": bool(
                (state.get("worldFlags") or {}).get("armadaTenebriumCrisis", True)
            ),
            "armadaTenebriumCrisisBlurb": (
                "Armada High Command has no Tenebrium left — they poured the black-hole "
                "metal into a continent of autonomous decoy commanders farming wind, solar, "
                "and converters across the scar. Their build-power is frozen; their eco shells "
                "are already spent."
            ),
            "nullMercs": {
                "reputation": round(merc_rep, 1),
                "alliedWithPlayer": merc_rep >= 40.0,
                "footholdScale": merc_foothold_scale(merc_rep),
                "footholdZoneIds": [
                    zid for zid, z in zones.items()
                    if (z.get("controllingFaction") or z.get("abstract", {}).get("control")) in ("nullmercs", "ashwalkers")
                ],
            },
        },
        "expectedEnemyScale": expected_map_enemy_scale(state, map_id),
        "hazardPolicy": "escalating_reset" if family == "wild" else "none",
        "economy": _economy_for_intent(state),
        "progression": ensure_progression(state),
        "difficultyPresentation": _difficulty_presentation(state, map_id),
        "flavor": flavor,
        "storyTags": intent_story_tags(map_id, family, pressure)
            + (["contract"] if contract_active else [])
            + (["com_solar_farm"] if flavor == "com_solar_farm" else [])
            + ([act_info["name"]] if act_info else [])
            + (["finale", "finale-" + str(finale_plan.get("kind"))] if finale_plan else [])
            + (["epilogue"] if state.get("campaignComplete") else []),
        "campaignComplete": bool(state.get("campaignComplete")),
        "campaignQuantumState": quantum_state,
        "environment": {
            "mapFamily": family,
            "campaignClockMinutes": round(float(state.get("campaignClockMinutes", 0.0)), 2),
            "targetDuration": (sortie or {}).get("targetDuration")
                or ("40min" if finale_plan else "10min"),
        },
        "dialogueHooks": intent_story_tags(map_id, family, pressure),
        "storyReason": (
            f"Path {finale_plan['pathKey']} finale ({finale_plan['kind']}): the campaign's closing battle on {map_id}."
            if finale_plan
            else (
                "Opening raid: hit Armada decoy farms in Greenest Fields with Thugs and Legion Karkinos, then extract."
                if (sortie or {}).get("openingMission")
                else f"Contract for {patron} against {against} on {map_id}/{objective.get('targetZoneId')}"
            )
            if contract_active
            else story_reason_for_intent(map_id, family, pressure)
        ),
        "contractActive": contract_active,
        # Hub dropping list (stamp sortie_roster). apply_sealed keeps that
        # list. It fills the whole company only when no list was named.
        "source": (sortie or {}).get("source"),
        "hubChoiceId": (sortie or {}).get("hubChoiceId"),
        "deployAces": list((sortie or {}).get("deployAces") or []),
        "crewBand": list((sortie or {}).get("crewBand") or []),
        "missionCallIns": list((sortie or {}).get("missionCallIns") or []),
        "captureZoneIds": list(
            objective.get("captureZoneIds")
            or (sortie or {}).get("captureZoneIds")
            or ([objective.get("targetZoneId")] if objective.get("targetZoneId") else [])
        ),
        "secondaryCaptureZoneIds": list(
            objective.get("secondaryCaptureZoneIds")
            or (sortie or {}).get("secondaryCaptureZoneIds")
            or []
        ),
    }
    # Mouth cards name their own doors. Carry them so the snap can see them
    # and the result's extract zone is the heading, not a near shore.
    infil_named = (sortie or {}).get("infilZoneId") or (sortie or {}).get("deploymentZoneId")
    exfil_named = (sortie or {}).get("exfilZoneId") or (sortie or {}).get("extractionZoneId")
    if (sortie or {}).get("wetReach") or (sortie or {}).get("headingZoneId"):
        if infil_named:
            intent["deploymentZoneId"] = infil_named
            intent["infilZoneId"] = infil_named
        if exfil_named:
            intent["extractionZoneId"] = exfil_named
            intent["exfilZoneId"] = exfil_named
        intent["wetReach"] = True
        intent["headingMapId"] = (sortie or {}).get("headingMapId")
        intent["headingZoneId"] = (sortie or {}).get("headingZoneId")
        intent["alongTheWay"] = list((sortie or {}).get("alongTheWay") or [])
    apply_sealed_company_to_packet(intent, state, workspace)
    # Authored content still names zones that a re-cut retired; translate the
    # whole intent forward in one place rather than trusting every source.
    intent = canonicalize_zone_ids(intent, workspace)
    separate_intent_zones(intent, workspace)
    from narrative_v1 import operation_summary, project as narrative_project
    intent["operationSummary"] = operation_summary({
        "id": intent.get("hubChoiceId") or intent.get("missionId"),
        "label": intent.get("title") or "Company operation",
        "blurb": intent.get("storyReason") or "Secure the marked objective and bring the company home.",
        "effect": {"mapId": map_id, "contractKind": intent.get("objective")},
    })
    narrative_view = narrative_project(state, workspace=workspace)
    active_thread = next((t for t in narrative_view.get("threads", []) if t["stage"] == "Committed" and map_id in t["maps"]), None)
    if active_thread:
        intent["narrativeContext"] = {"threadId": active_thread["id"], "purpose": active_thread["reason"],
                                      "perspectives": active_thread["perspectives"]}
        intent["briefing"]["lines"].append({"speaker": "ketha", "text": active_thread["reason"], "tag": "commitment"})
        for perspective in active_thread["perspectives"]:
            if perspective["speaker"] != "ketha":
                intent["briefing"]["lines"].append({"speaker": perspective["speaker"], "text": perspective["text"], "tag": "company"})
    return intent


# A landing zone this wet at rest is a beach, not a beachhead.
DRY_ENOUGH_TO_LAND = 0.35


def load_zone_map(map_id: str, workspace: Optional[Path] = None) -> Dict[str, Any]:
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "zone_maps" / "authored")
    roots.append(Path(__file__).resolve().parent.parent / "data" / "zone_maps" / "authored")
    for root in roots:
        path = root / f"{map_id}.authored.zone_map.json"
        if path.exists():
            try:
                data = load_json(path)
                if isinstance(data, dict) and data.get("zones"):
                    return data
            except Exception:
                continue
    return {}


def zone_is_landable(zone: Dict[str, Any], level: float) -> bool:
    """Dry enough to put an army on, at THIS mission's waterline.

    campEligible is a static property -- can this ground ever hold a camp. It
    cannot know that the campaign has since flooded the basin, so the dynamic
    check belongs here."""
    if not zone:
        return False
    if not zone.get("campEligible", True):
        return False
    hydro = zone.get("hydrology") or {}
    if float(hydro.get("restingSubmerged", 0.0) or 0.0) >= DRY_ENOUGH_TO_LAND:
        return False
    floods_at = float(hydro.get("floodsAt", 2.0) or 2.0)
    return floods_at > float(level)


# A zone rect wider than this is a region, not a pad. Its centre often sits
# in the river even when the anchor is on a shelf (Rock Jungle gates).
PAD_SPAN_MAX = 0.50
# Farther than the nearest dry pad by this much is a cross-map haul.
NEAR_PAD_SLACK = 0.12
# Absolute cap: a corner muster on the other shore is not a walk.
NEAR_PAD_CAP = 0.40


def _pad_span_ok(zone: Dict[str, Any], limit: float = PAD_SPAN_MAX) -> bool:
    bounds = zone.get("bounds") or {}
    try:
        sx = abs(float(bounds.get("xMax", 1.0)) - float(bounds.get("xMin", 0.0)))
        sz = abs(float(bounds.get("zMax", 1.0)) - float(bounds.get("zMin", 0.0)))
    except (TypeError, ValueError):
        return False
    return 0.02 <= sx <= limit and 0.02 <= sz <= limit


def _anchor_dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ax, az = zone_center_norm(a)
    bx, bz = zone_center_norm(b)
    return ((ax - bx) ** 2 + (az - bz) ** 2) ** 0.5


def ground_pads_by_distance(
    map_id: str,
    target_zone_id: str,
    workspace: Optional[Path] = None,
    level: float = 0.0,
    zones: Optional[Dict[str, Any]] = None,
) -> List[Tuple[float, str]]:
    """Dry, pad-sized zones nearest the objective anchor. Ground exfil only.

    Skips flooded basins and map-wide rects. The nearest hit is the shore a
    kbot can walk to; a far dry corner across the river is left off the front.
    """
    if zones is None:
        zones = {
            str(z.get("zoneId")): z
            for z in (load_zone_map(map_id, workspace).get("zones") or [])
            if z.get("zoneId")
        }
    target = zones.get(str(target_zone_id)) or {}
    if not target:
        return []
    ranked: List[Tuple[float, str]] = []
    for zid, zone in zones.items():
        if zid == str(target_zone_id):
            continue
        if not zone_is_landable(zone, level):
            continue
        if not _pad_span_ok(zone):
            continue
        ranked.append((_anchor_dist(target, zone), zid))
    ranked.sort()
    return ranked


def ground_pad_is_near(
    zone_id: str,
    map_id: str,
    target_zone_id: str,
    workspace: Optional[Path] = None,
    level: float = 0.0,
    zones: Optional[Dict[str, Any]] = None,
    ranked: Optional[List[Tuple[float, str]]] = None,
) -> bool:
    """True when this pad is dry, pad-sized, and on the objective's shore."""
    if zones is None:
        zones = {
            str(z.get("zoneId")): z
            for z in (load_zone_map(map_id, workspace).get("zones") or [])
            if z.get("zoneId")
        }
    zone = zones.get(str(zone_id)) or {}
    target = zones.get(str(target_zone_id)) or {}
    if not zone or not target:
        return False
    if str(zone_id) == str(target_zone_id):
        return False
    if not zone_is_landable(zone, level) or not _pad_span_ok(zone):
        return False
    if ranked is None:
        ranked = ground_pads_by_distance(
            map_id, target_zone_id, workspace, level, zones
        )
    if not ranked:
        return False
    dist = _anchor_dist(target, zone)
    best = ranked[0][0]
    return dist <= best + NEAR_PAD_SLACK and dist <= max(NEAR_PAD_CAP, best + 0.02)


def separate_intent_zones(intent: Dict[str, Any],
                          workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Infil and exfil are dry pads the company can walk to from the objective.

    The objective may sit in a flooded basin. A dry corner on the far shore is
    not an exit: at Rock Jungle's river level that crossing needs air
    transport, and far is a bad walk even when the graph draws an edge.
    Landing and leaving on the same near pad is intentional.
    """
    target = intent.get("targetZoneId")
    if not isinstance(target, str) or not target:
        return intent
    map_id = str(intent.get("mapId") or "")
    zones = {
        str(z.get("zoneId")): z
        for z in (load_zone_map(map_id, workspace).get("zones") or [])
        if z.get("zoneId")
    }
    if not zones or target not in zones:
        return intent
    level = float(((intent.get("hydrology") or {}).get("level")) or 0.0)
    ranked = ground_pads_by_distance(map_id, target, workspace, level, zones)

    def _near(zid: Optional[str]) -> bool:
        return bool(zid) and ground_pad_is_near(
            str(zid), map_id, target, workspace, level, zones, ranked
        )

    def _write(key: str, zid: str) -> None:
        intent[key] = zid
        if key == "extractionZoneId":
            objective = intent.get("objectiveTarget")
            if isinstance(objective, dict):
                objective["extractionZoneId"] = zid

    nearest = ranked[0][1] if ranked else None
    # A mouth is the door off this map. The nearest dry shore of an inland
    # hero must not move it. Non-mouth pads still snap.
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import wet_reach_v1 as _wet  # type: ignore

        def _mouth(zid: Any) -> bool:
            return bool(zid) and _wet.is_mouth(zid, workspace, map_id)
    except Exception:
        def _mouth(zid: Any) -> bool:
            return False

    deploy = intent.get("deploymentZoneId")
    if not _mouth(deploy) and not _near(deploy if isinstance(deploy, str) else None):
        if nearest:
            _write("deploymentZoneId", nearest)
    deploy = intent.get("deploymentZoneId")
    extract = intent.get("extractionZoneId")
    if not _mouth(extract) and not _near(extract if isinstance(extract, str) else None):
        if _mouth(deploy) or _near(deploy if isinstance(deploy, str) else None):
            _write("extractionZoneId", str(deploy))
        elif nearest:
            _write("extractionZoneId", nearest)
    return intent


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


def _economy_for_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Difficulty clarity pass: dial is the loud knob; graph is a soft nudge.

    Scarcity no longer starves early sorties into a corner (floor raised).
    Contested pressure multiplies less aggressively so the mission card label
    stays trustworthy.
    """
    prog = ensure_progression(state)
    dial = float(prog.get("difficultyDial", 1.0) or 1.0)
    graph = state.get("graph", {}) or {}
    q6 = float(graph.get("q6_contested", 0.5) or 0.5)
    q7 = float(graph.get("q7_resource_scarcity", 0.0) or 0.0)
    # Milder contested coeff (was *0.25); dial multiplies on top.
    coeff = (1.0 + q6 * 0.14) * dial
    # Resource floor 0.90 (was 0.80) so scarcity never obscures "what do I do".
    resource = clamp(1.12 - q7 * 0.22, 0.90, 1.15)
    return {
        "difficultyCoefficient": round(coeff, 3),
        "resourceModifier": round(resource, 3),
        "difficultyDial": round(dial, 3),
        "graphContested": round(q6, 3),
        "graphScarcity": round(q7, 3),
    }


def _difficulty_presentation(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Plain-English difficulty readout for mission card + HUD (no fog)."""
    eco = _economy_for_intent(state)
    scale_center = float(expected_map_enemy_scale(state, map_id).get("center") or 6000.0)
    mission_n = int(state.get("missionNumber", 1) or 1)
    ramp = min(1.0, 0.7 + 0.15 * (mission_n - 1))
    # Preview the compiler's enemyScale formula (clarity mirror).
    raw = max(0.7, min(2.2, scale_center / 6000.0)) * float(eco["difficultyCoefficient"]) * ramp
    preview = round(raw, 3)
    # Drop 4: the compiler clamps the field into the ladder's scale window, so
    # clamp the card preview the same way — the card must not promise "heavy"
    # on a mission the window pins to "light".
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import escalation_ladder_v1 as _ladder
        is_finale = act_for_mission(mission_n) >= 3
        window = _ladder.plan_for_mission(mission_n, is_finale).get("scaleWindow")
        preview = _ladder.clamp_scale(preview, window, float(eco["difficultyDial"] or 1.0))
    except Exception:
        pass
    if preview >= 1.6:
        band = "heavy"
    elif preview >= 1.2:
        band = "reinforced"
    elif preview <= 0.85:
        band = "light"
    else:
        band = "standard"
    prog = ensure_progression(state)
    return {
        "band": band,
        "enemyScalePreview": preview,
        "difficultyDial": eco["difficultyDial"],
        "onboardingRamp": round(ramp, 3),
        "missionNumber": mission_n,
        "label": f"Expected opposition: {band} (scale {preview:.2f})",
        "dialLine": f"Difficulty dial {eco['difficultyDial']:.2f} | ramp M{mission_n}",
        "mode": prog.get("mode"),
        "xpLine": (
            "XP farm ON - death keeps XP; farm sorties pay extra"
            if str(prog.get("mode")) == "cracked_farm"
            else "Standard XP - death still keeps XP"
        ),
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
    from narrative_v1 import world_snapshot
    narrative_before = world_snapshot(state)
    narrative_evidence = {k: copy.deepcopy(result[k]) for k in ("observedZoneIds", "deployAces", "deployedHeroes", "sortieHeroes") if k in result}
    state = migrate_state(state)
    ensure_zone_memory(state, workspace)
    raw_quantum_state = copy.deepcopy(result.get("finalQuantumState"))
    raw_quantum_journal = copy.deepcopy(result.get("quantumTransitionJournal") or [])
    # Normalize is law: MatchResult v2 fields only (no raw override soup).
    credit: Dict[str, Any] = {}
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        from contract_v2 import normalize_result, result_v2_to_v1_fields
        from match_credit_v1 import credit_from_result, presentable_debrief

        normalized = normalize_result(result)
        result = result_v2_to_v1_fields(normalized)
        if raw_quantum_state:
            result["finalQuantumState"] = raw_quantum_state
            result["quantumTransitionJournal"] = raw_quantum_journal
        # Preserve telemetry-adjacent extras from raw when normalize omitted them
        for k in ("graph", "reputation", "zoneMap", "economy", "map", "primaryCompanion"):
            if k in (result if False else {}) or k not in result:
                pass
        credit = credit_from_result(result)
        result["resultKey"] = credit.get("resultKey") or result.get("resultKey")
        result["status"] = credit.get("verdict") or result.get("status")
        result["verdict"] = credit.get("verdict")
        result["freeTnbMint"] = False
    except Exception:
        try:
            from match_credit_v1 import credit_from_result, presentable_debrief

            credit = credit_from_result(result)
        except Exception:
            credit = {
                "verdict": result.get("status") or "incomplete",
                "resultKey": result_key(result),
                "fullSuccess": result.get("status") == "victory",
                "anyPositive": result.get("status") in ("victory", "partial"),
                "zoneFlip": False,
                "xpTier": "full" if result.get("status") == "victory" else "none",
                "advanceMission": result.get("status") in ("victory", "partial", "defeat"),
                "applyState": True,
                "credits": {},
                "freeTnbMint": False,
                "headline": "Result",
                "changed": [],
                "nextAction": "mark_board",
                "terminalReason": result.get("terminalReason") or "",
            }

    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or (telemetry or {}).get("map", {}).get("mapId"))
    elapsed = get_elapsed_minutes(result, telemetry, map_id)
    key = str(credit.get("resultKey") or result_key(result))
    result["resultKey"] = key

    # incomplete: do not mutate campaign (bring_home surfaces debrief only)
    if credit.get("verdict") == "incomplete" or not credit.get("applyState", True):
        intent = materialize_next_intent(state, workspace)
        events = generate_story_events(state, result, None, False, workspace)
        try:
            from match_credit_v1 import presentable_debrief as _pd

            debrief = _pd(credit)
        except Exception:
            debrief = {
                "ok": False,
                "verdict": "incomplete",
                "headline": "Result not home — Retry extract or Abandon.",
                "resultKey": key,
                "duplicate": False,
            }
        return state, {
            "processed": False,
            "reason": "incomplete",
            "resultKey": key,
            "status": "incomplete",
            "verdict": "incomplete",
            "debrief": debrief,
            "credit": credit,
        }, intent, events

    # abandon: history bead only, no mission bump, no flips
    if credit.get("verdict") == "abandon":
        processed = key not in state.setdefault("processedResults", {})
        if not processed:
            intent = materialize_next_intent(state, workspace)
            events = generate_story_events(state, result, None, False, workspace)
            try:
                from match_credit_v1 import presentable_debrief as _pd

                debrief = _pd(credit, duplicate=True)
            except Exception:
                debrief = {"duplicate": True, "resultKey": key}
            return state, {
                "processed": False,
                "reason": "duplicate",
                "resultKey": key,
                "debrief": debrief,
                "credit": credit,
            }, intent, events
        bead = append_history_bead(state, result, elapsed, {})
        bead.setdefault("storyTags", []).append("abandon")
        state["processedResults"][key] = {
            "processedAt": bead["timestamp"],
            "beadIndex": len(state["history"]) - 1,
            "elapsedMinutes": elapsed,
            "verdict": "abandon",
        }
        intent = materialize_next_intent(state, workspace)
        events = generate_story_events(state, result, bead, True, workspace)
        try:
            from match_credit_v1 import presentable_debrief as _pd

            debrief = _pd(credit)
        except Exception:
            debrief = {"verdict": "abandon", "headline": "Left the field."}
        return state, {
            "processed": True,
            "resultKey": key,
            "status": "abandon",
            "verdict": "abandon",
            "zoneFlipped": False,
            "nodeClaimed": False,
            "freeTnbMint": False,
            "advanceMission": False,
            "bead": bead,
            "debrief": debrief,
            "credit": credit,
            "mapId": map_id,
        }, intent, events

    processed = key not in state.setdefault("processedResults", {})
    if not processed:
        # Intent/events for the response only — never mutate live state on a
        # duplicate (company seal / roster ensure would otherwise stick).
        intent = materialize_next_intent(copy.deepcopy(state), workspace)
        events = generate_story_events(copy.deepcopy(state), result, None, False, workspace)
        try:
            from match_credit_v1 import presentable_debrief as _pd

            debrief = _pd(credit, duplicate=True)
        except Exception:
            debrief = {"duplicate": True, "resultKey": key, "headline": "Already applied."}
        return state, {
            "processed": False,
            "reason": "duplicate",
            "resultKey": key,
            "debrief": debrief,
            "credit": credit,
        }, intent, events

    try:
        from company_v1 import ensure_company  # type: ignore

        ensure_company(state, workspace)
    except Exception:
        pass

    quantum_authoritative = False
    if raw_quantum_state:
        try:
            from quantum_campaign_state_v1 import persist_exported as _persist_quantum

            quantum_authoritative = _persist_quantum(state, result)
        except Exception:
            quantum_authoritative = False
    old_clock = float(state.get("campaignClockMinutes", 0.0) or 0.0)
    if not quantum_authoritative:
        state["campaignClockMinutes"] = round(old_clock + elapsed, 4)
    measured_zones = update_measured_zone_memory(state, result, telemetry, workspace)
    graph_delta = {} if quantum_authoritative else apply_graph_deltas(state, result, elapsed)
    apply_reputation_companion(state, result, elapsed)
    if not quantum_authoritative:
        try:
            evaluate_home_clear(state, result)
        except Exception:
            pass
    clean_extract = bool((credit.get("credits") or {}).get("cleanExtract")) or (
        result.get("extractionStatus", "") in ("clean", "success") or bool(result.get("cleanExtract"))
    )
    # Clean extract with a holding stack seeds the exfil pad as an Ashwalker
    # sortie origin (belief-majority base) for later inland / return raids.
    if clean_extract:
        extract_pad = (
            result.get("extractionZoneId")
            or (result.get("objectiveTarget") or {}).get("extractionZoneId")
            or result.get("deploymentZoneId")
        )
        if extract_pad:
            try:
                import landing_zones_v1 as _lz_seed

                stack = result.get("extractStackWeight")
                if stack is None:
                    # Presence left on the pad: prefer explicit unit count, else 1.0.
                    stack = float(
                        result.get("extractUnitCount")
                        or result.get("unitsExtracted")
                        or 1.0
                    )
                _lz_seed.seed_ashwalker_pad(
                    state,
                    canonical_map_id(map_id),
                    canonical_zone_id(str(extract_pad), workspace),
                    stack_weight=max(1.0, float(stack)),
                )
            except Exception:
                pass
    # Credit table law: fullSuccess for win tables; anyPositive for partial paths.
    success = bool(credit.get("fullSuccess"))
    any_positive = bool(credit.get("anyPositive"))
    xp_tier = str(credit.get("xpTier") or "none")
    # Roster uses success for full gains; partial gets half via xp flag on result
    result["_xpTier"] = xp_tier
    roster_success = success or (xp_tier == "partial")
    update_roster(state, result, roster_success, clean_extract)
    # Scale hero XP for partial/loss after update_roster base apply
    if xp_tier in ("partial", "loss"):
        mult = 0.5 if xp_tier == "partial" else 0.25
        for hero in (state.get("roster") or {}).get("heroes") or []:
            if not isinstance(hero, dict):
                continue
            gain = float(hero.get("lastSortieXpGain") or 0)
            if gain > 0 and xp_tier == "partial":
                # update_roster already applied full-ish; leave partial as-is if already scaled
                pass
            _ = mult  # roster gains use success bool; partial already lower via status
    # Abstract regrow first: heal *prior* scars over campaign time, then stamp new scars.
    regrow_report = apply_abstract_regrow(state, map_id, elapsed)
    apply_shell_scars(state, result, map_id)
    apply_surviving_installs(state, result, map_id)
    apply_player_footprint(state, result, map_id)

    # WO-006 / WO-005: Character Wreck Rule & Roster update.
    chars = state.setdefault("characters", default_v1_state()["characters"])
    named_outcomes = result.get("namedOutcomes", [])
    for outcome in named_outcomes:
        char_id = outcome.get("charId")
        res = outcome.get("outcome")  # dead, recovered, wounded
        if char_id in chars:
            c = chars[char_id]
            if res == "dead":
                c["status"] = "dead"
            elif res in ("recovered", "wounded"):
                c["wounds"] = c.get("wounds", 0) + 1
                if not isinstance(c.get("scars"), list):
                    c["scars"] = []
                c["scars"].append(f"wound_{c['wounds']}")
                c["status"] = "wounded"
    for hero in (state.get("roster") or {}).get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("heroId") or "")
        if hid not in chars or not isinstance(chars[hid], dict):
            continue
        camp = float(hero.get("campaignXp") or 0.0)
        sheet_target = camp * 12.5
        chars[hid]["xp"] = max(float(chars[hid].get("xp") or 0), sheet_target)
        if hero.get("status") == "dead":
            chars[hid]["status"] = "dead"
        elif hero.get("status") == "wounded":
            chars[hid]["status"] = "wounded"
        elif hero.get("status") == "active" and chars[hid].get("status") != "dead":
            chars[hid]["status"] = "active"

    # Zone flip: credit table only (capture claim or non-capture victory).
    zone_flipped = False
    target_zone_id = result.get("targetZoneId") or (
        result.get("objectiveTarget", {}).get("targetZoneId")
        if isinstance(result.get("objectiveTarget"), dict)
        else None
    )
    patron = result.get("patron") or "nullmercs"
    patron_bloc = "nullmercs" if patron in ("nullmercs", "ashwalkers") else patron
    node_claimed = bool((credit.get("credits") or {}).get("nodeClaimed")) or bool(
        result.get("nodeClaimed")
    ) or (result.get("capturePhase") == "claimed")
    capture_claim_report = None
    allow_flip = bool(credit.get("zoneFlip"))
    try:
        from capture_node_claims import apply_node_claim, is_capture_result  # type: ignore

        if is_capture_result(result):
            # Only claim when credit table says flip (requires nodeClaimed)
            capture_claim_report = apply_node_claim(
                state, result, map_id=map_id, success=allow_flip and node_claimed
            )
            node_claimed = bool(capture_claim_report.get("claimed"))
            zone_flipped = bool(capture_claim_report.get("zoneFlipped") or capture_claim_report.get("claimed"))
        elif allow_flip and target_zone_id and map_id in state.get("zoneMemory", {}):
            zone_mem = state["zoneMemory"][map_id].get(target_zone_id)
            if zone_mem:
                zone_mem["controllingFaction"] = patron_bloc
                absr = zone_mem.setdefault("abstract", {})
                absr["control"] = patron_bloc
                zone_flipped = True
    except Exception:
        if allow_flip and target_zone_id and map_id in state.get("zoneMemory", {}):
            zone_mem = state["zoneMemory"][map_id].get(target_zone_id)
            if zone_mem:
                is_cap = bool(
                    result.get("captureMode")
                    or result.get("capturePhase") in ("clear", "hold", "claimed")
                )
                if is_cap and not node_claimed:
                    pass
                else:
                    zone_mem["controllingFaction"] = patron_bloc
                    absr = zone_mem.setdefault("abstract", {})
                    absr["control"] = patron_bloc
                    if node_claimed:
                        absr["claimedNode"] = True
                        absr["captureMode"] = result.get("captureMode") or "clear_hold_shell"
                    zone_flipped = True
                    claims = state.setdefault("nodeClaims", {}).setdefault(map_id, [])
                    if node_claimed:
                        claims.append(
                            {
                                "zoneId": target_zone_id,
                                "patron": patron_bloc,
                                "pocketCleared": bool(result.get("pocketCleared") or node_claimed),
                                "freeTnbMint": False,
                                "resultKey": result.get("resultKey"),
                                "at": utc_now(),
                            }
                        )
    # Commerce: fullSuccess for victory awards; partial still settles loans lightly
    settle = settle_commerce_after_sortie(
        state, result, success or any_positive, clean_extract, zone_flipped, workspace
    )
    if (node_claimed or (capture_claim_report or {}).get("claimed")) and isinstance(settle, dict):
        settle.setdefault("notes", []).append("capture claim settled with freeTnbMint=false")
    attachment_delta = None
    try:
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import attachments_v1 as _att  # type: ignore
        import world_tick_v1 as _wt  # type: ignore

        _att.ensure_attachments(state)
        attachment_delta = _att.update_attachments_from_result(
            state, result, success=success or any_positive, zone_flipped=zone_flipped
        )
        _wt.power_response(state)
    except Exception:
        attachment_delta = None
    spectral = None if quantum_authoritative else (spectral_summary(translation, state) if translation else None)
    if spectral:
        state["lastSpectral"] = spectral
    graph_measured = (copy.deepcopy(state.get("graph") or {}) if quantum_authoritative
                      else measure_graph_from_world(state, result, spectral))
    update_destroyed_objectives(state, result)
    if not quantum_authoritative:
        reset_live_raptors_but_escalate(state, result, elapsed, workspace)
    offscreen_tick = ({
        "source": "lua_quantum_kernel",
        "elapsedMinutes": elapsed,
        "transitionCount": len(raw_quantum_journal),
    } if quantum_authoritative else tick_offscreen_zones(state, map_id, measured_zones, elapsed, workspace))
    front_flips = [] if quantum_authoritative else apply_front_decay(state, map_id, measured_zones, elapsed)
    regression_flips = [] if quantum_authoritative else apply_player_regression(state, map_id, measured_zones, elapsed, workspace)
    clash_report: Optional[Dict[str, Any]] = None
    try:
        if quantum_authoritative:
            raise RuntimeError("Lua quantum kernel already evolved offscreen state")
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import offscreen_clash_v1 as _clash  # type: ignore

        clash_report = _clash.run_offscreen_clashes(
            state,
            workspace,
            active_map_id=map_id,
            dt_minutes=elapsed,
            seed_key=str(result.get("resultKey") or key),
        )
    except Exception:
        clash_report = None
    bead = append_history_bead(state, result, elapsed, graph_delta)
    if front_flips:
        bead.setdefault("storyTags", []).append("territory-lost")
    if regression_flips:
        bead.setdefault("storyTags", []).append("player-regression")
    if clash_report and int(clash_report.get("flips") or 0) > 0:
        bead.setdefault("storyTags", []).append("offscreen-clash-flip")
    elif clash_report and int(clash_report.get("clashes") or 0) > 0:
        bead.setdefault("storyTags", []).append("offscreen-clash")
    bead["verdict"] = credit.get("verdict")
    bead["terminalReason"] = credit.get("terminalReason")
    bead["resultKey"] = key
    bead["offscreenTick"] = offscreen_tick
    if clash_report:
        bead["offscreenClash"] = {
            "clashes": clash_report.get("clashes"),
            "flips": clash_report.get("flips"),
        }
    state["processedResults"][key] = {
        "processedAt": bead["timestamp"],
        "beadIndex": len(state["history"]) - 1,
        "elapsedMinutes": elapsed,
        "verdict": credit.get("verdict"),
    }
    if credit.get("advanceMission", True):
        result_number = int(result.get("missionNumber", state.get("missionNumber", 1)))
        state["missionNumber"] = max(int(state.get("missionNumber", 1)) + 1, result_number + 1)
        state["currentMissionId"] = mission_id(state["missionNumber"])
        # The planet's water moves between missions, not during them: a basin
        # fills over a few sorties and drains over a few more.
        advance_planet_hydrology(state, workspace)
    # Consume a one-shot travel stamp from debrief/hub; lastSortie keeps Mode A
    # chains without stealing Ashwalker home onto a raid theater.
    travel = result.get("nextMapOverride") or result.get("travelIntent")
    if isinstance(travel, dict) and travel.get("mapId"):
        state["nextMapOverride"] = {
            "mapId": canonical_map_id(travel.get("mapId")),
            "deploymentZoneId": canonical_zone_id(
                travel.get("deploymentZoneId") or travel.get("targetZoneId") or "unknown_zone",
                workspace,
            ),
        }
    else:
        state.pop("nextMapOverride", None)
    if map_id:
        state["lastSortieMapId"] = canonical_map_id(map_id)
        if result.get("mapSpent") or result.get("theaterExhausted"):
            spent = state.setdefault("spentTheaters", {})
            if isinstance(spent, dict):
                spent[canonical_map_id(map_id)] = {
                    "at": utc_now(),
                    "missionNumber": int(result.get("missionNumber") or state.get("missionNumber") or 0),
                }
        # Ashwalker home is homeCamp / Rock Jungle. Raid theaters (Greenest, Eye, …)
        # must not rewrite sessionHomeMap — that trapped players on an emptied GF.
        camp_home = canonical_map_id(
            ((state.get("homeCamp") or {}).get("mapId"))
            or state.get("homeMapId")
            or "the_rock_jungle"
        )
        mid = canonical_map_id(map_id)
        journey = str(
            result.get("journey")
            or (result.get("sortie") or {}).get("journey")
            or ""
        ).lower()
        home_intent = bool(
            result.get("homeClearAttempt")
            or journey in ("home_founding", "home_clear", "home_hold")
            or mid == camp_home
        )
        if home_intent:
            state["sessionHomeMap"] = mid
        else:
            state["sessionHomeMap"] = camp_home or state.get("sessionHomeMap") or mid
        state.setdefault("sessionMode", result.get("sessionMode") or state.get("sessionMode") or "same_map")
        state.setdefault(
            "occupationModel",
            result.get("occupationModel") or state.get("occupationModel") or "living_shell",
        )
        # Holding the heading mouth opens the far map. A quit off that pad does not.
        try:
            tools_dir = Path(__file__).resolve().parent
            if str(tools_dir) not in sys.path:
                sys.path.insert(0, str(tools_dir))
            import wet_reach_v1 as _wet  # type: ignore

            headed = _wet.apply_heading(state, result, workspace)
            if headed:
                bead.setdefault("storyTags", []).append("wet-reach")
                bead["wetReach"] = headed
        except Exception as wet_exc:
            try:
                print(f"VA_WET_REACH_STAMP_FAIL {wet_exc}")
            except Exception:
                pass
    # Drop 3: the campaign answers the result — recruits sign on, act-2
    # victories mint earned specials, and a finale victory closes the book.
    completed_mission = int(result.get("missionNumber", state.get("missionNumber", 1)) or 1)
    hero_joins = apply_recruitment_beats(state, result, success, completed_mission)
    # Field wreck/rez recruits from BAR (company preamble leftovers).
    # Joins + losses (blasted rescue wreck → fieldPool status=lost).
    field_losses: list = []
    try:
        from company_v1 import (  # type: ignore
            apply_field_recruit_losses_from_result,
            apply_field_recruits_from_result,
        )

        field_losses = apply_field_recruit_losses_from_result(
            state, result, workspace=workspace
        ) or []
        field_joins = apply_field_recruits_from_result(
            state, result, workspace=workspace, full_success=bool(success)
        )
        if field_joins:
            hero_joins = list(hero_joins or []) + list(field_joins)
    except Exception as field_exc:
        # Never silently drop rescues — muster ownership depends on this path.
        try:
            print(f"VA_FIELD_RECRUIT_APPLY_FAIL {field_exc}")
        except Exception:
            pass
        field_joins = []
    walker = {"event": "scrap"}
    try:
        walker = apply_commander_story(state, result, hero_joins, workspace)
    except Exception as com_exc:
        try:
            print(f"VA_COMMANDER_STORY_FAIL {com_exc}")
        except Exception:
            pass
    else:
        if walker.get("event") == "unlocked":
            bead.setdefault("storyTags", []).append("commander-unlocked")
            bead["commander"] = walker
        elif walker.get("event") == "scrapped":
            bead.setdefault("storyTags", []).append("commander-scrapped")
            bead["commander"] = walker
    act_grant = apply_act_rewards(state, completed_mission, success)
    campaign_completed = False
    if success and act_for_mission(completed_mission) >= 3 and not state.get("campaignComplete"):
        campaign_completed = True
        state["campaignComplete"] = {
            "at": utc_now(),
            "missionNumber": completed_mission,
            "finaleKind": (finale_plan_for_state({**state, "missionNumber": completed_mission}) or {}).get("kind"),
            "pathSignal": state.get("pathSignal"),
        }
    if hero_joins:
        bead.setdefault("storyTags", []).append("hero-joined")
        # Readings layer: the bead must carry WHO joined, not just that someone did.
        bead["joined"] = [
            {"heroId": str(j.get("heroId") or j.get("id") or ""), "name": str(j.get("name") or "")}
            for j in hero_joins if isinstance(j, dict)
        ]
    # Readings layer: stamp named hero outcomes so the roll can be rebuilt from history.
    try:
        _outcomes = []
        for _o in (result.get("namedOutcomes") or []):
            if isinstance(_o, dict) and _o.get("charId"):
                _outcomes.append({"charId": str(_o["charId"]), "outcome": str(_o.get("outcome") or "")})
        _hr = result.get("heroResults") if isinstance(result.get("heroResults"), dict) else {}
        _seen = {o["charId"] for o in _outcomes}
        for _hid, _h in _hr.items():
            if isinstance(_h, dict) and _h.get("status") and str(_hid) not in _seen:
                _outcomes.append({"charId": str(_hid), "outcome": str(_h.get("status"))})
        if _outcomes:
            bead["namedOutcomes"] = _outcomes
    except Exception:
        pass
    if act_grant:
        bead.setdefault("storyTags", []).append("earned-specials")
    if campaign_completed:
        bead.setdefault("storyTags", []).append("campaign-complete")
    # Drop 4: bonus secondary marks pay out in merc standing. Required ones
    # gate victory in the gadget, so a processed win already implies them.
    bonus_secondaries = [
        s for s in (result.get("secondaryResults") or [])
        if isinstance(s, dict) and s.get("completed") and not s.get("required")
    ]
    if bonus_secondaries and result.get("status") in ("victory", "partial"):
        rep_map = state.setdefault("reputation", {})
        merc_now = float(rep_map.get("nullmercs", 43.0) or 43.0)
        rep_map["nullmercs"] = round(min(100.0, merc_now + 1.5 * len(bonus_secondaries)), 1)
        bead.setdefault("storyTags", []).append("secondary-cleared")
    else:
        bonus_secondaries = []
    from narrative_v1 import accept_result as accept_narrative_result
    narrative_event = accept_narrative_result(state, {**result, **narrative_evidence, "resultKey": key, "mapId": map_id}, credit, workspace, narrative_before)
    sortie_consume = consume_played_hub_sorties(workspace, result, map_id)
    # Belief world (Umwelt): fold this homecoming into the company's comprehension,
    # stamp the surprise (briefed vs found) on the bead, split truth from intel.
    # Skips cleanly when Umwelt is not importable; never blocks homecoming.
    if workspace is not None:
        try:
            import belief_homecoming_v1 as _belief
            _oc = bead.get("offscreenClash") or {}
            _new_fronts = int(_oc.get("clashes") or 0) + int(_oc.get("flips") or 0)
            _before = max(0, len(state.get("frontEvents") or []) - _new_fronts)
            _bf = _belief.fold_homecoming(state, result, bead, Path(workspace), before_front_count=_before)
            if _bf.get("skipped"):
                try:
                    print(f"VA_BELIEF_SKIP {_bf.get('reason')}")
                except Exception:
                    pass
        except Exception as _bx:
            try:
                print(f"VA_BELIEF_FAIL {_bx}")
            except Exception:
                pass
    # Readings layer (DERIVE faces; never world truth): rho_N over readings, attractor,
    # and the occasions the cast has to speak to. Written once per homecoming so
    # once-lines and recency carry forward. Failure here must never block homecoming.
    if workspace is not None:
        try:
            import readings_v1 as _readings
            import occasions_v1 as _occasions
            _ws = Path(workspace)
            _out = _ws / "outbox"
            _out.mkdir(parents=True, exist_ok=True)
            _prev_face = None
            _face_path = _out / "readings.latest.json"
            if _face_path.exists():
                try:
                    _prev_face = json.loads(_face_path.read_text(encoding="utf-8-sig"))
                    if _prev_face.get("generatedFrom", {}).get("campaignId") != state.get("campaignId"):
                        _prev_face = None
                except Exception:
                    _prev_face = None
            _face = _readings.project(json.loads(json.dumps(state)), _ws, _prev_face)
            _prev_occ = None
            _occ_path = _out / "occasions.latest.json"
            if _occ_path.exists():
                try:
                    _prev_occ = json.loads(_occ_path.read_text(encoding="utf-8-sig"))
                except Exception:
                    _prev_occ = None
            _occ = _occasions.build(_face, state, _ws, _prev_occ)
            _face_path.write_text(json.dumps(_face, indent=2, ensure_ascii=False), encoding="utf-8")
            _occ_path.write_text(json.dumps(_occ, indent=2, ensure_ascii=False), encoding="utf-8")
            (_out / "occasions.latest.md").write_text(_occasions.markdown(_occ), encoding="utf-8")
            # The dance tape (S3 shape): this homecoming's verbs, truth/goodness/beauty on the
            # bead, and the chronicle folded the brain-ant way.
            try:
                import story_dance_v1 as _dance
                import chronicle_v1 as _chron
                _dance.fold_homecoming(state, bead, _face, _occ, _ws, previous_face=_prev_face)
                _chron.write(state, _ws)
            except Exception as _dx:
                try:
                    print(f"VA_DANCE_FAIL {_dx}")
                except Exception:
                    pass
        except Exception as _rx:
            try:
                print(f"VA_READINGS_FAIL {_rx}")
            except Exception:
                pass
    intent = materialize_next_intent(state, workspace)
    events = generate_story_events(state, result, bead, True, workspace)
    extra_changed = []
    if zone_flipped:
        extra_changed.append("zone flipped")
    if node_claimed:
        extra_changed.append("node claimed")
    for j in hero_joins:
        extra_changed.append("{} joined the company".format(j["name"]))
    for lost in field_losses:
        if isinstance(lost, dict):
            extra_changed.append(
                "{} rescue lost — scrubbed from the wild".format(lost.get("name") or lost.get("heroId") or "recruit")
            )
    if act_grant:
        extra_changed.append("earned: {}".format(act_grant["label"]))
    for s in bonus_secondaries:
        extra_changed.append("bonus mark cleared: {} (+merc standing)".format(s.get("id") or "secondary"))
    if campaign_completed:
        extra_changed.append("CAMPAIGN COMPLETE — the ashes hold")
    # Drop-as-collapse: surface G axis moves on the debrief (GRAPH_COLLAPSE_SSOT).
    collapse = None
    try:
        from graph_collapse_v1 import collapse_chips, collapse_payload, character_collapse_chips

        extra_changed.extend(collapse_chips(graph_delta, graph_measured, max_chips=6))
        extra_changed.extend(character_collapse_chips(state, {"heroJoins": hero_joins}))
        collapse = collapse_payload(
            graph_after=state.get("graph"),
            graph_delta=graph_delta,
            graph_measured=graph_measured,
            quantum_authoritative=bool(quantum_authoritative),
        )
    except Exception:
        collapse = None
    try:
        from match_credit_v1 import presentable_debrief as _pd

        debrief = _pd(credit, extra_changed=extra_changed)
    except Exception:
        debrief = {
            "verdict": credit.get("verdict"),
            "headline": credit.get("headline"),
            "resultKey": key,
            "changed": extra_changed,
        }
    if isinstance(debrief, dict) and collapse:
        debrief["collapse"] = collapse
    if isinstance(debrief, dict) and narrative_event:
        debrief["narrativeEvent"] = narrative_event
    if campaign_completed and isinstance(debrief, dict):
        voice = load_ketha_voice(workspace)
        epilogue = pick_line(
            voice, "debrief.campaign_complete",
            state.get("campaignId", CAMPAIGN_ID), completed_mission,
        ) or "The war is over. The clans stand. Whatever grows here now grows ours."
        debrief["headline"] = epilogue
        debrief["epilogue"] = True
    report = {
        "processed": True,
        "resultKey": key,
        "elapsedMinutes": elapsed,
        "campaignClockMinutes": state["campaignClockMinutes"],
        "measuredZones": measured_zones,
        "graphDelta": graph_delta,
        "graphMeasured": graph_measured,
        "collapse": collapse,
        "spectral": spectral,
        "zoneFlipped": zone_flipped,
        "nodeClaimed": node_claimed,
        "freeTnbMint": False,
        "captureClaim": capture_claim_report,
        "regrow": regrow_report,
        "bead": bead,
        "sessionHomeMap": state.get("sessionHomeMap"),
        "sessionMode": state.get("sessionMode"),
        "sortieConsume": sortie_consume,
        "mapId": map_id,
        "targetZoneId": target_zone_id,
        "status": credit.get("verdict") or result.get("status"),
        "verdict": credit.get("verdict"),
        "terminalReason": credit.get("terminalReason"),
        "credit": credit,
        "debrief": debrief,
        "advanceMission": bool(credit.get("advanceMission", True)),
        "objectiveArchetype": result.get("objectiveArchetype") or (
            (result.get("objectiveTarget") or {}).get("kind") if isinstance(result.get("objectiveTarget"), dict) else None
        ),
        "attachmentDelta": attachment_delta,
        "worldResponse": state.get("worldResponse"),
        "offscreenTick": offscreen_tick,
        "offscreenClash": clash_report,
        "bpAccess": bp_access(state),
        "heroJoins": hero_joins,
        "actGrant": act_grant,
        "narrativeEvent": narrative_event,
        "bonusSecondaries": len(bonus_secondaries),
        "campaignComplete": bool(state.get("campaignComplete")),
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
