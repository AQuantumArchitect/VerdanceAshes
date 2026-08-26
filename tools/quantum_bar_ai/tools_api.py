"""Tool surface for the player proxy — only player-legal reads + commit.

Tools (what the LLM may call):
  read_briefing     — mission card / voice lines
  read_hud          — current fair HUD
  read_beliefs      — umwelt mood snapshot (belief graph, not raw sim)
  read_recent       — last actions taken
  think             — write a short thought into the tape (no world effect)
  commit_action     — spend the turn (terminal for the decision step)

No tool exposes enemy_scale, exact HP floats, or sim RNG.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .fair_obs import FairHUD, PlayerFacingCard
from .mood import MoodSnapshot
from .policy import ACTIONS, Decision


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_briefing",
            "description": "Read the mission briefing / pause card (player-visible only).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_hud",
            "description": "Read the current combat HUD (coarse bands, heroes, phase, clock).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_beliefs",
            "description": (
                "Read your belief graph (umwelt mood): signed axes and estimated "
                "mission sensors. This is your comprehension, not ground truth."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_recent",
            "description": "List the last few actions you already committed this mission.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "How many recent actions (default 8)",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Record a short internal thought for the tape. Does not act.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thought": {"type": "string", "description": "One or two sentences."}
                },
                "required": ["thought"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit_action",
            "description": (
                "Commit exactly one combat action for this decision tick. "
                "Valid: " + ", ".join(ACTIONS)
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(ACTIONS),
                        "description": "Action name",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Short player-style reason",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
]


@dataclass
class ToolContext:
    card: PlayerFacingCard
    hud: FairHUD
    mood: MoodSnapshot
    recent: list[str]
    thoughts: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    name: str
    ok: bool
    content: str
    decision: Decision | None = None


class ToolBelt:
    """Execute tools against a ToolContext."""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.log: list[dict[str, Any]] = []

    def execute(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        args = args or {}
        fn = getattr(self, f"_tool_{name}", None)
        if fn is None:
            res = ToolResult(name=name, ok=False, content=f"unknown tool: {name}")
        else:
            try:
                res = fn(args)
            except Exception as e:  # noqa: BLE001
                res = ToolResult(name=name, ok=False, content=f"tool error: {type(e).__name__}: {e}")
        self.log.append(
            {
                "tool": name,
                "args": args,
                "ok": res.ok,
                "content": res.content[:500],
                "decision": res.decision.as_dict() if res.decision else None,
            }
        )
        return res

    def _tool_read_briefing(self, args: dict) -> ToolResult:
        return ToolResult(name="read_briefing", ok=True, content=self.ctx.card.briefing_block())

    def _tool_read_hud(self, args: dict) -> ToolResult:
        return ToolResult(name="read_hud", ok=True, content=self.ctx.hud.text())

    def _tool_read_beliefs(self, args: dict) -> ToolResult:
        m = self.ctx.mood
        s = m.signed()
        text = (
            "BELIEF GRAPH (not ground truth):\n"
            f"  {m.brief_line()}\n"
            f"  signed: "
            + " ".join(f"{k}={v:+.2f}" for k, v in s.items())
            + f"\n  heroes_est: vane={m.hero_vane_alive:.2f} ketha={m.hero_ketha_alive:.2f}\n"
            "  note: advantage/enemy are estimates from contact+team feel only."
        )
        return ToolResult(name="read_beliefs", ok=True, content=text)

    def _tool_read_recent(self, args: dict) -> ToolResult:
        n = int(args.get("n") or 8)
        recent = self.ctx.recent[-n:]
        content = "RECENT: " + (" → ".join(recent) if recent else "(none yet)")
        return ToolResult(name="read_recent", ok=True, content=content)

    def _tool_think(self, args: dict) -> ToolResult:
        thought = str(args.get("thought") or "").strip()[:400]
        self.ctx.thoughts.append(thought)
        return ToolResult(name="think", ok=True, content=f"noted: {thought}")

    def _tool_commit_action(self, args: dict) -> ToolResult:
        action = str(args.get("action") or "").strip().upper()
        reason = str(args.get("reason") or "commit").strip()[:200]
        if action not in ACTIONS:
            return ToolResult(
                name="commit_action",
                ok=False,
                content=f"invalid action {action!r}; valid={list(ACTIONS)}",
            )
        dec = Decision(action=action, reason=reason, source="tool", confidence=0.75)
        return ToolResult(
            name="commit_action",
            ok=True,
            content=f"committed {action}: {reason}",
            decision=dec,
        )


SYSTEM_TOOL_AGENT = """You are playing Verdance Ashes (Beyond All Reason campaign) as the human player.
You command a small strike team. NO base building. Heroes matter.

You do NOT have god-mode knowledge. Use tools to read:
  - read_briefing  (mission card)
  - read_hud       (what you feel on the field)
  - read_beliefs   (your umwelt mood graph — imperfect comprehension)
  - read_recent    (what you already did)
  - think          (optional short reasoning on the tape)
  - commit_action  (required to spend the turn)

Rules:
1. You may call several read/think tools first.
2. You must end by calling commit_action with exactly one action.
3. Valid actions: PUSH_OBJECTIVE, PROBE, FLANK, HOLD_AND_HEAL, RALLY, FALLBACK, EXTRACT, WAIT.
4. Protect heroes. Extract when the objective is nearly/done.
5. Do not invent unit counts, metal income, or enemy HP — you cannot see them.
6. Prefer the briefing's how-to-win over reckless aggression.
"""
