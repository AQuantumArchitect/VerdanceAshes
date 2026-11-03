#!/usr/bin/env python3
"""The three endings can be played to a win (hard-AI campaign runs, 2026-11-02)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_overthrow_has_something_to_break():
    """Finale A's first hard-AI run: VA_OBJECTIVE_KIND kind=destroy_key_structure targets=0. The
    Bastion's standing war replaces the authored citadel, and its Keep seat was booked as war, not as
    the objective, so the finale fell back to holding the Keep with no marks. The seat in the
    objective's zone is the objective now."""
    ps1 = (ROOT / "scripts/build_next_mission_v1.ps1").read_text(encoding="utf-8-sig")
    assert '$isFinale -and $objectiveKind -eq "destroy_key_structure"' in ps1
    assert '[string]$camp.zoneId -eq $targetZoneId' in ps1
    snap = json.loads((ROOT / "data/base_templates/ancient_bastion/war_snapshot_v1.json").read_text(encoding="utf-8-sig"))
    __import__("sys").path.insert(0, str(ROOT / "tools"))
    from verdance.campaign.acts import FINALE_PLANS
    keep = FINALE_PLANS["A"]["objective"]["targetZoneId"]
    assert any(t.get("zoneId") == keep and t.get("faction") == "armada" for t in snap["teams"]), keep
