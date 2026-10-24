"""Campaign state schema: constants, the crafted map pool, the default save and its migration, zone memory.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from verdance.common import canonical_map_id, load_json, utc_now
from verdance.campaign.zones import canonical_zone_id

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

# The seven maps in road order: home, then around the ring (data/zone_maps/world_zone_graph.v1.json
# holds the roads themselves; verdance.world.roads reads them). Order only: never a map picker.
WORLD_MAPS = [
    "the_rock_jungle", "greenest_fields", "koom_valley", "tabula",
    "ancient_bastion", "all_that_simmers", "eye_of_horus",
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
            "pavise": { "id": "pavise", "name": "Pavise", "faction": "ashwalkers", "unitDef": "armwar", "xp": 0, "player": False, "home": None, "status": "locked", "wounds": 0, "scars": [] },
            "vane": { "id": "vane", "name": "Ash-Captain Vane", "faction": "ashwalkers", "unitDef": "legcen", "xp": 1480, "player": False, "home": None, "status": "locked", "wounds": 0, "scars": [] },
            "ketha": { "id": "ketha", "name": "Ketha", "faction": "ashwalkers", "unitDef": "legrezbot", "xp": 1120, "player": True, "home": None, "status": "active", "wounds": 0, "scars": [] },
            "anselm": { "id": "anselm", "name": "Broker Anselm Rue", "faction": "nullmercs", "unitDef": "legcen", "xp": 1900, "player": False, "home": ["greenest_fields", "GF_CENTRAL_OPEN_GRASSLAND"], "status": "active", "wounds": 0, "scars": [] },
            "grath": { "id": "grath", "name": "Grath Arrears", "faction": "nullmercs", "unitDef": "legkark", "xp": 2400, "player": False, "home": ["koom_valley", "KOOM_WEST_RIDGE_POCKET"], "status": "active", "wounds": 0, "scars": [] },
            "halq": { "id": "halq", "name": "Sisu Halq", "faction": "nullmercs", "unitDef": "legbal", "xp": 1350, "player": False, "home": ["the_rock_jungle", "RJ_WESTERN_CAUSEWAY"], "status": "active", "wounds": 0, "scars": [] },
            "brask": { "id": "brask", "name": "Line-Captain Odell Brask", "faction": "armada", "unitDef": "armcom", "xp": 1600, "player": False, "home": ["greenest_fields", "GF_SE_ENERGY_WORKS"], "status": "active", "wounds": 0, "scars": [] },
            "solvang": { "id": "solvang", "name": "Warden-Marshal Teir Solvang", "faction": "armada", "unitDef": "armcom", "xp": 3100, "player": False, "home": ["ancient_bastion", "AB_W_KEEP"], "status": "active", "wounds": 0, "scars": [] },
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
            "heroes": [
                {
                    "heroId": "pavise",
                    "name": "Pavise",
                    # Solo Centurion left hand (armwar) — grey shield captain, Hardened BAR XP, HP aura.
                    "unitDef": "armwar",
                    "missionCritical": False,
                    "status": "locked",  # a pick now (the recommended you), not core
                    "xp": 0.0,  # starting XP comes from the pack cost curve (crew_packs xpCurve)
                    "campaignXp": 0.0,
                    "peakBarXp": 0.0,
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
        # The company's door ledger (verdance.world.roads): it starts holding both
        # doors of the start road, home's north-west muster and Greenest Fields'.
        "doors": {zid: {"held": True, "since": 0, "by": "start"}
                  for zid in ("TRJ_NW_OUTER_MUSTER", "GF_NW_MUSTER")},
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
        # Fire Emblem company: sealed on hub preamble (Ketha always; pick 3, the first is you). Unpicked
        # band heroes live in fieldPool until wreck/rez or sortie recruit.
        "company": {
            "sealed": False,
            "core": ["ketha"],
            "band": [],
            "you": None,
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
        state.pop("campaignQuantumState", None)  # the retired Lua kernel's copy of the world
        state.pop("wetReach", None)  # the retired two-door sortie's ledger; doors replace it
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


WILD_HOME_MAP = "the_rock_jungle"
from verdance.world.theaters import EYE_RIM_ZONES, STANDING_CONTROL  # noqa: E402


def ensure_zone_memory(state: Dict[str, Any], workspace: Path) -> None:
    zone_maps = zone_maps_from_workspace(workspace)
    zone_memory = state.setdefault("zoneMemory", {})
    doors = state.get("doors") if isinstance(state.get("doors"), dict) else {}

    def held_door(zone_id: str) -> bool:
        rec = doors.get(zone_id)
        return bool(isinstance(rec, dict) and rec.get("held"))

    actors = state.setdefault("offscreenActors", {})
    hazard_state = state.setdefault("hazardState", {})
    for map_id, zone_map in zone_maps.items():
        zones = zone_memory.setdefault(map_id, {})
        map_actors = actors.setdefault(map_id, {})
        # A re-cut retires zone ids: what the campaign remembers about a retired
        # zone passes to the zone that inherited its ground (first heir wins).
        live = {z.get("zoneId") for z in zone_map.get("zones", []) or []}
        for old_id in [k for k in zones if k not in live]:
            heir = canonical_zone_id(old_id, workspace)
            memory = zones.pop(old_id)
            map_actors.pop(old_id, None)
            if heir in live and heir not in zones and isinstance(memory, dict):
                label = next((z.get("label") for z in zone_map["zones"] if z.get("zoneId") == heir), heir)
                memory.update(zoneId=heir, label=label)
                zones[heir] = memory
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
            standing = STANDING_CONTROL.get(map_id, {}).get(zone_id)
            if map_id == WILD_HOME_MAP and held_door(zone_id):
                actor = "Ashwalkers"
                control = "ashwalkers"
            elif standing:
                # A set piece's ground (Koom's standing war): its side holds it from the start.
                actor = "NullMercsAI" if standing == "nullmercs" else "SimpleAI"
                control = standing
            elif (map_id == WILD_HOME_MAP or (map_id == "eye_of_horus" and zone_id in EYE_RIM_ZONES)
                  or "raptors" in tags or "wilds" in tags or "hive" in role or "raptor" in role):
                # The Eye's outer rim is raptor ground too (owner call, 2026-10-23); Cortex keeps the eye.
                # The Rock Jungle is wild ground end to end: raptors hold every zone until
                # someone out-builds them there.
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
            elif standing or (control == "wild" and (map_id == WILD_HOME_MAP or map_id == "eye_of_horus")):
                # Older saves: unclaimed ground a set piece stands on (the wild jungle, the Eye's rim,
                # Koom's two camps) goes to whoever the set piece says holds it.
                zm = zones[zone_id]
                if str(zm.get("controllingFaction") or (zm.get("abstract") or {}).get("control") or "neutral").lower() in ("neutral", "contested", "none", ""):
                    zm["controllingFaction"] = control
                    zm.setdefault("abstract", {})["control"] = control
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


__all__ = [
    "WORLD_MAPS",
    "BP_PER_TNB",
    "CAMPAIGN_ID",
    "EVENTS_SCHEMA",
    "FAMILY_CALIBRATION",
    "FRONT_DECAY_MIN_PRESSURE",
    "FRONT_DECAY_RATE",
    "FRONT_EVENTS_KEEP",
    "INTENT_SCHEMA",
    "MAP_DISPLAY",
    "MAP_FAMILIES",
    "NULLMERC_FOOTHOLD_ROLES",
    "RESULT_SCHEMA",
    "STATE_SCHEMA",
    "TELEMETRY_SCHEMA",
    "TEST_WON_CALIBRATION_REFS",
    "TIME_BAND_FAR_RATE",
    "TIME_BAND_LIVE_RATE",
    "TIME_BAND_NEAR_RATE",
    "_INFRA_TOKENS",
    "_MAP_POOL_CACHE",
    "blank_zone_memory",
    "default_v1_state",
    "ensure_zone_memory",
    "load_map_pool",
    "map_family",
    "migrate_state",
    "mission_id",
    "parse_campaign_forces",
    "result_key",
    "zone_infrastructure_for",
    "zone_maps_from_workspace",
]
