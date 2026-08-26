"""Unit tests for UniversalLearner pilot on bar_brain width_action."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
UMWELT = Path(r"C:\Users\Luke Spooner\ws-win\umwelt\src")
for p in (str(TOOLS), str(UMWELT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _synthetic_result(won: bool, action: str = "PUSH_OBJECTIVE", width: str = "open", n: int = 8):
    tape = []
    for i in range(n):
        tape.append(
            {
                "action": action,
                "hud": {"phase": "CONTACT", "contact": "light", "objective_bar": "mid", "eco_feel": "steady", "width_band": width},
                "_truth": {"progress": 0.9 if won else 0.2, "heroes_alive_frac": 0.9 if won else 0.3, "eco": 0.5},
            }
        )
    return {
        "won": won,
        "player_card": {"kind": "seize_lane", "width_band": width},
        "tape": tape,
        "progress": 0.9 if won else 0.2,
        "heroes_alive_frac": 0.9 if won else 0.3,
    }


class TestBarBrainUL(unittest.TestCase):
    def test_win_vs_loss_moves_params_opposite(self):
        from quantum_bar_ai.bar_brain_ul import WidthActionUL, _param_key
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        ul = WidthActionUL.from_weights(seed_manifold_priors())
        key = _param_key("open", "PUSH_OBJECTIVE")
        v0 = float(ul.params[key].value)

        ul.learn_from_result(_synthetic_result(True, "PUSH_OBJECTIVE", "open"))
        v_win = float(ul.params[key].value)

        ul2 = WidthActionUL.from_weights(seed_manifold_priors())
        ul2.learn_from_result(_synthetic_result(False, "PUSH_OBJECTIVE", "open"))
        v_loss = float(ul2.params[key].value)

        # win: negative surprise raises preference; loss: positive lowers it
        self.assertGreater(v_win, v0 - 1e-9)
        self.assertLess(v_loss, v0 + 1e-9)
        self.assertGreater(v_win, v_loss)

    def test_sigma_shrinks(self):
        from quantum_bar_ai.bar_brain_ul import WidthActionUL, _param_key
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        ul = WidthActionUL.from_weights(seed_manifold_priors())
        key = _param_key("open", "FLANK")
        s0 = float(ul.params[key].sigma)
        for _ in range(5):
            ul.learn_from_result(_synthetic_result(True, "FLANK", "open", n=6))
        s1 = float(ul.params[key].sigma)
        self.assertLess(s1, s0)
        self.assertGreater(ul.params[key].update_count, 0)

    def test_roundtrip_save_load(self):
        from quantum_bar_ai.bar_brain_ul import WidthActionUL, save_ul_state, load_ul_state
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        ul = WidthActionUL.from_weights(seed_manifold_priors())
        ul.learn_from_result(_synthetic_result(True, "PROBE", "narrow"))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ul.json"
            save_ul_state(ul, path=path)
            loaded = load_ul_state(path=path, weights=seed_manifold_priors())
            self.assertEqual(loaded.missions, ul.missions)
            self.assertAlmostEqual(
                float(loaded.params["narrow|PROBE"].value),
                float(ul.params["narrow|PROBE"].value),
                places=4,
            )

    def test_project_to_weights(self):
        from quantum_bar_ai.bar_brain_ul import WidthActionUL
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        w = seed_manifold_priors()
        ul = WidthActionUL.from_weights(w)
        ul.params["wide|FLANK"].value = 7.77
        ul.project_to_weights(w)
        self.assertAlmostEqual(w.width_action["wide"]["FLANK"], 7.77, places=2)

    def test_doctrine_prior_missing_ok(self):
        from quantum_bar_ai.bar_brain_ul import read_hive_doctrine_posture, WidthActionUL
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        # may be None if hive file missing — must not raise
        _ = read_hive_doctrine_posture()
        ul = WidthActionUL.from_weights(seed_manifold_priors())
        bumps = ul.apply_doctrine_prior("support_push")
        self.assertTrue(bumps)

    def test_eco_family_learns(self):
        from quantum_bar_ai.bar_brain_ul import WidthActionUL, _param_key, ECO_BANDS
        from quantum_bar_ai.bar_brain import seed_manifold_priors

        ul = WidthActionUL.from_weights(seed_manifold_priors())
        # eco cells exist
        for eco in ECO_BANDS:
            self.assertIn(_param_key(eco, "FALLBACK"), ul.params)
        key = _param_key("thin", "FALLBACK")
        v0 = float(ul.params[key].value)
        # synthetic loss under thin eco should discourage FALLBACK less than win encourages
        loss = _synthetic_result(False, "FALLBACK", "open", n=6)
        for row in loss["tape"]:
            row["hud"]["eco_feel"] = "thin"
        ul.learn_from_result(loss)
        v1 = float(ul.params[key].value)
        self.assertNotEqual(v0, v1)
        self.assertGreater(ul.params[key].update_count, 0)
        # project writes eco_action
        w = seed_manifold_priors()
        ul.project_to_weights(w)
        self.assertIn("thin", w.eco_action)
        self.assertIn("FALLBACK", w.eco_action["thin"])


if __name__ == "__main__":
    unittest.main()
