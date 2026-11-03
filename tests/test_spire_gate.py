"""The Spire Jump (finale C): finish the Spire Gate, power it from the generators around it, port the named heroes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import acts  # noqa: E402
from verdance.world import spire_gate as G  # noqa: E402


def test_finale_c_is_the_gate_not_a_hive_burn():
    obj = acts.FINALE_PLANS["C"]["objective"]
    assert acts.FINALE_PLANS["C"]["mapId"] == "the_rock_jungle"
    assert obj["kind"] == "jump_gate"


def test_the_card_names_the_power_the_gate_wants():
    gate = G.jump_gate(ROOT)
    words = f"{gate['needPower']:,} energy a second"
    assert words in acts.FINALE_PLANS["C"]["objective"]["label"]
    from verdance.readings import narrative
    assert words in Path(narrative.__file__).read_text(encoding="utf-8")


def test_the_gate_wants_power_a_t1_company_can_raise():
    # The company raises T2 labs only on All That Simmers (game_verdance_lab_tier.lua), so a gate
    # on the Rock Jungle that wants advanced fusions cannot be powered: it counts any generator.
    gate = G.jump_gate(ROOT)
    assert gate and 0 < gate["needPower"] <= 3000 and "needAfus" not in gate
    assert gate["zoneId"] == "TRJ_NW_MUSTER"          # not the spillways' water; the hive holds those
    assert 0 < gate["x"] < 0.5 and 0 < gate["z"] < 0.5
    assert gate["channelSeconds"] > 0 and gate["chargeSeconds"] > 0


def test_the_campaign_gadget_takes_only_the_gates_word_for_it():
    import campaign_lua
    lua = campaign_lua.source()
    assert 'VA_GADGET_KINDS = { jump_gate = "jumped" }' in lua
    gate = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_jump_gate.lua").read_text(encoding="utf-8")
    assert 'GG.VA_ObjectiveComplete("jumped")' in gate
