#!/usr/bin/env python3
"""Stage 3 — shadow IntentResolver parallel brain.

score(intent) ≈ ⟨u, φ⟩ · g(b, η) · D(u)   (A=1 until Stage 5)

Compares shadow-preferred intent to a Python port of live IntentResolver.resolve
under hand doctrine. Shadow only — no live combat.

Usage:
  python tools/shadow_intent_v1.py scenarios
  python tools/shadow_intent_v1.py run
  python tools/shadow_intent_v1.py metrics
  python tools/shadow_intent_v1.py smoke
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_FACE = ROOT / "outbox" / "shadow_intent.latest.json"
OUT_METRICS = ROOT / "outbox" / "shadow_intent_metrics.json"
SCHEMA = "verdance-shadow-intent/0.1"

sys.path.insert(0, str(ROOT / "tools"))
import molecule_doctrine_v1 as mol  # noqa: E402
import phi_projector_v1 as phi_mod  # noqa: E402

AXES = mol.AXES
INTENTS = ("bail", "kite", "craft", "push", "hold")

# Mirrored from va_intent_resolver.lua ENTER/LEAVE/orders gates
ENTER = {"bail": 0.55, "kite": 0.52, "craft": 0.48, "push": 0.60}
LEAVE = {"bail": 0.32, "kite": 0.32, "craft": 0.28, "push": 0.35}
MIN_CONF = 0.28
COMMIT_CONF = 0.45
ORDERS_SOFT_BLOCK = 0.58
ORDERS_SOFT_CONF = 0.18
HARD_THREAT = 0.78
HARD_THREAT_CONF = 0.45


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _round(v: float, n: int = 3) -> float:
    return round(float(v), n)


def _leaf(beliefs: dict[str, Any], role: str) -> tuple[float, float]:
    b = beliefs.get(role) or {}
    if isinstance(b, (list, tuple)) and len(b) >= 2:
        return float(b[0]), float(b[1])
    if isinstance(b, dict):
        return float(b.get("value", 0.5)), float(b.get("confidence", 0.0))
    return 0.5, 0.0


def live_resolve(
    beliefs: dict[str, Any],
    doctrine: dict[str, Any],
    prev_intent: str = "hold",
    can_craft: bool = False,
) -> str:
    """Python port of va_intent_resolver.lua M.resolve — hand/live brain."""
    doctrine = doctrine or {}
    prev = prev_intent or "hold"
    orders_v, orders_c = _leaf(beliefs, "orders")
    threat_v, threat_c = _leaf(beliefs, "threat")
    pain_v, pain_c = _leaf(beliefs, "pain")
    craft_v, craft_c = _leaf(beliefs, "craft")
    hold_v, _ = _leaf(beliefs, "hold")
    pressure_v, _ = _leaf(beliefs, "pressure")

    kite_bias = float(doctrine.get("kiteBias", 0.6))
    bail_bias = float(doctrine.get("bailBias", 0.7))
    craft_bias = float(doctrine.get("craftBias", 0.3))
    push_bias = float(doctrine.get("pushBias", 0.5))
    squad = str(doctrine.get("squad") or "frontline")
    allow_bail = doctrine.get("allowBail")
    if allow_bail is None:
        allow_bail = True
    allow_kite = doctrine.get("allowKite")
    if allow_kite is None:
        allow_kite = True

    orders_block = orders_v >= ORDERS_SOFT_BLOCK and orders_c >= ORDERS_SOFT_CONF
    hard_danger = threat_v >= HARD_THREAT and threat_c >= HARD_THREAT_CONF

    def still(intent: str, value: float, leave: float) -> bool:
        return prev == intent and value >= leave

    if allow_bail:
        bail_score = pain_v * bail_bias
        if pain_c >= MIN_CONF:
            if still("bail", bail_score, LEAVE["bail"]) or bail_score >= ENTER["bail"]:
                if (not orders_block) or bail_score >= 0.85 or hard_danger:
                    return "bail"

    if allow_kite and kite_bias >= 0.12:
        kite_score = max(threat_v, pressure_v * 0.85) * kite_bias
        if threat_c >= MIN_CONF or still("kite", kite_score, LEAVE["kite"]):
            if still("kite", kite_score, LEAVE["kite"]) or kite_score >= ENTER["kite"]:
                if hard_danger or (not orders_block):
                    return "kite"

    if can_craft and craft_bias >= 0.4:
        craft_score = craft_v * craft_bias
        if craft_c >= MIN_CONF or still("craft", craft_score, LEAVE["craft"]):
            if still("craft", craft_score, LEAVE["craft"]) or craft_score >= ENTER["craft"]:
                if not hard_danger:
                    return "craft"

    if squad in ("skirm", "frontline", "siege"):
        engage = (1 - threat_v) * 0.5 + (1 - pain_v) * 0.5
        if squad == "siege":
            engage = 0.55 + (1 - pain_v) * 0.45
        push_score = engage * push_bias * (1 - orders_v * 0.35)
        if threat_c < COMMIT_CONF and squad == "skirm":
            if hold_v >= 0.45 or orders_block:
                return "hold"
        pain_gate = 0.92 if squad == "siege" else 0.45
        if (
            still("push", push_score, LEAVE["push"]) or push_score >= ENTER["push"]
        ) and (not orders_block) and pain_v < pain_gate:
            return "push"

    if orders_block or hold_v >= 0.4 or squad in ("soak", "frontline", "backline"):
        return "hold"
    return "hold"


def g_belief(intent: str, beliefs: dict[str, Any]) -> float:
    """η-aware belief gate in [0.35, 1.35] — colors score, does not replace D(u)."""
    threat_v, threat_c = _leaf(beliefs, "threat")
    pain_v, pain_c = _leaf(beliefs, "pain")
    craft_v, craft_c = _leaf(beliefs, "craft")
    hold_v, hold_c = _leaf(beliefs, "hold")
    pressure_v, pressure_c = _leaf(beliefs, "pressure")
    orders_v, orders_c = _leaf(beliefs, "orders")

    if intent == "bail":
        return 0.45 + 0.9 * pain_v * max(pain_c, 0.25)
    if intent == "kite":
        env = max(threat_v, pressure_v * 0.85)
        return 0.45 + 0.85 * env * max(threat_c, pressure_c, 0.2)
    if intent == "craft":
        return 0.4 + 0.9 * craft_v * max(craft_c, 0.2)
    if intent == "push":
        engage = (1 - threat_v) * 0.5 + (1 - pain_v) * 0.5
        return 0.4 + 0.85 * engage * (1 - 0.35 * orders_v * max(orders_c, 0.15))
    # hold
    return 0.5 + 0.5 * hold_v * max(hold_c, 0.15) + 0.25 * orders_v * max(orders_c, 0.1)


def shadow_scores(
    u: dict[str, float],
    phi: dict[str, float],
    beliefs: dict[str, Any],
    doctrine: dict[str, Any],
    *,
    can_craft: bool = False,
    A: float = 1.0,
) -> dict[str, float]:
    """score(intent) ≈ ⟨u,φ⟩ · g(b,η) · D(u) · A."""
    fit = phi_mod.fit(u, phi)
    # Fit colors: positive fit boosts character-aligned intents via D biases already.
    # Soft fit multiplier shared, then per-intent D knobs.
    fit_mult = 1.0 + 0.22 * max(-1.5, min(1.5, fit))

    kite_b = float(doctrine.get("kiteBias", 0.6))
    bail_b = float(doctrine.get("bailBias", 0.7))
    craft_b = float(doctrine.get("craftBias", 0.3))
    push_b = float(doctrine.get("pushBias", 0.5))
    allow_bail = doctrine.get("allowBail", True)
    allow_kite = doctrine.get("allowKite", True)
    if allow_bail is None:
        allow_bail = True
    if allow_kite is None:
        allow_kite = True

    # Intent temperament pull from molecule×φ contribution axes
    mob_pull = float(u.get("mobility", 0)) * float(phi.get("mobility", 0))
    pad_pull = float(u.get("pad", 0)) * float(phi.get("pad", 0))
    off_pull = float(u.get("offense", 0)) * float(phi.get("offense", 0))
    craft_pull = float(u.get("craft", 0)) * float(phi.get("craft", 0))
    heat_pull = float(u.get("heat", 0)) * float(phi.get("heat", 0))

    scores: dict[str, float] = {}
    # base D(u) · g(b) · fit · A, plus small axis pulls
    scores["bail"] = (
        bail_b * g_belief("bail", beliefs) * (0.85 + 0.1 * fit_mult) * A
        if allow_bail
        else -1.0
    )
    scores["kite"] = (
        kite_b * g_belief("kite", beliefs) * fit_mult * A * (1.0 + 0.15 * mob_pull - 0.1 * pad_pull)
        if allow_kite and kite_b >= 0.12
        else -1.0
    )
    scores["craft"] = (
        craft_b * g_belief("craft", beliefs) * fit_mult * A * (1.0 + 0.2 * craft_pull)
        if can_craft and craft_b >= 0.35
        else -1.0
    )
    scores["push"] = (
        push_b
        * g_belief("push", beliefs)
        * fit_mult
        * A
        * (1.0 + 0.18 * off_pull + 0.12 * heat_pull - 0.08 * pad_pull)
    )
    scores["hold"] = (
        0.55
        * g_belief("hold", beliefs)
        * (1.0 + 0.12 * pad_pull + 0.08 * float(u.get("energy", 0)) * float(phi.get("energy", 0)))
        * A
    )

    # Soft-block under strong orders: damp kite/bail/push unless hard pain/threat
    orders_v, orders_c = _leaf(beliefs, "orders")
    threat_v, threat_c = _leaf(beliefs, "threat")
    pain_v, _ = _leaf(beliefs, "pain")
    if orders_v >= ORDERS_SOFT_BLOCK and orders_c >= ORDERS_SOFT_CONF:
        hard = threat_v >= HARD_THREAT and threat_c >= HARD_THREAT_CONF
        if not hard and pain_v < 0.85:
            for k in ("kite", "push", "bail"):
                if scores[k] > 0:
                    scores[k] *= 0.45
            scores["hold"] *= 1.25

    return {k: _round(v) for k, v in scores.items()}


def shadow_preferred(scores: dict[str, float]) -> str:
    valid = [(k, v) for k, v in scores.items() if v >= 0]
    if not valid:
        return "hold"
    valid.sort(key=lambda kv: -kv[1])
    return valid[0][0]


def build_scenarios() -> list[dict[str, Any]]:
    """Canned Drop micro-situations for agreement metrics."""
    heroes = ["vane", "brakhov", "hearth", "mira", "ketha", "anvil", "yeva", "fatboy", "warder", "volt"]
    situations = [
        {
            "id": "under_fire",
            "mapId": "all_that_simmers",
            "cues": {"threat_envelope": 0.9, "open_kite_room": 0.5},
            "beliefs": {
                "orders": {"value": 0.4, "confidence": 0.3},
                "threat": {"value": 0.78, "confidence": 0.7},
                "pain": {"value": 0.35, "confidence": 0.5},
                "craft": {"value": 0.3, "confidence": 0.2},
                "hold": {"value": 0.3, "confidence": 0.2},
                "pressure": {"value": 0.6, "confidence": 0.5},
            },
            "canCraft": False,
            "prev": "hold",
        },
        {
            "id": "dying",
            "mapId": "all_that_simmers",
            "cues": {"threat_envelope": 1.0},
            "beliefs": {
                "orders": {"value": 0.3, "confidence": 0.2},
                "threat": {"value": 0.7, "confidence": 0.6},
                "pain": {"value": 0.85, "confidence": 0.8},
                "craft": {"value": 0.2, "confidence": 0.1},
                "hold": {"value": 0.2, "confidence": 0.1},
                "pressure": {"value": 0.5, "confidence": 0.4},
            },
            "canCraft": False,
            "prev": "kite",
        },
        {
            "id": "kiln_heat_push",
            "mapId": "eye_of_horus",
            "cues": {"heat_ash": 1.0, "statics_nearby": 0.9, "siege_line": 0.7},
            "beliefs": {
                "orders": {"value": 0.35, "confidence": 0.3},
                "threat": {"value": 0.4, "confidence": 0.5},
                "pain": {"value": 0.35, "confidence": 0.4},
                "craft": {"value": 0.1, "confidence": 0.1},
                "hold": {"value": 0.25, "confidence": 0.2},
                "pressure": {"value": 0.45, "confidence": 0.4},
            },
            "canCraft": False,
            "prev": "hold",
        },
        {
            "id": "hearth_craft",
            "mapId": "greenest_fields",
            "cues": {"energy_surplus": 1.0, "craft_opportunity": 1.0, "pad_owned": 0.6},
            "beliefs": {
                "orders": {"value": 0.4, "confidence": 0.3},
                "threat": {"value": 0.25, "confidence": 0.4},
                "pain": {"value": 0.15, "confidence": 0.3},
                "craft": {"value": 0.85, "confidence": 0.75},
                "hold": {"value": 0.55, "confidence": 0.5},
                "pressure": {"value": 0.2, "confidence": 0.2},
            },
            "canCraft": True,
            "prev": "hold",
        },
        {
            "id": "orders_hold",
            "mapId": "ancient_bastion",
            "cues": {"pad_contested": 0.7, "statics_nearby": 0.5},
            "beliefs": {
                "orders": {"value": 0.9, "confidence": 0.85},
                "threat": {"value": 0.45, "confidence": 0.5},
                "pain": {"value": 0.2, "confidence": 0.3},
                "craft": {"value": 0.3, "confidence": 0.2},
                "hold": {"value": 0.7, "confidence": 0.6},
                "pressure": {"value": 0.4, "confidence": 0.4},
            },
            "canCraft": False,
            "prev": "hold",
        },
        {
            "id": "scout_screen",
            "mapId": "the_rock_jungle",
            "cues": {"scout_screen": 1.0, "jammer_radar": 0.8, "open_kite_room": 0.4},
            "beliefs": {
                "orders": {"value": 0.35, "confidence": 0.25},
                "threat": {"value": 0.55, "confidence": 0.55},
                "pain": {"value": 0.2, "confidence": 0.3},
                "craft": {"value": 0.15, "confidence": 0.1},
                "hold": {"value": 0.25, "confidence": 0.2},
                "pressure": {"value": 0.5, "confidence": 0.45},
            },
            "canCraft": False,
            "prev": "hold",
        },
        {
            "id": "arty_backline",
            "mapId": "eye_of_horus",
            "cues": {"heat_ash": 0.7, "statics_nearby": 0.6, "open_kite_room": 0.5},
            "beliefs": {
                "orders": {"value": 0.3, "confidence": 0.2},
                "threat": {"value": 0.65, "confidence": 0.6},
                "pain": {"value": 0.25, "confidence": 0.4},
                "craft": {"value": 0.1, "confidence": 0.1},
                "hold": {"value": 0.35, "confidence": 0.3},
                "pressure": {"value": 0.55, "confidence": 0.5},
            },
            "canCraft": False,
            "prev": "hold",
        },
    ]
    # Craft heroes override for hearth scenario
    craft_heroes = {"hearth", "ketha", "solarium", "consul", "twitch", "lumen"}
    rows = []
    for sit in situations:
        for hid in heroes:
            can = sit["canCraft"] or hid in craft_heroes and sit["id"] == "hearth_craft"
            if sit["id"] == "hearth_craft":
                can = hid in craft_heroes
            rows.append({**sit, "heroId": hid, "canCraft": can})
    return rows


def run_pair(
    hero_id: str,
    *,
    map_id: str,
    cues: dict[str, float],
    beliefs: dict[str, Any],
    can_craft: bool = False,
    prev: str = "hold",
    umwelt: dict[str, Any] | None = None,
    codex: dict[str, Any] | None = None,
) -> dict[str, Any]:
    umwelt = umwelt or mol.load_umwelt()
    codex = codex or mol.load_codex()
    by_hero = {
        str(h["heroId"]): h
        for h in (umwelt.get("heroes") or [])
        if isinstance(h, dict) and h.get("heroId")
    }
    by_codex = {
        str(h["heroId"]): h
        for h in (codex.get("heroes") or [])
        if isinstance(h, dict) and h.get("heroId")
    }
    h = by_hero.get(hero_id)
    if not h:
        return {"ok": False, "error": f"unknown hero {hero_id}"}
    u = mol.axes_of(h)
    hand = mol.hand_for_hero(by_codex.get(hero_id))
    naive = mol.derive_naive(u)
    D = mol.apply_codex_gates(naive, hand)
    # Shadow doctrine for scoring: gated D biases + hand squad
    shadow_doc = {
        "kind": hand["kind"],
        "squad": hand["squad"],
        "kiteBias": D["kiteBias"],
        "bailBias": D["bailBias"],
        "craftBias": D["craftBias"],
        "pushBias": D["pushBias"],
        "preferDefenses": D["preferDefenses"],
        "allowBail": D["allowBail"],
        "allowKite": D["allowKite"],
        "flock": naive.get("flock", False),
    }
    phi = phi_mod.project_cues(cues, map_id=map_id)
    fit = _round(phi_mod.fit(u, phi))
    scores = shadow_scores(u, phi, beliefs, shadow_doc, can_craft=can_craft)
    shadow_intent = shadow_preferred(scores)
    live_intent = live_resolve(beliefs, hand, prev, can_craft)
    return {
        "ok": True,
        "heroId": hero_id,
        "doctrine": hand["kind"],
        "glyph": h.get("glyph"),
        "mapId": map_id,
        "phiGlyph": phi_mod.glyph_phi(phi),
        "fit": fit,
        "liveIntent": live_intent,
        "shadowIntent": shadow_intent,
        "agree": live_intent == shadow_intent,
        "scores": scores,
        "handBiases": {
            k: hand[k] for k in ("kiteBias", "bailBias", "craftBias", "pushBias")
        },
        "shadowBiases": {
            k: shadow_doc[k] for k in ("kiteBias", "bailBias", "craftBias", "pushBias")
        },
    }


def run_all() -> dict[str, Any]:
    umwelt = mol.load_umwelt()
    codex = mol.load_codex()
    scenarios = build_scenarios()
    rows = []
    for sit in scenarios:
        r = run_pair(
            sit["heroId"],
            map_id=sit["mapId"],
            cues=sit["cues"],
            beliefs=sit["beliefs"],
            can_craft=sit["canCraft"],
            prev=sit.get("prev", "hold"),
            umwelt=umwelt,
            codex=codex,
        )
        r["scenarioId"] = sit["id"]
        rows.append(r)

    agree_n = sum(1 for r in rows if r.get("agree"))
    total = len(rows)
    by_hero: dict[str, dict[str, int]] = {}
    by_doc: dict[str, dict[str, int]] = {}
    by_sit: dict[str, dict[str, int]] = {}
    disagreements = []
    for r in rows:
        hid = r["heroId"]
        kind = r.get("doctrine") or "?"
        sid = r.get("scenarioId") or "?"
        for bag, key in ((by_hero, hid), (by_doc, kind), (by_sit, sid)):
            bag.setdefault(key, {"agree": 0, "total": 0})
            bag[key]["total"] += 1
            if r.get("agree"):
                bag[key]["agree"] += 1
        if not r.get("agree"):
            disagreements.append(
                {
                    "scenarioId": sid,
                    "heroId": hid,
                    "doctrine": kind,
                    "live": r.get("liveIntent"),
                    "shadow": r.get("shadowIntent"),
                    "fit": r.get("fit"),
                    "scores": r.get("scores"),
                }
            )

    def pct(bag: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        out = []
        for k, v in bag.items():
            out.append(
                {
                    "key": k,
                    "agree": v["agree"],
                    "total": v["total"],
                    "pct": _round(100.0 * v["agree"] / max(1, v["total"]), 1),
                }
            )
        out.sort(key=lambda x: (x["pct"], -x["total"]))
        return out

    return {
        "schemaVersion": SCHEMA,
        "mode": "shadow",
        "liveCombat": False,
        "generatedAt": _now_iso(),
        "formula": "score(intent) ≈ ⟨u,φ⟩ · g(b,η) · D(u) · A(=1)",
        "total": total,
        "agree": agree_n,
        "agreementPct": _round(100.0 * agree_n / max(1, total), 1),
        "byHero": pct(by_hero),
        "byDoctrine": pct(by_doc),
        "byScenario": pct(by_sit),
        "disagreements": disagreements[:40],
        "disagreementCount": len(disagreements),
        "rows": rows,
    }


def write_outputs(doc: dict[str, Any]) -> tuple[Path, Path]:
    OUT_FACE.parent.mkdir(parents=True, exist_ok=True)
    face = {
        k: doc[k]
        for k in (
            "schemaVersion",
            "mode",
            "liveCombat",
            "generatedAt",
            "formula",
            "total",
            "agree",
            "agreementPct",
            "byHero",
            "byDoctrine",
            "byScenario",
            "disagreementCount",
            "disagreements",
        )
        if k in doc
    }
    # slim sample rows for face
    face["sample"] = [
        {
            "scenarioId": r.get("scenarioId"),
            "heroId": r["heroId"],
            "live": r.get("liveIntent"),
            "shadow": r.get("shadowIntent"),
            "agree": r.get("agree"),
            "fit": r.get("fit"),
        }
        for r in (doc.get("rows") or [])[:24]
    ]
    OUT_FACE.write_text(json.dumps(face, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_METRICS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return OUT_FACE, OUT_METRICS


def cmd_scenarios(_args: argparse.Namespace) -> int:
    sits = {}
    for s in build_scenarios():
        sits.setdefault(s["id"], {"mapId": s["mapId"], "cues": s["cues"], "heroes": []})
        sits[s["id"]]["heroes"].append(s["heroId"])
    for sid, info in sits.items():
        print(f"{sid:16} map={info['mapId']:20} cues={list(info['cues'])}  n={len(info['heroes'])}")
    return 0


def cmd_run(_args: argparse.Namespace) -> int:
    doc = run_all()
    face, metrics = write_outputs(doc)
    print(f"agreement {doc['agreementPct']}%  ({doc['agree']}/{doc['total']})")
    print(f"face {face}")
    print(f"metrics {metrics}")
    print("\nBy doctrine:")
    for row in doc["byDoctrine"]:
        print(f"  {row['key']:12} {row['pct']:5.1f}%  ({row['agree']}/{row['total']})")
    print("\nBy scenario:")
    for row in doc["byScenario"]:
        print(f"  {row['key']:16} {row['pct']:5.1f}%  ({row['agree']}/{row['total']})")
    print(f"\nDisagreements shown: {min(12, doc['disagreementCount'])}/{doc['disagreementCount']}")
    for d in doc["disagreements"][:12]:
        print(
            f"  {d['scenarioId']:16} {d['heroId']:10} live={d['live']:5} shadow={d['shadow']:5} fit={d['fit']:+.2f}"
        )
    return 0


def cmd_metrics(_args: argparse.Namespace) -> int:
    if not OUT_METRICS.is_file():
        return cmd_run(_args)
    doc = json.loads(OUT_METRICS.read_text(encoding="utf-8"))
    print(json.dumps({k: doc[k] for k in ("agreementPct", "agree", "total", "byDoctrine", "byScenario", "disagreementCount") if k in doc}, indent=2))
    return 0


def cmd_smoke(_args: argparse.Namespace) -> int:
    doc = run_all()
    write_outputs(doc)
    checks = []
    checks.append(("ran_rows", doc["total"] >= 50))
    checks.append(("agreement_sane", 20.0 <= doc["agreementPct"] <= 100.0))
    # Kiln under heat should prefer push (shadow) and not bail
    kiln_rows = [
        r
        for r in doc["rows"]
        if r["heroId"] == "brakhov" and r.get("scenarioId") == "kiln_heat_push"
    ]
    checks.append(("kiln_row", bool(kiln_rows)))
    if kiln_rows:
        checks.append(("kiln_no_bail_shadow", kiln_rows[0]["shadowIntent"] != "bail"))
        checks.append(
            (
                "kiln_push_or_hold",
                kiln_rows[0]["shadowIntent"] in ("push", "hold"),
            )
        )
    # Vane under fire should lean kite in shadow or live
    vane_rows = [
        r for r in doc["rows"] if r["heroId"] == "vane" and r.get("scenarioId") == "under_fire"
    ]
    checks.append(("vane_row", bool(vane_rows)))
    if vane_rows:
        checks.append(
            (
                "vane_kite_ish",
                vane_rows[0]["shadowIntent"] in ("kite", "hold", "push")
                and vane_rows[0]["liveIntent"] in ("kite", "hold", "push", "bail"),
            )
        )
    # Dying: most allowBail heroes bail live; kiln must not
    dying_kiln = [
        r for r in doc["rows"] if r["heroId"] == "brakhov" and r.get("scenarioId") == "dying"
    ]
    if dying_kiln:
        checks.append(("kiln_dying_no_bail", dying_kiln[0]["shadowIntent"] != "bail"))
        checks.append(("kiln_dying_live_no_bail", dying_kiln[0]["liveIntent"] != "bail"))

    checks.append(("face_written", OUT_FACE.is_file()))
    checks.append(("metrics_written", OUT_METRICS.is_file()))
    ok = all(v for _, v in checks)
    print(
        json.dumps(
            {
                "ok": ok,
                "agreementPct": doc["agreementPct"],
                "checks": dict(checks),
                "face": str(OUT_FACE),
            },
            indent=2,
        )
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage 3 shadow IntentResolver")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scenarios", help="List canned scenarios")
    sub.add_parser("run", help="Run all pairs + write faces")
    sub.add_parser("metrics", help="Print latest metrics face")
    sub.add_parser("smoke", help="Assert pins + write faces")
    args = p.parse_args(argv)
    if args.cmd == "scenarios":
        return cmd_scenarios(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "metrics":
        return cmd_metrics(args)
    if args.cmd == "smoke":
        return cmd_smoke(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
