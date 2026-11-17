"""The players: one per hero (owner call, 2026-11-16: "the multiplayer should hook in something like
1 player per hero... shared company co-op").

Every person playing is one of the company's heroes. The first player is ``company.you``, the hero
the player picked as themselves at the seal. Each further player takes another hero of the company.
They all command the same company: one team in the engine, every unit shared (Recoil gives every
player on a team control of all of it). A player's hero is what is theirs: it is mission-critical for
them as "you" is, and the HUD marks it as theirs.

Single player is one player, and a save without ``company.players`` is that. The list lives on the
state (``company.players``, hero ids in player order); the mission carries it (``mission.players``,
only when there is more than one, so a one-player mission keeps its shape), and the start script
seats one engine player per entry, all on the company's team (scripts/install_playable_slice.ps1).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# The engine player names, by player index. The first is the name every single-player start script
# has always used; a joining player's start script must give the same name (MyPlayerName).
FIRST_PLAYER = "VerdanceCommander"
GONE = ("dead", "lost")


def player_name(index: int) -> str:
    return FIRST_PLAYER if int(index) == 0 else f"VerdancePlayer{int(index) + 1}"


def _company(state: Dict[str, Any]) -> Dict[str, Any]:
    c = state.get("company")
    return c if isinstance(c, dict) else {}


def _status(state: Dict[str, Any], hid: str) -> str:
    for h in ((state.get("roster") or {}).get("heroes") or []):
        if isinstance(h, dict) and str(h.get("heroId") or h.get("id") or "") == hid:
            return str(h.get("status") or "active")
    return str(((state.get("characters") or {}).get(hid) or {}).get("status") or "active")


def company_heroes(state: Dict[str, Any]) -> List[str]:
    """Every hero the company has now: the core, the band picked at the seal, and those who joined later."""
    c = _company(state)
    out: List[str] = []
    for key in ("core", "band", "joinedLater"):
        for hid in c.get(key) or []:
            if str(hid) not in out:
                out.append(str(hid))
    return out


def players(state: Dict[str, Any]) -> List[str]:
    """The heroes the players are, in player order; the first is always ``you``. A hero who is dead or
    lost leaves the list (that player goes on without a hero of their own until given another)."""
    c = _company(state)
    you = str(c.get("you") or "")
    if not you:
        return []
    out = [you]
    for hid in c.get("players") or []:
        hid = str(hid)
        if hid and hid not in out and hid in company_heroes(state) and _status(state, hid) not in GONE:
            out.append(hid)
    return out


def set_players(state: Dict[str, Any], others: List[str], *, workspace: Optional[Path] = None) -> Tuple[bool, str, List[str]]:
    """Give the players after the first their heroes. ``others`` are hero ids, one per further player,
    in order; [] is single player. Each must be one of the company's heroes, alive, able to lead (a
    player walks, as "you" does), and nobody else's."""
    from verdance.company.company import hero_can_lead, load_crew_packs
    c = _company(state)
    you = str(c.get("you") or "")
    if not c.get("sealed") or not you:
        return False, "seal the company first: the first player is the hero you pick as yourself", players(state)
    packs = load_crew_packs(workspace)
    mine = company_heroes(state)
    out = [you]
    for raw in others or []:
        hid = str(raw or "").strip()
        if not hid:
            continue
        if hid in out:
            return False, f"{hid} is already a player's hero", players(state)
        if hid not in mine:
            return False, f"{hid} is not in the company", players(state)
        if _status(state, hid) in GONE:
            return False, f"{hid} is {_status(state, hid)}", players(state)
        if not hero_can_lead(hid, packs):
            return False, f"{hid} cannot lead (a building cannot walk)", players(state)
        out.append(hid)
    c["players"] = out[1:]
    state["company"] = c
    return True, "", out


def mission_players(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """For the mission: [{player, heroId, name}], with ``name`` the engine player's name."""
    return [{"player": i, "heroId": hid, "name": player_name(i)} for i, hid in enumerate(players(state))]
