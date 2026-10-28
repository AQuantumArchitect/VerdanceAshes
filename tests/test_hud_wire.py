"""Every signal between the gadgets and the HUD has both ends (tools/hud_wire.py).

Rules params a widget reads, the events the synced side sends and the kinds inside them, the
VA_CMD commands widgets send, and WG fields: a one-ended signal is a HUD showing nothing, or a
gadget talking to nobody.
"""
from __future__ import annotations

import hud_wire


def test_no_hud_signal_has_only_one_end():
    cut = hud_wire.hud_problems()
    assert not cut, "\n".join(f"{what}: {name} ({', '.join(where[:3])})" for what, name, where in cut)


def test_the_scan_sees_the_wire():
    params, events, luaui_fns, cmds, wg, vocab = hud_wire.scan()
    assert ("Game", "va_hud_heroes_json") in params and params[("Game", "va_hud_heroes_json")]["r"]
    assert events["VERDANCE_MISSION_EVENT"]["send"] and events["VERDANCE_MISSION_EVENT"]["catch"]
    sent, heard = vocab["VERDANCE_MISSION_EVENT"]
    assert "sortie_over" in sent and "sortie_over" in heard
    assert cmds["manifest"]["send"] and cmds["manifest"]["handle"]
