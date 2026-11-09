"""Standing set pieces: what a field is like whenever the company drops onto it.

    the_rock_jungle   wild ground end to end: a den on every zone the wild holds; the hive in the
                      south-west corner
    eye_of_horus      the crater's outer rim is raptor ground (dens along the edge); Cortex keeps the eye
    koom_valley, tabula, ancient_bastion, eye_of_horus (Greenest Fields' war retired 2026-10-25)
                      standing wars: BARbarians fight on the map, one side stacked each way (Koom
                      east/west, Greenest Fields north/south, Tabula east/west, the Bastion a
                      siege, the Eye Cortex south against Armada north), some minutes into a full
                      game (tools/war_bake_v1.py plays each once and saves the field); the company
                      takes the seat the war left empty
    all_that_simmers  the kings' showdown, a classic game of BAR: Armada, Cortex, Null Mercs and the
                      company each start with one commander and nothing else; last commander standing
                      takes the throne. The company's king is its commander suit
                      (verdance.campaign.suits); in Cortex's own suit, Cortex does not come

The engine puts what this returns on the mission intent (``theater``, ``wildDens``); the mission
builder only places it. Positions are normalized map coordinates (x east, z south).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.world import war_snapshot as _war

# The Rock Jungle's hive (owner call, 2026-10-23): no den there; the hive camp stands in it.
JUNGLE_HIVE_ZONE = "TRJ_SW_LANE"

# Eye of Horus's rim, seat by seat: points on the ridges around the crater, each in the zone that
# holds it. The two door corners (NW, SE) are left to whoever comes through them.
EYE_RIM_SEATS = [
    ("EOH_NE_CAUSEWAY", 0.50, 0.06), ("EOH_NE_CAUSEWAY", 0.92, 0.08), ("EOH_NE_CAUSEWAY", 0.95, 0.32),
    ("EOH_E_LANE", 0.95, 0.55), ("EOH_W_LANE", 0.05, 0.36), ("EOH_SW_CAUSEWAY", 0.05, 0.62),
    ("EOH_SW_CAUSEWAY", 0.08, 0.92), ("EOH_SW_CAUSEWAY", 0.50, 0.95),
]
EYE_RIM_ZONES = sorted({z for z, _, _ in EYE_RIM_SEATS})
EYE_RIM_DENS = False  # the rim's dens are off: Armada's glassing burned the spread out

# The standing wars (data/base_templates/<map>/war_recipe.json, baked by tools/war_bake_v1.py): every
# seat but the company's, with the side that holds it and the zone it stands in. The company's seat
# is the recipe's ``playerSeat``: BARbarian held it for the sim and the baked field leaves it empty.
# tests/test_theaters.py keeps this table and the recipes in step.
WARS = {
    "koom_valley": [
        {"key": "w", "faction": "nullmercs", "zoneId": "KV_NW_SPILLWAY"},
        {"key": "sw", "faction": "nullmercs", "zoneId": "KV_SW_MUSTER"},
        {"key": "ne", "faction": "armada", "zoneId": "KV_NE_MUSTER"},
        {"key": "e", "faction": "armada", "zoneId": "KV_NE_SPILLWAY"},
        {"key": "se", "faction": "armada", "zoneId": "KV_SE_MUSTER"},
        {"key": "fort_e", "faction": "armada", "zoneId": "KV_E_LOWER_LANE"},  # tier 3's fort (va_warden)
    ],
    # greenest_fields: retired 2026-10-25 (Luke): the old field, the living shell's many bases to
    # clear and harvest, is back. Its war is kept in data/base_templates/greenest_fields/retired_war/.
    "tabula": [
        {"key": "w", "faction": "nullmercs", "zoneId": "T_NW_OUTER_RESERVE"},
        {"key": "wm", "faction": "nullmercs", "zoneId": "T_W_CAUSEWAY"},
        {"key": "sw", "faction": "nullmercs", "zoneId": "T_SW_CAUSEWAY"},
        {"key": "ne", "faction": "armada", "zoneId": "T_NE_CAUSEWAY"},
        {"key": "e", "faction": "armada", "zoneId": "T_SE_OUTER_RESERVE"},
        {"key": "em", "faction": "armada", "zoneId": "T_E_CAUSEWAY"},
        {"key": "se", "faction": "armada", "zoneId": "T_SE_RESERVE"},
        # tier 2 and 3's forts (va_warden): the keep and the south high terrace's main line
        {"key": "fort_keep", "faction": "armada", "zoneId": "T_SE_MUSTER"},
        {"key": "fort_s", "faction": "armada", "zoneId": "T_SE_LANE"},
    ],
    # the Overthrow's soak (2026-11-09): the Keep alone, ten works; no besiegers
    "ancient_bastion": [
        {"key": "keep_s", "faction": "armada", "zoneId": "AB_SW_RAMPART"},
        {"key": "keep_n", "faction": "armada", "zoneId": "AB_W_KEEP"},
        {"key": "keep", "faction": "armada", "zoneId": "AB_W_KEEP"},
        {"key": "out_n", "faction": "armada", "zoneId": "AB_NW_RAMPART"},
        {"key": "out_s", "faction": "armada", "zoneId": "AB_SW_RAMPART"},
        {"key": "gate", "faction": "armada", "zoneId": "AB_W_GATEHOUSES"},
        {"key": "rampart_n", "faction": "armada", "zoneId": "AB_NW_RAMPART"},
        {"key": "rampart_s", "faction": "armada", "zoneId": "AB_SW_RAMPART"},
        {"key": "tor_n", "faction": "armada", "zoneId": "AB_NW_TOR"},
        {"key": "tor_s", "faction": "armada", "zoneId": "AB_SW_TOR"},
    ],
    # The Eye (2026-10-26): only the Cortex mercenary camp in the glassed crater stands; Armada's assault
    # from the corners was the bake's history and is gone but for its wrecks.
    "eye_of_horus": [
        {"key": "c_n", "faction": "cortex", "zoneId": "EOH_C_GATE"},
        {"key": "c_ne", "faction": "cortex", "zoneId": "EOH_C_LANE"},
        {"key": "c_sw", "faction": "cortex", "zoneId": "EOH_C_INNER_LANE"},
        {"key": "c_s", "faction": "cortex", "zoneId": "EOH_C_INNER_GATE"},
    ],
}
KOOM_WAR = WARS["koom_valley"]

# Who plays a war's seats while the company is on the field: the bake ran its own profiles (the
# snapshot's), the live field may not. Koom (owner call, 2026-10-29): BARbarian on medium for every
# seat, the Null Mercs' Legion as well as Armada. A fort's builder (va_warden) stays a fort builder.
LIVE_PROFILES = {"koom_valley": "medium"}
KEEP_PROFILES = {"va_warden"}

# Who truly holds ground because a set piece stands there (the campaign's zone memory seeds it):
# the seats each war holds.
# The Eye's rim stays the raptors' whoever stands on it: its seats are the war's, its ground is wild.
# A tier's added fort (key fort_*) is not standing at the opening, so it holds nothing yet.
STANDING_CONTROL = {m: {s["zoneId"]: s["faction"] for s in seats
                        if not (m == "eye_of_horus" and s["zoneId"] in EYE_RIM_ZONES) and not s["key"].startswith("fort")}
                    for m, seats in WARS.items()}

# All That Simmers' four corners, clockwise from the north-west. The showdown (owner call, 2026-11-03):
# the company in its corner (the finale lands it in the north-west), Armada in the next corner
# clockwise (north-east), Cortex across the map (south-east), and a raptor den in the last corner
# (south-west). Three kings and the wild; every corner occupied.
SIMMERS_SEATS = ["ATS_NW_SHORE", "ATS_NE_MUSTER", "ATS_SE_SHORE", "ATS_SW_MUSTER"]
SIMMERS_THRONE = "ATS_C_BASTION"
SIMMERS_RIVALS = ("armada", "cortex")

# A den or a camp never stands this close to the company's pad.
PAD_CLEARANCE = 0.22


def _zones(map_id: str, workspace: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if workspace is None:
        return {}
    p = Path(workspace) / "data" / "zone_maps" / "authored" / f"{map_id}.authored.zone_map.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}
    return {str(z.get("zoneId")): z for z in data.get("zones") or [] if z.get("zoneId")}


def _point(zone: Dict[str, Any]) -> Optional[tuple]:
    a = zone.get("anchor") or {}
    if a.get("x") is not None and a.get("z") is not None:
        return float(a["x"]), float(a["z"])
    b = zone.get("bounds") or {}
    if not b:
        return None
    return (float(b.get("xMin", 0)) + float(b.get("xMax", 1))) / 2, (float(b.get("zMin", 0)) + float(b.get("zMax", 1))) / 2


def _seat(zones: Dict[str, Dict[str, Any]], zone_id: str, **extra: Any) -> Optional[Dict[str, Any]]:
    z = zones.get(zone_id)
    p = _point(z) if z else None
    if not p:
        return None
    return {"zoneId": zone_id, "label": z.get("label") or zone_id, "x": round(p[0], 4), "z": round(p[1], 4), **extra}


def _wild(state: Dict[str, Any], map_id: str) -> set:
    out = set()
    for zid, zm in ((state.get("zoneMemory") or {}).get(map_id) or {}).items():
        if isinstance(zm, dict) and str(zm.get("controllingFaction") or (zm.get("abstract") or {}).get("control") or "").lower() == "wild":
            out.add(str(zid))
    return out


def wild_dens(state: Dict[str, Any], map_id: str, workspace: Optional[Path], pad_zone: Optional[str]) -> List[Dict[str, Any]]:
    """Where the wild has dens this sortie: one per zone the wild truly holds (the Eye: one per rim
    seat the wild holds), none on the hive and none near the pad."""
    zones = _zones(map_id, workspace)
    wild = _wild(state, map_id)
    pad = _point(zones.get(str(pad_zone), {})) if pad_zone else None
    if map_id == "eye_of_horus":
        # The glassing worked (owner call, 2026-10-26): no raptor ground left on the Eye. EYE_RIM_SEATS
        # stay as data, should a remnant ever come back.
        seats = [{"zoneId": z, "label": (zones.get(z) or {}).get("label") or z, "x": x, "z": zz}
                 for z, x, zz in EYE_RIM_SEATS if z in wild and EYE_RIM_DENS]
    else:
        seats = [s for s in (_seat(zones, z) for z in sorted(wild) if z != JUNGLE_HIVE_ZONE) if s]
    if pad:
        seats = [s for s in seats if math.hypot(s["x"] - pad[0], s["z"] - pad[1]) >= PAD_CLEARANCE]
    return seats


def standing_war(map_id: str, workspace: Optional[Path], pad_zone: Optional[str] = None,
                 tier: int = 1) -> Optional[Dict[str, Any]]:
    """A map's war: each seat's side, profile, bank and the units the baked field has standing on it,
    less any that stand where the company lands. A map whose war has not been baked yet is an
    ordinary field (its living shell), not an empty war. ``tier`` is the visit tier
    (verdance.world.visit_tiers): a later visit meets the war baked harder, when that bake exists."""
    seats = WARS.get(map_id)
    snap = _war.load_snapshot(workspace, map_id, tier) if workspace is not None and seats else None
    if not snap:
        return None
    zones = _zones(map_id, workspace)
    baked = {t["key"]: t for t in snap.get("teams") or []}
    pad = _point(zones.get(str(pad_zone), {})) if pad_zone else None
    camps = []
    for c in seats:
        seat = _seat(zones, c["zoneId"], faction=c["faction"], key=c["key"])
        if not seat:
            return None
        field = baked.get(c["key"])
        if not field:
            if c["key"].startswith("fort"):
                continue  # a tier's added fort: not in this tier's war
            return None
        live = LIVE_PROFILES.get(map_id)
        profile = live if live and field["profile"] not in KEEP_PROFILES else field["profile"]
        seat.update(x=field["seat"][0], z=field["seat"][1], profile=profile, bank=field["bank"])
        # the start commander is the engine's; every baked unit but a commander is placed
        seat["units"] = [u for u in field["units"]
                         if u[5] != "C" and not (pad and math.hypot(u[1] - pad[0], u[2] - pad[1]) < PAD_CLEARANCE)]
        camps.append(seat)
    out = {"kind": "standing_war", "label": SET_PIECES[map_id]["label"], "minutes": snap.get("minutes"), "camps": camps,
           "tier": int(snap.get("tier") or 1)}
    # the war's dead lie where they fell (metal to reclaim, hulls to raise), none where the company lands
    out["wrecks"] = [w for w in snap.get("wrecks") or []
                     if not (pad and math.hypot(w[1] - pad[0], w[2] - pad[1]) < PAD_CLEARANCE)]
    # A young war on a big field (Greenest Fields) keeps the map's living shell too: the shell's
    # little commander-grown works stand beside the war, allied to the war's seats of their faction.
    recipe = _war.load_recipe(workspace, map_id) if workspace is not None else None
    if recipe and recipe.get("keepShell"):
        out["keepShell"] = True
    # Tabula (owner call, 2026-10-26): no commanders on the field but the company's own.
    if recipe and recipe.get("noCommanders"):
        out["noCommanders"] = True
    # The Overthrow's soak (owner call, 2026-11-09): one commander, the one nearest this zone, and
    # every other start commander but the company's goes (game_verdance_suits.lua).
    spare = recipe.get("keepOneCommander") if recipe else None
    if spare and _point(zones.get(spare, {})):
        out["noCommanders"] = True
        sx, sz = _point(zones[spare])
        out["commanderSpare"] = {"zoneId": spare, "x": round(sx, 4), "z": round(sz, 4)}
    return out


def kings_showdown(map_id: str, workspace: Optional[Path], pad_zone: Optional[str],
                   state: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The kings' showdown on All That Simmers: the company in the corner nearest its pad, Armada in
    the next corner clockwise, Cortex across the map, a raptor den in the last corner. In Cortex's own
    suit Cortex stays home and its corner stands empty."""
    if map_id != "all_that_simmers":
        return None
    from verdance.campaign import suits as _suits
    worn = _suits.suit(state) if state is not None else None
    zones = _zones(map_id, workspace)
    seats = [_seat(zones, z) for z in SIMMERS_SEATS]
    pad = _point(zones.get(str(pad_zone), {})) if pad_zone else None
    if not pad or not all(seats):
        return None
    home = min(range(4), key=lambda i: math.hypot(seats[i]["x"] - pad[0], seats[i]["z"] - pad[1]))
    corner = lambda k: seats[(home + k) % 4]  # noqa: E731
    cortex_out = bool(worn and worn["unitDef"] == "corcom")
    kings = [dict(corner(1), faction="armada")]
    if not cortex_out:
        kings.append(dict(corner(2), faction="cortex"))
    den = dict(corner(3), label=corner(3)["label"] + " den")
    throne = _seat(zones, SIMMERS_THRONE)
    company: Dict[str, Any] = {"zoneId": pad_zone}
    if worn:
        company.update(unitDef=worn["unitDef"], side=worn["side"])
    out = {"kind": "kings_showdown",
           "label": "The kings' showdown: one commander each, last one standing; raptors in the fourth corner",
           "throne": throne, "kings": kings, "raptorDen": den, "company": company}
    if cortex_out:
        out["cortexSitsOut"] = True
    return out


# What the hub says about each field's set piece (the board's subtitle, the Drop dialog).
SET_PIECES = {
    "koom_valley": {"kind": "standing_war", "label": "Standing war: Null Mercs hold the west, Armada the east, twenty minutes in; you take the north-west seat"},
    "tabula": {"kind": "standing_war", "label": "Standing war: Null Mercs hold the west terraces, Armada the east, twenty minutes in; you take the north-west seat"},
    "ancient_bastion": {"kind": "standing_war", "label": "Standing war: Armada hold the western castle, Null Mercs besiege it from the east; you take the north-east seat"},
    "eye_of_horus": {"kind": "standing_war", "label": "The glassed crater: a Cortex mercenary camp dug into the crater Armada once glassed; the corners are littered with Armada's old assault"},
    "all_that_simmers": {"kind": "kings_showdown", "label": "Kings' showdown: the company, Armada and Cortex, one commander each, and a raptor den in the fourth corner; last one standing takes the throne. No duel without a commander suit"},
    "the_rock_jungle": {"kind": "wild_ground", "label": "Wild ground: raptors wander every zone; the hive is in the south-west"},
}


def still_water(hydrology: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The kings' showdown's waterline: the map's own, all match long (no sink, no tide)."""
    out = dict(hydrology or {})
    out.update(level=0.0, nextLevel=0.0, amplitude=0.0, elevation=0.0, terraformDelta=0.0,
               areaSubmerged=0.0, metalSpotsSubmerged=0.0, still=True)
    return out


def solo_command(intent: Dict[str, Any]) -> Dict[str, Any]:
    """The kings' showdown: the company's commander walks out alone. No packs, no heroes, no
    reserve; the field's start commander is the company's king, and the job is the throne."""
    theater = intent.get("theater") or {}
    throne = (theater.get("throne") or {}).get("zoneId") or SIMMERS_THRONE
    objective = dict(intent.get("objectiveTarget") or {})
    objective.update(kind="kings_showdown", targetZoneId=throne,
                     label="The kings' showdown: one commander each, last one standing takes the throne")
    intent.update(objective="kings_showdown", objectiveTarget=objective, targetZoneId=throne,
                  captureZoneIds=[throne])
    intent["soloCommand"] = True
    intent["deployAces"] = []
    intent["crewBand"] = []
    roster = intent.get("roster")
    if isinstance(roster, dict):
        roster["heroes"] = []
        roster["cadre"] = {}
    return intent


def is_solo(intent: Optional[Dict[str, Any]]) -> bool:
    return bool(isinstance(intent, dict) and intent.get("soloCommand"))


def theater_for(state: Dict[str, Any], map_id: str, workspace: Optional[Path], pad_zone: Optional[str],
                tier: int = 1) -> Optional[Dict[str, Any]]:
    """The set piece this field stages, or None for an ordinary field."""
    return standing_war(map_id, workspace, pad_zone, tier) or kings_showdown(map_id, workspace, pad_zone, state)


__all__ = [
    "EYE_RIM_SEATS", "EYE_RIM_ZONES", "JUNGLE_HIVE_ZONE", "KOOM_WAR", "WARS", "SET_PIECES", "SIMMERS_SEATS", "SIMMERS_THRONE",
    "STANDING_CONTROL",
    "is_solo", "kings_showdown", "solo_command", "standing_war", "theater_for", "wild_dens",
]
