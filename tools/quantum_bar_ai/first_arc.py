"""First campaign arc — player-facing cards only.

Mirrors Verdance early sorties (no base building / strike team fiction):
  va_001 Greenest Fields eco raid
  va_002 Eye of Horus strike relay
  va_003 All That Simmers seize
  va_004 Koom fluid scar seize (continue flavor)
  va_005 Koom ridge stress

SimTruth knobs stay private. PlayerFacingCard is all the agent is allowed
to read at mission start.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, TYPE_CHECKING

from .fair_obs import PlayerFacingCard

if TYPE_CHECKING:
    from .campaign_manifold import MissionSolutionSpace
    from .lane_war import LaneGeometry


@dataclass
class SimTruth:
    """Hidden balance knobs — never serialize into agent context."""

    enemy_scale: float = 1.0
    fortified: bool = False
    duration_ticks: int = 100
    player_start_strength: float = 0.72
    enemy_start_strength: float = 0.55
    # difficulty name for operator logs only
    difficulty_label: str = "standard"


@dataclass
class ArcMission:
    card: PlayerFacingCard
    truth: SimTruth
    # for sim wiring
    map_id: str = ""
    deploy_zone: str = ""
    objective_id: str = ""
    # Manifold B — campaign solution geometry (operator + sim; fair band only to proxy)
    solution_space: Any = None  # MissionSolutionSpace | None
    # Lane membrane geometry when kind is seize_lane / hold_plateau
    lane_geometry: Any = None  # LaneGeometry | None

    @property
    def id(self) -> str:
        return self.card.id

    @property
    def kind(self) -> str:
        return self.card.kind

    def player_view(self) -> dict[str, Any]:
        """Only this is legal for the agent (no full solution_space / rho)."""
        d = self.card.as_dict()
        if self.solution_space is not None:
            ss = self.solution_space
            width = getattr(ss, "width", 0.3)
            d["width_band"] = (
                "narrow" if width < 0.4 else ("open" if width < 0.7 else "wide")
            )
            prim = getattr(ss, "primary_vectors", None) or []
            if prim:
                d["primary_hint"] = prim[0]
        if self.lane_geometry is not None:
            g = self.lane_geometry
            d["lane_feel"] = {
                "count": getattr(g, "lane_count", 0),
                "labels": list(getattr(g, "labels", [])),
                "primary": (
                    g.labels[g.primary_index]
                    if getattr(g, "labels", None)
                    else None
                ),
            }
        return d

    def operator_view(self) -> dict[str, Any]:
        d = self.card.as_dict()
        d["_sim_truth"] = asdict(self.truth)
        d["map_id"] = self.map_id
        if self.solution_space is not None:
            ss = self.solution_space
            d["_solution_space"] = ss.as_dict() if hasattr(ss, "as_dict") else ss
        if self.lane_geometry is not None:
            g = self.lane_geometry
            d["_lane_geometry"] = g.as_dict() if hasattr(g, "as_dict") else g
        return d


def build_first_arc(*, difficulty: float = 1.0) -> list[ArcMission]:
    """difficulty scales enemy — 1.0 baseline, >1 harder, <1 softer (tuning dial)."""
    d = max(0.5, float(difficulty))

    return [
        ArcMission(
            map_id="greenest_fields",
            deploy_zone="GF_SE_STAGING",
            objective_id="GF_SE_ENERGY_WORKS",
            card=PlayerFacingCard(
                id="va_001",
                title="Greenest Fields: Economy Onboarding",
                kind="eco_raid",
                map_name="Greenest Fields",
                deploy_label="Southeast Staging Ground",
                objective_label="Southeast Armada Energy Works",
                extraction_label="Central Open Grassland",
                situation=(
                    "Armada parked a converter farm on the green. No metal for you — "
                    "this is a raid, not a base crawl."
                ),
                objective_text="Destroy or wreck the Armada energy works, then extract.",
                how_to_win=(
                    "No commanders. Lead with named heroes and ground units. "
                    "Blow the eco — do not expand. Soft clock ~8 min."
                ),
                threats="Light perimeter guns. Static defenses, not endless waves.",
                allies="None meaningful. You are the main effort.",
                plain_objective="eco_raid: Southeast Armada Energy Works",
                soft_clock_minutes=8,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Pack light. Hit the converters. Walk away."},
                    {"speaker": "vane", "text": "If we plant a lab here, we lose the plot."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=0.88 * d,
                fortified=False,
                duration_ticks=90,
                player_start_strength=0.78,
                enemy_start_strength=0.46,
                difficulty_label="tutorial",
            ),
        ),
        ArcMission(
            map_id="eye_of_horus",
            deploy_zone="EOH_STAGING",
            objective_id="EOH_SE_CORTEX_POCKET",
            card=PlayerFacingCard(
                id="va_002",
                title="Glass Under the Eye",
                kind="strike_relay",
                map_name="Eye of Horus",
                deploy_label="Crater rim staging",
                objective_label="Cortex Dealer Relay (SE pocket)",
                extraction_label="West glass shelf",
                situation=(
                    "Cortex runs a dealer relay in the glassed crater. Armada perimeter "
                    "garrison watches the approaches. Null mercs hold a foothold on the flank."
                ),
                objective_text="Strike the Cortex dealer relay. Heroes must live.",
                how_to_win=(
                    "No base building. Approach under fire, break the relay, extract. "
                    "Losing Ketha or Vane fails the sortie."
                ),
                threats="Fortified pocket. Frontal is a meat grinder. Flanks exist.",
                allies="Null mercs hold ground nearby — do not treat them as your reserve.",
                plain_objective="strike_relay: Cortex Dealer Relay",
                soft_clock_minutes=10,
                briefing_lines=[
                    {"speaker": "ketha", "text": "That name is not going on the wall today."},
                    {"speaker": "ketha", "text": "Feel the flank. The glass lies about cover."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.05 * d,
                fortified=True,
                duration_ticks=110,
                player_start_strength=0.74,
                enemy_start_strength=0.58,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="all_that_simmers",
            deploy_zone="ATS_STAGING",
            objective_id="ATS_CENTRAL_LANE",
            card=PlayerFacingCard(
                id="va_003",
                title="All That Simmers — Hold the Lane",
                kind="seize_lane",
                map_name="All That Simmers",
                deploy_label="South staging shelf",
                objective_label="Central simmering lane",
                extraction_label="North mouth",
                situation=(
                    "The lane is contested. Standing on it long enough claims it — "
                    "not a one-shot demolition."
                ),
                objective_text="Take and hold the central lane until the hold marks complete.",
                how_to_win=(
                    "Push onto the lane, survive the counter, hold. Then extract. "
                    "Soft clock ~10 min."
                ),
                threats="Pre-built positions. Simple defenders who dig in.",
                allies="Light. You are still the main effort.",
                plain_objective="seize_lane: Central simmering lane",
                soft_clock_minutes=10,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Stand on it. Stay standing. That's the order."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.0 * d,
                fortified=True,
                duration_ticks=100,
                player_start_strength=0.74,
                enemy_start_strength=0.55,
                difficulty_label="standard",
            ),
        ),
        ArcMission(
            map_id="koom_valley",
            deploy_zone="KOOM_NW_GREEN_SHELF",
            objective_id="KOOM_CENTRAL_FLUID_SCAR",
            card=PlayerFacingCard(
                id="va_004",
                title="Contract — Fluid Scar",
                kind="seize_lane",
                map_name="Koom Valley",
                deploy_label="Northwest Green Shelf",
                objective_label="Central Fluid Scar",
                extraction_label="North Scar Mouth",
                situation=(
                    "Null merc contract: stand on the Fluid Scar. Armada poured ferrocrete. "
                    "Same-map continue pressure — the roster may already be tired."
                ),
                objective_text="Seize and hold the Fluid Scar, then extract north.",
                how_to_win=(
                    "Running fight, not a siege. Hit the mark, hold the mark, walk away. "
                    "Respect fortifications — route around when you can."
                ),
                threats="Fortified Armada works. Soft clock ~10 min.",
                allies="Null mercs share the front — light support only.",
                plain_objective="seize_lane: Central Fluid Scar",
                soft_clock_minutes=10,
                briefing_lines=[
                    {
                        "speaker": "ketha",
                        "text": "This is a running fight, not a siege. Pack light, hit the mark, walk away.",
                    },
                    {
                        "speaker": "ketha",
                        "text": "They've had time to pour ferrocrete. Respect it, then route around it.",
                    },
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.02 * d,
                fortified=True,
                duration_ticks=115,
                player_start_strength=0.73,
                enemy_start_strength=0.55,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="koom_valley",
            deploy_zone="KOOM_CENTRAL_FLUID_SCAR",
            objective_id="KOOM_EAST_RIDGE_POCKET",
            card=PlayerFacingCard(
                id="va_005",
                title="Contract — East Ridge Pocket",
                kind="eco_raid",
                map_name="Koom Valley",
                deploy_label="Central Fluid Scar (continue)",
                objective_label="East Ridge Pocket",
                extraction_label="North Scar Mouth",
                situation=(
                    "Seamless continue. Same valley, next contract. Heroes may be bruised. "
                    "Raid the ridge pocket eco and leave."
                ),
                objective_text="Raid the East Ridge Pocket infrastructure, then extract.",
                how_to_win=(
                    "No rebuild. Use what you still have. Finish the wreck, then extract. "
                    "If the team is strained, patch once, then commit."
                ),
                threats="Residual Armada presence. Tired roster risk.",
                allies="Thin.",
                plain_objective="eco_raid: East Ridge Pocket",
                soft_clock_minutes=10,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Same dirt. New scar. Don't get greedy."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=0.95 * d,
                fortified=False,
                duration_ticks=100,
                player_start_strength=0.72,
                enemy_start_strength=0.5,
                difficulty_label="standard",
            ),
        ),
    ]


FIRST_ARC = build_first_arc(difficulty=1.0)
