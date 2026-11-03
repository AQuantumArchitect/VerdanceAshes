#!/usr/bin/env python3
"""The first match on a stock BAR, from the hub to the first objective (issue #4, 2026-11-02).

Three places a new player stalled, from the stock-BAR rehearsal and a walk through a fresh hub:
  * the hold never started: the company's allies counted against its claim (test_claim_and_headcount)
  * the job card sent the player to the wrong zone, and "To win" named a job the game does not run
  * a stopped hold clock and a failed Drop gave no reason (the HUD harness has the clock's words)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine  # noqa: E402
from verdance.campaign import sorties  # noqa: E402
from verdance.readings.narrative import TAKE_ZONE, operation_summary  # noqa: E402


def test_the_opening_card_names_the_zone_the_game_marks():
    """The opening's target is the Northwest Bastion (Luke, 2026-10-25); the card still said the
    southeast plateau and promised the Koom Valley road."""
    choice = sorties.opening_hub_choice(engine.default_v1_state(), ROOT)
    assert choice["effect"]["preferredCaptureZoneId"] == sorties.OPENING_TARGET == "GF_NW_BASTION"
    assert "Northwest Bastion" in choice["blurb"]
    assert "southeast plateau" not in choice["blurb"].lower() and "Koom" not in choice["blurb"]
    assert "decoy's" not in choice["blurb"]


def test_to_win_says_what_the_game_checks():
    """Every contract with a target zone runs as a capture of that zone (as_territory_capture). The
    opening raid's card said "Destroy the required raid targets" while the HUD asked to clear and hold."""
    opening = operation_summary(sorties.opening_hub_choice(engine.default_v1_state(), ROOT))
    assert opening["kind"] == "eco_raid" and opening["required"] == TAKE_ZONE
    assert "1,500" in TAKE_ZONE and "three times" in TAKE_ZONE
    kept = operation_summary({"effect": {"objectiveArchetype": "kings_showdown", "targetZoneId": "ATS_THRONE"}})
    assert kept["required"].startswith("Be the last commander standing")
    no_zone = operation_summary({"effect": {"objectiveArchetype": "eco_raid"}})
    assert no_zone["required"].startswith("Destroy the required raid targets")


def test_a_failed_mod_sync_says_why():
    """The Drop's "mod sync failed" carried no reason; on a stock BAR the installer's first error
    line is the one thing the player can act on."""
    from verdance_kernel.api import _mod_sync_reason
    rep = {"ok": False, "stderr_tail": "\n  BAR data folder 'C:\\x' has no engine\\ folder.\nCategoryInfo : ..."}
    assert _mod_sync_reason(rep) == "mod sync failed: BAR data folder 'C:\\x' has no engine\\ folder."
    assert _mod_sync_reason({"ok": False}).startswith("mod sync failed: the installer gave no reason")


def test_the_stopped_hold_clock_says_why():
    sidebar = (ROOT / "mod/VerdanceAshes.sdd/luaui/Widgets/gui_verdance_sidebar.lua").read_text(encoding="utf-8")
    assert '" · waiting for presence"' in sidebar and '" · contested"' in sidebar
    harness = (ROOT / "tools/hud_harness/harness.py").read_text(encoding="utf-8")
    assert "hold 0s / 30s · waiting for presence" in harness
