"""Map proxy mood/actions → BAR PlayerController profiles + startscript hints.

Real spring-headless still uses BARbarIAn / SimpleAI in the player seat today.
This module chooses which profile best matches the proxy's current mood so we
can A/B quantum-BAR-AI against stock AI without writing a full Lua AI yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mood import MoodSnapshot


@dataclass
class BarSeatPlan:
    player_controller: str
    reason: str
    aggressiveness: float  # 0..1
    suggested_sim_frames: int
    debug_hints: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_controller": self.player_controller,
            "reason": self.reason,
            "aggressiveness": self.aggressiveness,
            "suggested_sim_frames": self.suggested_sim_frames,
            "debug_hints": self.debug_hints,
        }


# Known controllers used by run_headless_balance_test.ps1 / install_playable_slice.
CONTROLLERS = (
    "simple",
    "barbarian_aggressive",
    # future hooks if/when available in the playable installer:
    # "barbarian_defensive",
    # "barbarian_balanced",
)


def plan_from_mood(mood: MoodSnapshot, *, mission_kind: str = "eco_raid") -> BarSeatPlan:
    s = mood.signed()
    agg = s["aggression"]
    caut = s["caution"]
    press = s["pressure"]
    mom = s["momentum"]

    score = agg * 0.45 + mom * 0.25 - caut * 0.35 + press * 0.1
    # kind biases: eco/siege may grow first; raids push; wilds hold
    if mission_kind in ("eco_raid", "strike_relay", "multipressure"):
        score += 0.1
    elif mission_kind in ("seize_lane", "hold_plateau"):
        score -= 0.05
    elif mission_kind in ("eco_expand",):
        score -= 0.12  # grow first
    elif mission_kind == "siege":
        score += 0.05
    elif mission_kind == "survive_wilds":
        score -= 0.15

    aggressiveness = max(0.0, min(1.0, 0.5 + score * 0.5))

    if aggressiveness >= 0.55:
        controller = "barbarian_aggressive"
        reason = f"mood pushy (score={score:+.2f}) → barbarian_aggressive"
    else:
        controller = "simple"
        reason = f"mood cautious/hold/eco (score={score:+.2f}) → simple"

    frames = 12000 if mission_kind in ("eco_raid", "strike_relay") else 18000
    if mission_kind in ("siege", "multipressure", "eco_expand"):
        frames = 22000
    if mission_kind == "survive_wilds":
        frames = 20000
    if press > 0.3:
        frames = int(frames * 0.85)

    hints = [
        f"proxy_agg={s['aggression']:+.2f}",
        f"proxy_caut={s['caution']:+.2f}",
        f"mission_kind={mission_kind}",
    ]
    if mood.objective > 0.9:
        hints.append("prefer extract / quit after objective markers")
    return BarSeatPlan(
        player_controller=controller,
        reason=reason,
        aggressiveness=round(aggressiveness, 3),
        suggested_sim_frames=frames,
        debug_hints=hints,
    )


def plan_from_action_histogram(actions: list[str], *, mission_kind: str = "eco_raid") -> BarSeatPlan:
    """Aggregate a sim tape into a single BAR seat plan (post-hoc or pre-seed)."""
    if not actions:
        return plan_from_mood(MoodSnapshot(), mission_kind=mission_kind)
    pushy = sum(1 for a in actions if a in ("PUSH_OBJECTIVE", "FLANK"))
    holdy = sum(1 for a in actions if a in ("HOLD_AND_HEAL", "FALLBACK", "RALLY", "WAIT"))
    total = max(1, len(actions))
    pseudo = MoodSnapshot(
        aggression=pushy / total,
        caution=holdy / total,
        momentum=pushy / total,
        pressure=0.4,
        focus=0.6,
        cohesion=0.6,
    )
    return plan_from_mood(pseudo, mission_kind=mission_kind)
