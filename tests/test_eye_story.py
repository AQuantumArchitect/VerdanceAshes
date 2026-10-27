"""The Eye of Horus: the glassed crater, its Armada scouts, and who hires the company there."""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import eye_story as E, war_snapshot as W, theaters  # noqa: E402


def test_whoever_thinks_better_of_the_company_hires_it():
    assert E.patron({"reputation": {"cortex": 70, "armada": 18}}) == "cortex"
    assert E.patron({"reputation": {"cortex": 30, "armada": 55}}) == "armada"
    assert E.patron({"reputation": {"cortex": 40, "armada": 40}}) == "cortex"
    assert E.objective(E.story({"reputation": {"cortex": 70, "armada": 18}}, None))["kind"] == "hunt_scouts"
    raze = E.objective(E.story({"reputation": {"cortex": 1, "armada": 99}}, None))
    assert raze["kind"] == "raze_camp" and raze["enemyFaction"] == "cortex"


def test_scouts_come_from_the_corners_the_company_did_not_land_in():
    nw = E.CORNERS[0]
    parties = E.scout_parties((nw[1], nw[2]))
    assert len(parties) == 3 and nw[0] not in {p["zoneId"] for p in parties}
    assert [p["arriveSeconds"] for p in parties] == sorted(p["arriveSeconds"] for p in parties)
    assert parties[0]["arriveSeconds"] >= 120
    for p in parties:
        defs = {u["unitDefName"] for u in p["units"]}
        assert "armck" in defs and not any("com" in d for d in defs)  # constructors, no commander suits


def test_the_bake_is_armada_corners_round_a_cortex_crater_and_missions_keep_only_cortex():
    rec = W.load_recipe(ROOT, "eye_of_horus")
    sides = {t["key"]: rec["sides"][t["ally"]]["faction"] for t in rec["teams"]}
    assert sorted(sides.values()) == ["armada"] * 4 + ["cortex"] * 4
    assert rec["fieldSides"] == ["crater"]
    assert {c["faction"] for c in theaters.WARS["eye_of_horus"]} == {"cortex"}
    mx, mz = rec["mapSize"]
    for t in rec["teams"]:
        x, z = t["startElmos"][0] / mx, t["startElmos"][1] / mz
        if sides[t["key"]] == "armada":
            assert min(x, 1 - x) < 0.2 and min(z, 1 - z) < 0.2, t["key"]       # a corner
        else:
            assert math.hypot(x - 0.5, z - 0.5) < 0.2, t["key"]                # the crater


def test_a_baked_eye_fields_only_the_camp_but_keeps_everyones_wrecks():
    snap = W.load_snapshot(ROOT, "eye_of_horus")
    if not snap or snap["teams"][0]["key"] != "c_n":
        return  # the new history is not baked yet
    assert {t["faction"] for t in snap["teams"]} == {"cortex"}
    assert any(w[0].startswith("arm") for w in snap.get("wrecks") or [])


def test_hunting_scouts_for_cortex_warms_cortex_and_razing_the_camp_burns_it():
    from verdance.campaign.progression import apply_reputation_companion
    hunt = {"reputation": {"cortex": 70, "armada": 18}}
    apply_reputation_companion(hunt, {"status": "victory", "mapId": "eye_of_horus", "against": "armada",
                                      "destroyedObjectiveIds": ["EOH_STOP_THE_SCOUTS"]}, 10)
    assert hunt["reputation"]["cortex"] > 70 and hunt["reputation"]["armada"] <= 18
    raze = {"reputation": {"cortex": 70, "armada": 18}}
    apply_reputation_companion(raze, {"status": "victory", "mapId": "eye_of_horus", "against": "cortex",
                                      "destroyedObjectiveIds": ["EOH_WIPE_THE_CAMP"]}, 10)
    assert raze["reputation"]["cortex"] < 70
