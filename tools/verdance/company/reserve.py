"""The company's reserve: the army it builds, keeps and brings.

Everything the player builds, survives with and lifts off the pad goes into the reserve (the
roster's ``reserve``: unitDef -> count). Hero packs and escorts are not reserve: they come back
with their hero every drop. At each Drop the player chooses what to bring (``roster.cadre`` is
this drop's bring; the builder spawns it), up to the lift limit: what one drop can carry, in
metal value (metal + energy / energyPerMetal, the same measure as the hero packs). The limit
grows with what the company has actually brought home (owner call, 2026-11-09): it is
LIFT_SHARE of the metal value of every unit that has ever lifted off a pad into the reserve. A
partial that lifts 3k off the pad grows it as much as a victory that lifts 3k; a sortie that
lifts nothing grows it not at all. Units left in the field stay where they were left; they are
not in the reserve.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from verdance.common import WORKSPACE_ROOT

LIFT_BASE = 0.0           # the first drop is the packs alone
LIFT_SHARE = 0.5          # the lift is half of all the value ever brought home off a pad
LIFT_PER_SORTIE = 1000.0  # the old rule (1k per victory/extraction): seeds a save from before the ledger
VETERAN_LIFT = 1000.0     # the commander's veteran_cadre perk: one more load's worth
SUCCESS = ("victory", "extracted")
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


def sorties_home(state: Dict[str, Any]) -> int:
    n = 0
    for b in state.get("history") or []:
        if not isinstance(b, dict):
            continue
        if str(b.get("verdict") or "").lower() in SUCCESS:
            n += 1
    return n


def brought_home(state: Dict[str, Any]) -> float:
    """Metal value of everything that has ever lifted off a pad into the reserve. A save from
    before the ledger starts where its old lift stood (1k per victory or extraction), so a
    campaign in progress never loses lift on the upgrade."""
    roster = state.get("roster") or {}
    v = roster.get("broughtHomeValue")
    if isinstance(v, (int, float)):
        return float(v)
    return LIFT_PER_SORTIE * sorties_home(state) / LIFT_SHARE


def lift_cap(state: Dict[str, Any]) -> float:
    perks = (((state.get("roster") or {}).get("commander") or {}).get("perks") or [])
    veteran = VETERAN_LIFT if "veteran_cadre" in perks else 0.0  # the commander's level-3 perk
    return LIFT_BASE + LIFT_SHARE * brought_home(state) + veteran


def bring_value(bring: Dict[str, int], workspace: Optional[Path] = None) -> float:
    return sum(unit_value(d, workspace) * n for d, n in bring.items())


def clamp_bring(requested: Any, reserve: Dict[str, int], cap: float, workspace: Optional[Path] = None) -> Dict[str, int]:
    """What actually boards: never more than the reserve holds, never past the lift limit
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


def homecoming(roster: Dict[str, Any], result: Dict[str, Any], history: Optional[list] = None,
               workspace: Optional[Path] = None) -> Dict[str, Any]:
    """After a sortie: the units brought left the reserve; what lifted off the pad (minus hero
    packs) comes back into it and its value joins the lift ledger. Brought units that died or
    stayed in the field are not in it. `history` is the campaign's, before this sortie's bead,
    to seed the ledger of a save from before it."""
    reserve = ensure_reserve(roster)
    if not isinstance(roster.get("broughtHomeValue"), (int, float)):
        roster["broughtHomeValue"] = brought_home({"roster": {}, "history": history or []})
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
    value = bring_value(lifted, workspace)
    roster["broughtHomeValue"] = round(float(roster["broughtHomeValue"]) + value, 1)
    roster["cadre"] = {}
    return {"brought": brought, "lifted": lifted, "reserve": dict(reserve), "liftedValue": round(value)}


def hub_surface(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """For the hub: the reserve with names and values, the lift limit and the suggestion."""
    roster = state.get("roster") or {}
    reserve = _counts(roster.get("reserve")) if isinstance(roster.get("reserve"), dict) else _counts(roster.get("cadre"))
    cap = lift_cap(state)
    rows = sorted(
        ({"unitDef": d, "name": unit_name(d, workspace), "count": n, "value": round(unit_value(d, workspace))}
         for d, n in reserve.items()),
        key=lambda r: -r["value"],
    )
    return {"units": rows, "liftCap": round(cap), "sortiesHome": sorties_home(state),
            "suggested": default_bring(reserve, cap, workspace),
            "broughtHome": round(brought_home(state)), "liftShare": LIFT_SHARE, "base": round(LIFT_BASE)}
