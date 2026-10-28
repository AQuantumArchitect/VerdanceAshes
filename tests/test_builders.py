#!/usr/bin/env python3
"""The builders (owner, 2026-10-26): Mask raises a T1 Bot Lab, a Legion constructor joins the cast,
no company constructor raises a T2 (or later) lab, the scout buildings come with storage, and no XP
unlocks a build. The gadget itself runs in tools/hud_harness/lab_tier_test.py."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "mod" / "VerdanceAshes.sdd"
S = ROOT / "data" / "story"
PACKS = json.loads((S / "crew_packs.json").read_text(encoding="utf-8-sig"))
LUA = (MOD / "luarules" / "gadgets" / "include" / "va_crew_roster.lua").read_text(encoding="utf-8")


def _esc(h):
    return {e["unitDef"]: e["count"] for e in PACKS["heroes"][h].get("escorts", [])}


def test_mask_has_his_own_decoy_that_raises_a_bot_lab():
    src = (MOD / "units" / "va_mask.lua").read_text(encoding="utf-8")
    assert 'units/armdecom_tenebrium.lua' in src and '"armlab"' in src and "va_mask = def" in src
    assert PACKS["heroes"]["mask"]["unitDef"] == "va_mask" and PACKS["chassis"]["va_mask"]["hasBuildPower"]
    assert 'unitDef = "va_mask"' in LUA.split("\n  mask = {", 1)[1].split("\n  },", 1)[0]
    costs = json.loads((S / "unit_costs.json").read_text(encoding="utf-8"))
    assert costs["units"]["va_mask"] == costs["units"]["armdecom"]
    # the occupation shells' ordinary decoys are untouched
    assert '"armlab"' not in (MOD / "units" / "armdecom_tenebrium.lua").read_text(encoding="utf-8")
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import rename_heroes_v1 as r
    assert r.UNITDEFS["mask"] == ("armdecom", "va_mask")


def test_a_legion_constructor_joins_the_cast():
    p = PACKS["heroes"]["mason"]
    assert p["unitDef"] == "legck" and _esc("mason") == {"legmlv": 2, "legdrag": 10, "legforti": 4}   # walls and Sappers (2026-10-28)
    assert PACKS["chassis"]["legck"]["hasBuildPower"]
    codex = {h["heroId"]: h for h in json.loads((S / "hero_codex.json").read_text(encoding="utf-8"))["heroes"]}
    assert codex["mason"]["faction"] == "legion" and codex["mason"]["doctrine"] == "constructor"
    web = json.loads((S / "support_web.json").read_text(encoding="utf-8"))
    ties = {frozenset((e["a"], e["b"])) for e in web["edges"] if e.get("authored")}
    assert {frozenset(("mason", x)) for x in ("consul", "rusk", "twitch")} <= ties


def test_builders_the_data_now_knows_about():
    builders = {h for h, p in PACKS["heroes"].items() if PACKS["chassis"].get(p["unitDef"], {}).get("hasBuildPower")}
    assert {"consul", "twitch", "solarium", "mask", "mason"} <= builders
    for unit in ("va_lumen", "armfark", "va_printer"):
        assert PACKS["chassis"][unit]["hasBuildPower"], unit


def test_no_company_constructor_raises_a_t2_lab():
    src = (MOD / "luarules" / "gadgets" / "game_verdance_lab_tier.lua").read_text(encoding="utf-8")
    for lab in ("armalab", "coralab", "legalab", "armavp", "coravp", "legavp", "armaap", "coraap", "legaap", "corgant"):
        assert f'"{lab}"' in src, lab
    assert "techlevel" in src and "AllowUnitCreation" in src
    # greyed out with the reason, never cut from the menu; All That Simmers allows them
    assert "EditUnitCmdDesc" in src and "disabled = true" in src and "RemoveUnitCmdDesc(" not in src
    assert "all_that_simmers" in src and "all that simmers" in src


def test_the_scout_heroes_are_their_bays():
    """Owner call 2026-10-28: the scout hero is the factory, lands with a metal storage and an extra
    1k metal, and starts printing scouts on repeat; no starting scouts."""
    for hid, bay, stor in (("spoke", "legvp", "legmstor"), ("tick", "armlab", "armmstor"), ("noctua", "legap", "legmstor")):
        p = PACKS["heroes"][hid]
        assert p["unitDef"] == bay and p["packTotal"] == 1 and _esc(hid) == {stor: 1} and p["canLead"] is False, hid
        fab = PACKS["factories"][p["factory"]]
        assert fab["structureDef"] is None and fab["startMetal"] == 1000 and fab["repeatQueue"] >= 1, hid
    src = (MOD / "luarules/gadgets/include/campaign/crew_packs.lua").read_text(encoding="utf-8")
    assert "CMD.REPEAT" in src and "VA_SCOUT_BONUS_METAL" in src and "fab.startMetal" in src
    start = (MOD / "luarules/gadgets/include/campaign/start.lua").read_text(encoding="utf-8")
    assert "VA_SCOUT_BONUS_METAL" in start and "VA_COMMERCE_APPLIED = true" in start


def test_no_xp_unlocks_a_build():
    craft = (MOD / "luarules" / "gadgets" / "game_verdance_craft_xp.lua").read_text(encoding="utf-8")
    assert "InsertUnitCmdDesc" not in craft and "buildoptions" not in craft.lower()


def test_a_builder_seeds_a_base_build_power_is_not_enough():
    """Owner call 2026-10-28: builders are the heroes who can raise a base (economy, factories,
    constructors), flagged baseSeeder. Build power alone (Ketha's rez bots, nano towers, Sister Lumen's
    defences, the Infestor) is not a builder."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from verdance.company import encounters as EN
    seeders = {h for h, p in PACKS["heroes"].items() if p.get("baseSeeder")}
    assert seeders == {"twitch", "consul", "solarium", "mason", "mask", "rookery", "dam"}
    assert all(PACKS["heroes"][h].get("buildsEco") for h in seeders)
    assert not PACKS["heroes"]["lumen"].get("buildsEco") and not PACKS["heroes"]["lumen"].get("baseSeeder")
    assert set(EN.eco_builders(ROOT)) == seeders
    for h in ("ketha", "lumen", "infestor", "commando", "noctua"):
        assert not EN.is_builder(PACKS["heroes"][h]), h


def test_the_six_packs_of_2026_10_28():
    want = {"rookery": ("armca", 3, {"armfig": 4, "corveng": 2, "legionnaire": 2, "legvenator": 2}), "dam": ("armbeaver", 4, {}),
            "arc": ("armzeus", 1, {"armsam": 6}), "mammoth": ("corsumo", 1, {}), "gladius": ("legaskirmtank", 6, {}),
            "triton": ("legfloat", 1, {"armanac": 8})}   # as recast on 2026-10-28
    for h, (unit, n, esc) in want.items():
        p = PACKS["heroes"][h]
        assert p["unitDef"] == unit and p["packTotal"] == n and _esc(h) == esc, h
    assert len(PACKS["heroes"]) == 64   # 64, recast to 63, then Gorgon
    web = json.loads((S / "support_web.json").read_text(encoding="utf-8"))
    for h in want:
        ties = [e for e in web["edges"] if h in (e["a"], e["b"]) and e.get("authored")]
        pols = {e["polarity"] for e in ties}
        assert len(ties) >= 4 and pols & {"bond", "attract", "sibling", "mentor", "mirror"} and pols & {"rivalry", "tension", "friction"}, h
    lua = (MOD / "luarules/gadgets/include/va_crew_roster.lua").read_text(encoding="utf-8")
    assert all(f"  {h} = {{" in lua for h in want)
