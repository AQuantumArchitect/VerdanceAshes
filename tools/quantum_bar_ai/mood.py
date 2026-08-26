"""Mood readout + sensor packing for the player-proxy field."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping

from .world import AXES, HEROES


@dataclass
class MoodSnapshot:
    """Calibrated scalars in ~[0,1] warmth space + signed axes in [-1,+1]."""

    aggression: float = 0.5
    caution: float = 0.5
    focus: float = 0.5
    pressure: float = 0.5
    cohesion: float = 0.5
    momentum: float = 0.5
    # Mission / force (0..1)
    objective: float = 0.0
    threat: float = 0.0
    clock: float = 0.0
    progress: float = 0.0
    player_strength: float = 0.5
    enemy_strength: float = 0.5
    advantage: float = 0.5
    # Heroes
    hero_vane_alive: float = 1.0
    hero_ketha_alive: float = 1.0
    turn: int = 0

    def signed(self) -> dict[str, float]:
        """Map warmth [0,1] → signed [-1,+1] where +1 is the warm/high pole."""
        return {a: (getattr(self, a) * 2.0) - 1.0 for a in AXES}

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signed"] = self.signed()
        return d

    def brief_line(self) -> str:
        s = self.signed()
        return (
            f"agg={s['aggression']:+.2f} caut={s['caution']:+.2f} "
            f"foc={s['focus']:+.2f} press={s['pressure']:+.2f} "
            f"coh={s['cohesion']:+.2f} mom={s['momentum']:+.2f} | "
            f"obj={self.objective:.2f} thr={self.threat:.2f} "
            f"clk={self.clock:.2f} adv={self.advantage:.2f}"
        )


def _z_to_warm(z: float) -> float:
    """Bloch z: warm pole is z=-1 per yurt_mood wire law → warmth=(1-z)/2."""
    return max(0.0, min(1.0, (1.0 - float(z)) / 2.0))


def _role_z(engine, node: str, role: str) -> float:
    try:
        cluster = engine.field.clusters[node]
        return float(cluster.role_bloch(role)[2])
    except Exception:
        return 0.0


def read_mood(engine, turn: int = 0) -> MoodSnapshot:
    """Pull mood + mission beliefs from a live engine."""
    snap = MoodSnapshot(turn=turn)
    for axis in AXES:
        setattr(snap, axis, _z_to_warm(_role_z(engine, "proxy", axis)))

    for role in ("objective", "threat", "clock", "progress"):
        # mission roles use range normalizer → z≈+1 means high value under
        # default path; convert via (z+1)/2 as conventional scalar.
        z = _role_z(engine, "mission", role)
        setattr(snap, role, max(0.0, min(1.0, (z + 1.0) / 2.0)))

    for role in ("player_strength", "enemy_strength", "advantage"):
        z = _role_z(engine, "force", role)
        setattr(snap, role, max(0.0, min(1.0, (z + 1.0) / 2.0)))

    for hero, attr in (("hero_vane", "hero_vane_alive"), ("hero_ketha", "hero_ketha_alive")):
        z = _role_z(engine, hero, "alive")
        setattr(snap, attr, max(0.0, min(1.0, (z + 1.0) / 2.0)))

    return snap


def pack_wall_sensors(state: Mapping[str, Any]) -> dict[str, float]:
    """Pack abstract sim state into wall-tier sensor readings for ingest.

    Mood wall values are signed evidence in [-1,+1] for WARM_NORM
    (positive = warm / high pole). Mission/force use [0,1] range.
    """
    # Derive mood evidence from combat state (mechanical hose).
    progress = float(state.get("progress", 0.0))
    threat = float(state.get("threat", 0.0))
    clock = float(state.get("clock_frac", 0.0))  # 0 start → 1 end
    p_str = float(state.get("player_strength", 0.5))
    e_str = float(state.get("enemy_strength", 0.5))
    advantage = max(0.0, min(1.0, 0.5 + (p_str - e_str)))
    approach = float(state.get("approach", 0.0))
    heroes_alive = float(state.get("heroes_alive_frac", 1.0))
    grouped = float(state.get("cohesion_proxy", 0.7))

    # Signed mood evidence (-1 cool .. +1 warm).
    aggression = (advantage - 0.5) * 1.4 + (1.0 - threat) * 0.3 - clock * 0.1
    caution = threat * 0.8 + (1.0 - advantage) * 0.4 + (1.0 - heroes_alive) * 0.5
    focus = 0.3 + progress * 0.4 + approach * 0.3 - threat * 0.2
    pressure = clock * 0.7 + threat * 0.4 - advantage * 0.2
    cohesion = grouped * 1.2 - 0.2
    momentum = (progress - 0.3) * 1.2 + (advantage - 0.5) * 0.8 - threat * 0.3

    def clip_s(v: float) -> float:
        return max(-1.0, min(1.0, v))

    sensors: dict[str, float] = {
        "proxy_aggression_wall": clip_s(aggression),
        "proxy_caution_wall": clip_s(caution),
        "proxy_focus_wall": clip_s(focus),
        "proxy_pressure_wall": clip_s(pressure),
        "proxy_cohesion_wall": clip_s(cohesion),
        "proxy_momentum_wall": clip_s(momentum),
        "mission_objective_wall": max(0.0, min(1.0, float(state.get("objective", progress)))),
        "mission_threat_wall": max(0.0, min(1.0, threat)),
        "mission_clock_wall": max(0.0, min(1.0, clock)),
        "mission_progress_wall": max(0.0, min(1.0, progress)),
        "force_player_strength_wall": max(0.0, min(1.0, p_str)),
        "force_enemy_strength_wall": max(0.0, min(1.0, e_str)),
        "force_advantage_wall": advantage,
        "hero_vane_alive_wall": float(state.get("vane_alive", 1.0)),
        "hero_vane_wounded_wall": float(state.get("vane_wounded", 0.0)),
        "hero_vane_near_objective_wall": float(state.get("vane_near_obj", approach)),
        "hero_ketha_alive_wall": float(state.get("ketha_alive", 1.0)),
        "hero_ketha_wounded_wall": float(state.get("ketha_wounded", 0.0)),
        "hero_ketha_near_objective_wall": float(state.get("ketha_near_obj", approach)),
    }
    return sensors


def pack_claim_sensors(action_name: str, mood: MoodSnapshot) -> dict[str, float]:
    """LLM/policy self-report claims at low η — what the proxy *intends* to feel."""
    # Nudge mood toward the chosen action's implied affect.
    claims = {
        "PUSH_OBJECTIVE": dict(aggression=0.7, caution=-0.3, focus=0.6, momentum=0.5),
        "PROBE": dict(aggression=0.2, caution=0.3, focus=0.4, momentum=0.1),
        "FLANK": dict(aggression=0.4, caution=0.1, focus=0.5, cohesion=-0.2),
        "HOLD_AND_HEAL": dict(aggression=-0.6, caution=0.7, cohesion=0.5, pressure=-0.2),
        "RALLY": dict(cohesion=0.8, focus=0.3, aggression=-0.2, momentum=-0.1),
        "FALLBACK": dict(aggression=-0.8, caution=0.8, pressure=0.4, momentum=-0.5),
        "EXTRACT": dict(focus=0.7, aggression=-0.4, caution=0.5, pressure=0.3),
        "WAIT": dict(aggression=-0.2, caution=0.2, pressure=-0.1),
    }
    deltas = claims.get(action_name, {})
    out: dict[str, float] = {}
    for axis in AXES:
        if axis in deltas:
            out[f"proxy_{axis}_claim"] = max(-1.0, min(1.0, float(deltas[axis])))
    return out


def pack_referee_sensors(outcome: Mapping[str, Any]) -> dict[str, float]:
    """Ground-truth post-mission / post-tick referees."""
    won = 1.0 if outcome.get("verdict") in ("victory", "extracted", "objective_complete") else 0.0
    lost = 1.0 if outcome.get("verdict") in ("defeat", "heroes_dead", "timeout_fail") else 0.0
    progress = float(outcome.get("progress", won))
    return {
        "mission_objective_referee": progress if won or progress > 0 else 0.0,
        "mission_progress_referee": progress,
        "mission_threat_referee": float(outcome.get("final_threat", 0.0)),
        "mission_clock_referee": float(outcome.get("clock_frac", 1.0 if won or lost else 0.5)),
        # Mood referees: victory warms momentum/focus; defeat warms caution/pressure.
        "proxy_momentum_referee": 0.8 if won else (-0.7 if lost else 0.0),
        "proxy_focus_referee": 0.6 if won else (-0.3 if lost else 0.0),
        "proxy_caution_referee": -0.3 if won else (0.7 if lost else 0.0),
        "proxy_pressure_referee": -0.5 if won else (0.6 if lost else 0.0),
        "proxy_aggression_referee": 0.3 if won else (-0.2 if lost else 0.0),
        "proxy_cohesion_referee": float(outcome.get("heroes_alive_frac", 0.5)) * 1.2 - 0.2,
    }
