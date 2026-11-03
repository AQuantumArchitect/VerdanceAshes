#!/usr/bin/env python3
"""Taking ground: who owns a zone.

The rule (owner call, 2026-10-29, replacing the 2026-10-24 claim presence):

  * Presence is AV + DV standing in a zone: the metal in every faction's armed units (army value)
    and armed structures (defensive value), the company's and everyone else's alike.
  * A side owns a zone when its presence there is more than CLAIM_NEED (1500) and more than
    DOMINANCE (3) times everyone else's presence there put together:
        1500 < (AV+DV)self > 3 * SUM(AV+DV)others
  * Nobody meeting that changes nothing: the zone stays as it was believed.
  * Allies don't contest each other (owner call, 2026-11-02): a faction allied with the company in
    the match (result.alliedFactions: the Null Mercs when they fight beside it) competes against
    Armada and everyone else, but not against the company, and the company not against it. Neither
    lends presence to the other.
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
COMPANY = "ashwalkers"


def claim_need(map_id: object = None, workspace: Optional[Path] = None) -> float:
    """Presence a side needs to own a zone: the same on every map (owner call, 2026-10-29)."""
    return CLAIM_NEED


def holder(presence: Dict[str, float], need: float = CLAIM_NEED,
           dominance: float = DOMINANCE, allies: Iterable[str] = ()) -> Tuple[Optional[str], float]:
    """Who owns a zone given its presence row (faction -> AV+DV), or (None, best) when nothing
    changes: nobody stands there, or nobody has more than ``need`` and more than ``dominance``
    times the presence of everyone it is fighting there.

    ``allies`` are the company's allies in the match. The company and its allies do not contest
    each other (owner call, 2026-11-02): the Null Mercs compete against Armada but not against the
    player, and the player not against them. Neither lends presence to the other. When the company
    and an ally both qualify, the company holds it."""
    vals = {str(f).lower(): float(v or 0) for f, v in (presence or {}).items()}
    if not vals:
        return None, 0.0
    bloc = {COMPANY} | {str(a).lower() for a in (allies or ())}

    def hostile(f: str) -> float:
        return sum(v for g, v in vals.items() if g != f and not (f in bloc and g in bloc))

    qualified = [f for f, v in vals.items() if v > float(need) and v > float(dominance) * hostile(f)]
    best = max(vals.values())
    if not qualified:
        return None, best
    leader = COMPANY if COMPANY in qualified else max(qualified, key=lambda f: (vals[f], f))
    return leader, vals[leader]


def without_allies(presence: Dict[str, float], allies: Iterable[str] = ()) -> Dict[str, float]:
    """The presence row with the company's allies left out (the company itself always stays)."""
    skip = {str(a).lower() for a in (allies or ())} - {COMPANY}
    return {f: v for f, v in (presence or {}).items() if str(f).lower() not in skip}


def company_owns(presence: Dict[str, float], need: float = CLAIM_NEED, allies: Iterable[str] = (),
                 dominance: float = DOMINANCE) -> bool:
    """Whether the company owns a zone: more than ``need`` of its own, and more than ``dominance``
    times its enemies' there (its allies count neither way)."""
    return holder(presence, need, dominance, allies)[0] == COMPANY


def zone_holder(presence: Dict[str, float], need: float = CLAIM_NEED, allies: Iterable[str] = (),
                dominance: float = DOMINANCE) -> Optional[str]:
    """Who holds a zone after a sortie (or None: nothing changes). The company and its allies do
    not contest each other; each still has to outweigh the enemies there three to one."""
    return holder(presence, need, dominance, allies)[0]
