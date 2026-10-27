"""The Eye of Horus: the glassed crater and who hires the company there.

Years ago Armada glassed the crater to stop the raptors' terraforming spread; it worked, and cauterized
the ground. Long after, a Cortex mercenary operation set up in the empty crater. The war bake is that
history (Armada assaulting from the four corners, Cortex dug in around the crater; only the Cortex camp
and everyone's wrecks are kept). On the field now:

    Armada scouts   in each corner the company did not land in, an Armada party (no commander) and the
                    camp it has built over five minutes; Simple AI keeps building. Party and camps:
                    data/base_templates/eye_of_horus/scouts.json; corners: the war recipe's seats.
    the contract    whoever thinks better of the company offers the job (reputation):
                      Cortex  stop the scouts: every Armada scout constructor dead
                              (objective kind hunt_scouts; the Cortex camp is the company's ally)
                      Armada  wipe the mercenary camp (raze_camp: the crater's works are the target;
                              the scouts are the company's allies)
"""
from __future__ import annotations

import math
from pathlib import Path
import json
from typing import Any, Dict, List, Optional

MAP_ID = "eye_of_horus"

SCOUTS_REL = "data/base_templates/eye_of_horus/scouts.json"
CAMP_ZONE = "EOH_C_LANE"          # the heart of the mercenary camp
PAD_CLEARANCE = 0.25              # no scouts from the corner the company landed in


def _json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def scouts_config(workspace: Optional[Path]) -> Dict[str, Any]:
    return _json(Path(workspace) / SCOUTS_REL) if workspace is not None else {}


def corners(workspace: Optional[Path]) -> List[Dict[str, Any]]:
    """Armada's corners, read off the war recipe's 'corners' seats (the map's own start positions)."""
    if workspace is None:
        return []
    from verdance.world import war_snapshot as W
    rec = W.load_recipe(Path(workspace), MAP_ID)
    mx, mz = rec.get("mapSize") or (1, 1)
    return [{"key": t["key"], "zoneId": t["zoneId"], "x": round(t["startElmos"][0] / mx, 4), "z": round(t["startElmos"][1] / mz, 4)}
            for t in rec.get("teams") or [] if t.get("ally") == "corners"]


def patron(state: Dict[str, Any]) -> str:
    """Who offers the job: whichever of Cortex and Armada thinks better of the company (Cortex on a tie)."""
    rep = state.get("reputation") or {}
    return "armada" if float(rep.get("armada", 0) or 0) > float(rep.get("cortex", 0) or 0) else "cortex"


def scout_parties(pad_xz: Optional[tuple], workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """One party per corner the company did not land in: the data file's party, and its baked camp."""
    cfg = scouts_config(workspace)
    party = [dict(u) for u in cfg.get("party") or []]
    out = []
    for c in corners(workspace):
        if pad_xz and math.hypot(c["x"] - pad_xz[0], c["z"] - pad_xz[1]) < PAD_CLEARANCE:
            continue
        out.append({"zoneId": c["zoneId"], "corner": c["key"], "x": c["x"], "z": c["z"],
                    "arriveSeconds": int(cfg.get("arriveSeconds", 0)) + int(cfg.get("stagger", 0)) * len(out),
                    "units": party, "camp": list((cfg.get("camps") or {}).get(c["key"]) or [])})
    return out


def story(state: Dict[str, Any], pad_xz: Optional[tuple], workspace: Optional[Path] = None) -> Dict[str, Any]:
    who = patron(state)
    return {
        "patron": who,
        "kind": "hunt_scouts" if who == "cortex" else "raze_camp",
        "alliedWith": who,
        "scoutParties": scout_parties(pad_xz, workspace),
    }


def objective(story_: Dict[str, Any]) -> Dict[str, Any]:
    """The contract the Eye's patron offers, as the mission's objective."""
    if story_["patron"] == "cortex":
        first = (story_.get("scoutParties") or [{}])[0]
        return {"id": "EOH_STOP_THE_SCOUTS", "kind": "hunt_scouts", "patron": "cortex", "enemyFaction": "armada",
                "label": "Stop the Armada scouts: kill every one of their constructors",
                "targetZoneId": first.get("zoneId") or "EOH_NE_CAUSEWAY"}
    return {"id": "EOH_WIPE_THE_CAMP", "kind": "raze_camp", "patron": "armada", "enemyFaction": "cortex",
            "label": "Wipe out the mercenary camp in the crater", "targetZoneId": CAMP_ZONE}


BRIEFING = {
    "cortex": "Cortex pays well and asks little: Armada is sniffing at the crater again. They've had scouts "
              "dug into the corners for a few minutes already. Kill their builders. Every one.",
    "armada": "Armada remembers glassing this crater. They don't like what grew in it since. "
              "They want the mercenary camp gone, every last works.",
}


__all__ = ["BRIEFING", "CAMP_ZONE", "MAP_ID", "corners", "objective", "patron", "scout_parties", "scouts_config", "story"]
