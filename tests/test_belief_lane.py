#!/usr/bin/env python3
"""The belief lane, unit by unit.

Facts in, meaning out — and never a truth read. Four seams:

  verdance.belief.manifest.verdict_from        the gadget's terminal facts become a verdict word
  verdance.belief.hub_belief.belief_surface    the belief frame becomes the hub's painted zones
  verdance.hub.stamp_deploy_plan               pad legality is judged on belief, not zoneMemory
  verdance.belief.intel_lua.intel_to_lua       the Drop carries the believed holder into BAR

Plain ``test_*`` functions; ``python3 tests/run_tests.py belief`` runs them.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.belief import hub_belief, intel_lua, manifest  # noqa: E402
from verdance.hub import stamp_deploy_plan as stamp  # noqa: E402

MAP = "greenest_fields"
PAD = "GF_NE_PLATEAU"          # authored quiet rim pad (edge score 0.22)
MID = "GF_C_GATE"              # midfield (edge score 0.40)


# --------------------------------------------------------------------------- manifest

def _result(kind: str, *, objective: bool = True, staying: list | None = None) -> dict:
    return {
        "status": kind,
        "manifest": {
            "schema": "verdance-manifest/1",
            "kind": kind,
            "destination": "home",
            "going": {"heroes": [{"heroId": "pavise"}]},
            "staying": {"heroes": [{"heroId": h} for h in (staying or [])]},
            "enemyOnPad": 0,
            "objectiveComplete": objective,
        },
    }


def test_manifest_extracted_complete_nobody_left_is_victory():
    assert manifest.verdict_from(_result("extracted")) == "victory"


def test_manifest_extracted_with_a_hero_left_is_partial():
    r = _result("extracted", staying=["ketha"])
    assert manifest.heroes_left(r) == ["ketha"]
    assert manifest.verdict_from(r) == "partial"


def test_manifest_extracted_objective_undone_is_partial():
    assert manifest.verdict_from(_result("extracted", objective=False)) == "partial"


def test_manifest_wiped_is_defeat():
    assert manifest.verdict_from(_result("wiped")) == "defeat"


def test_manifest_closed_is_abandon():
    assert manifest.verdict_from(_result("closed")) == "abandon"


def test_manifest_contested_pad_reads_from_enemy_on_pad():
    r = _result("extracted")
    assert manifest.extraction_status_from(r) == "clean"
    r["manifest"]["enemyOnPad"] = 3
    assert manifest.extraction_status_from(r) == "contested"


def test_manifest_legacy_result_without_manifest_keeps_its_own_status():
    assert manifest.verdict_from({"status": "victory"}) is None
    assert manifest.verdict_from({"status": "extracted"}) == "partial"


# --------------------------------------------------------------------------- hub belief

def _ws_with_frame(nodes: list | None) -> Path:
    ws = Path(tempfile.mkdtemp(prefix="va_belief_"))
    (ws / "outbox").mkdir()
    if nodes is not None:
        (ws / "outbox" / "intel.latest.json").write_text(json.dumps({
            "schema": "verdance-intel/1", "as_of_minute": 120.0, "nodes": nodes, "surprise": {"top": []},
        }), encoding="utf-8")
    return ws


def _state() -> dict:
    return {"zoneMemory": {MAP: {PAD: {"label": "Northeast Plateau"}, MID: {"label": "Central Gate"}}}}


def test_belief_surface_frame_row_held_by_a_faction():
    ws = _ws_with_frame([
        {"node": MID, "role": "held", "value": 0.9, "confidence": 0.7, "state": "current",
         "age_min": 0.0, "source": "drop:m1", "faction": "armada", "mapId": MAP, "label": "Central Gate"},
    ])
    surf = hub_belief.belief_surface(ws, _state(), MAP)
    row = surf["zones"][MID]
    assert surf["source"] == "intel.latest.json"
    assert row["believed"] == "held"
    assert row["faction"] == "armada"
    assert abs(row["confidence"] - 0.7) < 1e-9
    assert row["state"] == "current"
    assert hub_belief.believed_holder(row) == "armada"


def test_belief_surface_no_frame_is_dark_everywhere():
    ws = _ws_with_frame(None)
    surf = hub_belief.belief_surface(ws, _state(), MAP)
    assert surf["source"] == "none"
    assert set(surf["zones"]) == {PAD, MID}
    for row in surf["zones"].values():
        assert row["believed"] == "dark"
        assert row["confidence"] == 0.0
        assert row["faction"] is None
    assert surf["counts"]["dark"] == 2
    assert hub_belief.believed_holder(surf["zones"][PAD]) == "unknown"


def test_belief_surface_ours_row_is_ashwalkers():
    ws = _ws_with_frame([
        {"node": PAD, "role": "ours", "value": 0.95, "confidence": 0.8, "state": "current",
         "age_min": 0.0, "source": "drop:m1", "mapId": MAP, "label": "Northeast Plateau"},
    ])
    row = hub_belief.belief_surface(ws, _state(), MAP)["zones"][PAD]
    assert row["believed"] == "ours"
    assert row["faction"] == "ashwalkers"
    assert hub_belief.believed_ours(ws, _state()) == {PAD}


def test_belief_surface_never_reads_controlling_faction():
    # The truth says armada; the company has not looked. The board stays dark.
    ws = _ws_with_frame(None)
    st = {"zoneMemory": {MAP: {MID: {"controllingFaction": "armada", "abstract": {"control": "armada"}}}}}
    row = hub_belief.belief_surface(ws, st, MAP)["zones"][MID]
    assert row["believed"] == "dark"
    assert row["faction"] is None


# --------------------------------------------------------------------------- stamp legality

def _ws_for_stamp(nodes: list | None) -> Path:
    ws = _ws_with_frame(nodes)
    dst = ws / "data" / "zone_maps" / "authored"
    dst.mkdir(parents=True)
    src = ROOT / "data" / "zone_maps" / "authored" / f"{MAP}.authored.zone_map.json"
    shutil.copy2(src, dst / src.name)
    return ws


def _plan(pad: str) -> dict:
    return stamp.normalize_plan({"mapId": MAP, "marks": {"deployZoneId": pad, "captureZoneIds": [MID]}})


def _lz_warnings(ws: Path, pad: str) -> list[str]:
    return [w for w in stamp.soft_validate(_plan(pad), ws, _state()) if w.startswith("LZ_")]


def test_stamp_believed_ours_is_legal_even_midfield():
    ws = _ws_for_stamp([
        {"node": MID, "role": "ours", "value": 0.95, "confidence": 0.8, "state": "current",
         "age_min": 0.0, "source": "drop:m1", "mapId": MAP, "label": "Central Gate"},
    ])
    assert _lz_warnings(ws, MID) == []


def test_stamp_believed_held_is_illegal_with_the_sentence():
    ws = _ws_for_stamp([
        {"node": PAD, "role": "held", "value": 0.9, "confidence": 0.7, "state": "current",
         "age_min": 0.0, "source": "drop:m1", "faction": "armada", "mapId": MAP, "label": "Northeast Plateau"},
    ])
    warns = _lz_warnings(ws, PAD)
    assert len(warns) == 1, warns
    assert warns[0].startswith(f"LZ_DEPLOY: {PAD} illegal (believed held by armada (70%))"), warns[0]
    assert warns[0].endswith("a pad is ground we believe is ours, or a door we hold")


def test_stamp_open_ground_is_never_a_pad():
    # Believed empty, or nobody has looked: open ground either way, rim or midfield.
    ws = _ws_for_stamp([
        {"node": PAD, "role": "held", "value": 0.1, "confidence": 0.6, "state": "current",
         "age_min": 0.0, "source": "drop:m1", "mapId": MAP, "label": "Northeast Plateau"},
    ])
    warns = _lz_warnings(ws, PAD)
    assert len(warns) == 1 and "believed empty, not ours" in warns[0], warns
    ws = _ws_for_stamp([])
    warns = _lz_warnings(ws, MID)
    assert len(warns) == 1 and "nobody has looked; not ours" in warns[0], warns


def test_stamp_a_held_door_is_a_pad():
    ws = _ws_for_stamp([])
    state = dict(_state(), doors={"GF_NW_MUSTER": {"held": True, "mapId": MAP}})
    warns = [w for w in stamp.soft_validate(_plan("GF_NW_MUSTER"), ws, state) if w.startswith("LZ_")]
    assert warns == [], warns


# --------------------------------------------------------------------------- intel → Lua

def test_intel_to_lua_carries_the_faction():
    intel = {
        "schema": "verdance-intent-intel/0.1", "perspective": "company", "mapId": MAP, "asOfMinute": 120.0,
        "zones": {
            MID: {"label": "Central Gate",
                  "held": {"value": 0.9, "confidence": 0.7, "state": "current", "age_min": 0.0,
                           "source": "drop:m1", "faction": "armada"},
                  "ours": {"value": 0.05, "confidence": 0.7, "state": "current", "age_min": 0.0, "source": "drop:m1"}},
            PAD: {"label": "Northeast Plateau",
                  "held": {"value": None, "confidence": 0.0, "state": "dark", "age_min": None, "source": None}},
        },
    }
    lua = intel_lua.intel_to_lua(intel)
    assert lua.startswith("-- GENERATED")
    assert "return {" in lua
    assert 'faction = "armada"' in lua
    assert 'perspective = "company"' in lua
    # a value nobody measured renders nil, never zero
    pad_block = lua[lua.index(PAD):]
    assert "v = nil" in pad_block
    assert 'state = "dark"' in pad_block
    assert "controllingFaction" not in lua


def test_intel_to_lua_is_loadable_lua_shaped():
    lua = intel_lua.intel_to_lua({"zones": {}})
    body = lua.split("return ", 1)[1]
    assert body.count("{") == body.count("}")
