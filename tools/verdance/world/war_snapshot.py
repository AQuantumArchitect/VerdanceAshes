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


def war_maps(workspace: Path) -> List[str]:
    """Every map that has a war recipe, in name order."""
    base = Path(workspace) / "data" / "base_templates"
    return sorted(p.parent.name for p in base.glob("*/war_recipe.json"))


# ----------------------------------------------------------------------------- the sim's startscript

def _num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def baked_teams(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The seats that play in the bake, in engine team order. A seat marked ``skipBake`` (the
    company's, in a soak: nobody may attack the castle while it is raised) stays in the recipe for
    the mission but has no AI in the sim."""
    return [t for t in recipe["teams"] if not t.get("skipBake")]


def startscript(recipe: Dict[str, Any], *, game_type: str, frames: Optional[int] = None,
                map_size: Optional[tuple] = None) -> str:
    """The BARb war as a Spring startscript: one ally team per side, a spectator host, seats at the
    recipe's positions (StartPosType 3 reads StartPosX/Z from the script)."""
    map_size = tuple(map_size or recipe.get("mapSize") or DEFAULT_MAP_SIZE)
    teams = baked_teams(recipe)
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
        if t.get("ai"):
            # one of BAR's Lua AIs (SimpleDefenderAI, SimpleConstructorAI, SimpleAI): no version, no profile
            blocks.append(
                f"  [AI{i}]\n  {{\n    Name={t['ai']} ({side['side']} {t['key']});\n    ShortName={t['ai']};\n"
                f"    Team={i};\n    Host=0;\n    Version=<not-versioned>;\n  }}\n")
            continue
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

_UNIT = re.compile(r"VA_SHELL_UNIT\s+(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(-?\d+)\s+([\d.]+)\s+([\d.]+)\s+([SMAWC])"
                   r"(?:\s+bp=([\d.]+)\s+fac=(\d))?")
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
            d, x, z, face, team, hp, built, kind, bp, fac = m.groups()
            out["units"].append({"def": d, "x": float(x), "z": float(z), "facing": int(face), "team": int(team),
                                 "hp": float(hp), "built": float(built), "kind": kind,
                                 "bp": float(bp) if bp is not None else None, "factory": fac == "1"})
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


def soak_strip(recipe: Dict[str, Any], dump: Dict[str, Any], map_size: tuple) -> Dict[str, Any]:
    """After a soak (owner call, 2026-11-09): the AIs built the fortress; most of what built it goes.
    recipe.snapshot.strip = {"builderKeep": share of builders kept (mobile constructors and nano
    turrets, never factories), "commanders": how many commanders each side keeps (the ones nearest the
    middle of that side's seats)}. Fewer builders on the field is less Tenebrium to reclaim from it.
    Returns {"units": the dump's units without the stripped, "stripped": counts}."""
    strip = (recipe.get("snapshot") or {}).get("strip") or {}
    if not strip:
        return {"units": dump["units"], "stripped": {}}
    keep_share = max(0.0, min(1.0, float(strip.get("builderKeep", 1.0))))
    keep_coms = int(strip.get("commanders", 10 ** 6))
    rec_teams = baked_teams(recipe)
    ally_of = {i: t["ally"] for i, t in enumerate(rec_teams)}
    centre: Dict[str, tuple] = {}
    for ally in set(ally_of.values()):
        seats = [t["startElmos"] for t in rec_teams if t["ally"] == ally]
        centre[ally] = (sum(s[0] for s in seats) / len(seats), sum(s[1] for s in seats) / len(seats))

    def dist(u: Dict[str, Any]) -> float:
        cx, cz = centre.get(ally_of.get(u["team"]), (map_size[0] / 2, map_size[1] / 2))
        return (u["x"] - cx) ** 2 + (u["z"] - cz) ** 2

    gone: set = set()
    counts = {"builders": 0, "commanders": 0}
    for ally in set(ally_of.values()):
        mine = [u for u in dump["units"] if ally_of.get(u["team"]) == ally]
        builders = sorted((u for u in mine if (u.get("bp") or 0) > 0 and not u.get("factory") and u["kind"] != "C"), key=dist)
        keep_n = int(round(len(builders) * keep_share))
        for u in builders[keep_n:]:
            gone.add(id(u))
            counts["builders"] += 1
        coms = sorted((u for u in mine if u["kind"] == "C"), key=dist)
        for u in coms[keep_coms:]:
            gone.add(id(u))
            counts["commanders"] += 1
    return {"units": [u for u in dump["units"] if id(u) not in gone], "stripped": counts}


def build_snapshot(recipe: Dict[str, Any], dump: Dict[str, Any], *, costs: Optional[Dict[str, Any]] = None,
                   baked_at: str = "", minutes: Optional[float] = None) -> Dict[str, Any]:
    """The war as the mission builder wants it: positions normalized, the company's seat pulled out,
    unfinished work left behind, each side capped to what a drop can carry."""
    rec_teams = baked_teams(recipe)
    sides = recipe["sides"]
    mx, mz = dump.get("map") or tuple(recipe.get("mapSize") or DEFAULT_MAP_SIZE)
    cfg = recipe.get("snapshot") or {}
    cap = int(cfg.get("maxUnitsPerTeam") or 900)
    min_built = float(cfg.get("minBuilt") or 0.5)
    player_key = recipe.get("playerSeat")
    teams: List[Dict[str, Any]] = []
    pulled: Dict[str, Any] = {}
    stripped = soak_strip(recipe, dump, (mx, mz))
    all_units = stripped["units"]
    for i, t in enumerate(rec_teams):
        mine = [u for u in all_units if u["team"] == i]
        if t["key"] == player_key:
            pulled = {"key": t["key"], "units": len(mine), "commanders": sum(1 for u in mine if u["kind"] == "C")}
            continue
        if recipe.get("fieldSides") and t["ally"] not in recipe["fieldSides"]:
            continue  # a side the history needed but missions do not field (its wrecks stay)
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
    # Emplacements (owner call 2026-11-09: LRPCs on the walls): set down after the soak, so the AIs never
    # build around them or pull them; each joins its team as a finished structure.
    by_key = {t["key"]: t for t in teams}
    for e in recipe.get("emplace") or []:
        t = by_key.get(e.get("team"))
        if not t:
            continue
        ex, ez = e["elmos"]
        t["units"].append([e["def"], round(ex / mx, 4), round(ez / mz, 4), int(e.get("facing", 0)), 100, "S"])
        t["unitCount"] = len(t["units"])
    # The field's dead: the war's wrecks and heaps, richest first, none on the company's own seat.
    max_wrecks = int(cfg.get("maxWrecks") or 240)
    seat = next((t["startElmos"] for t in recipe["teams"] if t["key"] == player_key), None)
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
        **({"stripped": stripped["stripped"]} if stripped["stripped"] else {}),
        "unitCount": sum(t["unitCount"] for t in teams),
    }


def write_snapshot(workspace: Path, snapshot: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Write a snapshot where the builder reads it (its map and tier), or to ``path`` (a soak trial)."""
    path = Path(path) if path else Path(workspace) / snapshot_rel(str(snapshot.get("mapId") or MAP_ID), int(snapshot.get("tier") or 1))
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
