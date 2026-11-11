"""Hero minds: specified once as an Umwelt graph, run live in the engine.

Owner direction (2026-11-10 and 11-11): Umwelt-driven hero behaviour is a first-class product, a way
to contribute to the engine. Umwelt runs efficiently "in clusters of bits with only a few bridges
across; if they all connect it becomes a giant matrix and it's a mess, so keep it sparse and run the
clusters in parallel". It needn't run fast: it steps in coarse chunks as the battlefield changes (an
order given, the known field changing). The resolver lives in the engine and the HUD reads the results
through the same interface. Plan: docs/PLAN_pathway_and_umwelt_minds.md, Part 2.

This module is the single source of truth for a drop's minds:
  * mind_tables(state, drop)  the plain tables the engine runs (mission.heroMind): roles, clusters,
                              each cluster's bridges with their couplings, every role's start
  * clusters(drop, bonds)     the connected components of the drop's bond graph: a hero with no bond
                              on this drop is a cluster of one
  * domain_spec(tables)       the same mind as an Umwelt DomainSpec, the reference the Lua runtime
                              (va_umwelt_lite.lua) is parity-tested against (tests/test_umwelt_lite_parity.py)

Each hero on the drop is a node. Its roles are dissipative beliefs: nerve and drive (the temper, as it
comes from camp: verdance.company.temper), threat and pain (what the field does to it). A bond between
drop-mates is a bridge with coupling = points / 100, negative for a rivalry (as temper).
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROLES = ("nerve", "drive", "threat", "pain")
TEMPER_ROLES = ("nerve", "drive")   # carried in from camp (temper in [-1, 1] -> belief (t + 1) / 2)
# What a bond carries: mood (nerve, drive), as temper's bridges do. Threat and pain are a hero's own:
# a friend's danger reaches it as a change of heart, not as danger seen.
SHARED_ROLES = TEMPER_ROLES


def clusters(drop: List[str], bonds: Iterable[Tuple[str, str, float]]) -> List[List[str]]:
    """The connected components of the bond graph, each in drop order, in order of their first hero."""
    adj: Dict[str, List[str]] = {h: [] for h in drop}
    for a, b, c in bonds:
        if c and a in adj and b in adj:
            adj[a].append(b)
            adj[b].append(a)
    seen: Dict[str, int] = {}
    out: List[List[str]] = []
    for h in drop:
        if h in seen:
            continue
        comp, q = [], deque([h])
        seen[h] = len(out)
        while q:
            u = q.popleft()
            comp.append(u)
            for v in adj[u]:
                if v not in seen:
                    seen[v] = len(out)
                    q.append(v)
        order = {x: i for i, x in enumerate(drop)}
        out.append(sorted(comp, key=order.__getitem__))
    return out


def mind_tables(state: Dict[str, Any], drop: Iterable[str], workspace: Optional[Path] = None,
                temper: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """mission.heroMind for this drop."""
    from verdance.company.temper import _camp, temper_for_drop
    drop = list(dict.fromkeys(str(h) for h in drop if h))
    if not drop:
        return {}
    _, bonds, _ = _camp(state, drop, workspace)
    if temper is None:
        temper = temper_for_drop(state, drop, workspace)
    out_clusters = []
    for comp in clusters(drop, bonds):
        inside = set(comp)
        out_clusters.append({
            "heroes": comp,
            "bridges": [[a, b, round(float(c), 4)] for a, b, c in bonds if a in inside and b in inside and c],
        })
    start: Dict[str, Dict[str, float]] = {}
    for h in drop:
        t = temper.get(h) or {}
        start[h] = {r: round((float(t.get(r, 0.0)) + 1.0) / 2.0, 4) if r in TEMPER_ROLES else 0.5 for r in ROLES}
    return {"roles": list(ROLES), "shared": list(SHARED_ROLES), "clusters": out_clusters, "start": start,
            "umwelt": dict(UMWELT), "holdS": HOLD_S}


# --- Umwelt's own numbers, for the engine's copy ----------------------------------------------------
# On the GameHost path with learning frozen, each role of each node is a Bloch vector that evolves on
# its own (Umwelt a00a0e7; paths under src/umwelt). The Lua runtime takes these from mind_tables, and
# the parity suite fails if Umwelt moves them.
UMWELT = {
    "h": 0.01,              # compute step per ingest (engine.py:99, batched_evolve.py:382)
    "gammaDiss": 5.0,       # dissipative relaxation rate of a node without a param bundle (field.py:98-112)
    "bridgeStrength": 0.5,  # the root bundle's bridge_strength (param_bundles.py:140-153)
    "rObs": 0.95,           # how far an observation pulls toward its pole (SensorBinding r_obs, ingress.py:163)
    "catchupMax": 32,       # catch-up steps a long gap may run (UMWELT_WALL_CATCHUP_MAX default)
}
# The hold: one compute step per ingest_hold_s of quiet (engine.py:1070-1089). The hero doctrine thinks
# every 18 frames (game_verdance_unit_behavior.lua THINK_PERIOD, 0.6 s), so a mind forgets at the pace
# the hero acts: about 14 holds (8 s) to forget half of what it saw.
HOLD_S = 18 / 30


def domain_spec(cluster: Dict[str, Any], start: Dict[str, Dict[str, float]], roles=ROLES, hold_s: float = HOLD_S,
                shared=SHARED_ROLES):
    """One cluster's mind as an Umwelt DomainSpec, and the couplings to set on its bridges. Every role is
    dissipative and observed directly (force_observe: a high reading raises the belief), as temper's are."""
    from umwelt import BindingSpec, BridgeSpec, DomainSpec, NodeSpec
    modes = {r: "dissipative" for r in roles}
    nodes = [NodeSpec("mind", parent=None, kind="root", roles=())]
    for h in cluster["heroes"]:
        prep = {r: (0.0, 0.0, 2.0 * float(start[h][r]) - 1.0) for r in roles}
        nodes.append(NodeSpec(f"hero:{h}", parent="mind", kind="entity", roles=tuple(roles),
                              role_modes=dict(modes), initial_bloch=prep))
    bridges, couplings = [], {}
    for a, b, c in cluster["bridges"]:
        bridges.append(BridgeSpec(f"hero:{a}", f"hero:{b}", shared_roles=tuple(shared), kind="open"))
        couplings[frozenset((f"hero:{a}", f"hero:{b}"))] = float(c)
    norm = {"type": "range", "lo": 0.0, "hi": 1.0}
    bindings = [BindingSpec(f"obs_{h}_{r}", zone=f"hero:{h}", role=r, normalizer=norm, force_observe=True,
                            efficiency=1.0, strength=1.0) for h in cluster["heroes"] for r in roles]
    spec = DomainSpec(name="verdance-hero-mind", nodes=tuple(nodes), bridges=tuple(bridges),
                      bindings=tuple(bindings), ingest_hold_s=hold_s)
    return spec, couplings


def reference_run(cluster: Dict[str, Any], start: Dict[str, Dict[str, float]], script: List[Any],
                  roles=ROLES, hold_s: float = HOLD_S, shared=SHARED_ROLES) -> List[Dict[str, Dict[str, List[float]]]]:
    """Run one cluster's mind on Umwelt itself: the reference the Lua runtime must match.

    script: [[dt_s, [[hero, role, value01, eta], ...]], ...]; an empty list is a heartbeat (a step with
    nothing seen). Returns, after each entry, {hero: {role: [value, confidence]}}.

    For a reproducible run set UMWELT_FP64=1 before Umwelt is imported (a fresh process): learning is
    frozen here (the root's context_learn, as ContextState.forebrain does), because the default host
    draws its learned Hamiltonian from an unseeded generator."""
    from datetime import timedelta
    from umwelt import GameHost
    spec, couplings = domain_spec(cluster, start, roles, hold_s, shared)
    host = GameHost().register_world(spec, population=False)
    host.engine.graph.root.param_bundle.params["context_learn"].value = 0.0
    for br in host.engine.graph.bridges:
        c = couplings.get(frozenset((str(br.source), str(br.target))))
        if c is not None:
            br.coupling_param.value = max(br.coupling_param.lo, min(br.coupling_param.hi, c))
            br.coupling_param.frozen = True
    out = []
    t = host.now
    for dt, seen in script:
        t = t + timedelta(seconds=float(dt))
        readings = {f"obs_{h}_{r}": float(v) for h, r, v, _ in seen}
        conf = {f"obs_{h}_{r}": float(e) for h, r, _, e in seen}
        if readings:
            host.observe_many("field", readings, confidence=conf, t=t)
        else:
            host.step(t=t)
        row = {}
        for h in cluster["heroes"]:
            row[h] = {}
            for r in roles:
                b = host.belief_value(f"hero:{h}", r)
                row[h][r] = [float(b.value), float(b.confidence)]
        out.append(row)
    return out


def _main(argv: List[str]) -> int:
    """python -m verdance.company.hero_mind reference <in.json> <out.json>  (the parity suite's reference)"""
    import json
    if len(argv) != 4 or argv[1] != "reference":
        print(_main.__doc__)
        return 2
    case = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    rows = reference_run(case["cluster"], case["start"], case["script"], tuple(case.get("roles") or ROLES),
                         float(case.get("holdS") or HOLD_S), tuple(case.get("shared") or SHARED_ROLES))
    Path(argv[3]).write_text(json.dumps(rows), encoding="utf-8")
    return 0


__all__ = ["ROLES", "SHARED_ROLES", "UMWELT", "HOLD_S", "clusters", "mind_tables", "domain_spec", "reference_run"]

if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv))
