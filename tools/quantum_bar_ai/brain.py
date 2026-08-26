"""Grok / xAI brain for the player proxy.

Loads credentials from yurt.env (GROK_API_KEY / GROK_API_URL / GROK_MODEL)
or environment. Falls back cleanly when offline so sim iteration never blocks.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mood import MoodSnapshot
from .policy import ACTIONS, Decision, decide

YURT_ENV_CANDIDATES = (
    Path(r"C:\Users\Luke Spooner\ws-win\yurt\config\yurt.env"),
    Path.home() / "ws-win" / "yurt" / "config" / "yurt.env",
    Path.home() / ".config" / "yurt" / "yurt.env",
)

SYSTEM_BRIEF = """You are the player proxy for Beyond All Reason — Verdance Ashes campaign.
You command a small strike team (named heroes + ground units). NO base building.
Early missions: approach → take objective → extract. Heroes dying is bad.

Each turn you receive:
- MOOD graph (signed axes + mission sensors)
- MISSION card (kind, map, objective)
- last few actions

Reply with EXACTLY one line:
  ACTION <NAME> | <short reason>

Valid ACTION names:
  PUSH_OBJECTIVE, PROBE, FLANK, HOLD_AND_HEAL, RALLY, FALLBACK, EXTRACT, WAIT

No markdown, no JSON, no second line. Prefer objective progress; extract when done.
Protect heroes when threat is high and advantage is low."""


@dataclass
class BrainConfig:
    api_key: str = ""
    api_url: str = "https://api.x.ai/v1/chat/completions"
    model: str = "grok-code-fast"
    enabled: bool = False
    timeout_s: float = 45.0
    temperature: float = 0.35
    max_tokens: int = 64


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_brain_config() -> BrainConfig:
    file_env: dict[str, str] = {}
    for p in YURT_ENV_CANDIDATES:
        if p.is_file():
            file_env = _parse_env_file(p)
            break

    def pick(name: str, default: str = "") -> str:
        return (os.environ.get(name) or file_env.get(name) or default).strip()

    key = pick("GROK_API_KEY") or pick("XAI_API_KEY")
    cfg = BrainConfig(
        api_key=key,
        api_url=pick("GROK_API_URL", "https://api.x.ai/v1/chat/completions"),
        model=pick("GROK_MODEL", "grok-code-fast"),
        enabled=bool(key) and os.environ.get("QBAI_NO_LLM", "").strip() not in ("1", "true", "yes"),
    )
    # Allow force-offline for deterministic tests.
    if os.environ.get("QBAI_FORCE_LLM", "").strip() in ("0", "false", "no"):
        cfg.enabled = False
    return cfg


ACTION_RE = re.compile(
    r"\bACTION\s+(?P<action>[A-Z_]+)\s*(?:\|\s*(?P<reason>.+))?",
    re.IGNORECASE,
)
# Also accept bare action name as first token
BARE_RE = re.compile(r"^\s*(?P<action>[A-Z_]+)\b", re.IGNORECASE)


def parse_action_line(text: str) -> Decision | None:
    if not text:
        return None
    # strip think blocks if a reasoning model leaks them
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.I | re.S)
    text = re.sub(r"<think>.*\Z", "", text, flags=re.I | re.S)
    line = text.strip().splitlines()[0].strip()
    m = ACTION_RE.search(line) or ACTION_RE.search(text)
    if not m:
        m = BARE_RE.match(line)
        if not m:
            return None
        action = m.group("action").upper()
        reason = line[m.end() :].strip(" |:-")
    else:
        action = m.group("action").upper()
        reason = (m.groupdict().get("reason") or "").strip()
    if action not in ACTIONS:
        # fuzzy: allow partial
        for a in ACTIONS:
            if a.startswith(action) or action in a:
                action = a
                break
        else:
            return None
    return Decision(
        action=action,
        reason=reason or "llm",
        source="llm",
        confidence=0.7,
    )


class GrokBrain:
    """One next-action oracle over xAI chat completions."""

    def __init__(self, config: BrainConfig | None = None):
        self.config = config or load_brain_config()
        self.history: list[dict[str, str]] = []
        self.last_error: str | None = None
        self.call_count = 0

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

    def decide(
        self,
        mood: MoodSnapshot,
        *,
        mission: dict[str, Any] | None = None,
        recent: list[str] | None = None,
        fallback: bool = True,
    ) -> Decision:
        policy_dec = decide(
            mood,
            mission_kind=(mission or {}).get("kind", "eco_raid"),
            recent=recent or [],
        )
        if not self.available:
            policy_dec.source = "policy"
            return policy_dec

        user = self._format_user(mood, mission=mission or {}, recent=recent or [])
        messages = [{"role": "system", "content": SYSTEM_BRIEF}]
        # keep last few exchanges small
        for h in self.history[-4:]:
            messages.append(h)
        messages.append({"role": "user", "content": user})

        try:
            raw = self._http(
                {
                    "model": self.config.model,
                    "messages": messages,
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                }
            )
            self.call_count += 1
            content = (
                ((raw.get("choices") or [{}])[0].get("message") or {}).get("content")
                or ""
            )
            parsed = parse_action_line(content)
            self.history.append({"role": "user", "content": user})
            self.history.append({"role": "assistant", "content": content.strip()[:200]})
            if parsed:
                # hybrid: if LLM contradicts hard safety, keep policy
                if policy_dec.action == "FALLBACK" and parsed.action in (
                    "PUSH_OBJECTIVE",
                    "FLANK",
                ):
                    if mood.hero_vane_alive < 0.4 or mood.hero_ketha_alive < 0.4:
                        policy_dec.source = "hybrid"
                        policy_dec.reason = (
                            f"llm wanted {parsed.action} but heroes critical — "
                            f"kept FALLBACK ({parsed.reason})"
                        )
                        return policy_dec
                parsed.extras = {"raw": content.strip()[:240], "policy": policy_dec.action}
                return parsed
            self.last_error = f"unparseable llm: {content[:120]!r}"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            self.last_error = f"HTTP {e.code}: {body}"
        except Exception as e:  # noqa: BLE001 — seat must never die on LLM
            self.last_error = f"{type(e).__name__}: {e}"

        if fallback:
            policy_dec.source = "policy_fallback"
            policy_dec.reason = f"{policy_dec.reason} [llm fail: {self.last_error}]"
            return policy_dec
        raise RuntimeError(self.last_error or "llm failed")

    def _format_user(
        self,
        mood: MoodSnapshot,
        *,
        mission: dict[str, Any],
        recent: list[str],
    ) -> str:
        lines = [
            f"MISSION: {mission.get('id', '?')} | {mission.get('title', '')}",
            f"kind={mission.get('kind', '?')} map={mission.get('map_id', '?')} "
            f"obj={mission.get('objective_label', mission.get('objective_id', '?'))}",
            f"MOOD: {mood.brief_line()}",
            f"heroes: vane_alive={mood.hero_vane_alive:.2f} "
            f"ketha_alive={mood.hero_ketha_alive:.2f}",
        ]
        if recent:
            lines.append("RECENT: " + " → ".join(recent[-6:]))
        lines.append("Decide ACTION.")
        return "\n".join(lines)
