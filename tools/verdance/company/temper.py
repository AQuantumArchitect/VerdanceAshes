"""Hero temper: how each named hero comes to this drop, read from what the camp has done to them.

Owner direction (2026-11-09): heroes have their own behaviour on top of the AI's orders, driven by
personality and mood, and the mood moves with camp interactions, so a hero plays differently after
what happened at camp. Personality is the hero's doctrine (data/story/hero_codex.json ->
va_hero_doctrine.lua: line, skirm, rez...). Temper is the mood on top of it, two numbers in [-1, 1]:

  nerve   steadiness under fire. Bonds with the people on this drop steady a hero (a camp talk adds
          bond points; so does fighting together); a rival on the drop, a wound being carried, the
          times they have gone down, and bonded friends lost all shake it.
  drive   appetite to push. Bonds and experience raise it; grief lowers it.

The field reads them (game_verdance_unit_behavior.lua via mission.heroTemper): low nerve bails and
kites sooner, high nerve holds; high drive pushes. Continuous throughout: no thresholds, no ranks.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from verdance.common import WORKSPACE_ROOT, load_json

ADVERSARY = {"rivalry", "tension", "friction"}
# weights on the raw signals (bond points are 0..100, so 100 points with one drop-mate is 1.0)
W_SUPPORT_NERVE = 0.9
W_SUPPORT_DRIVE = 0.6
W_WOUNDED_NOW = 0.5      # carrying a wound into this drop
W_TIMES_DOWN = 0.12      # each time wounded or downed before (capped at 5)
W_GRIEF = 0.35           # each dead hero they were bonded to (25+ points)
W_LEVEL = 0.06           # each level above 1


def _web_polarity(workspace: Optional[Path]) -> Dict[frozenset, str]:
    """{frozenset({a, b}): polarity} from data/story/support_web.json, when it says."""
    p = Path(workspace or WORKSPACE_ROOT) / "data" / "story" / "support_web.json"
    data = load_json(p) if p.exists() else {}
    out: Dict[frozenset, str] = {}
    rows = data.get("pairs") or data.get("edges") or data.get("supports") or [] if isinstance(data, dict) else []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        a, b = r.get("a") or r.get("from"), r.get("b") or r.get("to")
        pol = r.get("polarity") or r.get("type")
        if a and b and pol:
            out[frozenset((str(a), str(b)))] = str(pol)
    return out


def _points(pairs: Dict[str, Any], a: str, b: str) -> float:
    x, y = sorted((a, b))
    row = pairs.get(f"{x}__{y}")
    return float((row or {}).get("points") or 0.0) if isinstance(row, dict) else 0.0


def temper_for_drop(state: Dict[str, Any], drop: Iterable[str], workspace: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """{heroId: {"nerve", "drive"}} for every hero on this drop."""
    drop = [str(h) for h in drop if h]
    pairs = ((state.get("attachments") or {}).get("pairBonds") or {})
    pairs = pairs if isinstance(pairs, dict) else {}
    chars = state.get("characters") or {}
    roster = {str(h.get("heroId")): h for h in ((state.get("roster") or {}).get("heroes") or []) if isinstance(h, dict)}
    dead = {hid for hid, h in roster.items() if str(h.get("status") or "") == "dead"}
    dead |= {hid for hid, c in chars.items() if isinstance(c, dict) and str(c.get("status") or "") == "dead"}
    polarity = _web_polarity(workspace)
    out: Dict[str, Dict[str, float]] = {}
    for hid in drop:
        support = 0.0
        for other in drop:
            if other == hid:
                continue
            pts = _points(pairs, hid, other) / 100.0
            sign = -1.0 if polarity.get(frozenset((hid, other))) in ADVERSARY else 1.0
            support += sign * pts
        grief = sum(1 for d in dead if d != hid and _points(pairs, hid, d) >= 25)
        h = roster.get(hid) or {}
        c = chars.get(hid) if isinstance(chars.get(hid), dict) else {}
        wounded_now = 1.0 if str(h.get("status") or "") == "wounded" else 0.0
        times_down = min(5, int(h.get("timesWounded") or c.get("wounds") or 0))
        level = int(h.get("level") or 1)
        nerve = (W_SUPPORT_NERVE * support - W_WOUNDED_NOW * wounded_now - W_TIMES_DOWN * times_down
                 - W_GRIEF * grief + W_LEVEL * (level - 1))
        drive = W_SUPPORT_DRIVE * support - W_GRIEF * grief + W_LEVEL * (level - 1)
        out[hid] = {"nerve": round(math.tanh(nerve), 3), "drive": round(math.tanh(drive), 3)}
    return out


__all__ = ["temper_for_drop"]
