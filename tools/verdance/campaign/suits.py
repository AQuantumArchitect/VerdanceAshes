"""Commander suits: what it takes to duel in All That Simmers.

All That Simmers is the kings' showdown, and a king is a commander. The company has no suit at the
start (roster.commander is scrap); there are three ways to get one (owner call, 2026-10-26):

    bought_cortex   Cortex sells one off its shelf for an outrageous Tenebrium fee
                    (data/commerce/commerce_catalog.json, cortex_commander_suit). Easter egg: wear
                    Cortex's own suit to the showdown and Cortex does not come to the fight.
    stolen_koom     on Koom Valley, a fallen war commander's wreck raised (or a commander captured)
                    onto the company is its suit (game_verdance_suits.lua)
    queen_rez       a Legion suit lies under the hive queen's corpse wherever she falls; raise it

Without one, the roads do not run onto All That Simmers (verdance.world.roads) and the Sovereignty
finale gives way to the next path. Losing the walker in the field scraps the suit again.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

SIMMERS = "all_that_simmers"
WALL = "You can't duel in All That Simmers without a commander suit."
WALL_HOW = ("Buy one from Cortex, steal one off Koom Valley's war, or raise the Legion suit that lies "
            "under the hive queen's corpse.")

SUITS = {
    "corcom": {"faction": "cortex", "side": "Cortex", "label": "a Cortex commander suit"},
    "armcom": {"faction": "armada", "side": "Armada", "label": "an Armada commander suit"},
    "legcom": {"faction": "legion", "side": "Legion", "label": "a Legion commander suit"},
}
HOW = {
    "bought_cortex": "bought from Cortex",
    "stolen_koom": "stolen off Koom Valley",
    "queen_rez": "raised from under the hive queen",
}


def base_def(unit_def: Any) -> str:
    """armcom / corcom / legcom for any of their levels (armcomlvl3 -> armcom)."""
    d = str(unit_def or "").lower()
    for k in SUITS:
        if d.startswith(k):
            return k
    return ""


def _commander(state: Dict[str, Any]) -> Dict[str, Any]:
    from .roster import ensure_roster
    return ensure_roster(state)["commander"]


def has_suit(state: Dict[str, Any]) -> bool:
    from .roster import commander_is_unlocked
    return commander_is_unlocked(state)


def suit(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The suit the company wears, or None."""
    if not has_suit(state):
        return None
    c = _commander(state)
    d = base_def(c.get("unitDef")) or "legcom"
    return dict(SUITS[d], unitDef=d, how=c.get("suitFrom") or "story")


def grant_suit(state: Dict[str, Any], unit_def: Any, how: str) -> bool:
    """The company has a suit now. A second suit is not taken while one is worn."""
    from .roster import grant_commander
    d = base_def(unit_def)
    if not d or has_suit(state):
        return False
    c = _commander(state)
    c["unitDef"] = d
    c["suitFrom"] = str(how or "story")[:40]
    return grant_commander(state, "suit:" + c["suitFrom"])


def cortex_sits_out(state: Dict[str, Any]) -> bool:
    """The easter egg: wearing Cortex's own suit, Cortex does not come to the showdown."""
    s = suit(state)
    return bool(s and s["unitDef"] == "corcom")


def line(state: Dict[str, Any]) -> Optional[str]:
    s = suit(state)
    if not s:
        return None
    return f"The company wears {s['label']}, {HOW.get(s['how'], 'from the story')}."


__all__ = ["HOW", "SIMMERS", "SUITS", "WALL", "WALL_HOW", "base_def", "cortex_sits_out", "grant_suit",
           "has_suit", "line", "suit"]
