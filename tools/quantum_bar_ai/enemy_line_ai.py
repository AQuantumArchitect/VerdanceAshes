"""Enemy line AI — disposition ⊗ lane membrane adversary.

The campaign-shape side does not only author solution width; it fields an
enemy that *fights the line* using deembed disposition + path coherence.

Fair rule: proxy never reads exact enemy mass or this planner's internals —
only HUD contact/pressure bands after combat resolves.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .campaign_manifold import CampaignRho, deembed_disposition, disposition_from_density
from .lane_war import LineFront, LineOrder, apply_line_order
from .quantum_membrane import CampaignDensity


@dataclass
class EnemyLinePlan:
    order: LineOrder
    disposition: dict[str, float]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order.as_dict(),
            "disposition": {k: round(v, 3) for k, v in self.disposition.items()},
            "reason": self.reason,
        }


def plan_enemy_line(
    front: LineFront,
    *,
    rho: CampaignRho | None = None,
    density: CampaignDensity | None = None,
    width: float = 0.3,
    rng: random.Random | None = None,
) -> EnemyLinePlan:
    """Choose an enemy line order against the player front."""
    rng = rng or random.Random(0)
    rho = rho or CampaignRho()
    disp = disposition_from_density(rho, density) if density is not None else deembed_disposition(rho)
    mil = disp.get("military_aggression", 0.5)
    swarm = disp.get("swarm_bias", 0.4)
    fort = disp.get("fortify_bias", 0.4)
    expand = disp.get("expansion_target", 0.4)

    n = front.geometry.lane_count
    prim = front.geometry.primary_index
    holds = [L.hold for L in front.lanes]
    # enemy wants to deny player hold — target strongest player push
    hottest = max(range(n), key=lambda i: front.lanes[i].friendly_mass * (1.0 + front.lanes[i].push))
    weakest_player = min(range(n), key=lambda i: holds[i])

    # High fortify + low mil → hold line / reinforce
    if fort > 0.55 and mil < 0.45:
        order = LineOrder("HOLD_LINE", reason="enemy fortify bias — dress the line", confidence=0.7)
        return EnemyLinePlan(order, disp, order.reason)

    # Swarm: stagger or multi-weight
    if swarm > 0.55 and width >= 0.45:
        if rng.random() < 0.4:
            order = LineOrder("STAGGER_ADVANCE", reason="swarm bias — stagger the line", confidence=0.65)
        else:
            order = LineOrder(
                "WEIGHT_LANE",
                lane=hottest,
                reason="swarm weight on player mass",
                confidence=0.68,
            )
        return EnemyLinePlan(order, disp, order.reason)

    # High military: breakthrough weak player lane
    if mil > 0.55:
        target = weakest_player if holds[weakest_player] < 0.45 else prim
        order = LineOrder(
            "BREAKTHROUGH",
            lane=target,
            reason="military aggression — crack weak column",
            confidence=0.75,
        )
        return EnemyLinePlan(order, disp, order.reason)

    # Expansion: weight outer lanes
    if expand > 0.55 and n >= 3:
        edge = 0 if rng.random() < 0.5 else n - 1
        order = LineOrder("WEIGHT_LANE", lane=edge, reason="expansion — pressure flank", confidence=0.6)
        return EnemyLinePlan(order, disp, order.reason)

    # Default: reinforce primary against player
    order = LineOrder(
        "REINFORCE_LANE",
        lane=prim,
        reason="default — reinforce contested primary",
        confidence=0.55,
    )
    return EnemyLinePlan(order, disp, order.reason)


def apply_enemy_plan(front: LineFront, plan: EnemyLinePlan, *, dt: float = 0.7) -> LineFront:
    """Apply enemy order to *enemy* mass (mirrored: shift enemy_diag / enemy_mass).

    Classical lanes store enemy_mass per column; we reweight those.
    """
    n = len(front.lanes)
    if n == 0:
        return front
    o = plan.order.order
    lane = plan.order.lane if plan.order.lane is not None else front.geometry.primary_index
    lane = max(0, min(n - 1, lane))

    def shift_enemy(target: int, amount: float) -> None:
        donors = [i for i in range(n) if i != target]
        if not donors:
            return
        take = amount / len(donors)
        for i in donors:
            moved = min(take, front.lanes[i].enemy_mass * 0.5)
            front.lanes[i].enemy_mass -= moved
            front.lanes[target].enemy_mass += moved

    if o == "HOLD_LINE":
        avg = sum(L.enemy_mass for L in front.lanes) / n
        for L in front.lanes:
            L.enemy_mass = 0.75 * L.enemy_mass + 0.25 * avg
    elif o in ("WEIGHT_LANE", "REINFORCE_LANE", "BREAKTHROUGH"):
        shift_enemy(lane, 0.1 * dt if o != "BREAKTHROUGH" else 0.16 * dt)
    elif o == "STAGGER_ADVANCE":
        for i, L in enumerate(front.lanes):
            if i % 2 == 0:
                L.enemy_mass = min(0.55, L.enemy_mass * 1.05)
    elif o == "REFUSE_FLANK":
        if n >= 3:
            for edge in (0, n - 1):
                pull = front.lanes[edge].enemy_mass * 0.2
                front.lanes[edge].enemy_mass -= pull
                front.lanes[n // 2].enemy_mass += pull

    total = sum(L.enemy_mass for L in front.lanes) or 1.0
    for L in front.lanes:
        L.enemy_mass = max(0.04, L.enemy_mass / total)

    # quantum enemy mirror if density present
    if front.density is not None:
        try:
            front.density.enemy_diag = [L.enemy_mass for L in front.lanes]
            # enemy breakthrough also dephases *their* adjacency feel (purity hit)
            if o == "BREAKTHROUGH":
                front.density.purity = max(0.2, front.density.purity - 0.03)
        except Exception:
            pass
    return front
