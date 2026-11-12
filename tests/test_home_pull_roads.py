"""Tenebrium pulls the company home to muster; the army in hand pulls it out (owner calls: 2026-11-11,
"go to the jungle, do a sortie while the builders spend all their Tnb, and then the next sortie should
be out on the fields of battle again", muster and fortify one mission type; 2026-11-12, no rule about
when, "the total amount of tenebrium you have available to spend should apply pressure to go to the
jungle... the larger the army you have, the more pressure there is to go somewhere else"). Both are
pressures on the one seeded draw every job is in; the job it falls on is the recommendation."""
import copy
from pathlib import Path

from verdance.common import WORKSPACE_ROOT
from verdance.campaign import engine
from verdance.world import roads
from verdance.world.claim import CLAIM_NEED

WS = Path(WORKSPACE_ROOT)
SEEDS = range(300)


def _home_scores(tnb):
    st = engine.default_v1_state()
    st["commerce"]["tenebrium"] = tnb
    return {j["id"]: j["score"] for j in roads.legal_jobs(copy.deepcopy(st), WS)
            if j["mapId"] == roads.HOME_MAP_ID}


def _founded(tnb, last_kind="seize_lane", reserve=None):
    st = engine.default_v1_state()
    st["commerce"]["tenebrium"] = tnb
    st["history"] = [{"mapId": "greenest_fields", "objectiveKind": "seize_lane", "verdict": "victory", "resultKey": "a"},
                     {"mapId": roads.HOME_MAP_ID, "objectiveKind": "fortify_zone", "verdict": "partial", "resultKey": "b"},
                     {"mapId": roads.HOME_MAP_ID, "objectiveKind": last_kind, "verdict": "partial", "resultKey": "c"}]
    if reserve is not None:
        st.setdefault("roster", {})["reserve"] = dict(reserve)
    return st


def _cards(st, seed=None):
    return roads.road_sorties(copy.deepcopy(st), WS, seed=seed)["cards"]


def _muster_share(st):
    return sum(_cards(st, s)[0]["id"] == roads.MUSTER_ID for s in SEEDS) / len(SEEDS)


def test_the_door_jobs_no_longer_move_with_the_bag():
    assert _home_scores(0), "a fresh state has Rock Jungle jobs"
    assert _home_scores(0) == _home_scores(7)


def test_one_draw_one_recommendation_and_the_muster_always_offered():
    for seed in range(40):
        cards = _cards(_founded(3), seed)
        rec = [c for c in cards if c.get("recommended")]
        assert len(rec) == 1 and rec[0] is cards[0] and cards[0]["lean"], seed
        assert sum(c["id"] == roads.MUSTER_ID for c in cards) == 1, "the muster is a standing offer"


def test_tenebrium_pulls_home():
    shares = [_muster_share(_founded(t)) for t in (1, 3, 9)]
    assert shares[0] < shares[1] < shares[2], shares
    m = roads.muster_job(_founded(4), WS)
    assert abs(m["pull"] - roads.TEMPERATURE * __import__("math").log(4)) < 1e-12, "four stakes: four times as likely"
    card = next(c for c in _cards(_founded(3)) if c["id"] == roads.MUSTER_ID)
    eff = card["effect"]
    assert (eff["mapId"], eff["contractKind"], eff["preferredCaptureZoneId"], eff["journey"]) ==         (roads.HOME_MAP_ID, "fortify_zone", roads.MUSTER_ZONE, "muster")
    assert "3 Tenebrium sits unstaked, 3 builders' stake" in card["blurb"]


def test_no_rule_after_a_muster():
    """A muster last time is no bar: the bag and the army decide."""
    assert _muster_share(_founded(3, last_kind="fortify_zone")) > 0


def test_an_empty_bag_has_nothing_to_muster_with():
    floor = roads.build_floor(WS)
    st = _founded(floor - 1)
    assert _muster_share(st) == 0
    muster = next(c for c in _cards(st) if c["id"] == roads.MUSTER_ID)
    assert not muster["recommended"] and "Nothing to stake" in muster["blurb"]
    assert _muster_share(_founded(floor)) > 0, "the cheapest builder's stake is enough"


def test_the_army_in_hand_pulls_out():
    """Each claim's worth of army the company can bring raises every job off the home map, up to
    the drop limit: units past it stay in the reserve and do not pull."""
    bare = _founded(3)
    full = _founded(3, reserve={"leggob": 400})
    hand = roads.army_in_hand(full, WS)
    assert hand["army"] == hand["cap"] < hand["reserve"]
    out = roads.out_pressure(full, WS)
    assert abs(out - roads.TEMPERATURE * __import__("math").log1p(hand["cap"] / CLAIM_NEED)) < 1e-12
    away = lambda st: {j["id"]: j["score"] for j in roads.road_sorties(copy.deepcopy(st), WS, seed=0)["jobs"]
                       if j["mapId"] not in (roads.HOME_MAP_ID,) and j.get("kind") != "fetch"}
    a, b = away(bare), away(full)
    assert a and all(abs(b[k] - a[k] - out) < 1e-3 for k in a)
    assert _muster_share(full) < _muster_share(bare)


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
