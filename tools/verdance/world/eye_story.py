"""The Eye of Horus: the glassed crater and who hires the company there.

Years ago Armada glassed the crater to stop the raptors' terraforming spread; it worked, and cauterized
the ground. Long after, a Cortex mercenary operation set up in the empty crater. The war bake is that
history (Armada assaulting from the four corners, Cortex dug in around the crater; only the Cortex camp
and everyone's wrecks are kept). On the field now:

    Armada scouts   a few minutes in, small Armada parties walk in from the corners the company did not
                    land in: constructors and light escorts, no commander. Simple AI, left to build.
    the contract    whoever thinks better of the company offers the job (reputation):
                      Cortex  stop the scouts: every Armada constructor dead and nothing they built standing
                              (objective kind hunt_scouts; the Cortex camp is the company's ally)
                      Armada  wipe the mercenary camp (raze_camp: the crater's works are the target;
                              the scouts are the company's allies)
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

MAP_ID = "eye_of_horus"

# The map's own corner start positions (normalized), each with the zone it stands in.
CORNERS = [
    ("EOH_NW_MUSTER", 573 / 6144, 1075 / 7168),
    ("EOH_NE_CAUSEWAY", 5170 / 6144, 989 / 7168),
    ("EOH_SW_CAUSEWAY", 1003 / 6144, 6207 / 7168),
    ("EOH_SE_MUSTER", 5557 / 6144, 6078 / 7168),
]
CAMP_ZONE = "EOH_C_LANE"          # the heart of the mercenary camp
PAD_CLEARANCE = 0.25              # no scouts from the corner the company landed in
FIRST_ARRIVAL = 180               # seconds: the first party walks in three minutes in
STAGGER = 60                      # each later party a minute after
SCOUT_PARTY = [
    {"unitDefName": "armck", "count": 3},     # the job: constructors
    {"unitDefName": "armpw", "count": 2},     # escorts
    {"unitDefName": "armflea", "count": 1},   # the scout proper
]


def patron(state: Dict[str, Any]) -> str:
    """Who offers the job: whichever of Cortex and Armada thinks better of the company (Cortex on a tie)."""
    rep = state.get("reputation") or {}
    return "armada" if float(rep.get("armada", 0) or 0) > float(rep.get("cortex", 0) or 0) else "cortex"


def scout_parties(pad_xz: Optional[tuple]) -> List[Dict[str, Any]]:
    out = []
    for zid, x, z in CORNERS:
        if pad_xz and math.hypot(x - pad_xz[0], z - pad_xz[1]) < PAD_CLEARANCE:
            continue
        out.append({"zoneId": zid, "x": round(x, 4), "z": round(z, 4),
                    "arriveSeconds": FIRST_ARRIVAL + STAGGER * len(out), "units": [dict(u) for u in SCOUT_PARTY]})
    return out


def story(state: Dict[str, Any], pad_xz: Optional[tuple]) -> Dict[str, Any]:
    who = patron(state)
    return {
        "patron": who,
        "kind": "hunt_scouts" if who == "cortex" else "raze_camp",
        "alliedWith": who,
        "scoutParties": scout_parties(pad_xz),
    }


def objective(story_: Dict[str, Any]) -> Dict[str, Any]:
    """The contract the Eye's patron offers, as the mission's objective."""
    if story_["patron"] == "cortex":
        first = (story_.get("scoutParties") or [{}])[0]
        return {"id": "EOH_STOP_THE_SCOUTS", "kind": "hunt_scouts", "patron": "cortex", "enemyFaction": "armada",
                "label": "Stop the Armada scouts: no constructor walks out, nothing they build stands",
                "targetZoneId": first.get("zoneId") or "EOH_NE_CAUSEWAY"}
    return {"id": "EOH_WIPE_THE_CAMP", "kind": "raze_camp", "patron": "armada", "enemyFaction": "cortex",
            "label": "Wipe out the mercenary camp in the crater", "targetZoneId": CAMP_ZONE}


BRIEFING = {
    "cortex": "Cortex pays well and asks little: Armada is sniffing at the crater again. Their scouts walk in "
              "from the corners a few minutes after we land. Not one builder walks back out.",
    "armada": "Armada remembers glassing this crater. They don't like what grew in it since. "
              "They want the mercenary camp gone, every last works.",
}


__all__ = ["BRIEFING", "CAMP_ZONE", "CORNERS", "MAP_ID", "objective", "patron", "scout_parties", "story"]
