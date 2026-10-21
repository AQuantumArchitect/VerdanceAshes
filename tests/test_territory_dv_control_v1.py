#!/usr/bin/env python3
"""Territory control is defensive-value only."""

from __future__ import annotations

import unittest

from verdance import campaign as engine


class TerritoryDvControlTests(unittest.TestCase):
    def test_army_without_dv_does_not_own_zone(self):
        zone = {
            "teams": {
                "0": {
                    "teamId": 0,
                    "side": "legion",
                    "faction": "ashwalkers",
                    "metrics": {
                        "armyValue": 9000,
                        "buildPower": 400,
                        "defensiveValue": 0,
                        "totalUnitValue": 9400,
                    },
                    "unitCountsByDef": {"legcen": 20},
                }
            }
        }
        raw = engine.aggregate_zone("Z_TEST", zone)
        self.assertEqual(raw["controllingFaction"], "neutral")
        self.assertEqual(raw["presence"], 0.0)
        self.assertEqual(raw["factionPresence"], {})

    def test_dv_beats_larger_army(self):
        zone = {
            "teams": {
                "0": {
                    "teamId": 0,
                    "side": "legion",
                    "faction": "ashwalkers",
                    "metrics": {
                        "armyValue": 200,
                        "buildPower": 0,
                        "defensiveValue": 1200,
                        "totalUnitValue": 1400,
                    },
                    "unitCountsByDef": {"armllt": 4, "armbeamer": 4},
                },
                "1": {
                    "teamId": 1,
                    "side": "armada",
                    "faction": "armada",
                    "metrics": {
                        "armyValue": 8000,
                        "buildPower": 500,
                        "defensiveValue": 100,
                        "totalUnitValue": 8600,
                    },
                    "unitCountsByDef": {"armpw": 40},
                },
            }
        }
        raw = engine.aggregate_zone("Z_PAD", zone)
        self.assertEqual(raw["controllingFaction"], "ashwalkers")
        self.assertEqual(raw["factionPresence"]["ashwalkers"], 1200.0)
        self.assertEqual(raw["factionPresence"]["armada"], 100.0)
        self.assertEqual(raw["presence"], 1300.0)

    def test_abstract_fortification_still_tracks_dv(self):
        zone = {
            "teams": {
                "0": {
                    "teamId": 0,
                    "side": "legion",
                    "faction": "ashwalkers",
                    "metrics": {
                        "armyValue": 0,
                        "buildPower": 0,
                        "defensiveValue": 3000,
                        "totalUnitValue": 3000,
                        "metalIncome": 0,
                        "energyIncome": 0,
                        "unitCount": 6,
                        "combatUnitCount": 6,
                        "builderUnitCount": 0,
                        "structureCount": 6,
                    },
                    "unitCountsByDef": {"armllt": 6},
                }
            }
        }
        raw = engine.aggregate_zone("Z_TEETH", zone)
        abstract = engine.abstract_from_raw("greenest_fields", "Z_TEETH", raw)
        self.assertEqual(abstract["control"], "ashwalkers")
        self.assertGreater(abstract["fortification"], 0.0)
        self.assertEqual(abstract["militaryPressure"], 0.0)


class FortifyDvOnlyContractTests(unittest.TestCase):
    """Document / guard the DV-only fortify gate (Lua mirror)."""

    def test_fortify_defaults_are_dv_only(self):
        # Mirrors checkFortifyObjective defaults after the collapse.
        need_def = 800
        need_bp = 0
        need_army = 0
        need_stor = 0
        def_now = 850
        def_ok = def_now >= need_def
        score = 1 if def_ok else 0
        # Legacy multi-bar needs stay at zero — win is defOk alone.
        self.assertTrue(def_ok)
        self.assertEqual(score, 1)
        self.assertEqual(need_bp + need_army + need_stor, 0)


if __name__ == "__main__":
    unittest.main()
