#!/usr/bin/env python3
"""Manifold co-evolution gym — proxy-player vs campaign-shape density membrane.

Overnight craft loop:
  1. Build campaign at current difficulty / width bias / disposition.
  2. Proxy (LocalToolAgent + bar_brain) plays fair campaign.
  3. Campaign density evolves from outcomes (PathKet + CampaignDensity).
  4. Proxy trains bar_brain from tapes.
  5. Craft controller retunes difficulty / width curve / decoy pressure so the
     campaign stays **clear early, wider late, beatable overall**.

Targets (tunable):
  - Arc 1 hard-win rate: 0.80 – 0.98
  - Arc 2: 0.55 – 0.85
  - Arc 3: 0.40 – 0.75
  - Overall: 0.55 – 0.85
  - Action diversity mean: >= 0.35
  - Path A/B/C not collapsed to one forever

Usage:
  python -m quantum_bar_ai.manifold_gym --gens 12 --seeds 2
  python -m quantum_bar_ai.manifold_gym --gens 40 --seeds 3 --hours 6
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bar_brain import BarBrain, BarBrainWeights, ingest_campaign_report, load_weights, save_weights
from .campaign import build_full_campaign
from .campaign_manifold import (
    CampaignRho,
    evolve_rho,
    mission_width_curve,
    solution_space_for,
)
from .craft_apply import CraftKnobs, craft_mission, knobs_width
from .fair_sim import play_missions
from .first_arc import ArcMission
from .lane_war import geometry_for_map
from .quantum_membrane import (
    CampaignDensity,
    DualMembraneState,
    PathKet,
    PredicateAmplitudes,
    path_hint_from_actions,
    solution_entropy_width,
    vector_diversity,
)
from .interference_tuner import (
    aggregate_craft_nudge,
    score_mission_interference,
)
from .anneal_paths import anneal_path_space, craft_nudge_from_anneal
from .schism_entangle import entangle_paths_for_schism, widen_solution_for_schism
from .suite import _workspace_root
from .tool_agent import LocalToolAgent


# ---------------------------------------------------------------------------
# Craft knobs live in craft_apply (shared with live campaign roll-in).
# ---------------------------------------------------------------------------

@dataclass
class CraftTargets:
    arc1_lo: float = 0.80
    arc1_hi: float = 0.98
    arc2_lo: float = 0.55
    arc2_hi: float = 0.85
    arc3_lo: float = 0.40
    arc3_hi: float = 0.75
    overall_lo: float = 0.55
    overall_hi: float = 0.85
    diversity_min: float = 0.32


def build_crafted_campaign(
    knobs: CraftKnobs,
    rho: CampaignRho,
    density: CampaignDensity,
    *,
    arcs: tuple[int, ...] = (1, 2, 3),
) -> list[ArcMission]:
    # use_craft=False so gym knobs (not pinned recipe) own the stamp each gen
    missions = build_full_campaign(difficulty=knobs.difficulty, arcs=arcs, use_craft=False)
    n = len(missions)
    for i, m in enumerate(missions):
        craft_mission(m, i, knobs, rho, density, n_missions=n)
    return missions


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _arc_of(mission_id: str) -> str:
    try:
        n = int(str(mission_id).split("_")[-1])
    except ValueError:
        return "0"
    if n <= 5:
        return "1"
    if n <= 10:
        return "2"
    return "3"


def analyze_report(rep: dict[str, Any], dual: DualMembraneState) -> dict[str, Any]:
    results = rep.get("results") or []
    by_arc: dict[str, dict[str, float]] = {
        "1": {"wins": 0, "total": 0},
        "2": {"wins": 0, "total": 0},
        "3": {"wins": 0, "total": 0},
    }
    diversities: list[float] = []
    path_hints: list[str] = []
    predicate_hits: dict[str, int] = {}
    decoy_hits = 0
    total_actions = 0

    for r in results:
        mid = r.get("mission_id") or ""
        arc = _arc_of(mid)
        if arc in by_arc:
            by_arc[arc]["total"] += 1
            if r.get("won"):
                by_arc[arc]["wins"] += 1
        actions = r.get("actions") or []
        diversities.append(vector_diversity(actions))
        card = r.get("player_card") or {}
        ph = path_hint_from_actions(actions, kind=card.get("kind"))
        if ph:
            path_hints.append(ph)
        total_actions += len(actions)
        # decoy-ish: TECH_UP spam on early strike
        card = r.get("player_card") or {}
        kind = card.get("kind") or ""
        if kind in ("eco_raid", "strike_relay"):
            decoy_hits += sum(1 for a in actions if a.startswith("BUILD") or a == "TECH_UP")
        # predicate scores from last tape row
        tape = r.get("tape") or []
        if tape:
            preds = (tape[-1].get("_truth") or {}).get("predicates") or {}
            for k, v in preds.items():
                if float(v) >= 0.72:
                    predicate_hits[k] = predicate_hits.get(k, 0) + 1

    def rate(a: str) -> float:
        t = by_arc[a]["total"]
        return by_arc[a]["wins"] / t if t else 0.0

    path_counts = {p: path_hints.count(p) for p in ("A", "B", "C")}
    path_entropy = 0.0
    if path_hints:
        from .quantum_membrane import shannon_entropy

        s = len(path_hints)
        ps = [path_counts[p] / s for p in ("A", "B", "C") if path_counts[p]]
        path_entropy = shannon_entropy(ps)

    overall = rep.get("hard_wins", 0) / max(1, rep.get("missions", 1))

    # InterferenceTuner batch (operator craft signal)
    ireports = []
    for r in results:
        card = r.get("player_card") or {}
        kind = card.get("kind") or "eco_raid"
        width = 0.3
        wb = card.get("width_band")
        if wb == "narrow":
            width = 0.25
        elif wb == "open":
            width = 0.55
        elif wb == "wide":
            width = 0.85
        tape = r.get("tape") or []
        preds = {}
        if tape:
            preds = (tape[-1].get("_truth") or {}).get("predicates") or {}
        ireports.append(
            score_mission_interference(
                kind=kind,
                width=width,
                predicate_scores={k: float(v) for k, v in preds.items()},
                predicates=list(preds.keys()),
                actions=r.get("actions") or [],
            )
        )
    inter_nudge = aggregate_craft_nudge(ireports)
    inter_summary = {
        "reward_multipath": sum(1 for x in ireports if x.recommended == "reward_multipath"),
        "punish_thrash": sum(1 for x in ireports if x.recommended == "punish_thrash"),
        "narrow_ok": sum(1 for x in ireports if x.recommended == "narrow_ok"),
        "nudge": inter_nudge,
    }

    return {
        "overall_win_rate": round(overall, 4),
        "arc_rates": {a: round(rate(a), 4) for a in ("1", "2", "3")},
        "diversity_mean": round(sum(diversities) / max(1, len(diversities)), 4),
        "path_hints": path_counts,
        "path_entropy": round(path_entropy, 4),
        "predicate_hits": predicate_hits,
        "decoy_action_count": decoy_hits,
        "interference": inter_summary,
        "campaign_density": dual.campaign.as_dict(),
        "path_ket": dual.path_ket.as_dict(),
        "belief": dual.belief.fair_dict(),
    }


# ---------------------------------------------------------------------------
# Evolve dual membrane from a played report
# ---------------------------------------------------------------------------

def evolve_dual_from_report(
    dual: DualMembraneState,
    rep: dict[str, Any],
    rho: CampaignRho,
) -> tuple[DualMembraneState, CampaignRho]:
    results = rep.get("results") or []
    n = max(1, len(results))
    for i, r in enumerate(results):
        won = bool(r.get("won"))
        actions = r.get("actions") or []
        kind = (r.get("player_card") or {}).get("kind") or "eco_raid"
        hint = path_hint_from_actions(actions, kind=kind)
        div = vector_diversity(actions)
        dual.campaign.evolve_after_mission(
            won=won,
            mission_index=i,
            path_hint=hint,
            n_missions=n,
            vector_diversity=div,
        )
        if hint:
            # gentle soft-measure — overnight runs were collapsing to pure |A⟩
            dual.path_ket.soft_measure(hint, strength=0.08 if won else 0.04)
            if won:
                dual.path_ket.phase_kick(("A", "B", "C").index(hint), 0.12)
            # anti-collapse: tiny feed to other paths
            for lab in ("A", "B", "C"):
                if lab != hint:
                    dual.path_ket.soft_measure(lab, strength=0.02)
        else:
            dual.path_ket.rotate(i % 3, 0.05 if won else -0.03)
        # periodic rephase of campaign density if one path > 80%
        pw = dual.campaign.path_weights()
        if max(pw.values()) > 0.8:
            dual.campaign.diag = [
                0.7 * dual.campaign.diag[j] + 0.1 for j in range(3)
            ]
            dual.campaign._renorm_diag()
            dual.campaign.rephase(0.08)

        # belief: observe last HUD if any
        tape = r.get("tape") or []
        if tape:
            last = tape[-1]
            dual.belief.observe_hud(last.get("hud") or {})
            # decoy POVM if many decoy actions
            if sum(1 for a in actions if a in ("TECH_UP", "RECLAIM")) > 4:
                dual.belief.apply_decoy_povm(0.12)

        # classical rho evolve too
        rho = evolve_rho(
            rho,
            won=won,
            mission_index=i,
            kind=kind,
            path_nudge=hint,
            n_missions=n,
        )

        # interference diagnostic (operator)
        if tape:
            preds = (tape[-1].get("_truth") or {}).get("predicates") or {}
            pa = PredicateAmplitudes.from_scores(preds, list(preds.keys()))
            # store lightly on dual via belief confusion if thrashing
            switches = sum(
                1
                for j in range(1, min(len(actions), 20))
                if actions[j] != actions[j - 1]
            )
            if switches > 12 and not won:
                dual.belief.confusion = min(1.0, dual.belief.confusion + 0.05)

    return dual, rho


# ---------------------------------------------------------------------------
# Craft controller — retune knobs toward targets
# ---------------------------------------------------------------------------

def retune_knobs(
    knobs: CraftKnobs,
    metrics: dict[str, Any],
    targets: CraftTargets,
) -> CraftKnobs:
    k = CraftKnobs(**knobs.as_dict())
    ar = metrics.get("arc_rates") or {}
    a1, a2, a3 = ar.get("1", 0.5), ar.get("2", 0.5), ar.get("3", 0.5)
    overall = metrics.get("overall_win_rate", 0.5)
    div = metrics.get("diversity_mean", 0.3)

    # Aggressive steps when steamrolled (100% clears) so craft moves overnight
    steamroll = overall >= 0.95
    step_d = 0.12 if steamroll else 0.06
    step_a = 0.08 if steamroll else 0.04

    # --- difficulty ---
    if overall > targets.overall_hi:
        k.difficulty = min(1.75, k.difficulty + step_d)
        k.enemy_aggro = min(1.65, k.enemy_aggro + step_a)
        if steamroll:
            # late missions get teeth faster
            k.decoy_pressure = min(2.0, k.decoy_pressure + 0.15)
            k.width_late = max(0.65, k.width_late - 0.03)
    elif overall < targets.overall_lo:
        k.difficulty = max(0.65, k.difficulty - 0.08)
        k.enemy_aggro = max(0.7, k.enemy_aggro - 0.06)

    # arc-specific width / curve + per-arc scales
    if a1 < targets.arc1_lo:
        k.width_early = max(0.08, k.width_early - 0.02)  # clearer early
        k.arc1_scale = max(0.7, k.arc1_scale - 0.06)
        k.difficulty = max(0.7, k.difficulty - 0.03)
    elif a1 > targets.arc1_hi:
        # early still free — keep vectors clear, nudge arc1 only
        k.width_early = min(0.28, k.width_early + 0.01)
        k.arc1_scale = min(1.15, k.arc1_scale + (0.05 if steamroll else 0.02))

    if a2 < targets.arc2_lo:
        # mid arc dying — ease hard (common overnight failure mode)
        step = 0.1 if a2 < 0.35 else 0.06
        k.arc2_scale = max(0.65, k.arc2_scale - step)
        k.decoy_pressure = max(0.8, k.decoy_pressure - 0.08)
        k.width_ease = max(0.5, k.width_ease - 0.04)  # open mid earlier
    elif a2 > targets.arc2_hi:
        k.decoy_pressure = min(2.0, k.decoy_pressure + 0.12)
        k.arc2_scale = min(1.35, k.arc2_scale + 0.05)
        k.enemy_aggro = min(1.65, k.enemy_aggro + 0.03)

    if a3 < targets.arc3_lo:
        # late too hard — open width, ease arc3
        k.width_late = min(0.98, k.width_late + 0.03)
        k.arc3_scale = max(0.8, k.arc3_scale - 0.07)
        k.enemy_aggro = max(0.7, k.enemy_aggro - 0.04)
    elif a3 > targets.arc3_hi:
        # late still free — climb arc3 hard without thrashing arc1/2
        step = 0.1 if a3 >= 0.95 else 0.06
        k.width_late = max(0.58, k.width_late - 0.02)
        k.decoy_pressure = min(2.2, k.decoy_pressure + 0.1)
        k.arc3_scale = min(1.9, k.arc3_scale + step)
        # do NOT raise global enemy_aggro when only arc3 is free
        # (that was killing arc2 overnight)

    # diversity: if thrashing low diversity, widen mid curve
    if div < targets.diversity_min:
        k.width_ease = max(0.5, k.width_ease - 0.06)  # open mid earlier
        k.width_late = min(0.98, k.width_late + 0.02)
    else:
        k.width_ease = min(1.15, k.width_ease + 0.02)

    # path collapse: if path entropy low, force multipath craft
    pe = metrics.get("path_entropy", 0.5)
    hints = metrics.get("path_hints") or {}
    dominant = max(hints.values()) if hints else 0
    total_h = sum(hints.values()) or 1
    if pe < 0.45 or (dominant / total_h) > 0.75:
        k.path_purity_target = max(0.35, k.path_purity_target - 0.08)
        # open width mid so B/C eco-hold paths exist
        k.width_ease = max(0.5, k.width_ease - 0.04)
        k.width_late = min(0.98, k.width_late + 0.02)
    else:
        k.path_purity_target = min(0.9, k.path_purity_target + 0.02)

    # lane: if arc2/3 hold maps struggle, more lanes for multipath
    if a2 < 0.5 or a3 < 0.45:
        k.lane_bias = min(1.45, k.lane_bias + 0.06)
    elif steamroll:
        k.lane_bias = min(1.35, k.lane_bias + 0.04)  # more columns = more line-war skill
    else:
        k.lane_bias = max(0.85, k.lane_bias - 0.02)

    # clamp
    k.difficulty = round(k.difficulty, 4)
    k.width_early = round(k.width_early, 4)
    k.width_late = round(k.width_late, 4)
    k.width_ease = round(k.width_ease, 4)
    k.decoy_pressure = round(k.decoy_pressure, 4)
    k.enemy_aggro = round(k.enemy_aggro, 4)
    k.lane_bias = round(k.lane_bias, 4)
    k.path_purity_target = round(k.path_purity_target, 4)
    k.arc1_scale = round(k.arc1_scale, 4)
    k.arc2_scale = round(k.arc2_scale, 4)
    k.arc3_scale = round(k.arc3_scale, 4)
    return k


def craft_score(metrics: dict[str, Any], targets: CraftTargets) -> float:
    """Higher = closer to ideal campaign feel (1.0 perfect)."""
    ar = metrics.get("arc_rates") or {}

    def band(v: float, lo: float, hi: float) -> float:
        if lo <= v <= hi:
            return 1.0
        if v < lo:
            return max(0.0, 1.0 - (lo - v) / max(0.2, lo))
        return max(0.0, 1.0 - (v - hi) / max(0.2, 1.0 - hi))

    s1 = band(ar.get("1", 0), targets.arc1_lo, targets.arc1_hi)
    s2 = band(ar.get("2", 0), targets.arc2_lo, targets.arc2_hi)
    s3 = band(ar.get("3", 0), targets.arc3_lo, targets.arc3_hi)
    so = band(metrics.get("overall_win_rate", 0), targets.overall_lo, targets.overall_hi)
    sd = min(1.0, metrics.get("diversity_mean", 0) / max(0.01, targets.diversity_min))
    pe = min(1.0, metrics.get("path_entropy", 0) / 0.8)
    # prefer early clear (weight arc1)
    return round(0.25 * s1 + 0.2 * s2 + 0.2 * s3 + 0.2 * so + 0.1 * sd + 0.05 * pe, 4)


# ---------------------------------------------------------------------------
# One generation
# ---------------------------------------------------------------------------

def run_generation(
    *,
    gen: int,
    knobs: CraftKnobs,
    dual: DualMembraneState,
    rho: CampaignRho,
    weights: BarBrainWeights,
    seeds: list[int],
    verbose: bool = False,
) -> tuple[dict[str, Any], CraftKnobs, DualMembraneState, CampaignRho, BarBrainWeights]:
    # sync path ket purity toward density
    dual.campaign.purity = 0.6 * dual.campaign.purity + 0.4 * knobs.path_purity_target

    agent = LocalToolAgent(use_bar_brain=True)
    # inject current weights
    try:
        agent._brain = BarBrain(weights)
    except Exception:
        pass

    seed_reports: list[dict[str, Any]] = []
    for seed in seeds:
        missions = build_crafted_campaign(knobs, rho, dual.campaign)
        rep = play_missions(
            missions,
            agent=agent,
            difficulty=knobs.difficulty,
            seed=seed,
            verbose=verbose,
            schema="quantum-bar-ai-manifold-gym/0.1",
            label=f"gym_gen{gen}_s{seed}",
        )
        seed_reports.append(rep)
        weights = ingest_campaign_report(rep, weights)
        dual, rho = evolve_dual_from_report(dual, rep, rho)

    # aggregate metrics across seeds
    agg_wins = sum(r.get("hard_wins", 0) for r in seed_reports)
    agg_miss = sum(r.get("missions", 0) for r in seed_reports)
    # use last report structure but recompute rates
    fake = {
        "hard_wins": agg_wins,
        "missions": agg_miss,
        "results": [row for r in seed_reports for row in (r.get("results") or [])],
    }
    metrics = analyze_report(fake, dual)
    metrics["craft_score"] = craft_score(metrics, CraftTargets())
    metrics["knobs"] = knobs.as_dict()
    metrics["gen"] = gen
    metrics["seeds"] = list(seeds)
    metrics["seed_win_rates"] = [
        round(r.get("hard_wins", 0) / max(1, r.get("missions", 1)), 4) for r in seed_reports
    ]

    new_knobs = retune_knobs(knobs, metrics, CraftTargets())
    # InterferenceTuner craft nudge (small deltas on top of controller)
    nudge = ((metrics.get("interference") or {}).get("nudge")) or {}
    for key, delta in nudge.items():
        if hasattr(new_knobs, key):
            cur = float(getattr(new_knobs, key))
            setattr(new_knobs, key, round(cur + float(delta), 4))
    # Path-space annealing: reheat collapsed A/B/C multipath
    arep = anneal_path_space(dual.campaign, dual.path_ket, gen=gen, max_gen=80)
    metrics["anneal"] = arep.as_dict()
    for key, delta in craft_nudge_from_anneal(arep).items():
        if hasattr(new_knobs, key):
            cur = float(getattr(new_knobs, key))
            setattr(new_knobs, key, round(cur + float(delta), 4))
    # Schism path entanglement on density (operator membrane)
    entangle_paths_for_schism(dual.campaign, rho)
    return metrics, new_knobs, dual, rho, weights


# ---------------------------------------------------------------------------
# Overnight runner
# ---------------------------------------------------------------------------

def run_gym(
    *,
    generations: int = 12,
    seeds_per_gen: int = 2,
    base_seed: int = 11,
    hours: float | None = None,
    verbose: bool = False,
    workspace: Path | None = None,
) -> dict[str, Any]:
    ws = workspace or _workspace_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ws / "headless_runs" / f"manifold_gym_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    knobs = CraftKnobs()
    # resume from last craft recipe if present (overnight continuity)
    recipe_path = ws / "app" / "brain" / "craft_recipe.json"
    if recipe_path.is_file():
        try:
            rd = json.loads(recipe_path.read_text(encoding="utf-8-sig"))
            if isinstance(rd.get("knobs"), dict):
                knobs = CraftKnobs.from_dict(rd["knobs"])
                print(f"loaded craft recipe knobs from {recipe_path}")
        except Exception as e:  # noqa: BLE001
            print(f"craft recipe load skipped: {e}")
    dual = DualMembraneState(
        campaign=CampaignDensity.from_path_weights(0.33, 0.34, 0.33, purity=0.8),
        path_ket=PathKet.from_weights(0.33, 0.34, 0.33),
    )
    rho = CampaignRho()
    weights = load_weights()
    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    best_knobs: CraftKnobs | None = None

    t0 = time.time()
    deadline = t0 + hours * 3600 if hours else None
    gen = 0
    max_gens = generations if hours is None else max(generations, 500)

    print(f"=== manifold gym start gens={generations} seeds={seeds_per_gen} hours={hours} ===")
    print(f"out: {out}")

    while gen < max_gens:
        if deadline and time.time() >= deadline:
            print(f"time budget hit after gen {gen}")
            break
        seeds = [base_seed + gen * 31 + i * 17 for i in range(seeds_per_gen)]
        print(f"\n----- gen {gen} knobs.diff={knobs.difficulty:.2f} "
              f"w=[{knobs.width_early:.2f}..{knobs.width_late:.2f}] -----")
        metrics, knobs, dual, rho, weights = run_generation(
            gen=gen,
            knobs=knobs,
            dual=dual,
            rho=rho,
            weights=weights,
            seeds=seeds,
            verbose=verbose,
        )
        history.append(metrics)
        score = metrics.get("craft_score", 0)
        print(
            f"  win={metrics['overall_win_rate']:.0%} "
            f"arcs={metrics['arc_rates']} "
            f"div={metrics['diversity_mean']:.2f} "
            f"pathH={metrics['path_entropy']:.2f} "
            f"score={score:.3f} "
            f"ρ.pur={dual.campaign.purity:.2f} "
            f"paths={dual.campaign.path_weights()}"
        )
        if best is None or score > best.get("craft_score", -1):
            best = dict(metrics)
            best_knobs = CraftKnobs(**knobs.as_dict())
            # save champion knobs mid-run
            (out / "champion_knobs.json").write_text(
                json.dumps(best_knobs.as_dict(), indent=2), encoding="utf-8"
            )
            save_weights(weights, out / "champion_bar_brain.json")
        # periodic checkpoint
        if gen % 3 == 0 or gen == max_gens - 1:
            ck = {
                "gen": gen,
                "history_tail": history[-5:],
                "knobs": knobs.as_dict(),
                "dual": dual.operator_export(),
                "rho": rho.as_dict(),
            }
            (out / f"checkpoint_gen{gen:03d}.json").write_text(
                json.dumps(ck, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        gen += 1

    # final export
    save_weights(weights)  # write to app/brain too
    report = {
        "schemaVersion": "manifold-gym/0.1",
        "stamp": stamp,
        "elapsed_s": round(time.time() - t0, 2),
        "generations_run": gen,
        "best": best,
        "best_knobs": best_knobs.as_dict() if best_knobs else None,
        "final_knobs": knobs.as_dict(),
        "final_dual": dual.operator_export(),
        "final_rho": rho.as_dict(),
        "history": history,
        "out_dir": str(out),
        "novel_mechanisms": [
            "PathKet path superposition A/B/C",
            "CampaignDensity Hermitian path membrane",
            "ProxyBelief partial-trace fair belief",
            "LaneDensity n×n line-war coherence",
            "PredicateInterference multipath amplitudes",
            "SolutionEntropy width",
            "DecoyPOVM belief dephasing",
            "Craft controller dual-manifold retune",
        ],
    }
    path = out / "gym_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = ws / "outbox" / "manifold_gym.latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # craft recipe export for campaign defaults
    recipe = {
        "schemaVersion": "verdance-craft-recipe/0.1",
        "source": "manifold_gym",
        "stamp": stamp,
        "knobs": (best_knobs or knobs).as_dict(),
        "craft_score": (best or {}).get("craft_score"),
        "arc_rates": (best or {}).get("arc_rates"),
        "notes": (
            "Apply knobs.width_* via manifold_gym.knobs_width; "
            "difficulty via build_full_campaign(difficulty=...)."
        ),
    }
    recipe_path = ws / "app" / "brain" / "craft_recipe.json"
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    recipe_path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")

    print("\n=== manifold gym done ===")
    print(f"gens={gen} elapsed={report['elapsed_s']}s best_score={(best or {}).get('craft_score')}")
    print(f"best arcs={(best or {}).get('arc_rates')} overall={(best or {}).get('overall_win_rate')}")
    print(f"report: {path}")
    print(f"recipe: {recipe_path}")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Dual-manifold co-evolution gym")
    p.add_argument("--gens", type=int, default=12)
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--base-seed", type=int, default=11)
    p.add_argument("--hours", type=float, default=None, help="time budget hours (overrides gens cap up)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    run_gym(
        generations=args.gens,
        seeds_per_gen=args.seeds,
        base_seed=args.base_seed,
        hours=args.hours,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
