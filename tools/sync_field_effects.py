#!/usr/bin/env python3
"""Check data/story/field_effects.json and write va_field_effects.lua from it.

    python3 tools/sync_field_effects.py          # check, then rewrite the Lua
    python3 tools/sync_field_effects.py --check  # exit 1 when the data is wrong or the Lua is out of date

Field effects v2 (2026-10-29): every hero has a self effect (itself and its pack, 20-40%, maybe
conditional) and one or two auras that reach the company members who match them (tags, axes, unit
names, unit kinds), at most +15% per stat in total. The generated Lua also carries what the auras
need at runtime and nobody else has in the gadget: each hero's tags and axes, the authored bond web
(ally +1, rival -1), and every map's pressure on the same axes (the home-ground rule).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "data" / "story"
LUA = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_field_effects.lua"

STATS = ("hp", "speed", "range", "reload", "build", "vision", "energy", "splash")
KINDS = ("stat", "income", "xp", "repair")
MATCH_KEYS = ("tags", "axes", "units", "kinds", "any", "self")
UNIT_KINDS = ("fusion",)
SCALE_BY = ("matching", "allies_near", "company_tag")
ALLY = {"bond", "attract", "sibling", "mentor", "mirror"}
ENEMY = {"rivalry", "tension", "friction"}


def _j(name):
    return json.loads((S / name).read_text(encoding="utf-8-sig"))


def validate(fx, packs, axes_names):
    errs = []
    rules, vocab, conds = fx["rules"], set(fx["tagVocab"]), set(fx["conditions"])
    lo, hi = rules["selfBonus"]
    heroes = fx["heroes"]
    if set(heroes) != set(packs):
        errs.append(f"heroes differ from crew_packs: {sorted(set(heroes) ^ set(packs))}")
    for hid, h in heroes.items():
        if not h.get("tags") or not set(h["tags"]) <= vocab:
            errs.append(f"{hid}: tags {h.get('tags')} not in the vocabulary")
        s = h.get("self") or {}
        if s.get("kind") != "stat" or s.get("stat") not in STATS:
            errs.append(f"{hid}: the self effect must be a stat")
        elif not (lo - 1e-9 <= s.get("bonus", 0) <= hi + 1e-9):
            errs.append(f"{hid}: self bonus {s.get('bonus')} outside {lo}-{hi}")
        if s.get("when") and s["when"] not in conds:
            errs.append(f"{hid}: self condition {s['when']}")
        if not h.get("auras"):
            errs.append(f"{hid}: no aura")
        for a in h.get("auras") or []:
            k = a.get("kind")
            if k not in KINDS:
                errs.append(f"{hid}: aura kind {k}")
                continue
            if k == "stat":
                if a.get("stat") not in STATS:
                    errs.append(f"{hid}: aura stat {a.get('stat')}")
                if not (0 < a.get("bonus", 0) <= rules["auraCap"] + 1e-9):
                    errs.append(f"{hid}: aura bonus {a.get('bonus')} above the {rules['auraCap']} ceiling")
            if k == "income" and a.get("resource") not in ("metal", "energy"):
                errs.append(f"{hid}: income resource {a.get('resource')}")
            if k == "repair" and not (0 < a.get("bonus", 0) <= 0.02 and 0 < a.get("below", 0) <= 1):
                errs.append(f"{hid}: repair rate/below")
            if k == "xp" and not (0 < a.get("bonus", 0) <= 0.005):
                errs.append(f"{hid}: xp rate")
            m = a.get("match") or {}
            if not m or not set(m) <= set(MATCH_KEYS):
                errs.append(f"{hid}: match {m}")
            if not set(m.get("tags", [])) <= vocab:
                errs.append(f"{hid}: match tags {m.get('tags')}")
            if not set(m.get("axes", {})) <= set(axes_names):
                errs.append(f"{hid}: match axes {m.get('axes')}")
            if not set(m.get("kinds", [])) <= set(UNIT_KINDS):
                errs.append(f"{hid}: match kinds {m.get('kinds')}")
            if a.get("when") and a["when"] not in conds:
                errs.append(f"{hid}: aura condition {a['when']}")
            if not a.get("scope") and not a.get("radius"):
                errs.append(f"{hid}: an aura needs a radius or scope company")
            if a.get("scope") not in (None, "company"):
                errs.append(f"{hid}: scope {a.get('scope')}")
            sc = a.get("scale")
            if sc and (sc.get("by") not in SCALE_BY or not sc.get("per")):
                errs.append(f"{hid}: scale {sc}")
            if not a.get("note"):
                errs.append(f"{hid}: an aura needs its note (the ledger reads it)")
        sc = s.get("scale")
        if sc and (sc.get("by") not in SCALE_BY or not sc.get("per")):
            errs.append(f"{hid}: self scale {sc}")
    return errs


def ties(web, heroes):
    out = {h: {} for h in heroes}
    for e in web["edges"]:
        if not e.get("authored"):
            continue
        a, b, pol = e["a"], e["b"], e.get("polarity")
        sign = 1 if pol in ALLY else -1 if pol in ENEMY else 0
        if sign and a in out and b in out:
            out[a][b] = sign
            out[b][a] = sign
    return out


def lua_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua(v, ind=""):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(round(float(v), 4)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return lua_str(v)
    if isinstance(v, list):
        if all(not isinstance(x, (dict, list)) for x in v):
            return "{ " + ", ".join(lua(x) for x in v) + " }" if v else "{}"
        inner = ind + "  "
        return "{\n" + "".join(f"{inner}{lua(x, inner)},\n" for x in v) + ind + "}"
    if isinstance(v, dict):
        if not v:
            return "{}"
        inner = ind + "  "
        body = ""
        for k, x in v.items():
            key = k if k.isidentifier() else f"[{lua_str(k)}]"
            body += f"{inner}{key} = {lua(x, inner)},\n"
        return "{\n" + body + ind + "}"
    return "nil"


def strip_notes(d):
    if isinstance(d, dict):
        return {k: strip_notes(v) for k, v in d.items() if k != "note"}
    if isinstance(d, list):
        return [strip_notes(x) for x in d]
    return d


def render(fx, umwelt, maps, tie):
    rules = {k: v for k, v in fx["rules"].items() if k != "notes"}
    heroes = {}
    for hid, h in fx["heroes"].items():
        ax = {k: round(v, 3) for k, v in (umwelt.get(hid, {}).get("axes") or {}).items() if abs(v) >= 0.05}
        heroes[hid] = {"tags": h["tags"], "axes": ax, "self": strip_notes(h["self"]), "auras": strip_notes(h["auras"])}
    mp = {m["mapId"]: {k: round(v, 3) for k, v in m["mapPressure"].items() if abs(v) >= 0.05} for m in maps}
    return (
        "-- GENERATED by tools/sync_field_effects.py from data/story/field_effects.json: do not edit.\n"
        "-- Field effects v2: self effect + conditional auras; bond web; map pressure (home ground).\n"
        "local M = {}\n\n"
        f"M.RULES = {lua(rules)}\n\n"
        f"M.HEROES = {lua(heroes)}\n\n"
        f"M.TIES = {lua({h: t for h, t in tie.items() if t})}\n\n"
        f"M.MAPS = {lua(mp)}\n\n"
        "return M\n"
    )


def main(argv):
    fx = _j("field_effects.json")
    packs = _j("crew_packs.json")["heroes"]
    hu = _j("hero_umwelt.json")
    umwelt = {h["heroId"]: h for h in hu["heroes"]}
    errs = validate(fx, packs, hu["axes"])
    missing = [h for h in packs if not any(abs(v) > 0 for v in (umwelt.get(h, {}).get("axes") or {}).values())]
    if missing:
        errs.append(f"heroes without axes: {missing}")
    if errs:
        print("\n".join(errs))
        return 1
    out = render(fx, umwelt, _j("map_umwelt.json")["maps"], ties(_j("support_web.json"), packs))
    if "--check" in argv:
        if not LUA.is_file() or LUA.read_text(encoding="utf-8") != out:
            print("va_field_effects.lua is out of date: run tools/sync_field_effects.py")
            return 1
        return 0
    LUA.write_text(out, encoding="utf-8")
    print(f"wrote {LUA.relative_to(ROOT)} ({len(packs)} heroes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
