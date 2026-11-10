#!/usr/bin/env python3
"""Check a staged ship tree (ship.ps1 -SkipPython -SkipZip) for what a release must carry.

    python tools/check_ship_dryrun_v1.py export/dist/VerdanceAshes_v<VERSION>

Looks for: the repo LICENSE and NOTICE beside the build, Umwelt's LICENSE,
LICENSE-EXCEPTION.md and NOTICE beside the vendored snapshot (AGPL-3.0-or-later
with the AQuantumArchitect exception), the exception's source link left intact,
and a release_manifest.json with every field and the right values for a
-SkipPython build. Exit 0 = clean, 1 = problems (each printed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FIELDS = (
    "schemaVersion", "name", "version", "builtAt", "sourceCommit", "umweltCommit", "fileCount",
    "playerEntry", "includesKernel", "includesMod", "includesPython", "includesScience",
    "includesUmwelt", "includesDevKit", "beliefWorks",
)


def check(staging: Path) -> list[str]:
    bad: list[str] = []
    for rel in ("LICENSE", "NOTICE", "tools/_vendor/umwelt/LICENSE",
                "tools/_vendor/umwelt/LICENSE-EXCEPTION.md", "tools/_vendor/umwelt/NOTICE",
                "tools/_vendor/umwelt/__init__.py", "tools/_vendor/UMWELT_SNAPSHOT.txt"):
        f = staging / rel
        if not f.is_file() or f.stat().st_size == 0:
            bad.append(f"missing or empty: {rel}")
    exc = staging / "tools/_vendor/umwelt/LICENSE-EXCEPTION.md"
    if exc.is_file() and "https://github.com/AQuantumArchitect/umwelt-engine" not in exc.read_text(encoding="utf-8"):
        bad.append("LICENSE-EXCEPTION.md does not keep the umwelt-engine source link")
    mf = staging / "release_manifest.json"
    if not mf.is_file():
        return bad + ["missing: release_manifest.json"]
    # ship.ps1 writes UTF8 (BOM on Windows PowerShell 5.1); utf-8-sig reads both.
    m = json.loads(mf.read_text(encoding="utf-8-sig"))
    for k in REQUIRED_FIELDS:
        if k not in m:
            bad.append(f"manifest lacks field: {k}")
    if bad:
        return bad
    version = (ROOT / "VERSION").read_text(encoding="utf-8").split()[0]
    if m["version"] != version:
        bad.append(f"manifest version {m['version']!r} != VERSION {version!r}")
    if m["name"] != f"VerdanceAshes_v{version}":
        bad.append(f"manifest name {m['name']!r} unexpected")
    if not m["includesKernel"] or not m["includesMod"] or not m["includesUmwelt"]:
        bad.append("manifest says kernel/mod/umwelt not included")
    if m["includesPython"] or m["includesDevKit"]:
        bad.append("manifest includesPython/includesDevKit set on a -SkipPython, non-Dev dry run")
    if not isinstance(m["fileCount"], int) or m["fileCount"] <= 0:
        bad.append("manifest fileCount is not a positive integer")
    n = sum(1 for p in staging.rglob("*") if p.is_file())
    # ship.ps1 counts the files before it writes the manifest itself, hence the +1.
    if n != m["fileCount"] + 1:
        bad.append(f"manifest fileCount {m['fileCount']} + manifest != files on disk {n}")
    return bad


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    staging = Path(argv[1])
    bad = check(staging)
    for b in bad:
        print("FAIL:", b)
    print("ship dry-run check:", "FAILED" if bad else "ok", f"({staging})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
