"""Standing set pieces: what a field is like whenever the company drops onto it.

    the_rock_jungle   wild ground end to end: a den on every zone the wild holds; the hive in the
                      south-west corner
    eye_of_horus      the crater's outer rim is raptor ground (dens along the edge); Cortex keeps the eye
    koom_valley       a standing war: three Null Mercs on the west, three Armada on the east,
                      twenty minutes into a full game (tools/koom_war_bake_v1.py plays it once and
                      saves the field); the company takes the north-west seat the war left empty
    all_that_simmers  the kings' showdown, a classic game of BAR: Armada, Null Mercs and the company
                      each start with one commander and nothing else; last commander standing takes
                      the throne

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

# Koom Valley's standing war (data/base_templates/koom_valley/war_recipe_3v3.json): three Null Mercs
# on the west, three Armada on the east, the far side by the Bastion. The Mercs' north-west seat is
# the company's: BARbarian held it for the sim and the baked field leaves it empty.
KOOM_WAR = [
    {"key": "w", "faction": "nullmercs", "zoneId": "KV_NW_SPILLWAY"},
    {"key": "sw", "faction": "nullmercs", "zoneId": "KV_SW_MUSTER"},
    {"key": "ne", "faction": "armada", "zoneId": "KV_NE_MUSTER"},
    {"key": "e", "faction": "armada", "zoneId": "KV_NE_SPILLWAY"},
    {"key": "se", "faction": "armada", "zoneId": "KV_SE_MUSTER"},
]

# Who truly holds ground because a set piece stands there (the campaign's zone memory seeds it):
# the seats Koom's war holds.
STANDING_CONTROL = {
    "koom_valley": {c["zoneId"]: c["faction"] for c in KOOM_WAR},
}

# All That Simmers' seats: the corners a king can start from. The company's seat is its pad; the
# two rivals take the seats that make the widest triangle with it.
SIMMERS_SEATS = ["ATS_NE_MUSTER", "ATS_SE_SHORE", "ATS_SW_MUSTER", "ATS_NW_SHORE"]
SIMMERS_THRONE = "ATS_C_BASTION"
SIMMERS_RIVALS = ("armada", "nullmercs")

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
        seats = [{"zoneId": z, "label": (zones.get(z) or {}).get("label") or z, "x": x, "z": zz}
                 for z, x, zz in EYE_RIM_SEATS if z in wild]
    else:
        seats = [s for s in (_seat(zones, z) for z in sorted(wild) if z != JUNGLE_HIVE_ZONE) if s]
    if pad:
        seats = [s for s in seats if math.hypot(s["x"] - pad[0], s["z"] - pad[1]) >= PAD_CLEARANCE]
    return seats


def standing_war(map_id: str, workspace: Optional[Path], pad_zone: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Koom's war: each seat's side, profile, bank and (from the baked field) the units standing on it,
    less any that stand where the company lands. Without a baked field the seats come bare and the
    builder gives them a stock base."""
    if map_id != "koom_valley":
        return None
    zones = _zones(map_id, workspace)
    snap = _war.load_snapshot(workspace) if workspace is not None else None
    baked = {t["key"]: t for t in (snap or {}).get("teams") or []}
    pad = _point(zones.get(str(pad_zone), {})) if pad_zone else None
    camps = []
    for c in KOOM_WAR:
        seat = _seat(zones, c["zoneId"], faction=c["faction"], key=c["key"])
        if not seat:
            return None
        field = baked.get(c["key"])
        if field:
            seat.update(x=field["seat"][0], z=field["seat"][1], profile=field["profile"], bank=field["bank"])
            # the start commander is the engine's; every baked unit but a commander is placed
            seat["units"] = [u for u in field["units"]
                             if u[5] != "C" and not (pad and math.hypot(u[1] - pad[0], u[2] - pad[1]) < PAD_CLEARANCE)]
        else:
            seat["profile"] = "hard"
        seat["front"] = {"zoneId": seat["zoneId"], "x": seat["x"], "z": seat["z"]}
        camps.append(seat)
    return {"kind": "standing_war", "label": "Null Mercs and Armada, a full war in progress",
            "baked": bool(baked), "minutes": (snap or {}).get("minutes"), "camps": camps}


def kings_showdown(map_id: str, workspace: Optional[Path], pad_zone: Optional[str]) -> Optional[Dict[str, Any]]:
    if map_id != "all_that_simmers":
        return None
    zones = _zones(map_id, workspace)
    seats = [s for s in (_seat(zones, z) for z in SIMMERS_SEATS) if s]
    pad = _point(zones.get(str(pad_zone), {})) if pad_zone else None
    if not pad or len(seats) < 3:
        return None
    open_seats = [s for s in seats if math.hypot(s["x"] - pad[0], s["z"] - pad[1]) >= PAD_CLEARANCE]

    def spread(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        d = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])  # noqa: E731
        pa, pb = (a["x"], a["z"]), (b["x"], b["z"])
        return min(d(pad, pa), d(pad, pb), d(pa, pb))

    pairs = [(a, b) for i, a in enumerate(open_seats) for b in open_seats[i + 1:]]
    if not pairs:
        return None
    a, b = max(pairs, key=lambda ab: (round(spread(*ab), 4), ab[0]["zoneId"], ab[1]["zoneId"]))
    kings = [dict(a, faction=SIMMERS_RIVALS[0]), dict(b, faction=SIMMERS_RIVALS[1])]
    throne = _seat(zones, SIMMERS_THRONE)
    return {"kind": "kings_showdown", "label": "The kings' showdown: one commander each, last one standing",
            "throne": throne, "kings": kings, "company": {"zoneId": pad_zone}}


# What the hub says about each field's set piece (the board's subtitle, the Drop dialog).
SET_PIECES = {
    "koom_valley": {"kind": "standing_war", "label": "Standing war: Null Mercs hold the west, Armada the east, twenty minutes in; you take the north-west seat"},
    "all_that_simmers": {"kind": "kings_showdown", "label": "Kings' showdown: one commander each, last one standing takes the throne"},
    "eye_of_horus": {"kind": "wild_rim", "label": "Raptors hold the crater's outer rim; Cortex keeps the eye"},
    "the_rock_jungle": {"kind": "wild_ground", "label": "Wild ground: raptors wander every zone; the hive is in the south-west"},
}


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


def theater_for(state: Dict[str, Any], map_id: str, workspace: Optional[Path], pad_zone: Optional[str]) -> Optional[Dict[str, Any]]:
    """The set piece this field stages, or None for an ordinary field."""
    return standing_war(map_id, workspace, pad_zone) or kings_showdown(map_id, workspace, pad_zone)


__all__ = [
    "EYE_RIM_SEATS", "EYE_RIM_ZONES", "JUNGLE_HIVE_ZONE", "KOOM_WAR", "SET_PIECES", "SIMMERS_SEATS", "SIMMERS_THRONE",
    "STANDING_CONTROL",
    "is_solo", "kings_showdown", "solo_command", "standing_war", "theater_for", "wild_dens",
]
