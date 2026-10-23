#!/usr/bin/env python3
"""campaign_fruit_v1 — harvest campaign + swarm ideas from proxy/UL residuals.

Dual track:
  - campaign ideas (flow / craft knobs)
  - swarm_digest (soft doctrine prior only — never commands fair agent)

Auto-apply craft only inside a safety band. Story/flow changes stay proposals.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOOLS = Path(__file__).resolve().parent
WS_DEFAULT = TOOLS.parent
HIVE_VITALS = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals")

SCHEMA = "campaign-fruit/1.0"
CRAFT_BAND_FRAC = 0.10  # ±10% of current for auto knobs
CRAFT_ABSOLUTE = {
    "difficulty": (1.0, 2.2),
    "width_early": (0.05, 0.95),
    "width_late": (0.20, 1.0),
    "width_ease": (0.10, 0.90),
    "decoy_pressure": (0.5, 3.5),
    "enemy_aggro": (0.6, 2.0),
    "lane_bias": (0.3, 1.5),
    "path_purity_target": (0.15, 0.85),
    "arc1_scale": (0.5, 1.5),
    "arc2_scale": (0.5, 1.5),
    "arc3_scale": (0.5, 2.5),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _workspace(ws: Optional[Path] = None) -> Path:
    if ws is not None:
        return Path(ws)
    env = (os.environ.get("BAR_WORKSPACE") or os.environ.get("VERDANCE_WORKSPACE") or "").strip()
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return WS_DEFAULT.resolve()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def collect_signals(workspace: Path) -> Dict[str, Any]:
    residual = load_json(workspace / "outbox" / "hive_bar_residual.latest.json", {}) or {}
    proxy = load_json(workspace / "outbox" / "proxy_campaign.latest.json", {}) or {}
    weights = load_json(workspace / "app" / "brain" / "bar_brain_weights.json", {}) or {}
    ul = load_json(workspace / "app" / "brain" / "bar_brain_ul_state.json", {}) or {}
    craft = load_json(workspace / "app" / "brain" / "craft_recipe.json", {}) or {}

    by = residual.get("byStyle") or proxy.get("byStyle") or {}
    simple = by.get("simple") or {}
    barb = by.get("barbarian") or {}
    brain = residual.get("brain") or {}
    ac = weights.get("action_counts") or {}
    total_ac = sum(_f(v) for v in ac.values()) or 1.0
    push = _f(ac.get("PUSH_OBJECTIVE"))
    push_dom = push / total_ac

    # top UL by update_count
    params = ul.get("params") or {}
    top_ul: List[Tuple[str, int, float]] = []
    for k, v in params.items():
        if not isinstance(v, dict):
            continue
        uc = int(v.get("update_count") or 0)
        if uc <= 0:
            continue
        top_ul.append((k, uc, _f(v.get("sigma"), 1.5)))
    top_ul.sort(key=lambda t: -t[1])

    dry_push = next((uc for k, uc, _ in top_ul if k == "dry|PUSH_OBJECTIVE"), 0)
    open_push = next((uc for k, uc, _ in top_ul if k == "open|PUSH_OBJECTIVE"), 0)
    open_push_sig = next((sig for k, _, sig in top_ul if k == "open|PUSH_OBJECTIVE"), 1.5)

    source_mtime = None
    rp = workspace / "outbox" / "hive_bar_residual.latest.json"
    if rp.is_file():
        source_mtime = rp.stat().st_mtime

    return {
        "simpleWin": _f(simple.get("meanWinRate"), -1.0),
        "barbWin": _f(barb.get("meanWinRate"), -1.0),
        "funSimple": _f(simple.get("meanFun"), -1.0),
        "funBarb": _f(barb.get("meanFun"), -1.0),
        "clashSimple": _f(simple.get("meanClashEvents"), 0.0),
        "clashBarb": _f(barb.get("meanClashEvents"), 0.0),
        "pushDominance": round(push_dom, 4),
        "ecoDryPushUpdates": dry_push,
        "openPushUpdates": open_push,
        "openPushSigma": round(open_push_sig, 4),
        "ulFamily": brain.get("ulFamily") or ul.get("family"),
        "ulEcoUpdates": brain.get("ulEcoUpdates"),
        "ulWidthUpdates": brain.get("ulWidthUpdates"),
        "ulMissions": brain.get("ulMissions") or ul.get("missions"),
        "samples": brain.get("samples") or weights.get("samples"),
        "craftKnobs": (craft.get("knobs") or {}),
        "craftScore": craft.get("craft_score"),
        "topUl": [{"key": k, "updates": u, "sigma": s} for k, u, s in top_ul[:8]],
        "source_mtime": source_mtime,
        "difficulty": proxy.get("difficulty") or residual.get("proxyMeta", {}).get("difficulty"),
    }


def synthesize_ideas(signals: Dict[str, Any]) -> List[Dict[str, Any]]:
    ideas: List[Dict[str, Any]] = []
    sw = signals.get("simpleWin", -1)
    bw = signals.get("barbWin", -1)
    fun_s = signals.get("funSimple", -1)
    fun_b = signals.get("funBarb", -1)
    push_dom = signals.get("pushDominance", 0)
    open_sig = signals.get("openPushSigma", 1.5)
    eco_u = int(signals.get("ulEcoUpdates") or 0)

    if sw >= 0.95:
        ideas.append(
            {
                "id": "fruit-simple-saturated",
                "track": "campaign",
                "severity": "med",
                "claim": "Proxy stomps simple — campaign pressure too soft on easy lane",
                "evidence": [f"simpleWin={sw}", f"openPushSigma={open_sig}"],
                "proposal": {
                    "craft_delta": {"difficulty": 0.08, "width_late": 0.03, "enemy_aggro": 0.05},
                    "flow": "raise late multipath + enemy aggro; keep fun",
                },
                "auto_apply_ok": True,
            }
        )
    if sw >= 0.95 and fun_s >= 0 and fun_s < 0.45:
        ideas.append(
            {
                "id": "fruit-fun-low-on-easy-wins",
                "track": "campaign",
                "severity": "low",
                "claim": "Easy wins feel dull — need mid-mission pressure beat without densify",
                "evidence": [f"simpleWin={sw}", f"funSimple={fun_s}"],
                "proposal": {
                    "flow": "inject clash/pressure beat on easy clears; diversify contracts",
                },
                "auto_apply_ok": False,
            }
        )
    if bw >= 0 and sw >= 0 and (bw - sw) > 0.05:
        ideas.append(
            {
                "id": "fruit-ladder-inverted",
                "track": "campaign",
                "severity": "high",
                "claim": "Barb not harder than simple — ladder honesty at risk",
                "evidence": [f"simpleWin={sw}", f"barbWin={bw}"],
                "proposal": {
                    "craft_delta": {"enemy_aggro": 0.1, "decoy_pressure": 0.15},
                    "flow": "retune barbarian_aggressive mapping / scale",
                },
                "auto_apply_ok": True,
            }
        )
    if push_dom >= 0.75:
        ideas.append(
            {
                "id": "fruit-push-monoculture",
                "track": "campaign",
                "severity": "med",
                "claim": "Scar monoculture on PUSH_OBJECTIVE — diversify mission geometry",
                "evidence": [f"pushDominance={push_dom}"],
                "proposal": {
                    "craft_delta": {"width_early": -0.03, "lane_bias": 0.05},
                    "flow": "more multipath early; reward FLANK/PROBE contexts",
                },
                "auto_apply_ok": True,
            }
        )
    if eco_u < 20 and int(signals.get("ulMissions") or 0) > 50:
        ideas.append(
            {
                "id": "fruit-eco-undertrained",
                "track": "swarm",
                "severity": "med",
                "claim": "Eco family under-updated relative to missions — curriculum needs eco stress",
                "evidence": [f"ulEcoUpdates={eco_u}", f"ulMissions={signals.get('ulMissions')}"],
                "proposal": {
                    "flow": "prefer C2_eco curriculum slots; longer ticks for eco_feel variety",
                },
                "auto_apply_ok": False,
            }
        )
    if open_sig is not None and open_sig < 0.02 and sw >= 0.9:
        ideas.append(
            {
                "id": "fruit-open-push-locked",
                "track": "campaign",
                "severity": "low",
                "claim": "open|PUSH locked (low sigma) while stomping — raise late width pressure",
                "evidence": [f"openPushSigma={open_sig}", f"simpleWin={sw}"],
                "proposal": {
                    "craft_delta": {"width_late": 0.04, "path_purity_target": -0.03},
                    "flow": "force multipath late so PUSH is not free",
                },
                "auto_apply_ok": True,
            }
        )
    if fun_b >= 0 and fun_s >= 0 and fun_b > fun_s + 0.05 and bw < sw:
        ideas.append(
            {
                "id": "fruit-harder-more-fun",
                "track": "campaign",
                "severity": "info",
                "claim": "Harder barb is more fun — lean campaign tension toward that band",
                "evidence": [f"funBarb={fun_b}", f"funSimple={fun_s}", f"barbWin={bw}"],
                "proposal": {
                    "flow": "bias theater contracts toward contested holds; keep Tnb/clash alive",
                },
                "auto_apply_ok": False,
            }
        )

    if not ideas:
        ideas.append(
            {
                "id": "fruit-stable-hold",
                "track": "swarm",
                "severity": "info",
                "claim": "No strong anomaly — keep organic ladder + dual UL accruing",
                "evidence": [f"simpleWin={sw}", f"barbWin={bw}", f"pushDominance={push_dom}"],
                "proposal": {"flow": "continue curriculum C1/C2; harvest again after more units"},
                "auto_apply_ok": False,
            }
        )
    return ideas


def swarm_digest_from_signals(signals: Dict[str, Any], ideas: List[Dict[str, Any]]) -> Dict[str, Any]:
    biases: List[str] = []
    for row in signals.get("topUl") or []:
        key = str(row.get("key") or "")
        if key:
            biases.append(key.replace("|", "_").lower())
    if signals.get("pushDominance", 0) >= 0.6:
        doctrine = "support_push"
    elif signals.get("simpleWin", 1) < 0.4:
        doctrine = "farm_patrol"
    else:
        doctrine = "rest"
    return {
        "soft_doctrine": doctrine,
        "note": "soft prior only — never command fair agent",
        "learned_bias": biases[:6],
        "idea_ids": [i.get("id") for i in ideas if i.get("track") == "swarm"][:6],
        "ulEcoUpdates": signals.get("ulEcoUpdates"),
        "ulWidthUpdates": signals.get("ulWidthUpdates"),
    }


def clamp_craft_delta(
    knobs: Dict[str, Any],
    delta: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
    """Apply delta with ±band and absolute clamps. Returns (new_knobs, applied, notes)."""
    applied: Dict[str, float] = {}
    notes: List[str] = []
    out = {k: _f(v) for k, v in (knobs or {}).items() if isinstance(v, (int, float))}
    for k, d in (delta or {}).items():
        if k not in out and k not in CRAFT_ABSOLUTE:
            notes.append(f"skip_unknown:{k}")
            continue
        cur = out.get(k, _f((CRAFT_ABSOLUTE.get(k) or (0, 1))[0]))
        dv = _f(d)
        # band relative to current magnitude (min step floor)
        band = max(abs(cur) * CRAFT_BAND_FRAC, 0.02)
        if abs(dv) > band:
            dv = band if dv > 0 else -band
            notes.append(f"band_clip:{k}")
        nxt = cur + dv
        lo, hi = CRAFT_ABSOLUTE.get(k, (None, None))
        if lo is not None:
            nxt = max(lo, nxt)
        if hi is not None:
            nxt = min(hi, nxt)
        out[k] = round(nxt, 4)
        applied[k] = round(nxt - cur, 4)
    return out, applied, notes


def apply_safe_craft(
    ideas: List[Dict[str, Any]],
    *,
    workspace: Path,
    apply: bool = True,
) -> Dict[str, Any]:
    craft_path = workspace / "app" / "brain" / "craft_recipe.json"
    craft = load_json(craft_path, {}) or {}
    knobs = dict(craft.get("knobs") or {})
    merged_delta: Dict[str, float] = {}
    used_ids: List[str] = []
    for idea in ideas:
        if not idea.get("auto_apply_ok"):
            continue
        prop = idea.get("proposal") or {}
        cd = prop.get("craft_delta") or {}
        if not isinstance(cd, dict):
            continue
        for k, v in cd.items():
            merged_delta[k] = merged_delta.get(k, 0.0) + _f(v)
        used_ids.append(str(idea.get("id")))

    if not merged_delta:
        return {
            "applied": False,
            "reason": "no_auto_craft_deltas",
            "idea_ids": [],
        }

    new_knobs, applied, notes = clamp_craft_delta(knobs, merged_delta)
    if not apply:
        return {
            "applied": False,
            "reason": "dry_run",
            "would_apply": applied,
            "idea_ids": used_ids,
            "notes": notes,
        }

    if not applied:
        return {"applied": False, "reason": "nothing_after_clamp", "idea_ids": used_ids, "notes": notes}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    craft = dict(craft) if craft else {"schemaVersion": "verdance-craft-recipe/0.1"}
    craft["knobs"] = new_knobs
    craft["source"] = "campaign_fruit"
    craft["stamp"] = stamp
    craft["fruit_idea_ids"] = used_ids
    craft["fruit_notes"] = notes
    craft["updated_at"] = _now()
    write_json(craft_path, craft)
    return {
        "applied": True,
        "applied_delta": applied,
        "idea_ids": used_ids,
        "notes": notes,
        "stamp": stamp,
        "path": str(craft_path),
    }


def write_soft_doctrine(digest: Dict[str, Any], *, workspace: Path) -> Path:
    face = {
        "schema": "bar-swarm-doctrine-soft/1.0",
        "at": _now(),
        "posture": digest.get("soft_doctrine") or "rest",
        "note": digest.get("note"),
        "learned_bias": digest.get("learned_bias") or [],
        "source": "campaign_fruit_v1",
        "law": "soft prior only — never command fair agent",
    }
    op = workspace / "outbox" / "bar_swarm_doctrine_soft.json"
    write_json(op, face)
    try:
        if HIVE_VITALS.is_absolute() and HIVE_VITALS.is_dir():  # only the owner's synced hive, never a stray relative dir
            write_json(HIVE_VITALS / "bar_swarm_doctrine_soft.json", face)
        # also a thin hive_rts-compatible nudge if missing posture elsewhere
    except OSError:
        pass
    return op


def harvest(
    *,
    workspace: Optional[Path] = None,
    apply_craft: bool = True,
    also_hive: bool = True,
) -> Dict[str, Any]:
    ws = _workspace(workspace)
    signals = collect_signals(ws)
    ideas = synthesize_ideas(signals)
    digest = swarm_digest_from_signals(signals, ideas)
    craft_result = apply_safe_craft(ideas, workspace=ws, apply=apply_craft)
    doctrine_path = write_soft_doctrine(digest, workspace=ws)

    age = None
    if signals.get("source_mtime"):
        age = round(time.time() - float(signals["source_mtime"]), 1)

    fruit = {
        "schema": SCHEMA,
        "at": _now(),
        "source_age_s": age,
        "signals": {k: v for k, v in signals.items() if k not in ("craftKnobs", "source_mtime")},
        "ideas": ideas,
        "swarm_digest": digest,
        "craft": craft_result,
        "doctrine_soft_path": str(doctrine_path),
        "honesty": {
            "barDensifyBanned": True,
            "godBrainMerge": False,
            "craftAutoBandFrac": CRAFT_BAND_FRAC,
            "humanSealBotClearForbidden": True,
        },
    }
    op = ws / "outbox" / "campaign_fruit.latest.json"
    write_json(op, fruit)
    if also_hive:
        try:
            HIVE_VITALS.mkdir(parents=True, exist_ok=True)
            write_json(HIVE_VITALS / "bar_campaign_fruit.latest.json", fruit)
        except OSError:
            pass
    return fruit


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Campaign fruit harvest from BAR learning")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--no-apply-craft", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    ws = Path(args.workspace).resolve()

    if args.self_test:
        sig = {
            "simpleWin": 1.0,
            "barbWin": 0.5,
            "funSimple": 0.37,
            "funBarb": 0.46,
            "pushDominance": 0.82,
            "openPushSigma": 0.007,
            "ulEcoUpdates": 5,
            "ulMissions": 100,
            "topUl": [{"key": "open|PUSH_OBJECTIVE", "updates": 100, "sigma": 0.007}],
        }
        ideas = synthesize_ideas(sig)
        assert any(i["id"] == "fruit-simple-saturated" for i in ideas), ideas
        assert any(i["id"] == "fruit-push-monoculture" for i in ideas), ideas
        knobs = {"difficulty": 1.28, "width_late": 0.98, "enemy_aggro": 1.35}
        new, applied, _ = clamp_craft_delta(knobs, {"difficulty": 0.5, "width_late": 0.04})
        assert applied["difficulty"] <= 0.13 + 1e-6  # band clip
        print("campaign_fruit_v1 self_test OK", len(ideas), "ideas", applied)
        return 0

    fruit = harvest(workspace=ws, apply_craft=not args.no_apply_craft)
    print(
        json.dumps(
            {
                "ok": True,
                "ideas": len(fruit.get("ideas") or []),
                "craft": fruit.get("craft"),
                "doctrine": (fruit.get("swarm_digest") or {}).get("soft_doctrine"),
                "path": str(ws / "outbox" / "campaign_fruit.latest.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
