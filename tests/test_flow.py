"""The field and its descent (verdance.world.flow): chains end at a stronghold, bakes stay in range."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verdance.world import flow as F  # noqa: E402

WAR_MAPS = sorted(p.parent.name for p in (ROOT / "data" / "base_templates").glob("*/war_recipe.json"))


def test_every_war_map_has_a_chain_that_ends_at_a_stronghold():
    for m in WAR_MAPS:
        rep = F.report(m, ROOT)
        assert rep.get("chains"), m
        for side, steps in rep["chains"].items():
            assert steps and steps[-1]["kind"] == "stronghold", (m, side, steps)
            ids = [s["zoneId"] for s in steps]
            assert len(ids) == len(set(ids)), (m, side, ids)
            for a, b in zip(ids, ids[1:]):
                assert b in rep["adjacency"][a], (m, a, b)


def test_bake_plan_stays_in_range_and_keeps_profiles():
    for m in WAR_MAPS:
        b = F.report(m, ROOT)["bake"]
        assert 10 <= b["minutes"] <= 30, (m, b["minutes"])
        for s in b["seats"]:
            assert -5 <= s["handicap"] <= 30
            assert s["profile"] == b["was"]["profiles"][s["key"]]


def test_richer_steeper_maps_bake_longer():
    gf = F.report("greenest_fields", ROOT)["bake"]["minutes"]
    ab = F.report("ancient_bastion", ROOT)["bake"]["minutes"]
    assert ab > gf


def test_chains_switchback_in_stages_and_never_climb_out():
    staged = 0
    for m in WAR_MAPS:
        rep = F.report(m, ROOT)
        for side, steps in rep["chains"].items():
            rings = [s["ring"] for s in steps]
            assert all(b in (a, a - 1) for a, b in zip(rings, rings[1:])), (m, side, rings)
            staged += len(steps) >= 4
    assert staged >= 3  # most wars take four or more sorties now, not a dive straight in


def test_straight_dive_is_still_available():
    for s in F.report("greenest_fields", ROOT, stages=0)["chains"].values():
        assert len(s) <= 3
