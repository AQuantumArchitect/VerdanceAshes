"""Commander suits: what it takes to duel in All That Simmers.

All That Simmers is the kings' showdown, and a king is a commander. The company has no suit at the
start (roster.commander is scrap); there are three ways to get one (owner call, 2026-10-26):

    loaned_cortex   Cortex loans one off its shelf for ONE fight, for an outrageous Tenebrium fee
                    (data/commerce/commerce_catalog.json, cortex_commander_suit). It goes back to
                    Cortex at homecoming, like a hired hero (owner call, 2026-10-27; it used to be
                    bought for good). Easter egg: wear Cortex's own suit to the showdown and Cortex
                    does not come to the fight.
    stolen_koom     on Koom Valley, a fallen war commander's wreck raised (or a commander captured)
                    onto the company is its suit (game_verdance_suits.lua)
    queen_rez       a Legion suit lies under the hive queen's corpse wherever she falls; raise it
    raised          any commander the company raises from its wreck and brings home (owner, 2026-10-29)

Without one, the roads do not run onto All That Simmers (verdance.world.roads) and the Sovereignty
finale gives way to the next path. Losing the walker in the field scraps the suit again.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

SIMMERS = "all_that_simmers"
WALL = "You can't duel in All That Simmers without a commander suit."
WALL_HOW = ("Borrow one from Cortex for a fight, steal one off Koom Valley's war, or raise the Legion "
            "suit that lies under the hive queen's corpse.")
LOAN = "loaned_cortex"

SUITS = {
    "corcom": {"faction": "cortex", "side": "Cortex", "label": "a Cortex commander suit"},
    "armcom": {"faction": "armada", "side": "Armada", "label": "an Armada commander suit"},
    "legcom": {"faction": "legion", "side": "Legion", "label": "a Legion commander suit"},
}
HOW = {
    "loaned_cortex": "on loan from Cortex for this fight",
    "bought_cortex": "bought from Cortex",
    "stolen_koom": "stolen off Koom Valley",
    "queen_rez": "raised from under the hive queen",
    "raised": "raised from its wreck in the field",
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


def came_home(result: Dict[str, Any], unit_def: Any) -> bool:
    """A suit won in the field is the company's only if it lifted off with the company: the exfil
    manifest's going units name its body. A result without a manifest (an old or headless one)
    is taken at its word."""
    d = base_def(unit_def)
    manifest = result.get("manifest") if isinstance(result, dict) else None
    if not d or not isinstance(manifest, dict):
        return bool(d)
    going = (manifest.get("going") or {}).get("units") or {}
    if not isinstance(going, dict):
        return True
    return any(base_def(k) == d and int(n or 0) > 0 for k, n in going.items())


def on_loan(state: Dict[str, Any]) -> bool:
    """The suit the company wears is Cortex's, for one fight."""
    s = suit(state)
    return bool(s and s["how"] == LOAN)


def return_loan(state: Dict[str, Any]) -> bool:
    """After the drop a loaned suit goes back to Cortex, whatever happened in the fight. The fee is
    not refunded. A suit lost in the field is already scrap; the loan is just cleared."""
    from .roster import scrap_commander
    c = _commander(state)
    if c.get("suitFrom") != LOAN:
        return False
    c.pop("suitFrom", None)
    if c.get("unlocked") is True:
        scrap_commander(state, "suit_returned_to_cortex")
        c["unitDef"] = "corcom"
    return True


def cortex_sits_out(state: Dict[str, Any]) -> bool:
    """The easter egg: wearing Cortex's own suit, Cortex does not come to the showdown."""
    s = suit(state)
    return bool(s and s["unitDef"] == "corcom")


def line(state: Dict[str, Any]) -> Optional[str]:
    s = suit(state)
    if not s:
        return None
    return f"The company wears {s['label']}, {HOW.get(s['how'], 'from the story')}."


__all__ = ["HOW", "LOAN", "SIMMERS", "SUITS", "WALL", "WALL_HOW", "base_def", "cortex_sits_out", "grant_suit",
           "has_suit", "line", "on_loan", "return_loan", "suit"]
