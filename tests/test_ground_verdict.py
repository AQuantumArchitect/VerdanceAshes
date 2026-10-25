#!/usr/bin/env python3
"""A sortie is won by the ground the company holds when it lifts, not by one fixed checkbox.

  * the primary objective done, OR ground taken from an enemy and still held (claim presence);
  * nobody stranded: a hero left on ground the company holds is a garrison, not an abandonment.

Built from the Ancient Bastion run where the Keep fell and eight heroes stayed to hold it while the
assigned fortify target stood 12 of 18 done: the old reading scored it a partial."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine  # noqa: E402
from verdance.belief import manifest  # noqa: E402
from verdance.hub.contract import normalize_result  # noqa: E402

KEEP, TOR, HEIGHTS = "AB_W_KEEP", "AB_NW_TOR", "AB_NE_HEIGHTS"


def _result(**over):
    r = {
        "missionId": "va_009", "missionNumber": 9, "campaignId": "verdance_ashes",
        "status": "extracted", "terminalReason": "extracted", "mapId": "ancient_bastion",
        "deploymentMapId": "ancient_bastion", "deploymentZoneId": HEIGHTS, "targetZoneId": TOR,
        "extractionZoneId": HEIGHTS, "patron": "nullmercs", "elapsedMinutes": 9.4, "frame": 16981,
        "resultKey": "verdance_ashes|va_009|9|ch1|extracted|extracted|f16981",
        "objectiveKind": "fortify_zone", "objectiveComplete": False,
        "manifest": {
            "schema": "verdance-manifest/1", "kind": "extracted", "destination": "home",
            "going": {"heroes": [{"heroId": "solarium"}], "unitCount": 6},
            "staying": {"heroes": [{"heroId": "fatboy", "zoneId": KEEP}, {"heroId": "grath", "zoneId": KEEP}]},
            "dropped": ["solarium", "fatboy", "grath"], "enemyOnPad": 0, "objectiveComplete": False,
        },
        "zoneDv": {KEEP: {"ashwalkers": 13040}, HEIGHTS: {"ashwalkers": 4836, "nullmercs": 1085},
                   "AB_SE_CRATERS": {"armada": 5385, "ashwalkers": 73}},
        "playerSurvivors": {"armpeep": 3},
    }
    r.update(over)
    return r


def _state(before=("armada",)):
    s = engine.default_v1_state()
    s["zoneMemory"] = {"ancient_bastion": {
        KEEP: {"controllingFaction": before[0], "abstract": {"control": before[0]}},
        TOR: {"controllingFaction": "armada", "abstract": {"control": "armada"}},
        HEIGHTS: {"controllingFaction": "nullmercs", "abstract": {"control": "nullmercs"}},
    }}
    return s


def test_the_keep_taken_and_garrisoned_is_a_victory_though_the_target_stands_undone():
    r = manifest.with_ground(_state(), _result(), ROOT)
    assert r["groundHeld"] == [HEIGHTS, KEEP] and r["groundTaken"] == [KEEP]
    assert manifest.stranded(r, ROOT) == []
    assert manifest.verdict_from(r) == "victory"
    n = normalize_result(r)
    assert n["verdict"] == "victory" and n["objectiveComplete"] is True
    assert n["objectiveCompleteHow"] == "ground_taken" and n["groundTaken"] == [KEEP]


def test_heroes_left_on_ground_the_company_does_not_hold_are_stranded():
    r = _result()
    r["manifest"]["staying"]["heroes"].append({"heroId": "quill", "zoneId": "AB_SE_CRATERS"})
    r = manifest.with_ground(_state(), r, ROOT)
    assert manifest.stranded(r, ROOT) == ["quill"]
    assert manifest.verdict_from(r) == "partial"


def test_ground_that_was_nobodys_enemy_is_not_a_conquest():
    r = manifest.with_ground(_state(before=("neutral",)), _result(), ROOT)
    assert r["groundHeld"] and r["groundTaken"] == []
    assert manifest.verdict_from(r) == "partial"


def test_presence_below_the_claim_holds_nothing():
    r = _result(zoneDv={KEEP: {"ashwalkers": 200}})
    r = manifest.with_ground(_state(), r, ROOT)
    assert r["groundHeld"] == [] and manifest.verdict_from(r) == "partial"
    assert manifest.stranded(r, ROOT) == ["fatboy", "grath"]


def test_the_objective_done_with_a_garrison_on_held_ground_is_a_victory_now():
    r = _result()
    r["manifest"]["objectiveComplete"] = True
    r = manifest.with_ground(_state(before=("neutral",)), r, ROOT)
    assert r["groundTaken"] == [] and manifest.verdict_from(r) == "victory"


def test_a_result_with_no_ground_facts_keeps_the_old_reading():
    r = _result()
    r.pop("zoneDv")
    assert manifest.stranded(r) == ["fatboy", "grath"]
    assert manifest.verdict_from(r) == "partial"
    r["manifest"]["objectiveComplete"] = True
    assert manifest.verdict_from(r) == "partial"       # still two people left, nowhere known to hold


def test_a_kings_showdown_is_the_throne_alone():
    r = _result(kings=[{"faction": "ashwalkers", "fallen": False}, {"faction": "armada", "fallen": False}])
    r = manifest.with_ground(_state(), r, ROOT)
    assert r["groundTaken"] == [] and manifest.verdict_from(r) == "partial"


def test_the_campaign_scores_the_ground_win_and_does_not_hand_the_target_away():
    state = _state()
    state["fieldPool"] = {"brakhov": {"heroId": "brakhov", "name": "Brakhov the Kiln", "unitDef": "leginc", "status": "wild",
                                      "home": ["ancient_bastion", KEEP],
                                      "recruit": {"type": "sortie", "requiresVictory": True, "mapId": "ancient_bastion", "zoneId": KEEP}}}
    state["company"] = {"sealed": True, "core": ["ketha"], "band": ["solarium"], "you": "solarium", "joinedLater": [], "seatCap": 3}
    r = _result(recruitedHeroIds=["brakhov"])
    state2, report, _, _ = engine.process_result(copy.deepcopy(state), r, None, ROOT, None)
    assert report.get("verdict") == "victory"
    bead = state2["history"][-1]
    assert bead["verdict"] == "victory" and "ground-taken" in bead["storyTags"] and bead["groundTaken"] == [KEEP]
    zm = state2["zoneMemory"]["ancient_bastion"]
    assert zm[KEEP]["controllingFaction"] == "ashwalkers"
    assert zm[TOR]["controllingFaction"] != "nullmercs"      # the assigned target is not handed to the patron
    assert state2["fieldPool"]["brakhov"]["status"] == "recruited"      # a win that needs a win recruits


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
