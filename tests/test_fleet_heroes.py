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
    "scylla": ("leganavybattleship", 1, {}),
    "tsunami": ("armsb", 1, {"legspbomber": 2, "armpeep": 5}),
    # the kit export (2026-10-26), as recast on 2026-10-28
    "starlight": ("armmanni", 1, {"armfast": 4}),
    "banisher": ("corban", 3, {}),
    "arrow": ("corparrow", 1, {"corsala": 6}),
    "hornet": ("armblade", 2, {}),
    "charybdis": ("legehovertank", 1, {}),
    "shiva": ("corshiva", 1, {}),
    "tremor": ("cortrem", 1, {"corspec": 1, "corfav": 5}),
    "stiletto": ("armstil", 3, {"legwhisper": 1}),
    "lunkhead": ("armlun", 1, {"legcar": 2}),
    "stronghold": ("legstronghold", 1, {"armhawk": 4, "armkam": 5}),
    "possum": ("armmh", 1, {"legsh": 4, "legmh": 5, "legah": 2}),
    "loom": ("armspid", 6, {"legbal": 6}),
    "hundred": ("legspcarrier", 1, {"legamcluster": 2}),
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
    # the dearest mercenary package (heroes for hire are dearer still, and metal-only)
    assert w["metalCostK"] > max(v["metalCostK"] for k, v in L.items()
                                 if k != "wasp_flight" and v.get("kind") == "purchase_package")
    sp = _j(ROOT / "data/commerce/print_spaces.json")["spaces"]
    assert "wasp_flight" in sp["eye_of_horus"]["listings"]
    assert "armada_surplus_pawns" not in sp["pawn_launcher"]["listings"]
    assert not any(p["heroId"] == "wasp" for p in CODEX["heroes"])


def test_the_new_pairs_are_authored():
    web = _j(S / "support_web.json")
    ids = {frozenset((e["a"], e["b"])) for e in web["edges"]}
    for a, b in (("phoenix", "thresh"), ("hundred", "noctua"), ("scylla", "halq"), ("tsunami", "gale")):
        assert frozenset((a, b)) in ids


def test_kit_export_particulars():
    h = PACKS["heroes"]
    assert h["lunkhead"]["startXpFixed"] == 0.45 and h["lunkhead"]["startXp"] == 0.45   # the showcase high-XP hero
    assert h["hornet"]["packMind"] == "pair" and h["hornet"]["partners"] == ["Saffi"]       # the Marsh sisters
    kit = {e["unitDef"]: e["count"] for e in h["kit"]["escorts"]}
    assert kit["leghrk"] == 1 and kit["legbar"] == 1                                    # Kit took the napalm park
    assert h["mira"]["unitDef"] == "armmart" and h["mira"]["packTotal"] == 5            # Mira: a Mauser firing line
    block = re.search(r"\n  kit = \{\n(.*?)\n  \},", LUA, re.S).group(1)
    assert 'unitDef = "leghrk"' in block


def test_every_hero_has_authored_ties_and_a_node():
    web = _j(S / "support_web.json")
    deg = {}
    for e in web["edges"]:
        if e.get("authored"):
            for h in (e["a"], e["b"]):
                deg[h] = deg.get(h, 0) + 1
    nodes = {n["heroId"] for n in web["nodes"]}
    for h in PACKS["heroes"]:
        assert h in nodes, h
        assert deg.get(h, 0) >= 2, (h, deg.get(h, 0))
    talks = _j(S / "camp_talks_authored.json")["talks"]
    assert all(len(t["beats"]) >= 3 for t in talks if t["pairId"].split("__")[0] in WANT)
