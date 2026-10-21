#!/usr/bin/env python3
"""Escalation map v1 — chart the campaign's complexity/difficulty curve.

Simulates a full offline campaign (materialize intent -> synthesize a clean
victory -> process result -> repeat) and renders a per-mission table of every
knob that decides "how hard and how complex is mission N": enemy scale (the
compiler's REAL formula, mirrored), arc/enemy doctrine, tech policy, objective
kind and count, escalation waves, roster growth.

The sim runs in a sandbox — `data/` is junctioned (or copied) into a temp
workspace with an EMPTY outbox — because materialize_next_intent persists its
sortie pick to outbox/next_sortie_order.json. The live campaign state, outbox,
and inbox are never touched.

Usage:
  python tools/escalation_map_v1.py                 # 12 missions, markdown to stdout
  python tools/escalation_map_v1.py --missions 13 --out outbox/escalation_map.latest.md
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


from verdance import campaign as engine

WS_DEFAULT = Path(__file__).resolve().parents[1]


# --- Sandbox ---------------------------------------------------------------

def make_sandbox(real_ws: Path) -> tempfile.TemporaryDirectory:
    """Temp workspace: data/ junctioned from the real one, empty outbox."""
    tmp = tempfile.TemporaryDirectory(prefix="va_escmap_")
    root = Path(tmp.name)
    src = real_ws / "data"
    dst = root / "data"
    linked = False
    if sys.platform == "win32":
        try:
            import _winapi  # noqa: PLC0415
            _winapi.CreateJunction(str(src), str(dst))
            linked = True
        except Exception:
            linked = False
    if not linked:
        try:
            dst.symlink_to(src, target_is_directory=True)
            linked = True
        except OSError:
            linked = False
    if not linked:
        shutil.copytree(src, dst)
    (root / "outbox").mkdir(exist_ok=True)
    return tmp


# --- Compiler mirrors ------------------------------------------------------
# These mirror scripts/build_next_mission_v1.ps1 so the map reports the scale
# the FIELD will actually get, not the (stale) card preview. If the compiler
# formula changes, change these too — verify_escalation tests pin the values.

TACTICS_KINDS = {
    "seize_lane", "eco_raid", "economy_disrupt", "strike_relay",
    "gate_control", "destroy_key_structure",
}


def arc_profile_mirror(n: int, kind: str, is_finale: bool) -> Dict[str, Any]:
    arc_id = "raid_tactics" if n <= 3 else ("contested_front" if n <= 6 else "strike_lead")
    is_tactics = kind in TACTICS_KINDS
    commanders = 0 if (arc_id in ("raid_tactics", "contested_front") or is_tactics) else 1
    escalation = {"raid_tactics": "off", "contested_front": "light"}.get(arc_id, "full")
    enemy_mode = "light_qrf" if arc_id == "strike_lead" else "static_bases"
    # Drop 3: act-1 non-finale static bases become roving warbands.
    act = engine.act_for_mission(n)
    if act <= 1 and not is_finale and enemy_mode == "static_bases":
        enemy_mode = "warband"
    return {
        "id": arc_id,
        "playerCommanders": commanders,
        "escalation": escalation,
        "enemyMode": enemy_mode,
    }


def pressure_tier_legacy(n: int) -> float:
    if n <= 1:
        return 0.25
    if n <= 2:
        return 0.35
    if n <= 4:
        return 0.5
    if n <= 7:
        return 0.75
    return 1.0


def ramp_factor(n: int) -> float:
    return min(1.0, 0.55 + 0.1 * (n - 1))


def load_craft_knobs(real_ws: Path) -> Optional[Dict[str, Any]]:
    for name, active_gate in (("app/brain/campaign_craft.json", True), ("app/brain/craft_recipe.json", False)):
        p = real_ws / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if active_gate and not data.get("active"):
            continue
        if data.get("knobs"):
            return dict(data["knobs"])
    return None


def compiler_scale_mirror(
    intent: Dict[str, Any],
    state: Dict[str, Any],
    craft_knobs: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    n = int(intent.get("missionNumber", 1) or 1)
    is_finale = bool(intent.get("finale"))
    kind = str(
        (intent.get("objectiveTarget") or {}).get("kind")
        or intent.get("objective") or ""
    )
    eco = intent.get("economy") or {}
    diff_coeff = float(eco.get("difficultyCoefficient") or 1.0)
    center = float((intent.get("expectedEnemyScale") or {}).get("center") or 6000.0)
    center = min(11000.0, max(3500.0, center))
    plan = intent.get("escalationPlan") or {}
    tier = pressure_tier_legacy(n)
    ramp = ramp_factor(n)
    scale = max(0.35, min(2.0, center / 6000.0)) * diff_coeff * ramp * tier
    if craft_knobs:
        arc_s = float(
            craft_knobs.get("arc1_scale" if n <= 5 else ("arc2_scale" if n <= 10 else "arc3_scale")) or 1.0
        ) or 1.0
        aggro = float(craft_knobs.get("enemy_aggro") or 1.0) or 1.0
        arc_ramp = 1.0 + 0.03 * max(0, n - 5)
        scale = min(1.95, max(0.55, scale * aggro * arc_s * arc_ramp))
    if is_finale:
        scale = min(2.6, max(1.35, scale * 1.6))
    rep = state.get("reputation") or {}
    merc_rep = float(rep.get("nullmercs") or 43.0)
    mercs_present = kind != "hive_clear_or_bypass"
    if mercs_present and merc_rep >= 40.0:
        scale = scale * 1.1
    # Drop 4: the ladder's scale window clamps last (dial scales the walls),
    # exactly as the compiler applies it.
    pre_window = round(scale, 3)
    window = plan.get("scaleWindow") or []
    if len(window) >= 2:
        dial = float(eco.get("difficultyDial") or 1.0) or 1.0
        lo, hi = float(window[0]) * dial, float(window[1]) * dial
        if hi < lo:
            lo, hi = hi, lo
        scale = min(hi, max(lo, scale))
    scale = round(scale, 3)
    band = "heavy" if scale >= 1.6 else ("reinforced" if scale >= 1.2 else ("light" if scale <= 0.85 else "standard"))
    return {
        "enemyScale": scale,
        "band": band,
        "tier": round(tier, 3),
        "ramp": round(ramp, 3),
        "diffCoeff": round(diff_coeff, 3),
        "preWindow": pre_window,
        "fortified": scale >= 1.4,
    }


# --- Simulation ------------------------------------------------------------

def synth_victory(intent: Dict[str, Any]) -> Dict[str, Any]:
    """A full-fidelity clean win, shaped like the gadget's real result JSON —
    capture kinds carry the node claim (zone flips need it), destruction kinds
    carry the destroyed objective ids and target zone."""
    obj = intent.get("objectiveTarget") or {}
    n = int(intent.get("missionNumber", 1) or 1)
    mission = str(intent.get("missionId") or engine.mission_id(n))
    kind = str(obj.get("kind") or intent.get("objective") or "")
    capture = bool(obj.get("captureMode")) or kind in ("seize_lane", "gate_control", "hold_plateau")
    result = {
        "schemaVersion": engine.RESULT_SCHEMA,
        "campaignId": str(intent.get("campaignId") or "verdance_ashes"),
        "missionId": mission,
        "missionNumber": n,
        "status": "victory",
        "mapId": intent.get("mapId"),
        "deploymentMapId": intent.get("mapId"),
        "deploymentZoneId": intent.get("deploymentZoneId"),
        "extractionStatus": "clean",
        "extractionZoneId": intent.get("extractionZoneId") or intent.get("deploymentZoneId"),
        "elapsedMinutes": 14,
        "pathSignal": intent.get("pathSignal") or "B",
        "objectiveComplete": True,
        "objectiveArchetype": kind,
        "targetZoneId": obj.get("targetZoneId"),
        "patron": intent.get("patron") or "nullmercs",
        # Plausible field survivors so the roster/cadre columns track a real
        # campaign's growth instead of staying empty all sim long.
        "playerSurvivors": {"legcen": 5, "leggat": 3},
        "destroyedObjectiveIds": [obj.get("id") or (mission + "_objective")],
        "resultKey": "|".join(["verdance_ashes", mission, str(n), "victory"]),
    }
    if capture:
        result["captureMode"] = str(obj.get("captureMode") or "clear_hold_shell")
        result["capturePhase"] = "claimed"
        result["nodeClaimed"] = True
        result["pocketCleared"] = True
    return result


def _tech_summary(policy: Dict[str, Any]) -> str:
    if not policy:
        return "?"
    if not policy.get("buildStructures", True):
        return "no-build"
    max_tech = int(policy.get("buildTech", 3) or 3)
    return "full" if max_tech >= 3 else ("T%d" % max_tech)


def _objective_summary(intent: Dict[str, Any]) -> str:
    plan = intent.get("escalationPlan") or {}
    secs = list(plan.get("secondaries") or [])
    req = sum(1 for s in secs if s.get("required"))
    bonus = len(secs) - req
    parts = ["1"]
    if req:
        parts.append("+%dreq" % req)
    if bonus:
        parts.append("+%dbonus" % bonus)
    strength = str(plan.get("objectiveStrength") or "surgical")
    label = "".join(parts)
    if strength != "surgical":
        label += " " + strength.upper()
    return label


def simulate(real_ws: Path, missions: int = 12) -> List[Dict[str, Any]]:
    craft = load_craft_knobs(real_ws)
    rows: List[Dict[str, Any]] = []
    with make_sandbox(real_ws) as tmp:
        ws = Path(tmp)
        state = engine.default_v1_state()
        intent = engine.materialize_next_intent(state, ws)
        for _ in range(missions):
            n = int(intent.get("missionNumber", 1) or 1)
            is_finale = bool(intent.get("finale"))
            kind = str(
                (intent.get("objectiveTarget") or {}).get("kind")
                or intent.get("objective") or ""
            )
            arc = arc_profile_mirror(n, kind, is_finale)
            scale = compiler_scale_mirror(intent, state, craft)
            roster = state.get("roster") or {}
            heroes = [h for h in (roster.get("heroes") or []) if str(h.get("status", "active")) == "active"]
            cadre_n = sum(int(v or 0) for v in (roster.get("cadre") or {}).values())
            plan = intent.get("escalationPlan") or {}
            card_prev = (intent.get("difficulty") or {}).get("enemyScalePreview")
            rows.append({
                "mission": n,
                "act": engine.act_for_mission(n),
                "missionId": intent.get("missionId"),
                "mapId": intent.get("mapId"),
                "kind": kind,
                "target": (intent.get("objectiveTarget") or {}).get("targetZoneId") or "",
                "finaleKind": (intent.get("finale") or {}).get("kind") if is_finale else "",
                "arc": arc["id"],
                "enemyMode": arc["enemyMode"],
                "waves": str(plan.get("wavesMode") or arc["escalation"]),
                "commanders": arc["playerCommanders"],
                "tech": _tech_summary(intent.get("techPolicy") or {}),
                "enemyScale": scale["enemyScale"],
                "rawScale": scale.get("preWindow"),
                "band": scale["band"],
                "tier": scale["tier"],
                "ramp": scale["ramp"],
                "cardPreview": card_prev,
                "objectives": _objective_summary(intent),
                "heroes": len(heroes),
                "cadre": cadre_n,
                "grants": len((roster.get("grants") or [])),
                "epilogue": bool(state.get("campaignComplete")),
            })
            result = synth_victory(intent)
            state, report, intent, _events = engine.process_result(state, result, None, ws)
            joins = report.get("heroJoins") or []
            if joins:
                rows[-1]["notes"] = "joins: " + ", ".join(str(j.get("heroId")) for j in joins)
            grant = report.get("actGrant") or {}
            if grant.get("units"):
                extra = "grant: " + ", ".join("%sx%s" % (v, k) for k, v in grant["units"].items())
                rows[-1]["notes"] = (rows[-1].get("notes", "") + "; " + extra).strip("; ")
            if report.get("campaignComplete"):
                rows[-1]["notes"] = (rows[-1].get("notes", "") + "; CAMPAIGN COMPLETE").strip("; ")
    return rows


# --- Rendering -------------------------------------------------------------

SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: List[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return "".join(SPARK[min(7, int((v - lo) / span * 7.999))] for v in values)


def render_markdown(rows: List[Dict[str, Any]], title: str = "Escalation map") -> str:
    cols = [
        ("M", "mission"), ("Act", "act"), ("Map", "mapId"), ("Kind", "kind"),
        ("Objectives", "objectives"), ("EnemyScale", "enemyScale"), ("Band", "band"),
        ("Tier", "tier"), ("Mode", "enemyMode"), ("Waves", "waves"),
        ("Tech", "tech"), ("Heroes", "heroes"), ("Cadre", "cadre"), ("Notes", "notes"),
    ]
    lines = ["# " + title, ""]
    lines.append("enemyScale curve: `" + sparkline([float(r["enemyScale"]) for r in rows]) + "`")
    lines.append("")
    lines.append("| " + " | ".join(c[0] for c in cols) + " |")
    lines.append("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        cells = []
        for _, key in cols:
            v = r.get(key, "")
            if key == "mission" and r.get("finaleKind"):
                v = "%s (finale:%s)" % (v, r["finaleKind"])
            if key == "mission" and r.get("epilogue"):
                v = "%s (epilogue)" % v
            cells.append(str(v if v is not None else ""))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    # Card-vs-field divergence check (the stale preview finding).
    diverged = [
        r for r in rows
        if r.get("cardPreview") is not None
        and abs(float(r["cardPreview"]) - float(r["enemyScale"])) > 0.25
    ]
    if diverged:
        lines.append(
            "**Card preview drift:** %d/%d missions where the intent's card preview "
            "differs from the compiled field scale by >0.25 (engine mirror is stale)."
            % (len(diverged), len(rows))
        )
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Simulate a campaign and chart the escalation curve")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--missions", type=int, default=12)
    ap.add_argument("--out", default="", help="Write markdown here (default: stdout only)")
    ap.add_argument("--json", default="", help="Also write raw rows as JSON")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ws = Path(args.workspace).resolve()
    rows = simulate(ws, missions=max(1, args.missions))
    md = render_markdown(rows)
    print(md)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ws / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print("WROTE " + str(out))
    if args.json:
        jp = Path(args.json)
        if not jp.is_absolute():
            jp = ws / jp
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("WROTE " + str(jp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
