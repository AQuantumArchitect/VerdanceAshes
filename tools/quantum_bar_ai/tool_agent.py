"""Tool-using player agent: belief graph + thoughts + commit_action.

Two backends share the same tool belt:
  - LocalToolAgent: pure belief/HUD policy expressed AS tool calls (offline, fair)
  - GrokToolAgent:  xAI chat.completions with tools= (when network/key available)

Neither backend receives SimTruth.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .brain import BrainConfig, load_brain_config
from .fair_obs import FairHUD, PlayerFacingCard
from .mood import MoodSnapshot
from .policy import ACTIONS, Decision, decide
from .tools_api import SYSTEM_TOOL_AGENT, TOOL_SPECS, ToolBelt, ToolContext


@dataclass
class AgentStep:
    decision: Decision
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    backend: str = "local"
    raw_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.as_dict(),
            "tool_trace": self.tool_trace,
            "thoughts": self.thoughts,
            "backend": self.backend,
            "raw_error": self.raw_error,
        }


class LocalToolAgent:
    """Fair offline agent: uses the same tools a human-shaped LLM would.

    Deliberately routes through ToolBelt so the tape always shows tool use,
    not magic private fields. Optionally overlays trained bar_brain weights.
    """

    name = "local_tools"

    def __init__(self, *, use_bar_brain: bool = True):
        self.use_bar_brain = use_bar_brain
        self._brain = None
        if use_bar_brain:
            try:
                from .bar_brain import BarBrain

                self._brain = BarBrain()
            except Exception:
                self._brain = None

    def act(
        self,
        *,
        card: PlayerFacingCard,
        hud: FairHUD,
        mood: MoodSnapshot,
        recent: list[str],
    ) -> AgentStep:
        ctx = ToolContext(card=card, hud=hud, mood=mood, recent=list(recent))
        belt = ToolBelt(ctx)

        # Mandatory fair reads (what a careful player checks)
        belt.execute("read_hud")
        belt.execute("read_beliefs")
        if not recent:
            belt.execute("read_briefing")
        belt.execute("read_recent", {"n": 8})

        # Decision from fair mood only (already wall-fed from HUD, not sim truth)
        allow_eco = not card.no_base_building
        no_metal = (
            "no metal" in (card.situation + card.threats + card.how_to_win).lower()
            or "converter" in (card.situation + card.objective_text).lower()
        )
        eco_bands = {
            "eco": hud.eco_feel,
            "metal": hud.metal_feel,
            "energy": hud.energy_feel,
            "buildpower": hud.buildpower_feel,
        }
        # fair width band if player_view / card carried it
        _card_d = card.as_dict() if hasattr(card, "as_dict") else {}
        _width_band = getattr(card, "width_band", None) or _card_d.get("width_band")
        policy_dec = decide(
            mood,
            mission_kind=card.kind,
            recent=recent,
            allow_eco=allow_eco,
            eco_bands=eco_bands if allow_eco else None,
            no_metal_map=no_metal,
            width_band=_width_band,
        )

        # Overlay HUD hard rules a player can see without math
        action = policy_dec.action
        reason = policy_dec.reason
        extract_spam = sum(1 for a in recent[-6:] if a == "EXTRACT")
        push_run = sum(1 for a in recent[-10:] if a == "PUSH_OBJECTIVE")
        flank_run = sum(1 for a in recent[-8:] if a == "FLANK")
        heal_run = sum(1 for a in recent[-6:] if a == "HOLD_AND_HEAL")
        build_run = sum(
            1
            for a in recent[-10:]
            if a in ("BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "EXPAND_FRONT", "TECH_UP")
        )
        fortified = (
            "ferrocrete" in card.threats.lower()
            or "fortif" in card.threats.lower()
            or "fortified" in card.how_to_win.lower()
            or "route around" in card.how_to_win.lower()
            or "citadel" in card.situation.lower()
            or "siege" in card.kind
        )
        tired = hud.team_feeling in ("strained", "breaking")
        stalled = (
            len(recent) >= 10
            and hud.objective_bar in ("empty", "started", "half")
            and push_run >= 7
        )
        eco_dry = allow_eco and hud.eco_feel in ("dry", "thin")
        energy_dry = allow_eco and hud.energy_feel in ("dry", "thin")

        # EXTRACT only when objective is DONE (or phase EXTRACT). "nearly" means finish.
        if hud.objective_bar == "done" or hud.phase == "EXTRACT":
            action, reason = "EXTRACT", "HUD objective done — extract"
        elif hud.objective_bar == "nearly":
            if tired and heal_run < 2:
                action, reason = "HOLD_AND_HEAL", "nearly done but tired — patch then finish"
            else:
                action, reason = "PUSH_OBJECTIVE", "HUD nearly done — finish before extract"
        elif extract_spam >= 2 and hud.objective_bar not in ("done",):
            action, reason = "PUSH_OBJECTIVE", "extract too early — back on the objective"
        elif hud.vane in ("down", "critical") or hud.ketha in ("down", "critical") or hud.phase == "CRITICAL":
            if hud.team_feeling == "breaking" or hud.vane == "down" or hud.ketha == "down":
                action, reason = "FALLBACK", "HUD critical heroes — break contact"
            else:
                action, reason = "HOLD_AND_HEAL", "HUD critical — stabilize"
        elif tired and hud.objective_bar not in ("done",) and heal_run < 2:
            action, reason = "HOLD_AND_HEAL", "team strained — reconstitute before push"
        elif allow_eco and energy_dry and hud.contact in ("none", "light", "moderate") and build_run < 6:
            action, reason = "BUILD_ENERGY", "HUD energy thin — plant power"
        elif allow_eco and eco_dry and not no_metal and hud.metal_feel in ("dry", "thin") and build_run < 6:
            if hud.contact in ("none", "light", "moderate"):
                action, reason = "BUILD_MEX", "HUD metal thin — plant mex"
        elif allow_eco and eco_dry and no_metal and build_run < 6:
            action, reason = "BUILD_ENERGY", "no-metal map — converter path needs energy"
        elif card.kind == "survive_wilds" and hud.team_feeling in ("strained", "breaking"):
            action, reason = "RALLY", "wilds HUD — tighten the knot"
        elif stalled:
            if allow_eco and eco_dry and build_run < 4:
                action, reason = "EXPAND_FRONT", "stalled + thin eco — expand then re-push"
            elif fortified and flank_run < 4:
                action, reason = "FLANK", "stalled on fortified — change the angle"
            elif heal_run < 2:
                action, reason = "HOLD_AND_HEAL", "stalled — reset the line then re-push"
            else:
                action, reason = "FLANK", "stalled after heal — re-approach from side"
        elif fortified and hud.objective_bar in ("empty", "started") and flank_run < 4:
            if hud.approach_feel in ("far", "closing", "on_it") and not (
                allow_eco and eco_dry and build_run < 3
            ):
                action, reason = "FLANK", "briefing: fortified — work the flank"
        elif hud.clock_band == "red" and hud.objective_bar in ("empty", "started", "half"):
            if hud.team_feeling in ("fresh", "steady") and hud.contact in ("none", "light", "moderate"):
                action, reason = "PUSH_OBJECTIVE", "clock red, still standing — commit"
            elif hud.contact in ("heavy", "extreme"):
                action, reason = "FLANK", "clock red under fire — refuse frontal"
            else:
                action, reason = "PUSH_OBJECTIVE", "clock red — force the objective"
        elif hud.approach_feel == "far" and hud.objective_bar == "empty":
            if allow_eco and eco_dry and build_run < 3 and hud.contact in ("none", "light"):
                action, reason = "BUILD_ENERGY", "far + thin eco — plant before march"
            elif hud.contact in ("none", "light"):
                action, reason = "PROBE", "still far — probe in"
            else:
                action, reason = "FLANK", "contact on approach — swing wide"
        elif hud.objective_bar in ("half", "started") and action in ("EXTRACT", "WAIT", "PROBE"):
            action, reason = "PUSH_OBJECTIVE", "objective incomplete — keep pressure"

        # Trained bar_brain overlay (campaign scars + eco manifold) — never overrides
        # hard survival / extract rules above (decide_overlay respects FALLBACK/EXTRACT).
        source = "local_tools"
        if self._brain is not None:
            from .policy import Decision as _Dec

            base = _Dec(action, reason, source="local_tools", confidence=0.72)
            hud_d = hud.as_dict() if hasattr(hud, "as_dict") else {}
            # fair width band from mission card extras if present
            wb = getattr(card, "width_band", None) or (card.as_dict() if hasattr(card, "as_dict") else {}).get(
                "width_band"
            )
            if wb:
                hud_d = dict(hud_d)
                hud_d["width_band"] = wb
            over = self._brain.decide_overlay(
                base,
                mood=mood,
                kind=card.kind,
                hud=hud_d,
                allow_eco=allow_eco,
                recent=recent,
            )
            if over.action != action:
                belt.execute(
                    "think",
                    {
                        "thought": (
                            f"bar_brain scar: {action}→{over.action} "
                            f"({over.reason[:100]})"
                        )
                    },
                )
                action, reason = over.action, over.reason
                source = "local_tools+bar_brain"

        thought = (
            f"phase={hud.phase} contact={hud.contact} obj={hud.objective_bar} "
            f"team={hud.team_feeling}"
        )
        if allow_eco and hud.eco_feel != "n/a":
            thought += f" eco={hud.eco_feel}"
        thought += f" → {action}"
        belt.execute("think", {"thought": thought})
        commit = belt.execute("commit_action", {"action": action, "reason": reason})
        assert commit.decision is not None
        commit.decision.source = source
        return AgentStep(
            decision=commit.decision,
            tool_trace=list(belt.log),
            thoughts=list(ctx.thoughts),
            backend="local_tools" if source == "local_tools" else "local_tools+brain",
        )


class GrokToolAgent:
    """xAI tool-calling agent. Falls back to LocalToolAgent on any failure."""

    name = "grok_tools"

    def __init__(self, config: BrainConfig | None = None, *, max_tool_rounds: int = 6):
        self.config = config or load_brain_config()
        self.max_tool_rounds = max_tool_rounds
        self.call_count = 0
        self.last_error: str | None = None
        self._local = LocalToolAgent()
        # raise max tokens for tool loops
        if self.config.max_tokens < 256:
            self.config.max_tokens = 256

    @property
    def available(self) -> bool:
        return bool(self.config.enabled and self.config.api_key)

    def _http(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.config.api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def act(
        self,
        *,
        card: PlayerFacingCard,
        hud: FairHUD,
        mood: MoodSnapshot,
        recent: list[str],
    ) -> AgentStep:
        if not self.available:
            step = self._local.act(card=card, hud=hud, mood=mood, recent=recent)
            step.backend = "local_tools_no_key"
            return step

        ctx = ToolContext(card=card, hud=hud, mood=mood, recent=list(recent))
        belt = ToolBelt(ctx)

        user_kickoff = (
            "New decision tick. Use tools. You have not been given sim internals.\n"
            f"Quick HUD peek (also available via read_hud):\n{hud.text()}\n"
            "Call tools as needed, then commit_action."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_TOOL_AGENT},
            {"role": "user", "content": user_kickoff},
        ]

        try:
            for _round in range(self.max_tool_rounds):
                payload = {
                    "model": self.config.model,
                    "messages": messages,
                    "tools": TOOL_SPECS,
                    "tool_choice": "auto",
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                }
                raw = self._http(payload)
                self.call_count += 1
                msg = (raw.get("choices") or [{}])[0].get("message") or {}
                tool_calls = msg.get("tool_calls") or []
                content = msg.get("content")

                # Append assistant message (with tool_calls if any)
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                if not tool_calls:
                    # try parse free text ACTION as last resort
                    if content:
                        from .brain import parse_action_line

                        parsed = parse_action_line(content)
                        if parsed:
                            belt.execute("think", {"thought": f"freeform: {content[:160]}"})
                            commit = belt.execute(
                                "commit_action",
                                {"action": parsed.action, "reason": parsed.reason},
                            )
                            if commit.decision:
                                commit.decision.source = "llm_freeform"
                                return AgentStep(
                                    decision=commit.decision,
                                    tool_trace=list(belt.log),
                                    thoughts=list(ctx.thoughts),
                                    backend="grok_freeform",
                                )
                    break

                decided: Decision | None = None
                for tc in tool_calls:
                    fn = (tc.get("function") or {})
                    name = fn.get("name") or ""
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                    result = belt.execute(name, args)
                    # tool response message
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id") or name,
                            "content": result.content[:2000],
                        }
                    )
                    if result.decision is not None:
                        decided = result.decision
                if decided is not None:
                    decided.source = "grok_tools"
                    return AgentStep(
                        decision=decided,
                        tool_trace=list(belt.log),
                        thoughts=list(ctx.thoughts),
                        backend="grok_tools",
                    )

            self.last_error = "tool loop ended without commit_action"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            self.last_error = f"HTTP {e.code}: {body}"
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"

        # Fair fallback — still tool-traced local
        step = self._local.act(card=card, hud=hud, mood=mood, recent=recent)
        step.backend = "local_tools_fallback"
        step.raw_error = self.last_error
        step.decision.source = "local_tools_fallback"
        step.decision.reason = f"{step.decision.reason} [llm: {self.last_error}]"
        return step
