"""Heroes for hire: the Cortex mercenary store rents a hero for one drop.

Owner call (2026-10-27): Marrow Gale's Cutlass wing and Bro's Tzar are sold in the mercenary store,
in the drop window. A rental is expensive and lasts one drop: the hero joins the company for that
drop (company.rented, plus a roster row marked rented) and leaves at homecoming. You keep a hero
the way you keep any other: win the campaign with them in the company. So a hero rented for the
drop that wins the campaign, who comes home alive, is a starting option from then on
(state/profile.json, verdance.company.company.unlock_rescued_survivors).

    rent(state, listing)       the hero is in the company for the next drop
    rented(state)              who is rented now
    settle(state, result)      after the drop: rentals leave; who came home alive is remembered as
                               company.rentedLastDrop (the campaign-end unlock reads it)
"""
from __future__ import annotations

from typing import Any, Dict, List

from verdance.common import utc_now


def rented(state: Dict[str, Any]) -> List[str]:
    return [str(h) for h in ((state.get("company") or {}).get("rented") or []) if h]


def _owned_for_good(state: Dict[str, Any], hid: str) -> bool:
    company = state.get("company") or {}
    if hid in [str(x) for x in (company.get("band") or [])] + [str(x) for x in (company.get("joinedLater") or [])]:
        return True
    for h in ((state.get("roster") or {}).get("heroes") or []):
        if isinstance(h, dict) and str(h.get("heroId")) == hid and not h.get("rented") \
                and str(h.get("status") or "active") not in ("locked",):
            return True
    return False


def can_rent(state: Dict[str, Any], hid: str) -> tuple:
    if not hid:
        return False, "no hero on this listing"
    if not (state.get("company") or {}).get("sealed"):
        return False, "form the company first"
    if hid in rented(state):
        return False, "already rented for this drop"
    if _owned_for_good(state, hid):
        return False, "already in the company"
    return True, "ok"


def rent(state: Dict[str, Any], listing: Dict[str, Any], workspace=None) -> Dict[str, Any]:
    """Put the listing's hero in the company for the next drop (pack from data/story/crew_packs.json)."""
    from verdance.company.company import load_crew_packs
    hid = str(listing.get("heroId") or "")
    pack = (load_crew_packs(workspace).get("heroes") or {}).get(hid) or {}
    company = state.setdefault("company", {})
    company.setdefault("rented", [])
    if hid not in company["rented"]:
        company["rented"].append(hid)
    heroes = state.setdefault("roster", {}).setdefault("heroes", [])
    row = next((h for h in heroes if isinstance(h, dict) and str(h.get("heroId")) == hid), None)
    rec = {
        "heroId": hid,
        "name": str(pack.get("name") or listing.get("label") or hid),
        "unitDef": str(pack.get("unitDef") or listing.get("unitDef") or ""),
        "missionCritical": False,
        "status": "active",
        "rented": True,
        "xp": float(pack.get("startXp") or 0.15),
        "campaignXp": 0.0,
        "peakBarXp": float(pack.get("startXp") or 0.15),
        "timesWounded": 0,
        "rentedAtMission": int(state.get("missionNumber", 1) or 1),
    }
    if row is None:
        heroes.append(rec)
    else:
        row.update(rec)
    return rec


def settle(state: Dict[str, Any], result: Dict[str, Any]) -> List[str]:
    """After the drop the rentals go back to Cortex. Returns who came home alive with the company."""
    company = state.setdefault("company", {})
    ids = rented(state)
    if not ids:
        company["rentedLastDrop"] = []
        return []
    heroes = (state.get("roster") or {}).get("heroes") or []
    home: List[str] = []
    for h in list(heroes):
        if isinstance(h, dict) and h.get("rented") and str(h.get("heroId")) in ids:
            if str(h.get("status") or "active") in ("active", "wounded"):
                home.append(str(h["heroId"]))
            heroes.remove(h)
    company["rented"] = []
    company["rentedLastDrop"] = home
    company.setdefault("rentalLedger", []).append({"heroes": ids, "home": home, "at": utc_now(),
                                                   "missionNumber": int(state.get("missionNumber", 1) or 1)})
    return home


__all__ = ["can_rent", "rent", "rented", "settle"]
