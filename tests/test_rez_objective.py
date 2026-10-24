#!/usr/bin/env python3
"""A field recruit's wreck lying in the wound is the sortie's objective: the builder names that hero
(objective.rezHeroId) and the campaign gadget completes the objective only when they are raised."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if Path("/opt/pwsh/pwsh").exists() else None)
GADGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"


def _pick(recruits, wound):
    if not PWSH:
        raise unittest.SkipTest("pwsh is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "case.json"
        p.write_text(json.dumps({"recruits": recruits, "wound": wound}), encoding="utf-8")
        r = subprocess.run([PWSH, "-NoProfile", "-File", str(ROOT / "tools" / "hud_harness" / "rez_objective_probe.ps1"),
                            "-Script", str(ROOT / "scripts" / "build_next_mission_v1.ps1"), "-CasePath", str(p)],
                           capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])["heroId"]


def test_a_wreck_in_the_wound_becomes_the_objective():
    recruits = [{"heroId": "fatboy", "zoneId": "GF_NW", "spawnAsWreck": True},
                {"heroId": "hearth", "zoneId": "GF_C", "spawnAsWreck": True}]
    assert _pick(recruits, ["GF_C"]) == "hearth"


def test_no_wreck_in_the_wound_leaves_the_objective_alone():
    assert _pick([{"heroId": "fatboy", "zoneId": "GF_NW", "spawnAsWreck": True}], ["GF_C"]) is None
    # a live join standing in the wound is not a rez
    assert _pick([{"heroId": "consul", "zoneId": "GF_C", "spawnAsWreck": False}], ["GF_C"]) is None


def test_the_gadget_waits_for_the_rez():
    src = GADGET.read_text(encoding="utf-8")
    assert 'if rezHero and how ~= "rescued" then return end' in src
    assert 'onObjectiveComplete("rescued")' in src
