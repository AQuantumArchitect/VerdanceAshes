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


def test_ketha_reach_is_the_bonus_doubled_and_never_compounds():
    craft = (MOD / "luarules" / "gadgets" / "game_verdance_craft_xp.lua").read_text(encoding="utf-8")
    k = {n: float(v) for n, v in re.findall(r"local (KETHA_RANGE_\w+) = ([0-9.]+)", craft)}
    per = float(re.search(r"local RANGE_PER_XP = ([0-9.]+)", craft).group(1))
    cap = float(re.search(r"local RANGE_CAP = ([0-9.]+)", craft).group(1))
    assert k["KETHA_RANGE_BASE"] == 1.0 and k["KETHA_RANGE_PER_XP"] == 2 * per
    assert k["KETHA_RANGE_CAP"] - 1 == 2 * (cap - 1)
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
