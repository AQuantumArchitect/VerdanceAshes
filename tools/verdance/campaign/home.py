"""The Rock Jungle home camp: clearing it, building in it.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from verdance.common import save_json, utc_now
from .zones import load_zone_migration
from .commerce import ensure_commerce

HOME_MAP_ID = "the_rock_jungle"
HOME_CLEAR_TNB_MIN = 3
HOME_CLEAR_CAMP_MIN = 1
HOME_KEY_ZONES = (
    "TRJ_C_SPILLWAY",
    "TRJ_C_INNER_SPILLWAY",
    "TRJ_NW_GATE",
    "TRJ_SE_GATE",
    # legacy aliases (pre-TRJ remap) — kept so old states still evaluate
    "RJ_CENTRAL_LAGOON_MAZE",
    "RJ_NW_JUNGLE_SHELF",
    "RJ_SE_JUNGLE_SHELF",
)
HOME_BUILD_TNB_COST = 1
HOME_BUILD_METAL_K_COST = 1


def ensure_home_camp(state: Dict[str, Any]) -> Dict[str, Any]:
    camp = state.setdefault("homeCamp", {})
    if not isinstance(camp, dict):
        camp = {}
        state["homeCamp"] = camp
    camp.setdefault("level", 0)
    camp.setdefault("mapId", HOME_MAP_ID)
    camp.setdefault("label", "Jungle shelf camp")
    flags = state.setdefault("flags", {})
    if not isinstance(flags, dict):
        flags = {}
        state["flags"] = flags
    flags.setdefault("homeClearReady", False)
    flags.setdefault("homeCleared", False)
    state.setdefault("sessionHomeMap", HOME_MAP_ID)
    state.setdefault("sessionMode", "same_map")
    return camp


def _zone_control(state: Dict[str, Any], map_id: str, zone_id: str) -> str:
    zm = (state.get("zoneMemory") or {}).get(map_id) or {}
    z = zm.get(zone_id) or zm.get(load_zone_migration().get(zone_id, "")) or {}
    return str(
        z.get("controllingFaction")
        or (z.get("abstract") or {}).get("control")
        or "unknown"
    ).lower()


def evaluate_home_clear(state: Dict[str, Any], result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Update homeClearReady / homeCleared from camp, Tnb, and Rock Jungle control."""
    ensure_home_camp(state)
    flags = state["flags"]
    camp = state["homeCamp"]
    commerce = state.get("commerce") or {}
    tnb = int(commerce.get("tenebrium") or 0)
    level = int(camp.get("level") or 0)
    ready = tnb >= HOME_CLEAR_TNB_MIN or level >= HOME_CLEAR_CAMP_MIN
    flags["homeClearReady"] = bool(ready) and not bool(flags.get("homeCleared"))

    playerish = {"ashwalkers", "nullmercs", "legion"}
    key_held = sum(1 for zid in HOME_KEY_ZONES if _zone_control(state, HOME_MAP_ID, zid) in playerish)
    center = _zone_control(state, HOME_MAP_ID, "TRJ_C_SPILLWAY")
    if not center or center == "unknown":
        center = _zone_control(state, HOME_MAP_ID, "RJ_CENTRAL_LAGOON_MAZE")
    map_id = str((result or {}).get("mapId") or "").lower().replace(" ", "_")
    verdict = str((result or {}).get("verdict") or (result or {}).get("status") or "")
    home_win = (
        map_id in (HOME_MAP_ID, "rock_jungle")
        and verdict in ("victory", "victoryClean")
        and (center in playerish or key_held >= 2)
        and ready
    )
    if home_win or (center in playerish and key_held >= 2 and ready and level >= 2):
        flags["homeCleared"] = True
        flags["homeClearReady"] = False
    return {
        "homeClearReady": flags.get("homeClearReady"),
        "homeCleared": flags.get("homeCleared"),
        "keyHeld": key_held,
        "centerControl": center,
        "tenebrium": tnb,
        "campLevel": level,
    }


def apply_home_build(state: Dict[str, Any], workspace: Path | None = None) -> Dict[str, Any]:
    """Spend Tnb + 1km$ metal to raise the Rock Jungle camp (hub-only)."""
    ensure_home_camp(state)
    commerce = ensure_commerce(state, workspace)
    tnb = int(commerce.get("tenebrium") or 0)
    metal_k = int(commerce.get("metalK") or 0)
    if tnb < HOME_BUILD_TNB_COST:
        return {
            "ok": False,
            "error": f"need {HOME_BUILD_TNB_COST} Tenebrium (have {tnb}) — raid to print, then build home",
        }
    if metal_k < HOME_BUILD_METAL_K_COST:
        return {
            "ok": False,
            "error": f"need {HOME_BUILD_METAL_K_COST}×1km$ metal (have {metal_k})",
        }
    commerce["tenebrium"] = tnb - HOME_BUILD_TNB_COST
    commerce["metalK"] = metal_k - HOME_BUILD_METAL_K_COST
    camp = state["homeCamp"]
    camp["level"] = int(camp.get("level") or 0) + 1
    camp["lastBuiltAt"] = utc_now()
    # Light kit hook: mark an owned "camp_bp" stub for deploy kit flavor.
    owned = commerce.setdefault("owned", {})
    prev = owned.get("home_camp_bp") or {}
    owned["home_camp_bp"] = {
        "kind": "home_camp",
        "label": f"Jungle camp L{camp['level']}",
        "qty": int(prev.get("qty") or 0) + 1,
        "builds": True,
        "mapId": HOME_MAP_ID,
    }
    evaluate_home_clear(state)
    if workspace is not None:
        try:
            save_json(Path(workspace) / "state" / "campaign_state.json", state)
        except Exception:
            pass
    return {
        "ok": True,
        "homeCamp": camp,
        "tenebrium": commerce["tenebrium"],
        "metalK": commerce["metalK"],
        "flags": dict(state.get("flags") or {}),
    }


__all__ = [
    "HOME_BUILD_METAL_K_COST",
    "HOME_BUILD_TNB_COST",
    "HOME_CLEAR_CAMP_MIN",
    "HOME_CLEAR_TNB_MIN",
    "HOME_KEY_ZONES",
    "HOME_MAP_ID",
    "_zone_control",
    "apply_home_build",
    "ensure_home_camp",
    "evaluate_home_clear",
]
