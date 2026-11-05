#!/usr/bin/env python3
"""The Python mission builder writes the scenario the PowerShell one did (port of 2026-11-04).

The corpus is a real tour from Luke's PC (autopilot --tour, commit 9ce74de): for each sortie, the
state and intent build_next_mission_v1.ps1 read and the scenario and manifest it wrote. Each case is
rebuilt here from its state and intent against this workspace and compared as JSON, value for value
(bool is not 1; 2 and 2.0 are one number, as they are to every JSON reader). Every mismatch is
reported by its path.

    /home/claude/corpus154455 (or $VA_BUILDER_CORPUS)   the whole tour; skipped when absent
    tests/fixtures/mission_builder/                    three cases of it, gzipped, run everywhere

The fixture was cut with ``python3 tests/test_mission_builder_parity.py --make-fixture`` (tour 02:
Greenest Fields' shell with one visit-tier warden; tour 08: the Bastion's standing war with Armada
seated first; tour 11: the spire-jump finale). The run-specific paths are blanked in it.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.mission_builder import build_scenario  # noqa: E402
from verdance.mission_builder import _ps  # noqa: E402

CORPUS = Path(os.environ.get("VA_BUILDER_CORPUS") or "/home/claude/corpus154455")
FIXTURE = ROOT / "tests" / "fixtures" / "mission_builder"
FIXTURE_CASES = ("02", "08", "11")

# Run-specific, so never compared: where that run's workspace sat on that PC, and when it ran.
IGNORED_SCENARIO = ("/sourceIntentPath", "/sourceStatePath")
IGNORED_MANIFEST = ("/generatedAt", "/intentPath", "/statePath", "/scenarioPath", "/seedOutbox", "/seedDestination",
                    # Python only: whether install_playable_slice.ps1 ran. The PS1 had no such field.
                    "/installed")
# The field recruits are the encounter field's draw, which is Umwelt's (umwelt.foresight.encounter).
# Without Umwelt the draw is a different one, so that subtree is compared only when Umwelt imports.
NEEDS_UMWELT = ("/missionBase/fieldRecruits",)


def _umwelt() -> bool:
    from verdance.company import encounters

    return bool(encounters.available())


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def mismatches(want: Any, got: Any, path: str = "", ignore: Iterable[str] = ()) -> List[str]:
    ignore = tuple(ignore)
    out: List[str] = []

    def walk(a: Any, b: Any, p: str) -> None:
        if any(p == i or p.startswith(i + "/") or p.startswith(i + "[") for i in ignore):
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a:
                if k not in b:
                    out.append(f"{p}/{k}: missing from the Python build")
                else:
                    walk(a[k], b[k], f"{p}/{k}")
            for k in b:
                if k not in a and not any(f"{p}/{k}" == i for i in ignore):
                    out.append(f"{p}/{k}: only in the Python build")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                out.append(f"{p}: {len(a)} items in the PS1 build, {len(b)} in Python")
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{p}[{i}]")
        elif _num(a) and _num(b):
            if a != b:
                out.append(f"{p}: {a!r} != {b!r}")
        elif type(a) is not type(b) or a != b:
            out.append(f"{p}: {json.dumps(a)[:120]} != {json.dumps(b)[:120]}")

    walk(want, got, path)
    return out


def _check(case: str, state: Any, intent: Any, scenario: Any, manifest: Any) -> List[str]:
    sc, man = build_scenario(ROOT, intent, state, log=lambda _line: None, ps1_faults=True)
    sc = json.loads(json.dumps(sc))
    man = json.loads(json.dumps(man))
    skip = list(IGNORED_SCENARIO) + ([] if _umwelt() else list(NEEDS_UMWELT))
    bad = [f"{case} scenario {m}" for m in mismatches(scenario, sc, ignore=skip)]
    bad += [f"{case} manifest {m}" for m in mismatches(manifest, man, ignore=IGNORED_MANIFEST)]
    return bad


def _load(p: Path) -> Any:
    if p.suffix == ".gz":
        return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8-sig"))
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _corpus_cases() -> List[Path]:
    tour = CORPUS / "tour"
    if not tour.is_dir():
        return []
    return [d / "build" for d in sorted(tour.iterdir()) if (d / "build" / "scenario.json").is_file()]


def test_the_python_builder_matches_every_corpus_sortie():
    cases = _corpus_cases()
    if not cases:
        raise unittest.SkipTest(f"no parity corpus at {CORPUS} (set VA_BUILDER_CORPUS)")
    bad: List[str] = []
    for b in cases:
        bad += _check(b.parent.name, _load(b / "state.json"), _load(b / "intent.json"),
                      _load(b / "scenario.json"), _load(b / "manifest.json"))
    assert not bad, "\n".join(bad[:200])


def test_the_python_builder_matches_the_committed_fixture():
    bad: List[str] = []
    for case in FIXTURE_CASES:
        d = FIXTURE / f"tour{case}"
        assert d.is_dir(), f"missing fixture {d}"
        bad += _check(f"tour{case}", _load(d / "state.json.gz"), _load(d / "intent.json.gz"),
                      _load(d / "scenario.json.gz"), _load(d / "manifest.json.gz"))
    assert not bad, "\n".join(bad[:200])


def test_field_recruits_match_when_umwelt_is_here():
    if not _umwelt():
        raise unittest.SkipTest("umwelt.foresight.encounter not importable (UMWELT_SRC): field recruits not compared")
    bad: List[str] = []
    for case in FIXTURE_CASES:
        d = FIXTURE / f"tour{case}"
        sc, _ = build_scenario(ROOT, _load(d / "intent.json.gz"), _load(d / "state.json.gz"), log=lambda _l: None, ps1_faults=True)
        want = _load(d / "scenario.json.gz")["missionBase"]["fieldRecruits"]
        bad += [f"tour{case} {m}" for m in mismatches(want, json.loads(json.dumps(sc["missionBase"]["fieldRecruits"])),
                                                      "/missionBase/fieldRecruits")]
    assert not bad, "\n".join(bad)


def test_the_kernel_builds_with_python_unless_told_otherwise():
    from verdance_kernel import api

    calls = []
    saved = (api.run_module, api.run_ps1, os.environ.get("VERDANCE_BUILDER"))
    api.run_module = lambda ws, module, args=None, **kw: calls.append(("py", module)) or {"ok": True}
    api.run_ps1 = lambda script, ws, extra_args=None, **kw: calls.append(("ps1", Path(script).name)) or {"ok": True}
    try:
        os.environ.pop("VERDANCE_BUILDER", None)
        k = api.CampaignKernel(ROOT)
        assert k.build_mission()["ok"] and calls[-1] == ("py", "verdance.mission_builder")
        os.environ["VERDANCE_BUILDER"] = "ps1"
        k.build_mission()
        # The PS1 path still resolves its scripts by Windows-style relative paths, so off Windows it
        # reports the script missing instead of calling it.
        assert calls[-1][0] == "ps1" or len(calls) == 1
    finally:
        api.run_module, api.run_ps1 = saved[0], saved[1]
        if saved[2] is None:
            os.environ.pop("VERDANCE_BUILDER", None)
        else:
            os.environ["VERDANCE_BUILDER"] = saved[2]


# --- The PowerShell 5.1 rules the port leans on ----------------------------------------------------

def test_numbers_round_and_print_as_windows_powershell_did():
    assert _ps.I(2.5) == 2 and _ps.I(3.5) == 4 and _ps.I(-2.5) == -2     # [int] rounds half to even
    assert _ps.R(0.95, 2) == 0.95 and _ps.R(1.0005, 3) == 1.0             # scale, round, unscale
    assert _ps.S(1.0) == "1" and _ps.S(0.1 + 0.2) == "0.3" and _ps.S(1e-7) == "1E-07"   # "G", 15 digits
    assert _ps.D(_ps.JNum("0.24000000000000002")) == 0.24                  # a JSON decimal cast to double
    assert _ps.T({}) and not _ps.T([]) and not _ps.T([0]) and _ps.T("False")


def test_strings_compare_without_case():
    assert _ps.ieq("Armada", "armada") and _ps.iin("SEIZE_LANE", ("seize_lane",))
    assert _ps.ilike("armcom_suit", "ARMCOM*") and _ps.imatch("Ash-Captain Vane", "vane")


def _make_fixture() -> None:
    blank = "<run-specific>"
    for case in FIXTURE_CASES:
        src = CORPUS / "tour" / case / "build"
        dst = FIXTURE / f"tour{case}"
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("state", "intent", "scenario", "manifest"):
            doc = _load(src / f"{name}.json")
            if name == "scenario":
                for k in ("sourceIntentPath", "sourceStatePath"):
                    doc[k] = blank
            if name == "manifest":
                for k in ("intentPath", "statePath", "scenarioPath", "seedOutbox", "seedDestination"):
                    doc[k] = blank
            raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            (dst / f"{name}.json.gz").write_bytes(gzip.compress(raw, 9, mtime=0))
        print(f"wrote {dst}")


if __name__ == "__main__":
    if "--make-fixture" in sys.argv:
        _make_fixture()
    else:
        for fn in (test_the_python_builder_matches_every_corpus_sortie, test_the_python_builder_matches_the_committed_fixture,
                   test_field_recruits_match_when_umwelt_is_here, test_the_kernel_builds_with_python_unless_told_otherwise,
                   test_numbers_round_and_print_as_windows_powershell_did,
                   test_strings_compare_without_case):
            try:
                fn()
                print("ok  ", fn.__name__)
            except unittest.SkipTest as e:
                print("skip", fn.__name__, e)


def test_the_game_builds_with_the_ps1_faults_fixed():
    """Proxy call, 2026-11-04: war seats get their side's colour, and a lone warden takes the field.
    Tour 02 had one warden and a standing war; tour 08 seats Armada in a standing war."""
    from verdance.mission_builder.builder import FIXED_PS1_FAULTS
    assert set(FIXED_PS1_FAULTS) == {"war_seat_colour", "lone_warden"}
    for case in FIXTURE_CASES:
        d = FIXTURE / f"tour{case}"
        intent, state = _load(d / "intent.json.gz"), _load(d / "state.json.gz")
        fixed, _ = build_scenario(ROOT, intent, state, log=lambda _l: None)
        faulty, _ = build_scenario(ROOT, intent, state, log=lambda _l: None, ps1_faults=True)
        teams = lambda sc: (sc.get("variants") or {}).get(sc.get("defaultVariant") or "", sc).get("teams") or sc.get("teams") or []
        def all_teams(sc):
            out = []
            def walk(x):
                if isinstance(x, dict):
                    if "rgb" in x and "side" in x:
                        out.append(x)
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)
            walk(sc)
            return out
        war = [t for t in all_teams(fixed) if str(t.get("side")) in ("Armada", "Cortex")]
        assert all(t.get("rgb") for t in war), f"tour{case}: a war seat without colour"
        wardens = lambda sc: [t for t in all_teams(sc) if "warden" in str(t.get("label") or "")]
        n_wardens = len(((intent.get("visitTier") or {}).get("wardens")) or [])
        if n_wardens == 1:
            assert len(wardens(faulty)) == 0 and len(wardens(fixed)) == 1, f"tour{case}: the lone warden"
