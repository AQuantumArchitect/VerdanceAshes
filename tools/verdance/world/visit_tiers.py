"""Visit tiers: a field ranks up each time the company fights on it.

The first sortie on a map meets it at tier 1, the second at tier 2, every one after at tier 3, and it
stays there. That gives each board depth and gives the company a reason to move on.

    standing wars (Koom Valley, Tabula, the Eye)   the war baked harder: war_snapshot_t2/_t3.json
                                                   (tools/war_bake_v1.py --tier N; recipe "tiers")
    living-shell fields (Greenest Fields)           Armada wardens (BARb va_warden) join the shell
                                                   and fortify the richest pockets as the drop runs;
                                                   a metal-poor field keeps them modest
    raptor ground (the Rock Jungle, the Eye's rim)  grace 10 minutes, then none, then the raptors
                                                   already half an hour into their clock
    the Ancient Bastion, All That Simmers           no tiers: the siege and the kings' showdown are
                                                   authored as they are
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from verdance.common import canonical_map_id

MAX_TIER = 3
NO_TIERS = {"ancient_bastion", "all_that_simmers"}
RAPTOR_MAPS = {"the_rock_jungle", "eye_of_horus"}

# Raptor pace by tier: grace before the first waves, and how far into the raptors' own clock the
# drop starts (game_verdance raptor_spawner_defense.lua: va_raptor_grace_seconds, va_raptor_clock_seconds).
RAPTOR_TIERS = {
    1: {"graceSeconds": 600, "clockSeconds": 0},
    2: {"graceSeconds": 1, "clockSeconds": 0},
    3: {"graceSeconds": 1, "clockSeconds": 1800},
}

# Living-shell fields: wardens by tier, on the shell's pockets in this order (the first that exist).
WARDEN_POCKETS = {
    "greenest_fields": ["gf_c_gate_fus", "gf_central_s", "gf_c_inner_fus"],
}
WARDENS_BY_TIER = {1: 0, 2: 1, 3: 2}
WARDEN_HANDICAP = {2: 0, 3: 10}


def visits(state: Dict[str, Any], map_id: str) -> int:
    """Sorties the company has already fought on this map (its history beads)."""
    mid = canonical_map_id(map_id)
    return sum(1 for b in state.get("history") or []
               if canonical_map_id(b.get("mapId") or b.get("deploymentMapId")) == mid)


def tier_for(state: Dict[str, Any], map_id: str) -> int:
    if canonical_map_id(map_id) in NO_TIERS:
        return 1
    return min(MAX_TIER, 1 + visits(state, map_id))


def plan(state: Dict[str, Any], map_id: str, pockets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """What this visit's tier asks of the mission builder (intent.visitTier)."""
    mid = canonical_map_id(map_id)
    tier = tier_for(state, mid)
    out: Dict[str, Any] = {"tier": tier, "visits": visits(state, mid), "tiered": mid not in NO_TIERS}
    if mid in RAPTOR_MAPS:
        out["raptor"] = dict(RAPTOR_TIERS[tier])
    wanted = WARDENS_BY_TIER.get(tier, 0)
    if wanted and mid in WARDEN_POCKETS:
        by_id = {str(p.get("pocketId")): p for p in pockets or []}
        wardens = []
        for pid in WARDEN_POCKETS[mid]:
            p = by_id.get(pid)
            if p and p.get("center"):
                wardens.append({"pocketId": pid, "zoneId": p.get("zoneId"), "x": float(p["center"][0]),
                                "z": float(p["center"][1]), "handicap": WARDEN_HANDICAP.get(tier, 0)})
            if len(wardens) >= wanted:
                break
        out["wardens"] = wardens
    out["label"] = {1: "", 2: "We've been here before. They've dug in since.",
                    3: "Third time on this ground. It won't get easier than this, and it won't get harder."}[tier]
    return out


__all__ = ["MAX_TIER", "NO_TIERS", "RAPTOR_MAPS", "RAPTOR_TIERS", "WARDEN_POCKETS", "plan", "tier_for", "visits"]
