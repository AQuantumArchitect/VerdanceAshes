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
    # ...its guns and its factories, not all 66 structures of the seat (the second run broke 10 of 66
    # in 33 minutes, most of them windmills and extractors)
    assert '$force.book = "guns_and_command"' in ps1
    # ...and the installer's whitelist carries it into the seed (the first try booked all 66 again)
    slice_ps1 = (ROOT / "scripts/install_playable_slice.ps1").read_text(encoding="utf-8-sig")
    assert "$expanded.book = [string]$force.book" in slice_ps1
    spawn = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/campaign/spawn.lua").read_text(encoding="utf-8")
    assert 'force.book == "guns_and_command"' in spawn and "canFight(defID) or (ud and ud.isFactory)" in spawn
    snap = json.loads((ROOT / "data/base_templates/ancient_bastion/war_snapshot_v1.json").read_text(encoding="utf-8-sig"))
    __import__("sys").path.insert(0, str(ROOT / "tools"))
    from verdance.campaign.acts import FINALE_PLANS
    keep = FINALE_PLANS["A"]["objective"]["targetZoneId"]
    assert any(t.get("zoneId") == keep and t.get("faction") == "armada" for t in snap["teams"]), keep


def test_a_finale_is_won_by_its_own_objective_not_by_ground():
    """The first hard-AI campaign completed on the Overthrow by taking AB_NE_CRATERS (ground taken)
    with the objective incomplete. The ground rule is for ordinary sorties."""
    from verdance.belief import manifest
    state = {"zoneMemory": {"ancient_bastion": {"AB_NE_CRATERS": {"controllingFaction": "armada"}}}}
    base = {"deploymentMapId": "ancient_bastion", "zoneDv": {"AB_NE_CRATERS": {"ashwalkers": 4000}},
            "manifest": {"schema": "verdance-manifest/1", "kind": "extracted", "objectiveComplete": False}}
    sortie = dict(base, objectiveResults=[{"objectiveId": "GF_X", "status": "incomplete"}])
    assert manifest.ground_taken(state, sortie) == ["AB_NE_CRATERS"]
    finale = dict(base, objectiveResults=[{"objectiveId": "FINALE_OVERTHROW", "status": "incomplete"}])
    assert manifest.ground_taken(state, finale) == []
    assert manifest.verdict_from(manifest.with_ground(state, finale)) == "partial"
