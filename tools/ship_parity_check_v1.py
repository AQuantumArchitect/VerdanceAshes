#!/usr/bin/env python3
"""Assert a staged ship tree can actually import everything it uses.

Why this exists
---------------
Every optional subsystem in the story engine is imported inside a bare
``try/except Exception`` -- see verdance_story_engine_v1.py:4574 and :5008.
That is a reasonable pattern for a genuinely optional feature and a disastrous
one for a packaging mistake, because the two are indistinguishable at runtime:
a module left out of the ship list produces no error, no log line, and no
missing feature you can point at. It produces a quieter game.

v0.10.0 shipped without ``escalation_ladder_v1``, ``match_credit_v1`` or
``offscreen_clash_v1``. Without the first of those, build_next_mission_v1.ps1
falls through to ``objectiveStrength = "surgical"`` for the entire campaign --
which is precisely the flat difficulty curve Drop 4 was written to remove. The
build looked fine. It was the pre-Drop-4 game with a newer version number.

So: resolve the import closure statically and fail the ship, rather than
discovering it from a playtester saying the missions felt samey.

  python tools/ship_parity_check_v1.py --staging export/dist/VerdanceAshes_v0.10.0
  python tools/ship_parity_check_v1.py --staging . --closure   # what SHOULD ship
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Modules the embedded CPython provides. Checked with sys.stdlib_module_names
# where available (3.10+), so this only has to cover what that misses.
_EXTRA_STDLIB = {"__future__", "typing_extensions"}

# Declared in requirements-ship.txt and genuinely optional -- the kernel falls
# back to the system browser when it is absent, which is a real feature flag
# rather than a packaging accident.
_ALLOWED_THIRD_PARTY = {"webview"}


def stdlib_names() -> Set[str]:
    # sys.stdlib_module_names is 3.10+, which requirements-ship.txt already
    # requires and the embedded 3.12 runtime provides. No fallback: the obvious
    # one imports distutils, which 3.12 removed, so it would be dead code that
    # this very checker then reports as an unresolved import.
    names = set(getattr(sys, "stdlib_module_names", set()))
    if not names:
        raise SystemExit("needs Python 3.10+ (sys.stdlib_module_names)")
    return names | _EXTRA_STDLIB


def top_level_imports(path: Path) -> Set[str]:
    """Every module name this file needs, normalised to a staged-tools name.

    Walks the whole tree rather than just module-level statements: the imports
    that actually broke the v0.10.0 build were all inside functions, several
    levels into a try block.

    `tools` is unwrapped rather than reported. Several modules use the pattern
    `try: import attachments_v1 / except ImportError: from tools import
    attachments_v1` -- the same module by either name, depending on whether the
    tools directory is on sys.path directly or as a package. Reporting the
    package spelling as a missing dependency is a false positive; what matters
    is whether `attachments_v1` itself is staged.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise SystemExit(f"cannot parse {path}: {exc}")
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                # import tools.attachments_v1 -> attachments_v1
                found.add(parts[1] if parts[0] == "tools" and len(parts) > 1 else parts[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import; it resolves inside its own
            # package and cannot be a missing top-level module.
            if node.level != 0 or not node.module:
                continue
            parts = node.module.split(".")
            if parts[0] == "tools":
                if len(parts) > 1:
                    found.add(parts[1])
                else:
                    # from tools import X, Y -> the names ARE the modules
                    found.update(a.name for a in node.names)
            else:
                found.add(parts[0])
    return found


def data_dirs_referenced(paths: List[Path]) -> Set[str]:
    """Data subdirectories named anywhere in source, in any of three spellings.

    The pathlib form is the one that matters and the one a naive scan misses:
    the story engine reaches hydrology as `Path(workspace) / "data" /
    "hydrology" / ...`, so there is no "data/hydrology" substring in the file
    at all. Both dirs left out of v0.10.0 were referenced this way.
    """
    import re
    pats = (
        re.compile(r'["\']data[\\/]+([A-Za-z0-9_]+)'),          # "data/escalation"
        re.compile(r'["\']data["\']\s*/\s*["\']([A-Za-z0-9_]+)'),  # "data" / "escalation"
        re.compile(r'["\']data["\']\s*,\s*["\']([A-Za-z0-9_]+)'),  # "data", "escalation"
    )
    out: Set[str] = set()
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        # Drop whole-line comments first. Both Python and PowerShell use '#',
        # and prose about this very check ("no \"data/x\" substring exists")
        # otherwise registers as a reference to a directory named x -- which is
        # exactly what happened the first time this gate ran.
        code = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#"))
        for pat in pats:
            out.update(pat.findall(code))
    return out


def analyse(tools_dir: Path) -> Tuple[Dict[str, Set[str]], Set[str]]:
    """Map every local module -> the local modules it needs."""
    local = {p.stem for p in tools_dir.glob("*.py")}
    local |= {d.name for d in tools_dir.iterdir() if d.is_dir() and (d / "__init__.py").exists()}
    std = stdlib_names()

    needs: Dict[str, Set[str]] = {}
    unknown: Set[str] = set()
    py_files = sorted(tools_dir.rglob("*.py"))
    for f in py_files:
        if "__pycache__" in f.parts:
            continue
        owner = f.stem if f.parent == tools_dir else f.parent.name
        for name in top_level_imports(f):
            if name in std or name in _ALLOWED_THIRD_PARTY:
                continue
            if name in local:
                needs.setdefault(owner, set()).add(name)
            else:
                unknown.add(name)
    return needs, unknown


def closure(entry: Set[str], needs: Dict[str, Set[str]]) -> Set[str]:
    seen: Set[str] = set()
    stack = list(entry)
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        stack.extend(needs.get(mod, set()))
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staging", required=True,
                    help="the staged dist root (or the workspace, with --closure)")
    ap.add_argument("--closure", action="store_true",
                    help="print the full transitive module closure and exit 0")
    ap.add_argument("--entry", default="",
                    help="comma-separated entry modules for --closure (default: "
                         "everything present, which from the workspace means "
                         "every dev tool too -- pass the ship list instead)")
    args = ap.parse_args()

    root = Path(args.staging).resolve()
    tools = root / "tools"
    if not tools.is_dir():
        print(f"FAIL no tools/ under {root}")
        return 2

    needs, unknown = analyse(tools)
    present = {p.stem for p in tools.glob("*.py")}
    present |= {d.name for d in tools.iterdir() if d.is_dir() and (d / "__init__.py").exists()}

    if args.closure:
        entry = ({e.strip() for e in args.entry.split(",") if e.strip()}
                 if args.entry else set(present))
        unknown_entry = entry - present
        if unknown_entry:
            print(f"FAIL entry modules not found: {', '.join(sorted(unknown_entry))}")
            return 2
        want = closure(entry, needs)
        for m in sorted(want):
            print(f"{'  ' if m in entry else '+ '}{m}")
        added = want - entry
        print(f"\n{len(entry)} entry, {len(added)} pulled in transitively")
        # The data those modules reach for, so $dataParts can be fixed in the
        # same pass rather than discovered one failed ship at a time.
        files = [tools / f"{m}.py" for m in want if (tools / f"{m}.py").exists()]
        files += [p for m in want if (tools / m).is_dir()
                  for p in (tools / m).rglob("*.py") if "__pycache__" not in p.parts]
        print("data dirs reached: " + ", ".join(sorted(data_dirs_referenced(files))))
        return 0

    problems: List[str] = []

    # Every local import must resolve inside the staged tree.
    for owner in sorted(needs):
        for dep in sorted(needs[owner]):
            if dep not in present:
                problems.append(f"{owner} imports '{dep}' -- not staged")

    for name in sorted(unknown):
        problems.append(f"unresolved import '{name}' (not stdlib, not staged, not allowed)")

    # Data directories referenced by staged code must be staged too.
    py_files = [p for p in tools.rglob("*.py") if "__pycache__" not in p.parts]
    ps_files = list((root / "scripts").rglob("*.ps1")) if (root / "scripts").is_dir() else []
    for d in sorted(data_dirs_referenced(py_files + ps_files)):
        if not (root / "data" / d).exists():
            problems.append(f"data/{d} referenced by staged code -- not staged")

    if problems:
        print("SHIP PARITY FAILED")
        for p in problems:
            print(f"  {p}")
        print("\nA missing module here does not crash -- it silently disables a")
        print("subsystem. Add it to $toolPy / $dataParts in scripts/ship.ps1.")
        return 1

    print(f"ship parity OK ({len(present)} modules staged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
