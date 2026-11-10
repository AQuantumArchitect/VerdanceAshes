#!/usr/bin/env python3
"""Umwelt Engine v0.2.1 pin: the breaks that touch this game, and nothing broader.

  * umwelt.consumers is gone; this tree does not import it
  * validate_spec is strict; the world spec and the camp-temper spec pass it
  * forecast confidence may be None (DARK), and a non-finite Bloch vector is not a pole
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_game_does_not_import_removed_umwelt_consumers():
    pat = re.compile(r"(?m)^(?:from|import)\s+umwelt\.consumers\b")
    hits = []
    for path in (ROOT / "tools").rglob("*.py"):
        if pat.search(path.read_text(encoding="utf-8", errors="replace")):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_a_missing_forecast_confidence_is_dark_not_zero():
    from verdance.belief.world import finite_bloch, read_confidence
    assert read_confidence(None) is None
    assert read_confidence(float("nan")) is None
    assert read_confidence(float("inf")) is None
    assert read_confidence(0.0) == 0.0
    assert read_confidence(0.42) == 0.42
    # RK4 guard: a refused non-finite step is DARK, not a -1 pole.
    assert finite_bloch((float("nan"), 0.0, -1.0)) == (0.0, 0.0, 0.0)
    assert finite_bloch((0.1, -0.2, 0.3)) == (0.1, -0.2, 0.3)


def test_game_specs_pass_validate_spec():
    from verdance.belief import world as W
    if not W.umwelt_available():
        raise unittest.SkipTest("umwelt not importable (UMWELT_SRC)")
    from umwelt import validate_spec
    from verdance.company.temper import build_temper_spec
    world = W.build_spec(ROOT)
    report = validate_spec(world)
    assert report.ok, report.summary()
    schema, _api = W._umwelt()
    temper, _node, _couplings, _mourned = build_temper_spec(
        schema,
        ["pavise", "halbard"],
        [("pavise", "halbard", 0.4)],
        [("pavise", "ceil", 0.5)],
    )
    temper_report = validate_spec(temper)
    assert temper_report.ok, temper_report.summary()
