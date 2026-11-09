"""The company's reserve: the army it builds, keeps and brings.

Everything the player builds, survives with and lifts off the pad goes into the reserve (the
roster's ``reserve``: unitDef -> count). Hero packs and escorts are not reserve: they come back
with their hero every drop. At each Drop the player chooses what to bring (``roster.cadre`` is
this drop's bring; the builder spawns it), up to the drop limit: how much of the reserve one
drop can start with, in metal value (metal + energy / energyPerMetal, the same measure as the
hero packs). The code calls it the lift cap (``lift_cap`` / ``liftCap``).

The drop limit grows with time on Verdance (owner call, 2026-11-09): DROP_PER_MISSION for every
sortie played, whatever its verdict, with no ceiling. The longer the campaign, the more of the
reserve the company can start a drop with. Units left in the field stay where they were left;
they are not in the reserve.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from verdance.common import WORKSPACE_ROOT

LIFT_BASE = 0.0            # the first drop is the packs alone
DROP_PER_MISSION = 1000.0  # every sortie played lets the next drops start with 1k metal more
VETERAN_LIFT = 1000.0      # the commander's veteran_cadre perk: one more mission's worth
NOT_PLAYED = ("abandon",)  # a sortie abandoned before it was fought does not count
_COSTS: Dict[str, Any] = {}


def _costs(workspace: Optional[Path] = None) -> Dict[str, Any]:
    key = str(workspace or WORKSPACE_ROOT)
    if key not in _COSTS:
        p = Path(workspace or WORKSPACE_ROOT) / "data" / "story" / "unit_costs.json"
        try:
            _COSTS[key] = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            _COSTS[key] = {"units": {}, "names": {}}
    return _COSTS[key]


def unit_value(unit_def: str, workspace: Optional[Path] = None, epm: float = 70.0) -> float:
    m, e = (_costs(workspace).get("units") or {}).get(str(unit_def)) or (100.0, 1000.0)
    return float(m) + float(e) / epm


def unit_name(unit_def: str, workspace: Optional[Path] = None) -> str:
    return (_costs(workspace).get("names") or {}).get(str(unit_def)) or str(unit_def)


def _counts(d: Any) -> Dict[str, int]:
    if not isinstance(d, dict):
        return {}
    return {str(k): int(v) for k, v in d.items() if isinstance(v, (int, float)) and int(v) > 0}


def ensure_reserve(roster: Dict[str, Any]) -> Dict[str, int]:
    """The reserve on the roster. A save from before the reserve starts it from the old cadre."""
    if not isinstance(roster.get("reserve"), dict):
        roster["reserve"] = dict(_counts(roster.get("cadre")))
    return roster["reserve"]


def missions_played(state: Dict[str, Any]) -> int:
    """Sorties fought, whatever the verdict: victory, partial, defeat. An abandoned sortie
    (left before it was fought) does not count."""
    n = 0
    for b in state.get("history") or []:
        if isinstance(b, dict) and str(b.get("verdict") or "").lower() not in NOT_PLAYED:
            n += 1
    return n


def lift_cap(state: Dict[str, Any]) -> float:
    """The drop limit: how much of the reserve, in metal value, a drop can start with."""
    perks = (((state.get("roster") or {}).get("commander") or {}).get("perks") or [])
    veteran = VETERAN_LIFT if "veteran_cadre" in perks else 0.0  # the commander's level-3 perk
    return LIFT_BASE + DROP_PER_MISSION * missions_played(state) + veteran


def bring_value(bring: Dict[str, int], workspace: Optional[Path] = None) -> float:
    return sum(unit_value(d, workspace) * n for d, n in bring.items())


def clamp_bring(requested: Any, reserve: Dict[str, int], cap: float, workspace: Optional[Path] = None) -> Dict[str, int]:
    """What actually boards: never more than the reserve holds, never past the drop limit
    (the most valuable requested units board first)."""
    want = {d: min(n, int(reserve.get(d, 0))) for d, n in _counts(requested).items()}
    out: Dict[str, int] = {}
    room = cap
    for d in sorted(want, key=lambda d: -unit_value(d, workspace)):
        v = unit_value(d, workspace)
        k = min(want[d], int(room // v)) if v > 0 else want[d]
        if k > 0:
            out[d] = k
            room -= k * v
    return out


def default_bring(reserve: Dict[str, int], cap: float, workspace: Optional[Path] = None) -> Dict[str, int]:
    """The suggestion: the most valuable units that fit."""
    return clamp_bring(reserve, reserve, cap, workspace)


def homecoming(roster: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """After a sortie: the units brought left the reserve; everything that lifted off the pad
    (minus hero packs and hired units) comes back into it. Brought units that died or stayed in
    the field are not in it."""
    reserve = ensure_reserve(roster)
    brought = _counts(roster.get("cadre"))
    for d, n in brought.items():
        left = int(reserve.get(d, 0)) - n
        if left > 0:
            reserve[d] = left
        else:
            reserve.pop(d, None)
    going = ((result.get("manifest") or {}).get("going") or {})
    lifted = _counts(going.get("units"))
    # a hero's pack comes home with the hero; what the shop hired was for this drop only
    for key in ("packUnits", "hiredUnits"):
        for d, n in _counts(going.get(key)).items():
            if d in lifted:
                lifted[d] = max(0, lifted[d] - n)
    lifted = {d: n for d, n in lifted.items() if n > 0 and not d.endswith("com")}
    for d, n in lifted.items():
        reserve[d] = int(reserve.get(d, 0)) + n
    roster["cadre"] = {}
    return {"brought": brought, "lifted": lifted, "reserve": dict(reserve)}


def hub_surface(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """For the hub: the reserve with names and values, the drop limit and the suggestion."""
    roster = state.get("roster") or {}
    reserve = _counts(roster.get("reserve")) if isinstance(roster.get("reserve"), dict) else _counts(roster.get("cadre"))
    cap = lift_cap(state)
    rows = sorted(
        ({"unitDef": d, "name": unit_name(d, workspace), "count": n, "value": round(unit_value(d, workspace))}
         for d, n in reserve.items()),
        key=lambda r: -r["value"],
    )
    return {"units": rows, "liftCap": round(cap), "missionsPlayed": missions_played(state),
            "suggested": default_bring(reserve, cap, workspace),
            "perMission": round(DROP_PER_MISSION), "base": round(LIFT_BASE)}
