#!/usr/bin/env python3
"""Closed-loop multi-sortie campaign sim — real story engine settle, no BAR.

Drives: Mode A sortie → synthetic match_result.v2 → process_result → world_tick
→ attachments. Multi-seed divergence report under headless_runs/kernel_sim_*.

Usage:
  python tools/kernel_campaign_sim_v1.py --workspace . --sorties 8 --seeds 5
  python tools/kernel_campaign_sim_v1.py --workspace . --sorties 10 --seed 42 --write
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


from verdance.company import attachments as att_mod
from verdance.world import world_tick as wt
from verdance import campaign as engine

PROFILES = (
    "clean_win",
    "bloody_win",
    "partial",
    "fail_extract",
    "hero_wound",
    "node_claim",
    "eco_raid_scavenge",
    "defeat",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _seed_workspace(src: Path) -> Path:
    """Temp workspace with data/ maps + commerce; empty outbox/state."""
    td = Path(tempfile.mkdtemp(prefix="kernel_sim_"))
    for rel in (
        "data/zone_maps",
        "data/commerce",
        "data/map_pool",
        "data/story",
        "data/contracts",
        "data/scenarios",
    ):
        s = src / rel
        if s.exists():
            shutil.copytree(s, td / rel, dirs_exist_ok=True)
    (td / "outbox").mkdir(parents=True, exist_ok=True)
    (td / "state").mkdir(parents=True, exist_ok=True)
    (td / "inbox").mkdir(parents=True, exist_ok=True)
    return td


def _fresh_state(workspace: Path, home_map: str = "koom_valley") -> Dict[str, Any]:
    state = engine.default_v1_state()
    engine.ensure_zone_memory(state, workspace)
    engine.ensure_commerce(state, workspace)
    engine.ensure_faction_banks(state)
    att_mod.ensure_attachments(state)
    state["sessionHomeMap"] = home_map
    state["sessionMode"] = "same_map"
    state["occupationModel"] = "living_shell"
    # Seed a foothold so Mode A quests have from-zones
    zm = state.setdefault("zoneMemory", {}).setdefault(home_map, {})
    # Zone IDs must match authored zone_memory (KV_*/GF_*/TRJ_*), not legacy aliases.
    # Wrong IDs leave Mode A with no foothold → materialize falls through to GF opener.
    footholds = {
        "koom_valley": "KV_NW_MUSTER",
        "greenest_fields": "GF_NW_MUSTER",
        "eye_of_horus": "EOH_NW_CRATER_CAMP",
        "all_that_simmers": "ATS_NW_RIM",
        "ancient_bastion": "AB_WEST_APPROACH",
        "tabula": "T_NW_MUSTER",
        "the_rock_jungle": "TRJ_NW_OUTER_MUSTER",
    }
    fz = footholds.get(home_map)
    if fz and fz in zm:
        zm[fz]["controllingFaction"] = "nullmercs"
        absr = zm[fz].setdefault("abstract", {})
        absr["control"] = "nullmercs"
    elif fz:
        zm[fz] = {
            "controllingFaction": "nullmercs",
            "abstract": {"control": "nullmercs"},
            "label": fz,
        }
    elif zm:
        # first zone as foothold
        first = next(iter(zm.keys()))
        zm[first]["controllingFaction"] = "nullmercs"
    return state


def _pick_profile(rng: random.Random, strength: Dict[str, float], mission_i: int) -> str:
    """Stochastic outcome profile biased by player strength + mission index."""
    c = float(strength.get("composite") or 0.3)
    weights = {
        "clean_win": 0.14 + 0.10 * c,
        "bloody_win": 0.14,
        "partial": 0.10,
        "node_claim": 0.18 + 0.08 * c,  # prefer claim path for occupation drama
        "eco_raid_scavenge": 0.14,
        "hero_wound": 0.10 + (0.08 if strength.get("wounds", 0) > 1 else 0),
        "fail_extract": 0.10 - 0.03 * c,
        "defeat": 0.10 - 0.05 * c,
    }
    # Early missions slightly easier; mid force a claim attempt
    if mission_i < 2:
        weights["defeat"] *= 0.5
        weights["clean_win"] *= 1.15
    if mission_i in (2, 5):
        weights["node_claim"] *= 2.0
    names = list(weights.keys())
    w = [max(0.02, weights[n]) for n in names]
    return rng.choices(names, weights=w, k=1)[0]


def synthesize_result(
    intent: Dict[str, Any],
    state: Dict[str, Any],
    profile: str,
    *,
    rng: random.Random,
    sortie_index: int,
) -> Dict[str, Any]:
    """Build a schema-valid match result from intent + profile."""
    map_id = str(intent.get("mapId") or state.get("sessionHomeMap") or "koom_valley")
    obj = intent.get("objectiveTarget") if isinstance(intent.get("objectiveTarget"), dict) else {}
    zone = str(
        (obj or {}).get("targetZoneId")
        or intent.get("targetZoneId")
        or ""
    )
    kind = str((obj or {}).get("kind") or intent.get("objective") or "seize_lane")
    mission_id = str(intent.get("missionId") or state.get("currentMissionId") or f"va_{sortie_index:03d}")
    mission_n = int(intent.get("missionNumber") or state.get("missionNumber") or sortie_index)
    key = f"ksim|{mission_id}|{mission_n}|{profile}|{rng.randint(0, 99999)}"

    status = "victory"
    success = True
    clean = True
    node_claimed = False
    pocket = False
    capture_phase = "idle"
    scars: List[Dict[str, Any]] = []
    tnb_bank = int((state.get("commerce") or {}).get("tenebrium") or 0)
    tnb_loot = 0
    tnb_lost = 0
    survivors = {"corthud": 5, "legbal": 2}
    loan_hp = {"corthud": {"count": 5, "avgHpFrac": 0.75, "minHpFrac": 0.5}}
    named: List[Dict[str, Any]] = []
    extract = "clean"
    against = "armada"

    if profile == "clean_win":
        status, clean, extract = "victory", True, "clean"
        tnb_loot = rng.randint(1, 3)
        scars = [{"zoneId": zone, "unitDefName": "armsolar", "destroyed": True, "damageFrac": 1.0}]
    elif profile == "bloody_win":
        status, clean, extract = "victory", False, "contested"
        survivors = {"corthud": 2, "legbal": 1}
        loan_hp = {"corthud": {"count": 2, "avgHpFrac": 0.35, "minHpFrac": 0.15}}
        named = [{"charId": "vane", "outcome": "wounded"}]
        tnb_loot = rng.randint(0, 2)
        scars = [
            {"zoneId": zone, "unitDefName": "armwin", "destroyed": True, "damageFrac": 1.0},
            {"zoneId": zone, "unitDefName": "armllt", "destroyed": True, "damageFrac": 1.0},
        ]
    elif profile == "partial":
        status, clean, extract = "partial", False, "contested"
        tnb_loot = rng.randint(0, 1)
        survivors = {"corthud": 3}
    elif profile == "fail_extract":
        status, success, clean, extract = "defeat", False, False, "failed"
        tnb_lost = rng.randint(1, 2)
        survivors = {"corthud": 1}
        loan_hp = {"corthud": {"count": 1, "avgHpFrac": 0.2, "minHpFrac": 0.1}}
    elif profile == "hero_wound":
        status, clean = "victory", True
        named = [{"charId": "ketha", "outcome": "wounded"}]
        survivors = {"corthud": 4, "legcen": 1}
        tnb_loot = rng.randint(0, 1)
    elif profile == "node_claim":
        status, clean = "victory", True
        node_claimed = True
        pocket = True
        capture_phase = "claimed"
        kind = kind if kind in ("seize_lane", "gate_control", "hold_plateau") else "seize_lane"
        scars = [
            {"zoneId": zone, "unitDefName": "armmex", "destroyed": True, "damageFrac": 1.0},
            {"zoneId": zone, "unitDefName": "armhlt", "destroyed": True, "damageFrac": 1.0},
            {"zoneId": zone, "unitDefName": "armsolar", "destroyed": True, "damageFrac": 0.9},
        ]
        # freeTnbMint false — reclaim loot only (small)
        tnb_loot = 1 if rng.random() < 0.35 else 0
    elif profile == "eco_raid_scavenge":
        status, clean = "victory", True
        tnb_loot = rng.randint(2, 4)
        scars = [{"zoneId": zone, "unitDefName": "armmex", "destroyed": True, "damageFrac": 1.0}]
        survivors = {"corthud": 4}
        # mark as raid-ish for histogram (intent may still say seize)
        kind = "eco_raid"
    elif profile == "defeat":
        status, success, clean, extract = "defeat", False, False, "failed"
        named = [{"charId": "vane", "outcome": "wounded"}]
        tnb_lost = rng.randint(1, 3)
        survivors = {}
        loan_hp = {}
    else:
        status = "victory"

    # Apply loot/lost to bank field gadget style
    if success:
        tnb_bank = tnb_bank + tnb_loot
    else:
        tnb_bank = max(0, tnb_bank - tnb_lost)

    result: Dict[str, Any] = {
        "schemaVersion": "verdance-match-result/1.0",
        "campaignId": state.get("campaignId") or "verdance_ashes",
        "resultKey": key,
        "missionId": mission_id,
        "missionNumber": mission_n,
        "mapId": map_id,
        "deploymentMapId": map_id,
        "status": status,
        "success": success,
        "cleanExtract": clean,
        "extractionStatus": extract,
        "targetZoneId": zone,
        "patron": "nullmercs",
        "against": against,
        "objectiveArchetype": kind,
        "playerSurvivors": survivors,
        "loanUnitHp": loan_hp,
        "tenebriumBank": tnb_bank,
        "tenebriumLooted": tnb_loot,
        "tenebriumLost": tnb_lost,
        "tenebriumSpent": 0,
        "shellScars": scars,
        "namedOutcomes": named,
        "elapsedMinutes": round(rng.uniform(8.0, 22.0), 2),
        "elapsedFrames": int(rng.uniform(8, 22) * 1800),
        "sessionMode": "same_map",
        "occupationModel": "living_shell",
        "nodeClaimed": node_claimed,
        "pocketCleared": pocket,
        "capturePhase": capture_phase,
        "captureMode": "clear_hold_shell" if node_claimed or kind in ("seize_lane", "gate_control", "hold_plateau") else None,
        "regrowWaves": rng.randint(1, 3) if node_claimed else 0,
        "freeTnbMint": False,
        "destroyedObjectiveIds": [zone] if success and zone else [],
        "simProfile": profile,
    }
    return result


def _clear_sortie_stamps(ws: Path) -> None:
    for name in ("next_sortie_order.json", "next_sortie_choice.json"):
        p = ws / "outbox" / name
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def run_campaign(
    workspace: Path,
    *,
    sorties: int = 8,
    seed: int = 0,
    home_map: str = "koom_valley",
    hours_between: float = 0.75,
    profiles: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Run N sorties in an isolated temp workspace; return scorecard dict."""
    rng = random.Random(seed)
    tw = _seed_workspace(workspace)
    try:
        state = _fresh_state(tw, home_map=home_map)
        history: List[Dict[str, Any]] = []
        contract_hist: Dict[str, int] = {}
        pushback_all: List[str] = []

        for i in range(sorties):
            _clear_sortie_stamps(tw)
            # Power response before intent
            strength = wt.player_strength(state)
            wt.power_response(state, strength)

            intent = engine.materialize_next_intent(state, tw)
            intent = wt.apply_power_to_intent(intent, state)
            map_id = str(intent.get("mapId") or home_map)
            obj = intent.get("objectiveTarget") if isinstance(intent.get("objectiveTarget"), dict) else {}
            kind = str((obj or {}).get("kind") or intent.get("objective") or "?")
            zone = str((obj or {}).get("targetZoneId") or "")
            contract_hist[kind] = contract_hist.get(kind, 0) + 1

            if profiles and i < len(profiles):
                profile = profiles[i]
            else:
                profile = _pick_profile(rng, strength, i)

            result = synthesize_result(intent, state, profile, rng=rng, sortie_index=i + 1)
            state2, report, next_intent, events = engine.process_result(
                state, result, None, tw, None
            )
            state = state2
            success = bool(report.get("processed")) and result.get("success")
            # Attachments (process_result may not call us yet — always apply)
            att_delta = att_mod.update_attachments_from_result(
                state,
                result,
                success=bool(result.get("success")),
                zone_flipped=bool(report.get("zoneFlipped") or report.get("nodeClaimed")),
            )
            # World tick between sorties
            tick = wt.world_tick(
                state,
                hours_offline=hours_between,
                map_id=map_id,
                rest=(profile in ("defeat", "hero_wound", "fail_extract") and rng.random() < 0.4),
            )
            for ev in (tick.get("power") or {}).get("pushbackEvents") or []:
                if ev not in pushback_all:
                    pushback_all.append(ev)

            clash = report.get("offscreenClash") or tick.get("clash") or {}
            history.append(
                {
                    "i": i,
                    "profile": profile,
                    "mapId": map_id,
                    "zoneId": zone,
                    "kind": kind,
                    "status": result.get("status"),
                    "success": result.get("success"),
                    "nodeClaimed": result.get("nodeClaimed"),
                    "tenebriumBank": result.get("tenebriumBank"),
                    "processed": report.get("processed"),
                    "zoneFlipped": report.get("zoneFlipped"),
                    "sessionHomeMap": state.get("sessionHomeMap"),
                    "attMemories": list(att_delta.get("memories") or [])[:2],
                    "pushback": list((tick.get("power") or {}).get("pushbackEvents") or []),
                    "q7": (state.get("graph") or {}).get("q7_resource_scarcity"),
                    "q0": (state.get("graph") or {}).get("q0_armada_cortex"),
                    "offscreenBands": (report.get("offscreenTick") or {}).get("bands"),
                    "clashes": clash.get("clashes"),
                    "clashFlips": clash.get("flips"),
                    "bpAccess": (report.get("bpAccess") or {}).get("maxPlayerBuildPower"),
                }
            )

        end_strength = wt.player_strength(state)
        graph = state.get("graph") or {}
        att = att_mod.fair_dossier(state)
        commerce = state.get("commerce") or {}
        claims = 0
        for v in (state.get("nodeClaims") or {}).values():
            if isinstance(v, list):
                claims += len(v)
        for v in (state.get("claimedNodes") or {}).values():
            if isinstance(v, dict):
                claims += len(v)
            elif isinstance(v, list):
                claims += len(v)
        front = state.get("frontEvents") or []
        clash_events = [e for e in front if isinstance(e, dict) and "clash" in str(e.get("type") or "").lower()]
        access = engine.bp_access(state)
        return {
            "seed": seed,
            "homeMap": home_map,
            "sorties": sorties,
            "contractHistogram": contract_hist,
            "history": history,
            "end": {
                "tenebrium": commerce.get("tenebrium"),
                "credits": commerce.get("credits"),
                "nodeClaims": claims,
                "sessionHomeMap": state.get("sessionHomeMap"),
                "q0": graph.get("q0_armada_cortex"),
                "q2": graph.get("q2_void_structure"),
                "q6": graph.get("q6_contested"),
                "q7": graph.get("q7_resource_scarcity"),
                "strengthComposite": end_strength.get("composite"),
                "missionNumber": state.get("missionNumber"),
                "clockMinutes": state.get("campaignClockMinutes"),
                "bpAccess": access,
                "offscreenClashEvents": len(clash_events),
                "frontEvents": len(front),
                "lastOffscreenClash": state.get("lastOffscreenClash"),
            },
            "attachments": att,
            "pushbackEvents": pushback_all,
            "worldResponse": state.get("worldResponse"),
        }
    finally:
        shutil.rmtree(tw, ignore_errors=True)


def divergence_report(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare multi-seed ends: cluster-ish diversity score."""
    if not runs:
        return {"seeds": 0, "diverse": False}
    tnb = [r["end"].get("tenebrium") for r in runs]
    q0 = [r["end"].get("q0") for r in runs]
    claims = [r["end"].get("nodeClaims") for r in runs]
    homes = {r["end"].get("sessionHomeMap") for r in runs}
    kinds = set()
    for r in runs:
        kinds.update((r.get("contractHistogram") or {}).keys())

    def _spread(vals: List[Any]) -> float:
        nums = [float(v) for v in vals if v is not None]
        if len(nums) < 2:
            return 0.0
        return max(nums) - min(nums)

    # Simple cluster count by (tnb bucket, claim bucket, q0 polarity)
    clusters = set()
    for r in runs:
        e = r["end"]
        tb = int(float(e.get("tenebrium") or 0) // 3)
        cb = int(float(e.get("nodeClaims") or 0))
        qp = "arm" if float(e.get("q0") or 0.5) < 0.45 else ("cor" if float(e.get("q0") or 0.5) > 0.55 else "mid")
        clusters.add((tb, min(cb, 4), qp))

    return {
        "seeds": len(runs),
        "tnbSpread": _spread(tnb),
        "q0Spread": _spread(q0),
        "claimSpread": _spread(claims),
        "homeMaps": sorted(str(h) for h in homes if h),
        "contractKinds": sorted(kinds),
        "clusterCount": len(clusters),
        "clusters": [list(c) for c in sorted(clusters)],
        "diverse": len(clusters) >= min(3, len(runs)),
        "pushbackUnion": sorted({e for r in runs for e in (r.get("pushbackEvents") or [])}),
    }


def fun_score(run: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristic fun for one run (LLM-readability + drama)."""
    hist = run.get("history") or []
    wins = sum(1 for h in hist if h.get("success"))
    fails = sum(1 for h in hist if not h.get("success"))
    wounds = 0
    for h in hist:
        if h.get("profile") in ("hero_wound", "bloody_win"):
            wounds += 1
    att = run.get("attachments") or {}
    mem_n = 0
    for a in (att.get("agents") or {}).values():
        if isinstance(a, dict):
            mem_n += len(a.get("memoryLines") or [])
    push = len(run.get("pushbackEvents") or [])
    kinds = len(run.get("contractHistogram") or {})
    # entropy of outcomes
    profiles = [h.get("profile") for h in hist]
    uniq = len(set(profiles))
    score = (
        0.2 * min(1.0, uniq / 5.0)
        + 0.2 * min(1.0, kinds / 3.0)
        + 0.15 * min(1.0, push / 4.0)
        + 0.15 * min(1.0, mem_n / 8.0)
        + 0.15 * (1.0 if wins and fails else 0.4)  # mixed outcomes
        + 0.15 * min(1.0, wounds / 2.0)
    )
    return {
        "score": round(score, 3),
        "wins": wins,
        "fails": fails,
        "uniqueProfiles": uniq,
        "contractKinds": kinds,
        "pushbackEvents": push,
        "memoryLines": mem_n,
        "drama": "mixed" if wins and fails else ("stomp" if wins > fails else "rough"),
    }


_MAP_ROTATE = (
    "koom_valley",
    "greenest_fields",
    "eye_of_horus",
    "all_that_simmers",
    "ancient_bastion",
    "tabula",
    "the_rock_jungle",
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Kernel multi-sortie campaign sim")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--sorties", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0, help="base seed (seeds uses base..base+n-1)")
    ap.add_argument("--map", default="koom_valley", dest="home_map")
    ap.add_argument(
        "--rotate-maps",
        action="store_true",
        help="rotate home map per seed for multi-seed divergence",
    )
    ap.add_argument("--hours-between", type=float, default=0.75)
    ap.add_argument("--write", action="store_true", help="write headless_runs + outbox summary")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve()
    runs: List[Dict[str, Any]] = []
    rotate = bool(args.rotate_maps) or args.seeds >= 3
    for i in range(max(1, args.seeds)):
        s = args.seed + i
        home = _MAP_ROTATE[i % len(_MAP_ROTATE)] if rotate else args.home_map
        print(f"[kernel_sim] seed={s} sorties={args.sorties} map={home}", flush=True)
        run = run_campaign(
            ws,
            sorties=args.sorties,
            seed=s,
            home_map=home,
            hours_between=args.hours_between,
        )
        run["fun"] = fun_score(run)
        runs.append(run)
        e = run["end"]
        print(
            f"  end tnb={e.get('tenebrium')} claims={e.get('nodeClaims')} "
            f"q7={e.get('q7')} strength={e.get('strengthComposite')} fun={run['fun']['score']}",
            flush=True,
        )

    div = divergence_report(runs)
    out = {
        "schemaVersion": "verdance-kernel-sim/1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ws),
        "runs": runs,
        "divergence": div,
        "meanFun": round(sum(r["fun"]["score"] for r in runs) / max(1, len(runs)), 3),
    }
    print(json.dumps({"divergence": div, "meanFun": out["meanFun"]}, indent=2))

    if args.write or args.seeds > 1:
        stamp = _utc()
        run_dir = ws / "headless_runs" / f"kernel_sim_{stamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        latest = ws / "outbox" / "kernel_sim.latest.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        # slim latest
        slim = {
            "schemaVersion": out["schemaVersion"],
            "generatedAt": out["generatedAt"],
            "divergence": div,
            "meanFun": out["meanFun"],
            "runDir": str(run_dir),
            "ends": [r["end"] for r in runs],
            "fun": [r["fun"] for r in runs],
            "nightWorld": {
                "bpAccessEnds": [(r.get("end") or {}).get("bpAccess") for r in runs],
                "clashEvents": [(r.get("end") or {}).get("offscreenClashEvents") for r in runs],
                "frontEvents": [(r.get("end") or {}).get("frontEvents") for r in runs],
            },
        }
        latest.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
        night = ws / "outbox" / "night_world.latest.json"
        night.write_text(
            json.dumps(
                {
                    "schemaVersion": "verdance-night-world/1.0",
                    "generatedAt": out["generatedAt"],
                    "meanFun": out["meanFun"],
                    "divergence": div,
                    "ends": [r["end"] for r in runs],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {run_dir / 'report.json'}", flush=True)
        print(f"wrote {latest}", flush=True)
        print(f"wrote {night}", flush=True)

    # Exit 0 if diverse enough when multi-seed; single seed always 0 if finished
    if args.seeds >= 3 and not div.get("diverse"):
        print("WARN: multi-seed not diverse enough (clusterCount < 3)", flush=True)
        return 0  # still success for infra; warn only
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
