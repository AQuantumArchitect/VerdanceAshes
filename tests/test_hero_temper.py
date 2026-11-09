#!/usr/bin/env python3
"""Hero temper (verdance.company.temper): the camp's bonds, wounds and griefs as each hero's nerve and
drive on a drop, which the field uses to scale the hero's doctrine (owner direction 2026-11-09: mood
moves with camp interactions, and behaviour in the game moves with it)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.company import temper as T  # noqa: E402
from verdance.company.attachments import apply_pair_talk  # noqa: E402


def _state():
    return {"roster": {"heroes": [{"heroId": h, "status": "active", "level": 1} for h in ("vane", "ketha", "halbard", "pavise")]},
            "characters": {}, "attachments": {}}


def test_a_fresh_company_is_level():
    out = T.temper_for_drop(_state(), ["halbard", "pavise"], ROOT)
    assert out == {"halbard": {"nerve": 0.0, "drive": 0.0}, "pavise": {"nerve": 0.0, "drive": 0.0}}


def test_camp_talks_steady_the_pair_on_the_same_drop():
    st = _state()
    before = T.temper_for_drop(st, ["halbard", "pavise"], ROOT)["halbard"]
    for i in range(4):
        apply_pair_talk(st, "halbard", "pavise", talk_id=f"t{i}")     # four camp talks, 32 bond points
    after = T.temper_for_drop(st, ["halbard", "pavise"], ROOT)["halbard"]
    assert after["nerve"] > before["nerve"] + 0.2 and after["drive"] > before["drive"]
    alone = T.temper_for_drop(st, ["halbard"], ROOT)["halbard"]
    assert alone["nerve"] == 0.0                                        # the bond steadies only when both drop


def test_wounds_and_grief_shake_a_hero():
    st = _state()
    apply_pair_talk(st, "vane", "ketha", delta=40)
    st["roster"]["heroes"][0].update(status="wounded", timesWounded=3)      # vane
    st["roster"]["heroes"][2]["status"] = "dead"                             # halbard
    apply_pair_talk(st, "vane", "halbard", delta=30)
    t = T.temper_for_drop(st, ["vane", "ketha"], ROOT)["vane"]
    assert t["nerve"] < 0 and t["drive"] < T.temper_for_drop(_state(), ["vane"], ROOT)["vane"]["drive"] + 0.5
    assert -1 < t["nerve"] < 1 and -1 < t["drive"] < 1


def test_a_rival_on_the_drop_unsettles():
    rivals = [e for e in T._web_polarity(ROOT).items() if e[1] in T.ADVERSARY]
    assert rivals, "the support web has rivalries"
    a, b = sorted(rivals[0][0])
    st = {"roster": {"heroes": [{"heroId": a, "level": 1}, {"heroId": b, "level": 1}]}, "attachments": {}}
    apply_pair_talk(st, a, b, delta=50)
    assert T.temper_for_drop(st, [a, b], ROOT)[a]["nerve"] < 0


def test_the_field_reads_temper_and_scales_a_copy_of_the_doctrine():
    lua = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_unit_behavior.lua").read_text(encoding="utf-8")
    assert "m.heroTemper" in lua and "doctrine = withTemper(doctrine, hid)" in lua
    assert "for k, v in pairs(doctrine) do out[k] = v end" in lua         # never scale a shared profile
