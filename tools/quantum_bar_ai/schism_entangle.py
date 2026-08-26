"""Schism entanglement — narrative multipath from campaign schism axis.

When CampaignRho.schism is high (Taelith-dominant fracture), late missions
should *feel* more split: more viable vectors, more decoys, and a soft
entanglement between path_b (free ashes) and path_c (void exit).

This is a craft-side operator on MissionSolutionSpace + CampaignDensity,
not a fair leak to the proxy.
"""
from __future__ import annotations

from typing import Any

from .campaign_manifold import CampaignRho, MissionSolutionSpace, VECTOR_POOL
from .quantum_membrane import CampaignDensity


def schism_level(rho: CampaignRho) -> float:
    """0..1 how fractured the war is."""
    return max(0.0, min(1.0, (float(rho.schism) + 1.0) / 2.0))


def entangle_paths_for_schism(density: CampaignDensity, rho: CampaignRho) -> CampaignDensity:
    """Boost B–C off-diagonal when schism high (free vs void entanglement)."""
    s = schism_level(rho)
    if s < 0.4:
        return density
    # off_re indices: 01=A-B, 12=B-C, 20=C-A
    if len(density.off_re) >= 3:
        density.off_re[1] = min(0.45, density.off_re[1] + 0.12 * s)
        density.off_re[2] = min(0.4, density.off_re[2] + 0.06 * s)
    density.purity = max(0.3, density.purity - 0.05 * s)  # schism lowers purity
    return density


def widen_solution_for_schism(
    ss: MissionSolutionSpace,
    rho: CampaignRho,
    *,
    kind: str,
) -> MissionSolutionSpace:
    """Late multipath gets extra viable vectors + decoys under high schism."""
    s = schism_level(rho)
    if s < 0.45 or ss.width < 0.5:
        return ss
    extras = []
    if kind in ("multipressure", "siege", "survive_wilds"):
        extras = ["FALLBACK", "EXTRACT", "RALLY", "DEFEND_BASE"]
    elif kind in ("eco_expand", "seize_lane"):
        extras = ["FLANK", "HOLD_AND_HEAL", "TECH_UP"]
    for a in extras:
        if a in VECTOR_POOL and a not in ss.viable_vectors and s > 0.5:
            # only add if schism high enough
            if a in ("FALLBACK", "EXTRACT") and s < 0.65:
                continue
            ss.viable_vectors.append(a)
    # decoys: pure aggression on survive, pure eco on strike under schism noise
    decoy_pool = {
        "survive_wilds": ["EXPAND_FRONT", "TECH_UP"],
        "multipressure": ["TECH_UP"],
        "siege": ["RECLAIM", "EXTRACT"],
        "strike_relay": ["BUILD_MEX", "DEFEND_BASE"],
    }.get(kind, [])
    for d in decoy_pool:
        if d not in ss.viable_vectors and d not in ss.decoy_vectors and s > 0.55:
            ss.decoy_vectors.append(d)
    # slight width bump from schism (capped)
    ss.width = min(0.98, ss.width + 0.04 * s)
    ss.vector_clarity = max(0.05, ss.vector_clarity - 0.05 * s)
    ss.notes = (ss.notes or "") + f" | schism={s:.2f} entangle"
    return ss


def fair_schism_band(rho: CampaignRho) -> str:
    """Only band leaks to briefing flavor — never the number."""
    s = schism_level(rho)
    if s < 0.35:
        return "united"
    if s < 0.65:
        return "fractured"
    return "shattered"
