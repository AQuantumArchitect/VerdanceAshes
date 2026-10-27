#!/usr/bin/env python3
"""Wild heroes roam by the bond web (owner, 2026-10-26): umwelt.foresight.encounter places them,
the Umwelt field carries the draw, anchored heroes (constructor-gated recruits, builders, factory
heroes, buildings) keep their authored place."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.company import company as C  # noqa: E402
from verdance.company import encounters as EN  # noqa: E402


def _state(band=("vane", "brakhov", "verse"), mission=1):
    st = {"campaignId": "t_enc", "missionNumber": mission, "seed": 7,
          "company": {"sealed": True, "core": ["ketha"], "band": list(band), "joinedLater": []},
          "fieldPool": {}, "roster": {"heroes": []}}
    C.ensure_company(st, ROOT)
    return st


def _skip():
    if not EN.available():
        import unittest
        raise unittest.SkipTest("umwelt.foresight.encounter not importable (UMWELT_SRC)")


def test_every_wild_hero_is_placed_and_anchors_hold():
    _skip()
    st = _state()
    r = EN.refresh_whereabouts(st, ROOT)
    assert r["placed"] == r["wild"] > 40
    consul = st["fieldPool"]["consul"]["roam"]
    assert consul["zoneId"] == "TRJ_NW_GATE" and consul["anchored"] and "constructor" in consul["reasons"][0]
    for hid in ("solarium", "spoke", "tick", "hearth"):
        assert st["fieldPool"][hid]["roam"]["anchored"], hid


def test_bonds_draw_heroes_toward_the_company():
    _skip()
    field, ctx = EN.build(_state(band=("vane", "brakhov", "verse")), ROOT)
    with_verse, why = field.presence("arrow", present=ctx["present"])
    without, _ = field.presence("arrow", present=["ketha"])
    assert with_verse > without and any("verse (rivalry)" in w for w in why)


def test_a_sortie_draw_is_seeded_and_heroes_roam_off_their_home_map():
    _skip()
    st = _state()
    a = EN.encounters_for_map(st, "tabula", workspace=ROOT, limit=2)
    assert a == EN.encounters_for_map(copy.deepcopy(st), "tabula", workspace=ROOT, limit=2) and len(a) == 2
    homes = {h: (st["fieldPool"][h]["home"] or [None])[0] for h in st["fieldPool"]}
    away = 0
    for m in range(1, 25):
        st["missionNumber"] = m
        for mp in ("tabula", "koom_valley", "eye_of_horus"):
            for e in EN.encounters_for_map(st, mp, workspace=ROOT, limit=2):
                away += homes.get(e["heroId"]) != mp
    assert away > 10                                     # not locked to one home each


def test_marking_a_hero_s_ground_still_meets_them_there():
    _skip()
    st = _state()
    rows = C.field_recruits_for_map(st, "greenest_fields", workspace=ROOT, limit=2, marked_zone_ids=["GF_NE_PLATEAU"])
    fat = next(r for r in rows if r["heroId"] == "fatboy")
    assert fat["zoneId"] == "GF_NE_PLATEAU" and fat["encounter"]["reasons"] == ["we marked this ground"]


def test_word_of_the_wild_comes_home_with_the_company():
    st = _state()
    obs = dict((h, eta) for h, _v, eta, _s in EN.draw_observations(st, {"manifest": {"dropped": ["verse"]}}, ROOT))
    assert "arrow" in obs and "halq" in obs and "vane" not in obs   # bound to Verse, still wild
    assert all(0 < e <= 0.35 for e in obs.values())


def test_the_belief_world_carries_draw_along_the_bond_web():
    from verdance.belief import world as W
    if not W.umwelt_available():
        import unittest
        raise unittest.SkipTest("umwelt not importable")
    spec = W.build_spec(ROOT)
    hero = next(n for n in spec.nodes if n.name == "hero:arrow")
    assert W.DRAW_ROLE in hero.roles
    drawn = {(b.source, b.target) for b in spec.bridges if W.DRAW_ROLE in b.shared_roles}
    assert ("hero:arrow", "hero:verse") in drawn and len(drawn) >= 80


def test_without_the_module_the_fixed_homes_stand(monkeypatch=None):
    st = _state()
    orig = EN._module
    EN._module = lambda: None
    try:
        rows = C.field_recruits_for_map(st, "greenest_fields", workspace=ROOT, limit=2)
        assert rows and all(r["mapId"] == "greenest_fields" and "encounter" not in r for r in rows)
        assert EN.refresh_whereabouts(st, ROOT) is None
    finally:
        EN._module = orig


def test_the_hub_preview_is_the_sortie_s_own_draw():
    _skip()
    st = _state()
    EN.refresh_whereabouts(st, ROOT)
    draws = EN.draws_by_map(st, ROOT)
    for mp in ("tabula", "greenest_fields"):
        real = [(e["heroId"], e["zoneId"]) for e in EN.encounters_for_map(st, mp, workspace=ROOT, limit=2)]
        assert real == [(d["heroId"], d["zoneId"]) for d in draws[mp][:2]]
    # marked: who is believed on the marked zone first, then the same draw minus them
    fat_zone = st["fieldPool"]["fatboy"]["roam"]["zoneId"]
    fat_map = st["fieldPool"]["fatboy"]["roam"]["mapId"]
    real = [e["heroId"] for e in EN.encounters_for_map(st, fat_map, workspace=ROOT, limit=2, marked_zone_ids=[fat_zone])]
    assert real[0] == "fatboy" and real[1:] == [d["heroId"] for d in draws[fat_map] if d["heroId"] != "fatboy"][:1]
