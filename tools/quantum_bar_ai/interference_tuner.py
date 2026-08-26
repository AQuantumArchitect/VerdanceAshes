"""InterferenceTuner — novel craft mechanism for multipath win predicates.

When campaign width is open/wide, win predicates should form a *coherent
ensemble*: playing two viable strategies can constructively interfere.
When the proxy thrash-switches, phases dephase and clears get harder.

This module:
  - assigns relative phases to predicates from mission geometry
  - scores a tape for multipath coherence vs thrash
  - suggests craft nudges (width / decoy) for the gym controller
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

from .quantum_membrane import PredicateAmplitudes, vector_diversity


# Kind → preferred multipath phase layout (radians)
KIND_PHASE_LAYOUT: dict[str, dict[str, float]] = {
    "eco_raid": {"objective_hold": 0.0, "eco_wreck": 0.35},
    "strike_relay": {"strike_cut": 0.0, "objective_hold": 0.4},
    "seize_lane": {"lane_hold": 0.0, "objective_hold": 0.25},
    "hold_plateau": {"lane_hold": 0.0, "objective_hold": 0.3},
    "eco_expand": {"eco_wreck": 0.0, "objective_hold": 0.5},
    "siege": {"siege_break": 0.0, "objective_hold": 0.45},
    "survive_wilds": {"survive_clock": 0.0, "objective_hold": 0.6},
    "multipressure": {
        "objective_hold": 0.0,
        "eco_wreck": 0.4,
        "lane_hold": 0.8,
        "strike_cut": 1.2,
    },
}


@dataclass
class InterferenceReport:
    kind: str
    width: float
    classical_max: float
    interference: float
    thrash_score: float
    diversity: float
    coherent_bonus: float
    recommended: str  # "reward_multipath" | "punish_thrash" | "narrow_ok" | "ok"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _switch_count(actions: list[str]) -> int:
    return sum(1 for i in range(1, len(actions)) if actions[i] != actions[i - 1])


def score_mission_interference(
    *,
    kind: str,
    width: float,
    predicate_scores: dict[str, float],
    predicates: list[str],
    actions: list[str],
) -> InterferenceReport:
    layout = KIND_PHASE_LAYOUT.get(kind, {})
    names = list(predicates) if predicates else list(predicate_scores.keys())
    re, im = [], []
    for n in names:
        amp = math.sqrt(max(0.0, min(1.0, float(predicate_scores.get(n, 0.0)))))
        phi = float(layout.get(n, 0.5 * len(re)))
        re.append(amp * math.cos(phi))
        im.append(amp * math.sin(phi))
    pa = PredicateAmplitudes(names=names, re=re, im=im, phases=[0.0] * len(names))
    inter = pa.interference_score()
    classical = max((float(predicate_scores.get(n, 0.0)) for n in names), default=0.0)
    switches = _switch_count(actions)
    thrash = pa.thrash_penalty(switches)
    div = vector_diversity(actions)

    # coherent multipath: high inter relative to classical, low thrash penalty gap
    gap = inter - thrash
    if width < 0.4:
        rec = "narrow_ok"
        bonus = 0.0
    elif div > 0.45 and gap < 0.05 and classical < 0.85:
        rec = "punish_thrash"
        bonus = -0.08
    elif div > 0.35 and inter > classical * 0.85 and thrash >= inter * 0.9:
        rec = "reward_multipath"
        bonus = 0.06
    else:
        rec = "ok"
        bonus = 0.0

    return InterferenceReport(
        kind=kind,
        width=width,
        classical_max=round(classical, 4),
        interference=round(inter, 4),
        thrash_score=round(thrash, 4),
        diversity=round(div, 4),
        coherent_bonus=bonus,
        recommended=rec,
    )


def aggregate_craft_nudge(reports: list[InterferenceReport]) -> dict[str, float]:
    """Translate a batch of mission interference reports into knob deltas."""
    if not reports:
        return {}
    thrash_n = sum(1 for r in reports if r.recommended == "punish_thrash")
    multi_n = sum(1 for r in reports if r.recommended == "reward_multipath")
    mean_div = sum(r.diversity for r in reports) / len(reports)
    nudge: dict[str, float] = {}
    if thrash_n >= max(2, len(reports) // 3):
        # too much thrash on wide cards — slightly narrow late or raise decoy clarity
        nudge["decoy_pressure"] = 0.05
        nudge["width_late"] = -0.01
    if multi_n >= 2 and mean_div > 0.4:
        # multipath is healthy — keep width open
        nudge["width_late"] = nudge.get("width_late", 0.0) + 0.01
        nudge["path_purity_target"] = -0.03
    if mean_div < 0.3:
        nudge["width_ease"] = -0.04
    return nudge
