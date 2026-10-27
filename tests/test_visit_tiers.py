"""Visit tiers: a field ranks up each time the company fights on it (verdance.world.visit_tiers)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import visit_tiers as V, war_snapshot as W, theaters  # noqa: E402
from verdance.campaign import engine  # noqa: E402


def _state(*maps):
    return {"history": [{"mapId": m} for m in maps]}


def test_first_second_and_every_later_visit():
    assert V.tier_for(_state(), "greenest_fields") == 1
    assert V.tier_for(_state("greenest_fields"), "greenest_fields") == 2
    assert V.tier_for(_state(*["greenest_fields"] * 5), "greenest_fields") == 3
    # visits elsewhere do not count
    assert V.tier_for(_state("tabula", "koom_valley"), "greenest_fields") == 1


def test_the_bastion_and_the_kings_do_not_rank_up():
    many = _state(*["ancient_bastion"] * 4 + ["all_that_simmers"] * 4)
    assert V.tier_for(many, "ancient_bastion") == 1
    assert V.tier_for(many, "all_that_simmers") == 1


def test_raptor_pace_shortens_then_starts_late():
    paces = [V.plan(_state(*["the_rock_jungle"] * n), "the_rock_jungle")["raptor"] for n in (0, 1, 2)]
    assert paces[0] == {"graceSeconds": 600, "clockSeconds": 0}
    assert paces[1]["graceSeconds"] <= 1 and paces[1]["clockSeconds"] == 0
    assert paces[2]["clockSeconds"] == 1800
    assert "raptor" not in V.plan(_state(), "greenest_fields")


def test_greenest_wardens_take_real_pockets_one_then_two():
    pockets = engine._shell_pockets("greenest_fields", ROOT)
    assert pockets, "no Greenest shell template"
    ids = {p["pocketId"] for p in pockets}
    assert "wardens" not in V.plan(_state(), "greenest_fields", pockets)
    two = V.plan(_state("greenest_fields"), "greenest_fields", pockets)["wardens"]
    three = V.plan(_state("greenest_fields", "greenest_fields"), "greenest_fields", pockets)["wardens"]
    assert len(two) == 1 and len(three) == 2
    assert all(w["pocketId"] in ids and 0 < w["x"] < 1 and 0 < w["z"] < 1 for w in three)


def test_a_tier_recipe_adds_its_seats_and_keeps_the_company_seat():
    for m in W.war_maps(ROOT):
        rec = W.load_recipe(ROOT, m)
        mx, mz = rec["mapSize"]
        for tier in (1, 2, 3):
            r = W.recipe_for_tier(rec, tier)
            keys = [t["key"] for t in r["teams"]]
            assert len(keys) == len(set(keys)), (m, tier)
            pad = next(t for t in r["teams"] if t["key"] == rec["playerSeat"])
            assert pad["profile"] == "hard_aggressive", (m, tier)
            for t in r["teams"]:
                x, z = t["startElmos"]
                assert 0 < x < mx and 0 < z < mz, (m, tier, t["key"])
        # every seat a tier can add is in the war table, so the theater can field it
        table = {s["key"] for s in theaters.WARS[m]}
        fielded = rec.get("fieldSides") or list(rec["sides"])
        keys = {t["key"] for t in rec["teams"] if t["ally"] in fielded} | \
            {t["key"] for over in (rec.get("tiers") or {}).values() for t in over.get("addTeams") or [] if t["ally"] in fielded}
        assert keys - {rec["playerSeat"]} <= table, m


def test_a_tier_not_baked_falls_back_to_the_one_below():
    for m in W.war_maps(ROOT):
        base = W.load_snapshot(ROOT, m, 1)
        if base:
            got = W.load_snapshot(ROOT, m, 3)
            assert got is not None and int(got.get("tier") or 1) <= 3
