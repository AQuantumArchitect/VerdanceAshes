"""Luke's Rock Jungle playtest, 2026-11-13: the smaller fixes.

- #17 "The raptor bar should get moved slightly over to the side": the rail drags BAR's Raptor Stats
  Panel left, clear of itself (tools/hud_harness/harness.py, with a stand-in that uses BAR's own
  placement and drag code).
- #18 "the raptor turrets should not drop tenebrium ... I don't even think they should drop
  anything": raptors leave no Tenebrium shard and lay no eggs (tools/hud_harness/raptor_loot_test.lua).
- #19 "we need some sort of like voice line telling us to extract": once the required work is done,
  the rail plays the extract cue once (a recorded Ketha line when it ships, BAR's beep6 until then)
  with a boxed Ketha prompt. The rail, the voice stack and the recorder now ask for the real
  widgetHandler (handler = true). Through BAR's proxy, RegisterGlobal(widget, name, fn) registered
  nothing, so the gadget's mission events (Script.LuaUI.VerdanceMissionEvent) never reached the rail.
Skipped where liblua5.4 is not installed."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lua_harness import liblua_paths, run as run_lua  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _harness():
    harness = ROOT / "tools" / "hud_harness" / "harness.py"
    if not liblua_paths():
        raise unittest.SkipTest("liblua5.4 is not installed")
    r = subprocess.run([sys.executable, str(harness)], capture_output=True, text=True,
                       env=dict(os.environ, VA_WS=str(ROOT)), timeout=120, cwd=str(harness.parent))
    return r.stdout + r.stderr


def test_raptor_panel_moves_and_extract_cue_plays():
    out = _harness()
    assert "HARNESS PASSED" in out, out[-3000:]
    for line in ("ok   raptor panel is moved clear of the rail (#17)",
                 "ok   extraction cue: a sound and a Ketha prompt, once (#19)",
                 "ok   every Verdance widget that registers globals asks for the real handler"):
        assert line in out, out[-3000:]


def test_raptors_drop_nothing():
    err = run_lua("tools/hud_harness/raptor_loot_test.lua")
    assert err is None, err
