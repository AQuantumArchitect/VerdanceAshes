#!/usr/bin/env python3
"""Stage 2 — world projector φ_t into molecule axes.

SSOT features: data/story/phi_features.json
Hero molecules: data/story/hero_umwelt.json
Map prior:      data/story/map_umwelt.json (optional blend)

Usage:
  python tools/phi_projector_v1.py features
  python tools/phi_projector_v1.py project --map eye_of_horus --cue heat_ash --cue statics_nearby
  python tools/phi_projector_v1.py fit --map eye_of_horus --cue heat_ash --top 8
  python tools/phi_projector_v1.py face --map eye_of_horus --heroes brakhov,vane,hearth,mira
  python tools/phi_projector_v1.py smoke
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PHI_PATH = ROOT / "data" / "story" / "phi_features.json"
HERO_PATH = ROOT / "data" / "story" / "hero_umwelt.json"
MAP_PATH = ROOT / "data" / "story" / "map_umwelt.json"
FACE_PATH = ROOT / "outbox" / "phi_shadow.latest.json"
SCHEMA = "verdance-phi-shadow/0.1"

sys.path.insert(0, str(ROOT / "tools"))
import map_umwelt_v1 as map_u  # noqa: E402

AXES = map_u.AXES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _round(v: float, n: int = 3) -> float:
    return round(float(v), n)


def load_phi(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or PHI_PATH).read_text(encoding="utf-8-sig"))


def features_by_id(doc: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    doc = doc or load_phi()
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("features") or []:
        if isinstance(row, dict) and row.get("id"):
            out[str(row["id"])] = row
    return out


def zero_phi() -> dict[str, float]:
    return {a: 0.0 for a in AXES}


def project_cues(
    cue_weights: dict[str, float],
    *,
    phi_doc: dict[str, Any] | None = None,
    map_id: str | None = None,
    zone_id: str | None = None,
) -> dict[str, float]:
    """Build φ from weighted feature cues (+ optional mapPressure prior)."""
    phi_doc = phi_doc or load_phi()
    by = features_by_id(phi_doc)
    blend = phi_doc.get("blend") or {}
    fw = float(blend.get("featureWeight", 1.0))
    mw = float(blend.get("mapPressureWeight", 0.35))
    lo, hi = blend.get("clamp") or [-1.0, 1.0]

    acc = zero_phi()
    used: list[dict[str, Any]] = []
    for fid, w in cue_weights.items():
        w = float(w)
        if w == 0.0:
            continue
        feat = by.get(fid)
        if not feat:
            continue
        axes = feat.get("axes") or {}
        for a, av in axes.items():
            if a in acc:
                acc[a] += fw * w * float(av)
        used.append({"id": fid, "weight": _round(w), "label": feat.get("label")})

    if map_id:
        pressure = map_u.pressure_for(map_id, zone_id)
        for a in AXES:
            acc[a] += mw * float(pressure.get(a, 0.0))

    phi = {a: _round(_clamp(acc[a], float(lo), float(hi))) for a in AXES}
    return phi


def beliefs_to_cues(
    beliefs: dict[str, Any],
    *,
    phi_doc: dict[str, Any] | None = None,
    extra: dict[str, float] | None = None,
) -> dict[str, float]:
    """Best-effort BeliefField leaves → cue weights. Unknown = absent."""
    phi_doc = phi_doc or load_phi()
    cues: dict[str, float] = dict(extra or {})
    hooks = ((phi_doc.get("beliefHooks") or {}).get("hooks")) or []

    def leaf_val(name: str) -> tuple[float, float]:
        b = beliefs.get(name) or {}
        if isinstance(b, (list, tuple)) and len(b) >= 2:
            return float(b[0]), float(b[1])
        if isinstance(b, dict):
            return float(b.get("value", 0.5)), float(b.get("confidence", 0.0))
        return 0.5, 0.0

    for hook in hooks:
        leaf = str(hook.get("leaf") or "")
        feat = str(hook.get("feature") or "")
        if not leaf or not feat:
            continue
        v, c = leaf_val(leaf)
        thr = float(hook.get("threshold", 0.5))
        if c < 0.2:
            continue
        if hook.get("when", "high") == "high" and v < thr:
            continue
        if hook.get("when") == "low" and v > thr:
            continue
        scale = float(hook.get("scale", 1.0))
        w = scale * (v if hook.get("weightFrom") == "value" else c)
        cues[feat] = max(float(cues.get(feat, 0.0)), _round(w))
    return cues


def glyph_phi(phi: dict[str, float], n: int = 3) -> str:
    ranked = sorted(phi.items(), key=lambda kv: -abs(kv[1]))
    parts = []
    for a, v in ranked[:n]:
        if abs(v) < 0.08:
            continue
        sign = "+" if v >= 0 else "−"
        parts.append(f"{sign}{a[:3]}")
    return "·".join(parts) if parts else "∅"


def fit(u: dict[str, float], phi: dict[str, float]) -> float:
    return sum(float(u.get(a, 0.0)) * float(phi.get(a, 0.0)) for a in AXES)


def load_heroes() -> dict[str, dict[str, Any]]:
    doc = json.loads(HERO_PATH.read_text(encoding="utf-8-sig"))
    out = {}
    for h in doc.get("heroes") or []:
        if isinstance(h, dict) and h.get("heroId"):
            out[str(h["heroId"])] = h
    return out


def rank_fit(
    phi: dict[str, float],
    *,
    hero_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    heroes = load_heroes()
    ids = hero_ids or list(heroes.keys())
    rows = []
    for hid in ids:
        h = heroes.get(hid)
        if not h:
            continue
        ax = {a: float((h.get("axes") or {}).get(a, 0.0)) for a in AXES}
        score = fit(ax, phi)
        rows.append(
            {
                "heroId": hid,
                "name": h.get("name"),
                "glyph": h.get("glyph"),
                "fit": _round(score),
                "topAxes": _top_pair_axes(ax, phi),
            }
        )
    rows.sort(key=lambda r: -float(r["fit"]))
    return rows


def _top_pair_axes(u: dict[str, float], phi: dict[str, float], n: int = 3) -> list[str]:
    contrib = [(a, float(u.get(a, 0)) * float(phi.get(a, 0))) for a in AXES]
    contrib.sort(key=lambda x: -abs(x[1]))
    out = []
    for a, c in contrib[:n]:
        if abs(c) < 0.05:
            continue
        out.append(f"{a}:{_round(c)}")
    return out


def write_face(doc: dict[str, Any], path: Path | None = None) -> Path:
    out = path or FACE_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def cmd_features(_args: argparse.Namespace) -> int:
    doc = load_phi()
    for f in doc.get("features") or []:
        axes = f.get("axes") or {}
        top = sorted(axes.items(), key=lambda kv: -abs(float(kv[1])))[:3]
        bits = " ".join(f"{a}={float(v):+.2f}" for a, v in top)
        print(f"{f['id']:18} {bits}  — {f.get('label','')}")
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    weights = {c: 1.0 for c in (args.cue or [])}
    for pair in args.weight or []:
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        weights[k.strip()] = float(v)
    phi = project_cues(weights, map_id=args.map or None, zone_id=args.zone or None)
    print(
        json.dumps(
            {
                "phi": phi,
                "glyph": glyph_phi(phi),
                "mapId": args.map or None,
                "cues": weights,
            },
            indent=2,
        )
    )
    return 0


def cmd_fit(args: argparse.Namespace) -> int:
    weights = {c: 1.0 for c in (args.cue or [])}
    phi = project_cues(weights, map_id=args.map or None, zone_id=args.zone or None)
    ranked = rank_fit(phi)
    print(f"φ {glyph_phi(phi)}  map={args.map or '-'} cues={list(weights)}")
    for r in ranked[: max(1, args.top)]:
        print(f"  {r['fit']:+.3f}  {r['heroId']:12}  {r.get('glyph','')}  {r['topAxes']}")
    return 0


def cmd_face(args: argparse.Namespace) -> int:
    weights = {c: 1.0 for c in (args.cue or [])}
    phi = project_cues(weights, map_id=args.map or None, zone_id=args.zone or None)
    hero_ids = [h.strip() for h in (args.heroes or "").split(",") if h.strip()] or None
    ranked = rank_fit(phi, hero_ids=hero_ids)
    doc = {
        "schemaVersion": SCHEMA,
        "mode": "shadow",
        "liveCombat": False,
        "generatedAt": _now_iso(),
        "mapId": args.map or None,
        "zoneId": args.zone or None,
        "cues": weights,
        "phi": phi,
        "phiGlyph": glyph_phi(phi),
        "topAxes": [
            {"axis": a, "value": phi[a]}
            for a, _ in sorted(phi.items(), key=lambda kv: -abs(kv[1]))[:5]
            if abs(phi[a]) >= 0.08
        ],
        "heroFits": ranked[: max(1, args.top)],
    }
    path = write_face(doc)
    print(f"Wrote {path}")
    print(f"φ {doc['phiGlyph']}  top fits: " + ", ".join(f"{r['heroId']}={r['fit']:+.2f}" for r in ranked[:5]))
    return 0


def cmd_smoke(_args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool]] = []
    doc = load_phi()
    checks.append(("features_loaded", len(doc.get("features") or []) >= 10))

    # Eye of Horus + heat → kiln/mira high fit
    phi = project_cues({"heat_ash": 1.0, "statics_nearby": 0.8}, map_id="eye_of_horus")
    ranked = rank_fit(phi)
    top_ids = [r["heroId"] for r in ranked[:5]]
    checks.append(("kiln_heat_fit", "brakhov" in top_ids or "mira" in top_ids))
    checks.append(("phi_nonzero", any(abs(v) > 0.1 for v in phi.values())))

    # Greenest + craft → hearth/lumen/solarium
    phi2 = project_cues({"energy_surplus": 1.0, "craft_opportunity": 0.9}, map_id="greenest_fields")
    ranked2 = rank_fit(phi2)
    eco = {r["heroId"] for r in ranked2[:6]}
    checks.append(("eco_fit", bool(eco & {"hearth", "lumen", "solarium", "twitch"})))

    # Belief hooks
    cues = beliefs_to_cues(
        {
            "threat": {"value": 0.8, "confidence": 0.7},
            "craft": {"value": 0.2, "confidence": 0.1},
        }
    )
    checks.append(("belief_threat_cue", cues.get("threat_envelope", 0) > 0.5))

    face = {
        "schemaVersion": SCHEMA,
        "mode": "shadow",
        "liveCombat": False,
        "generatedAt": _now_iso(),
        "smoke": True,
        "phi": phi,
        "phiGlyph": glyph_phi(phi),
        "heroFits": ranked[:8],
    }
    path = write_face(face)
    checks.append(("face_written", path.is_file()))

    ok = all(v for _, v in checks)
    print(json.dumps({"ok": ok, "checks": dict(checks), "path": str(path)}, indent=2))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage 2 φ projector (shadow)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("features", help="List feature → axis rows")
    sub.add_parser("smoke", help="Assert heat/eco fits + write face")

    pp = sub.add_parser("project", help="Project cues (+map) → φ")
    pp.add_argument("--map", default="")
    pp.add_argument("--zone", default="")
    pp.add_argument("--cue", action="append", default=[])
    pp.add_argument("--weight", action="append", default=[], help="id=weight")

    pf = sub.add_parser("fit", help="Rank heroes by ⟨u,φ⟩")
    pf.add_argument("--map", default="")
    pf.add_argument("--zone", default="")
    pf.add_argument("--cue", action="append", default=[])
    pf.add_argument("--top", type=int, default=8)

    pface = sub.add_parser("face", help="Write outbox/phi_shadow.latest.json")
    pface.add_argument("--map", default="")
    pface.add_argument("--zone", default="")
    pface.add_argument("--cue", action="append", default=[])
    pface.add_argument("--heroes", default="", help="comma heroIds (default all)")
    pface.add_argument("--top", type=int, default=12)

    args = p.parse_args(argv)
    if args.cmd == "features":
        return cmd_features(args)
    if args.cmd == "project":
        return cmd_project(args)
    if args.cmd == "fit":
        return cmd_fit(args)
    if args.cmd == "face":
        return cmd_face(args)
    if args.cmd == "smoke":
        return cmd_smoke(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
