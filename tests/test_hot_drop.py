#!/usr/bin/env python3
"""Hot drop plumbing: the drop line, the drop file, the roster record, the phases."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance_kernel import hot_drop  # noqa: E402


def test_the_drop_line_names_packs_and_reserve():
    assert hot_drop.drop_line("t0k", ["pavise", "halbard"], {"corthud": 3, "armwar": 0}) == "t0k|pavise,halbard|corthud:3"
    assert hot_drop.drop_line("t0k", [], {}) == "t0k||"


def test_arming_clears_a_stale_drop_file_and_disarm_removes_the_token():
    with tempfile.TemporaryDirectory() as td:
        ws, bar = Path(td) / "ws", Path(td) / "bar"
        (ws / "outbox").mkdir(parents=True)
        stale = hot_drop.write_drop(bar, "old|vane|")
        token = hot_drop.arm(ws, bar)
        assert not stale.exists()
        assert json.loads(hot_drop.arm_path(ws).read_text())["token"] == token
        hot_drop.disarm(ws)
        assert not hot_drop.arm_path(ws).exists()


def test_the_roster_record_rewrites_who_went():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "outbox").mkdir()
        p = ws / "outbox" / "next_mission_intent.json"
        p.write_text(json.dumps({"mapId": "x", "deployAces": ["ketha", "pavise", "halbard"], "crewBand": ["pavise", "halbard"]}))
        hot_drop.record_roster(ws, ["pavise"], ["ketha", "pavise"])
        d = json.loads(p.read_text())
        assert d["crewBand"] == ["pavise"] and d["deployAces"] == ["ketha", "pavise"] and d["mapId"] == "x"


def test_phases():
    assert hot_drop.status_of(None, "in-game")["phase"] == "none"
    hot = {"token": "t", "dropped": False}
    assert hot_drop.status_of(hot, "launching")["phase"] == "loading"
    assert hot_drop.status_of(hot, "in-game")["phase"] == "ready"
    assert hot_drop.status_of(hot, "closed-without-result")["phase"] == "closed"
    hot["dropped"] = True
    assert hot_drop.status_of(hot, "in-game")["phase"] == "dropped"
    assert hot_drop.status_of(hot, "home")["phase"] == "none"
