#!/usr/bin/env python3
"""Owner's loadout calls, 2026-10-26: Yeva, Rumor, Noctua, Twitcher (data and gadget roster agree)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS = json.loads((ROOT / "data/story/crew_packs.json").read_text(encoding="utf-8-sig"))
LUA = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_crew_roster.lua").read_text(encoding="utf-8")
H = PACKS["heroes"]


def _esc(h):
    return {e["unitDef"]: e["count"] for e in H[h].get("escorts", [])}


def _lua_block(h):
    return re.search(r"\n  " + h + r" = \{\n(.*?)\n  \},", LUA, re.S).group(1)


def test_yeva_is_one_sharpshooter_and_six_ticks():
    assert H["yeva"]["unitDef"] == "armsnipe" and H["yeva"]["packTotal"] == 1
    assert _esc("yeva") == {"armflea": 6}
    b = _lua_block("yeva")
    assert 'unitDef = "armflea"' in b and "count = 6" in b and "legaspy" not in b


def test_rumor_has_four_ghosts_and_two_stealth_tanks():
    # recast 2026-10-28: one Ghost, two Legion Eidolons, the two Gremlins
    assert H["rumor"]["packTotal"] == 1 and H["rumor"]["extras"] == 0
    assert _esc("rumor") == {"legaspy": 2, "armgremlin": 2}
    b = _lua_block("rumor")
    assert "packTotal = 1" in b and 'unitDef = "armgremlin"' in b and 'unitDef = "legaspy"' in b


def test_noctua_flies_blindfold_radar_killers():
    # recast 2026-10-28: the scout paradigm, the bay prints its fighters; no starting wing
    assert _esc("noctua") == {"legmstor": 1}
    assert PACKS["chassis"]["legcib"]["label"] == "Blindfold"
    assert 'unitDef = "legmstor"' in _lua_block("noctua")


def test_twitcher_hires_for_one_tnb_not_a_thousand_metal():
    assert H["twitch"]["hireTnb"] == 1 and "hireKm" not in H["twitch"]
    b = _lua_block("twitch")
    assert "hireTnb = 1" in b and "hireKm" not in b
