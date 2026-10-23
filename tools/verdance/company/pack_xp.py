#!/usr/bin/env python3
"""Starting XP from what a hero's whole pack costs.

A pack is the hero, its extras (more of the hero's chassis) and its escorts. Its cost is
metal + energy / energyPerMetal (BAR's metal-equivalent), from data/story/unit_costs.json.
Cheap packs start seasoned; a pack as dear as the Javelin pair (packAnchor.javelinPair,
the premium reference) or dearer starts green:

    startXp = xpCurve.max * max(0, 1 - packCombined / xpCurve.zeroAt)

Writes packMetal / packEnergy / packCombined / startXp into crew_packs.json, the hub's
crew_packs.embed.js and the gadget roster (va_crew_roster.lua). Run after changing a pack:

    python3 tools/verdance/company/pack_xp.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKS = ROOT / "data" / "story" / "crew_packs.json"
COSTS = ROOT / "data" / "story" / "unit_costs.json"
EMBED = ROOT / "app" / "showoff" / "crew_packs.embed.js"
ROSTER_LUA = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_crew_roster.lua"


def pack_units(pack: dict) -> list[tuple[str, int]]:
    units = [(str(pack.get("unitDef")), 1 + int(pack.get("extras") or 0))]
    for e in pack.get("escorts") or []:
        if isinstance(e, dict) and e.get("unitDef"):
            units.append((str(e["unitDef"]), int(e.get("count") or 1)))
    return units


def pack_cost(pack: dict, costs: dict, epm: float) -> tuple[float, float, float]:
    metal = energy = 0.0
    for ud, n in pack_units(pack):
        if ud not in costs:
            raise KeyError(f"no cost for {ud}: add it to {COSTS.name}")
        m, e = costs[ud]
        metal += m * n
        energy += e * n
    return metal, energy, metal + energy / epm


def start_xp(combined: float, curve: dict) -> float:
    return round(max(0.0, float(curve["max"]) * (1.0 - combined / float(curve["zeroAt"]))), 3)


def main() -> int:
    packs = json.loads(PACKS.read_text(encoding="utf-8-sig"))
    costs = json.loads(COSTS.read_text(encoding="utf-8-sig"))["units"]
    epm = float(packs.get("energyPerMetal") or 70)
    curve = packs.setdefault("xpCurve", {"max": 0.5, "zeroAt": (packs.get("packAnchor") or {}).get("javelinPair", {}).get("combined", 3000),
                                         "notes": "startXp = max * (1 - packCombined / zeroAt), floor 0. zeroAt = the Javelin pair."})
    rows = []
    for hid, pack in packs["heroes"].items():
        metal, energy, combined = pack_cost(pack, costs, epm)
        pack["packMetal"], pack["packEnergy"], pack["packCombined"] = round(metal), round(energy), round(combined)
        pack["startXp"] = start_xp(combined, curve)
        rows.append((pack["startXp"], round(combined), hid))
    PACKS.write_text(json.dumps(packs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    EMBED.write_text("window.CREW_PACKS = " + json.dumps(packs, indent=2, ensure_ascii=False) + ";\n", encoding="utf-8")
    lua = ROSTER_LUA.read_text(encoding="utf-8")
    for hid, pack in packs["heroes"].items():
        m = re.search(r"\n  " + re.escape(hid) + r" = \{\n(.*?)\n  \},", lua, re.S)
        if not m:
            continue
        block = m.group(1)
        new = re.sub(r"startXp = [0-9.]+,", f"startXp = {pack['startXp']},", block, count=1)
        if new == block and "startXp" not in block:
            new = block + f"\n    startXp = {pack['startXp']},"
        lua = lua[:m.start(1)] + new + lua[m.end(1):]
    ROSTER_LUA.write_text(lua, encoding="utf-8")
    for xp, c, hid in sorted(rows, reverse=True):
        print(f"{hid:14s} pack {c:6d}  startXp {xp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
