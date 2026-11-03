"""Verdance runs on whatever BAR the player has. BAR test-31774 (2026-11) moved its utilities from
Spring.Utilities to BAR.Utilities, and Verdance's raptor spawner, which read Spring.Utilities on its
first line, failed to load on a stock install: the Rock Jungle had no raptor waves, no rage and no
queen. Every Verdance Lua file reads the utilities through a fallback that works on both."""
import re
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "mod" / "VerdanceAshes.sdd"


def test_no_verdance_lua_reads_spring_utilities_without_a_fallback():
    bad = []
    for path in MOD.rglob("*.lua"):
        src = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(src.splitlines(), 1):
            code = line.split("--", 1)[0]
            if re.search(r"Spring\.Utilities\.", code):
                bad.append(f"{path.relative_to(MOD)}:{n}: {line.strip()}")
    assert not bad, "read BAR.Utilities or Spring.Utilities, whichever exists:\n" + "\n".join(bad)


def test_the_raptor_spawner_reads_whichever_utilities_this_bar_has():
    src = (MOD / "luarules" / "gadgets" / "raptor_spawner_defense.lua").read_text(encoding="utf-8")
    assert "local Utilities = (BAR and BAR.Utilities) or Spring.Utilities" in src
