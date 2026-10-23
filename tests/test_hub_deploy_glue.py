"""Tests for hub deploy stamp + contract v2 hub field preservation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from verdance.hub.contract import normalize_sortie, sortie_v2_to_v1_order
from verdance.hub.stamp_deploy_plan import normalize_plan, plan_to_sortie, stamp


def test_normalize_plan_marks():
    raw = {
        "mapId": "greenest_fields",
        "contractKind": "eco_raid",
        "deployAces": ["vane", "ketha"],
        "choiceId": "c1",
        "marks": {
            "deployZoneId": "GF_NW_MUSTER",
            "extractZoneId": "GF_NW_MUSTER",
            "captureZoneIds": ["GF_SE_PLATEAU", "GF_NE_PLATEAU"],
        },
    }
    p = normalize_plan(raw)
    assert p["mapId"] == "greenest_fields"
    assert p["marks"]["captureZoneIds"][0] == "GF_SE_PLATEAU"
    assert len(p["marks"]["captureZoneIds"]) == 2


def test_plan_to_sortie_secondary():
    plan = normalize_plan({
        "mapId": "greenest_fields",
        "contractKind": "eco_raid",
        "choiceId": "c_multi",
        "deployAces": ["vane"],
        "marks": {
            "deployZoneId": "D",
            "extractZoneId": "E",
            "captureZoneIds": ["A", "B"],
        },
    })
    s = plan_to_sortie(plan, {})
    assert s["targetZoneId"] == "A"
    assert s["secondaryCaptureZoneIds"] == ["B"]
    assert s["deploymentZoneId"] == "D"
    # pass six: raiders land and lift from the same pad; the extract mark is accepted, not honoured
    assert s["extractionZoneId"] == "D"
    assert s["hubChoiceId"] == "c_multi"
    assert s["deployAces"] == ["vane"]
    assert s["valid"] is True


def test_contract_v2_preserves_hub_fields():
    raw = {
        "mapId": "koom_valley",
        "targetZoneId": "KOOM_CENTRAL_FLUID_SCAR",
        "deploymentZoneId": "KOOM_NW_GREEN_SHELF",
        "extractionZoneId": "KOOM_NW_GREEN_SHELF",
        "captureZoneIds": ["KOOM_CENTRAL_FLUID_SCAR", "KOOM_EAST_RIDGE_POCKET"],
        "hubChoiceId": "c_hub",
        "deployAces": ["vane", "ketha"],
        "patron": "nullmercs",
        "against": "armada",
        "objectiveArchetype": "seize_lane",
    }
    v1 = sortie_v2_to_v1_order(normalize_sortie(raw))
    assert v1["deploymentZoneId"] == "KOOM_NW_GREEN_SHELF"
    assert v1["extractionZoneId"] == "KOOM_NW_GREEN_SHELF"
    assert v1["hubChoiceId"] == "c_hub"
    assert v1["deployAces"] == ["vane", "ketha"]
    assert v1["secondaryCaptureZoneIds"] == ["KOOM_EAST_RIDGE_POCKET"]
    assert "KOOM_CENTRAL_FLUID_SCAR" in v1["captureZoneIds"]


def test_stamp_writes_outbox(tmp_path: Path | None = None):
    # Use real workspace outbox (idempotent) if available
    ws = ROOT
    if not (ws / "state" / "campaign_state.json").is_file():
        return
    plan = {
        "mapId": "greenest_fields",
        "contractKind": "eco_raid",
        "choiceId": "c_test_pytest",
        "deployAces": ["vane", "ketha"],
        "sessionMode": "same_map",
        "marks": {
            # Live campaign_state may paint NW muster as Armada; use an
            # Ashwalker-held rim pad so the LZ rule is what we exercise.
            "deployZoneId": "GF_S_PLATEAU",
            "extractZoneId": "GF_S_PLATEAU",
            "captureZoneIds": ["GF_SE_PLATEAU"],
        },
    }
    report = stamp(plan, ws)
    assert report["ok"] is True, report
    assert report["hubChoiceId"] == "c_test_pytest"
    order = json.loads((ws / "outbox" / "next_sortie_order.json").read_text(encoding="utf-8-sig"))
    assert order["hubChoiceId"] == "c_test_pytest"
    assert order["targetZoneId"] == "GF_SE_PLATEAU"
    assert order["deploymentZoneId"] == "GF_S_PLATEAU"
    assert order["source"] == "hub_deploy_plan"
    assert order["sessionMode"] == "same_map"
    home = json.loads((ws / "outbox" / "session_home.latest.json").read_text(encoding="utf-8-sig"))
    assert home["sessionHomeMap"] == "greenest_fields"


def test_consume_played_hub_sorties():
    from verdance.campaign import consume_played_hub_sorties, save_json

    import tempfile
    import shutil

    td = Path(tempfile.mkdtemp())
    try:
        out = td / "outbox"
        out.mkdir()
        hub_order = {
            "mapId": "greenest_fields",
            "targetZoneId": "GF_SE_ENERGY_WORKS",
            "hubChoiceId": "c1",
            "source": "hub_deploy_plan",
        }
        debrief = {
            "mapId": "greenest_fields",
            "targetZoneId": "GF_NORTH_DESERT_EDGE",
            "source": "debrief",
            "fromDebrief": True,
        }
        save_json(out / "next_sortie_order.json", hub_order)
        save_json(out / "next_sortie_choice.json", debrief)
        report = consume_played_hub_sorties(
            td,
            {"mapId": "greenest_fields", "targetZoneId": "GF_SE_ENERGY_WORKS"},
            "greenest_fields",
        )
        assert "next_sortie_order.json" in report["cleared"]
        assert not (out / "next_sortie_order.json").is_file()
        assert (out / "next_sortie_choice.json").is_file()  # debrief kept
        assert any(k.get("reason") == "debrief_pick" for k in report["kept"])
    finally:
        shutil.rmtree(td, ignore_errors=True)


