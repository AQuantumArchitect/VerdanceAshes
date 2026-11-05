"""The Rock Jungle home camp: clearing it.

The camp is whatever the company has built in the Rock Jungle and left standing (its footprint on
that map, state["playerFootprints"]["the_rock_jungle"]). There is no camp level and nothing to buy
in the hub (owner call, 2026-11-03): Tenebrium to spend sends the company home to build.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

from verdance.common import save_json, utc_now
from .zones import load_zone_migration
from .commerce import ensure_commerce

HOME_MAP_ID = "the_rock_jungle"

# The pull home (owner call, 2026-11-04: "everything should be parametric and continuous. smooth
# curves. the more TnB in the rock jungle already the larger value we should stock up before we go
# back"). Tenebrium in the bag pulls the company home to build, along a logistic curve; the point
# where the pull crosses one half (the stock worth going home for) rises with what the camp is
# already worth. No step anywhere: a camp of nothing wants about two Tnb, a big camp wants more.
#   stake      camp worth in 1k metal-equivalent (metal + energy / 70 of everything standing there)
#   threshold  HOME_PULL_BASE + HOME_PULL_PER_STAKE * HOME_PULL_STAKE_SCALE * log1p(stake / SCALE)
#              (about linear for small camps, slowing for huge ones so it never runs away)
#   pull       1 / (1 + exp(-(tnb - threshold) / HOME_PULL_WIDTH))       in (0, 1)
HOME_PULL_BASE = 2.0          # Tnb worth going home with when there is no camp yet
HOME_PULL_PER_STAKE = 0.6     # Tnb more per 1k metal of camp, while the camp is small
HOME_PULL_STAKE_SCALE = 8.0   # 1k metal: where the rise starts to slow
HOME_PULL_WIDTH = 0.9         # Tnb: how soft the curve is around its threshold
HOME_READY_PULL = 0.5         # the clear job is offered from here (the curve's midpoint)
# A beating at home raises the bar too (hard-AI run, 2026-11-04: three Rock Jungle defeats in six
# sorties with 2 Tnb and no camp, the bag never moving): each Rock Jungle defeat adds
# HOME_SCAR_RISE Tnb to the stock a visit wants, fading by e every HOME_SCAR_FADE sorties since.
HOME_SCAR_RISE = 1.5          # Tnb
HOME_SCAR_FADE = 3.0          # sorties
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


def ensure_home_camp(state: Dict[str, Any]) -> Dict[str, Any]:
    camp = state.setdefault("homeCamp", {})
    if not isinstance(camp, dict):
        camp = {}
        state["homeCamp"] = camp
    camp.pop("level", None)
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


def camp_footprint(state: Dict[str, Any]) -> int:
    """How much the company has built and left standing in the Rock Jungle: the camp."""
    fp = (state.get("playerFootprints") or {}).get(HOME_MAP_ID) or {}
    units = fp.get("units") if isinstance(fp, dict) else fp
    return len(units) if isinstance(units, list) else 0


def camp_stake(state: Dict[str, Any], workspace: Path | None = None) -> float:
    """What the camp is worth: everything standing in the Rock Jungle, in 1k metal-equivalent."""
    from verdance.company.reserve import unit_value   # company imports campaign; keep this lazy
    fp = (state.get("playerFootprints") or {}).get(HOME_MAP_ID) or {}
    units = fp.get("units") if isinstance(fp, dict) else fp
    total = 0.0
    for u in units if isinstance(units, list) else []:
        d = str((u or {}).get("unitDefName") or (u or {}).get("def") or "") if isinstance(u, dict) else ""
        if d:
            total += unit_value(d, workspace) * max(0.05, min(1.0, float((u or {}).get("hpFrac") or 1.0)))
    return total / 1000.0


def home_scar(state: Dict[str, Any]) -> float:
    """Recent Rock Jungle defeats, each fading by e every HOME_SCAR_FADE sorties."""
    hist = [b for b in (state.get("history") or []) if isinstance(b, dict)]
    total = 0.0
    for age, b in enumerate(reversed(hist)):
        mid = str(b.get("mapId") or "").lower().replace(" ", "_")
        if mid in (HOME_MAP_ID, "rock_jungle") and str(b.get("verdict") or "").lower() == "defeat":
            total += math.exp(-age / HOME_SCAR_FADE)
    return total


def home_pull(state: Dict[str, Any], workspace: Path | None = None) -> Dict[str, Any]:
    """How hard the Tenebrium in the bag pulls the company home: a smooth curve, never a rule."""
    tnb = float((state.get("commerce") or {}).get("tenebrium") or 0)
    stake = camp_stake(state, workspace)
    threshold = HOME_PULL_BASE + HOME_PULL_PER_STAKE * HOME_PULL_STAKE_SCALE * math.log1p(stake / HOME_PULL_STAKE_SCALE)
    scar = home_scar(state)
    threshold += HOME_SCAR_RISE * scar
    pull = 1.0 / (1.0 + math.exp(-(tnb - threshold) / HOME_PULL_WIDTH))
    return {"pull": round(pull, 4), "tenebrium": int(tnb), "stake": round(stake, 3), "scar": round(scar, 4),
            "threshold": round(threshold, 3), "ready": pull >= HOME_READY_PULL}


# The camp grows while the company is away (owner call, 2026-11-04): whoever is not on the drop
# is at base, and constructors left there build. Each one left home while the company fights on
# another map adds CAMP_GROWTH_PER_BUILDER structures (eco first, then laser towers) to what the
# next Rock Jungle sortie finds standing; game_verdance_camp_growth.lua places them on ground a
# builder could use, near the home pad. Once placed they are the camp like anything built by hand.
CAMP_GROWTH_PER_BUILDER = 2
CAMP_GROWTH_PER_SORTIE_MAX = 8
CAMP_GROWTH_PENDING_MAX = 24
BUILDER_DEFS = frozenset(
    f + kind for f in ("arm", "cor", "leg") for kind in ("ck", "cv", "ca", "ch", "ack", "acv", "aca", "ach")
)


def builders_left_home(reserve: Dict[str, Any], brought: Dict[str, Any]) -> int:
    """Constructors in the reserve that did not board this drop."""
    n = 0
    for d, k in (reserve or {}).items():
        if str(d) in BUILDER_DEFS:
            n += max(0, int(k or 0) - int((brought or {}).get(d, 0) or 0))
    return n


def grow_camp_while_away(state: Dict[str, Any], reserve: Dict[str, Any], brought: Dict[str, Any],
                         map_id: str) -> int:
    """A sortie came home: builders left at base grew the camp, unless the sortie was at home
    (then the camp was in play, and what the field built is the camp). Returns the pending count."""
    camp = ensure_home_camp(state)
    mid = str(map_id or "").lower().replace(" ", "_")
    if mid in (HOME_MAP_ID, "rock_jungle"):
        camp["growthPending"] = 0          # the Rock Jungle sortie placed it; the footprint keeps it
        return 0
    add = min(CAMP_GROWTH_PER_SORTIE_MAX, CAMP_GROWTH_PER_BUILDER * builders_left_home(reserve, brought))
    camp["growthPending"] = min(CAMP_GROWTH_PENDING_MAX, int(camp.get("growthPending") or 0) + add)
    return camp["growthPending"]


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
    hp = home_pull(state)
    tnb = hp["tenebrium"]
    ready = hp["ready"]
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
    if home_win:
        flags["homeCleared"] = True
        flags["homeClearReady"] = False
    return {
        "homeClearReady": flags.get("homeClearReady"),
        "homeCleared": flags.get("homeCleared"),
        "keyHeld": key_held,
        "centerControl": center,
        "tenebrium": tnb,
        "homePull": hp["pull"],
        "homeThreshold": hp["threshold"],
        "campBuilt": camp_footprint(state),
    }


__all__ = [
    "HOME_PULL_BASE",
    "HOME_PULL_PER_STAKE",
    "HOME_PULL_STAKE_SCALE",
    "HOME_PULL_WIDTH",
    "HOME_READY_PULL",
    "HOME_SCAR_RISE",
    "HOME_SCAR_FADE",
    "home_scar",
    "camp_stake",
    "home_pull",
    "HOME_KEY_ZONES",
    "HOME_MAP_ID",
    "_zone_control",
    "camp_footprint",
    "builders_left_home",
    "grow_camp_while_away",
    "ensure_home_camp",
    "evaluate_home_clear",
]
