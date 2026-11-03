#!/usr/bin/env python3
"""Taking ground needs presence (verdance.world.claim); the extraction headcount decides who lived
(manifest.dropped / vanished); people left on a map are found there next time (field_people)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine  # noqa: E402
from verdance.belief import manifest  # noqa: E402
from verdance.campaign.measure import apply_zone_dv  # noqa: E402
from verdance.world import claim, roads  # noqa: E402


def test_one_need_on_every_map():
    for map_id in ("greenest_fields", "koom_valley", "tabula", "all_that_simmers"):
        assert claim.claim_need(map_id, ROOT) == 1500


def test_ownership_is_over_1500_and_over_three_times_everyone_else():
    """Owner call (2026-10-29): 1500 < (AV+DV)self > 3 * SUM(AV+DV)others, for every side."""
    assert claim.holder({"ashwalkers": 1500}) == (None, 1500)                  # not more than 1500
    assert claim.holder({"ashwalkers": 1600})[0] == "ashwalkers"
    assert claim.holder({"ashwalkers": 1600, "armada": 500})[0] == "ashwalkers"   # 1600 > 1500
    assert claim.holder({"ashwalkers": 1600, "armada": 300, "wild": 300})[0] is None  # 3 x 600 = 1800
    assert claim.holder({"armada": 2000, "ashwalkers": 700})[0] is None        # the factions too: 2100
    assert claim.holder({"armada": 2000, "ashwalkers": 500})[0] == "armada"
    assert claim.holder({"armada": 50}) == (None, 50)
    assert claim.holder({}) == (None, 0.0)


def test_the_gadgets_read_the_same_rule():
    lua = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_claim.lua").read_text(encoding="utf-8")
    assert "NEED = 1500, DOMINANCE = 3" in lua
    exfil = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_exfil.lua").read_text(encoding="utf-8")
    assert "VA_CLAIM.ours(row, need, nil, allies)" in exfil and "liveOwned[zid]" in exfil
    presence = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/campaign/objective_presence.lua").read_text(encoding="utf-8")
    assert "VA_CLAIM.withoutAllies(row, allies)" in presence


ROWS = [
    {"ashwalkers": 1600, "nullmercs": 7731}, {"ashwalkers": 1400, "nullmercs": 7731},
    {"nullmercs": 4000, "ashwalkers": 1400, "armada": 500}, {"nullmercs": 4000, "armada": 1400},
    {"armada": 5200, "nullmercs": 900, "ashwalkers": 800}, {"armada": 5000, "nullmercs": 900, "ashwalkers": 800},
    {"ashwalkers": 2000, "nullmercs": 3000, "armada": 100}, {"ashwalkers": 1600, "armada": 300, "wild": 300},
    {"armada": 2000, "ashwalkers": 500}, {"armada": 50}, {},
]


def test_lua_and_python_name_the_same_holder():
    """va_claim.lua and verdance.world.claim are one rule: same row, same allies, same owner."""
    import ctypes, glob
    libs = glob.glob("/usr/lib/x86_64-linux-gnu/liblua5.4.so*")
    if not libs:
        return
    L = ctypes.CDLL(libs[0])
    L.luaL_newstate.restype = ctypes.c_void_p
    L.luaL_openlibs.argtypes = [ctypes.c_void_p]
    L.luaL_loadbufferx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p]
    L.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    L.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    L.lua_tolstring.restype = ctypes.c_char_p
    st = L.luaL_newstate(); L.luaL_openlibs(st)
    lua_src = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_claim.lua").read_text(encoding="utf-8")
    def row(r):
        return "{" + ",".join(f'["{k}"]={v}' for k, v in r.items()) + "}"
    cases = []
    for r in ROWS:
        for allies in ([], ["nullmercs"]):
            cases.append((r, allies))
    body = "local M = (function()\n" + lua_src + "\nend)()\nlocal out = {}\n"
    for r, allies in cases:
        al = "{" + ",".join(f'["{a}"]=true' for a in allies) + "}"
        body += f"out[#out+1] = tostring((M.holder({row(r)}, 1500, 3, {al})))\n"
    body += "return table.concat(out, ',')"
    b = body.encode()
    assert L.luaL_loadbufferx(st, b, len(b), b"claim", b"t") == 0, L.lua_tolstring(st, -1, None)
    assert L.lua_pcallk(st, 0, 1, 0, None, None) == 0, L.lua_tolstring(st, -1, None)
    lua = L.lua_tolstring(st, -1, None).decode().split(",")
    py = [str(claim.holder(r, 1500, 3, allies)[0]) for r, allies in cases]
    assert lua == [p.replace("None", "nil") for p in py], list(zip(cases, lua, py))


def test_allies_do_not_contest_the_company():
    """Mission 1 on a stock BAR (2026-11-02): the Null Mercs, allied with the company, followed it into
    GF_NW_BASTION, and the hold's need climbed from 3871 to 27751 because their presence counted as
    "everyone else". The company's allies in the match now count neither for it nor against it."""
    mercs = ["nullmercs"]
    assert claim.company_owns({"ashwalkers": 1600, "nullmercs": 7731}, allies=mercs)
    assert not claim.company_owns({"ashwalkers": 1600, "nullmercs": 7731})          # without the alliance
    assert not claim.company_owns({"ashwalkers": 1400, "nullmercs": 7731}, allies=mercs)  # allies don't lend
    assert not claim.company_owns({"ashwalkers": 1600, "armada": 600, "nullmercs": 50}, allies=mercs)
    assert claim.zone_holder({"nullmercs": 7731}, allies=mercs) == "nullmercs"     # the mercs' own ground
    # the mercs compete against Armada but not against the company (owner call, 2026-11-02)
    assert claim.zone_holder({"nullmercs": 4000, "ashwalkers": 1400, "armada": 500}, allies=mercs) == "nullmercs"
    assert claim.zone_holder({"nullmercs": 4000, "ashwalkers": 1400, "armada": 500}) is None
    assert claim.zone_holder({"nullmercs": 4000, "armada": 1400}, allies=mercs) is None     # 3 x 1400 = 4200
    assert claim.zone_holder({"armada": 5000, "nullmercs": 900, "ashwalkers": 800}, allies=mercs) is None  # 3 x 1700
    assert claim.zone_holder({"armada": 5200, "nullmercs": 900, "ashwalkers": 800}, allies=mercs) == "armada"
    # both qualify: the company holds it
    assert claim.zone_holder({"ashwalkers": 2000, "nullmercs": 3000, "armada": 100}, allies=mercs) == "ashwalkers"
    assert claim.zone_holder({"ashwalkers": 2000, "nullmercs": 4000}, allies=mercs) == "ashwalkers"
    assert claim.zone_holder({"ashwalkers": 2000, "nullmercs": 4000}) is None


def test_allied_presence_at_home_follows_the_same_rule():
    state = {"zoneMemory": {"greenest_fields": {"GF_NW_BASTION": {"controllingFaction": "armada", "abstract": {"control": "armada"}}}}}
    res = {"deploymentMapId": "greenest_fields", "alliedFactions": ["nullmercs"],
           "zoneDv": {"GF_NW_BASTION": {"ashwalkers": 2000, "nullmercs": 4000}}}
    assert apply_zone_dv(state, res, ROOT) == ["GF_NW_BASTION"]
    assert state["zoneMemory"]["greenest_fields"]["GF_NW_BASTION"]["controllingFaction"] == "ashwalkers"
    assert manifest.held_zones(res) == ["GF_NW_BASTION"]
    assert manifest.held_zones(dict(res, alliedFactions=[])) == []


def test_homecoming_claims_only_with_presence():
    state = {"zoneMemory": {"greenest_fields": {"GF_SE_PLATEAU": {"controllingFaction": "neutral", "abstract": {"control": "neutral"}}}}}
    weak = {"deploymentMapId": "greenest_fields", "zoneDv": {"GF_SE_PLATEAU": {"ashwalkers": 250}}}
    assert apply_zone_dv(state, weak, ROOT) == []
    assert state["zoneMemory"]["greenest_fields"]["GF_SE_PLATEAU"]["controllingFaction"] == "neutral"
    strong = {"deploymentMapId": "greenest_fields", "zoneDv": {"GF_SE_PLATEAU": {"ashwalkers": 1650}}}
    assert apply_zone_dv(state, strong, ROOT) == ["GF_SE_PLATEAU"]


def test_a_door_is_held_only_with_the_claim_presence():
    state = engine.default_v1_state()
    base = {"deploymentMapId": "greenest_fields", "missionNumber": 3}
    roads.record_homecoming(state, dict(base, zoneDv={"GF_SE_PLATEAU": {"ashwalkers": 1400}}), ROOT)
    assert not roads.held(state, "GF_SE_PLATEAU")
    roads.record_homecoming(state, dict(base, zoneDv={"GF_SE_PLATEAU": {"ashwalkers": 1600}}), ROOT)
    assert roads.held(state, "GF_SE_PLATEAU")


def test_a_door_take_card_names_the_presence():
    state = engine.default_v1_state()
    state["history"] = [{"mapId": "greenest_fields"}, {"mapId": "the_rock_jungle"}]   # both walked: doors to take
    cards = [roads._card(j, False) for j in roads.legal_jobs(state, ROOT) if j["kind"] == "take"]
    assert cards and all("more than 1500 metal of army and defences" in c["blurb"] for c in cards)


def _result(going, staying, dropped):
    return {"manifest": {"schema": "verdance-manifest/1", "kind": "extracted",
                         "going": {"heroes": [{"heroId": h} for h in going]},
                         "staying": {"heroes": [{"heroId": h, "zoneId": "Z"} for h in staying]},
                         "dropped": dropped}}


def test_a_hero_who_dropped_and_is_nowhere_at_extraction_did_not_survive():
    r = _result(["vane"], ["hearth"], ["ketha", "vane", "hearth"])
    assert manifest.dropped(r) == {"ketha", "vane", "hearth"}
    assert manifest.vanished(r) == {"ketha"}
    assert manifest.vanished({"manifest": {"kind": "extracted", "going": {}, "staying": {}}}) == set()


def test_people_left_on_a_map_are_found_there():
    state = {"camp": {"people": {"hearth": {"where": "field", "mapId": "greenest_fields", "zoneId": "GF_NW_CITADEL"},
                                 "mask": {"where": "posted", "mapId": "greenest_fields", "zoneId": "GF_C_GATE"},
                                 "rusk": {"where": "field", "mapId": "tabula", "zoneId": "T_C_SPILLWAY"}}},
             "characters": {}}
    assert manifest.field_people(state, "greenest_fields") == [{"heroId": "hearth", "zoneId": "GF_NW_CITADEL"}]


def test_the_roster_buries_a_hero_the_ledger_lost():
    from verdance.campaign.roster import update_roster
    state = engine.default_v1_state()
    roster = state.setdefault("roster", {})
    roster["heroes"] = [{"heroId": "ketha", "status": "active", "campaignXp": 10.0},
                        {"heroId": "vane", "status": "active", "campaignXp": 10.0},
                        {"heroId": "pavise", "status": "locked", "campaignXp": 0.0}]
    r = _result(["vane"], [], ["ketha", "vane"])
    r["heroResults"] = {}        # the gadget's hero ledger was emptied (a LuaRules reload)
    update_roster(state, r, True, True)
    by = {h["heroId"]: h for h in roster["heroes"]}
    assert by["ketha"]["status"] == "dead"
    assert by["vane"]["status"] == "active"
    assert by["pavise"]["campaignXp"] == 0.0     # never on the field: no XP for sitting at home


def test_the_alliance_reaches_home_through_the_result_contract():
    """Three-sortie stock rehearsal (2026-11-02): mission 2 took the Koom door (GF_SE_PLATEAU) and lifted
    from it with the Null Mercs beside it (9425 to our 9112), but the door was not held at home: the
    result contract dropped alliedFactions, so the mercs counted against the company again, and mission 3
    was offered the same door."""
    from verdance.hub.contract import normalize_result, result_v2_to_v1_fields
    raw = {"zoneDv": {"GF_SE_PLATEAU": {"nullmercs": 9425, "ashwalkers": 9112}}, "alliedFactions": ["nullmercs"]}
    norm = normalize_result(raw)
    assert norm["alliedFactions"] == ["nullmercs"]
    v1 = result_v2_to_v1_fields(norm)
    assert v1["alliedFactions"] == ["nullmercs"]
    state = engine.default_v1_state()
    roads.record_homecoming(state, dict(v1, deploymentMapId="greenest_fields", missionNumber=2), ROOT)
    assert roads.held(state, "GF_SE_PLATEAU")

