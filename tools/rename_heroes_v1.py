#!/usr/bin/env python3
"""Give heroes their proper names everywhere a name is written, without touching anything else
(and, in a save, move Halbard onto her own Halberd).

The data files keep their own formatting: only `"name": "<old>"` (JSON) and `name = "<old>",`
(the gadget roster) are rewritten, for the heroes in NAMES. With --state, a campaign save's cached
names (characters, roster sheets, field pool) are updated too, with a backup next to it.

    python tools/rename_heroes_v1.py                 # the repo's data
    python tools/rename_heroes_v1.py --state state/campaign_state.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# owner pass, 2026-10-24: callsigns kept, so the camp talks still read
NAMES = {
    "fatboy": ("Fatboy Contract", "Dorran 'Fatboy' Kell"),
    "halbard": ("Halbard", "Ilse 'Halbard' Varn"),
    "consul": ("Armada Consul", "Consul Aurel Weiss"),
    "twitch": ("Twitcher", "Benno 'Twitcher' Sallow"),
    "spoke": ("Spoke", "Ivo 'Spoke' Rask"),
    "tick": ("Tick Stream", "Tamsin 'Tick' Hollis"),
    "noctua": ("Noctua Bay", "Ada Noctua"),
    "verse": ("Verse Adder", "Verse & Adder"),
    "anvil": ("Anvil Mire", "Anvil & Mire"),
}

# the Halberd is now Halbard's own unit (heat ray) and the Archangel Saint Kettle's (radar-guided
# missiles); a save made before that still says corhal / armaak
UNITDEFS = {"halbard": ("corhal", "va_halberd"), "kettle": ("armaak", "va_kettle")}

DATA = ["data/story/hero_roster.json", "data/story/hero_codex.json", "data/story/crew_packs.json",
        "data/story/hero_umwelt.json", "data/story/support_web.json", "app/showoff/crew_packs.embed.js"]
ROSTER_LUA = "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_crew_roster.lua"


def rename_text(text: str, lua: bool) -> tuple[str, int]:
    n = 0
    for old, new in NAMES.values():
        a, b = ((f'name = "{old}",', f'name = "{new}",') if lua
                else (f'"name": "{old}"', f'"name": {json.dumps(new, ensure_ascii=False)}'))
        n += text.count(a)
        text = text.replace(a, b)
    return text, n


def rename_repo() -> None:
    for rel in DATA + [ROSTER_LUA]:
        p = ROOT / rel
        raw = p.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text, n = rename_text(raw.decode("utf-8-sig"), rel.endswith(".lua"))
        p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
        print(f"{rel}: {n} names")


def rename_state(path: Path) -> None:
    raw = path.read_bytes()
    state = json.loads(raw.decode("utf-8-sig"))
    n = 0
    for old, new in UNITDEFS.values():
        bank = (state.get("roster") or {}).get("cadreXp")      # her veterancy is banked by unit type
        if isinstance(bank, dict) and old in bank and new not in bank:
            bank[new] = dict(bank[old])
            n += 1
    for hid, (old, new) in UNITDEFS.items():
        for row in [(state.get("characters") or {}).get(hid), (state.get("fieldPool") or {}).get(hid)] + [
                h for h in (state.get("roster") or {}).get("heroes") or [] if isinstance(h, dict) and h.get("heroId") == hid]:
            if isinstance(row, dict) and row.get("unitDef") == old:
                row["unitDef"] = new
                n += 1
    for hid, (_old, new) in NAMES.items():
        for row in [(state.get("characters") or {}).get(hid), (state.get("fieldPool") or {}).get(hid)] + [
                h for h in (state.get("roster") or {}).get("heroes") or [] if isinstance(h, dict) and h.get("heroId") == hid]:
            if isinstance(row, dict) and row.get("name") != new:
                row["name"] = new
                n += 1
    if not n:
        print("save: nothing to change")
        return
    backup = path.with_name(f"campaign_state.before_rename_{time.strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy2(path, backup)
    newline = "\r\n" if b"\r\n" in raw[:200] else "\n"
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(json.dumps(state, indent=2) + "\n")
    print(f"save: {n} fields (backup {backup.name})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state")
    args = ap.parse_args()
    if args.state:
        rename_state(Path(args.state))
    else:
        rename_repo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
