#!/usr/bin/env python3
"""Proxy-player campaign — quantum-BAR-AI sits the player seat; enemies are Simple/BARb.

No human, no spring.exe required. Drives the *real* story engine:

  materialize_next_intent → fair_sim (quantum proxy) → match_result → process_result
  → world_tick (offscreen clash + multirate)

Enemy styles map to BAR controllers for later headless A/B:
  simple     → SimpleAI / simple
  barbarian  → BARbarIAn aggressive

Usage:
  set PYTHONPATH=tools;C:\\Users\\Luke Spooner\\ws-win\\umwelt\\src
  python tools/proxy_campaign_v1.py --sorties 6 --seeds 2 --enemy both --write
  python tools/proxy_campaign_v1.py --sorties 4 --enemy simple --seed 11 --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import attachments_v1 as att_mod  # noqa: E402
import kernel_campaign_sim_v1 as ksim  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402
import world_tick_v1 as wt  # noqa: E402

# ---------------------------------------------------------------------------
# Enemy styles (BAR seat mapping)
# ---------------------------------------------------------------------------

ENEMY_STYLES: Dict[str, Dict[str, Any]] = {
    "simple": {
        "label": "SimpleAI",
        "bar_controller": "simple",
        "enemy_scale_mul": 1.05,
        "enemy_start_strength": 0.55,
        "player_start_strength": 0.72,
        "fortified_kinds": frozenset({"hold_plateau", "siege", "gate_control"}),
        "note": "Stock SimpleAI: moderate screen, slower counter",
    },
    "barbarian": {
        "label": "BARb_aggressive",
        "bar_controller": "barbarian_aggressive",
        "enemy_scale_mul": 1.45,
        "enemy_start_strength": 0.72,
        "player_start_strength": 0.70,
        "fortified_kinds": frozenset({"hold_plateau", "siege", "gate_control", "seize_lane"}),
        "note": "BARbarIAn aggressive: higher mass, pushy counters",
    },
}

MAP_LABELS = {
    "koom_valley": "Koom Valley",
    "greenest_fields": "Greenest Fields",
    "eye_of_horus": "Eye of Horus",
    "all_that_simmers": "All That Simmers",
    "ancient_bastion": "Ancient Bastion",
    "tabula": "Tabula",
    "the_rock_jungle": "The Rock Jungle",
}

NO_BASE_KINDS = frozenset(
    {
        "eco_raid",
        "strike_relay",
        "seize_lane",
        "gate_control",
        "hold_plateau",
        "survive_wilds",
    }
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ensure_umwelt() -> None:
    """Make quantum_bar_ai importable (needs umwelt on path)."""
    candidates = [
        Path(r"C:\Users\Luke Spooner\ws-win\umwelt\src"),
        Path.home() / "ws-win" / "umwelt" / "src",
        TOOLS.parent.parent / "ws-win" / "umwelt" / "src",
    ]
    for c in candidates:
        if c.is_dir() and str(c) not in sys.path:
            sys.path.insert(0, str(c))
    try:
        import umwelt  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "umwelt not found. Add ws-win\\umwelt\\src to PYTHONPATH.\n"
            f"  tried: {[str(c) for c in candidates]}\n"
            f"  error: {e}"
        ) from e


def intent_to_arc_mission(
    intent: Dict[str, Any],
    state: Dict[str, Any],
    *,
    enemy_style: str,
    difficulty: float,
    duration_ticks: int,
    sortie_index: int,
) -> Any:
    """Build a fair-sim ArcMission from a story-engine mission intent."""
    from quantum_bar_ai.fair_obs import PlayerFacingCard
    from quantum_bar_ai.first_arc import ArcMission, SimTruth
    from quantum_bar_ai.lane_war import geometry_for_map

    style = ENEMY_STYLES[enemy_style]
    map_id = str(intent.get("mapId") or state.get("sessionHomeMap") or "koom_valley")
    obj = intent.get("objectiveTarget") if isinstance(intent.get("objectiveTarget"), dict) else {}
    kind = str((obj or {}).get("kind") or intent.get("objective") or "seize_lane")
    zone = str((obj or {}).get("targetZoneId") or intent.get("targetZoneId") or f"Z_{sortie_index}")
    deploy = str(
        intent.get("deploymentZoneId")
        or intent.get("deployZoneId")
        or (intent.get("fromZoneIds") or [None])[0]
        or "DEPLOY"
    )
    mission_id = str(intent.get("missionId") or state.get("currentMissionId") or f"va_{sortie_index:03d}")
    title = str(intent.get("title") or intent.get("missionTitle") or f"{MAP_LABELS.get(map_id, map_id)} — {kind}")
    d = max(0.5, float(difficulty))
    fortified = kind in style["fortified_kinds"]
    no_base = kind in NO_BASE_KINDS

    threats = {
        "simple": "Enemy holds with SimpleAI — predictable screen, slower push.",
        "barbarian": "Enemy fields BARbarIAn aggressive — heavy counters, tempo pressure.",
    }.get(enemy_style, "Hostile AI.")

    card = PlayerFacingCard(
        id=mission_id,
        title=title,
        kind=kind,
        map_name=MAP_LABELS.get(map_id, map_id.replace("_", " ").title()),
        deploy_label=deploy,
        objective_label=zone,
        extraction_label="Rim exfil",
        situation=(
            f"Proxy sortie on {MAP_LABELS.get(map_id, map_id)}. "
            f"Contract {kind} vs {style['label']}. Theater pressure is live."
        ),
        objective_text=str((obj or {}).get("summary") or f"Complete {kind} at {zone}."),
        how_to_win=(
            "Read the HUD. Probe, flank, or push as mood allows. Extract when the mark is yours. "
            f"Soft clock ~{max(8, duration_ticks // 8)} min."
        ),
        threats=threats,
        allies="Ashwalker strike team (Vane + Ketha).",
        plain_objective=f"{kind}: {zone}",
        soft_clock_minutes=max(8, duration_ticks // 8),
        no_base_building=no_base,
        briefing_lines=[
            {"speaker": "ketha", "text": "No spooner tonight — we run the graph."},
            {"speaker": "vane", "text": f"Enemy seat is {style['label']}. Fight the plan, not the fog."},
        ],
    )
    truth = SimTruth(
        enemy_scale=d * float(style["enemy_scale_mul"]),
        fortified=fortified,
        duration_ticks=int(duration_ticks),
        player_start_strength=float(style["player_start_strength"]),
        enemy_start_strength=float(style["enemy_start_strength"]),
        difficulty_label=f"{enemy_style}@d{d:.2f}",
    )
    mission = ArcMission(
        card=card,
        truth=truth,
        map_id=map_id,
        deploy_zone=deploy,
        objective_id=zone,
    )
    # Lane geometry when seize/hold — same as fair campaign
    if kind in ("seize_lane", "hold_plateau", "gate_control", "multipressure"):
        try:
            geo = geometry_for_map(map_id)
            if geo is not None:
                mission.lane_geometry = geo
        except Exception:
            pass
    return mission


def fair_to_match_result(
    fair: Any,
    intent: Dict[str, Any],
    state: Dict[str, Any],
    *,
    enemy_style: str,
    sortie_index: int,
    rng: random.Random,
) -> Dict[str, Any]:
    """Map FairMissionResult → verdance-match-result/1.0 for process_result."""
    map_id = str(intent.get("mapId") or state.get("sessionHomeMap") or "koom_valley")
    obj = intent.get("objectiveTarget") if isinstance(intent.get("objectiveTarget"), dict) else {}
    zone = str((obj or {}).get("targetZoneId") or intent.get("targetZoneId") or "")
    kind = str((obj or {}).get("kind") or intent.get("objective") or "seize_lane")
    mission_id = str(intent.get("missionId") or fair.mission_id or f"va_{sortie_index:03d}")
    mission_n = int(intent.get("missionNumber") or state.get("missionNumber") or sortie_index)

    verdict = str(fair.verdict or "")
    progress = float(fair.progress or 0.0)
    heroes = float(fair.heroes_alive_frac or 0.0)
    won = bool(getattr(fair, "won", False) or verdict in ("extracted", "objective_complete"))

    if won and progress >= 0.9 and heroes >= 0.75:
        status, success, clean, extract = "victory", True, True, "clean"
        profile = "clean_win"
    elif won and progress >= 0.85:
        status, success, clean, extract = "victory", True, False, "contested"
        profile = "bloody_win" if heroes < 0.75 else "node_claim"
    elif progress >= 0.55 and heroes > 0:
        status, success, clean, extract = "partial", True, False, "contested"
        profile = "partial"
    elif verdict == "heroes_dead" or heroes <= 0:
        status, success, clean, extract = "defeat", False, False, "failed"
        profile = "defeat"
    else:
        status, success, clean, extract = "defeat", False, False, "failed"
        profile = "fail_extract"

    node_claimed = won and kind in ("seize_lane", "gate_control", "hold_plateau") and progress >= 0.88
    if node_claimed:
        profile = "node_claim"

    tnb_bank = int((state.get("commerce") or {}).get("tenebrium") or 0)
    tnb_loot = 0
    tnb_lost = 0
    if success:
        if kind == "eco_raid":
            tnb_loot = rng.randint(1, 3)
            profile = "eco_raid_scavenge" if won else profile
        elif node_claimed:
            tnb_loot = 1 if rng.random() < 0.4 else 0
        else:
            tnb_loot = rng.randint(0, 2)
        tnb_bank = tnb_bank + tnb_loot
    else:
        tnb_lost = rng.randint(0, 2)
        tnb_bank = max(0, tnb_bank - tnb_lost)

    named: List[Dict[str, Any]] = []
    if heroes < 0.6 and heroes > 0:
        named.append({"charId": "ketha" if rng.random() < 0.5 else "vane", "outcome": "wounded"})
        if profile == "clean_win":
            profile = "hero_wound"
    if heroes <= 0:
        named = [{"charId": "vane", "outcome": "wounded"}, {"charId": "ketha", "outcome": "wounded"}]

    survivors = {"corthud": max(0, int(round(5 * heroes))), "legbal": max(0, int(round(2 * heroes)))}
    loan_hp = {
        "corthud": {
            "count": survivors["corthud"],
            "avgHpFrac": max(0.15, heroes * 0.85),
            "minHpFrac": max(0.1, heroes * 0.5),
        }
    }
    scars: List[Dict[str, Any]] = []
    if success and zone:
        scars = [{"zoneId": zone, "unitDefName": "armmex", "destroyed": True, "damageFrac": 1.0}]
        if node_claimed:
            scars.append({"zoneId": zone, "unitDefName": "armhlt", "destroyed": True, "damageFrac": 1.0})

    style = ENEMY_STYLES[enemy_style]
    hist = {}
    for a in fair.actions or []:
        hist[a] = hist.get(a, 0) + 1

    # BAR seat plan for the *player* proxy (what we'd run in headless A/B)
    try:
        from quantum_bar_ai.bar_map import plan_from_action_histogram

        player_plan = plan_from_action_histogram(list(fair.actions or []), mission_kind=kind).as_dict()
    except Exception:
        player_plan = {"player_controller": "simple", "reason": "fallback"}

    key = f"proxy|{mission_id}|{mission_n}|{enemy_style}|{profile}|{rng.randint(0, 99999)}"
    elapsed_min = max(4.0, float(fair.ticks or 40) * 0.12)

    return {
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
        "against": "armada",
        "objectiveArchetype": kind,
        "playerSurvivors": survivors,
        "loanUnitHp": loan_hp,
        "tenebriumBank": tnb_bank,
        "tenebriumLooted": tnb_loot,
        "tenebriumLost": tnb_lost,
        "tenebriumSpent": 0,
        "shellScars": scars,
        "namedOutcomes": named,
        "elapsedMinutes": round(elapsed_min, 2),
        "elapsedFrames": int(elapsed_min * 1800),
        "sessionMode": "same_map",
        "occupationModel": "living_shell",
        "nodeClaimed": node_claimed,
        "pocketCleared": node_claimed,
        "capturePhase": "claimed" if node_claimed else "idle",
        "captureMode": "clear_hold_shell" if node_claimed else None,
        "regrowWaves": rng.randint(1, 3) if node_claimed else 0,
        "freeTnbMint": False,
        "destroyedObjectiveIds": [zone] if success and zone else [],
        "simProfile": profile,
        "proxy": {
            "enemyStyle": enemy_style,
            "enemyBarController": style["bar_controller"],
            "playerBarPlan": player_plan,
            "fairVerdict": verdict,
            "fairProgress": progress,
            "heroesAliveFrac": heroes,
            "actionHistogram": hist,
            "ticks": fair.ticks,
            "backends": dict(getattr(fair, "backends", None) or {}),
        },
    }


def run_proxy_campaign(
    workspace: Path,
    *,
    sorties: int = 6,
    seed: int = 11,
    home_map: str = "the_rock_jungle",
    enemy_style: str = "simple",
    difficulty: float = 1.0,
    duration_ticks: int = 48,
    hours_between: float = 0.75,
    verbose: bool = False,
    collect_fair: bool = True,
) -> Dict[str, Any]:
    """One full proxy campaign against a single enemy style."""
    _ensure_umwelt()
    from umwelt.boot import build_engine
    from quantum_bar_ai.fair_sim import carry_from_fair, run_fair_mission
    from quantum_bar_ai.tool_agent import LocalToolAgent
    from quantum_bar_ai.world import player_proxy_spec

    if enemy_style not in ENEMY_STYLES:
        raise ValueError(f"unknown enemy_style {enemy_style!r}; use {list(ENEMY_STYLES)}")

    rng = random.Random(seed)
    tw = ksim._seed_workspace(workspace)
    t0 = time.time()
    try:
        state = ksim._fresh_state(tw, home_map=home_map)
        # Night-play defaults (already in default_v1_state, reinforce home)
        state["sessionHomeMap"] = home_map
        state["reputation"] = dict(state.get("reputation") or {})
        state["reputation"].setdefault("armada", 18)
        state["reputation"].setdefault("cortex", 70)

        agent = LocalToolAgent(use_bar_brain=True)
        um_engine = build_engine(spec=player_proxy_spec())
        carry: Dict[str, float] = {}
        history: List[Dict[str, Any]] = []
        contract_hist: Dict[str, int] = {}
        pushback_all: List[str] = []
        bar_plans: List[Dict[str, Any]] = []
        fair_dicts: List[Dict[str, Any]] = []

        for i in range(sorties):
            ksim._clear_sortie_stamps(tw)
            strength = wt.player_strength(state)
            wt.power_response(state, strength)

            intent = engine.materialize_next_intent(state, tw)
            intent = wt.apply_power_to_intent(intent, state)
            map_id = str(intent.get("mapId") or home_map)
            obj = intent.get("objectiveTarget") if isinstance(intent.get("objectiveTarget"), dict) else {}
            kind = str((obj or {}).get("kind") or intent.get("objective") or "?")
            zone = str((obj or {}).get("targetZoneId") or "")
            contract_hist[kind] = contract_hist.get(kind, 0) + 1

            mission = intent_to_arc_mission(
                intent,
                state,
                enemy_style=enemy_style,
                difficulty=difficulty,
                duration_ticks=duration_ticks,
                sortie_index=i + 1,
            )
            if verbose:
                print(
                    f"  sortie {i+1}/{sorties} {mission.id} {kind} @ {map_id} "
                    f"vs {enemy_style} ticks={duration_ticks}"
                )

            fair = run_fair_mission(
                mission,
                agent=agent,
                engine=um_engine,
                seed=seed + i * 17,
                carry=carry or None,
                verbose=False,
            )
            if collect_fair:
                fair_dicts.append(fair.as_dict())
            if fair.verdict != "heroes_dead":
                carry = carry_from_fair(fair)
            else:
                carry = {
                    "vane_hp": 0.55,
                    "ketha_hp": 0.55,
                    "player_strength": 0.58,
                    "cohesion_proxy": 0.6,
                    "eco_level": 0.2,
                }

            result = fair_to_match_result(
                fair, intent, state, enemy_style=enemy_style, sortie_index=i + 1, rng=rng
            )
            bar_plans.append(result.get("proxy") or {})

            state2, report, _next_intent, _events = engine.process_result(
                state, result, None, tw, None
            )
            state = state2
            att_mod.update_attachments_from_result(
                state,
                result,
                success=bool(result.get("success")),
                zone_flipped=bool(report.get("zoneFlipped") or report.get("nodeClaimed")),
            )
            tick = wt.world_tick(
                state,
                hours_offline=hours_between,
                map_id=map_id,
                rest=(not result.get("success") and rng.random() < 0.4),
            )
            for ev in (tick.get("power") or {}).get("pushbackEvents") or []:
                if ev not in pushback_all:
                    pushback_all.append(ev)

            clash = report.get("offscreenClash") or tick.get("clash") or {}
            history.append(
                {
                    "i": i,
                    "profile": result.get("simProfile"),
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
                    "fairVerdict": fair.verdict,
                    "fairProgress": fair.progress,
                    "heroes": fair.heroes_alive_frac,
                    "enemyStyle": enemy_style,
                    "playerController": (result.get("proxy") or {})
                    .get("playerBarPlan", {})
                    .get("player_controller"),
                    "enemyController": ENEMY_STYLES[enemy_style]["bar_controller"],
                    "clashes": clash.get("clashes"),
                    "clashFlips": clash.get("flips"),
                    "bpAccess": (report.get("bpAccess") or {}).get("maxPlayerBuildPower"),
                    "q7": (state.get("graph") or {}).get("q7_resource_scarcity"),
                    "q0": (state.get("graph") or {}).get("q0_armada_cortex"),
                }
            )
            if verbose:
                print(
                    f"    → {fair.verdict} prog={fair.progress:.2f} "
                    f"status={result.get('status')} tnb={result.get('tenebriumBank')}"
                )

        end_strength = wt.player_strength(state)
        graph = state.get("graph") or {}
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
        clash_events = [
            e for e in front if isinstance(e, dict) and "clash" in str(e.get("type") or "").lower()
        ]
        wins = sum(1 for h in history if h.get("success"))
        out: Dict[str, Any] = {
            "seed": seed,
            "homeMap": home_map,
            "enemyStyle": enemy_style,
            "enemyBarController": ENEMY_STYLES[enemy_style]["bar_controller"],
            "difficulty": difficulty,
            "durationTicks": duration_ticks,
            "sorties": sorties,
            "wins": wins,
            "winRate": round(wins / max(1, sorties), 3),
            "contractHistogram": contract_hist,
            "history": history,
            "barPlans": bar_plans,
            "elapsed_s": round(time.time() - t0, 2),
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
                "bpAccess": engine.bp_access(state),
                "offscreenClashEvents": len(clash_events),
                "frontEvents": len(front),
                "lastOffscreenClash": state.get("lastOffscreenClash"),
                "rep": {
                    "armada": (state.get("reputation") or {}).get("armada"),
                    "cortex": (state.get("reputation") or {}).get("cortex"),
                },
            },
            "pushbackEvents": pushback_all,
            "attachments": att_mod.fair_dossier(state),
        }
        if collect_fair:
            out["fairResults"] = fair_dicts
        return out
    finally:
        shutil.rmtree(tw, ignore_errors=True)


def compare_enemy_styles(
    workspace: Path,
    *,
    styles: Sequence[str],
    sorties: int,
    seeds: int,
    base_seed: int,
    home_map: str,
    difficulty: float,
    duration_ticks: int,
    hours_between: float,
    verbose: bool,
) -> Dict[str, Any]:
    """Multi-seed A/B: quantum proxy vs each enemy style."""
    runs: List[Dict[str, Any]] = []
    for style in styles:
        for s in range(seeds):
            seed = base_seed + s
            if verbose:
                print(f"\n=== proxy campaign seed={seed} enemy={style} ===")
            run = run_proxy_campaign(
                workspace,
                sorties=sorties,
                seed=seed,
                home_map=home_map,
                enemy_style=style,
                difficulty=difficulty,
                duration_ticks=duration_ticks,
                hours_between=hours_between,
                verbose=verbose,
            )
            run["fun"] = ksim.fun_score(run)
            runs.append(run)

    by_style: Dict[str, Any] = {}
    for style in styles:
        subset = [r for r in runs if r.get("enemyStyle") == style]
        if not subset:
            continue
        wr = [float(r.get("winRate") or 0) for r in subset]
        funs = [float((r.get("fun") or {}).get("score") or 0) for r in subset]
        tnbs = [float((r.get("end") or {}).get("tenebrium") or 0) for r in subset]
        clashes = [int((r.get("end") or {}).get("offscreenClashEvents") or 0) for r in subset]
        player_ctrl: Dict[str, int] = {}
        for r in subset:
            for h in r.get("history") or []:
                c = h.get("playerController") or "?"
                player_ctrl[c] = player_ctrl.get(c, 0) + 1
        by_style[style] = {
            "runs": len(subset),
            "meanWinRate": round(sum(wr) / len(wr), 3),
            "meanFun": round(sum(funs) / len(funs), 3),
            "meanTnb": round(sum(tnbs) / len(tnbs), 2),
            "meanClashEvents": round(sum(clashes) / len(clashes), 2),
            "playerControllerHist": player_ctrl,
            "barEnemy": ENEMY_STYLES[style]["bar_controller"],
            "divergence": ksim.divergence_report(subset),
        }

    # Head-to-head delta when both styles present
    h2h = None
    if "simple" in by_style and "barbarian" in by_style:
        h2h = {
            "winRateDelta_barb_minus_simple": round(
                by_style["barbarian"]["meanWinRate"] - by_style["simple"]["meanWinRate"], 3
            ),
            "funDelta_barb_minus_simple": round(
                by_style["barbarian"]["meanFun"] - by_style["simple"]["meanFun"], 3
            ),
            "note": (
                "Negative winRateDelta means barbarian is harder for the proxy "
                "(expected). Fun should stay playable on both."
            ),
        }

    # Collect fair tapes across runs for bar_brain + UL train
    fair_all: List[Dict[str, Any]] = []
    for r in runs:
        for fd in r.get("fairResults") or []:
            fair_all.append(fd)
        # drop bulky tapes from per-run payload (kept in fairTrainReport)
        r.pop("fairResults", None)

    fair_train_report = None
    if fair_all:
        fair_train_report = {
            "results": [
                {
                    "won": bool(d.get("won") or d.get("verdict") in ("extracted", "objective_complete")),
                    "player_card": d.get("player_card") or {},
                    "tape": d.get("tape") or [],
                    "progress": d.get("progress"),
                    "heroes_alive_frac": d.get("heroes_alive_frac"),
                    "verdict": d.get("verdict"),
                    "mission_id": d.get("mission_id"),
                }
                for d in fair_all
            ],
            "source": "proxy_campaign_v1",
            "nMissions": len(fair_all),
        }

    return {
        "schemaVersion": "verdance-proxy-campaign/1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "player": "quantum_bar_ai.LocalToolAgent",
        "sorties": sorties,
        "seeds": seeds,
        "baseSeed": base_seed,
        "homeMap": home_map,
        "difficulty": difficulty,
        "durationTicks": duration_ticks,
        "styles": list(styles),
        "byStyle": by_style,
        "headToHead": h2h,
        "runs": runs,
        "fairTrainReport": fair_train_report,
    }


def self_test(workspace: Path) -> int:
    """Fast smoke: 2 sorties × simple, assert process_result path works."""
    _ensure_umwelt()
    rep = run_proxy_campaign(
        workspace,
        sorties=2,
        seed=3,
        home_map="the_rock_jungle",
        enemy_style="simple",
        difficulty=1.0,
        duration_ticks=24,
        verbose=False,
    )
    assert rep["sorties"] == 2, rep
    assert len(rep["history"]) == 2, rep
    assert all(h.get("processed") for h in rep["history"]), rep["history"]
    assert "bpAccess" in (rep.get("end") or {}), rep.get("end")
    print("proxy_campaign_v1 self_test OK")
    print(
        f"  wins={rep['wins']}/{rep['sorties']} "
        f"tnb={(rep.get('end') or {}).get('tenebrium')} "
        f"clashes={(rep.get('end') or {}).get('offscreenClashEvents')}"
    )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Proxy-player campaign (quantum-BAR-AI vs Simple/BARb)")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--sorties", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--seed", type=int, default=11, help="base seed")
    ap.add_argument("--map", default="the_rock_jungle", dest="home_map")
    ap.add_argument(
        "--enemy",
        default="both",
        choices=["simple", "barbarian", "both"],
        help="enemy AI style (both = A/B)",
    )
    ap.add_argument("--difficulty", type=float, default=1.0)
    ap.add_argument("--ticks", type=int, default=48, help="fair-sim ticks per sortie")
    ap.add_argument("--hours-between", type=float, default=0.75)
    ap.add_argument("--write", action="store_true", help="write headless_runs + outbox")
    ap.add_argument(
        "--train",
        action="store_true",
        help="train bar_brain histogram + UL width_action+eco_action",
    )
    ap.add_argument("--no-train", action="store_true", help="skip training even when --write")
    ap.add_argument("--hose", action="store_true", help="write hive residual vitals")
    ap.add_argument("--no-hose", action="store_true", help="skip residual hose")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    ws = Path(args.workspace).resolve()
    if args.self_test:
        return self_test(ws)

    styles: List[str]
    if args.enemy == "both":
        styles = ["simple", "barbarian"]
    else:
        styles = [args.enemy]

    # Default: train+hose when writing (overnight path)
    do_train = bool(args.train or (args.write and not args.no_train))
    do_hose = bool(args.hose or (args.write and not args.no_hose))

    report = compare_enemy_styles(
        ws,
        styles=styles,
        sorties=args.sorties,
        seeds=args.seeds,
        base_seed=args.seed,
        home_map=args.home_map,
        difficulty=args.difficulty,
        duration_ticks=args.ticks,
        hours_between=args.hours_between,
        verbose=args.verbose,
    )

    train_info: Optional[Dict[str, Any]] = None
    if do_train and report.get("fairTrainReport"):
        try:
            _ensure_umwelt()
            from quantum_bar_ai.bar_brain_ul import (
                read_hive_doctrine_posture,
                train_report_with_ul,
            )

            posture = read_hive_doctrine_posture(ws)
            train_info = train_report_with_ul(
                report["fairTrainReport"],
                workspace=ws,
                save=True,
                doctrine_posture=posture,
            )
            report["train"] = {
                "histogramSamples": train_info.get("histogramSamples"),
                "wins": train_info.get("wins"),
                "losses": train_info.get("losses"),
                "ul": train_info.get("ul"),
                "doctrinePosture": train_info.get("doctrinePosture"),
                "nMissions": (report.get("fairTrainReport") or {}).get("nMissions"),
                "ulFamily": "width_action+eco_action",
            }
            # mission learn tape (every mission in this unit)
            try:
                import organic_pathway_v1 as pathway

                ran = __import__("os").environ.get("BAR_MUSCLE_NODE") or "unknown"
                rows = pathway.mission_rows_from_train(
                    train_info, proxy_report=report, ran_on=str(ran)
                )
                if rows:
                    tape_info = pathway.append_mission_learn_rows(rows, workspace=ws)
                    report["train"]["missionLearnTape"] = tape_info
            except Exception as te:
                report["train"]["missionLearnTapeError"] = str(te)
            print(
                f"\n=== bar_brain+UL train === samples={train_info.get('histogramSamples')} "
                f"ulUpdates={(train_info.get('ul') or {}).get('ulUpdateCount')} "
                f"meanSigma={(train_info.get('ul') or {}).get('ulMeanSigma')} "
                f"width={(train_info.get('ul') or {}).get('ulWidthUpdates')} "
                f"eco={(train_info.get('ul') or {}).get('ulEcoUpdates')} "
                f"doctrine={train_info.get('doctrinePosture')}"
            )
        except Exception as e:
            report["trainError"] = str(e)
            print(f"train failed (non-fatal): {e}")

    print("\n=== proxy campaign summary ===")
    print(f"player=quantum LocalToolAgent  sorties={args.sorties} seeds={args.seeds}")
    for style, row in (report.get("byStyle") or {}).items():
        print(
            f"  vs {style:10s} ({row.get('barEnemy')}): "
            f"winRate={row.get('meanWinRate')} fun={row.get('meanFun')} "
            f"tnb={row.get('meanTnb')} clashes={row.get('meanClashEvents')} "
            f"playerCtrl={row.get('playerControllerHist')}"
        )
    if report.get("headToHead"):
        print(f"  H2H: {report['headToHead']}")

    if args.write:
        stamp = _utc_stamp()
        out = ws / "headless_runs" / f"proxy_campaign_{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        # full report without giant fair tapes in latest; keep tapes only in train path already consumed
        full = copy.deepcopy(report)
        full.pop("fairTrainReport", None)
        path = out / "report.json"
        path.write_text(json.dumps(full, indent=2, ensure_ascii=False), encoding="utf-8")
        latest = ws / "outbox" / "proxy_campaign.latest.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        # slim latest (drop full run histories for size)
        slim = copy.deepcopy(full)
        for r in slim.get("runs") or []:
            r.pop("history", None)
            r.pop("barPlans", None)
            r.pop("attachments", None)
        latest.write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path}")
        print(f"wrote {latest}")

    if do_hose and (args.write or args.hose):
        try:
            import hive_bar_residual_v1 as residual_mod

            # Prefer slim latest if written; else build from in-memory report
            residual = residual_mod.build_residual(report, workspace=ws)
            hose = residual_mod.write_residual(residual, ws, also_hive=True)
            report["residualHose"] = {"written": hose.get("written"), "skipped": hose.get("skipped")}
            for w in hose.get("written") or []:
                print(f"residual wrote {w}")
        except Exception as e:
            print(f"residual hose failed (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
