"""What a bond is worth on the field.

Pairs that drop together and have built a bond (attachments.pairBonds, ranks C/B/A) get:

    rank B   both heroes start the sortie with a little more XP
    rank A   more XP, and the pair brings one gift: a unit neither hero's pack already has

The gift is the pair's own recommendation when one is new to both packs, otherwise a draw from
the pool weighted toward the axes the two care most about (their field profiles), seeded by the
campaign, the pair and the mission so a sortie always rolls the same. Data: bond_gifts.json.

Python decides; the campaign gadget only spawns the gifts and adds the XP, and only when both
heroes are actually on the field (VA_BOND_apply in game_verdance_campaign.lua).
"""
from __future__ import annotations

import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from verdance.common import WORKSPACE_ROOT


def _load(workspace: Optional[Path], name: str) -> dict:
    for root in ([Path(workspace)] if workspace else []) + [WORKSPACE_ROOT]:
        p = root / "data" / "story" / name
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8-sig"))
    return {}


def pair_id(a: str, b: str) -> str:
    x, y = sorted([str(a), str(b)])
    return f"{x}__{y}"


def pack_units(pack: Dict[str, Any], factories: Optional[dict] = None) -> set:
    """Every unit type a hero's pack already brings: the chassis, its support units, its factory."""
    out = {str(pack.get("unitDef") or "")}
    out |= {str(e.get("unitDef")) for e in pack.get("escorts") or [] if isinstance(e, dict)}
    fab = (factories or {}).get(str(pack.get("factory") or "")) or {}
    out |= {str(fab.get("structureDef") or ""), str(fab.get("product") or "")}
    return {u for u in out if u and u != "None"}


def _rank(points: float) -> Optional[str]:
    return "A" if points >= 55 else "B" if points >= 25 else "C" if points > 0 else None


def _seed(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def choose_gift(a: str, b: str, *, gifts: dict, packs: dict, umwelt: dict, seed: Any,
                factories: Optional[dict] = None) -> Optional[Dict[str, Any]]:
    """The rank-A gift for this pair, or None when nothing new is left to give."""
    taken = pack_units(packs.get(a) or {}, factories) | pack_units(packs.get(b) or {}, factories)
    pid = pair_id(a, b)
    for rec in (gifts.get("recommended") or {}).get(pid) or []:
        if rec.get("unitDef") not in taken:
            return {"unitDef": rec["unitDef"], "count": int(rec.get("count") or 1), "why": rec.get("why") or "", "source": "recommended"}
    ax_a = (umwelt.get(a) or {}).get("axes") or {}
    ax_b = (umwelt.get(b) or {}).get("axes") or {}
    care = {k: max(abs(float(ax_a.get(k) or 0)), abs(float(ax_b.get(k) or 0))) for k in set(ax_a) | set(ax_b)}
    pool = [p for p in gifts.get("pool") or [] if p.get("unitDef") not in taken]
    if not pool:
        return None
    ranked = sorted(pool, key=lambda p: (-sum(care.get(x, 0.0) for x in p.get("axes") or []), p["unitDef"]))
    top = ranked[: max(1, int(gifts.get("poolDraw") or 5))]
    pick = top[_seed(seed, pid) % len(top)]
    axes = sorted(p for p in pick.get("axes") or [] if care.get(p, 0) > 0)
    return {"unitDef": pick["unitDef"], "count": int(pick.get("count") or 1),
            "why": f"drawn for what they share: {', '.join(axes) or 'the company'}", "source": "pool"}


def bond_perks(state: Dict[str, Any], hero_ids: Iterable[str], workspace: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """{"bondXp": [{a, b, rank, xp}], "bondGifts": [{a, b, unitDef, count, why}]} for every pair of
    these heroes with a rank-B or rank-A bond. The gadget applies a row only if both drop."""
    ids = sorted({str(h) for h in hero_ids if h})
    pairs = ((state.get("attachments") or {}).get("pairBonds") or {})
    gifts = _load(workspace, "bond_gifts.json")
    crew = _load(workspace, "crew_packs.json")
    packs, factories = crew.get("heroes") or {}, crew.get("factories") or {}
    umwelt = {h["heroId"]: h for h in _load(workspace, "hero_umwelt.json").get("heroes") or []}
    names = _load(workspace, "unit_costs.json").get("names") or {}
    bonus = gifts.get("bonusXp") or {"B": 0.05, "A": 0.1}
    seed = (state.get("campaignId") or "verdance_ashes", state.get("seed") or 0, int(state.get("missionNumber") or 1))
    xp_rows, gift_rows = [], []
    for a, b in combinations(ids, 2):
        row = pairs.get(pair_id(a, b))
        if not isinstance(row, dict):
            continue
        rank = _rank(float(row.get("points") or 0))
        if rank not in ("A", "B"):
            continue
        xp_rows.append({"a": a, "b": b, "rank": rank, "xp": float(bonus.get(rank) or 0)})
        if rank == "A":
            gift = choose_gift(a, b, gifts=gifts, packs=packs, umwelt=umwelt, seed=seed, factories=factories)
            if gift:
                gift_rows.append({"a": a, "b": b, "name": names.get(gift["unitDef"], gift["unitDef"]), **gift})
    return {"bondXp": xp_rows, "bondGifts": gift_rows}


__all__ = ["bond_perks", "choose_gift", "pack_units", "pair_id"]
