"""Subscription brain via yurt ant_brain (Grok CLI + grok.com session).

Law: yurt-sync/work/_wargen/plans/GROK_SUBSCRIPTION_BRAINS.md
  - Prefer ~/.grok/auth.json (subscription)
  - Refuse XAI_API_KEY unless GROK_ALLOW_API=1
  - real_spend_usd = 0 under subscription billing

This is the steam piston for quantum-BAR-AI. Free chassis remains:
FairHUD + umwelt walls + LocalToolAgent tool belt. Ant only *decides*.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .brain import parse_action_line
from .fair_obs import FairHUD, PlayerFacingCard
from .mood import MoodSnapshot
from .policy import ACTIONS, Decision

_ANT_CORAL = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral")
_SYNC = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync")
_VITALS = _SYNC / "commons" / "vitals"
_VERDANCE_CASTE = "verdance-proxy-ant"

# Strip metered API keys from the child env so ant_brain guard stays subscription.
_METERED_KEYS = ("XAI_API_KEY", "GROK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def _ensure_ant_import() -> Any:
    coral = str(_ANT_CORAL)
    if coral not in sys.path:
        sys.path.insert(0, coral)
    import ant_brain  # type: ignore

    return ant_brain


def scrub_metered_env() -> dict[str, str]:
    """Return env copy without metered API keys (subscription path only)."""
    env = dict(os.environ)
    for k in _METERED_KEYS:
        env.pop(k, None)
    # Explicitly allow only subscription unless operator opts into API
    env.pop("GROK_ALLOW_API", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


@dataclass
class AntBrainResult:
    ok: bool
    decision: Decision | None
    billing: str = "subscription"
    wall_s: float | None = None
    raw_tail: str = ""
    error: str | None = None
    skipped: bool = False
    caste: str = _VERDANCE_CASTE
    prompt_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "decision": self.decision.as_dict() if self.decision else None,
            "billing": self.billing,
            "wall_s": self.wall_s,
            "raw_tail": self.raw_tail[-800:],
            "error": self.error,
            "skipped": self.skipped,
            "caste": self.caste,
            "prompt_path": self.prompt_path,
        }


def check_ant_ready() -> dict[str, Any]:
    """Probe subscription auth without spending a turn."""
    try:
        ant = _ensure_ant_import()
        # Temporarily hide metered keys for the guard
        saved = {k: os.environ.pop(k) for k in _METERED_KEYS if k in os.environ}
        try:
            guard = ant.check_auth_guard()
        finally:
            os.environ.update(saved)
        return {
            "ok": bool(guard.get("ok")),
            "billing": guard.get("billing"),
            "grok": guard.get("grok"),
            "error": guard.get("error"),
            "caste": _VERDANCE_CASTE,
            "coral": str(_ANT_CORAL),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def build_decision_prompt(
    *,
    card: PlayerFacingCard,
    hud: FairHUD,
    mood: MoodSnapshot,
    recent: list[str],
    tool_reads: dict[str, str] | None = None,
) -> str:
    """Player-legal context only — never SimTruth."""
    tool_block = ""
    if tool_reads:
        parts = []
        for name, content in tool_reads.items():
            parts.append(f"### tool:{name}\n{content}")
        tool_block = "\n\n".join(parts)

    return f"""# verdance-proxy-ant — one combat decision (subscription brain)

You are the human player of Verdance Ashes (Beyond All Reason campaign).
Strike team only. NO base building. Heroes matter.

You do NOT have god-mode knowledge. Below is only what a player sees:
- mission briefing
- coarse HUD
- your umwelt belief graph (imperfect)
- recent actions

## Law
- Billing: Grok **subscription** (ant_brain / grok.com session). Not metered API.
- Reply with EXACTLY one line after optional short thought:
  ACTION <NAME> | <short reason>
- Valid names: {", ".join(ACTIONS)}
- Prefer briefing how-to-win. Fortified → flank. Extract only when objective done.
- Protect heroes when critical/breaking.

## Mission card
{card.briefing_block()}

## HUD now
{hud.text()}

## Belief graph
{mood.brief_line()}
signed: {mood.signed()}

## Recent actions
{" → ".join(recent[-10:]) if recent else "(none)"}

## Free chassis tool reads
{tool_block or "(none — decide from card+HUD+beliefs)"}

## Commit
One line only:
ACTION <NAME> | <reason>
"""


def ant_decide(
    *,
    card: PlayerFacingCard,
    hud: FairHUD,
    mood: MoodSnapshot,
    recent: list[str],
    tool_reads: dict[str, str] | None = None,
    max_turns: int = 1,
    force: bool = True,
    dry_run: bool = False,
) -> AntBrainResult:
    """Summon one subscription brain turn via ant_brain.spawn_grok."""
    ant = _ensure_ant_import()

    saved = {k: os.environ.pop(k) for k in _METERED_KEYS if k in os.environ}
    try:
        guard = ant.check_auth_guard()
        if not guard.get("ok"):
            return AntBrainResult(
                ok=False,
                decision=None,
                billing=str(guard.get("billing") or "unknown"),
                error=str(guard.get("error") or "auth guard failed"),
            )

        prompt = build_decision_prompt(
            card=card,
            hud=hud,
            mood=mood,
            recent=recent,
            tool_reads=tool_reads,
        )

        # Patch env for child: spawn_grok uses os.environ in subprocess
        for k in _METERED_KEYS:
            os.environ.pop(k, None)

        out = ant.spawn_grok(
            grok_bin=str(guard["grok"]),
            caste=_VERDANCE_CASTE,
            prompt=prompt,
            max_turns=max_turns,
            dry_run=dry_run,
            billing=str(guard.get("billing") or "subscription"),
            force=force,
        )
    finally:
        os.environ.update(saved)

    if out.get("skipped"):
        return AntBrainResult(
            ok=True,
            decision=None,
            skipped=True,
            error=str(out.get("reason") or "skipped"),
            billing=str(out.get("billing") or "subscription"),
            wall_s=out.get("wall_s"),
        )
    if out.get("dry_run"):
        return AntBrainResult(
            ok=True,
            decision=None,
            skipped=True,
            error="dry_run",
            billing="subscription",
            prompt_path=out.get("prompt_path"),
        )
    if not out.get("ok"):
        return AntBrainResult(
            ok=False,
            decision=None,
            error=str(out.get("error") or out.get("stderr_tail") or f"rc={out.get('rc')}"),
            billing=str(out.get("billing") or "subscription"),
            wall_s=out.get("wall_s"),
            raw_tail=str(out.get("stdout_tail") or "") + "\n" + str(out.get("stderr_tail") or ""),
            prompt_path=out.get("prompt_path"),
        )

    raw = str(out.get("stdout_tail") or "")
    # Prefer last ACTION line in output
    decision = None
    for line in reversed(raw.splitlines()):
        decision = parse_action_line(line)
        if decision:
            break
    if decision is None:
        decision = parse_action_line(raw)
    if decision is None:
        # last resort: find any ACTION token
        m = re.search(
            r"\b(" + "|".join(ACTIONS) + r")\b",
            raw,
            re.I,
        )
        if m:
            decision = Decision(
                action=m.group(1).upper(),
                reason="parsed bare action from ant stdout",
                source="ant_subscription",
                confidence=0.55,
            )
    if decision is None:
        return AntBrainResult(
            ok=False,
            decision=None,
            error="could not parse ACTION from ant/grok stdout",
            billing="subscription",
            wall_s=out.get("wall_s"),
            raw_tail=raw[-800:],
            prompt_path=out.get("prompt_path"),
        )

    decision.source = "ant_subscription"
    decision.confidence = 0.8
    decision.extras = {
        "billing": "subscription",
        "wall_s": out.get("wall_s"),
        "caste": _VERDANCE_CASTE,
        "raw": raw[-240:],
    }
    return AntBrainResult(
        ok=True,
        decision=decision,
        billing="subscription",
        wall_s=out.get("wall_s"),
        raw_tail=raw[-800:],
        prompt_path=out.get("prompt_path"),
    )
