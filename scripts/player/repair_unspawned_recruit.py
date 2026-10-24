#!/usr/bin/env python3
"""Put a wild field recruit back in the field after their wreck failed to spawn.

The building-chassis heroes (Noctua's bay, Warder's turret) could fail BAR's CreateUnit on rough
ground; the gadget then had no wreck to rez, and the homecoming marked the hero lost. This undoes
that for the named heroes: the fieldPool entry goes back to wild, the roster sheet back to locked,
and the character back to active. A backup of the state is written first.

    python scripts/player/repair_unspawned_recruit.py noctua [more ids] [--state state/campaign_state.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path


def repair(state: dict, hero_ids: list[str]) -> list[str]:
    fixed = []
    pool = state.get("fieldPool") or {}
    for hid in hero_ids:
        entry = pool.get(hid)
        if not isinstance(entry, dict) or entry.get("status") != "lost":
            continue
        entry["status"] = "wild"
        entry.pop("lostAt", None)
        entry.pop("lostReason", None)
        for sheet in (state.get("roster") or {}).get("heroes") or []:
            if isinstance(sheet, dict) and sheet.get("heroId") == hid and sheet.get("status") == "dead":
                sheet["status"] = "locked"
        ch = (state.get("characters") or {}).get(hid)
        if isinstance(ch, dict) and ch.get("status") == "dead":
            ch["status"] = "active"
        fixed.append(hid)
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("heroes", nargs="+")
    ap.add_argument("--state", default="state/campaign_state.json")
    args = ap.parse_args()
    path = Path(args.state)
    raw = path.read_bytes()
    state = json.loads(raw.decode("utf-8-sig"))
    fixed = repair(state, args.heroes)
    if fixed:
        backup = path.with_name(f"campaign_state.before_recruit_repair_{time.strftime('%Y%m%d_%H%M%S')}.json")
        shutil.copy2(path, backup)
        newline = "\r\n" if b"\r\n" in raw[:200] else "\n"     # keep the file's own line endings
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(json.dumps(state, indent=2) + "\n")
        print(f"back in the field: {', '.join(fixed)} (backup {backup.name})")
    else:
        print("nothing to repair")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
