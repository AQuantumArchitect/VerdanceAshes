"""Commander suits: no duel in All That Simmers without one; three ways to get one."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import engine, suits, acts  # noqa: E402
from verdance.campaign.commerce import purchase_listing  # noqa: E402
from verdance.campaign.roster import apply_commander_story  # noqa: E402
from verdance.world import roads, theaters  # noqa: E402


def _state():
    s = engine.default_v1_state()
    engine.ensure_zone_memory(s, ROOT)
    return s


def _at_the_simmers_door(s):
    """The company holds a door whose road runs onto All That Simmers."""
    doors = roads.load_doors(ROOT)
    zid, door = next((z, d) for z, d in sorted(doors.items()) if d["farMapId"] == suits.SIMMERS)
    s["history"] = [{"mapId": door["mapId"]}]
    s["doors"] = {zid: {"held": True, "since": 1, "by": "ashwalkers"}}
    return s


def test_no_suit_no_duel_and_the_board_says_why():
    s = _at_the_simmers_door(_state())
    assert not suits.has_suit(s)
    assert not any(j["mapId"] == suits.SIMMERS for j in roads.legal_jobs(s, ROOT))
    out = roads.road_sorties(s, ROOT, seed=1)
    assert out["walls"] and out["walls"][0]["label"] == suits.WALL
    assert suits.WALL in out["voice"]
    suits.grant_suit(s, "legcom", "queen_rez")
    assert any(j["mapId"] == suits.SIMMERS for j in roads.legal_jobs(s, ROOT))
    assert roads.road_sorties(s, ROOT, seed=1)["walls"] == []


def test_cortex_sells_one_for_an_outrageous_fee():
    s = _state()
    s.setdefault("reputation", {})["cortex"] = 50
    s.setdefault("commerce", {}).update(tenebrium=3, metalK=40)
    assert not purchase_listing(s, "cortex_commander_suit", ROOT)["ok"]       # 3 Tnb is nowhere near
    s["commerce"]["tenebrium"] = 15
    r = purchase_listing(s, "cortex_commander_suit", ROOT)
    assert r["ok"] and r["tenebriumCost"] >= 10
    assert suits.suit(s)["unitDef"] == "corcom" and suits.suit(s)["how"] == suits.LOAN and suits.on_loan(s)
    s["commerce"]["tenebrium"] = 99
    assert not purchase_listing(s, "cortex_commander_suit", ROOT)["ok"]       # one suit at a time


def test_the_cortex_suit_is_a_loan_for_one_fight():
    from verdance.campaign.commerce import settle_commerce_after_sortie
    s = _state()
    s.setdefault("reputation", {})["cortex"] = 50
    s.setdefault("commerce", {}).update(tenebrium=30, metalK=40)
    assert purchase_listing(s, "cortex_commander_suit", ROOT)["ok"]
    assert s["commerce"]["tenebrium"] == 20 and s["commerce"]["metalK"] == 30 and suits.has_suit(s)   # 10 Tnb + 10k
    settle_commerce_after_sortie(s, {"resultKey": "k1", "status": "extracted"}, True, True, False, ROOT)
    assert not suits.has_suit(s) and not suits.on_loan(s)                     # back to Cortex
    assert purchase_listing(s, "cortex_commander_suit", ROOT)["ok"]           # same fee, next fight
    assert s["commerce"]["tenebrium"] == 10


def test_a_suit_won_for_good_is_not_returned():
    s = _state()
    suits.grant_suit(s, "armcom", "stolen_koom")
    assert not suits.return_loan(s) and suits.has_suit(s)


def test_a_suit_won_in_the_field_comes_home():
    for how, d in (("queen_rez", "legcom"), ("stolen_koom", "armcom")):
        s = _state()
        out = apply_commander_story(s, {"status": "extracted", "commanderSuit": {"unitDef": d, "how": how}}, [], ROOT)
        assert out["event"] == "unlocked" and suits.suit(s)["unitDef"] == d and suits.suit(s)["how"] == how


def test_in_cortexs_own_suit_cortex_stays_home():
    s = _state()
    suits.grant_suit(s, "armcom", "stolen_koom")
    show = theaters.kings_showdown(suits.SIMMERS, ROOT, "ATS_NW_SHORE", s)
    assert sorted(k["faction"] for k in show["kings"]) == ["armada", "cortex", "nullmercs"]
    assert show["company"]["unitDef"] == "armcom" and not show.get("cortexSitsOut")
    c = _state()
    suits.grant_suit(c, "corcom", "bought_cortex")
    show = theaters.kings_showdown(suits.SIMMERS, ROOT, "ATS_NW_SHORE", c)
    assert sorted(k["faction"] for k in show["kings"]) == ["armada", "nullmercs"] and show["cortexSitsOut"]


def test_sovereignty_waits_on_a_suit():
    s = _state()
    s["missionNumber"] = 99
    s.setdefault("graph", {}).update(pathSignalA=0.2, pathSignalB=0.9, pathSignalC=0.4)
    assert acts.finale_path_for_state(s) == "C"
    suits.grant_suit(s, "legcom", "queen_rez")
    assert acts.finale_path_for_state(s) == "B"


def test_no_commanders_on_tabula_but_koom_keeps_its_suits():
    tab = theaters.standing_war("tabula", ROOT, "TAB_NW_MUSTER") or theaters.standing_war("tabula", ROOT, None)
    assert tab and tab.get("noCommanders") is True
    koom = theaters.standing_war("koom_valley", ROOT, "KV_NW_MUSTER")
    assert koom and not koom.get("noCommanders")
    lua = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_suits.lua").read_text(encoding="utf-8")
    assert '"stolen_koom"' in lua and '"queen_rez"' in lua and "legcom_dead" in lua
