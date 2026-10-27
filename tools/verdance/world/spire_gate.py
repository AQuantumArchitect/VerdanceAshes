"""The Rock Jungle's Spire Gate (finale C, the Spire Jump).

The gate's tuning lives in data/base_templates/the_rock_jungle/spire_gate.json; this places it on its
zone's anchor (map fractions) for the mission seed's jumpGate, which game_verdance_jump_gate.lua reads.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

MAP_ID = "the_rock_jungle"
CONFIG_REL = "data/base_templates/the_rock_jungle/spire_gate.json"
KEYS = ("startBuilt", "needAfus", "radius", "chargeSeconds", "padRadius", "channelSeconds",
        "rageOnline", "angerOnline", "ragePerHero", "angerPerHero")


def config(workspace: Optional[Path]) -> Dict[str, Any]:
    if workspace is None:
        return {}
    try:
        return json.loads((Path(workspace) / CONFIG_REL).read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def jump_gate(workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """The seed's jumpGate: where the gate stands and how it charges; None without data."""
    from verdance.world import theaters
    cfg = config(workspace)
    zone_id = cfg.get("zoneId")
    z = theaters._zones(MAP_ID, workspace).get(str(zone_id)) if zone_id else None
    p = theaters._point(z) if z else None
    if not p:
        return None
    out: Dict[str, Any] = {"zoneId": zone_id, "x": round(p[0], 4), "z": round(p[1], 4)}
    out.update({k: cfg[k] for k in KEYS if k in cfg})
    return out


__all__ = ["CONFIG_REL", "MAP_ID", "config", "jump_gate"]
