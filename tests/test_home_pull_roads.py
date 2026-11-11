"""Tenebrium sends the company home to muster (owner call, 2026-11-11: "go to the jungle, do a sortie
while the builders spend all their Tnb, and then the next sortie should be out on the fields of battle
again"; muster and fortify are one mission type). It replaced the home pull on the Rock Jungle's door
jobs (2026-11-04), which raised them while the bag was full."""
import copy
from pathlib import Path

from verdance.common import WORKSPACE_ROOT
from verdance.campaign import engine
from verdance.world import roads

WS = Path(WORKSPACE_ROOT)


def _home_scores(tnb):
    st = engine.default_v1_state()
    st["commerce"]["tenebrium"] = tnb
    return {j["id"]: j["score"] for j in roads.legal_jobs(copy.deepcopy(st), WS)
            if j["mapId"] == roads.HOME_MAP_ID}


def _founded(tnb, last_kind="seize_lane", last_map=roads.HOME_MAP_ID):
    st = engine.default_v1_state()
    st["commerce"]["tenebrium"] = tnb
    st["history"] = [{"mapId": "greenest_fields", "objectiveKind": "seize_lane", "verdict": "victory", "resultKey": "a"},
                     {"mapId": roads.HOME_MAP_ID, "objectiveKind": "fortify_zone", "verdict": "partial", "resultKey": "b"},
                     {"mapId": last_map, "objectiveKind": last_kind, "verdict": "partial", "resultKey": "c"}]
    return st


def _cards(st):
    return roads.road_sorties(copy.deepcopy(st), WS)["cards"]


def test_the_door_jobs_no_longer_move_with_the_bag():
    assert _home_scores(0), "a fresh state has Rock Jungle jobs"
    assert _home_scores(0) == _home_scores(7)


def test_tenebrium_after_a_battle_recommends_the_muster():
    cards = _cards(_founded(3))
    assert cards[0]["id"] == roads.MUSTER_ID and cards[0]["recommended"]
    assert [c["id"] for c in cards if c.get("recommended")] == [roads.MUSTER_ID], "one recommendation"
    eff = cards[0]["effect"]
    assert (eff["mapId"], eff["contractKind"], eff["preferredCaptureZoneId"], eff["journey"]) == \
        (roads.HOME_MAP_ID, "fortify_zone", roads.MUSTER_ZONE, "muster")
    assert "3 Tenebrium sits unstaked" in cards[0]["blurb"]
    lean = [c for c in cards if c.get("lean")]
    assert len(lean) == 1 and not lean[0]["recommended"], "the lean stays, as a mark"


def test_after_a_muster_the_next_sortie_is_a_battle():
    cards = _cards(_founded(3, last_kind="fortify_zone"))
    muster = next(c for c in cards if c["id"] == roads.MUSTER_ID)
    assert not muster["recommended"] and muster["muster"]["builtLast"]
    assert "Take the army out" in muster["blurb"]
    rec = [c for c in cards if c.get("recommended")]
    assert len(rec) == 1 and rec[0]["id"] != roads.MUSTER_ID, "one battle is recommended"


def test_an_empty_bag_has_nothing_to_muster_with():
    floor = roads.build_floor(WS)
    cards = _cards(_founded(floor - 1))
    muster = next(c for c in cards if c["id"] == roads.MUSTER_ID)
    assert not muster["recommended"] and "Nothing to stake" in muster["blurb"]
    assert _cards(_founded(floor))[0]["id"] == roads.MUSTER_ID, "the cheapest builder's stake is enough"


def test_no_muster_before_the_jungle_is_founded():
    st = engine.default_v1_state()
    st["commerce"]["tenebrium"] = 9
    assert roads.muster_job(st, WS) is None
    assert all(c["id"] != roads.MUSTER_ID for c in _cards(st))


def test_the_debrief_says_what_moved():
    before = {"reputation": {"armada": 20.0, "cortex": 50.0}}
    st = {"reputation": {"armada": 17.0, "cortex": 50.2}}
    res = {"secondaryResults": [{"kind": "scout", "label": "the ford", "completed": True},
                                {"kind": "vault", "label": "x", "completed": True}]}
    mv = engine.what_moved(before, st, res, "tabula", [{"name": "Vane"}], [])
    assert mv["standing"] == [{"side": "armada", "name": "Armada", "before": 20, "after": 17, "delta": -3.0}]
    assert mv["marks"] == [{"kind": "scout", "label": "the ford", "done": True}]
    assert mv["rescued"] == ["Vane"] and "camp" not in mv
    assert mv["joined"] == [{"name": "Vane", "where": "camp"}]


def test_the_debrief_says_where_a_new_recruit_waits():
    """Playtester note 2026-11-04: a recruit raised and left on the field says where to fetch them."""
    st = {"camp": {"people": {"mira": {"where": "field", "mapId": "tabula", "zoneId": "T_W_CAUSEWAY", "label": "West Causeway"}}}}
    mv = engine.what_moved({}, st, {}, "tabula", [{"heroId": "mira", "name": "Mira"}], [])
    assert mv["joined"] == [{"name": "Mira", "where": "field", "mapId": "tabula", "label": "West Causeway"}]


def test_the_battle_goes_out_from_the_jungle():
    """Once home is founded, a recommended battle is off the home map when one is open; the lean keeps
    its mark wherever the draw fell, and the home doors stay on offer (owner call, 2026-11-11)."""
    st = _founded(3, last_kind="fortify_zone")      # after a muster: a battle is the move
    jobs = roads.legal_jobs(copy.deepcopy(st), WS)
    assert any(j["mapId"] != roads.HOME_MAP_ID for j in jobs) and any(j["mapId"] == roads.HOME_MAP_ID for j in jobs)
    checked = 0
    for seed in range(200):
        out = roads.road_sorties(copy.deepcopy(st), WS, seed=seed)
        lean = next(c for c in out["cards"] if c.get("lean"))
        rec = [c for c in out["cards"] if c.get("recommended")]
        assert len(rec) == 1
        assert rec[0]["effect"]["mapId"] != roads.HOME_MAP_ID, (seed, rec[0]["id"])
        if lean["effect"]["mapId"] == roads.HOME_MAP_ID:
            assert not lean["recommended"] and rec[0]["id"] != lean["id"]
            assert any(c["id"] == lean["id"] for c in out["cards"]), "the home door stays on offer"
            checked += 1
    assert checked, "some draw leaned home"
