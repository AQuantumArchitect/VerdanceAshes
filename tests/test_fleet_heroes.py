#!/usr/bin/env python3
"""Second wave of new heroes (owner, 2026-10-26): Phoenix, Tarn's Salamanders, Scylla, Tsunami's
seaplane wing; the Wasp flight is a dear Cortex mercenary; the surplus Pawns left the shop."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "data" / "story"


def _j(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


PACKS, CODEX, ROSTER = _j(S / "crew_packs.json"), _j(S / "hero_codex.json"), _j(S / "hero_roster.json")
UMWELT = _j(S / "hero_umwelt.json")
LUA = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_crew_roster.lua").read_text(encoding="utf-8")
TAGS = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_hero_tags.lua").read_text(encoding="utf-8")
CO = ROOT / "tools/verdance/company/company.py"
WANT = {  # hero: (unit, packTotal, escorts)
    "phoenix": ("legphoenix", 2, {}),
    "tarn": ("corsala", 5, {}),
    "scylla": ("leganavybattleship", 1, {}),
    "tsunami": ("armsb", 4, {"armsehak": 3}),
}


def test_each_new_hero_is_wired_everywhere():
    costs = _j(S / "unit_costs.json")
    for h, (unit, total, esc) in WANT.items():
        p = PACKS["heroes"][h]
        assert (p["unitDef"], p["packTotal"], p["extras"]) == (unit, total, total - 1)
        assert {e["unitDef"]: e["count"] for e in p.get("escorts", [])} == esc
        for u in [unit, *esc]:
            assert u in PACKS["chassis"] and u in costs["units"], u
        assert p["packCombined"] > 0 and 0 <= p["startXp"] <= 0.5
        assert next(x for x in CODEX["heroes"] if x["heroId"] == h)["unitDef"] == unit
        assert next(x for x in ROSTER["heroes"] if x["heroId"] == h)["status"] == "locked"
        assert any(x["heroId"] == h for x in UMWELT["heroes"])
        block = re.search(r"\n  " + h + r" = \{\n(.*?)\n  \},", LUA, re.S).group(1)
        assert f'unitDef = "{unit}"' in block and f"packTotal = {total}" in block
        assert f'"{h}"' in LUA.split("M.BAND_ORDER", 1)[1]
        assert re.search(rf"\b{h} = \{{ \"\w+\" \}}", TAGS)
        assert f'"{h}": [' in CO.read_text(encoding="utf-8")


def test_wasp_is_a_dear_cortex_merc_and_pawns_are_gone():
    L = _j(ROOT / "data/commerce/commerce_catalog.json")["listings"]
    assert "armada_surplus_pawns" not in L
    w = L["wasp_flight"]
    assert w["unitDef"] == "corape" and w["shelf"] == "cortex" and w["metalCostK"] >= 9
    assert w["metalCostK"] > max(v["metalCostK"] for k, v in L.items() if k != "wasp_flight")
    sp = _j(ROOT / "data/commerce/print_spaces.json")["spaces"]
    assert "wasp_flight" in sp["eye_of_horus"]["listings"]
    assert "armada_surplus_pawns" not in sp["pawn_launcher"]["listings"]
    assert not any(p["heroId"] == "wasp" for p in CODEX["heroes"])


def test_the_new_pairs_are_authored():
    web = _j(S / "support_web.json")
    ids = {frozenset((e["a"], e["b"])) for e in web["edges"]}
    for a, b in (("phoenix", "thresh"), ("tarn", "odessa"), ("scylla", "halq"), ("tsunami", "gale")):
        assert frozenset((a, b)) in ids
