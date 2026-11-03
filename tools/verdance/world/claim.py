#!/usr/bin/env python3
"""Taking ground: who owns a zone.

The rule (owner call, 2026-10-29, replacing the 2026-10-24 claim presence):

  * Presence is AV + DV standing in a zone: the metal in every faction's armed units (army value)
    and armed structures (defensive value), the company's and everyone else's alike.
  * A side owns a zone when its presence there is more than CLAIM_NEED (1500) and more than
    DOMINANCE (3) times everyone else's presence there put together:
        1500 < (AV+DV)self > 3 * SUM(AV+DV)others
  * Nobody meeting that changes nothing: the zone stays as it was believed.
  * Allies don't contest (owner-proxy call, 2026-11-02): a faction allied with the company in the
    match (result.alliedFactions: the Null Mercs when they fight beside it) is left out of the
    company's "everyone else", and does not count for the company either (company_owns).
  * Every zone the company owns is an extraction point (game_verdance_exfil.lua), and what lifts
    from any of them goes into the one reserve, ready for any sortie.

The gadget reads the same numbers (mission.objective.claimValue, include/va_claim.lua), so a
zone-taking objective completes and a zone lifts only by this rule.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

CLAIM_NEED = 1500.0
DOMINANCE = 3.0


def claim_need(map_id: object = None, workspace: Optional[Path] = None) -> float:
    """Presence a side needs to own a zone: the same on every map (owner call, 2026-10-29)."""
    return CLAIM_NEED


def holder(presence: Dict[str, float], need: float = CLAIM_NEED,
           dominance: float = DOMINANCE) -> Tuple[Optional[str], float]:
    """Who owns a zone given its presence row (faction -> AV+DV), or (None, best) when nothing
    changes: nobody stands there, or nobody has more than ``need`` and more than ``dominance``
    times everyone else together."""
    vals = {str(f).lower(): float(v or 0) for f, v in (presence or {}).items()}
    if not vals:
        return None, 0.0
    leader, best = max(vals.items(), key=lambda kv: kv[1])
    others = sum(vals.values()) - best
    if best <= float(need) or best <= float(dominance) * others:
        return None, best
    return leader, best


COMPANY = "ashwalkers"


def without_allies(presence: Dict[str, float], allies: Iterable[str] = ()) -> Dict[str, float]:
    """The presence row with the company's allies left out (the company itself always stays)."""
    skip = {str(a).lower() for a in (allies or ())} - {COMPANY}
    return {f: v for f, v in (presence or {}).items() if str(f).lower() not in skip}


def company_owns(presence: Dict[str, float], need: float = CLAIM_NEED, allies: Iterable[str] = (),
                 dominance: float = DOMINANCE) -> bool:
    """Whether the company owns a zone: the rule above on the row without its allies."""
    return holder(without_allies(presence, allies), need, dominance)[0] == COMPANY


def zone_holder(presence: Dict[str, float], need: float = CLAIM_NEED, allies: Iterable[str] = (),
                dominance: float = DOMINANCE) -> Optional[str]:
    """Who holds a zone after a sortie: the company when it owns it (company_owns, allies left
    out), otherwise whoever the plain rule names (or None: nothing changes)."""
    if company_owns(presence, need, allies, dominance):
        return COMPANY
    return holder(presence, need, dominance)[0]
