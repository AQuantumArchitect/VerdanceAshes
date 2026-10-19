"""Guard: game_verdance_campaign.lua must stay under Lua 5.1's 200-local limit.

If the main chunk exceeds 200 locals, BAR refuses to load the gadget and
Initial Spawn leaves a stock Legion commander at a random start position.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GADGET = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"

# Soft ceiling so the next feature still has room.
SOFT_MAX = 190
HARD_MAX = 200


def _strip_strings_and_comments(line: str) -> str:
    result: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        if i + 3 < n and line[i : i + 4] == "--[[":
            j = line.find("]]", i + 4)
            if j < 0:
                return "".join(result)
            i = j + 2
            continue
        if i + 1 < n and line[i : i + 2] == "--":
            break
        c = line[i]
        if c in ('"', "'"):
            q = c
            i += 1
            while i < n:
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i] == q:
                    i += 1
                    break
                i += 1
            result.append('""')
            continue
        result.append(c)
        i += 1
    return "".join(result)


def count_main_chunk_locals(src: str) -> list[tuple[int, str, str]]:
    """Locals in the main chunk (nested function bodies excluded; do/if count)."""
    stack: list[str] = []
    found: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(src.splitlines(), 1):
        code = _strip_strings_and_comments(line)
        fdepth = sum(1 for x in stack if x == "function")
        stripped = code.strip()
        if fdepth == 0:
            m = re.match(r"local\s+function\s+([A-Za-z_][\w]*)", stripped)
            if m:
                found.append((lineno, m.group(1), "fn"))
            elif stripped.startswith("local ") and not stripped.startswith("local function"):
                left = stripped[6:].split("=", 1)[0]
                for part in left.split(","):
                    name = part.strip().split()[0] if part.strip() else ""
                    if re.match(r"^[A-Za-z_][\w]*$", name):
                        found.append((lineno, name, "var"))
        for m in re.finditer(r"\b(function|repeat|then|do|end|until|else|elseif)\b", code):
            kw = m.group(1)
            if kw == "function":
                stack.append("function")
            elif kw == "repeat":
                stack.append("repeat")
            elif kw == "then":
                stack.append("then")
            elif kw == "do":
                stack.append("do")
            elif kw == "else":
                pass
            elif kw == "elseif":
                if stack and stack[-1] == "then":
                    stack.pop()
            elif kw == "end":
                while stack:
                    k = stack.pop()
                    if k in ("function", "do", "then"):
                        break
            elif kw == "until":
                while stack:
                    k = stack.pop()
                    if k == "repeat":
                        break
    return found


class CampaignLocalBudgetTests(unittest.TestCase):
    def test_gadget_exists(self):
        self.assertTrue(GADGET.is_file(), f"missing {GADGET}")

    def test_under_hard_limit(self):
        locals_ = count_main_chunk_locals(GADGET.read_text(encoding="utf-8"))
        n = len(locals_)
        self.assertLessEqual(
            n,
            HARD_MAX,
            f"main-chunk locals={n} exceeds Lua 5.1 hard limit {HARD_MAX}; "
            f"last={locals_[-5:]}. Promote helpers to gadget-env globals or IIFE includes.",
        )

    def test_soft_headroom(self):
        locals_ = count_main_chunk_locals(GADGET.read_text(encoding="utf-8"))
        n = len(locals_)
        self.assertLessEqual(
            n,
            SOFT_MAX,
            f"main-chunk locals={n} above soft ceiling {SOFT_MAX} "
            f"(hard={HARD_MAX}). Free headroom before the next feature.",
        )

    def test_includes_use_iife_not_main_locals(self):
        text = GADGET.read_text(encoding="utf-8")
        self.assertIn("WorkerFeature = (function()", text)
        self.assertNotIn("local WorkerFeature", text)
        # Tenebrium attach pack must not be a main-chunk local.
        self.assertNotRegex(
            text,
            r"(?m)^do\n\s*local pack = \{ ok = false",
        )


if __name__ == "__main__":
    unittest.main()
