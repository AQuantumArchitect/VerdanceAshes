"""Build the next mission: the mission intent and the campaign state in, the playable scenario out.

A port of scripts/build_next_mission_v1.ps1 (2026-11-04), which stays in the repo as the reference.
The scenario it writes must match the PowerShell one value for value: tests/test_mission_builder_parity.py
holds it to a corpus of real builds from Luke's PC. Where the PowerShell had a fault that shaped its
output, the port keeps the fault and says so in a comment, so the scenario does not change under the
gadget without anyone deciding it should.

The order of the steps is the PowerShell's order, because later steps read what earlier ones set.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from verdance.mission_builder import kits
from verdance.mission_builder import shell as shell_mod
from verdance.mission_builder._ps import (
    CIDict, B, D, I, JNum, R, S, T, arr, plain_json, ps_json, eq, fmt, g, has, hashtable_key_order, ieq, iin, ilike, imatch, sign, sort_unique_ints,
)
from verdance.mission_builder.field import (
    SHELL_CAPABLE_KINDS, Field, clamp01, edge_score, push_to_rim, start_rect, zone_by_id, zone_center,
)
from verdance.mission_builder.kits import each, faction, props

Log = Callable[[str], None]

SCENARIO_REL = Path("data") / "scenarios" / "generated" / "next_mission_intent.playable.json"
MANIFEST_REL = Path("outbox") / "next_mission_build_manifest.json"


def piped(v: Any) -> Any:
    """The value of ``key = if (...) { $v }`` or ``$( $v )``: PowerShell collects the statement's
    output, so an empty array becomes null and a one-element array becomes its element."""
    if isinstance(v, list):
        if len(v) == 0:
            return None
        if len(v) == 1:
            return v[0]
        return list(v)
    return v


# --- The mission's shape ------------------------------------------------------------------------

def enemy_side(map_id: str, intent: Dict[str, Any]) -> str:
    """Faction comes from the CRAFTED world (data/map_pool/seven_maps.json), not a guess off the zone
    name. The standing war is Null Mercs vs Armada; Cortex is an accent that holds only its own
    authored maps. A camp is one faction."""
    against = ""
    if has(intent, "against") and T(intent["against"]):
        against = S(intent["against"])
    elif has(intent, "worldConflict") and T(intent["worldConflict"]) and T(g(intent["worldConflict"], "primaryEnemy")):
        against = S(intent["worldConflict"]["primaryEnemy"])
    # Wild / Rock Jungle home dig-ins are raptor shelves, never Armada; the key stays valid.
    if ieq(against, "wild") or ieq(map_id, "the_rock_jungle"):
        return "Armada"
    ot = g(intent, "objectiveTarget")
    if T(ot) and T(g(ot, "enemyFaction")):
        ef = S(ot["enemyFaction"])
        if ieq(ef, "cortex"):
            return "Cortex"
        if ieq(ef, "armada") or ieq(ef, "wild"):
            return "Armada"
    infra = g(intent, "enemyInfrastructure")
    if T(infra) and T(g(infra, "campaignForces")):
        cf = infra["campaignForces"]
        arm = S(cf["ARM"]) if has(cf, "ARM") else ""
        cor = S(cf["COR"]) if has(cf, "COR") else ""
        if cor.strip() and not arm.strip():
            return "Cortex"
        if arm.strip():
            return "Armada"
    if ieq(map_id, "eye_of_horus"):
        return "Cortex"
    return "Armada"


def objective_description(intent: Dict[str, Any]) -> str:
    ot = g(intent, "objectiveTarget")
    ok = S(ot["kind"]) if (T(ot) and T(g(ot, "kind"))) else S(g(intent, "objective"))
    if iin(ok, ("fortify_zone", "home_founding")):
        if T(ot) and T(g(ot, "targetZoneId")):
            zid = S(ot["targetZoneId"])
        elif T(g(intent, "targetZoneId")):
            zid = S(intent["targetZoneId"])
        else:
            zid = "the zone"
        return f"Fortify {zid} — raise defense, build power, army, and storage. Defense is what 'secured' means."
    if T(ot) and T(g(ot, "label")):
        return S(ot["label"])
    if T(g(intent, "storyReason")):
        return S(intent["storyReason"])
    return "Complete the local Verdance sortie objective, then extract."


def required_frames(intent: Dict[str, Any]) -> int:
    # Drop 2 finale: a full unconstrained game of BAR gets a ~40 minute clock.
    if has(intent, "finale") and T(intent["finale"]):
        return 72000
    env = g(intent, "environment")
    # WO-004: contracts target ~10 minutes (18000 frames @ 30fps), not 20.
    td = S(env["targetDuration"]) if (T(env) and T(g(env, "targetDuration"))) else ""
    # Soft clocks are REAL mission ends (gadget checkSoftClock). Keep them tight.
    mission_num = I(intent["missionNumber"]) if T(g(intent, "missionNumber")) else 1
    # Early sorties: ~7.5 min walk-up, take the ground, extract.
    if mission_num <= 3:
        return 13500
    if imatch(td, r"10\s*min") or ieq(td, "10min"):
        return 18000
    # Contract missions (any with contractActive or targetDuration) stay front-band.
    if has(intent, "contractActive") and T(intent["contractActive"]):
        return 19800
    family = S(env["mapFamily"]) if (T(env) and T(g(env, "mapFamily"))) else "tempo"
    for k, v in (("siege", 27000), ("wild", 24000), ("economy", 21600)):
        if ieq(family, k):
            return v
    return 19800


def resolve_arc_profile(mission_number: int, act: int, map_id: str, kings: bool, commander_worn: bool,
                        waves: str) -> Dict[str, Any]:
    """The mission's shape, decided once (2026-10-27; it used to be set in six places, later ones
    silently overriding earlier ones). Read by the gadget: id, playerCommanders, enemyMode,
    sweepEnemyCommanders, escalation. Read here: unitPrinter, allyPower, enemyAI, allowEnemyProduction."""
    n = max(1, mission_number)
    act1_id = "raid_tactics" if n <= 3 else ("contested_front" if n <= 6 else "strike_lead")
    pid = "unbound_finale" if act >= 3 else ("constrained_rts" if act == 2 else act1_id)
    # Act 1 reads warband against warband (roving packs over a thinned shell); later acts a quick
    # reaction force. Act 1 strips enemy start commanders (except Tabula, a BARbarian with its own).
    enemy_mode = "light_qrf" if (act >= 2 or act1_id == "strike_lead") else "warband"
    barbarian = kings or act >= 2 or ieq(map_id, "tabula")
    if kings:
        escalation = "off"
    elif waves:
        escalation = waves
    elif act >= 3:
        escalation = "full"
    elif act == 2:
        escalation = "light" if n <= 7 else "full"
    elif act1_id == "raid_tactics":
        escalation = "off"
    elif act1_id == "contested_front":
        escalation = "light"
    else:
        escalation = "full"
    ally_power = 0.95 if n <= 1 else 0.55 if n == 2 else 0.35 if n == 3 else 0.25 if n <= 5 else 0.15
    return {
        "id": pid,
        "playerCommanders": 1 if (kings or commander_worn) else 0,
        # Arc A prints Phobos (legcen) for the act-1 tactics kit; later acts build their own.
        "unitPrinter": None if act >= 2 else {"def": "leglab", "product": "legcen", "count": 1,
                                             "metalIncome": 10, "energyIncome": 50},
        "enemyMode": enemy_mode,
        "enemyAI": "barbarian" if barbarian else "simple",
        "allyPower": R(ally_power, 2),
        "escalation": escalation,
        "sweepEnemyCommanders": bool(not barbarian and act <= 1 and act1_id != "strike_lead"),
        "allowEnemyProduction": bool(kings or act >= 2 or act1_id == "strike_lead"),
    }


# --- Workspace reads ----------------------------------------------------------------------------

def _bar_data_root(cfg: Dict[str, Any]) -> Optional[str]:
    """Find-BARDataRoot without the Steam library walk: verdance_config.json, then BAR_DATA_ROOT, then
    the standard installer folders. The PowerShell threw when it found none; the port leaves the seed
    destination null instead, so a scenario can be built on a machine without BAR."""
    v = cfg.get("barDataRoot")
    if T(v) and Path(S(v)).exists():
        return S(v)
    env = os.environ.get("BAR_DATA_ROOT")
    if env and Path(env).exists():
        return env
    cands = []
    for var, rel in (("LOCALAPPDATA", ("Programs", "Beyond-All-Reason", "data")),
                     ("ProgramFiles", ("Beyond-All-Reason", "data")),
                     ("ProgramFiles(x86)", ("Beyond-All-Reason", "data"))):
        base = os.environ.get(var)
        if base:
            cands.append(Path(base).joinpath(*rel))
    for c in cands:
        if (c / "engine").exists():
            return str(c)
    for c in cands:
        if (c / "games").exists() or (c / "packages").exists():
            return str(c)
    return None


def verdance_config(ws: Path) -> Dict[str, Any]:
    """The part of Get-VerdanceConfig the manifest reports (seedOutbox, seedDestination)."""
    path = ws / "verdance_config.json"
    cfg: Dict[str, Any] = {}
    if path.exists():
        try:
            cfg = shell_mod.read_json(path)
        except Exception:  # noqa: BLE001
            cfg = {}
    out: Dict[str, Any] = {}
    out["seedOutbox"] = S(cfg["seedOutbox"]) if T(cfg.get("seedOutbox")) else str(ws / "outbox" / "va_current.lua")
    if T(cfg.get("seedDestination")):
        out["seedDestination"] = S(cfg["seedDestination"])
    else:
        bar = _bar_data_root(cfg)
        mod_sdd = S(cfg["modSdd"]) if T(cfg.get("modSdd")) else (str(Path(bar) / "games" / "VerdanceAshes.sdd") if bar else None)
        out["seedDestination"] = (str(Path(mod_sdd) / "singleplayer" / "verdance_ashes" / "generated" / "va_current.lua")
                                  if mod_sdd else None)
    return out


def hot_drop(ws: Path, log: Log) -> Optional[Dict[str, str]]:
    """outbox/hot_drop.json exists only for a hot-drop launch; its token keeps a stale drop file out."""
    p = ws / "outbox" / "hot_drop.json"
    if not p.exists():
        return None
    try:
        hd = shell_mod.read_json(p)
    except Exception:  # noqa: BLE001
        return None
    if not T(g(hd, "token")):
        return None
    log("Hot drop: the company waits off the field until the drop.")
    return {"token": S(hd["token"])}


def _field_recruit_rows(ws: Path, state: Any, map_id: str, marked: List[Any], archetype: str, log: Log) -> List[Any]:
    """The encounter field's draw for this sortie (verdance.company.company.field_recruits_for_map).

    The PowerShell ran this in a child Python and read the rows back through JSON; the port calls it
    in process on a copy of the state (it calls ensure_company, which writes to the state it is
    given) and keeps the JSON round trip, so the rows are the same plain values the PS1 saw. If the
    draw fails, this sortie meets nobody, as before.
    """
    try:
        from verdance.company.company import field_recruits_for_map

        rows = field_recruits_for_map(plain_json(state), map_id, workspace=Path(ws), limit=None,
                                      marked_zone_ids=list(marked or []), objective_archetype=archetype or "")
        payload = json.loads(json.dumps({"rows": rows}), parse_float=JNum)
    except Exception as e:  # noqa: BLE001
        log(fmt("Field recruit draw failed ({0}); this sortie meets nobody.", str(e)))
        return []
    if T(payload) and has(payload, "rows"):
        return arr(payload["rows"])
    return arr(payload)


def _soft_double(v: Any, default: float) -> float:
    """The recruit row's seedXp / beliefScore: a number unless it is missing, empty or an array."""
    try:
        if v is not None and S(v) != "" and not isinstance(v, list):
            return D(v)
    except (TypeError, ValueError):
        return default
    return default


# --- The build ----------------------------------------------------------------------------------

class BuildResult:
    def __init__(self) -> None:
        self.scenario: Dict[str, Any] = {}
        self.manifest: Dict[str, Any] = {}
        self.installer_args: Dict[str, Any] = {}
        self.scenario_path: Path = Path()
        self.manifest_path: Path = Path()
        self.mission_id = ""
        self.map_name = ""


def _build(ws: Path, intent: Dict[str, Any], state: Any, *, intent_path: str, state_path: str,
           launch: bool = False, save_game: bool = False, save_name: str = "", timeout_seconds: int = 300,
           extra_mod_options: str = "", log: Log = print) -> BuildResult:
    ws = Path(ws)
    # 5.1 held every non-integer JSON number as a decimal (see _ps.JNum).
    intent = ps_json(copy.deepcopy(intent))
    state = ps_json(copy.deepcopy(state))
    res = BuildResult()

    pool_path = ws / "data" / "map_pool" / "seven_maps.json"
    if not pool_path.exists():
        raise FileNotFoundError(f"Missing map pool: {pool_path}")
    pool = shell_mod.read_json(pool_path)
    map_id = S(g(intent, "mapId"))
    map_entry = next((m for m in arr(g(pool, "maps")) if eq(g(m, "id"), map_id)), None)
    if not T(map_entry):
        raise ValueError(f"Unknown campaign map id in intent: {map_id}")

    zone_map_rel = f"data\\zone_maps\\authored\\{map_id}.authored.zone_map.json"
    zone_map_path = ws / "data" / "zone_maps" / "authored" / f"{map_id}.authored.zone_map.json"
    if not zone_map_path.exists():
        raise FileNotFoundError(f"Missing authored zone map for {map_id}: {zone_map_path}")
    zone_map = shell_mod.read_json(zone_map_path)

    if T(g(intent, "missionNumber")):
        mission_number = I(intent["missionNumber"])
    elif T(state) and T(g(state, "missionNumber")):
        mission_number = I(state["missionNumber"])
    else:
        mission_number = 1
    mission_id = S(intent["missionId"]) if T(g(intent, "missionId")) else "va_" + fmt("{0:d3}", mission_number)
    ot = g(intent, "objectiveTarget")
    objective_kind = S(ot["kind"]) if (T(ot) and T(g(ot, "kind"))) else S(g(intent, "objective"))
    # Drop 2 act structure labels pacing; the act is Python's (verdance.campaign.acts, intent.act).
    act_num = I(g(g(intent, "act"), "act"))
    act_name = S(g(g(intent, "act"), "name"))
    is_finale = bool(has(intent, "finale") and T(intent["finale"]))
    finale_kind = S(intent["finale"]["kind"]) if (is_finale and T(g(intent["finale"], "kind"))) else ""
    log(fmt("Act structure: act={0} ({1}) finale={2}", act_num, act_name, finale_kind))
    # Story owns the walker. A missing or false flag is scrap. Level and perks do not field it.
    commander_unlocked = False
    commander_row = None
    if T(state) and T(g(state, "roster")) and T(g(state["roster"], "commander")):
        commander_row = state["roster"]["commander"]
    if not T(commander_row) and T(g(intent, "roster")) and T(g(intent["roster"], "commander")):
        commander_row = intent["roster"]["commander"]
    if T(commander_row) and has(commander_row, "unlocked") and eq(commander_row["unlocked"], True):
        commander_unlocked = True
    log(fmt("Command walker: {0}", "unlocked" if commander_unlocked else "scrap"))
    # The field's standing set piece (verdance.world.theaters, on the intent). The engine decides it;
    # this only places it.
    theater = intent["theater"] if (has(intent, "theater") and T(intent["theater"])) else None
    is_kings = bool(T(theater) and ieq(S(g(theater, "kind")), "kings_showdown"))
    is_standing_war = bool(T(theater) and ieq(S(g(theater, "kind")), "standing_war"))
    # A young war on a big field keeps the map's living shell beside it (theaters: recipe keepShell).
    keep_shell = bool(is_standing_war and has(theater, "keepShell") and T(theater["keepShell"]))
    if is_kings:
        log("Kings' showdown: one commander each, last one standing takes the throne.")
    # Drop 4 escalation ladder: the engine's authored plan. One authority for pacing.
    esc_plan = intent["escalationPlan"] if (has(intent, "escalationPlan") and T(intent["escalationPlan"])) else None
    objective_strength = S(esc_plan["objectiveStrength"]) if (T(esc_plan) and T(g(esc_plan, "objectiveStrength"))) else "surgical"
    if ieq(objective_strength, "finale"):
        objective_strength = "surgical"
    waves = S(esc_plan["wavesMode"]) if (T(esc_plan) and T(g(esc_plan, "wavesMode"))) else ""
    arc = resolve_arc_profile(mission_number, act_num, map_id, is_kings, commander_unlocked, waves)
    esc_secondaries: List[Any] = []
    if T(esc_plan) and T(g(esc_plan, "secondaries")):
        esc_secondaries = arr(esc_plan["secondaries"])
    if T(esc_plan):
        log(fmt("Escalation plan: strength={0} waves={1} secondaries={2}", objective_strength,
                S(arc["escalation"]), len(esc_secondaries)))

    deploy_zone_id = S(g(intent, "deploymentZoneId"))
    target_zone_id = S(ot["targetZoneId"]) if (T(ot) and T(g(ot, "targetZoneId"))) else ""
    # The pad is the zone the player chose on the hub. The builder never moves it: infil, pad, radar
    # and extraction are one place.
    opening_mission = bool(has(intent, "openingMission") and T(intent["openingMission"]))

    deploy_zone = zone_by_id(zone_map, deploy_zone_id)
    target_zone = zone_by_id(zone_map, target_zone_id)
    deploy_center = zone_center(deploy_zone, [0.16, 0.16])
    enemy_center = zone_center(target_zone, [0.84, 0.84])
    is_contract = (has(intent, "contractActive") and T(intent["contractActive"])) or \
        (has(intent, "fromZoneIds") and T(intent["fromZoneIds"]) and len(arr(intent["fromZoneIds"])) > 0)
    front_band = bool(is_contract or iin(S(g(intent, "objective")), ("seize_lane", "gate_control")))

    side = enemy_side(map_id, intent)
    has_wild = (has(map_entry, "wilds") and T(map_entry["wilds"])) or (has(map_entry, "raptors") and T(map_entry["raptors"])) \
        or (T(g(intent, "hazardPolicy")) and not eq(intent["hazardPolicy"], "none"))
    # Rock Jungle is always a raptor shelf, even if map_pool forgot the wilds flag.
    if ieq(map_id, "the_rock_jungle"):
        has_wild = True

    if has(intent, "title") and T(intent["title"]):
        title = f"{S(intent['title'])} - {S(g(map_entry, 'title'))}"
    else:
        title = f"Verdance Alpha: {S(g(map_entry, 'title'))}"
    frames = required_frames(intent)
    description = objective_description(intent)

    f = Field(ws, intent, state, log)
    f.eye_story = intent["eyeStory"] if (has(intent, "eyeStory") and T(intent["eyeStory"])) else None

    # --- Difficulty scaling from campaign state ---
    # expectedEnemyScale.center comes from zone-memory abstract presence; the difficulty coefficient
    # already folds the operator dial + softened graph.
    economy = g(intent, "economy")
    diff_coeff = D(economy["difficultyCoefficient"]) if (T(economy) and T(g(economy, "difficultyCoefficient"))) else 1.0
    progression = g(intent, "progression")
    if T(economy) and g(economy, "difficultyDial") is not None:
        dial = D(economy["difficultyDial"])
    elif T(progression) and g(progression, "difficultyDial") is not None:
        dial = D(progression["difficultyDial"])
    elif T(state) and T(g(state, "progression")) and g(state["progression"], "difficultyDial") is not None:
        dial = D(state["progression"]["difficultyDial"])
    else:
        dial = 1.0
    ees = g(intent, "expectedEnemyScale")
    scale_center = D(ees["center"]) if (T(ees) and T(g(ees, "center"))) else 6000.0
    # Soft-cap zone presence so one bloated map cannot jump to "heavy" by accident.
    scale_center = min(11000.0, max(3500.0, scale_center))
    # Onboarding ramp: first hours were ~4x too hot (playtest). Soft open, then climb.
    if mission_number <= 1:
        pressure_tier = 0.25
    elif mission_number <= 2:
        pressure_tier = 0.35
    elif mission_number <= 4:
        pressure_tier = 0.5
    elif mission_number <= 7:
        pressure_tier = 0.75
    else:
        pressure_tier = 1.0
    ramp = min(1.0, 0.55 + 0.1 * (mission_number - 1))
    es = R(max(0.35, min(2.0, scale_center / 6000.0)) * diff_coeff * ramp * pressure_tier, 3)
    log(fmt("Pressure soft-open: mission={0} tier={1} ramp={2} → enemyScale={3}", mission_number, pressure_tier, ramp, es))
    # Difficulty by act (data/escalation/difficulty.json): enemy aggression x the act's scale.
    difficulty_path = ws / "data" / "escalation" / "difficulty.json"
    if difficulty_path.exists():
        try:
            dif = shell_mod.read_json(difficulty_path)
            act_key = "1" if mission_number <= 5 else ("2" if mission_number <= 10 else "3")
            arc_s = D(shell_mod.ci_get(g(dif, "actScale"), act_key))
            if not T(arc_s) or arc_s <= 0:
                arc_s = 1.0
            aggro = D(g(dif, "enemyAggro"))
            if not T(aggro) or aggro <= 0:
                aggro = 1.0
            arc_ramp = 1.0 + 0.03 * max(0, mission_number - 5)
            es = R(min(1.95, max(0.55, es * aggro * arc_s * arc_ramp)), 3)
            log(f"Difficulty: act={act_key} aggro={S(aggro)} actScale={S(arc_s)} -> enemyScale={S(es)}")
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: difficulty.json unreadable: {e}")
    dev_telemetry = False
    dev_period = 150
    # Drop 2 Act 3: massive starting conditions on BOTH sides of the field.
    if is_finale:
        es = R(min(2.6, max(1.35, es * 1.6)), 3)
        log(fmt("Finale scale: kind={0} -> enemyScale={1}", finale_kind, es))
    ops = g(intent, "offscreenPressureSummary")
    max_hazard = D(ops["maxHazard"]) if (T(ops) and T(g(ops, "maxHazard"))) else 0.0

    # Aiming at ground where no enemy base stands is establishing presence there: build defensive value
    # in that zone (fortify_zone; the gadget measures DV). The target never moves. The enemy still
    # stands where its bases are, and anchors on the nearest of them, not on the empty zone.
    presence_from = None
    if not is_finale and target_zone_id and iin(objective_kind, SHELL_CAPABLE_KINDS) and not ieq(objective_kind, "survive_wilds"):
        standing = _standing_pocket_zones(ws, state, map_id)
        if standing is not None and len(standing) > 0 and target_zone_id not in standing:
            presence_from = objective_kind
            objective_kind = "fortify_zone"
            tz_label = S(target_zone["label"]) if (T(target_zone) and T(g(target_zone, "label"))) else target_zone_id
            if T(ot):
                ot["kind"] = "fortify_zone"
                ot["label"] = f"Establish presence in {tz_label}"
            best = None
            best_d = sys.float_info.max
            # PowerShell walked a hashtable's keys here; only an exact tie between two zones' distances
            # could make the order show, and the first-seen order is kept for that.
            for zid in standing.keys():
                zc = zone_center(zone_by_id(zone_map, zid), None)
                if T(zc):
                    d = (zc[0] - enemy_center[0]) ** 2 + (zc[1] - enemy_center[1]) ** 2
                    if d < best_d:
                        best = zc
                        best_d = d
            if T(best):
                enemy_center = best
            log(fmt("Presence: nothing stands in {0}; the job is to establish presence there (was {1}).",
                    target_zone_id, presence_from))
    presence_kind = iin(objective_kind, ("seize_lane", "gate_control", "hold_plateau"))
    fortify_kind = iin(objective_kind, ("fortify_zone", "home_founding"))
    env = g(intent, "environment")
    map_family = S(env["mapFamily"]) if (T(env) and T(g(env, "mapFamily"))) else "tempo"
    # Rock Jungle founding / dig-in: empty deep wilds (raptors only). No Armada/Cortex camps, no
    # living-shell scrap occupation, no Null Merc foothold on the shelf.
    against = ""
    if has(intent, "against") and T(intent["against"]):
        against = S(intent["against"])
    elif has(intent, "worldConflict") and T(intent["worldConflict"]) and T(g(intent["worldConflict"], "primaryEnemy")):
        against = S(intent["worldConflict"]["primaryEnemy"])
    journey = S(intent["journey"]) if (has(intent, "journey") and T(intent["journey"])) else ""
    is_rock_jungle = ieq(map_id, "the_rock_jungle")
    is_wild_home = is_rock_jungle and (fortify_kind or ieq(against, "wild") or ieq(journey, "home_founding")
                                       or ieq(objective_kind, "survive_wilds"))
    if is_wild_home:
        log("Rock Jungle wild home: empty shelf (raptors only; no empire camps / living-shell scrap).")

    if T(progression) and T(g(progression, "mode")):
        xp_mode = S(progression["mode"])
    elif T(state) and T(g(state, "progression")) and T(g(state["progression"], "mode")):
        xp_mode = S(state["progression"]["mode"])
    else:
        xp_mode = "cracked_farm"

    # --- The standing war: Null Mercs vs Armada ---
    # The mercs keep a foothold on every faction-war mission. Reputation decides whether their guns
    # tolerate the player (allied) or merely share a target (wary). Allied mercs tip the field, so the
    # Armada garrison scales up slightly to compensate.
    merc_info = intent["worldConflict"]["nullMercs"] if (has(intent, "worldConflict") and T(g(g(intent, "worldConflict"), "nullMercs"))) else None
    if T(merc_info) and g(merc_info, "reputation") is not None:
        merc_rep = D(merc_info["reputation"])
    elif T(state) and T(g(state, "reputation")) and g(state["reputation"], "nullmercs") is not None:
        merc_rep = D(state["reputation"]["nullmercs"])
    else:
        merc_rep = 43.0
    mercs_allied = B(merc_info["alliedWithPlayer"]) if (T(merc_info) and g(merc_info, "alliedWithPlayer") is not None) else merc_rep >= 40.0
    merc_foothold_scale = D(merc_info["footholdScale"]) if (T(merc_info) and g(merc_info, "footholdScale") is not None) else 1.0
    mercs_present = (not ieq(objective_kind, "hive_clear_or_bypass")) and (not is_wild_home)
    if mercs_present and mercs_allied:
        es = R(es * 1.1, 3)
    # Drop 4: clamp the final scale into the ladder's authored window. Campaign state still moves the
    # needle INSIDE the window; the owner's difficulty dial scales the window walls themselves.
    if T(esc_plan) and T(g(esc_plan, "scaleWindow")):
        win = arr(esc_plan["scaleWindow"])
        if len(win) >= 2:
            lo = D(win[0]) * dial
            hi = D(win[1]) * dial
            if hi < lo:
                lo, hi = hi, lo
            pre = es
            es = R(min(hi, max(lo, es)), 3)
            if es != pre:
                log(fmt("Escalation window: {0} -> {1} (window [{2}, {3}] x dial {4})", pre, es, win[0], win[1], R(dial, 2)))
    fortify = es >= 1.4

    # Defenses face the player's approach; patrols defend presence zones or pressure the midline on
    # destruction objectives.
    face_x = sign(deploy_center[0] - enemy_center[0]) or 1
    face_z = sign(deploy_center[1] - enemy_center[1]) or 1
    if presence_kind:
        patrol_target = [enemy_center[0], enemy_center[1]]
    else:
        # Destruction objectives: patrols screen the camp approaches (2/3 toward the camp from the
        # midline) rather than camping the middle of the map.
        mid_x = (deploy_center[0] + enemy_center[0]) / 2.0
        mid_z = (deploy_center[1] + enemy_center[1]) / 2.0
        patrol_target = [((mid_x + 2.0 * enemy_center[0]) / 3.0), ((mid_z + 2.0 * enemy_center[1]) / 3.0)]

    wild_center = push_to_rim([0.08, 0.50])
    # The Rock Jungle's hive stands in its south-west corner (owner call, 2026-10-23): the nest, the
    # queen and every new burrow (the raptor startbox) all sit there.
    jungle_hive_center = zone_center(zone_by_id(zone_map, "TRJ_SW_LANE"), [0.14, 0.84])
    if is_rock_jungle:
        wild_center = jungle_hive_center

    # --- Camp assembly ---
    roster = intent["roster"] if (has(intent, "roster") and T(intent["roster"])) else None
    commerce = intent["commerce"] if (has(intent, "commerce") and T(intent["commerce"])) else None
    resource_mod = D(economy["resourceModifier"]) if (T(economy) and g(economy, "resourceModifier") is not None) else 1.0
    strike_doctrine = I(arc["playerCommanders"]) <= 0
    # Drop 2: act 2+ is base-building doctrine even on raid contracts; act 3 is the finale kit.
    if act_num >= 2:
        strike_doctrine = False
    if is_kings:
        player_kit: List[Any] = []  # the start commander is the company's king; nobody else walks out
    elif opening_mission:
        player_kit = kits.opening_strike_team(commerce)
        log("Opening kit: mercenary Punch of Thugs + 2 Karkinos + Phobos Vane + durable rez-bot Ketha; no commander suit.")
    elif act_num >= 3 or is_finale:
        player_kit = kits.finale_kit_from_roster(map_family, roster, resource_mod, commerce)
    elif act_num >= 2 and T(roster):
        player_kit = kits.player_kit_from_roster(map_family, roster, resource_mod, commerce)
    elif strike_doctrine:
        player_kit = kits.tactics_player_kit(map_family, roster, resource_mod, arc["unitPrinter"], commerce)
    elif T(roster):
        player_kit = kits.player_kit_from_roster(map_family, roster, resource_mod, commerce)
    else:
        player_kit = kits.add_commerce_deploy_to_kit(kits.player_kit(map_family), commerce)
    player_kit = kits.add_reserve_to_kit(player_kit, roster)
    if T(commerce):
        tnb = commerce["tenebrium"] if g(commerce, "tenebrium") is not None else 0
        if g(commerce, "metalK") is not None:
            mk = commerce["metalK"]
        elif g(commerce, "credits") is not None:
            mk = commerce["credits"]
        else:
            mk = 0
        dep_n = len(arr(commerce["deploy"])) if T(g(commerce, "deploy")) else 0
        log(fmt("Commerce: Tenebrium={0} metalK={1} deployables={2}", tnb, mk, dep_n))
    # Stamp banked veteran XP onto kit units (the majority is retained between rounds).
    if T(roster):
        player_kit = kits.apply_cadre_xp_to_kit(player_kit, roster)
        stamped = sum(1 for s in player_kit if T(s) and g(s, "xp") is not None and D(s["xp"]) > 0)
        if stamped > 0:
            log(fmt("Cadre XP stamped on {0} kit unit groups (majority retain).", stamped))
    # Chassis side stays Legion (BAR unit tree); presentation is Ashwalkers.
    f.base_recipes = {"ashwalker_player_kit": list(player_kit), "legion_player_kit": list(player_kit)}
    # Final band after merc / farm modifiers so the card matches the field.
    diff_band = "heavy" if es >= 1.6 else ("reinforced" if es >= 1.2 else ("light" if es <= 0.85 else "standard"))
    difficulty_line = f"Expected opposition: {diff_band} (scale {S(es)}) | dial {S(R(dial, 2))}"
    log(fmt("Arc profile: id={0} playerCommanders={1} enemyMode={2} allyPower={3} escalation={4} ai={5}",
            arc["id"], arc["playerCommanders"], arc["enemyMode"], arc["allyPower"], arc["escalation"], arc["enemyAI"]))
    # The enemy AI for the startscript: BARb, else SimpleAI. (A Greenest Fields SimpleDefenderAI branch
    # tested a $mapId that was never set, so it never ran; removed 2026-10-27.)
    enemy_ai_short = "BARb" if ieq(S(arc["enemyAI"]), "barbarian") else "SimpleAI"
    log(fmt("Enemy AI shortName: {0} (map={1} profile={2})", enemy_ai_short, map_id, arc["enemyAI"]))
    f.ally_teams = [{"id": 0, "startRect": start_rect(deploy_center, 0.20)}]
    f.teams = [{"id": 0, "side": "Legion", "allyTeam": 0, "base": [deploy_center[0], deploy_center[1]],
                "rgb": [0.25, 0.85, 0.35], "label": "Ashwalkers", "faction": "ashwalkers"}]
    # The walker wears the company's commander suit (verdance.campaign.suits): its start commander is
    # that suit's body. Buy Cortex's and the company starts in a corcom; Koom's Armada suit, an armcom.
    if commander_unlocked and T(commander_row) and has(commander_row, "unitDef"):
        suit = S(commander_row["unitDef"])
        if ilike(suit, "armcom*"):
            f.teams[0]["side"] = "Armada"
        elif ilike(suit, "corcom*"):
            f.teams[0]["side"] = "Cortex"
        log(fmt("Commander suit: {0} ({1})", suit, f.teams[0]["side"]))
    f.forces = [{"id": "player_deployment", "label": f"Ashwalker drop - {S(g(intent, 'deploymentZoneId'))}", "teamID": 0,
                 "side": "Legion", "faction": "ashwalkers", "role": "player_anchor",
                 "base": {"x": deploy_center[0], "z": deploy_center[1]}, "recipe": "ashwalker_player_kit"}]

    # The numbers every camp reads.
    f.arc_profile = arc
    f.enemy_scale = es
    f.face_x, f.face_z = face_x, face_z
    f.patrol_target = patrol_target
    f.fortify = fortify
    f.objective_strength = objective_strength
    f.max_hazard = max_hazard
    f.enemy_ai_short = enemy_ai_short
    f.is_finale = is_finale
    f.objective_kind = objective_kind
    f.target_zone_id = target_zone_id
    f.mercs_allied = mercs_allied
    f.enemy_center = enemy_center

    # OCCUPATION MODEL LOCK (outbound 44): living shell + decoy + scars is the ONE path. Hand-built
    # camps are the fallback when no template exists. used_shell: anything shell-shaped stands
    # (occupation or only the company's footprint). shell_occupied: the living shell's enemy bases
    # stand; a company footprint is not an enemy base.
    shell_occupied = False
    if is_wild_home:
        # The founding shelf stays empty: the player builds the Ashwalker pad; raptors are the only pressure.
        log("Skipping living-shell occupation on Rock Jungle wild home founding.")
    elif T(theater) and (is_kings or (is_standing_war and not keep_shell)):
        log(fmt("Set piece {0}: no living-shell occupation.", S(g(theater, "kind"))))
    elif iin(objective_kind, SHELL_CAPABLE_KINDS) or T(presence_from):
        # The enemy's bases stand whatever the job is; a presence job still has the world around it.
        anchor_side = side
        if ieq(objective_kind, "survive_wilds"):
            anchor_side = "Legion"
        if ieq(map_id, "ancient_bastion"):
            anchor_side = "Armada"
        f.used_shell = f.try_apply_living_shell(map_id, target_zone_id, description, enemy_center, anchor_side)
        shell_occupied = bool(f.used_shell)
    # DRY: company pads always rehydrate when there is a footprint bag, even if the occupation shell
    # path skipped (non-capable kind / missing template).
    if not f.used_shell:
        if f.ensure_player_footprint_shell(map_id, target_zone_id):
            f.used_shell = True

    # The field's set piece replaces the usual camps; then the finale set pieces, authored by path.
    if is_kings:
        f.add_kings(theater)
    elif is_standing_war:
        f.add_standing_war(theater)
    elif is_finale:
        if ieq(finale_kind, "spire_jump"):
            # Burn the hive heart; a deep nest keeps the pressure honest.
            f.add_raptor_camp(enemy_center, True, description)
            nest = [clamp01(enemy_center[0] + 0.18), clamp01(enemy_center[1] - 0.16)]
            f.add_raptor_camp(nest, False, "Raptor deep nest")
        else:
            # Overthrow: the citadel, an LRPC crown plus a command post wing; both are objective
            # targets, so the finale requires breaking the whole spine.
            t = faction(side)
            f.add_faction_camp(side, enemy_center, kits.centerpiece_lrpc(t), description, with_eco=True,
                               with_production=True, support=kits.support_lrpc(t))
            post = [clamp01(enemy_center[0] - 0.14), clamp01(enemy_center[1] + 0.12)]
            f.add_faction_camp(side, post, kits.centerpiece_command_post(t), "Citadel command post", with_eco=True,
                               with_production=True)
    else:
        # Outside the finales Python sends seize_lane, hive_clear_or_bypass, fortify/home kinds and
        # survive_wilds; the camps for the old raid / relay / key-structure kinds were retired 2026-10-27.
        if ieq(objective_kind, "hive_clear_or_bypass"):
            # On the Rock Jungle the hive is the south-west nest, wherever the card aimed.
            f.add_raptor_camp(jungle_hive_center if is_rock_jungle else enemy_center, True, description)
        elif is_wild_home or ieq(against, "wild"):
            # Empty wilds dig-in / fortify: raptor pressure only (added below via has_wild).
            log(fmt("Wild objective {0}: no empire faction camp.", objective_kind))
        elif not shell_occupied:
            # Fallback = thin front-band garrison + reinforcement packs (WO-004).
            f.add_faction_camp(side, enemy_center, None, description, with_eco=False, front_band=True)

    # Visit tier wardens (verdance.world.visit_tiers): on a living-shell field's second and later
    # visits, Armada BARbarians (va_warden) start on the shell's richest pockets and fortify them.
    #
    # PS 5.1 FAULT, KEPT: the PS1 read the list with `$x = if (...) { @(list) }`, which hands back the
    # bare object when the list holds one warden, and Windows PowerShell 5.1 gives a bare
    # PSCustomObject no .Count. So one warden never took the field on the PC (tour 02, 2026-11-04:
    # one warden on Greenest Fields, three teams), while two or more did. Kept so the field does not
    # change under the gadget unannounced; fixing it is an owner call.
    visit_tier = g(intent, "visitTier")
    tier_wardens = arr(visit_tier["wardens"]) if (T(visit_tier) and has(visit_tier, "wardens")) else []
    warden_count = None if (len(tier_wardens) == 1 and isinstance(tier_wardens[0], dict)) else len(tier_wardens)
    if shell_occupied and warden_count is not None and warden_count > 0 and not is_finale and not T(theater):
        for wd in tier_wardens:
            wc = [D(g(wd, "x")), D(g(wd, "z"))]
            wt = f.new_war_team("armada", wc, "warden " + S(g(wd, "zoneId")), 0.08)
            f.ai[-1]["options"] = {"profile": "va_warden"}
            f.teams[-1]["handicap"] = I(g(wd, "handicap"))
            if f.shell_ally_id is not None:
                f._ally(f.shell_ally_id, wt["allyID"])
        log(fmt("Visit tier {0}: {1} Armada warden(s) fortifying {2}", g(visit_tier, "tier"), warden_count,
                ", ".join(S(g(w, "zoneId")) for w in tier_wardens)))

    # Drop 3 act-1 texture: roving warband packs on the approach axis.
    if not is_finale and not T(theater) and not shell_occupied and ieq(S(arc["enemyMode"]), "warband"):
        f.add_warband_packs(deploy_center, enemy_center, max(0.6, es * 0.8))

    # Drop 4 escalation: secondary-objective camps at the plan's resolved zones. Anything that
    # collides with the deploy/target zones or lacks a center is skipped.
    if len(esc_secondaries) > 0 and not is_finale and not is_kings and T(zone_map) and T(g(zone_map, "zones")):
        sec_side = S(f.primary_enemy_side) if T(f.primary_enemy_side) else side
        for sec in esc_secondaries:
            if not T(sec) or not T(g(sec, "zoneId")):
                continue
            sec_zid = S(sec["zoneId"])
            if ieq(sec_zid, target_zone_id) or ieq(sec_zid, deploy_zone_id):
                continue
            sec_zone = next((z for z in arr(zone_map["zones"]) if ieq(S(g(z, "zoneId")), sec_zid)), None)
            if not T(sec_zone):
                continue
            sec_center = zone_center(sec_zone, None)
            if not T(sec_center):
                continue
            sec_label = S(sec["label"]) if T(g(sec, "label")) else sec_zid
            sec_id = S(sec["id"]) if T(g(sec, "id")) else "sec_" + sec_zid.lower()
            if ieq(S(g(sec, "kind")), "scout"):
                # A scout mark: look hard at the zone (the gadget reads the company's look at it).
                f.secondary_meta.append({"id": sec_id, "label": sec_label, "kind": "scout", "required": False,
                                         "zoneId": sec_zid, "x": D(sec_center[0]), "z": D(sec_center[1])})
                log(fmt("Secondary objective: scout {0} ({1})", sec_zid, sec_label))
                continue
            if shell_occupied and T(f.living_shell):
                # The mark is the shell's own works in that zone (the gadget tags them); no camp is
                # built. The opening only spawns its primary pocket, and a scarred or vault pocket is
                # no mark.
                if T(f.living_shell.get("localPocketOnly")):
                    continue
                sec_pk = next((p for p in arr(f.living_shell.get("pockets"))
                               if T(p) and ieq(S(g(p, "zoneId")), sec_zid) and not T(g(p, "scarred"))
                               and not T(g(p, "optionalTarget")) and I(g(p, "unitCount")) > 0), None)
                if not T(sec_pk):
                    continue
                sec_zones = arr(f.living_shell["secondaryZones"]) if "secondaryZones" in f.living_shell else []
                sec_zones.append({"zoneId": sec_zid, "id": sec_id, "required": B(g(sec, "required"))})
                f.living_shell["secondaryZones"] = sec_zones
                sec_meta = {"id": sec_id, "label": sec_label, "required": B(g(sec, "required")),
                            "x": D(sec_pk["center"][0]), "z": D(sec_pk["center"][1]),
                            "pocketId": S(g(sec_pk, "pocketId")), "source": "living_shell_secondary"}
                log(fmt("Secondary objective: {0} ({1}) on the shell works at {2}", sec_id,
                        "REQUIRED" if T(g(sec, "required")) else "bonus", sec_zid))
            else:
                sec_meta = f.add_secondary_objective_camp(sec_side, sec_center, max(0.4, es * 0.5), sec_id,
                                                          B(g(sec, "required")), sec_label)
            if T(sec_meta):
                sec_meta["zoneId"] = sec_zid
                f.secondary_meta.append(sec_meta)

    # Living-shell optional high-value pockets (e.g. Greenest centre fusion vaults). Already
    # pre-placed in the shell: register bonus secondary meta only (required=false). Lua books the
    # fusion keepClass=high_value into the ledger.
    if T(f.living_shell) and T(f.living_shell.get("pockets")) and not is_finale:
        seen = CIDict()
        for sm in f.secondary_meta:
            if T(sm) and T(g(sm, "id")):
                seen[S(sm["id"])] = True
        for pk in arr(f.living_shell["pockets"]):
            if not T(pk) or not shell_mod.pocket_optional(pk):
                continue
            sec_zid = S(g(pk, "zoneId"))
            if not sec_zid or ieq(sec_zid, target_zone_id) or ieq(sec_zid, deploy_zone_id):
                continue
            sec_id = "bonus_fus_" + S(g(pk, "pocketId")).lower()
            if sec_id in seen:
                continue
            cx, cz = 0.5, 0.5
            if T(g(pk, "center")) and len(arr(pk["center"])) >= 2:
                cx, cz = D(pk["center"][0]), D(pk["center"][1])
            sec_label = S(pk["label"]) if T(g(pk, "label")) else sec_zid
            f.secondary_meta.append({"id": sec_id, "label": sec_label, "required": False, "x": cx, "z": cz,
                                     "zoneId": sec_zid, "pocketId": S(g(pk, "pocketId")),
                                     "source": "living_shell_optional", "highValue": True})
            seen[sec_id] = True
            log(fmt("Optional high-value mark: {0} at {1} ({2:n2}, {3:n2}) — bonus, not required", sec_id, sec_zid, cx, cz))

    # Drop 3 finale dressing: persistent-base snapshots walk back onto the field. Player-bloc zones
    # return as standing team-0 bases; empire zones as thin static camps on the primary enemy team.
    if is_finale and not is_kings and has(intent, "persistentBaseRehydrate") and T(intent["persistentBaseRehydrate"]):
        rehydrated = 0
        for entry in arr(intent["persistentBaseRehydrate"]):
            if rehydrated >= 3:
                break
            if not T(entry) or not T(g(entry, "zoneId")):
                continue
            zid = S(entry["zoneId"])
            if ieq(zid, deploy_zone_id) or ieq(zid, target_zone_id):
                continue
            zone = zone_by_id(zone_map, zid)
            if not T(zone):
                continue
            zc = zone_center(zone, None)
            if not T(zc):
                continue
            ctrl = S(g(entry, "control"))
            if iin(ctrl, ("nullmercs", "ashwalkers")):
                specs = shell_mod.rehydrate_specs(g(entry, "snapshot"), "leg")
                if len(specs) == 0:
                    continue
                rid = f"rehydrate_player_{zid}"
                f.base_recipes[rid] = specs
                f.forces.append({"id": rid, "label": f"Standing base - {zid}", "teamID": 0, "side": "Legion",
                                 "faction": "ashwalkers", "role": "rehydrated_base",
                                 "base": {"x": zc[0], "z": zc[1]}, "recipe": rid})
                rehydrated += 1
            elif iin(ctrl, ("armada", "cortex")) and f.primary_enemy_team_id is not None:
                # Only zones matching the primary enemy's faction: a second empire's hardware on that
                # team would read as nonsense.
                if not ieq(ctrl, S(f.primary_enemy_side).lower()):
                    continue
                prefix = "cor" if ieq(ctrl, "cortex") else "arm"
                specs = shell_mod.rehydrate_specs(g(entry, "snapshot"), prefix)
                if len(specs) == 0:
                    continue
                rid = f"rehydrate_enemy_{zid}"
                f.base_recipes[rid] = specs
                f.forces.append({"id": rid, "label": f"Standing works - {zid}", "teamID": f.primary_enemy_team_id,
                                 "side": f.primary_enemy_side, "faction": ctrl, "role": "rehydrated_base",
                                 "base": {"x": zc[0], "z": zc[1]}, "recipe": rid})
                rehydrated += 1
        if rehydrated > 0:
            log(fmt("Finale rehydration: {0} standing bases restored from campaign memory.", rehydrated))

    # Null Merc foothold: same rim constraint as player infil; enter from an edge lane on the flank,
    # not a mid-map pop-in on the deploy->target axis.
    if mercs_present and not T(theater):
        axis_x = enemy_center[0] - deploy_center[0]
        axis_z = enemy_center[1] - deploy_center[1]
        axis_len = math.sqrt(axis_x * axis_x + axis_z * axis_z)
        if axis_len < 0.001:
            axis_len = 0.001
        perp_x = -axis_z / axis_len
        perp_z = axis_x / axis_len
        mid_x = (deploy_center[0] + enemy_center[0]) / 2.0
        mid_z = (deploy_center[1] + enemy_center[1]) / 2.0
        candidates = [
            push_to_rim([clamp01(mid_x + 0.26 * perp_x), clamp01(mid_z + 0.26 * perp_z)]),
            push_to_rim([clamp01(mid_x - 0.26 * perp_x), clamp01(mid_z - 0.26 * perp_z)]),
        ]
        merc_center = candidates[0]
        best_score = -1.0
        for cand in candidates:
            dxd = cand[0] - deploy_center[0]
            dzd = cand[1] - deploy_center[1]
            dxw = cand[0] - wild_center[0]
            dzw = cand[1] - wild_center[1]
            rim_bonus = 1.0 - edge_score(cand[0], cand[1])
            score = min(math.sqrt(dxd * dxd + dzd * dzd), math.sqrt(dxw * dxw + dzw * dzw)) + (0.35 * rim_bonus)
            if score > best_score:
                best_score = score
                merc_center = cand
        # Drop 3: finales field a full-war merc foothold; the standing war shows up.
        merc_scale_base = max(1.0, es * 1.05) if is_finale else max(0.5, es * 0.75)
        f.add_null_merc_camp(merc_center, merc_scale_base * merc_foothold_scale, mercs_allied)
        # Drop 3 finale dressing: availableAllies defectors materialize on the opposite flank.
        if is_finale:
            ally_names: List[str] = []
            r = g(intent, "roster")
            if T(r) and has(r, "availableAllies") and T(r["availableAllies"]):
                ally_names = [S(x) for x in each(r["availableAllies"])]
            low = [n.lower() for n in ally_names]
            def_side = "Cortex" if "cortex_defectors" in low else ("Armada" if "armada_deserters" in low else "")
            if def_side:
                def_center = [clamp01(2.0 * mid_x - merc_center[0]), clamp01(2.0 * mid_z - merc_center[1])]
                f.add_defector_camp(def_side, def_center, max(0.5, es * 0.45))

    # Wild pressure nest on wild-family maps whose objective is not already the hive.
    if has_wild and not is_kings and not ieq(objective_kind, "hive_clear_or_bypass"):
        f.add_raptor_camp(wild_center, False, "Raptor wild pressure")
    if not is_finale and not is_kings:
        f.add_wild_dens()

    # Same-faction camps must never shoot each other: Spring allies only through explicit pacts and
    # every camp rides its own allyteam, so pact all armada-armada and cortex-cortex allyteam pairs.
    # Player, mercs, defectors and raptors are deliberately excluded (their stances are set above).
    same = CIDict()
    for tm in f.teams:
        fac = S(g(tm, "faction"))
        if not ieq(fac, "armada") and not ieq(fac, "cortex"):
            continue
        if fac not in same:
            same[fac] = []
        same[fac] = same[fac] + [I(tm["allyTeam"])]
    for fac in hashtable_key_order(same.keys()):
        ids = sort_unique_ints(same[fac])
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                f._ally(ids[i], ids[j])
        if len(ids) > 1:
            log(fmt("Faction pact: {0} camps allied across {1} allyteams.", fac, len(ids)))
    # Everyone standing WITH the player also stands with each other (mercs + defectors on a finale
    # would otherwise brawl across their own allyteams).
    player_allied: List[int] = []
    for pact in list(f.alliances):
        if T(pact.get("allied")) and I(pact["allyTeamA"]) == 0:
            player_allied.append(I(pact["allyTeamB"]))
        elif T(pact.get("allied")) and I(pact["allyTeamB"]) == 0:
            player_allied.append(I(pact["allyTeamA"]))
    player_allied = sort_unique_ints(player_allied)
    for i in range(len(player_allied)):
        for j in range(i + 1, len(player_allied)):
            f._ally(player_allied[i], player_allied[j])

    # Stable installation identity is map + authored pocket. It survives candidate regeneration and
    # lets Lua retarget a specific pre-existing installation even when several pockets share a zone.
    ordinal = 0
    for node in f.map_occupation:
        ordinal += 1
        pocket_key = S(node["pocketId"]) if T(node.get("pocketId")) else f"zone_{S(node.get('zoneId'))}_{ordinal}"
        node["installationId"] = f"{map_id}::{pocket_key}"

    # Hero manifest for the HUD/name tags: the hub dropping list only. deployAces is core + the packs
    # on this sheet. No union with crewBand on top of it, and no invented Vane/Ketha when the sheet
    # left them home.
    hero_manifest: List[Dict[str, Any]] = []
    aces_early = arr(intent["deployAces"]) if T(g(intent, "deployAces")) else []
    crew_band = arr(intent["crewBand"]) if (has(intent, "crewBand") and T(intent["crewBand"])) else []
    deploy_allow: List[str] = []  # a HashSet[string]: case-sensitive, insertion order

    def _allow(x: Any) -> None:
        if T(x) and S(x) not in deploy_allow:
            deploy_allow.append(S(x))

    for x in (aces_early if len(aces_early) > 0 else crew_band):
        _allow(x)
    if T(roster) and has(roster, "heroes") and T(roster["heroes"]):
        for h in each(roster["heroes"]):
            hid = S(g(h, "heroId"))
            if hid not in deploy_allow:
                continue
            hero_manifest.append({
                "id": hid,
                "name": S(g(h, "name")),
                "unitDefName": S(g(h, "unitDef")),
                "missionCritical": B(g(h, "missionCritical")),
                "level": I(h["level"]) if g(h, "level") is not None else 1,
                "rank": S(h["rank"]) if T(g(h, "rank")) else "Runner",
                "xp": D(h["xp"]) if g(h, "xp") is not None else 0.0,
                "campaignXp": D(h["campaignXp"]) if g(h, "campaignXp") is not None else 0.0,
                "hpMult": D(h["hpMult"]) if g(h, "hpMult") is not None else 1.35,
            })
    # Every deployAllow id appears on the HUD (core + sealed band). Roster sheets sometimes omit band
    # packs; crew_packs / characters fill the gaps.
    crew_pack_heroes = None
    crew_pack_path = ws / "data" / "story" / "crew_packs.json"
    if crew_pack_path.exists():
        try:
            crew_pack_heroes = g(shell_mod.read_json(crew_pack_path), "heroes")
        except Exception:  # noqa: BLE001
            crew_pack_heroes = None
    for need in list(deploy_allow):
        if any(ieq(S(hm["id"]), need) for hm in hero_manifest):
            continue
        pack = shell_mod.ci_get(crew_pack_heroes, need) if (T(crew_pack_heroes) and shell_mod.ci_has(crew_pack_heroes, need)) else None
        ch = None
        if T(state) and T(g(state, "characters")) and shell_mod.ci_has(state["characters"], need):
            ch = shell_mod.ci_get(state["characters"], need)
        fallback_name = "Ash-Captain Vane" if ieq(need, "vane") else ("Ketha" if ieq(need, "ketha") else need)
        fallback_def = "legcen" if ieq(need, "vane") else ("legrezbot" if ieq(need, "ketha") else "legcen")
        if T(pack) and T(g(pack, "name")):
            name = pack["name"]
        elif T(ch) and T(g(ch, "name")):
            name = ch["name"]
        else:
            name = fallback_name
        if T(pack) and T(g(pack, "unitDef")):
            udef = pack["unitDef"]
        elif T(ch) and T(g(ch, "unitDef")):
            udef = ch["unitDef"]
        else:
            udef = fallback_def
        hero_manifest.append({
            "id": S(need),
            "name": S(name),
            "unitDefName": S(udef),
            "missionCritical": ieq(need, "ketha") or bool(T(pack) and eq(g(pack, "missionCritical"), True)),
            "level": 1,
            "rank": "Runner",
            "xp": 0.0,
            "campaignXp": 0.0,
            "hpMult": 2.5 if ieq(need, "ketha") else (1.65 if ieq(need, "vane") else 1.35),
        })

    # Escalation fallback: if the camp's live mobiles are all dead, waves keep arriving as the enemy
    # side's standard column instead of silently drying up.
    fb_t = faction(side)
    fallback_wave_defs = [fb_t["raider"], fb_t["skirm"], fb_t["assault"]]
    if ieq(objective_kind, "hive_clear_or_bypass"):
        fallback_wave_defs = ["raptor_land_swarmer_basic_t1_v1", "raptor_land_swarmer_basic_t2_v1"]

    graph = state["graph"] if (T(state) and T(g(state, "graph"))) else {}
    reputation = state["reputation"] if (T(state) and T(g(state, "reputation"))) else {}
    companions: List[Dict[str, Any]] = []
    if T(state) and T(g(state, "companion")):
        comp = state["companion"]
        comp_def = S(comp["unitDefName"]) if T(g(comp, "unitDefName")) else "legcen"
        comp_xp = D(comp["xp"]) if g(comp, "xp") is not None else 0.0
        bag = kits.cadre_xp_bag(roster, comp_def)
        if T(bag) and bag["xp"] > comp_xp:
            comp_xp = D(bag["xp"])
        companions = [{
            "id": g(comp, "id"),
            "displayName": g(comp, "displayName"),
            "unitDefName": comp_def,
            "xp": comp_xp,
            "morale": g(comp, "morale"),
            "loyalty": g(comp, "loyalty"),
            "stress": g(comp, "stress"),
            "autonomy": g(comp, "autonomy"),
            "commandMode": g(comp, "commandMode"),
        }]

    # Hub multi-capture (arc 2+): the primary is targetZoneId; the rest are secondary marks.
    if T(g(intent, "captureZoneIds")):
        capture_ids = arr(intent["captureZoneIds"])
    elif T(ot) and T(g(ot, "captureZoneIds")):
        capture_ids = arr(ot["captureZoneIds"])
    else:
        capture_ids = [target_zone_id]
    secondary_ids: List[Any] = []
    if T(g(intent, "secondaryCaptureZoneIds")):
        secondary_ids = arr(intent["secondaryCaptureZoneIds"])
    elif T(ot) and T(g(ot, "secondaryCaptureZoneIds")):
        secondary_ids = arr(ot["secondaryCaptureZoneIds"])
    hub_choice_id = S(intent["hubChoiceId"]) if T(g(intent, "hubChoiceId")) else None
    hub_deploy_aces = list(aces_early)

    # Field recruits: the encounter field's draw for this sortie. Marked hub zones (target / infil)
    # make their hero likelier (encounter_rules markedGround); they do not seat them. Wreck-rez modes
    # stamp spawnAsWreck so BAR seeds a corpse, not a live poof.
    field_recruits: List[Dict[str, Any]] = []
    marked: List[Any] = []
    if T(g(intent, "captureZoneIds")):
        marked += arr(intent["captureZoneIds"])
    marks = g(intent, "marks")
    if has(intent, "marks") and T(marks):
        if T(g(marks, "captureZoneIds")):
            marked += arr(marks["captureZoneIds"])
        if T(g(marks, "deployZoneId")):
            marked.append(S(marks["deployZoneId"]))
    if T(g(intent, "deploymentZoneId")):
        marked.append(S(intent["deploymentZoneId"]))
    if target_zone_id:
        marked.append(target_zone_id)
    uniq: List[Any] = []
    for z in marked:  # Where-Object { $_ } | Select-Object -Unique (case-sensitive, first wins)
        if T(z) and z not in uniq:
            uniq.append(z)
    marked = uniq
    # Not in the kings' showdown: a hostile recruit loose on the map decided the throne (a Tsunami
    # seaplane killed the Cortex king at minute 7, rig 2026-11-03).
    if not is_kings and T(state) and has(state, "fieldPool") and T(state["fieldPool"]):
        arch = S(g(intent, "objectiveArchetype"))
        if not arch and has(intent, "contractKind"):
            arch = S(intent["contractKind"])
        ranked = _field_recruit_rows(ws, state, map_id, marked, arch, log)
        rank_index = 0
        for row in ranked:
            if not T(row):
                continue
            rank_index += 1
            r_zone = S(row["zoneId"]) if T(g(row, "zoneId")) else None
            nx, nz = 0.55, 0.55
            if T(r_zone) and T(zone_map):
                fz = zone_by_id(zone_map, r_zone)
                if T(fz):
                    fc = zone_center(fz, [enemy_center[0], enemy_center[1]])
                    if T(fc):
                        nx, nz = D(fc[0]), D(fc[1])
            elif T(enemy_center):
                nx = min(0.92, D(enemy_center[0]) + 0.04)
                nz = min(0.92, D(enemy_center[1]) + 0.04)
            # Spread stacked same-pad wrecks so CreateUnit does not collide.
            nx = min(0.96, nx + ((rank_index - 1) * 0.012))
            nz = min(0.96, nz + ((rank_index - 1) * 0.008))
            mode = S(row["recruitMode"] if T(g(row, "recruitMode")) else "wreck_rez")
            as_wreck = True
            if g(row, "spawnAsWreck") is not None:
                as_wreck = B(row["spawnAsWreck"])
            elif not iin(mode, ("wreck_rez", "retrieve_stash")):
                as_wreck = False
            if T(g(row, "unitDef")):
                hero_def = S(row["unitDef"])
            elif T(g(row, "unitDefName")):
                hero_def = S(row["unitDefName"])
            else:
                hero_def = "legcen"
            wreck_def = S(row["wreckUnitDef"]) if (has(row, "wreckUnitDef") and T(row["wreckUnitDef"])) else None
            if T(g(row, "name")):
                hero_name = row["name"]
            elif T(g(row, "heroName")):
                hero_name = row["heroName"]
            else:
                hero_name = g(row, "heroId")
            entry = {
                "heroId": S(g(row, "heroId")),
                "heroName": S(hero_name),
                "unitDefName": hero_def,
                "zoneId": r_zone,
                "x": R(nx, 4),
                "z": R(nz, 4),
                "recruitable": True,
                "recruitMode": mode,
                "requiresVictory": B(g(row, "requiresVictory")),
                "optionalJoin": B(g(row, "optionalJoin")),
                "heroHpMult": 1.5,
                "heroXp": R(_soft_double(g(row, "seedXp"), 0.2), 3),
                "beliefScore": R(_soft_double(g(row, "beliefScore"), 0.0), 3),
                "spawnAsWreck": as_wreck,
                # Tension with the party: alive and against us (verdance.company.encounters.apply_meeting_stance).
                "stance": S(g(row["stance"], "kind")) if (has(row, "stance") and T(row["stance"])) else None,
                "blurb": S(row["blurb"]) if T(g(row, "blurb")) else None,
            }
            if T(wreck_def):
                entry["wreckUnitDef"] = wreck_def
            field_recruits.append(entry)
    # People the company left on this map stand where they stood (verdance.belief.manifest.field_people).
    field_people: List[Dict[str, Any]] = []
    for fp in (arr(intent["fieldPeople"]) if has(intent, "fieldPeople") else []):
        if not T(fp) or not T(g(fp, "heroId")):
            continue
        fz = zone_by_id(zone_map, S(g(fp, "zoneId"))) if T(zone_map) else None
        fc = zone_center(fz, [0.5, 0.5])
        field_people.append({"heroId": S(fp["heroId"]), "zoneId": S(g(fp, "zoneId")),
                             "x": R(D(fc[0]), 4), "z": R(D(fc[1]), 4)})
    # Rescues are never the job (2026-10-27): every job is territory, and a wreck waiting in the wound
    # is a bonus mark. A raised hero goes home from where the company landed (game_verdance_exfil).
    if len(field_recruits) > 0:
        log(fmt("Field recruits on {0}: {1} (marks={2})", map_id,
                ", ".join(fmt("{0}@{1} b={2}", r["heroId"], r["zoneId"], r["beliefScore"]) for r in field_recruits),
                "|".join(S(z) for z in marked)))

    claim_value = D(intent["claimValue"]) if (has(intent, "claimValue") and T(intent["claimValue"])) else 400
    if presence_kind or iin(objective_kind, ("seize_lane", "gate_control", "hold_plateau")):
        capture_mode = "clear_hold_shell"
    elif T(ot) and T(g(ot, "captureMode")):
        capture_mode = S(ot["captureMode"])
    elif T(g(intent, "captureMode")):
        capture_mode = S(intent["captureMode"])
    else:
        capture_mode = None
    env_td = S(env["targetDuration"]) if (T(env) and T(g(env, "targetDuration"))) else "10min"
    esc_mode = S(arc["escalation"])
    if ieq(esc_mode, "off"):
        escalation = {"fallbackWaveDefs": fallback_wave_defs, "firstWaveFrame": 999999, "intervalFrames": 999999,
                      "maxWaves": 0, "mode": "off", "frontBand": bool(front_band), "targetDuration": env_td,
                      "hotExtractOnly": True}
    elif ieq(esc_mode, "light"):
        escalation = {"fallbackWaveDefs": fallback_wave_defs, "firstWaveFrame": 3600, "intervalFrames": 2700,
                      "maxWaves": 3, "mode": "light", "frontBand": bool(front_band), "targetDuration": env_td}
    else:
        escalation = {"fallbackWaveDefs": fallback_wave_defs, "firstWaveFrame": 2700, "intervalFrames": 1800,
                      "maxWaves": 8, "mode": "full", "frontBand": bool(front_band), "targetDuration": env_td}
    cadre_xp: Dict[str, Any] = {}
    if T(roster) and has(roster, "cadreXp") and T(roster["cadreXp"]):
        for name, b in props(roster["cadreXp"]):
            if not T(b):
                continue
            cadre_xp[S(name)] = {k: (D(b[k]) if g(b, k) is not None else 0.0)
                                 for k in ("xp", "craftXp", "peakXp", "peakCraftXp", "avgXp", "avgCraftXp")}
    fb = intent["factionBanks"] if (has(intent, "factionBanks") and T(intent["factionBanks"])) else None
    wc_t = intent["worldConflict"] if (has(intent, "worldConflict") and T(intent["worldConflict"])) else None
    home = g(state, "homeCamp") if T(state) else None
    camp_growth = None
    if ieq(map_id, "the_rock_jungle") and T(state) and has(state, "homeCamp") and T(home) \
            and has(home, "growthPending") and I(home["growthPending"]) > 0:
        camp_growth = {"count": I(home["growthPending"])}

    mission_base = {
        "schemaVersion": "verdance-playable/1.0-alpha",
        "campaignId": "verdance_ashes",
        "missionId": mission_id,
        "missionNumber": mission_number,
        "deploymentMapId": g(intent, "mapId"),
        "deploymentZoneId": g(intent, "deploymentZoneId"),
        "extractionZoneId": g(intent, "extractionZoneId"),
        "strikeTeam": strike_doctrine,
        "arcProfile": arc,
        "act": piped(intent["act"]) if (has(intent, "act") and T(intent["act"])) else {"act": act_num, "name": act_name},
        # The waterline this mission inherits from the planet's water cycle. The gadget applies it at
        # start and flood beats move it from there.
        "hydrology": piped(intent["hydrology"]) if (has(intent, "hydrology") and T(intent["hydrology"])) else {"level": 0.0, "amplitude": 0.0},
        "finale": piped(intent["finale"]) if is_finale else None,
        # faction -> zones it truly holds here. Reinforcements enter only on the map edge inside one of
        # their own zones, out of the player's sight (game_verdance_campaign.lua enemyEntry).
        "entryZones": piped(intent["entryZones"]) if (has(intent, "entryZones") and T(intent["entryZones"])) else {},
        # Hot drop (tools/verdance_kernel/hot_drop.py): the company waits off the field until the drop
        # file names them.
        "hotDrop": hot_drop(ws, log),
        # The doors on this map (zoneId, farMapName, held): drawn on the in-game board.
        "doors": arr(intent["doors"]) if (has(intent, "doors") and T(intent["doors"])) else [],
        # The field's set piece, and for a kings' showdown the kings the kings gadget watches.
        "theater": theater,
        "kings": list(f.kings),
        # Bonds worth something on the field (verdance.company.synergy): the gadget applies a row only
        # when both heroes of the pair drop.
        "bondXp": arr(intent["bondXp"]) if (has(intent, "bondXp") and T(intent["bondXp"])) else [],
        "bondGifts": arr(intent["bondGifts"]) if (has(intent, "bondGifts") and T(intent["bondGifts"])) else [],
        "pathSignal": piped(state["pathSignal"]) if (T(state) and T(g(state, "pathSignal"))) else "B",
        "title": title,
        "zone": g(map_entry, "title"),
        "objective": {
            "id": piped(ot["id"]) if (T(ot) and T(g(ot, "id"))) else f"{mission_id}_objective",
            "kind": piped(ot["kind"]) if (T(ot) and T(g(ot, "kind"))) else piped(g(intent, "objective")),
            "requiredFrames": frames,
            "description": description,
            "targetZoneId": target_zone_id,
            # The presence (metal in armed units and defences) a claim needs here (verdance.world.claim).
            "claimValue": claim_value,
            "extractionZoneId": g(intent, "extractionZoneId"),
            "captureZoneIds": list(capture_ids),
            "secondaryCaptureZoneIds": list(secondary_ids),
            # Phase D: capture = clear living-shell pocket + hold under regrow (not empty grass).
            "captureMode": capture_mode,
            "requiredHoldFrames": 900 if presence_kind else None,
            # Fortify / secure foothold: defensive value = the "secured" signal.
            "fortifyDefensiveValue": claim_value if fortify_kind else None,
            # Drop 4: surgical | raze (whole camp tagged) | purge (clear the board).
            "strength": objective_strength,
        },
        # Drop 4: secondary objectives placed this mission (gadget ledger + HUD).
        "secondaries": list(f.secondary_meta),
        "hubChoiceId": hub_choice_id,
        "deployAces": list(hub_deploy_aces),
        "crewBand": list(crew_band),
        # The hero the player is (first company pick): mission-critical in the field.
        "you": S(state["company"]["you"]) if (T(state) and T(g(state, "company")) and has(state["company"], "you")
                                              and T(state["company"]["you"])) else None,
        "fieldRecruits": list(field_recruits),
        "fieldPeople": list(field_people),
        # Safe ground: everything of ours standing in these zones lifts on extract (game_verdance_exfil.lua).
        "safeZoneIds": [S(x) for x in each(intent["safeZoneIds"])] if (has(intent, "safeZoneIds") and T(intent["safeZoneIds"])) else [],
        # The camp grew while the company was away: builders left at base (verdance.campaign.home).
        "campGrowth": camp_growth,
        # Taking a door: once it is ours the extraction moves onto it (game_verdance_exfil.lua).
        "exitDoorZoneId": S(intent["exitDoorZoneId"]) if (has(intent, "exitDoorZoneId") and T(intent["exitDoorZoneId"])) else None,
        "economy": piped(state["economy"]) if (T(state) and T(g(state, "economy"))) else {"metalIncome": 0, "energyIncome": 0, "buildPower": 0},
        "difficulty": {
            "enemyScale": es,
            "difficultyCoefficient": diff_coeff,
            "difficultyDial": R(dial, 3),
            "band": diff_band,
            "hazardLevel": R(max_hazard, 3),
            "fortified": fortify,
            "enemyAI": S(arc["enemyAI"]),
            "label": difficulty_line,
        },
        "progression": {"mode": xp_mode, "xpPersistOnDeath": True},
        "devTelemetry": bool(dev_telemetry),
        "dev": {"telemetry": bool(dev_telemetry), "samplePeriodFrames": int(dev_period), "learnFaster": bool(dev_telemetry)},
        "mapOccupation": list(f.map_occupation),
        "livingShell": f.living_shell if T(f.living_shell) else None,
        "warWrecks": list(f.war_wrecks),
        "scoutParties": list(f.scout_parties),
        "jumpGate": piped(intent["jumpGate"]) if (has(intent, "jumpGate") and T(intent["jumpGate"])) else None,
        "noCommanders": bool(T(theater) and has(theater, "noCommanders") and T(theater["noCommanders"])),
        "occupationModel": "living_shell",
        "sessionMode": S(intent["sessionMode"]) if T(g(intent, "sessionMode")) else "same_map",
        # WO-035: Arc A off (hot extract wave only in the gadget); light/full later.
        "escalation": escalation,
        "heroes": hero_manifest,
        # Per-def veteran XP bank: the gadget seeds SetUnitExperience / craft XP on spawn.
        "cadreXp": cadre_xp,
        "beats": piped(arr(intent["beats"])) if (has(intent, "beats") and T(intent["beats"])) else None,
        "graph": graph,
        "reputation": reputation,
        "companions": companions,
        # Tenebrium banks and the Armada crisis, as Python decided them (intent.factionBanks,
        # intent.worldConflict.armadaTenebriumCrisis); no longer forced here.
        "commerce": piped(commerce) if T(commerce) else {"tenebrium": 0, "credits": 0},
        "tenebrium": {
            "playerBank": I(commerce["tenebrium"]) if (T(commerce) and g(commerce, "tenebrium") is not None) else 0,
            "armadaBank": I(fb["armada"]) if (T(fb) and g(fb, "armada") is not None) else 0,
            "cortexBank": I(fb["cortex"]) if (T(fb) and g(fb, "cortex") is not None) else 2,
            "armadaCrisis": B(wc_t["armadaTenebriumCrisis"]) if (T(wc_t) and g(wc_t, "armadaTenebriumCrisis") is not None) else True,
            # The kings' showdown is a straight game of BAR: the company builds without the Tnb gate.
            "gate": not is_kings,
            "notes": "Build-power units cost >=1 Tnb; wrecks keep Tnb until reclaimed or truly gone.",
        },
        "worldConflict": piped(intent["worldConflict"]) if (has(intent, "worldConflict") and T(intent["worldConflict"])) else {},
        "storyIntent": intent,
    }
    scenario = {
        "schemaVersion": "verdance-playable-scenario/1.0-alpha",
        "sourceIntentPath": intent_path,
        "sourceStatePath": state_path,
        "map": {"id": g(map_entry, "id"), "name": g(map_entry, "mapName"), "sizeX": 0, "sizeZ": 0,
                "descriptor": g(map_entry, "descriptor")},
        "zoneMapPath": zone_map_rel,
        "defaultVariant": "alpha_player",
        "notes": "Generated from Verdance Story Engine v1 mission intent. Human player controls team 0; NPCs use SimpleAI/RaptorsAI.",
        "missionBase": mission_base,
        "baseRecipes": f.base_recipes,
        "layout": {"allyTeams": f.ally_teams, "teams": f.teams, "alliances": f.alliances},
        "forces": f.forces,
        "variants": [{
            "id": "alpha_player",
            "label": "Alpha Campaign Player",
            "playerTeamID": 0,
            # The kings start on their seats (StartPosType 3 reads StartPosX/Z). With 1, BAR put each king
            # on one of the map's own start points in random order.
            "startPosType": 3 if is_kings else 1,
            # The showdown's raptor den harries every king without deciding the throne: at normal pace its
            # T4 broods took the company's commander at 35 minutes (Luke's PC, 2026-11-03).
            "raptorDifficulty": "veryeasy" if is_kings else "normal",
            "raptorQueenTimeMult": "1.5" if is_kings else "1",
            "playerSide": "Legion",
            "playerStartLabel": "Legion Green Player",
            "notes": "Human-controlled alpha campaign sortie generated from next_mission_intent.json.",
            "ai": f.ai,
        }],
    }
    # install_playable_slice needs explicit dimensions for start positions.
    authored_path = ws / "data" / "scenarios" / "authored" / f"{map_id}.authored_baseline.json"
    if authored_path.exists():
        authored = shell_mod.read_json(authored_path)
        if T(g(authored, "map")):
            scenario["map"]["sizeX"] = I(authored["map"].get("sizeX"))
            scenario["map"]["sizeZ"] = I(authored["map"].get("sizeZ"))
    if not T(scenario["map"]["sizeX"]) or not T(scenario["map"]["sizeZ"]):
        raise ValueError(f"Could not determine map dimensions for {map_id}.")

    scenario_path = ws / SCENARIO_REL
    if not save_name:
        save_name = "verdance_" + re.sub(r"[^A-Za-z0-9_-]", "_", mission_id) + "_alpha"

    # The installer's named arguments (a hashtable splat in the PS1, so they bind by name).
    installer_args: Dict[str, Any] = {
        "Workspace": str(ws),
        "ScenarioPath": str(scenario_path),
        "Variant": "alpha_player",
        "PlayerController": "human",
        "TimeoutSeconds": int(timeout_seconds),
    }
    extra_mods: List[str] = []
    if extra_mod_options:
        extra_mods.append(extra_mod_options)
    # Visit tier (verdance.world.visit_tiers): raptor grace and how far into its clock the hive starts.
    tier_raptor = visit_tier["raptor"] if (T(visit_tier) and has(visit_tier, "raptor")) else None
    if T(tier_raptor):
        extra_mods.append(fmt("va_raptor_grace_seconds={0}", I(g(tier_raptor, "graceSeconds"))))
        extra_mods.append(fmt("va_raptor_clock_seconds={0}", I(g(tier_raptor, "clockSeconds"))))
        log(fmt("Raptor pace (visit tier {0}): grace {1}s, clock +{2}s", g(visit_tier, "tier"),
                g(tier_raptor, "graceSeconds"), g(tier_raptor, "clockSeconds")))
    elif is_wild_home or (is_rock_jungle and ieq(against, "wild")):
        # PS FAULT, KEPT: `$extraMods -notmatch "..."` on an array filters it, so with no
        # -ExtraModOptions the filter is empty and false, and the ~5 min Rock Jungle grace was never
        # added. It is added only when the caller passed some other modoption. The kernel never passes
        # one, so on the PC the wild home kept the installer's default grace.
        if any(not re.search("raptor_graceperiodmult=", m, re.IGNORECASE) for m in extra_mods):
            extra_mods.append("raptor_graceperiodmult=0.85")
            log("Raptor grace: mult=0.85 (~5 min) for Rock Jungle wild home.")
    if len(extra_mods) > 0:
        installer_args["ExtraModOptions"] = ";".join(extra_mods)
    if launch:
        installer_args["Launch"] = True
    if save_game:
        installer_args["SaveGame"] = True
        installer_args["SaveName"] = save_name

    config = verdance_config(ws)
    if launch:
        next_step = "BAR launch requested."
    elif save_game:
        next_step = "Load the generated save from BAR Saves."
    else:
        next_step = "Launch BAR with playable_runs latest startscript, or use PLAY_NEXT_MISSION_V1.bat."
    manifest = {
        "ok": True,
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "intentPath": intent_path,
        "statePath": state_path,
        "scenarioPath": str(scenario_path),
        "missionId": mission_id,
        "missionNumber": mission_number,
        "mapId": g(intent, "mapId"),
        "mapName": g(map_entry, "mapName"),
        "deploymentZoneId": g(intent, "deploymentZoneId"),
        "objectiveTarget": g(intent, "objectiveTarget"),
        "act": act_num,
        "actName": act_name,
        "finaleKind": finale_kind if is_finale else None,
        "enemySide": side,
        "nullMercs": {"present": bool(mercs_present), "allied": bool(mercs_allied), "reputation": merc_rep},
        "hasWild": bool(has_wild),
        "saveName": save_name if save_game else None,
        "seedOutbox": config["seedOutbox"],
        "seedDestination": config["seedDestination"],
        "nextStep": next_step,
        # Python only: whether install_playable_slice.ps1 ran (no PowerShell host, no install).
        "installed": False,
    }
    res.scenario = scenario
    res.manifest = manifest
    res.installer_args = installer_args
    res.scenario_path = scenario_path
    res.manifest_path = ws / MANIFEST_REL
    res.mission_id = mission_id
    res.map_name = S(g(map_entry, "mapName"))
    return res


def _standing_pocket_zones(ws: Path, state: Any, map_id: str) -> Optional[CIDict]:
    """Get-StandingPocketZones: the zones where a template pocket still stands. No template: cannot
    judge, leave the job alone (null)."""
    path = shell_mod.template_path(ws, map_id)
    if path is None:
        return None
    tpl = shell_mod.read_json(path)
    scarred = shell_mod.scarred_zone_set(state, map_id)
    dead = shell_mod.destroyed_high_value_pockets(state, map_id)
    zones = CIDict()
    for pk in arr(g(tpl, "pockets")):
        zid = S(g(pk, "zoneId"))
        if zid and zid not in scarred and S(g(pk, "pocketId")) not in dead:
            zones[zid] = True
    return zones


def build_scenario(workspace: Path, intent: Dict[str, Any], state: Any, *, intent_path: Optional[str] = None,
                   state_path: Optional[str] = None, launch: bool = False, save_game: bool = False,
                   save_name: str = "", timeout_seconds: int = 300, extra_mod_options: str = "",
                   log: Log = print) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The scenario and the build manifest for this intent and state. Writes nothing."""
    ws = Path(workspace)
    ip = intent_path if intent_path is not None else str(ws / "outbox" / "next_mission_intent.json")
    sp = state_path if state_path is not None else str(ws / "state" / "campaign_state.json")
    res = _build(ws, intent, state, intent_path=ip, state_path=sp, launch=launch, save_game=save_game,
                 save_name=save_name, timeout_seconds=timeout_seconds, extra_mod_options=extra_mod_options, log=log)
    return res.scenario, res.manifest


# --- Writing and installing ---------------------------------------------------------------------

def save_json(obj: Any, path: Path) -> None:
    """Save-Json: UTF-8 with a BOM, as Set-Content -Encoding UTF8 wrote it on Windows PowerShell 5.1
    (every reader opens it as utf-8-sig or through ConvertFrom-Json)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8-sig")


def powershell_host() -> Optional[str]:
    """The host that runs install_playable_slice.ps1. On Windows, ``powershell`` first: it is what the
    kernel ran the whole build under (verdance_kernel.runtime.run_ps1), so the installer keeps the
    Windows PowerShell 5.1 it was written against; ``pwsh`` otherwise."""
    names = ("powershell", "pwsh") if os.name == "nt" else ("pwsh", "powershell")
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if Path("/opt/pwsh/pwsh").exists():
        return "/opt/pwsh/pwsh"
    return None


def installer_command(host: str, installer: Path, args: Dict[str, Any]) -> List[str]:
    cmd = [host, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer)]
    for k, v in args.items():
        if v is True:
            cmd.append(f"-{k}")
        else:
            cmd += [f"-{k}", str(v)]
    return cmd


def run(workspace: Path, *, intent_path: str = "", state_path: str = "", launch: bool = False,
        save_game: bool = False, save_name: str = "", timeout_seconds: int = 300, extra_mod_options: str = "",
        install: bool = True, log: Log = print) -> Dict[str, Any]:
    """Build, write the scenario, run the installer when a PowerShell host exists, write the manifest."""
    ws = Path(workspace).resolve()
    ip = Path(intent_path) if intent_path else ws / "outbox" / "next_mission_intent.json"
    sp = Path(state_path) if state_path else ws / "state" / "campaign_state.json"
    if not ip.exists():
        raise FileNotFoundError(f"No next mission intent at {ip}. Drop from the hub (PLAY.bat), or run "
                                "scripts\\advance_campaign_v1.ps1 first.")
    intent = shell_mod.read_json(ip)
    state = shell_mod.read_json(sp) if sp.exists() else None
    res = _build(ws, intent, state, intent_path=str(ip), state_path=str(sp), launch=launch, save_game=save_game,
                 save_name=save_name, timeout_seconds=timeout_seconds, extra_mod_options=extra_mod_options, log=log)
    save_json(res.scenario, res.scenario_path)
    installer = ws / "scripts" / "install_playable_slice.ps1"
    host = powershell_host() if install else None
    if host is None:
        log("Install skipped: no PowerShell host (powershell / pwsh) to run install_playable_slice.ps1." if install
            else "Install skipped: --no-install.")
    else:
        sys.stdout.flush()
        r = subprocess.run(installer_command(host, installer, res.installer_args), cwd=str(ws))
        if r.returncode != 0:
            raise RuntimeError(f"install_playable_slice.ps1 failed (exit {r.returncode})")
        res.manifest["installed"] = True
    save_json(res.manifest, res.manifest_path)
    log("Built Verdance alpha mission from v1 intent.")
    log(f"Mission: {res.mission_id} on {res.map_name}")
    log(f"Scenario: {res.scenario_path}")
    log(f"Manifest: {res.manifest_path}")
    return res.manifest


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m verdance.mission_builder",
                                 description="Build the next mission's playable scenario (port of build_next_mission_v1.ps1).")
    ap.add_argument("--workspace", default=os.environ.get("VERDANCE_WORKSPACE") or str(Path(__file__).resolve().parents[3]))
    ap.add_argument("--intent", default="", help="mission intent (default outbox/next_mission_intent.json)")
    ap.add_argument("--state", default="", help="campaign state (default state/campaign_state.json)")
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--save-game", action="store_true")
    ap.add_argument("--save-name", default="")
    ap.add_argument("--timeout-seconds", type=int, default=300)
    ap.add_argument("--extra-mod-options", default="",
                    help="passed straight through to install_playable_slice.ps1's [MODOPTIONS]; semicolon-separated key=value")
    ap.add_argument("--no-install", action="store_true", help="write the scenario and manifest only")
    a = ap.parse_args(argv)
    try:
        manifest = run(Path(a.workspace), intent_path=a.intent, state_path=a.state, launch=a.launch,
                       save_game=a.save_game, save_name=a.save_name, timeout_seconds=a.timeout_seconds,
                       extra_mod_options=a.extra_mod_options, install=not a.no_install,
                       log=lambda s: print(s, flush=True))
    except Exception as e:  # noqa: BLE001
        print(f"Mission build failed: {e}", file=sys.stderr, flush=True)
        return 1
    print(json.dumps({"ok": True, "installed": bool(manifest.get("installed")), "missionId": manifest.get("missionId"),
                      "scenarioPath": manifest.get("scenarioPath")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
