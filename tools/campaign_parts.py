#!/usr/bin/env python3
"""Keep the campaign gadget's parts honest (game_verdance_campaign.lua + include/campaign/*.lua).

The parts share one gadget environment, so a name one part defines as a global is visible to every
other part, and a name a part keeps `local` is visible to nobody else. Two things go wrong silently:

  * a part calls something another part made `local`: in Lua that is a read of a global that
    does not exist, and it fails only when that line runs;
  * the "Provides:" / "Uses:" lines at the top of a part drift from what the code does.

    python3 tools/campaign_parts.py            # report both; exit 1 on a problem
    python3 tools/campaign_parts.py --fix      # rewrite the Provides / Uses header lines

Names the engine gives every gadget (Spring, VFS, math, ...) are not the parts' business.
"""
from __future__ import annotations

import collections
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import campaign_lua  # noqa: E402
import lua_scope  # noqa: E402

ENGINE = set("""Spring VFS GG Game UnitDefs UnitDefNames FeatureDefs FeatureDefNames WeaponDefs WeaponDefNames
CMD CMDTYPE COB SFX LOG Script Engine Platform gl GL COBSCALE CallAsTeam SendToUnsynced SYNCED Json
math string table os io debug coroutine package tracy type pairs ipairs next tostring tonumber select
unpack pcall xpcall error assert rawget rawset rawequal setmetatable getmetatable print loadstring load
loadfile dofile require collectgarbage gcinfo getfenv setfenv pairsByKeys snext spairs sipairs _VERSION
_G gadget gadgetHandler include _""".split())


def _owners(files):
    """name -> part that defines it at top level (a function beats a plain assignment)."""
    owner, rank = {}, {}
    for part, path in files.items():
        for it in lua_scope.items(path.read_text(encoding="utf-8")):
            if it["kind"] not in ("global_fn", "global_var"):
                continue
            base = it["names"][0].split(".")[0].split(":")[0]
            if not base or base in ENGINE:
                continue
            r = 2 if it["kind"] == "global_fn" else 1
            if r > rank.get(base, 0):
                owner[base], rank[base] = part, r
    return owner


def analyse():
    files = dict(campaign_lua.parts())
    owner = _owners(files)
    assigned = set(owner)
    for path in files.values():
        assigned |= set(re.findall(r"(?m)^\s*([A-Za-z_]\w*)\s*=[^=]", path.read_text(encoding="utf-8")))
    provides = collections.defaultdict(set)
    uses = collections.defaultdict(set)
    undefined = []
    for part, path in files.items():
        refs = lua_scope.Resolver(path.read_text(encoding="utf-8")).run().refs
        for (line, _o), (name, b) in sorted(refs.items()):
            if b[0] != "G" or name in ENGINE:
                continue
            if name not in assigned:
                undefined.append((part, line, name))
                continue
            o = owner.get(name)
            if o and o != part:
                provides[o].add(name)
                uses[part].add(o)
    return files, provides, uses, undefined


def header_lines(part, provides, uses):
    out = []
    if provides.get(part):
        out += ["-- " + w for w in textwrap.wrap("Provides: " + ", ".join(sorted(provides[part])), 96)]
    if uses.get(part):
        out += ["-- " + w for w in textwrap.wrap("Uses: " + ", ".join(sorted(uses[part])), 96)]
    return out


def _split_header(text):
    """(the part's three-line preamble, its Provides/Uses lines, the rest). The Provides/Uses block
    follows the preamble and ends at the first blank line."""
    lines = text.split("\n")
    head, i = lines[:3], 3
    cur = []
    while i < len(lines) and lines[i].startswith("-- "):
        cur.append(lines[i])
        i += 1
    return head, cur, lines[i:]


def main(argv):
    fix = "--fix" in argv
    files, provides, uses, undefined = analyse()
    stale = []
    for part, path in files.items():
        if part == "core":
            continue
        text = path.read_text(encoding="utf-8")
        head, cur, rest = _split_header(text)
        want = header_lines(part, provides, uses)
        if cur != want:
            stale.append(part)
            if fix:
                path.write_text("\n".join(head + want + rest), encoding="utf-8")
    for part, line, name in undefined:
        print(f"UNDEFINED {part}.lua:{line}: {name} is read as a global but no part defines it "
              f"(a `local` in another part?)")
    if stale and not fix:
        for part in stale:
            print(f"STALE HEADER {part}.lua; want:\n  " + "\n  ".join(header_lines(part, provides, uses)))
        print("run: python3 tools/campaign_parts.py --fix")
    elif stale:
        print("rewrote headers:", ", ".join(stale))
    ok = not undefined and (fix or not stale)
    if ok:
        print(f"campaign parts OK: {len(files)} files")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
