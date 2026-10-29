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
    assert "VA_CLAIM.ours(row, need)" in exfil and "liveOwned[zid]" in exfil


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
