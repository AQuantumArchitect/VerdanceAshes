"""Abstract headless combat sim for early no-base Verdance strike missions.

Not a BAR physics clone — a fast, inspectable sand table so the umwelt mood
graph + brain can iterate without spring-headless. Tuned so:
  - reckless push with low advantage dies
  - pure hold never finishes objective in time
  - balanced push → extract wins most eco_raid / seize_lane cards
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from .mood import MoodSnapshot, pack_claim_sensors, pack_referee_sensors, pack_wall_sensors, read_mood
from .policy import Decision, action_effects, decide
from .world import TICK_S, player_proxy_spec


@dataclass
class MissionCard:
    id: str
    title: str
    kind: str  # eco_raid | seize_lane | strike_relay | sortie
    map_id: str
    deploy_zone: str
    objective_id: str
    objective_label: str
    # difficulty knobs
    enemy_scale: float = 1.0
    fortified: bool = False
    duration_ticks: int = 120  # ~10 min at 5s/tick
    player_start_strength: float = 0.72
    enemy_start_strength: float = 0.55
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# First several campaign-flavored cards (no base building).
EARLY_ARC: list[MissionCard] = [
    MissionCard(
        id="va_sim_001",
        title="Raid the Armada energy works",
        kind="eco_raid",
        map_id="greenest_fields",
        deploy_zone="GF_SE_STAGING",
        objective_id="GF_SE_ENERGY_WORKS",
        objective_label="Southeast Armada Energy Works",
        enemy_scale=0.85,
        fortified=False,
        duration_ticks=100,
        player_start_strength=0.78,
        enemy_start_strength=0.48,
        notes="Tutorial raid — short approach, soft defenders.",
    ),
    MissionCard(
        id="va_sim_002",
        title="Seize the simmering lane",
        kind="seize_lane",
        map_id="all_that_simmers",
        deploy_zone="ATS_STAGING",
        objective_id="ATS_CENTRAL_LANE",
        objective_label="Central simmering lane",
        enemy_scale=1.0,
        fortified=True,
        duration_ticks=120,
        player_start_strength=0.74,
        enemy_start_strength=0.58,
        notes="Hold objective after contact; fortifications bite.",
    ),
    MissionCard(
        id="va_sim_003",
        title="Strike the relay pocket",
        kind="strike_relay",
        map_id="koom_valley",
        deploy_zone="KOOM_NW_GREEN_SHELF",
        objective_id="KOOM_CENTRAL_FLUID_SCAR",
        objective_label="Central Fluid Scar relay",
        enemy_scale=1.05,
        fortified=True,
        duration_ticks=100,
        player_start_strength=0.74,
        enemy_start_strength=0.56,
        notes="Harder strike — heroes matter; extract under pressure.",
    ),
    MissionCard(
        id="va_sim_004",
        title="Eco cut on the north scar mouth",
        kind="eco_raid",
        map_id="koom_valley",
        deploy_zone="KOOM_CENTRAL_FLUID_SCAR",
        objective_id="KOOM_NORTH_SCAR_MOUTH",
        objective_label="North Scar Mouth",
        enemy_scale=0.95,
        fortified=False,
        duration_ticks=90,
        player_start_strength=0.72,
        enemy_start_strength=0.50,
        notes="Seamless continue flavor — same map, depleted heroes possible.",
    ),
    MissionCard(
        id="va_sim_005",
        title="Hold the east ridge pocket",
        kind="seize_lane",
        map_id="koom_valley",
        deploy_zone="KOOM_NORTH_SCAR_MOUTH",
        objective_id="KOOM_EAST_RIDGE_POCKET",
        objective_label="East Ridge Pocket",
        enemy_scale=1.1,
        fortified=True,
        duration_ticks=110,
        player_start_strength=0.70,
        enemy_start_strength=0.58,
        notes="Late early-arc stress test — careful play, not a wall.",
    ),
]


@dataclass
class SimState:
    tick: int = 0
    approach: float = 0.0
    progress: float = 0.0  # objective progress
    objective: float = 0.0
    threat: float = 0.2
    player_strength: float = 0.7
    enemy_strength: float = 0.5
    cohesion_proxy: float = 0.75
    vane_hp: float = 1.0
    ketha_hp: float = 1.0
    extract: float = 0.0
    done: bool = False
    verdict: str = "active"
    last_action: str = ""

    def heroes_alive_frac(self) -> float:
        alive = (1.0 if self.vane_hp > 0.05 else 0.0) + (1.0 if self.ketha_hp > 0.05 else 0.0)
        return alive / 2.0

    def as_sensor_state(self, duration_ticks: int) -> dict[str, Any]:
        return {
            "progress": self.progress,
            "objective": self.objective,
            "threat": self.threat,
            "clock_frac": min(1.0, self.tick / max(1, duration_ticks)),
            "player_strength": self.player_strength,
            "enemy_strength": self.enemy_strength,
            "approach": self.approach,
            "heroes_alive_frac": self.heroes_alive_frac(),
            "cohesion_proxy": self.cohesion_proxy,
            "vane_alive": 1.0 if self.vane_hp > 0.05 else 0.0,
            "vane_wounded": max(0.0, 1.0 - self.vane_hp) if self.vane_hp > 0.05 else 1.0,
            "vane_near_obj": self.approach,
            "ketha_alive": 1.0 if self.ketha_hp > 0.05 else 0.0,
            "ketha_wounded": max(0.0, 1.0 - self.ketha_hp) if self.ketha_hp > 0.05 else 1.0,
            "ketha_near_obj": self.approach,
        }


@dataclass
class MissionResult:
    mission_id: str
    verdict: str
    ticks: int
    progress: float
    final_threat: float
    heroes_alive_frac: float
    actions: list[str] = field(default_factory=list)
    tape: list[dict[str, Any]] = field(default_factory=list)
    mood_end: dict[str, Any] | None = None
    brain_source_counts: dict[str, int] = field(default_factory=dict)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


DecideFn = Callable[[MoodSnapshot, MissionCard, list[str]], Decision]


def _default_decide(mood: MoodSnapshot, card: MissionCard, recent: list[str]) -> Decision:
    return decide(mood, mission_kind=card.kind, recent=recent)


def run_mission(
    card: MissionCard,
    *,
    engine=None,
    decide_fn: DecideFn | None = None,
    seed: int = 7,
    carry: dict[str, float] | None = None,
    max_ticks: int | None = None,
    verbose: bool = False,
) -> MissionResult:
    """Run one abstract mission; optionally reuse a live umwelt engine."""
    from umwelt.boot import build_engine
    from datetime import datetime, timedelta, timezone

    rng = random.Random(seed)
    if engine is None:
        engine = build_engine(spec=player_proxy_spec())
    decide_fn = decide_fn or _default_decide

    st = SimState(
        player_strength=card.player_start_strength,
        enemy_strength=min(0.95, card.enemy_start_strength * card.enemy_scale),
        threat=0.25 + (0.1 if card.fortified else 0.0),
    )
    if carry:
        st.vane_hp = float(carry.get("vane_hp", st.vane_hp))
        st.ketha_hp = float(carry.get("ketha_hp", st.ketha_hp))
        st.player_strength = float(carry.get("player_strength", st.player_strength)) * 0.92
        st.cohesion_proxy = float(carry.get("cohesion_proxy", st.cohesion_proxy))

    t0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    duration = max_ticks or card.duration_ticks
    actions: list[str] = []
    tape: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}

    for tick in range(duration):
        st.tick = tick
        sensors = pack_wall_sensors(st.as_sensor_state(duration))
        engine.ingest(sensor_readings=sensors, now=t0 + timedelta(seconds=TICK_S * tick))
        mood = read_mood(engine, turn=tick)
        decision = decide_fn(mood, card, actions)
        source_counts[decision.source] = source_counts.get(decision.source, 0) + 1
        actions.append(decision.action)
        st.last_action = decision.action

        # claim sensors from intended action (low η) — same tick, one extra ingest only
        claims = pack_claim_sensors(decision.action, mood)
        if claims:
            engine.ingest(
                sensor_readings=claims,
                now=t0 + timedelta(seconds=TICK_S * tick + 0.25),
            )

        _step_combat(st, card, decision.action, rng)

        row = {
            "tick": tick,
            "action": decision.action,
            "source": decision.source,
            "reason": decision.reason,
            "mood": mood.brief_line(),
            "progress": round(st.progress, 3),
            "approach": round(st.approach, 3),
            "threat": round(st.threat, 3),
            "p_str": round(st.player_strength, 3),
            "e_str": round(st.enemy_strength, 3),
            "vane": round(st.vane_hp, 3),
            "ketha": round(st.ketha_hp, 3),
            "extract": round(st.extract, 3),
        }
        tape.append(row)
        if verbose and tick % 10 == 0:
            print(
                f"  t={tick:03d} {decision.action:16s} prog={st.progress:.2f} "
                f"thr={st.threat:.2f} hp=({st.vane_hp:.2f},{st.ketha_hp:.2f})"
            )

        if st.done:
            break

    if not st.done:
        if st.progress >= 0.85 and st.extract >= 0.5:
            st.verdict = "extracted"
            st.done = True
        elif st.progress >= 0.9:
            st.verdict = "objective_complete"
            st.done = True
        elif st.heroes_alive_frac() <= 0:
            st.verdict = "heroes_dead"
            st.done = True
        elif st.progress < 0.5:
            st.verdict = "timeout_fail"
            st.done = True
        else:
            st.verdict = "timeout_partial"
            st.done = True

    outcome = {
        "verdict": st.verdict,
        "progress": st.progress,
        "final_threat": st.threat,
        "clock_frac": min(1.0, st.tick / max(1, duration)),
        "heroes_alive_frac": st.heroes_alive_frac(),
    }
    engine.ingest(
        sensor_readings=pack_referee_sensors(outcome),
        now=t0 + timedelta(seconds=TICK_S * (st.tick + 1)),
    )
    mood_end = read_mood(engine, turn=st.tick).as_dict()

    return MissionResult(
        mission_id=card.id,
        verdict=st.verdict,
        ticks=st.tick + 1,
        progress=round(st.progress, 4),
        final_threat=round(st.threat, 4),
        heroes_alive_frac=st.heroes_alive_frac(),
        actions=actions,
        tape=tape,
        mood_end=mood_end,
        brain_source_counts=source_counts,
        notes=card.notes,
    )


def _step_combat(st: SimState, card: MissionCard, action: str, rng: random.Random) -> None:
    fx = action_effects(action)
    fort = 1.15 if card.fortified else 1.0
    noise = lambda s: 1.0 + rng.uniform(-s, s)  # noqa: E731

    # Exchange damage (incoming softened so heal/fallback can recover)
    out = 0.04 * fx["dmg_out"] * st.player_strength * noise(0.12)
    inn = 0.022 * fx["dmg_in"] * st.enemy_strength * fort * card.enemy_scale * noise(0.12)

    # Approach gate: need approach before full objective damage
    st.approach = max(0.0, min(1.0, st.approach + fx["approach"] * noise(0.08)))
    approach_gate = 0.3 + 0.7 * st.approach

    if st.approach > 0.12:
        st.enemy_strength = max(0.05, st.enemy_strength - out * approach_gate)
        st.player_strength = max(0.08, st.player_strength - inn)

    # Hero HP
    hero_share = inn * 0.45
    if action == "FALLBACK":
        hero_share *= 0.45
    if action == "HOLD_AND_HEAL":
        hero_share *= 0.6
    if action == "RALLY":
        hero_share *= 0.65
    # split damage; cohesion reduces splash
    splash = hero_share * (1.05 - 0.35 * st.cohesion_proxy)
    # random focus fire
    if rng.random() < 0.5:
        st.vane_hp = max(0.0, st.vane_hp - splash * 0.85)
        st.ketha_hp = max(0.0, st.ketha_hp - splash * 0.4)
    else:
        st.ketha_hp = max(0.0, st.ketha_hp - splash * 0.85)
        st.vane_hp = max(0.0, st.vane_hp - splash * 0.4)

    heal = fx.get("heal", 0.0)
    if heal:
        st.vane_hp = min(1.0, st.vane_hp + heal * 0.55)
        st.ketha_hp = min(1.0, st.ketha_hp + heal * 0.55)
        st.player_strength = min(0.95, st.player_strength + heal * 0.22)

    st.cohesion_proxy = max(0.1, min(1.0, st.cohesion_proxy + fx.get("cohesion", 0.0)))

    # Objective progress — allow work once on approach with thin but not dead force
    if st.approach > 0.28 and st.player_strength > 0.18:
        rate = fx["obj_rate"] * approach_gate
        if card.kind == "seize_lane":
            rate *= 0.95 if action in ("PUSH_OBJECTIVE", "HOLD_AND_HEAL", "FLANK") else 0.55
        if card.kind == "eco_raid":
            rate *= 1.25 if action in ("PUSH_OBJECTIVE", "FLANK") else 0.75
        if card.kind == "strike_relay":
            rate *= 1.15 if action in ("PUSH_OBJECTIVE", "FLANK") else 0.7
            if action == "PROBE":
                rate *= 0.85
        # weakened enemy = faster obj; PUSH still works against full bases
        rate *= 0.9 + 0.6 * (1.0 - st.enemy_strength)
        if action == "PUSH_OBJECTIVE":
            rate *= 1.15
        st.progress = min(1.0, st.progress + rate * noise(0.1))
        st.objective = st.progress

    # Threat model
    contact = st.approach * 0.5 + (0.3 if action in ("PUSH_OBJECTIVE", "FLANK") else 0.1)
    st.threat = max(
        0.05,
        min(
            0.98,
            0.55 * st.enemy_strength * fort
            + 0.25 * contact
            - 0.2 * st.player_strength
            + rng.uniform(-0.03, 0.03),
        ),
    )

    # Extract path
    if action == "EXTRACT" or st.progress >= 0.92:
        st.extract = min(1.0, st.extract + fx.get("extract_push", 0.08 if st.progress >= 0.9 else 0.02))

    # Terminal checks
    if st.vane_hp <= 0.05 and st.ketha_hp <= 0.05:
        st.done = True
        st.verdict = "heroes_dead"
        return
    if st.progress >= 0.92 and st.extract >= 0.85:
        st.done = True
        st.verdict = "extracted"
        return
    if st.progress >= 0.99 and card.kind != "seize_lane":
        # eco_raid / strike can complete without full extract bar if obj nuked
        st.done = True
        st.verdict = "objective_complete"
        return


def carry_from_result(result: MissionResult, prev_carry: dict | None = None) -> dict[str, float]:
    """Hero/force carry for seamless same-map continues."""
    prev = prev_carry or {}
    # recover HP slightly between missions
    tape_end = result.tape[-1] if result.tape else {}
    return {
        "vane_hp": min(1.0, float(tape_end.get("vane", 0.7)) + 0.15),
        "ketha_hp": min(1.0, float(tape_end.get("ketha", 0.7)) + 0.15),
        "player_strength": max(0.35, float(tape_end.get("p_str", 0.6)) * 0.9 + 0.1),
        "cohesion_proxy": 0.7,
        **{k: v for k, v in prev.items() if k.startswith("meta_")},
    }
