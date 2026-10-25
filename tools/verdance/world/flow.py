#!/usr/bin/env python3
"""The field and its descent: how a war's forces flow through a map's zones (prototype, 2026-10-25).

Every zone in data/zone_maps/world_zone_graph.v1.json carries evidence read off the terrain (metal,
buildable ground, defence, height, slope, choke). This module turns it into three things:

  field      V(z) in [0, 1]: what a zone is worth to hold (metal, room to build, defence, height).
             slope and choke are kept apart: they say how ground fights, not what it is worth.
  descent    each side's potential: low on its own valuable ground and near its seats. A force pushed
             out of a zone rolls down that potential along the zone edges, preferring chokes (a
             retreat funnels). The path it takes is the war's flow for that side.
  chain      the sorties that ride the flow, in switchbacks (2026-10-25): ground is measured in rings
             around the side's stronghold; the chain starts at the shallow end (the enemy's border
             zone with the most rings to go), and each sortie either crosses the slope along its ring
             or goes one ring in, never back out, about STAGES sorties in all, taking the gates and
             works on the way. stages=0 is the old straight dive. The belief over the graph is continuous; a sortie
             collapses it to one zone and its exits, and the result moves mass along these edges.

  bake plan  how long a map's standing war should run, and how each seat develops: richer seats and
             steeper ground get a longer war; a seat's Handicap (income bonus, percent) follows its
             ground's value against the map's mean (floor -5%, cap +30%); the recipe's BARb profiles
             stand.

    python -m verdance.world.flow --map ancient_bastion
"""
from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]

W_METAL, W_BUILD, W_DEF, W_HEIGHT = 0.40, 0.20, 0.25, 0.15
CHOKE_GATE = 0.6          # a zone at or above this choke is a gate the flow has to pass through


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def map_graph(map_id: str, workspace: Path = ROOT) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    g = _load(workspace / "data" / "zone_maps" / "world_zone_graph.v1.json")
    nodes = {n["zoneId"]: n for n in g["nodes"] if n.get("mapId") == map_id}
    adj: Dict[str, List[str]] = {z: [] for z in nodes}
    for e in g["edges"]:
        if e.get("kind") == "same_map" and e["from"] in nodes and e["to"] in nodes:
            adj[e["from"]].append(e["to"])
            adj[e["to"]].append(e["from"])
    return nodes, {z: sorted(set(v)) for z, v in adj.items()}


def field(nodes: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """V(z) and the raw terms, normalised within the map."""
    ev = {z: n.get("evidence") or {} for z, n in nodes.items()}
    def norm(key: str) -> Dict[str, float]:
        vals = {z: float(e.get(key) or 0.0) for z, e in ev.items()}
        hi = max(vals.values()) if vals else 0.0
        return {z: (v / hi if hi > 0 else 0.0) for z, v in vals.items()}
    metal, build, dfn, height = norm("metal"), norm("buildable"), norm("defence"), norm("relativeHeight")
    has_metal = any(v > 0 for v in metal.values())
    wm = W_METAL if has_metal else 0.0
    total = wm + W_BUILD + W_DEF + W_HEIGHT
    out = {}
    for z in nodes:
        v = (wm * metal[z] + W_BUILD * build[z] + W_DEF * dfn[z] + W_HEIGHT * height[z]) / total
        e = ev[z]
        worth = float(e.get("metal") or 0) + 0.5 * float(e.get("buildable") or 0) + 0.5 * float(e.get("defence") or 0)
        out[z] = {"V": round(v, 3), "slope": float(e.get("slope") or 0.0), "choke": float(e.get("choke") or 0.0),
                  "metal": float(e.get("metal") or 0.0), "worth": round(worth, 3)}
    return out


def hops(adj: Dict[str, List[str]], sources: List[str]) -> Dict[str, int]:
    dist = {s: 0 for s in sources if s in adj}
    q = [(0, s) for s in dist]
    while q:
        d, z = heapq.heappop(q)
        if d > dist.get(z, 1 << 30):
            continue
        for n in adj[z]:
            if d + 1 < dist.get(n, 1 << 30):
                dist[n] = d + 1
                heapq.heappush(q, (d + 1, n))
    return dist


def control(adj: Dict[str, List[str]], seats: Dict[str, List[str]]) -> Dict[str, Optional[str]]:
    """Who holds each zone: the side whose seats are nearest (ties: nobody, contested ground)."""
    d = {side: hops(adj, zs) for side, zs in seats.items()}
    out: Dict[str, Optional[str]] = {}
    for z in adj:
        best = sorted((d[s].get(z, 99), s) for s in d)
        out[z] = best[0][1] if best and (len(best) == 1 or best[0][0] < best[1][0]) else None
    return out


def potential(side: str, f: Dict[str, Dict[str, float]], adj: Dict[str, List[str]], seats: Dict[str, List[str]],
              ctrl: Dict[str, Optional[str]]) -> Dict[str, float]:
    """Low where the side wants to be: its seats, its own valuable ground; high far from home."""
    d = hops(adj, seats[side])
    span = max(1, max(d.values()) if d else 1)
    return {z: round(d.get(z, span) / span - (0.6 * f[z]["V"] if ctrl.get(z) == side else 0.2 * f[z]["V"]), 3) for z in adj}


def descent(start: str, side: str, phi: Dict[str, float], adj: Dict[str, List[str]], f: Dict[str, Dict[str, float]],
            limit: int = 12) -> List[str]:
    """Steepest descent from start down the side's potential; among near-equal steps take the choke."""
    path, z = [start], start
    for _ in range(limit):
        nxt = [(phi[n] - 0.08 * f[n]["choke"], n) for n in adj[z] if n not in path]
        if not nxt:
            break
        score, n = min(nxt)
        if phi[n] >= phi[z]:
            break
        path.append(n)
        z = n
    return path


STAGES = 5            # how many sorties a flow should take, stronghold included


def switchback(start: str, goal: str, adj: Dict[str, List[str]], f: Dict[str, Dict[str, float]],
               allowed: set, stages: int = STAGES) -> List[str]:
    """A staged descent to the stronghold. Ground is measured in rings (hops from the stronghold): a
    step either traverses along its ring or goes one ring in, never back out. The best path has as
    close to `stages` steps as the map allows, crosses the slope (traverses) instead of diving, takes
    the gates on the way and ground worth taking. It keeps to `allowed` (the enemy's ground and the
    contested middle; the company's own ground is not a sortie). Every simple path is weighed: the
    graphs are small."""
    ring = hops(adj, [goal])
    best: Tuple[float, List[str]] = (-1e9, [])
    traverse_cap = max(1, stages - ring.get(start, 0) - 1)

    def score(path: List[str]) -> float:
        steps = len(path)
        gates = sum(f[z]["choke"] >= CHOKE_GATE for z in path[1:-1])
        worth = sum(f[z]["V"] for z in path[1:-1]) / max(1, steps - 2)
        # a switchback alternates: across the slope, then down; two traverses in a row is a detour
        flat = [ring[b] == ring[a] for a, b in zip(path, path[1:])]
        alternations = sum(1 for x, y in zip(flat, flat[1:]) if x != y)
        runs = sum(1 for x, y in zip(flat, flat[1:]) if x and y)
        return -2.0 * abs(steps - stages) + 0.6 * gates + 0.5 * worth + 0.4 * alternations - 0.8 * runs

    def walk(path: List[str], traverses: int) -> None:
        nonlocal best
        z = path[-1]
        if z == goal:
            sc = score(path)
            if sc > best[0]:
                best = (sc, list(path))
            return
        if len(path) >= stages + 2:
            return
        for n in adj[z]:
            if n in path or (n != goal and n not in allowed):
                continue
            if ring[n] == ring[z] - 1:
                path.append(n); walk(path, traverses); path.pop()
            elif ring[n] == ring[z] and traverses < traverse_cap:
                path.append(n); walk(path, traverses + 1); path.pop()

    walk([start], 0)
    return best[1]


def _route(adj: Dict[str, List[str]], start: str, goal: List[str], f: Dict[str, Dict[str, float]]) -> List[str]:
    """Shortest path to the nearest goal zone, through chokes when there is a choice."""
    best = {start: 0.0}
    prev: Dict[str, str] = {}
    q = [(0.0, start)]
    while q:
        d, z = heapq.heappop(q)
        if z in goal:
            out = [z]
            while out[-1] in prev:
                out.append(prev[out[-1]])
            return out[::-1]
        for n in adj[z]:
            nd = d + 1.0 - 0.3 * f[n]["choke"]
            if nd < best.get(n, 1e9):
                best[n], prev[n] = nd, z
                heapq.heappush(q, (nd, n))
    return [start]


def chain(attacker_holds: List[str], enemy: str, f, adj, seats, ctrl, stages: int = STAGES,
          home_side: Optional[str] = None) -> List[Dict[str, Any]]:
    """The sorties that ride one enemy's flow: first the most valuable enemy zone on the company's
    frontier, then down the enemy's descent, marking the gates and the stronghold."""
    phi = potential(enemy, f, adj, seats, ctrl)
    # the flow starts where the two sides touch: the enemy zone nearest the company (richest first)
    near = hops(adj, attacker_holds)
    frontier = sorted((z for z in adj if ctrl.get(z) == enemy), key=lambda z: (near.get(z, 99), -f[z]["V"]))
    if not frontier:
        return []
    # the side's stronghold is its richest seat; the other seats are works on the way
    main = max(seats[enemy], key=lambda z: f[z]["V"])
    goal = [main]
    allowed = {z for z in adj if ctrl.get(z) != home_side} if home_side else set(adj)
    # start at the shallow end: of the enemy's ground on the border with the company's side, the zone
    # farthest from its stronghold (the most rings to descend), nearest the company on a tie
    ring = hops(adj, [main])
    border = [z for z in adj if ctrl.get(z) == enemy and any(n not in allowed for n in adj[z])]
    if border:
        frontier = sorted(border, key=lambda z: (-ring.get(z, 0), near.get(z, 99), -f[z]["V"]))
    path = switchback(frontier[0], main, adj, f, allowed, stages) if stages > 0 else []
    if not path:
        # steepest descent, finished by the shortest route (the old behaviour; stages=0 asks for it)
        path = descent(frontier[0], enemy, phi, adj, f, limit=20)
        if path[-1] not in goal:
            for z in _route(adj, path[-1], goal, f)[1:]:
                path = path[:path.index(z) + 1] if z in path else path + [z]
    out = []
    ring_of = hops(adj, [main])
    for i, z in enumerate(path):
        step_drop = (ring_of[path[i - 1]] - ring_of[z]) if i else 0
        kind = ("stronghold" if z == main else "works" if z in seats[enemy]
                else "gate" if f[z]["choke"] >= CHOKE_GATE else "field")
        out.append({"step": i + 1, "zoneId": z, "kind": kind, "V": f[z]["V"], "choke": f[z]["choke"], "slope": f[z]["slope"],
                    "held": ctrl.get(z), "drop": step_drop, "ring": ring_of.get(z),
                    "sortie": {"field": "push them off the field: they fall back down the flow",
                               "works": "raid the works: wreck what they built, they fall back",
                               "gate": "assault the choke they fell back through",
                               "stronghold": "take the stronghold: the flow ends here"}[kind]})
    return out


def bake_plan(recipe: Dict[str, Any], f: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    teams = recipe["teams"]
    vs = [f.get(t["zoneId"], {}).get("V", 0.0) for t in teams]
    ss = [f.get(t["zoneId"], {}).get("slope", 0.0) for t in teams]
    vbar = sum(vs) / len(vs) if vs else 0.0
    sbar = sum(ss) / len(ss) if ss else 0.0
    # how long the war runs follows ABSOLUTE worth (V is relative within a map): metal to spend,
    # room to build, defence to dig into, and slope (steep ground is slow ground to take, so the
    # sides have longer to build before the company arrives)
    worth = [f.get(t["zoneId"], {}).get("worth", 0.0) for t in teams]
    wbar = sum(worth) / len(worth) if worth else 0.0
    minutes = max(10, min(30, round(8 + 7 * wbar + 60 * sbar)))
    seats = []
    for t, v, s in zip(teams, vs, ss):
        dfn = f.get(t["zoneId"], {}).get("choke", 0.0)
        # The recipe's profile stands (a siege stays aggressive). First bake (Bastion, 2026-10-25) with
        # the field also choosing profiles and a -19% floor: the castle went 761 -> 914 units and the
        # siege collapsed (besiegers 93/101 -> 57/43, one commander lost). Rich ground still builds
        # faster; poor ground is barely held back.
        profile = t.get("profile")
        seats.append({"key": t["key"], "zoneId": t["zoneId"], "V": round(v, 3), "slope": round(s, 3),
                      "handicap": int(max(-5, min(30, round(50 * (v - vbar))))), "profile": profile})
    return {"minutes": minutes, "meanWorth": round(wbar, 3), "meanV": round(vbar, 3), "meanSlope": round(sbar, 3), "seats": seats,
            "was": {"minutes": recipe.get("minutes"), "profiles": {t["key"]: t.get("profile") for t in teams}}}


def apply_plan(recipe: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    r = json.loads(json.dumps(recipe))
    r["minutes"] = plan["minutes"]
    by = {s["key"]: s for s in plan["seats"]}
    for t in r["teams"]:
        s = by.get(t["key"])
        if s:
            t["profile"], t["handicap"] = s["profile"], s["handicap"]
    return r


def report(map_id: str, workspace: Path = ROOT, stages: int = STAGES) -> Dict[str, Any]:
    nodes, adj = map_graph(map_id, workspace)
    f = field(nodes)
    rp = workspace / "data" / "base_templates" / map_id / "war_recipe.json"
    recipe = _load(rp) if rp.is_file() else None
    seats: Dict[str, List[str]] = {}
    if recipe:
        for t in recipe["teams"]:
            seats.setdefault(t["ally"], []).append(t["zoneId"])
    out: Dict[str, Any] = {"mapId": map_id, "field": f, "adjacency": adj}
    if not seats:
        return out
    ctrl = control(adj, seats)
    out["control"] = ctrl
    player = next((t for t in recipe["teams"] if t["key"] == recipe.get("playerSeat")), None)
    home = player["ally"] if player else None
    holds = [player["zoneId"]] if player else []
    out["descent"] = {side: {z: descent(z, side, potential(side, f, adj, seats, ctrl), adj, f) for z in adj} for side in seats}
    out["chains"] = {side: chain(holds, side, f, adj, seats, ctrl, stages, home) for side in seats if side != home}
    out["bake"] = bake_plan(recipe, f)
    return out


def _print(rep: Dict[str, Any]) -> None:
    f, ctrl = rep["field"], rep.get("control") or {}
    print(f"\n=== {rep['mapId']} ===")
    print(f"{'zone':<22}{'held by':<9}{'V':>6}{'slope':>7}{'choke':>7}")
    for z in sorted(f, key=lambda z: -f[z]["V"]):
        print(f"{z:<22}{str(ctrl.get(z) or '-'):<9}{f[z]['V']:>6.2f}{f[z]['slope']:>7.3f}{f[z]['choke']:>7.2f}")
    for side, steps in (rep.get("chains") or {}).items():
        print(f"\n  sortie chain against {side}:")
        for s in steps:
            print(f"    {s['step']}. {s['zoneId']:<20} {s['kind']:<10} ring {s.get('ring')} {'across' if s['step'] > 1 and not s.get('drop') else 'down  ' if s['step'] > 1 else 'start '}  {s['sortie']}")
    b = rep.get("bake")
    if b:
        print(f"\n  bake: {b['was']['minutes']} -> {b['minutes']} min (mean worth {b['meanWorth']}, mean slope {b['meanSlope']})")
        for s in b["seats"]:
            print(f"    {s['key']:<5} {s['zoneId']:<20} V={s['V']:<5} slope={s['slope']:<6} handicap {s['handicap']:+d}%  {s['profile']}"
                  f"  (was {b['was']['profiles'].get(s['key'])})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stages", type=int, default=STAGES, help="sorties per flow (0 = straight down, the old way)")
    a = ap.parse_args()
    maps = [m for c in a.map for m in c.split(",") if m] or sorted(
        p.parent.name for p in (ROOT / "data" / "base_templates").glob("*/war_recipe.json"))
    reps = [report(m, stages=a.stages) for m in maps]
    if a.json:
        print(json.dumps(reps, indent=1))
    else:
        for r in reps:
            _print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
