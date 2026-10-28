"""The Spire Jump (finale C): finish the Spire Gate, power it with four advanced fusions, port the named heroes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import acts  # noqa: E402
from verdance.world import spire_gate as G  # noqa: E402


def test_finale_c_is_the_gate_not_a_hive_burn():
    obj = acts.FINALE_PLANS["C"]["objective"]
    assert acts.FINALE_PLANS["C"]["mapId"] == "the_rock_jungle"
    assert obj["kind"] == "jump_gate" and "four advanced fusions" in obj["label"]


def test_the_gate_stands_on_dry_company_ground_with_four_fusions_to_power_it():
    gate = G.jump_gate(ROOT)
    assert gate and gate["needAfus"] == 4
    assert gate["zoneId"] == "TRJ_NW_MUSTER"          # not the spillways' water; the hive holds those
    assert 0 < gate["x"] < 0.5 and 0 < gate["z"] < 0.5
    assert gate["channelSeconds"] > 0 and gate["chargeSeconds"] > 0


def test_the_campaign_gadget_takes_only_the_gates_word_for_it():
    import campaign_lua
    lua = campaign_lua.source()
    assert 'VA_GADGET_KINDS = { jump_gate = "jumped" }' in lua
    gate = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_jump_gate.lua").read_text(encoding="utf-8")
    assert 'GG.VA_ObjectiveComplete("jumped")' in gate
