"""The finale path is read off the company's belief questions (verdance.belief.world.path_signals)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verdance.belief.world import QUESTIONS, path_signals  # noqa: E402
from verdance.campaign.acts import finale_path_for_state  # noqa: E402


def frame(**z):
    return {"questions": [{"id": q, "pole_0": spec["pole_0"], "bloch": [0, 0, z.get(q, 0.0)]} for q, spec in QUESTIONS.items()]}


def test_open_questions_give_no_signal():
    assert path_signals(frame()) == {"A": 0.0, "B": 0.0, "C": 0.0}


def test_sovereign_company_reads_b():
    s = path_signals(frame(whose_war=0.8, whose_paper=0.6))  # pole_0 is sovereign on both
    assert s["B"] == 0.7 and s["A"] == 0.0


def test_auxiliary_against_falling_armada_reads_a():
    s = path_signals(frame(whose_war=-0.9, pressure=0.5))  # whose_war -z is auxiliary; pressure +z is armada_falling
    assert s["A"] == 0.7 and s["B"] == 0.0


def test_rooted_company_reads_c_and_picks_it():
    s = path_signals(frame(home_or_hospital=0.9, go_back=0.7))
    assert s["C"] == 0.8
    state = {"graph": {"pathSignal" + k: v for k, v in s.items()}, "pathSignal": "B"}
    assert finale_path_for_state(state) == "C"
