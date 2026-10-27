"""The war snapshots: a real BARbarian war on a map, frozen some minutes in.

Koom Valley, Greenest Fields, Tabula, the Ancient Bastion and the Eye of Horus are standing wars
(``verdance.world.theaters``). Rather than fake one with a few recipes, each war is played once by
BARb on its map (``tools/war_bake_v1.py``) and the field is saved as it stands: every unit, who owned
it and how hurt it was, and what each side's bank held. Every drop onto that map then starts from that
war. The company's own seat is played by BARb too, so the war has the shape of a full game, and is
then pulled out: its units are not in the snapshot.

The seats (``data/base_templates/<map>/war_recipe.json``) are the map's own start positions, or, where
the map has none on a side the war needs, ground chosen to match (``"virtual": true``). This module
only reads and writes facts: the recipe becomes a startscript, the engine's dump becomes a snapshot,
and the snapshot is what the mission builder and the theater read.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

MAP_ID = "koom_valley"
SCHEMA = "verdance-war-snapshot/1.0"
DEFAULT_MAP_SIZE = (12288.0, 8192.0)
MOBILE_KINDS = ("M", "A", "W")
WRECK_SEAT_CLEARANCE = 0.08  # no war dead on the company's own seat


def _json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def recipe_rel(map_id: str) -> str:
    return f"data/base_templates/{map_id}/war_recipe.json"


def snapshot_rel(map_id: str, tier: int = 1) -> str:
    """Tier 1 is the war as first met (war_snapshot_v1.json); tiers 2 and 3 are the same war baked
    harder for a second and later visit (war_snapshot_t2.json, _t3.json; verdance.world.visit_tiers)."""
    tier = int(tier or 1)
    name = "war_snapshot_v1.json" if tier <= 1 else f"war_snapshot_t{tier}.json"
    return f"data/base_templates/{map_id}/{name}"


def load_recipe(workspace: Path, map_id: str = MAP_ID) -> Dict[str, Any]:
    return _json(Path(workspace) / recipe_rel(map_id))


def load_snapshot(workspace: Path, map_id: str = MAP_ID, tier: int = 1) -> Optional[Dict[str, Any]]:
    """The war at this tier, or the nearest tier below it that has been baked."""
    for t in range(int(tier or 1), 0, -1):
        snap = _json(Path(workspace) / snapshot_rel(map_id, t))
        if snap.get("schemaVersion") == SCHEMA and snap.get("teams"):
            return snap
    return None


def recipe_for_tier(recipe: Dict[str, Any], tier: int) -> Dict[str, Any]:
    """The recipe a tier bakes: the base recipe with its ``tiers[<n>]`` overrides applied.
    ``minutes``; ``profiles`` {seat key or ally name: BARb profile}; ``handicap`` {seat key or ally: %};
    ``addTeams`` [seat, ...] (extra seats, e.g. va_warden forts)."""
    import copy
    tier = int(tier or 1)
    out = copy.deepcopy(recipe)
    over = (recipe.get("tiers") or {}).get(str(tier)) or {}
    if "minutes" in over:
        out["minutes"] = over["minutes"]
    for t in out["teams"]:
        for key in (t["ally"], t["key"]):
            if key in (over.get("profiles") or {}) and t["key"] != recipe.get("playerSeat"):
                t["profile"] = over["profiles"][key]
            if key in (over.get("handicap") or {}):
                t["handicap"] = over["handicap"][key]
    out["teams"] += copy.deepcopy(over.get("addTeams") or [])
    out["tier"] = tier
    out.pop("tiers", None)
    return out


def tier_seat_keys(recipe: Dict[str, Any]) -> List[str]:
    """Every seat any tier of this war can field (the base seats and each tier's added ones)."""
    keys = [t["key"] for t in recipe.get("teams") or []]
    for over in (recipe.get("tiers") or {}).values():
        keys += [t["key"] for t in over.get("addTeams") or [] if t["key"] not in keys]
    return keys


def war_maps(workspace: Path) -> List[str]:
    """Every map that has a war recipe, in name order."""
    base = Path(workspace) / "data" / "base_templates"
    return sorted(p.parent.name for p in base.glob("*/war_recipe.json"))


# ----------------------------------------------------------------------------- the sim's startscript

def _num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def startscript(recipe: Dict[str, Any], *, game_type: str, frames: Optional[int] = None,
                map_size: Optional[tuple] = None) -> str:
    """The BARb war as a Spring startscript: one ally team per side, a spectator host, seats at the
    recipe's positions (StartPosType 3 reads StartPosX/Z from the script)."""
    map_size = tuple(map_size or recipe.get("mapSize") or DEFAULT_MAP_SIZE)
    teams = recipe["teams"]
    sides = recipe["sides"]
    frames = int(frames or recipe.get("minutes", 20) * 60 * 30)
    allies = sorted({t["ally"] for t in teams})
    ally_ids = {name: i for i, name in enumerate(allies)}
    blocks: List[str] = []
    for name in allies:
        mine = [t for t in teams if t["ally"] == name]
        rect = [
            min(t["startElmos"][0] for t in mine) / map_size[0], min(t["startElmos"][1] for t in mine) / map_size[1],
            max(t["startElmos"][0] for t in mine) / map_size[0], max(t["startElmos"][1] for t in mine) / map_size[1],
        ]
        blocks.append(
            f"  [ALLYTEAM{ally_ids[name]}]\n  {{\n    NumAllies=0;\n"
            f"    StartRectLeft={_num(rect[0])};\n    StartRectTop={_num(rect[1])};\n"
            f"    StartRectRight={_num(rect[2])};\n    StartRectBottom={_num(rect[3])};\n  }}\n")
    for i, t in enumerate(teams):
        side = sides[t["ally"]]
        blocks.append(
            f"  [TEAM{i}]\n  {{\n    TeamLeader=0;\n    AllyTeam={ally_ids[t['ally']]};\n    Handicap={int(t.get('handicap', 0))};\n"
            f"    Side={side['side']};\n    RGBColor={side['rgb']};\n"
            f"    StartPosX={int(t['startElmos'][0])};\n    StartPosZ={int(t['startElmos'][1])};\n  }}\n")
    for i, t in enumerate(teams):
        side = sides[t["ally"]]
        blocks.append(
            f"  [AI{i}]\n  {{\n    Name=BARb {t['profile']} ({side['side']} {t['key']});\n    ShortName=BARb;\n"
            f"    Team={i};\n    Host=0;\n    Version=stable;\n    [OPTIONS]\n    {{\n      profile={t['profile']};\n    }}\n  }}\n")
    return (
        "[GAME]\n{\n"
        f"  MapName={recipe['mapName']};\n  GameType={game_type};\n  GameStartDelay=0;\n"
        "  StartPosType=3;\n  RecordDemo=0;\n  MyPlayerName=VerdanceWarBake;\n  IsHost=1;\n"
        f"  FixedRNGSeed={int(recipe.get('seed', 3303))};\n  NumPlayers=1;\n  NumUsers={len(teams) + 1};\n"
        "  HostIP=127.0.0.1;\n  HostPort=0;\n  NoHelperAIs=0;\n\n"
        "  [MODOPTIONS]\n  {\n    deathmode=neverend;\n    experimentallegionfaction=1;\n    va_campaign=0;\n"
        f"    va_shell_bake=1;\n    va_shell_bake_frames={frames};\n    va_shell_bake_mapid={recipe.get('mapId', MAP_ID)};\n"
        "    debugcommands=1:cheat;\n  }\n\n"
        "  [PLAYER0]\n  {\n    Name=VerdanceWarBake;\n    Spectator=1;\n    Team=0;\n    Rank=0;\n  }\n\n"
        + "\n".join(blocks) + "}\n")


# ----------------------------------------------------------------------------- the dump

_UNIT = re.compile(r"VA_SHELL_UNIT\s+(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(-?\d+)\s+([\d.]+)\s+([\d.]+)\s+([SMAWC])")
_TEAM = re.compile(r"VA_SHELL_TEAM\s+(\d+)\s+(\S*)\s+(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)")
_MAP = re.compile(r"VA_SHELL_MAP\s+(\d+)\s+(\d+)")
_WRECK = re.compile(r"VA_SHELL_WRECK\s+(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?\d+)\s+(\d+)")
_TICK = re.compile(r"VA_SHELL_BAKE_TICK\s+frame=(\d+)\s+target=(\d+)(?:\s+units=(\S+))?")


def parse_dump(text: str) -> Dict[str, Any]:
    """Facts out of an infolog: the map size, every unit the dump listed and every team's bank."""
    out: Dict[str, Any] = {"map": None, "units": [], "teams": {}, "wrecks": []}
    for line in text.splitlines():
        m = _WRECK.search(line)
        if m:
            name, x, z, heading, metal = m.groups()
            out["wrecks"].append({"def": name, "x": float(x), "z": float(z), "heading": int(heading), "metal": int(metal)})
            continue
        m = _UNIT.search(line)
        if m:
            d, x, z, face, team, hp, built, kind = m.groups()
            out["units"].append({"def": d, "x": float(x), "z": float(z), "facing": int(face), "team": int(team),
                                 "hp": float(hp), "built": float(built), "kind": kind})
            continue
        m = _TEAM.search(line)
        if m:
            t, side, ally, metal, mstor, energy, estor = m.groups()
            out["teams"][int(t)] = {"side": side, "ally": int(ally), "metal": int(metal), "mstor": int(mstor),
                                    "energy": int(energy), "estor": int(estor)}
            continue
        m = _MAP.search(line)
        if m:
            out["map"] = (float(m.group(1)), float(m.group(2)))
    return out


def progress(text: str) -> Optional[Dict[str, Any]]:
    """The last progress tick in an infolog, for watching a run: {frame, target, units: {team: n}}."""
    last = None
    for m in _TICK.finditer(text):
        last = m
    if not last:
        return None
    units = {}
    for part in (last.group(3) or "").split(","):
        k, _, v = part.partition(":")
        if v.isdigit():
            units[int(k)] = int(v)
    return {"frame": int(last.group(1)), "target": int(last.group(2)), "units": units}


# ----------------------------------------------------------------------------- the snapshot

def _cost(costs: Dict[str, Any], def_name: str) -> float:
    row = (costs or {}).get(def_name)
    return float(row[0]) if isinstance(row, (list, tuple)) and row else 0.0


def build_snapshot(recipe: Dict[str, Any], dump: Dict[str, Any], *, costs: Optional[Dict[str, Any]] = None,
                   baked_at: str = "", minutes: Optional[float] = None) -> Dict[str, Any]:
    """The war as the mission builder wants it: positions normalized, the company's seat pulled out,
    unfinished work left behind, each side capped to what a drop can carry."""
    rec_teams = recipe["teams"]
    sides = recipe["sides"]
    mx, mz = dump.get("map") or tuple(recipe.get("mapSize") or DEFAULT_MAP_SIZE)
    cfg = recipe.get("snapshot") or {}
    cap = int(cfg.get("maxUnitsPerTeam") or 900)
    min_built = float(cfg.get("minBuilt") or 0.5)
    player_key = recipe.get("playerSeat")
    teams: List[Dict[str, Any]] = []
    pulled: Dict[str, Any] = {}
    for i, t in enumerate(rec_teams):
        mine = [u for u in dump["units"] if u["team"] == i]
        if t["key"] == player_key:
            pulled = {"key": t["key"], "units": len(mine), "commanders": sum(1 for u in mine if u["kind"] == "C")}
            continue
        done = [u for u in mine if u["built"] >= min_built]
        kept = len(done)
        if kept > cap:
            # cheapest mobile units first out; structures and commanders stay
            mobile = sorted((u for u in done if u["kind"] in MOBILE_KINDS), key=lambda u: _cost(costs, u["def"]))
            drop = {id(u) for u in mobile[: kept - cap]}
            done = [u for u in done if id(u) not in drop]
        side = sides[t["ally"]]
        bank = dump.get("teams", {}).get(i) or {}
        teams.append({
            "key": t["key"], "ally": t["ally"], "faction": side["faction"], "side": side["side"], "profile": t["profile"],
            "zoneId": t["zoneId"], "label": t["label"],
            "seat": [round(t["startElmos"][0] / mx, 4), round(t["startElmos"][1] / mz, 4)],
            "bank": {k: bank.get(k, 0) for k in ("metal", "mstor", "energy", "estor")},
            "unitCount": len(done),
            "units": [[u["def"], round(u["x"] / mx, 4), round(u["z"] / mz, 4), u["facing"], int(round(u["hp"] * 100)), u["kind"]]
                      for u in done],
        })
    # The field's dead: the war's wrecks and heaps, richest first, none on the company's own seat.
    max_wrecks = int(cfg.get("maxWrecks") or 240)
    seat = next((t["startElmos"] for t in rec_teams if t["key"] == player_key), None)
    lying = [w for w in dump.get("wrecks") or []
             if not (seat and ((w["x"] - seat[0]) / mx) ** 2 + ((w["z"] - seat[1]) / mz) ** 2 < WRECK_SEAT_CLEARANCE ** 2)]
    lying.sort(key=lambda w: -w["metal"])
    wrecks = [[w["def"], round(w["x"] / mx, 4), round(w["z"] / mz, 4), w["heading"], w["metal"]] for w in lying[:max_wrecks]]
    return {
        "schemaVersion": SCHEMA, "mapId": recipe.get("mapId", MAP_ID), "mapName": recipe.get("mapName"),
        "bakedAt": baked_at, "minutes": minutes if minutes is not None else recipe.get("minutes"),
        "dry": bool(recipe.get("dry", True)), "seed": recipe.get("seed"),
        "character": recipe.get("character"), "mapSize": [mx, mz],
        "pulled": pulled, "teams": teams, "wrecks": wrecks, "tier": int(recipe.get("tier") or 1),
        "unitCount": sum(t["unitCount"] for t in teams),
    }


def write_snapshot(workspace: Path, snapshot: Dict[str, Any]) -> Path:
    path = Path(workspace) / snapshot_rel(str(snapshot.get("mapId") or MAP_ID), int(snapshot.get("tier") or 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    # one line per unit would be big; keep each team's units on a line apiece
    head = {k: v for k, v in snapshot.items() if k != "teams"}
    lines = ["{"]
    for k, v in head.items():
        lines.append(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
    lines.append('  "teams": [')
    for ti, t in enumerate(snapshot["teams"]):
        body = {k: v for k, v in t.items() if k != "units"}
        lines.append("    {")
        for k, v in body.items():
            lines.append(f"      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
        lines.append('      "units": [')
        lines.extend("        " + json.dumps(u) + ("," if i < len(t["units"]) - 1 else "") for i, u in enumerate(t["units"]))
        lines.append("      ]")
        lines.append("    }" + ("," if ti < len(snapshot["teams"]) - 1 else ""))
    lines.append("  ]")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = ["MAP_ID", "SCHEMA", "recipe_rel", "snapshot_rel", "load_recipe", "load_snapshot", "war_maps", "startscript",
           "parse_dump", "progress", "build_snapshot", "write_snapshot"]
