#!/usr/bin/env python3
"""Run the test suite without pytest.

Discovers ``tests/test_*.py``, imports each with ``tools/`` on ``sys.path``, runs every
``unittest.TestCase`` it defines and every module-level ``test_*`` callable that takes no
required arguments (anything that needs a fixture is skipped and listed), then prints the
pass/fail counts. Exit code 0 means everything that ran passed.

    python3 tests/run_tests.py                 # whole suite
    python3 tests/run_tests.py belief kernel   # only files whose name contains a word
    UMWELT_SRC=/path/to/umwelt/src python3 tests/run_tests.py   # with the belief field present
"""
from __future__ import annotations

import importlib.util
import inspect
import io
import os
import sys
import traceback
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
TOOLS = ROOT / "tools"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _runnable(fn) -> bool:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return True
    for p in sig.parameters.values():
        if p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            return False
    return True


def _bootstrap_fresh_tree() -> None:
    """A fresh clone or a SHIP -Dev unzip has no save until SETUP runs. Several suites read the
    live save in state/, so write the one SETUP would (init-state, mission 1 intent, hub rebuild);
    a played save is never touched."""
    import subprocess

    save = ROOT / "state" / "campaign_state.json"
    if save.is_file():
        return
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(TOOLS), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    steps = (
        ["-m", "verdance.campaign.engine", "init-state", "--workspace", str(ROOT), "--state", str(save), "--write-state"],
        ["-m", "verdance.campaign.engine", "intent", "--workspace", str(ROOT)],
        ["-m", "verdance_kernel", "rebuild", "--workspace", str(ROOT)],
    )
    for args in steps:
        r = subprocess.run([sys.executable, *args], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=900)
        if r.returncode:
            print(f"fresh tree: '{args[1]} {args[2]}' failed: {(r.stderr or r.stdout)[-400:]}")
            return
    print("fresh tree: wrote the save SETUP would (state/campaign_state.json, mission 1)")


def main(argv: list[str]) -> int:
    words = [a for a in argv if not a.startswith("-")]
    verbose = "-v" in argv
    for p in (str(TOOLS), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    # the belief field: UMWELT_SRC (or a sibling clone) on the path, as verdance.belief.world does
    umwelt = os.environ.get("UMWELT_SRC") or str(ROOT.parent / "umwelt" / "src")
    if (Path(umwelt) / "umwelt" / "__init__.py").is_file() and umwelt not in sys.path:
        sys.path.append(umwelt)
    os.chdir(ROOT)
    _bootstrap_fresh_tree()
    files = sorted(TESTS.glob("test_*.py"))
    if words:
        files = [f for f in files if any(w in f.name for w in words)]
    passed = failed = skipped = 0
    failures: list[tuple[str, str]] = []
    skips: list[str] = []
    for path in files:
        try:
            mod = _load(path)
        except SystemExit as e:  # a module that exits on a missing optional dependency
            skipped += 1
            skips.append(f"{path.name}: exited at import ({e.code})")
            continue
        except Exception:
            failed += 1
            failures.append((path.name, "import failed:\n" + traceback.format_exc()))
            print(f"FAIL {path.name} (import)")
            continue
        # unittest classes
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for name, obj in vars(mod).items():
            if inspect.isclass(obj) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                suite.addTests(loader.loadTestsFromTestCase(obj))
        if suite.countTestCases():
            stream = io.StringIO()
            res = unittest.TextTestRunner(stream=stream, verbosity=2 if verbose else 1).run(suite)
            n_bad = len(res.failures) + len(res.errors)
            passed += res.testsRun - n_bad - len(res.skipped)
            failed += n_bad
            skipped += len(res.skipped)
            for case, tb in res.failures + res.errors:
                failures.append((f"{path.name}::{case.id().split('.')[-1]}", tb))
                print(f"FAIL {path.name}::{case.id().split('.')[-1]}")
            for case, why in res.skipped:
                skips.append(f"{path.name}::{case.id().split('.')[-1]}: {why}")
            if verbose:
                print(stream.getvalue())
        # plain test_* functions
        for name, obj in vars(mod).items():
            if not name.startswith("test_") or not callable(obj) or inspect.isclass(obj):
                continue
            if getattr(obj, "__module__", None) != mod.__name__:
                continue  # imported from elsewhere
            if not _runnable(obj):
                skipped += 1
                skips.append(f"{path.name}::{name}: needs a fixture")
                continue
            try:
                obj()
                passed += 1
                if verbose:
                    print(f"ok   {path.name}::{name}")
            except unittest.SkipTest as e:
                skipped += 1
                skips.append(f"{path.name}::{name}: {e}")
            except Exception:
                failed += 1
                failures.append((f"{path.name}::{name}", traceback.format_exc()))
                print(f"FAIL {path.name}::{name}")
    print()
    for label, tb in failures:
        print("=" * 72)
        print(label)
        print(tb.rstrip()[-2500:])
    if skips:
        print("-" * 72)
        print("skipped:")
        for s in skips:
            print("  " + s)
    print("-" * 72)
    print(f"{passed} passed, {failed} failed, {skipped} skipped · {len(files)} files")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
