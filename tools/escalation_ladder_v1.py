#!/usr/bin/env python3
"""Escalation ladder v1 — the authored complexity/difficulty curve.

One authority for "how hard and how complex is mission N", answering the
Drop 4 baseline findings (see docs/archive/plans/drop4_escalation.md):

- Difficulty: a per-mission **scale window** [lo, hi]. The compiler still
  computes enemyScale from campaign state (zone presence, dial, craft knobs,
  merc standing), then clamps the result into the window. Zone-memory
  saturation can no longer flatline act 2 at "heavy", and the m4->m5 cliff is
  gone: pacing is authored, performance still moves the needle inside the
  window, and the owner's difficulty dial scales the window itself (dial 1.25
  raises both walls 25%).
- Complexity: per-mission **secondary objectives** (bonus first, then
  required) and an **objective strength** tier: surgical (today's single
  centerpiece) -> raze (the whole camp is the objective) -> purge (clear the
  board of the enemy faction).

Authored overrides live in data/escalation/mission_escalation.json; this
module carries matching built-in defaults so the pipeline works without the
file. Ladder entries are merged over the defaults per mission number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_WS_DEFAULT = Path(__file__).resolve().parents[1]
_LADDER_CACHE: Dict[str, Dict[str, Any]] = {}

# Built-in ladder. Mirrors data/escalation/mission_escalation.json — the JSON
# is the owner-tunable copy; keep both in sync when retuning.
# secondaries entries are SPECS ({"required": bool}); the engine resolves them
# to concrete zones from the quest board when materializing the intent.
DEFAULT_LADDER: Dict[str, Any] = {
    "schemaVersion": "verdance-escalation-ladder/1.0",
    "defaults": {
        "scaleWindow": [1.0, 1.6],
        "secondaries": [],
        "objectiveStrength": "surgical",
        "wavesMode": None,
    },
    "missions": {
        "1": {"scaleWindow": [0.35, 0.50], "wavesMode": "off"},
        "2": {"scaleWindow": [0.45, 0.62], "wavesMode": "off"},
        "3": {"scaleWindow": [0.55, 0.75], "wavesMode": "off"},
        "4": {"scaleWindow": [0.65, 0.88], "wavesMode": "light",
              "secondaries": [{"required": False}]},
        "5": {"scaleWindow": [0.75, 1.00], "wavesMode": "light",
              "secondaries": [{"required": False}]},
        "6": {"scaleWindow": [0.85, 1.12], "wavesMode": "light",
              "secondaries": [{"required": True}]},
        "7": {"scaleWindow": [0.95, 1.25], "wavesMode": "full",
              "secondaries": [{"required": True}]},
        "8": {"scaleWindow": [1.05, 1.40], "wavesMode": "full",
              "secondaries": [{"required": True}, {"required": False}]},
        "9": {"scaleWindow": [1.15, 1.55], "wavesMode": "full",
              "objectiveStrength": "raze",
              "secondaries": [{"required": True}]},
        "10": {"scaleWindow": [1.30, 1.70], "wavesMode": "full",
               "objectiveStrength": "purge"},
    },
    # Finales keep their own objective machinery (the spine IS the strong
    # objective); the ladder only bounds their scale.
    "finale": {"scaleWindow": [1.70, 2.60], "wavesMode": "full",
               "objectiveStrength": "finale", "secondaries": []},
}


def load_ladder(workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Authored ladder JSON merged over built-in defaults (cached per path)."""
    candidates = []
    if workspace is not None:
        candidates.append(Path(workspace) / "data" / "escalation" / "mission_escalation.json")
    candidates.append(_WS_DEFAULT / "data" / "escalation" / "mission_escalation.json")
    for path in candidates:
        key = str(path)
        if key in _LADDER_CACHE:
            return _LADDER_CACHE[key]
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        merged = json.loads(json.dumps(DEFAULT_LADDER))
        for k in ("defaults", "finale"):
            if isinstance(data.get(k), dict):
                merged[k].update(data[k])
        for num, entry in (data.get("missions") or {}).items():
            if isinstance(entry, dict):
                merged["missions"].setdefault(str(num), {})
                merged["missions"][str(num)].update(entry)
        _LADDER_CACHE[key] = merged
        return merged
    return DEFAULT_LADDER


def plan_for_mission(mission_number: int, is_finale: bool = False,
                     workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Merged ladder entry for one mission: defaults <- per-mission/finale."""
    ladder = load_ladder(workspace)
    plan = dict(ladder.get("defaults") or {})
    if is_finale:
        plan.update(ladder.get("finale") or {})
    else:
        entry = (ladder.get("missions") or {}).get(str(int(mission_number)))
        if entry is None and int(mission_number) > 10:
            # Post-ladder non-finale missions ride the finale window.
            entry = ladder.get("finale") or {}
        plan.update(entry or {})
    plan["missionNumber"] = int(mission_number)
    plan["secondaries"] = [dict(s) for s in (plan.get("secondaries") or [])]
    return plan


def clamp_scale(scale: float, window: Optional[List[float]],
                dial: float = 1.0) -> float:
    """Clamp a computed enemyScale into the ladder window (dial-scaled)."""
    if not window or len(window) < 2:
        return round(float(scale), 3)
    d = float(dial or 1.0) or 1.0
    lo = float(window[0]) * d
    hi = float(window[1]) * d
    if hi < lo:
        lo, hi = hi, lo
    return round(min(hi, max(lo, float(scale))), 3)
