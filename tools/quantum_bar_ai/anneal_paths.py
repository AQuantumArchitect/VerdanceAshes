"""Path-space quantum annealing — keep A/B/C multipath alive overnight.

When PathKet / CampaignDensity collapses toward one path, the campaign loses
narrative diversity. This module:

  - measures path purity / entropy
  - applies a controlled *annealing schedule* that reintroduces off-diagonal
    coherence and soft amplitude floors
  - returns craft suggestions (width_ease, path_purity_target)

Used by manifold_gym after each generation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .quantum_membrane import CampaignDensity, PathKet, PATH_LABELS


@dataclass
class AnnealReport:
    entropy: float
    purity: float
    dominant: str
    dominant_p: float
    annealed: bool
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def anneal_path_space(
    density: CampaignDensity,
    ket: PathKet,
    *,
    gen: int,
    max_gen: int = 40,
    collapse_thr: float = 0.72,
) -> AnnealReport:
    """If one path dominates, reheat (rephase + floor amps)."""
    pw = density.path_weights()
    dominant = max(pw, key=pw.get)
    dom_p = pw[dominant]
    ent = density.entropy()
    pur = density.purity

    # annealing temperature: higher early, cools later but never zero
    t = 1.0 - min(1.0, gen / max(1, max_gen))
    temp = 0.15 + 0.45 * t

    annealed = False
    notes = "stable multipath"
    if dom_p >= collapse_thr or ent < 0.55:
        # reheat density
        floor = 0.12 + 0.08 * temp
        density.diag = [max(floor, d) for d in density.diag]
        density._renorm_diag()
        density.rephase(0.1 + 0.2 * temp)
        density.purity = min(0.85, density.purity + 0.1 * temp)
        # reheat ket with soft measures on minorities
        for lab in PATH_LABELS:
            if lab != dominant:
                ket.soft_measure(lab, strength=0.05 + 0.1 * temp)
        ket.phase_kick(PATH_LABELS.index(dominant), 0.15 * temp)
        annealed = True
        notes = f"reheat path space (dom={dominant} p={dom_p:.2f} temp={temp:.2f})"

    return AnnealReport(
        entropy=round(density.entropy(), 4),
        purity=round(density.purity, 4),
        dominant=dominant,
        dominant_p=round(dom_p, 4),
        annealed=annealed,
        notes=notes,
    )


def craft_nudge_from_anneal(report: AnnealReport) -> dict[str, float]:
    if not report.annealed:
        return {}
    return {
        "path_purity_target": -0.05,
        "width_ease": -0.03,
        "width_late": 0.01,
    }
