"""How a met hero turns up (owner, 2026-10-27; continuous 2026-10-28): the chance they come in alive and
against us, like the Kiln, is a logistic in their stance toward the party; it rises over the campaign.
No thresholds."""
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


def test_tension_makes_hostility_likely_and_a_bond_makes_it_rare():
    e = _edge("tension")
    st = _state([e["a"], "ketha"] if e["a"] != "ketha" else ["ketha", "vane"])
    other = e["b"] if e["a"] in st["company"]["core"] else e["a"]
    score, why = E.stance_toward(other, st, ROOT)
    assert score < 0 and any("tension" in w for w in why)
    assert E.p_hostile(score, st, ROOT) > 0.7
    assert E.p_hostile(+1.0, st, ROOT) < 0.01
    assert 0.02 < E.p_hostile(0.0, st, ROOT) < 0.2          # a stranger, now and then


def test_the_curve_is_smooth_and_rises_over_the_campaign():
    early, late = _state(["vane", "ketha"], 2), _state(["vane", "ketha"], 9)
    xs = [x / 10.0 for x in range(-20, 21)]
    ps = [E.p_hostile(x, early, ROOT) for x in xs]
    assert all(a >= b for a, b in zip(ps, ps[1:]))            # monotone: the worse the stance, the likelier
    assert max(abs(a - b) for a, b in zip(ps, ps[1:])) < 0.2  # no cliff anywhere
    assert E.p_hostile(0.0, late, ROOT) > E.p_hostile(0.0, early, ROOT)
    mid = _state(["vane", "ketha"], 5)
    assert E.p_hostile(0.0, early, ROOT) < E.p_hostile(0.0, mid, ROOT) < E.p_hostile(0.0, late, ROOT)


def test_the_roll_is_seeded_and_stamps_the_row():
    e = _edge("tension")
    st = _state([e["a"], "ketha"] if e["a"] != "ketha" else ["ketha", "vane"])
    other = e["b"] if e["a"] in st["company"]["core"] else e["a"]
    a = E.meeting(other, st, ROOT, "greenest_fields")
    assert a == E.meeting(other, st, ROOT, "greenest_fields")
    rows = E.apply_meeting_stance([{"heroId": other, "recruitMode": "wreck_rez", "spawnAsWreck": True}], st, ROOT, "greenest_fields")
    assert rows[0]["stance"]["pHostile"] == a["pHostile"]
    assert (rows[0]["recruitMode"] == "hostile") == (a["roll"] < a["pHostile"])
    assert (rows[0]["spawnAsWreck"] is False) == (rows[0]["recruitMode"] == "hostile")


def test_bonds_are_the_default_meeting_rivals_the_accent():
    r = E.rules(ROOT)["presence"]
    assert float(r["ally"]) > float(r["adversary"]) > 0


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
