"""Ant-powered fair player agent.

Free chassis (deterministic, $0):
  read_briefing / read_hud / read_beliefs / read_recent / think via ToolBelt
  umwelt walls from FairHUD only

Steam (Grok subscription via yurt ant_brain):
  every N ticks, ant_client.ant_decide commits the action
  local tool policy fills gaps + falls back on ant failure
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ant_client import ant_decide, check_ant_ready
from .fair_obs import FairHUD, PlayerFacingCard
from .mood import MoodSnapshot
from .tool_agent import AgentStep, LocalToolAgent
from .tools_api import ToolBelt, ToolContext


@dataclass
class AntToolAgent:
    """Subscription ant brain on top of free tool chassis."""

    name: str = "ant_subscription"
    every_n: int = 4
    max_turns: int = 1
    force: bool = True
    dry_run: bool = False
    call_count: int = 0
    last_error: str | None = None
    last_billing: str | None = None
    last_wall_s: float | None = None
    _local: LocalToolAgent = field(default_factory=LocalToolAgent)
    _turn: int = 0
    _ready: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self._ready = check_ant_ready()

    @property
    def available(self) -> bool:
        return bool(self._ready and self._ready.get("ok"))

    def act(
        self,
        *,
        card: PlayerFacingCard,
        hud: FairHUD,
        mood: MoodSnapshot,
        recent: list[str],
    ) -> AgentStep:
        self._turn += 1
        ctx = ToolContext(card=card, hud=hud, mood=mood, recent=list(recent))
        belt = ToolBelt(ctx)

        # Free chassis — always run fair reads (matches ant doctrine)
        r_hud = belt.execute("read_hud")
        r_beliefs = belt.execute("read_beliefs")
        if not recent:
            r_brief = belt.execute("read_briefing")
        else:
            r_brief = None
        belt.execute("read_recent", {"n": 8})

        tool_reads = {
            "read_hud": r_hud.content,
            "read_beliefs": r_beliefs.content,
        }
        if r_brief is not None:
            tool_reads["read_briefing"] = r_brief.content

        use_ant = (
            self.available
            and not self.dry_run
            and (self._turn % max(1, self.every_n) == 0)
        )

        if use_ant:
            res = ant_decide(
                card=card,
                hud=hud,
                mood=mood,
                recent=recent,
                tool_reads=tool_reads,
                max_turns=self.max_turns,
                force=self.force,
                dry_run=False,
            )
            self.call_count += 1
            self.last_billing = res.billing
            self.last_wall_s = res.wall_s
            if res.ok and res.decision and not res.skipped:
                belt.execute(
                    "think",
                    {
                        "thought": (
                            f"ant subscription wall_s={res.wall_s} → "
                            f"{res.decision.action}: {res.decision.reason}"
                        )
                    },
                )
                commit = belt.execute(
                    "commit_action",
                    {"action": res.decision.action, "reason": res.decision.reason},
                )
                assert commit.decision is not None
                commit.decision.source = "ant_subscription"
                commit.decision.extras = res.decision.extras
                return AgentStep(
                    decision=commit.decision,
                    tool_trace=list(belt.log),
                    thoughts=list(ctx.thoughts),
                    backend="ant_subscription",
                )
            self.last_error = res.error or "ant skipped/failed"
            belt.execute(
                "think",
                {"thought": f"ant failed ({self.last_error}) — local tools fallback"},
            )

        # Free local tool policy (also used when ant not scheduled this tick)
        step = self._local.act(card=card, hud=hud, mood=mood, recent=recent)
        # Merge free reads we already did into trace for honesty
        step.tool_trace = list(belt.log) + [
            t for t in step.tool_trace if t.get("tool") in ("think", "commit_action")
        ]
        if use_ant:
            step.backend = "local_tools_ant_fallback"
            step.raw_error = self.last_error
            step.decision.source = "local_tools_ant_fallback"
        else:
            step.backend = "local_tools_chassis"
        return step
