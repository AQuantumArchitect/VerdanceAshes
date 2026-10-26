"""The synced exfil gadget, run in real Lua (tools/hud_harness/exfil_gadget_test.py): the HUD scan,
the manifest (pad = landing zone) and extract. Skipped where liblua5.4 is not installed."""
import glob, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exfil_gadget_in_lua():
    harness = ROOT / "tools" / "hud_harness" / "exfil_gadget_test.py"
    if not glob.glob('/usr/lib/x86_64-linux-gnu/liblua5.4.so*') or not harness.is_file():
        return  # no Lua here, or a SHIP -Dev tree (the HUD harness stays in the workspace)
    r = subprocess.run([sys.executable, str(harness)],
                       capture_output=True, text=True, env=dict(os.environ, VA_WS=str(ROOT)), timeout=60)
    assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout + r.stderr
