"""Every zone the player controls is outlined on the battlefield (issue #14, Luke 2026-11-13: "I'd like to
have those zones show up for all zones that I control. so that way I know who's safe to extract").

- tools/hud_harness/exfil_gadget_test.py: va_lift_zones is read off the extraction rule itself (safeZone),
  so a zone is listed exactly when a unit of ours standing there lifts; taken mid-fight it joins within a
  scan, lost it leaves (run by tests/test_exfil_gadget.py).
- tools/hud_harness/harness.py (here): the minimap widget outlines every listed zone on the ground but the
  pad (which keeps its ring), and the outlines follow the list.
Skipped where liblua5.4 is not installed."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lua_harness import liblua_paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_every_zone_we_control_is_outlined_on_the_ground():
    harness = ROOT / "tools" / "hud_harness" / "harness.py"
    if not liblua_paths():
        raise unittest.SkipTest("liblua5.4 is not installed")
    if not harness.is_file():
        return  # a SHIP -Dev tree: the HUD harness stays in the workspace
    r = subprocess.run([sys.executable, str(harness)], capture_output=True, text=True,
                       env=dict(os.environ, VA_WS=str(ROOT)), timeout=120, cwd=str(harness.parent))
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "HARNESS PASSED" in out, out[-3000:]
    assert "ok   every zone we control is outlined on the ground (#14)" in out, out[-3000:]


def test_the_outline_list_is_the_extraction_rule():
    src = (ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_exfil.lua").read_text(encoding="utf-8")
    body = src[src.index("local function publishLiftZones()"):src.index("local function liftsFrom(x, z)")]
    assert "safeZone(z)" in body, "va_lift_zones must come from safeZone, not a second list"
