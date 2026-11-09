"""Hero temper: how each named hero comes to this drop, read from what the camp has done to them.

Owner direction (2026-11-09): heroes have their own behaviour on top of the AI's orders, driven by
personality and mood, and the mood moves with camp interactions, so a hero plays differently after
what happened at camp. Personality is the hero's doctrine (data/story/hero_codex.json ->
va_hero_doctrine.lua: line, skirm, rez...). Temper is the mood on top of it, two numbers in [-1, 1]:

  nerve   steadiness under fire.
  drive   appetite to push.

The mood runs on an Umwelt graph (owner call 2026-11-09: personality and mood graphs on the Umwelt
substrate, no hand-set weights). Each hero on the drop is a node with nerve and drive as dissipative
beliefs; what happened to them is evidence, each event one observation of that node:

  each level above the first     steady and eager (nerve 1, drive 1)
  each time they went down       shaken (nerve 0)
  a wound carried into the drop  shaken (nerve 0)
  the bond with each drop-mate   steadied and eager (nerve 1, drive 1) for a friend, shaken and
                                 sapped (0, 0) for a rival, at a confidence of the bond's points / 100

and the people bind them: a bridge between bonded drop-mates (coupling = points / 100, negative for a
rivalry: their moods pull apart) and to each bonded friend who has died, whose node is held at despair
(0, 0) so that grief reaches the living through the bond. Umwelt's own transport carries mood along the
bridges, one hop per step, for as many steps as the graph is wide; nerve and drive are then read off
(belief value v in [0, 1] -> 2v - 1). Nothing here weighs one kind of event against another: the
substrate's observation and transport do.

The field reads them (game_verdance_unit_behavior.lua and the safety field via mission.heroTemper): a
shaken hero sees danger larger and a steady one smaller (x e^-nerve); an eager one sees gains larger
(x e^drive).

Without Umwelt (a build that cannot import it) the old closed form is used, so a drop still builds.
"""
from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, load_json

ADVERSARY = {"rivalry", "tension", "friction"}
ROLES = ("nerve", "drive")


def _web_polarity(workspace: Optional[Path]) -> Dict[frozenset, str]:
    """{frozenset({a, b}): polarity} from data/story/support_web.json, when it says."""
    p = Path(workspace or WORKSPACE_ROOT) / "data" / "story" / "support_web.json"
    data = load_json(p) if p.exists() else {}
    out: Dict[frozenset, str] = {}
    rows = data.get("pairs") or data.get("edges") or data.get("supports") or [] if isinstance(data, dict) else []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        a, b = r.get("a") or r.get("from"), r.get("b") or r.get("to")
        pol = r.get("polarity") or r.get("type")
        if a and b and pol:
            out[frozenset((str(a), str(b)))] = str(pol)
    return out


def _points(pairs: Dict[str, Any], a: str, b: str) -> float:
    x, y = sorted((a, b))
    row = pairs.get(f"{x}__{y}")
    return float((row or {}).get("points") or 0.0) if isinstance(row, dict) else 0.0


def _camp(state: Dict[str, Any], drop: List[str], workspace: Optional[Path]):
    """What the camp knows: per hero, the events; the bonds among the drop and to the dead."""
    pairs = ((state.get("attachments") or {}).get("pairBonds") or {})
    pairs = pairs if isinstance(pairs, dict) else {}
    chars = state.get("characters") or {}
    roster = {str(h.get("heroId")): h for h in ((state.get("roster") or {}).get("heroes") or []) if isinstance(h, dict)}
    dead = {hid for hid, h in roster.items() if str(h.get("status") or "") == "dead"}
    dead |= {hid for hid, c in chars.items() if isinstance(c, dict) and str(c.get("status") or "") == "dead"}
    polarity = _web_polarity(workspace)
    events: Dict[str, Dict[str, Any]] = {}
    for hid in drop:
        h = roster.get(hid) or {}
        c = chars.get(hid) if isinstance(chars.get(hid), dict) else {}
        events[hid] = {
            "level": int(h.get("level") or 1),
            "timesDown": int(h.get("timesWounded") or c.get("wounds") or 0),
            "woundedNow": str(h.get("status") or "") == "wounded",
        }
    bonds: List[Tuple[str, str, float]] = []      # (a, b, signed points / 100) among the drop
    for i, a in enumerate(drop):
        for b in drop[i + 1:]:
            pts = _points(pairs, a, b) / 100.0
            if pts:
                sign = -1.0 if polarity.get(frozenset((a, b))) in ADVERSARY else 1.0
                bonds.append((a, b, sign * pts))
    grief: List[Tuple[str, str, float]] = []      # (living, dead, points / 100)
    for hid in drop:
        for d in sorted(dead):
            if d != hid and d not in drop:
                pts = _points(pairs, hid, d) / 100.0
                if pts > 0:
                    grief.append((hid, d, pts))
    return events, bonds, grief


def _width(nodes: List[str], edges: List[Tuple[str, str]]) -> int:
    """The graph's diameter in hops (how many transport steps reach every node from every other)."""
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    best = 0
    for s in nodes:
        seen, q = {s: 0}, deque([s])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in seen:
                    seen[v] = seen[u] + 1
                    q.append(v)
        best = max(best, max(seen.values()))
    return best


def _umwelt_temper(drop: List[str], events, bonds, grief) -> Optional[Dict[str, Dict[str, float]]]:
    try:
        from verdance.belief.world import _umwelt
        mods = _umwelt()
    except Exception:  # noqa: BLE001
        mods = None
    if mods is None:
        return None
    schema, api = mods
    mourned = sorted({d for _, d, _ in grief})
    node = {h: f"hero:{h}" for h in drop}
    node.update({d: f"dead:{d}" for d in mourned})
    modes = {r: "dissipative" for r in ROLES}
    nodes = [schema.NodeSpec("camp", parent=None, kind="root", roles=())]
    for key in list(drop) + mourned:
        nodes.append(schema.NodeSpec(node[key], parent="camp", kind="entity", roles=ROLES, role_modes=dict(modes)))
    couplings: Dict[frozenset, float] = {}
    bridges = []
    for a, b, c in bonds:
        bridges.append(schema.BridgeSpec(node[a], node[b], shared_roles=ROLES, kind="open"))
        couplings[frozenset((node[a], node[b]))] = c
    for a, d, c in grief:
        bridges.append(schema.BridgeSpec(node[a], node[d], shared_roles=ROLES, kind="open"))
        couplings[frozenset((node[a], node[d]))] = c
    norm = {"type": "range", "lo": 0.0, "hi": 1.0}
    bindings = [schema.BindingSpec(f"obs_{node[k]}_{r}", zone=node[k], role=r, normalizer=norm, force_observe=True,
                                   efficiency=1.0, strength=1.0) for k in list(drop) + mourned for r in ROLES]
    spec = schema.DomainSpec(name="verdance-camp-temper", nodes=tuple(nodes), bridges=tuple(bridges), bindings=tuple(bindings))
    host = api.GameHost().register_world(spec, population=False)
    # the bonds as couplings, fixed (the substrate may not learn them away inside one reading)
    for br in host.engine.graph.bridges:
        c = couplings.get(frozenset((str(br.source), str(br.target))))
        if c is not None:
            br.coupling_param.value = max(br.coupling_param.lo, min(br.coupling_param.hi, c))
            br.coupling_param.frozen = True

    def obs(readings: Dict[str, float], conf: Dict[str, float]) -> None:
        if readings:
            host.observe_many("camp", readings, conf)

    # nobody knows yet how anyone feels: every belief starts at the mixed centre (as the world primes)
    prime = {b.sensor_id: 0.5 for b in spec.bindings}
    for _ in range(4):
        obs(prime, {k: 1.0 for k in prime})
    despair = {f"obs_{node[d]}_{r}": 0.0 for d in mourned for r in ROLES}
    held = {k: 1.0 for k in despair}
    obs(despair, held)
    # the events, one observation each; every hero's k-th event of a kind goes in together (each
    # observation steps the field, so one hero first would hear the others' news before its own)
    def rounds(count, readings_for):
        for k in range(1, max([count(h) for h in drop] + [0]) + 1):
            r: Dict[str, float] = {}
            for h in drop:
                if count(h) >= k:
                    r.update(readings_for(h))
            obs(r, {s: 1.0 for s in r})

    rounds(lambda h: events[h]["level"] - 1, lambda h: {f"obs_{node[h]}_nerve": 1.0, f"obs_{node[h]}_drive": 1.0})
    rounds(lambda h: events[h]["timesDown"], lambda h: {f"obs_{node[h]}_nerve": 0.0})
    rounds(lambda h: 1 if events[h]["woundedNow"] else 0, lambda h: {f"obs_{node[h]}_nerve": 0.0})
    # the bonds felt, both ends at once, at a confidence of their points
    for a, b, c in bonds:
        v = 1.0 if c > 0 else 0.0
        r = {f"obs_{node[h]}_{role}": v for h in (a, b) for role in ROLES}
        obs(r, {s: abs(c) for s in r})
    # transport along the bonds, the dead held at despair, one hop per step across the graph's width
    width = _width(list(node.values()), [(node[a], node[b]) for a, b, _ in bonds] + [(node[a], node[d]) for a, d, _ in grief])
    for _ in range(width):
        obs(despair, held)
    out: Dict[str, Dict[str, float]] = {}
    for h in drop:
        out[h] = {r: round(2.0 * float(host.belief_value(node[h], r).value) - 1.0, 3) for r in ROLES}
    return out


def _closed_form(drop: List[str], events, bonds, grief) -> Dict[str, Dict[str, float]]:
    """Without Umwelt: the 2026-11-09 tanh of weighted sums (kept only so a build without the substrate
    still has a temper)."""
    out: Dict[str, Dict[str, float]] = {}
    for hid in drop:
        mine = [c for a, b, c in bonds if hid in (a, b)]
        support = sum(mine) / max(1, len(drop) - 1)
        g = sum(1 for a, _, c in grief if a == hid and c >= 0.25)
        e = events[hid]
        nerve = 0.9 * support - 0.5 * e["woundedNow"] - 0.12 * min(5, e["timesDown"]) - 0.35 * g + 0.06 * (e["level"] - 1)
        drive = 0.6 * support - 0.35 * g + 0.06 * (e["level"] - 1)
        out[hid] = {"nerve": round(math.tanh(nerve), 3), "drive": round(math.tanh(drive), 3)}
    return out


def temper_for_drop(state: Dict[str, Any], drop: Iterable[str], workspace: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """{heroId: {"nerve", "drive"}} for every hero on this drop."""
    drop = list(dict.fromkeys(str(h) for h in drop if h))
    if not drop:
        return {}
    events, bonds, grief = _camp(state, drop, workspace)
    out = _umwelt_temper(drop, events, bonds, grief)
    return out if out is not None else _closed_form(drop, events, bonds, grief)


__all__ = ["temper_for_drop"]
