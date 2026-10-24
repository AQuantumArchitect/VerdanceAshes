#!/usr/bin/env python3
"""Bonds worth something on the field: rank-B XP, rank-A gifts that are new to both packs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.company import synergy  # noqa: E402

PACKS = json.loads((ROOT / "data" / "story" / "crew_packs.json").read_text(encoding="utf-8"))
COSTS = json.loads((ROOT / "data" / "story" / "unit_costs.json").read_text(encoding="utf-8-sig"))["units"]
GIFTS = json.loads((ROOT / "data" / "story" / "bond_gifts.json").read_text(encoding="utf-8"))


def _state(points):
    return {"campaignId": "t", "missionNumber": 3, "attachments": {"pairBonds": {
        synergy.pair_id(a, b): {"points": p} for (a, b), p in points.items()}}}


def test_ranks_give_xp_and_only_rank_a_gives_a_gift():
    s = _state({("ceil", "kettle"): 60, ("fatboy", "kettle"): 30, ("mira", "ceil"): 10})
    out = synergy.bond_perks(s, ["ceil", "kettle", "fatboy", "mira"], ROOT)
    xp = {(r["a"], r["b"]): r for r in out["bondXp"]}
    assert xp[("ceil", "kettle")]["rank"] == "A" and xp[("fatboy", "kettle")]["rank"] == "B"
    assert ("ceil", "mira") not in xp
    assert [(g["a"], g["b"]) for g in out["bondGifts"]] == [("ceil", "kettle")]
    assert out["bondGifts"][0]["unitDef"] == "armhawk" and out["bondGifts"][0]["source"] == "recommended"


def test_a_gift_is_never_a_unit_either_pack_has():
    heroes = sorted(PACKS["heroes"])
    for i, a in enumerate(heroes):
        for b in heroes[i + 1:]:
            g = synergy.choose_gift(a, b, gifts=GIFTS, packs=PACKS["heroes"], umwelt={}, seed=1, factories=PACKS["factories"])
            if g:
                taken = synergy.pack_units(PACKS["heroes"][a], PACKS["factories"]) | synergy.pack_units(PACKS["heroes"][b], PACKS["factories"])
                assert g["unitDef"] not in taken, (a, b, g)


def test_the_draw_is_seeded_and_falls_back_to_the_pool():
    packs = dict(PACKS["heroes"])
    packs["kettle"] = dict(packs["kettle"], escorts=[{"unitDef": "armhawk", "count": 2}])  # recommendation taken
    one = synergy.choose_gift("ceil", "kettle", gifts=GIFTS, packs=packs, umwelt={}, seed="x")
    two = synergy.choose_gift("ceil", "kettle", gifts=GIFTS, packs=packs, umwelt={}, seed="x")
    assert one == two and one["source"] == "pool" and one["unitDef"] != "armhawk"


def test_every_gift_unit_is_a_real_unit():
    units = [r["unitDef"] for rs in GIFTS["recommended"].values() for r in rs] + [p["unitDef"] for p in GIFTS["pool"]]
    assert not [u for u in units if u not in COSTS]
