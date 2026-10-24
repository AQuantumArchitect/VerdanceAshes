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


def test_claim_grows_half_again_per_road_from_greenest_fields():
    assert claim.claim_need("greenest_fields", ROOT) == 400
    assert claim.claim_need("koom_valley", ROOT) == 600          # one road out
    assert claim.claim_need("tabula", ROOT) == 900               # two
    assert claim.claim_need("all_that_simmers", ROOT) == 1350    # three


def test_the_company_needs_the_claim_presence_the_factions_do_not():
    assert claim.holder({"ashwalkers": 380}, 400) == (None, 380)
    assert claim.holder({"ashwalkers": 420, "armada": 300}, 400)[0] == "ashwalkers"
    assert claim.holder({"armada": 50}, 400)[0] == "armada"
    assert claim.holder({}, 400) == (None, 0.0)


def test_homecoming_claims_only_with_presence():
    state = {"zoneMemory": {"greenest_fields": {"GF_SE_PLATEAU": {"controllingFaction": "neutral", "abstract": {"control": "neutral"}}}}}
    weak = {"deploymentMapId": "greenest_fields", "zoneDv": {"GF_SE_PLATEAU": {"ashwalkers": 250}}}
    assert apply_zone_dv(state, weak, ROOT) == []
    assert state["zoneMemory"]["greenest_fields"]["GF_SE_PLATEAU"]["controllingFaction"] == "neutral"
    strong = {"deploymentMapId": "greenest_fields", "zoneDv": {"GF_SE_PLATEAU": {"ashwalkers": 650}}}
    assert apply_zone_dv(state, strong, ROOT) == ["GF_SE_PLATEAU"]


def test_a_door_is_held_only_with_the_claim_presence():
    state = engine.default_v1_state()
    base = {"deploymentMapId": "greenest_fields", "missionNumber": 3}
    roads.record_homecoming(state, dict(base, zoneDv={"GF_SE_PLATEAU": {"ashwalkers": 300}}), ROOT)
    assert not roads.held(state, "GF_SE_PLATEAU")
    roads.record_homecoming(state, dict(base, zoneDv={"GF_SE_PLATEAU": {"ashwalkers": 480}}), ROOT)
    assert roads.held(state, "GF_SE_PLATEAU")


def test_a_door_take_card_names_the_presence():
    state = engine.default_v1_state()
    cards = [roads._card(j, False) for j in roads.legal_jobs(state, ROOT) if j["kind"] == "take"]
    assert cards and all("metal of army or defences" in c["blurb"] for c in cards)


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
