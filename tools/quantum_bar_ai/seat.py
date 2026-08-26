"""Player proxy seat — observe → mood → decide → act loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from umwelt.boot import build_engine

from .brain import GrokBrain, load_brain_config
from .mood import MoodSnapshot, pack_wall_sensors, read_mood
from .policy import Decision, decide
from .sim import EARLY_ARC, MissionCard, MissionResult, carry_from_result, run_mission
from .world import TICK_S, player_proxy_spec


@dataclass
class SeatConfig:
    use_llm: bool = True
    llm_every_n: int = 1  # 1 = every tick; 3 = LLM every 3rd tick (cheap)
    seed: int = 7
    verbose: bool = False


@dataclass
class PlayerProxySeat:
    """One long-lived proxy mind that can play a sequence of missions."""

    config: SeatConfig = field(default_factory=SeatConfig)
    engine: Any = field(default=None)
    brain: GrokBrain | None = field(default=None)
    results: list[MissionResult] = field(default_factory=list)
    carry: dict[str, float] = field(default_factory=dict)
    _turn_global: int = 0

    def __post_init__(self) -> None:
        if self.engine is None:
            self.engine = build_engine(spec=player_proxy_spec())
        if self.brain is None and self.config.use_llm:
            self.brain = GrokBrain(load_brain_config())

    def decide_fn(self, mood: MoodSnapshot, card: MissionCard, recent: list[str]) -> Decision:
        self._turn_global += 1
        use_llm = (
            self.config.use_llm
            and self.brain is not None
            and self.brain.available
            and (self._turn_global % max(1, self.config.llm_every_n) == 0)
        )
        if use_llm:
            return self.brain.decide(
                mood,
                mission=card.as_dict(),
                recent=recent,
                fallback=True,
            )
        return decide(mood, mission_kind=card.kind, recent=recent)

    def play_mission(self, card: MissionCard, *, seed: int | None = None) -> MissionResult:
        result = run_mission(
            card,
            engine=self.engine,
            decide_fn=self.decide_fn,
            seed=seed if seed is not None else self.config.seed + len(self.results),
            carry=self.carry or None,
            verbose=self.config.verbose,
        )
        self.results.append(result)
        # seamless continue carry when not a hard wipe
        if result.verdict not in ("heroes_dead",):
            self.carry = carry_from_result(result, self.carry)
        else:
            # reset heroes after wipe (campaign wound fiction later)
            self.carry = {
                "vane_hp": 0.55,
                "ketha_hp": 0.55,
                "player_strength": 0.6,
                "cohesion_proxy": 0.65,
            }
        return result

    def play_arc(
        self,
        cards: list[MissionCard] | None = None,
        *,
        max_missions: int | None = None,
    ) -> list[MissionResult]:
        cards = list(cards or EARLY_ARC)
        if max_missions is not None:
            cards = cards[:max_missions]
        out: list[MissionResult] = []
        for card in cards:
            if self.config.verbose:
                print(f"\n=== {card.id}: {card.title} ({card.kind}) ===")
            r = self.play_mission(card)
            out.append(r)
            if self.config.verbose:
                print(
                    f"  → {r.verdict} ticks={r.ticks} prog={r.progress:.2f} "
                    f"heroes={r.heroes_alive_frac:.2f} sources={r.brain_source_counts}"
                )
        return out

    def mood_now(self) -> MoodSnapshot:
        return read_mood(self.engine, turn=self._turn_global)

    def save_field(self, path: str) -> None:
        self.engine.save(path)

    def summary(self) -> dict[str, Any]:
        wins = sum(
            1
            for r in self.results
            if r.verdict in ("victory", "extracted", "objective_complete", "timeout_partial")
            and r.progress >= 0.5
        )
        hard_wins = sum(
            1 for r in self.results if r.verdict in ("extracted", "objective_complete")
        )
        return {
            "missions": len(self.results),
            "hard_wins": hard_wins,
            "soft_wins": wins,
            "verdicts": [r.verdict for r in self.results],
            "progress": [r.progress for r in self.results],
            "llm_calls": self.brain.call_count if self.brain else 0,
            "llm_available": bool(self.brain and self.brain.available),
            "llm_last_error": self.brain.last_error if self.brain else None,
            "mood": self.mood_now().as_dict(),
        }
