"""Fair-play mission sim: agent sees only PlayerFacingCard + FairHUD.

Hidden SimTruth drives combat. Wall sensors come from fair HUD only.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from umwelt.boot import build_engine

from .eco_manifold import EcoState, apply_build_action
from .fair_obs import FairHUD, build_fair_hud, fair_hud_to_wall_sensors
from .first_arc import ArcMission, FIRST_ARC, build_first_arc
from .mood import pack_claim_sensors, pack_referee_sensors, read_mood
from .policy import action_effects
from .ant_agent import AntToolAgent
from .tool_agent import AgentStep, GrokToolAgent, LocalToolAgent
from .world import TICK_S, player_proxy_spec
from .lane_war import (
    LineFront,
    apply_line_order,
    decide_line,
    lane_objective_progress,
    tick_lane_combat,
)
from .campaign_manifold import MissionSolutionSpace


class AgentLike(Protocol):
    def act(self, *, card, hud, mood, recent) -> AgentStep: ...


@dataclass
class FairMissionResult:
    mission_id: str
    verdict: str
    ticks: int
    progress: float
    heroes_alive_frac: float
    actions: list[str] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    tool_trace_summary: list[dict[str, Any]] = field(default_factory=list)
    backends: dict[str, int] = field(default_factory=dict)
    tape: list[dict[str, Any]] = field(default_factory=list)
    player_card: dict[str, Any] = field(default_factory=dict)
    difficulty_label: str = ""
    notes: str = ""

    @property
    def won(self) -> bool:
        return self.verdict in ("extracted", "objective_complete")

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["won"] = self.won
        return d


@dataclass
class _TruthState:
    tick: int = 0
    approach: float = 0.0
    progress: float = 0.0
    threat: float = 0.2
    player_strength: float = 0.7
    enemy_strength: float = 0.5
    cohesion: float = 0.75
    vane_hp: float = 1.0
    ketha_hp: float = 1.0
    extract: float = 0.0
    done: bool = False
    verdict: str = "active"
    last_action: str = ""
    eco: EcoState = field(default_factory=EcoState)
    # multi-predicate trackers (diverging solutions)
    eco_wreck: float = 0.0
    strike_cut: float = 0.0
    lane_hold: float = 0.0
    siege_break: float = 0.0
    survive_clock: float = 0.0
    line_front: LineFront | None = None

    def heroes_frac(self) -> float:
        return ((1.0 if self.vane_hp > 0.05 else 0.0) + (1.0 if self.ketha_hp > 0.05 else 0.0)) / 2.0

    def predicate_scores(self) -> dict[str, float]:
        return {
            "objective_hold": self.progress,
            "eco_wreck": max(self.eco_wreck, self.eco.eco_level() if self.eco else 0.0),
            "lane_hold": self.lane_hold,
            "strike_cut": self.strike_cut,
            "siege_break": self.siege_break,
            "survive_clock": self.survive_clock,
        }


def run_fair_mission(
    mission: ArcMission,
    *,
    agent: AgentLike | None = None,
    engine=None,
    seed: int = 7,
    carry: dict[str, float] | None = None,
    verbose: bool = False,
) -> FairMissionResult:
    agent = agent or LocalToolAgent()
    if engine is None:
        engine = build_engine(spec=player_proxy_spec())

    rng = random.Random(seed)
    truth = mission.truth
    show_eco = not mission.card.no_base_building
    no_metal = "no metal" in (mission.card.situation + mission.card.threats).lower() or (
        mission.map_id == "greenest_fields" and mission.kind == "eco_expand"
    )
    st = _TruthState(
        player_strength=truth.player_start_strength,
        enemy_strength=min(0.95, truth.enemy_start_strength * truth.enemy_scale),
        threat=0.22 + (0.12 if truth.fortified else 0.0),
        eco=EcoState(
            metal=0.2 if show_eco else 0.1,
            energy=0.25 if show_eco else 0.1,
            metal_income=0.12 if show_eco and not no_metal else 0.05,
            energy_income=0.18 if show_eco else 0.08,
            buildpower=0.2 if show_eco else 0.05,
        ),
    )
    if carry:
        st.vane_hp = float(carry.get("vane_hp", st.vane_hp))
        st.ketha_hp = float(carry.get("ketha_hp", st.ketha_hp))
        # blend mission start strength with carried force (no double 0.92 tax)
        carried = float(carry.get("player_strength", st.player_strength))
        st.player_strength = min(0.9, 0.55 * truth.player_start_strength + 0.45 * carried)
        st.cohesion = float(carry.get("cohesion_proxy", st.cohesion))
        if show_eco and carry.get("eco_level") is not None:
            el = float(carry["eco_level"])
            st.eco.metal_income = min(0.55, 0.12 + el * 0.35)
            st.eco.energy_income = min(0.55, 0.15 + el * 0.35)
            st.eco.buildpower = min(0.5, 0.15 + el * 0.3)

    # Lane membrane for seize/hold when geometry authored
    ss: MissionSolutionSpace | None = getattr(mission, "solution_space", None)
    width = float(ss.width) if ss is not None else 0.3
    geo = getattr(mission, "lane_geometry", None)
    if geo is not None and mission.kind in ("seize_lane", "hold_plateau", "multipressure"):
        st.line_front = LineFront(geometry=geo)

    t0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    duration = truth.duration_ticks
    actions: list[str] = []
    thoughts: list[str] = []
    backends: dict[str, int] = {}
    tape: list[dict[str, Any]] = []
    tool_summaries: list[dict[str, Any]] = []

    for tick in range(duration):
        st.tick = tick
        eco_bands = st.eco.bands() if show_eco else None
        hud = build_fair_hud(
            tick=tick,
            duration_ticks=duration,
            progress=st.progress,
            approach=st.approach,
            threat=st.threat,
            player_strength=st.player_strength,
            enemy_strength=st.enemy_strength,
            vane_hp=st.vane_hp,
            ketha_hp=st.ketha_hp,
            extract=st.extract,
            rng=rng,
            last_action=st.last_action,
            eco_bands=eco_bands,
            show_eco=show_eco,
        )
        # Fair lane feel only (no enemy mass numbers)
        if st.line_front is not None:
            try:
                hud_dict = hud.as_dict() if hasattr(hud, "as_dict") else {}
                if isinstance(hud_dict, dict):
                    # attach for agent via card path only if FairHUD allows extras — tape only
                    pass
            except Exception:
                pass

        # Belief update from FAIR HUD only
        wall = fair_hud_to_wall_sensors(hud)
        engine.ingest(sensor_readings=wall, now=t0 + timedelta(seconds=TICK_S * tick))
        mood = read_mood(engine, turn=tick)

        step = agent.act(card=mission.card, hud=hud, mood=mood, recent=actions)
        dec = step.decision
        actions.append(dec.action)
        thoughts.extend(step.thoughts)
        backends[step.backend] = backends.get(step.backend, 0) + 1
        st.last_action = dec.action

        claims = pack_claim_sensors(dec.action, mood)
        if claims:
            engine.ingest(
                sensor_readings=claims,
                now=t0 + timedelta(seconds=TICK_S * tick + 0.25),
            )

        _step_truth(
            st,
            mission,
            dec.action,
            rng,
            no_metal_map=no_metal,
            width=width,
            mood_signed=mood.signed() if hasattr(mood, "signed") else None,
        )

        row = {
            "tick": tick,
            "action": dec.action,
            "reason": dec.reason,
            "source": dec.source,
            "backend": step.backend,
            "hud": hud.as_dict(),
            "mood": mood.brief_line(),
            "thoughts": list(step.thoughts),
            "tools": [t.get("tool") for t in step.tool_trace],
            # truth kept only in operator tape, not fed to agent next turn
            "_truth": {
                "progress": round(st.progress, 3),
                "approach": round(st.approach, 3),
                "threat": round(st.threat, 3),
                "p": round(st.player_strength, 3),
                "e": round(st.enemy_strength, 3),
                "vane": round(st.vane_hp, 3),
                "ketha": round(st.ketha_hp, 3),
                "eco": round(st.eco.eco_level(), 3),
                "lane_hold": round(st.lane_hold, 3),
                "predicates": {k: round(v, 3) for k, v in st.predicate_scores().items()},
                "line_order": (
                    st.line_front.last_order.as_dict()
                    if st.line_front and st.line_front.last_order
                    else None
                ),
                "lane_bands": st.line_front.fair_bands() if st.line_front else None,
            },
        }
        tape.append(row)
        tool_summaries.append(
            {
                "tick": tick,
                "backend": step.backend,
                "tools": [t.get("tool") for t in step.tool_trace],
                "action": dec.action,
            }
        )

        if verbose and tick % 10 == 0:
            lo = ""
            if st.line_front and st.line_front.last_order:
                lo = f" line={st.line_front.last_order.order}"
            print(
                f"  t={tick:03d} [{step.backend:18s}] {dec.action:16s} "
                f"HUD {hud.phase}/{hud.objective_bar}/{hud.contact} "
                f"truth_prog={st.progress:.2f}{lo}"
            )

        if st.done:
            break

    if not st.done:
        switches = sum(1 for i in range(1, len(actions)) if actions[i] != actions[i - 1])
        # Multi-predicate clear when solution_space declares any-of wins
        if _multi_predicate_clear(st, ss, action_switches=switches):
            st.verdict = "extracted" if st.extract >= 0.5 else "objective_complete"
        elif st.progress >= 0.9 and st.extract >= 0.5:
            st.verdict = "extracted"
        elif st.progress >= 0.9:
            st.verdict = "objective_complete"
        elif st.heroes_frac() <= 0:
            st.verdict = "heroes_dead"
        elif st.progress < 0.5:
            st.verdict = "timeout_fail"
        else:
            st.verdict = "timeout_partial"
        st.done = True

    engine.ingest(
        sensor_readings=pack_referee_sensors(
            {
                "verdict": st.verdict,
                "progress": st.progress,
                "final_threat": st.threat,
                "clock_frac": min(1.0, st.tick / max(1, duration)),
                "heroes_alive_frac": st.heroes_frac(),
            }
        ),
        now=t0 + timedelta(seconds=TICK_S * (st.tick + 1)),
    )

    return FairMissionResult(
        mission_id=mission.id,
        verdict=st.verdict,
        ticks=st.tick + 1,
        progress=round(st.progress, 4),
        heroes_alive_frac=st.heroes_frac(),
        actions=actions,
        thoughts=thoughts[-40:],
        tool_trace_summary=tool_summaries,
        backends=backends,
        tape=tape,
        player_card=mission.player_view(),
        difficulty_label=truth.difficulty_label,
        notes=mission.card.plain_objective,
    )


def _multi_predicate_clear(
    st: _TruthState,
    ss: MissionSolutionSpace | None,
    *,
    thr: float = 0.72,
    action_switches: int = 0,
) -> bool:
    """True if any declared win predicate is satisfied (diverging solutions).

    Wide cards also allow **predicate interference**: coherent multipath progress
    can clear slightly below classical thr when amplitudes constructively align.
    Thrash-switching strategies dephases that bonus.
    """
    if ss is None or not ss.win_predicates:
        return False
    # Narrow cards still need real progress — don't auto-clear on a lone side meter
    min_prog = 0.55 if ss.width < 0.4 else 0.35
    scores = st.predicate_scores()
    for p in ss.win_predicates:
        if scores.get(p, 0.0) >= thr and st.progress >= min_prog:
            return True
    # classic combo still works
    if "objective_hold" in ss.win_predicates and st.progress >= 0.92 and st.extract >= 0.55:
        return True
    # Quantum multipath: interference clear when width open and progress floor met
    if ss.width >= 0.55 and st.progress >= min_prog:
        try:
            from .quantum_membrane import PredicateAmplitudes

            pa = PredicateAmplitudes.from_scores(scores, list(ss.win_predicates))
            score = pa.thrash_penalty(action_switches)
            # need meaningful multipath energy, not single weak blip
            if score >= thr * 0.92 and max(scores.get(p, 0.0) for p in ss.win_predicates) >= thr * 0.78:
                return True
        except Exception:
            pass
    return False


def _action_to_line_bias(action: str) -> tuple[float, float, float]:
    """Map combat action → (aggression, caution, cohesion) deltas for lane AI."""
    if action in ("PUSH_OBJECTIVE", "EXPAND_FRONT"):
        return 0.55, -0.1, 0.3
    if action == "FLANK":
        return 0.45, 0.0, 0.1
    if action in ("HOLD_AND_HEAL", "DEFEND_BASE", "RALLY"):
        return -0.1, 0.4, 0.55
    if action == "FALLBACK":
        return -0.4, 0.6, 0.2
    if action == "PROBE":
        return 0.15, 0.2, 0.35
    return 0.1, 0.1, 0.4


def _step_truth(
    st: _TruthState,
    mission: ArcMission,
    action: str,
    rng: random.Random,
    *,
    no_metal_map: bool = False,
    width: float = 0.3,
    mood_signed: dict[str, float] | None = None,
) -> None:
    truth = mission.truth
    fx = action_effects(action)
    fort = 1.18 if truth.fortified else 1.0
    noise = lambda s: 1.0 + rng.uniform(-s, s)  # noqa: E731
    kind = mission.kind
    show_eco = not mission.card.no_base_building
    ss: MissionSolutionSpace | None = getattr(mission, "solution_space", None)
    if ss is not None:
        width = float(ss.width)

    # Eco tick (player-visible bands only; truth eco is operator-side)
    build_actions = (
        "BUILD_MEX",
        "BUILD_ENERGY",
        "BUILD_CON",
        "EXPAND_FRONT",
        "RECLAIM",
        "TECH_UP",
    )
    if show_eco or action in build_actions:
        st.eco = apply_build_action(
            st.eco,
            action if action in build_actions else "WAIT",
            no_metal_map=no_metal_map,
            noise=noise(0.08),
        )

    # Eco feeds combat strength mildly
    eco_boost = 1.0 + 0.15 * st.eco.eco_level() if show_eco else 1.0

    out = 0.04 * fx["dmg_out"] * st.player_strength * eco_boost * noise(0.1)
    inn = 0.02 * fx["dmg_in"] * st.enemy_strength * fort * truth.enemy_scale * noise(0.1)

    # wilds ambient chew
    if kind == "survive_wilds":
        inn += 0.008 * fort * noise(0.1)
        if action == "RALLY":
            inn *= 0.7
        if action == "PROBE":
            inn *= 0.85

    st.approach = max(0.0, min(1.0, st.approach + fx["approach"] * noise(0.08)))
    approach_gate = 0.3 + 0.7 * st.approach

    # eco_expand can progress without deep approach if footprint grows
    if kind == "eco_expand" and st.eco.eco_level() > 0.25:
        approach_gate = max(approach_gate, 0.45)

    if st.approach > 0.1 or (kind == "eco_expand" and action.startswith("BUILD")):
        st.enemy_strength = max(0.05, st.enemy_strength - out * max(0.35, approach_gate))
        st.player_strength = max(0.12, st.player_strength - inn)

    hero_share = inn * 0.48
    if action == "FALLBACK":
        hero_share *= 0.45
    if action in ("HOLD_AND_HEAL", "RALLY", "DEFEND_BASE"):
        hero_share *= 0.62
    if action.startswith("BUILD"):
        hero_share *= 0.75  # building under fire still risky
    splash = hero_share * (1.05 - 0.35 * st.cohesion)
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

    st.cohesion = max(0.1, min(1.0, st.cohesion + fx.get("cohesion", 0.0)))

    # Objective progress by kind
    can_progress = st.player_strength > 0.14 and (
        st.approach > 0.2
        or kind in ("eco_expand", "survive_wilds")
        or action in ("BUILD_MEX", "BUILD_ENERGY", "EXPAND_FRONT", "HOLD_AND_HEAL")
    )
    if can_progress:
        rate = fx["obj_rate"] * max(0.35, approach_gate)
        if kind == "seize_lane" or kind == "hold_plateau":
            rate *= 1.05 if action in ("PUSH_OBJECTIVE", "HOLD_AND_HEAL", "FLANK", "DEFEND_BASE") else 0.5
        elif kind == "eco_raid":
            rate *= 1.25 if action in ("PUSH_OBJECTIVE", "FLANK") else 0.65
            # decoy: pure eco does not clear early eco_raid
            if action.startswith("BUILD"):
                rate *= 0.15
        elif kind == "strike_relay":
            rate *= 1.15 if action in ("PUSH_OBJECTIVE", "FLANK") else 0.6
            if action == "PROBE":
                rate *= 0.85
            if action.startswith("BUILD"):
                rate *= 0.2
        elif kind == "eco_expand":
            # footprint + optional raid
            eco_part = 0.04 * st.eco.eco_level()
            combat_part = rate * (1.2 if action in ("PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT") else 0.7)
            rate = eco_part + combat_part * 0.55
            if action in ("BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "EXPAND_FRONT"):
                rate = max(rate, 0.025 + 0.04 * st.eco.eco_level())
        elif kind == "siege":
            rate *= 1.1 if action in ("PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT") else 0.55
            rate *= 0.85 + 0.4 * st.eco.eco_level()  # siege needs feed
            if truth.fortified and action == "FLANK":
                rate *= 1.2
        elif kind == "survive_wilds":
            rate *= 1.15 if action in ("PUSH_OBJECTIVE", "PROBE", "RALLY", "FLANK") else 0.55
            if action in ("HOLD_AND_HEAL", "RALLY"):
                rate = max(rate, 0.02)  # survival itself advances corridor slightly
        elif kind == "multipressure":
            rate *= 1.1 if action in ("PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT", "DEFEND_BASE") else 0.55
            rate *= 0.9 + 0.25 * st.eco.eco_level()
            # wide multipath: eco-heavy and strike-heavy both advance different predicates
            if action in ("BUILD_MEX", "BUILD_ENERGY", "BUILD_CON"):
                rate = max(rate, 0.02 + 0.05 * st.eco.eco_level())

        rate *= 0.95 + 0.5 * (1.0 - st.enemy_strength)
        if action == "PUSH_OBJECTIVE":
            rate *= 1.15
        if truth.fortified and action == "PUSH_OBJECTIVE" and st.approach < 0.55:
            rate *= 0.7
        if truth.fortified and action == "FLANK":
            rate *= 1.25
            st.approach = min(1.0, st.approach + 0.03)
        if st.progress >= 0.7 and action in (
            "PUSH_OBJECTIVE",
            "HOLD_AND_HEAL",
            "FLANK",
            "EXPAND_FRONT",
            "DEFEND_BASE",
        ):
            rate = max(rate, 0.035)
        st.progress = min(1.0, st.progress + rate * noise(0.08))

    # --- Lane membrane tick (line war) ---
    if st.line_front is not None:
        ms = mood_signed or {}
        agg, caut, coh = _action_to_line_bias(action)
        agg = 0.6 * agg + 0.4 * float(ms.get("aggression", 0.0))
        caut = 0.6 * caut + 0.4 * float(ms.get("caution", 0.0))
        coh = 0.6 * coh + 0.4 * float(ms.get("cohesion", 0.5))
        order = decide_line(
            st.line_front,
            aggression=agg,
            caution=caut,
            cohesion=coh,
            width=width,
            enemy=False,
            rng=rng,
        )
        apply_line_order(st.line_front, order, dt=1.0)
        # Enemy line AI: campaign disposition ⊗ density (operator-side only)
        try:
            from .enemy_line_ai import plan_enemy_line, apply_enemy_plan
            from .campaign_manifold import CampaignRho

            eplan = plan_enemy_line(
                st.line_front,
                rho=CampaignRho(),
                width=width,
                rng=rng,
            )
            apply_enemy_plan(st.line_front, eplan, dt=0.7)
        except Exception:
            pass
        tick_lane_combat(
            st.line_front,
            player_strength=st.player_strength,
            enemy_strength=st.enemy_strength,
            fortified=truth.fortified,
            rng=rng,
            dt=1.0,
        )
        lane_prog = lane_objective_progress(st.line_front, width=width)
        st.lane_hold = max(st.lane_hold, lane_prog)
        # blend lane progress into mission progress for seize/hold
        if kind in ("seize_lane", "hold_plateau"):
            st.progress = max(st.progress, 0.55 * st.progress + 0.45 * lane_prog)
            st.progress = min(1.0, st.progress)
        elif kind == "multipressure":
            st.progress = min(1.0, max(st.progress, 0.7 * st.progress + 0.3 * lane_prog))

    # --- Diverging predicate trackers ---
    # eco_raid: wreck means combat on converters — pure BUILD is a decoy
    if kind == "eco_raid":
        if action in ("PUSH_OBJECTIVE", "FLANK"):
            st.eco_wreck = min(1.0, st.eco_wreck + 0.06 * noise(0.05))
            st.eco_wreck = min(1.0, max(st.eco_wreck, st.progress * 0.95))
    elif kind in ("eco_expand", "multipressure"):
        if action in ("BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "EXPAND_FRONT"):
            st.eco_wreck = min(1.0, max(st.eco_wreck, st.eco.eco_level()))
            if kind == "multipressure":
                st.eco_wreck = min(1.0, st.eco_wreck + 0.03)
        if action in ("PUSH_OBJECTIVE", "FLANK") and kind == "multipressure":
            st.eco_wreck = min(1.0, st.eco_wreck + 0.02)
    if kind in ("strike_relay", "multipressure"):
        if action in ("PUSH_OBJECTIVE", "FLANK", "PROBE"):
            st.strike_cut = min(1.0, st.strike_cut + (0.055 if action != "PROBE" else 0.03) * noise(0.05))
    if kind == "siege":
        if action in ("PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT"):
            st.siege_break = min(1.0, st.siege_break + 0.05 * noise(0.05) * (0.85 + 0.4 * st.eco.eco_level()))
    if kind == "survive_wilds":
        st.survive_clock = min(1.0, st.tick / max(1.0, truth.duration_ticks * 0.85))
        if st.heroes_frac() < 0.5:
            st.survive_clock *= 0.5

    contact = st.approach * 0.5 + (
        0.28 if action in ("PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT") else 0.1
    )
    wild_extra = 0.12 if kind == "survive_wilds" else 0.0
    st.threat = max(
        0.05,
        min(
            0.98,
            0.55 * st.enemy_strength * fort
            + 0.25 * contact
            - 0.2 * st.player_strength
            + wild_extra
            + rng.uniform(-0.03, 0.03),
        ),
    )

    if st.progress >= 0.92:
        push = fx.get("extract_push", 0.12 if action == "EXTRACT" else 0.04)
        st.extract = min(1.0, st.extract + push)
    elif action == "EXTRACT":
        st.approach = max(0.0, st.approach - 0.03)
        st.extract = min(0.4, st.extract + 0.02)

    if st.vane_hp <= 0.05 and st.ketha_hp <= 0.05:
        st.done = True
        st.verdict = "heroes_dead"
        return

    # Diverging solutions: any declared predicate may clear early mid-mission
    # action_switches unknown mid-tick — use 0 (no thrash penalty mid-mission)
    if ss is not None and _multi_predicate_clear(st, ss, thr=0.78, action_switches=0):
        if st.extract < 0.45 and action == "EXTRACT":
            st.extract = min(1.0, st.extract + 0.15)
        if st.extract >= 0.5 or st.progress >= 0.85 or _multi_predicate_clear(st, ss, thr=0.85):
            st.done = True
            st.verdict = "extracted" if st.extract >= 0.5 else "objective_complete"
            return

    if st.progress >= 0.92 and st.extract >= 0.8:
        st.done = True
        st.verdict = "extracted"
        return
    if st.progress >= 0.98 and kind in ("eco_raid", "strike_relay", "siege"):
        st.done = True
        st.verdict = "objective_complete"
        return
    if st.progress >= 0.98 and kind in ("seize_lane", "hold_plateau", "survive_wilds") and st.extract >= 0.55:
        st.done = True
        st.verdict = "extracted"
        return
    if st.progress >= 0.98 and kind in ("eco_expand", "multipressure"):
        if st.extract >= 0.55 or st.eco.eco_level() >= 0.55:
            st.done = True
            st.verdict = "objective_complete" if st.extract < 0.55 else "extracted"
            return


def carry_from_fair(result: FairMissionResult) -> dict[str, float]:
    """Between-mission refit — player gets a short patch, not a full rebuild."""
    end = result.tape[-1]["_truth"] if result.tape else {}
    # Campaign fiction: short refit between sorties (rez + rest), not magic heal.
    vane = min(1.0, float(end.get("vane", 0.7)) + 0.22)
    ketha = min(1.0, float(end.get("ketha", 0.7)) + 0.22)
    p = float(end.get("p", 0.6))
    # Recover toward a floor so late-arc is playable but still tired
    p = max(0.48, min(0.85, p * 0.85 + 0.22))
    eco = float(end.get("eco", 0.2))
    eco = max(0.15, min(0.7, eco * 0.7 + 0.15))
    return {
        "vane_hp": vane,
        "ketha_hp": ketha,
        "player_strength": p,
        "cohesion_proxy": 0.72,
        "eco_level": eco,
    }


def play_missions(
    missions: list[ArcMission],
    *,
    agent: AgentLike | None = None,
    difficulty: float = 1.0,
    seed: int = 7,
    verbose: bool = True,
    use_llm: bool = False,
    use_ant: bool = False,
    ant_every_n: int = 4,
    schema: str = "quantum-bar-ai-fair-arc/0.1",
    label: str = "arc",
) -> dict[str, Any]:
    """Play an ordered list of ArcMissions with carry + shared umwelt engine."""
    if agent is None:
        if use_ant:
            agent = AntToolAgent(every_n=ant_every_n)
        elif use_llm:
            agent = GrokToolAgent()
        else:
            agent = LocalToolAgent()
    engine = build_engine(spec=player_proxy_spec())
    carry: dict[str, float] = {}
    results: list[FairMissionResult] = []

    if verbose and use_ant:
        ready = getattr(agent, "_ready", None) or {}
        print(
            f"ant subscription ready={ready.get('ok')} billing={ready.get('billing')} "
            f"every_n={ant_every_n}"
        )
        if ready.get("error"):
            print(f"  ant guard note: {ready.get('error')}")

    for i, m in enumerate(missions):
        if verbose:
            print(f"\n=== {m.id}: {m.card.title} ({m.kind}) diff={m.truth.difficulty_label} ===")
        r = run_fair_mission(
            m,
            agent=agent,
            engine=engine,
            seed=seed + i * 13,
            carry=carry or None,
            verbose=verbose,
        )
        results.append(r)
        if r.verdict != "heroes_dead":
            carry = carry_from_fair(r)
        else:
            carry = {
                "vane_hp": 0.55,
                "ketha_hp": 0.55,
                "player_strength": 0.58,
                "cohesion_proxy": 0.6,
                "eco_level": 0.2,
            }
        if verbose:
            print(
                f"  → {r.verdict} ticks={r.ticks} prog={r.progress:.2f} "
                f"heroes={r.heroes_alive_frac:.2f} backends={r.backends}"
            )

    hard = sum(1 for r in results if r.won)
    return {
        "schemaVersion": schema,
        "label": label,
        "difficulty": difficulty,
        "seed": seed,
        "use_llm": use_llm,
        "use_ant": use_ant,
        "ant_every_n": ant_every_n if use_ant else None,
        "agent": getattr(agent, "name", type(agent).__name__),
        "hard_wins": hard,
        "missions": len(results),
        "cleared": hard == len(results),
        "verdicts": [r.verdict for r in results],
        "progress": [r.progress for r in results],
        "results": [r.as_dict() for r in results],
        "llm_calls": getattr(agent, "call_count", 0),
        "llm_error": getattr(agent, "last_error", None),
        "llm_billing": getattr(agent, "last_billing", None),
        "ant_ready": getattr(agent, "_ready", None) if use_ant else None,
    }


def play_first_arc(
    *,
    agent: AgentLike | None = None,
    difficulty: float = 1.0,
    seed: int = 7,
    verbose: bool = True,
    use_llm: bool = False,
    use_ant: bool = False,
    ant_every_n: int = 4,
) -> dict[str, Any]:
    return play_missions(
        build_first_arc(difficulty=difficulty),
        agent=agent,
        difficulty=difficulty,
        seed=seed,
        verbose=verbose,
        use_llm=use_llm,
        use_ant=use_ant,
        ant_every_n=ant_every_n,
        schema="quantum-bar-ai-fair-arc/0.1",
        label="arc_1",
    )


def play_campaign(
    *,
    agent: AgentLike | None = None,
    difficulty: float = 1.0,
    seed: int = 7,
    verbose: bool = True,
    use_llm: bool = False,
    use_ant: bool = False,
    ant_every_n: int = 4,
    arcs: tuple[int, ...] = (1, 2, 3),
    use_craft: bool | None = None,
) -> dict[str, Any]:
    """Play full multi-arc Verdance campaign under fair-proxy contract."""
    from .campaign import build_full_campaign, campaign_meta

    missions = build_full_campaign(difficulty=difficulty, arcs=arcs, use_craft=use_craft)
    rep = play_missions(
        missions,
        agent=agent,
        difficulty=difficulty,
        seed=seed,
        verbose=verbose,
        use_llm=use_llm,
        use_ant=use_ant,
        ant_every_n=ant_every_n,
        schema="quantum-bar-ai-fair-campaign/0.2",
        label="campaign_" + "_".join(str(a) for a in arcs),
    )
    # per-arc tallies
    by_arc: dict[str, dict[str, Any]] = {}
    for r in rep["results"]:
        mid = r.get("mission_id") or ""
        try:
            n = int(mid.split("_")[-1])
        except ValueError:
            n = 0
        arc = "1" if n <= 5 else ("2" if n <= 10 else "3")
        bucket = by_arc.setdefault(arc, {"wins": 0, "total": 0, "verdicts": []})
        bucket["total"] += 1
        bucket["verdicts"].append(r.get("verdict"))
        if r.get("won"):
            bucket["wins"] += 1
    for a, b in by_arc.items():
        b["cleared"] = b["wins"] == b["total"]
    rep["arcs_played"] = list(arcs)
    rep["by_arc"] = by_arc
    rep["campaign_meta"] = campaign_meta()
    rep["cleared_all_arcs"] = all(by_arc.get(str(a), {}).get("cleared") for a in arcs)
    return rep
