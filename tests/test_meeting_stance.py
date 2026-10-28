"""How a met hero turns up (owner, 2026-10-27): tension with the party = alive and against us, like the
Kiln (put them down, raise the wreck); bonded = a wreck to raise; later it takes less tension."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.company import encounters as E  # noqa: E402


def _state(party, mission=2):
    return {"company": {"core": party[:2], "band": party[2:], "joinedLater": []}, "missionNumber": mission}


def _edge(polarity):
    import json
    web = json.loads((ROOT / "data/story/support_web.json").read_text(encoding="utf-8"))
    return next(e for e in web["edges"] if e.get("polarity") == polarity and e.get("authored"))


def test_tension_with_someone_in_the_company_comes_in_hostile():
    e = _edge("tension")
    st = _state([e["a"], "ketha"] if e["a"] != "ketha" else ["ketha", "vane"])
    other = e["b"] if e["a"] in st["company"]["core"] else e["a"]
    score, why = E.stance_toward(other, st, ROOT)
    assert score <= -0.8 and any("tension" in w for w in why)
    rows = E.apply_meeting_stance([{"heroId": other, "recruitMode": "wreck_rez", "spawnAsWreck": True}], st, ROOT)
    assert rows[0]["recruitMode"] == "hostile" and rows[0]["spawnAsWreck"] is False
    assert rows[0]["stance"]["kind"] == "hostile"


def test_a_bond_with_the_company_lies_as_a_wreck_to_raise():
    e = _edge("bond")
    st = _state([e["a"], "ketha"] if e["a"] != "ketha" else ["ketha", "vane"])
    other = e["b"] if e["a"] in st["company"]["core"] else e["a"]
    rows = E.apply_meeting_stance([{"heroId": other, "recruitMode": "wreck_rez", "spawnAsWreck": True}], st, ROOT)
    assert rows[0]["stance"]["kind"] == "wreck" and rows[0]["spawnAsWreck"] is True


def test_later_it_takes_less_tension():
    early, late = _state(["vane", "ketha"], 2), _state(["vane", "ketha"], 9)
    assert E.meeting_kind(-0.5, early, ROOT) == "authored"
    assert E.meeting_kind(-0.5, late, ROOT) == "hostile"
    assert E.meeting_kind(0.0, late, ROOT) == "authored"


def test_who_keeps_their_own_way():
    st = _state(["vane", "ketha"])
    rows = [{"heroId": "consul", "recruitMode": "wreck_rez", "entrance": True},
            {"heroId": "brakhov", "recruitMode": "sortie", "requiresVictory": True},
            {"heroId": "hearth", "recruitMode": "assist_fortify"}]
    out = E.apply_meeting_stance([dict(r) for r in rows], st, ROOT)
    assert all("stance" not in r for r in out)
    assert [r["recruitMode"] for r in out] == ["wreck_rez", "sortie", "assist_fortify"]


def test_the_gadget_spawns_a_non_wreck_recruit_alive_on_the_enemy_team():
    import campaign_lua
    lua = campaign_lua.source()
    assert 'or mode == "wreck_rez" or mode == "retrieve_stash")' in lua      # 'hostile' is neither: alive
    assert 'tryRecruitFieldHero(rec, unitID, "wreck_rez")' in lua               # put down, raised: signs on
