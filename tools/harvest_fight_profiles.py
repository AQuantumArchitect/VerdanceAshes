#!/usr/bin/env python3
"""Harvest every unit's fight profile from an autopilot infolog into data/story/unit_fight.json.

The engine's own numbers (include/va_safety_field.lua, M.profile, from BAR's unit and weapon defs):
fight = (dps x hp)^1/2, Lanchester's per-unit strength, the measure the in-game safety field uses. The
hub's reckoning of a job against the company reads this file, so both sides of the game weigh armies
alike. Make it with one short autopilot run:

    python tools/autopilot_campaign_v1.py --stock --sorties 1 --minutes 1 --modopt va_autopilot_profiles=1
    python tools/harvest_fight_profiles.py autopilot_runs/<run>/sortie_01.infolog.txt
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "story" / "unit_fight.json"
LINE = re.compile(r"VA_FIGHT_PROFILE (\S+) fight=([\d.]+) dps=([\d.]+) hp=([\d.]+) range=([\d.]+) speed=([\d.]+)")


def harvest(infolog: Path) -> dict:
    units = {}
    for line in infolog.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE.search(line)
        if m:
            name, fight, dps, hp, rng, speed = m.groups()
            units[name] = {"fight": round(float(fight), 3), "dps": round(float(dps), 3), "hp": round(float(hp), 1),
                           "range": round(float(rng), 1), "speed": round(float(speed), 3)}
    return {"schema": "verdance-unit-fight/1",
            "source": "va_safety_field.lua M.profile over BAR's UnitDefs and WeaponDefs, echoed by the autopilot "
                      "(va_autopilot_profiles=1) and harvested by tools/harvest_fight_profiles.py",
            "units": dict(sorted(units.items()))}


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = harvest(Path(argv[1]))
    if not data["units"]:
        print("no VA_FIGHT_PROFILE lines in", argv[1])
        return 1
    OUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(data['units'])} units)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
