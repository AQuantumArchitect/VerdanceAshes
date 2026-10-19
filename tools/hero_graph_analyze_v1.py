#!/usr/bin/env python3
"""Analytical assessments on the Verdance hero umwelt + support web.

Reads:
  data/story/hero_umwelt.json
  data/story/support_web.json

Writes (optional):
  outbox/hero_graph_analysis.json

Usage:
  python tools/hero_graph_analyze_v1.py
  python tools/hero_graph_analyze_v1.py --json
  python tools/hero_graph_analyze_v1.py --write
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "data" / "story"
OUT = ROOT / "outbox" / "hero_graph_analysis.json"

AXES_DEFAULT = [
    "energy",
    "offense",
    "mobility",
    "sight",
    "pad",
    "craft",
    "heat",
    "fog",
    "sky",
    "ledger",
]

# Synthetic archetype pressures (kept for offline geometry). Live seven-map
# pressures load from data/story/map_umwelt.json when present.
MAP_PRESSURES = {
    "pad_fortress": {"pad": 1.0, "offense": 0.4, "mobility": -0.6, "energy": 0.2},
    "fog_siege": {"fog": 1.0, "sight": 0.6, "offense": 0.3, "energy": -0.2},
    "sky_raid": {"sky": 0.8, "mobility": 1.0, "pad": -0.5, "sight": 0.4},
    "kiln_heat": {"heat": 1.0, "offense": 0.8, "energy": -0.8, "mobility": -0.5},
    "hearth_eco": {"energy": 1.0, "craft": 0.6, "pad": 0.5, "offense": -0.5},
    "ledger_raid": {"ledger": 1.0, "mobility": 0.4, "fog": 0.3, "pad": -0.2},
}


def _live_map_pressures() -> dict[str, dict[str, float]]:
    try:
        from map_umwelt_v1 import load_map_umwelt, maps_by_id  # noqa: WPS433

        doc = load_map_umwelt()
        out: dict[str, dict[str, float]] = {}
        for mid, row in maps_by_id(doc).items():
            out[mid] = {
                a: float((row.get("mapPressure") or {}).get(a, 0.0)) for a in AXES_DEFAULT
            }
        return out
    except Exception:  # noqa: BLE001
        return {}


def _dot(u, v):
    return sum(a * b for a, b in zip(u, v))


def _norm(u):
    return math.sqrt(sum(a * a for a in u)) or 1e-9


def _cos(u, v):
    return _dot(u, v) / (_norm(u) * _norm(v))


def _complement(u, v):
    return sum(-a * b for a, b in zip(u, v) if a * b < 0)


def _matvec(M, v):
    return [sum(M[i][j] * v[j] for j in range(len(v))) for i in range(len(M))]


def _power_pc(M, iters=80):
    v = [1.0] * len(M)
    for _ in range(iters):
        w = _matvec(M, v)
        nrm = _norm(w) or 1.0
        v = [x / nrm for x in w]
    lam = _dot(v, _matvec(M, v))
    return lam, v


def analyze(umwelt: dict, web: dict) -> dict:
    axes = umwelt.get("axes") or AXES_DEFAULT
    heroes = {h["heroId"]: h for h in umwelt["heroes"]}
    edges = web.get("edges") or []
    ids = sorted(heroes)

    X = [[float(heroes[hid]["axes"].get(a, 0.0)) for a in axes] for hid in ids]

    pairs = []
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if j <= i:
                continue
            ua, ub = X[i], X[j]
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "cos": _cos(ua, ub),
                    "complement": _complement(ua, ub),
                    "l1": sum(abs(x - y) for x, y in zip(ua, ub)),
                    "energy_prod": float(heroes[a]["axes"].get("energy", 0))
                    * float(heroes[b]["axes"].get("energy", 0)),
                }
            )

    n, d = len(X), len(axes)
    means = [sum(row[k] for row in X) / n for k in range(d)]
    Xc = [[row[k] - means[k] for k in range(d)] for row in X]
    C = [[0.0] * d for _ in range(d)]
    for row in Xc:
        for i in range(d):
            for j in range(d):
                C[i][j] += row[i] * row[j]
    for i in range(d):
        for j in range(d):
            C[i][j] /= max(1, n - 1)

    pcs = []
    M = [row[:] for row in C]
    for k in range(3):
        lam, v = _power_pc(M)
        order = sorted(range(d), key=lambda i: -abs(v[i]))
        pcs.append(
            {
                "id": f"PC{k + 1}",
                "lambda": lam,
                "loadings": {axes[i]: v[i] for i in order},
                "top": [(axes[i], v[i]) for i in order[:5]],
            }
        )
        for i in range(d):
            for j in range(d):
                M[i][j] -= lam * v[i] * v[j]

    v1 = [pcs[0]["loadings"][a] for a in axes]
    v2 = [pcs[1]["loadings"][a] for a in axes]
    projections = []
    for hid, row in zip(ids, Xc):
        projections.append(
            {
                "heroId": hid,
                "pc1": _dot(row, v1),
                "pc2": _dot(row, v2),
                "glyph": heroes[hid].get("glyph"),
                "position": heroes[hid].get("position"),
                "doctrine": heroes[hid].get("doctrine"),
            }
        )

    adj: dict[str, list[str]] = defaultdict(list)
    edge_rows = []
    for e in edges:
        a, b = e.get("a"), e.get("b")
        if not a or not b:
            continue
        adj[a].append(b)
        adj[b].append(a)
        edge_rows.append(
            {
                "a": a,
                "b": b,
                "score": e.get("score"),
                "polarity": e.get("polarity"),
                "motifs": e.get("motifs"),
                "authored": bool(e.get("authored")),
                "umwelt": e.get("umwelt"),
            }
        )

    degree = {h: len(set(adj[h])) for h in ids}
    isolates = [h for h in ids if degree.get(h, 0) == 0]
    polarity_counts = Counter(str(e.get("polarity")) for e in edge_rows)

    edge_set = {tuple(sorted((e["a"], e["b"]))) for e in edge_rows}
    complement_gaps = []
    for p in sorted(pairs, key=lambda d: -d["complement"]):
        if p["complement"] < 0.8:
            break
        if tuple(sorted((p["a"], p["b"]))) not in edge_set:
            complement_gaps.append(p)

    mirror_gaps = []
    for p in sorted(pairs, key=lambda d: -d["cos"]):
        if p["cos"] < 0.85:
            break
        if tuple(sorted((p["a"], p["b"]))) not in edge_set:
            mirror_gaps.append(p)

    clones = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            aa, bb = heroes[a]["axes"], heroes[b]["axes"]
            if all(abs(float(aa[k]) - float(bb[k])) < 0.05 for k in axes):
                clones.append({"a": a, "b": b, "glyph": heroes[a].get("glyph")})

    map_fit = {}
    pressures = dict(MAP_PRESSURES)
    pressures.update(_live_map_pressures())
    for mname, pressure in pressures.items():
        scored = []
        for hid in ids:
            ax = heroes[hid]["axes"]
            s = sum(float(ax.get(k, 0.0)) * float(v) for k, v in pressure.items())
            scored.append({"heroId": hid, "score": s})
        scored.sort(key=lambda d: -d["score"])
        map_fit[mname] = {"top": scored[:5], "bottom": scored[-3:]}

    coverage = {}
    for a in axes:
        strong = [h for h in ids if abs(float(heroes[h]["axes"].get(a, 0))) >= 0.5]
        coverage[a] = {
            "n": len(strong),
            "pos": [h for h in strong if float(heroes[h]["axes"][a]) > 0],
            "neg": [h for h in strong if float(heroes[h]["axes"][a]) < 0],
        }

    # mobility/pad cross edges (kite vs hold)
    def role(hid):
        ax = heroes[hid]["axes"]
        return float(ax.get("mobility", 0)) - float(ax.get("pad", 0))

    cross = []
    for e in edge_rows:
        ra, rb = role(e["a"]), role(e["b"])
        if ra * rb < 0 and abs(ra) > 0.5 and abs(rb) > 0.5:
            cross.append(
                {
                    "a": e["a"],
                    "b": e["b"],
                    "ra": ra,
                    "rb": rb,
                    "polarity": e["polarity"],
                    "motifs": e["motifs"],
                }
            )

    energy_bonds = [
        e
        for e in edge_rows
        if (e.get("umwelt") or {}).get("motif") == "supply meets hunger"
        or any(
            c.get("axis") == "energy" and c.get("kind") == "complement"
            for c in ((e.get("umwelt") or {}).get("couples") or [])
        )
    ]

    return {
        "schemaVersion": "verdance-hero-graph-analysis/1.0",
        "heroCount": len(ids),
        "edgeCount": len(edge_rows),
        "axes": axes,
        "pca": pcs,
        "projections": projections,
        "topCosine": sorted(pairs, key=lambda d: -d["cos"])[:15],
        "topComplement": sorted(pairs, key=lambda d: -d["complement"])[:15],
        "antiMirror": sorted(pairs, key=lambda d: d["cos"])[:12],
        "degree": degree,
        "isolates": isolates,
        "polarityCounts": dict(polarity_counts),
        "complementGaps": complement_gaps[:20],
        "mirrorGaps": mirror_gaps[:20],
        "clones": clones,
        "mapFit": map_fit,
        "axisCoverage": coverage,
        "mobilityPadCrossEdges": cross,
        "energyComplementEdges": [
            {
                "a": e["a"],
                "b": e["b"],
                "score": e["score"],
                "polarity": e["polarity"],
                "motif": (e.get("umwelt") or {}).get("motif"),
            }
            for e in energy_bonds
        ],
        "authoredEdgeCount": sum(1 for e in edge_rows if e.get("authored")),
        "notes": [
            "PC1 ≈ mobility↔pad (kite vs hold).",
            "PC2 ≈ offense↔energy/craft (push vs refuse / kiln vs hearth).",
            "PC3 ≈ fog/sight vs craft (recon/siege vs eco).",
            "Degree cap (maxDegree=5) flattens communities; gaps are often capacity, not absence of chemistry.",
            "Hero×map fit is the classical limit — same shape as eco-manifold candidate ranking under map state.",
        ],
    }


def print_report(rep: dict) -> None:
    print(f"heroes={rep['heroCount']} edges={rep['edgeCount']}")
    print("\n=== PCA ===")
    for pc in rep["pca"]:
        top = ", ".join(f"{a}:{v:+.2f}" for a, v in pc["top"])
        print(f"{pc['id']} λ={pc['lambda']:.3f}  {top}")

    print("\n=== PC1 extremes ===")
    proj = sorted(rep["projections"], key=lambda d: d["pc1"])
    for row in proj[:5]:
        print(f"  low  {row['heroId']:12} {row['pc1']:+.2f}  {row['glyph']}")
    for row in proj[-5:]:
        print(f"  high {row['heroId']:12} {row['pc1']:+.2f}  {row['glyph']}")

    print("\n=== top complement ===")
    for p in rep["topComplement"][:8]:
        print(f"  {p['a']:12} ↔ {p['b']:12}  comp={p['complement']:+.3f} cos={p['cos']:+.3f}")

    print("\n=== energy complement edges (cultivated) ===")
    for e in rep["energyComplementEdges"][:10]:
        print(f"  {e['a']}↔{e['b']}  {e['polarity']}  {e['motif']}  score={e['score']}")

    print("\n=== isolates / clones / gaps ===")
    print("  isolates:", rep["isolates"])
    print("  clones:", rep["clones"])
    print(f"  complement gaps (top): {len(rep['complementGaps'])}")
    for p in rep["complementGaps"][:6]:
        print(f"    {p['a']}↔{p['b']} comp={p['complement']:+.3f}")

    print("\n=== hero × map fit ===")
    for mname, block in rep["mapFit"].items():
        top = ", ".join(f"{r['heroId']}:{r['score']:.2f}" for r in block["top"][:4])
        print(f"  {mname:12} {top}")

    print("\n=== axis coverage (|v|>=0.5) ===")
    for a, block in rep["axisCoverage"].items():
        print(f"  {a:10} n={block['n']:2}  +{len(block['pos'])} -{len(block['neg'])}")

    print("\nnotes:")
    for n in rep["notes"]:
        print(" -", n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print full JSON to stdout")
    ap.add_argument("--write", action="store_true", help=f"write {OUT}")
    args = ap.parse_args()

    umwelt = json.loads((STORY / "hero_umwelt.json").read_text(encoding="utf-8"))
    web = json.loads((STORY / "support_web.json").read_text(encoding="utf-8"))
    rep = analyze(umwelt, web)

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"wrote {OUT}")

    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
