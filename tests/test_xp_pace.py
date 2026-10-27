#!/usr/bin/env python3
"""XP comes at half the old pace (owner, 2026-10-24), field effects grow their bonus rather than the
whole stat, and full craft doubles a builder's power and range."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine  # noqa: E402
from verdance.campaign import roster  # noqa: E402

GADGETS = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets"


def test_campaign_xp_is_half_the_old_pace():
    state = engine.default_v1_state()
    gains = roster._sortie_xp_gains(state, {"status": "extracted"}, True, True)
    assert gains["hero"] == 41.0          # was 82: a clean victory in cracked-farm mode
    assert roster.CAMPAIGN_XP_PACE == 0.5


def test_field_xp_is_paced_in_the_veterancy_gadget():
    src = (GADGETS / "game_verdance_veterancy.lua").read_text(encoding="utf-8")
    assert re.search(r"local FIELD_XP_RATE = 0\.5\b", src)


def test_a_field_effect_grows_its_bonus_not_the_stat():
    src = (GADGETS / "include" / "va_hero_tags.lua").read_text(encoding="utf-8")
    assert "out[stat] = 1 + ((tonumber(resolved[stat]) or 1) - 1) * scale" in src


def test_full_craft_doubles_build_power_and_reaches_1_8_range():
    # build power doubles at full experience; range is x1.8 (owner, 2026-10-27; Ketha x2.2)
    src = (GADGETS / "game_verdance_craft_xp.lua").read_text(encoding="utf-8")
    vals = dict(re.findall(r"local (BP_PER_XP|BP_CAP|RANGE_PER_XP|RANGE_CAP) = ([0-9.]+)", src))
    assert float(vals["BP_CAP"]) == 2.0 and float(vals["RANGE_CAP"]) == 1.8
    assert 1 + float(vals["BP_PER_XP"]) * 2.4 >= 2.0 and 1 + float(vals["RANGE_PER_XP"]) * 2.4 >= 1.8 - 1e-3
