#!/usr/bin/env python3
"""Playtest fixes, 2026-10-26 (owner, mid-campaign): the shop hires for one drop; Ketha's reach bonus
doubled (not runaway) and she starts experienced; the infil card lists what actually drops; a hero
raised in the wound of a territory mission does not turn it into a rescue (the gadget side runs in
tools/hud_harness/exfil_gadget_test.py)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MOD = ROOT / "mod" / "VerdanceAshes.sdd"


def test_hired_units_lift_but_never_join_the_reserve():
    from verdance.company import reserve
    roster = {"reserve": {"armpw": 2}, "cadre": {}}
    out = reserve.homecoming(roster, {"manifest": {"going": {"units": {"corthud": 9, "armpw": 2},
                                                                "hiredUnits": {"corthud": 7}}}})
    assert out["reserve"] == {"armpw": 4, "corthud": 2}      # two Thugs were built on the field, seven hired


def test_a_shop_purchase_is_spent_on_its_drop():
    from verdance.campaign import commerce
    state = {"missionNumber": 2, "commerce": {"tenebrium": 1, "metalK": 3, "owned": {
        "punch_of_thugs": {"qty": 2, "loan": False, "kind": "purchase_package", "unitDef": "corthud", "count": 7},
        "cortex_constructor": {"qty": 1, "loan": False, "kind": "constructor", "unitDef": "corck"}}}}
    commerce.settle_commerce_after_sortie(state, {"resultKey": "t|2"}, True, True, False, workspace=ROOT)
    assert "punch_of_thugs" not in state["commerce"]["owned"]
    assert "cortex_constructor" not in state["commerce"]["owned"]
    assert any(r.get("op") == "drop_spent" for r in state["commerce"]["ledger"])


def test_ketha_reach_is_toned_back_and_never_compounds():
    craft = (MOD / "luarules" / "gadgets" / "game_verdance_craft_xp.lua").read_text(encoding="utf-8")
    k = {n: float(v) for n, v in re.findall(r"local (KETHA_RANGE_\w+) = ([0-9.]+)", craft)}
    per = float(re.search(r"local RANGE_PER_XP = ([0-9.]+)", craft).group(1))
    cap = float(re.search(r"local RANGE_CAP = ([0-9.]+)", craft).group(1))
    # owner, 2026-10-27: x2.2 for Ketha and x1.8 for everyone else, reached at full experience (2.4)
    assert k["KETHA_RANGE_BASE"] == 1.0 and k["KETHA_RANGE_CAP"] == 2.2 and cap == 1.8
    assert abs(1 + k["KETHA_RANGE_PER_XP"] * 2.4 - 2.2) < 0.01 and abs(1 + per * 2.4 - 1.8) < 0.01
    assert 'GetUnitBuildParams(unitID, "buildDistance")' not in craft     # the base is the unit type's
    packs = json.loads((ROOT / "data/story/crew_packs.json").read_text(encoding="utf-8"))
    assert packs["heroes"]["ketha"]["startXpFixed"] >= 1.0 and packs["heroes"]["ketha"]["packTotal"] == 2


def test_the_infil_card_lists_what_drops():
    src = (MOD / "luaui" / "Widgets" / "gui_verdance_infil.lua").read_text(encoding="utf-8")
    assert "mission.roster and mission.roster.cadre" in src and "mission.commerce and mission.commerce.deploy" in src


def test_a_rez_in_a_territory_wound_keeps_the_territory_extraction():
    camp = (MOD / "luarules" / "gadgets" / "game_verdance_campaign.lua").read_text(encoding="utf-8")
    rule = camp.split("function GG.VA_ExtractRule()", 1)[1].split("\nend", 1)[0]
    assert "rezHeroId" not in rule


def test_kettle_is_an_archangel_and_a_heavy_transport():
    packs = json.loads((ROOT / "data/story/crew_packs.json").read_text(encoding="utf-8"))
    assert packs["heroes"]["kettle"]["escorts"] == [{"unitDef": "armhvytrans", "count": 1}]
    lua = (MOD / "luarules/gadgets/include/va_crew_roster.lua").read_text(encoding="utf-8")
    block = lua.split("\n  kettle = {", 1)[1].split("\n  },", 1)[0]
    assert "armhvytrans" in block and "armferret" not in block and "armatlas" not in block


def test_the_infestor_prints_goblins_and_flies_cover():
    src = (MOD / "units/va_infestor.lua").read_text(encoding="utf-8")
    assert '"leggob"' in src and '"va_infestor"' in src and "T2 Bots/leginfestor.lua" in src
    packs = json.loads((ROOT / "data/story/crew_packs.json").read_text(encoding="utf-8"))
    h = packs["heroes"]["infestor"]
    assert h["unitDef"] == "va_infestor" and h["escorts"] == [{"unitDef": "legah", "count": 2}]
    import rename_heroes_v1 as r
    assert r.UNITDEFS["infestor"] == ("leginfestor", "va_infestor")


def _state_with_people():
    return {"characters": {"halbard": {"name": "Halbard"}, "kettle": {"name": "Saint Kettle"}},
            "camp": {"people": {"halbard": {"where": "field", "mapId": "greenest_fields", "zoneId": "GF_SE_PLATEAU", "label": "Southeast Plateau"},
                                "kettle": {"where": "field", "mapId": "greenest_fields", "zoneId": "GF_NW_CITADEL", "label": "Northwest Citadel"}}},
            "doors": {"GF_SE_PLATEAU": {"held": True}}}


def test_the_spearhead_crosses_a_held_door():
    from verdance.belief import manifest
    from verdance.world import roads
    st = _state_with_people()
    door = roads.load_doors(ROOT)["GF_SE_PLATEAU"]
    here = {p["heroId"]: p for p in manifest.field_people(st, "greenest_fields", ROOT)}
    far = {p["heroId"]: p for p in manifest.field_people(st, door["farMapId"], ROOT)}
    assert set(here) == {"halbard", "kettle"}
    assert set(far) == {"halbard"} and far["halbard"]["zoneId"] == door["farZoneId"] and far["halbard"]["spearhead"]
    st["doors"]["GF_SE_PLATEAU"]["held"] = False
    assert manifest.field_people(st, door["farMapId"], ROOT) == []      # a door lost: the road is shut


def test_a_field_with_someone_on_it_always_offers_a_job():
    from verdance.world import roads
    st = _state_with_people()
    cards = roads.road_sorties(st, ROOT)["cards"]
    fetch = [c for c in cards if c["id"] == "fetch_greenest_fields"]
    assert fetch and set(fetch[0]["effect"]["fetchHeroIds"]) == {"halbard", "kettle"}
    assert fetch[0]["effect"]["mapId"] == "greenest_fields" and fetch[0]["effect"]["padLocked"]
