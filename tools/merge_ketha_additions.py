#!/usr/bin/env python3
"""Merge data/story/ketha_voice.additions.json into data/story/ketha_voice.json.

Idempotent: existing lines are kept, duplicates are not added, pool order is
preserved, and the notes field records the in-Drop / between-Drop split.
Prints a per-pool count so you can see the depth after the merge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "data" / "story" / "ketha_voice.json"
ADD = ROOT / "data" / "story" / "ketha_voice.additions.json"

SPLIT_NOTE = (" In-Drop voice (BAR HUD barks, pre-seeded debrief candidates) lives here and is hash-seeded per mission."
              " Between-Drop voice (hub briefing, debrief, camp, roll) comes from data/story/voices/*.json via"
              " tools/occasions_v1.py and is keyed by event class, reading and attractor, not mission number.")


def main() -> int:
    voice = json.loads(VOICE.read_text(encoding="utf-8-sig"))
    add = json.loads(ADD.read_text(encoding="utf-8-sig"))
    pools = voice.setdefault("pools", {})
    added = 0
    for key, lines in (add.get("pools") or {}).items():
        pool = pools.setdefault(key, [])
        for line in lines:
            if line not in pool:
                pool.append(line)
                added += 1
    notes = str(voice.get("notes") or "")
    if "Between-Drop voice" not in notes:
        voice["notes"] = notes.rstrip() + SPLIT_NOTE
    VOICE.write_text(json.dumps(voice, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"added {added} lines")
    for key in sorted(pools):
        if key.startswith(("debrief.", "bark.")):
            print(f"  {key:<34} {len(pools[key])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
