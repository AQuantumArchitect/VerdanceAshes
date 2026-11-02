#!/usr/bin/env python3
"""What a release build ships about the machine that built it, and which Umwelt it ships (2026-10-31).

  * no machine paths: release_manifest.json names commits, not the builder's workspace folder;
    UMWELT_SNAPSHOT.txt names Umwelt's repo and commit, not the folder it was copied from
  * the Umwelt a build vendors is the pinned commit (tools/umwelt_pin.json), never a home-folder
    clone (0.13.0/0.14.0 picked up a stale ~/ws-win/umwelt); a shipped build imports its own
    snapshot before any clone on the machine
  * Umwelt is Apache-2.0: its LICENSE ships beside the snapshot, NOTICE and RELEASE.md say so
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

SHIP = (ROOT / "scripts" / "ship.ps1").read_text(encoding="utf-8-sig")
PIN = json.loads((ROOT / "tools" / "umwelt_pin.json").read_text(encoding="utf-8"))


def test_the_pin_names_one_umwelt_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", PIN["commit"]), PIN
    assert PIN["repo"] == "https://github.com/AQuantumArchitect/umwelt.git"
    assert PIN["license"] == "Apache-2.0"


def test_the_manifest_carries_no_machine_path():
    block = SHIP[SHIP.index("# ---- manifest ----"):SHIP.index("release_manifest.json")]
    assert "sourceWorkspace" not in block and "$Workspace\n" not in block
    assert "sourceCommit" in block and "umweltCommit" in block
    snap = next(line for line in SHIP.splitlines() if "UMWELT_SNAPSHOT.txt" in line and "Set-Content" in line)
    assert "$umweltSrc" not in snap and "$umweltRoot" not in snap


def test_the_build_vendors_the_pin_not_a_home_clone():
    assert "ws-win" not in SHIP.replace("stale ~\\ws-win copy", "")
    assert "USERPROFILE \"umwelt" not in SHIP and "umwelt_pin.json" in SHIP
    assert "checkout --quiet --detach $umweltPin.commit" in SHIP
    assert "-AllowUmweltDrift" in SHIP or "$AllowUmweltDrift" in SHIP


def test_umwelts_license_ships_beside_it():
    assert 'Copy-File (Join-Path $umweltRoot "LICENSE") (Join-Path $vendor "umwelt\\LICENSE")' in SHIP
    assert "Apache-2.0 requires it beside the snapshot" in SHIP          # the build fails without it
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Umwelt  --  redistributed in shipped builds" in notice and "Apache License 2.0" in notice
    release = (ROOT / "RELEASE.md").read_text(encoding="utf-8")
    assert "Apache-2.0" in release and "Umwelt license check" in release
    assert "tools/_vendor/umwelt/" in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_a_shipped_build_imports_its_own_umwelt_first():
    from verdance.belief import world
    saved = os.environ.pop("UMWELT_SRC", None)
    try:
        paths = [str(p) for p in world.umwelt_search_paths()]
    finally:
        if saved is not None:
            os.environ["UMWELT_SRC"] = saved
    assert paths[0].endswith(os.path.join("tools", "_vendor")), paths
    assert not any("ws-win" in p for p in paths), paths


def test_the_umwelt_the_tests_import_is_the_pin():
    """When the tests run against a git clone of Umwelt (UMWELT_SRC), it should be the shipped one."""
    src = os.environ.get("UMWELT_SRC")
    if not src or not (Path(src).parent / ".git").exists():
        return
    head = subprocess.run(["git", "-C", str(Path(src).parent), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head == PIN["commit"], f"UMWELT_SRC is at {head}; tools/umwelt_pin.json pins {PIN['commit']}"


def test_release_ps1_runs_on_windows_powershell():
    """Two 0.14.0 bugs the first dry run hit: git stderr under Stop, and an array splat."""
    rel = (ROOT / "tools" / "release.ps1").read_text(encoding="utf-8-sig")
    code = "\n".join(line for line in rel.splitlines() if not line.lstrip().startswith("#"))
    assert "2>$null" not in code.replace("& git @args 2>$null", "")
    assert "@scriptArgs" in rel and "@($C.ScriptArgs)" not in rel
    # Join-Path with three paths is PowerShell 7; the build PC runs Windows PowerShell 5.1
    assert not re.search(r"Join-Path \$\w+ \$[\w.]+ '", code), "three-argument Join-Path"


def test_the_installed_mutator_depends_on_the_bar_the_player_has():
    """A BAR from beyondallreason.info is a rapid package named 'Beyond All Reason test-N-hash';
    'Beyond All Reason $VERSION' is only a developer checkout (games/BAR.sdd). Against a stock install
    the engine stopped at load: Dependent archive "Beyond All Reason $VERSION" not found (headless rig,
    2026-11-01). The copy SETUP and every Drop install is stamped with the BAR that is there."""
    inst = (ROOT / "scripts" / "install_mod_archive.ps1").read_text(encoding="utf-8-sig")
    assert "function Resolve-InstalledBarGame" in inst
    assert "versions.gz" in inst and '"packages"' in inst and "^Beyond All Reason test-(\\d+)-" in inst
    assert "Replace(\"'Beyond All Reason `$VERSION'\"" in inst
    modinfo = (ROOT / "mod" / "VerdanceAshes.sdd" / "modinfo.lua").read_text(encoding="utf-8")
    assert "'Beyond All Reason $VERSION'" in modinfo      # the stamp's anchor: keep the two in step
