#!/usr/bin/env python3
"""Every hero in one dataset, for the Hero Ledger page (and for anyone reviewing the roster).

    python3 tools/hero_ledger/build_data.py OUT.json [PAGE.html]  (PAGE: template.html with the data spliced in)

Reads the same story files the campaign reads; computes nothing the game does not.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S = ROOT / "data" / "story"
sys.path.insert(0, str(ROOT / "tools"))


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def main(out_path: str) -> None:
    from verdance.company.company import DEFAULT_HOMES
    packs = jl(S / "crew_packs.json")
    roster = {h["heroId"]: h for h in jl(S / "hero_roster.json")["heroes"]}
    codex = {h["heroId"]: h for h in jl(S / "hero_codex.json")["heroes"]}
    umw = {h["heroId"]: h for h in jl(S / "hero_umwelt.json")["heroes"]}
    web = jl(S / "support_web.json")
    costs = jl(S / "unit_costs.json")
    gifts = jl(S / "bond_gifts.json")
    talks = jl(S / "camp_talks.json").get("talks") or []
    rules = jl(S / "encounter_rules.json")
    voices = {}
    for p in (S / "voices").glob("*.json"):
        v = jl(p)
        if v.get("speaker"):
            voices[v["speaker"]] = {"register": v.get("register"), "argues": v.get("argues"), "resists": v.get("resists"),
                                    "lines": [ln.get("text") or ln.get("line") for ln in (v.get("lines") or [])
                                              if isinstance(ln, dict) and (ln.get("text") or ln.get("line"))][:4]}

    # field effects (kit tags) from the gadget include
    src = (ROOT / "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_hero_tags.lua").read_text(encoding="utf-8")
    tags = {}
    for m in re.finditer(r'^  (\w+) = \{ label = "([^"]+)", (.*?) fiction = "((?:[^"\\]|\\.)*)" \},?$', src, re.M):
        key, label, mid, fic = m.groups()
        stats = [[k, float(v)] for k, v in re.findall(r'(\w+) = ([0-9.]+)', mid)]
        if stats:
            tags[key] = {"label": label, "stats": stats, "fiction": fic.replace('\\"', '"')}
    dflt = src.split("M.HERO_DEFAULTS = {", 1)[1].split("\n}\n", 1)[0]
    hero_tag = {h: t for h, t in re.findall(r'(\w+) = \{ "(\w+)" \}', dflt)}

    names = dict(costs.get("names") or {})
    names.update({u: c.get("label") for u, c in (packs.get("chassis") or {}).items() if c.get("label")})

    def links_for(h):
        out = []
        for e in web["edges"]:
            if h not in (e["a"], e["b"]):
                continue
            out.append({"other": e["b"] if e["a"] == h else e["a"], "polarity": e["polarity"],
                        "score": e.get("score", 1.0), "authored": bool(e.get("authored")),
                        "motifs": [m for m in (e.get("motifs") or []) if not str(m).startswith("shared:")][:3]})
        return sorted(out, key=lambda l: (not l["authored"], l["other"]))

    def talk_for(h):
        best = None
        for t in talks:
            if h not in (t.get("a"), t.get("b")):
                continue
            line = next((b.get("line") for b in t.get("beats") or [] if b.get("speaker") == h), None)
            if not line:
                continue
            cand = {"with": t["b"] if t["a"] == h else t["a"], "title": t.get("title"), "line": line,
                    "authored": t.get("generated") is False}
            if best is None or (cand["authored"] and not best["authored"]):
                best = cand
        return best

    def gifts_for(h):
        out = []
        for pair, recs in (gifts.get("recommended") or {}).items():
            a, b = pair.split("__")
            if h in (a, b):
                for r in recs[:1]:
                    out.append({"with": b if a == h else a, "unitDef": r.get("unitDef"), "count": r.get("count"), "why": r.get("why")})
        return out

    starters = set(packs.get("starterUnlocks") or [])
    core = set(packs.get("core") or [])
    order = list(packs.get("core") or []) + list(packs.get("bandOrder") or [])
    heroes = []
    for hid, pack in packs["heroes"].items():
        r, c, u = roster.get(hid) or {}, codex.get(hid) or {}, umw.get(hid) or {}
        voice = c.get("voice") or {}
        tag = tags.get(hero_tag.get(hid, ""), None)
        rec = r.get("recruit") or {}
        home = DEFAULT_HOMES.get(hid) or ([rec.get("mapId"), rec.get("zoneId")] if rec.get("mapId") else None)
        heroes.append({
            "id": hid,
            "name": pack.get("name") or c.get("name") or hid,
            "faction": c.get("faction") or "",
            "status": "core" if hid in core else ("starter" if hid in starters else "recruit"),
            "position": c.get("position") or u.get("position") or "",
            "verb": c.get("combatVerb") or "",
            "temperament": c.get("temperament") or r.get("traits") or [],
            "doctrine": c.get("doctrine") or u.get("doctrine") or "",
            "hook": voice.get("hook") or "",
            "tagLine": voice.get("tagLine") or "",
            "fiction": voice.get("fiction") or r.get("fiction") or "",
            "blurb": pack.get("blurb") or "",
            "chassis": pack.get("unitDef"),
            "chassisName": names.get(pack.get("unitDef")) or pack.get("unitDef"),
            "packTotal": pack.get("packTotal") or 1,
            "escorts": [dict(e, name=names.get(e.get("unitDef")) or e.get("unitDef")) for e in pack.get("escorts") or []],
            "partners": pack.get("partners") or [],
            "packTags": pack.get("tags") or [],
            "fieldEffect": ({"key": hero_tag.get(hid), **tag} if tag else None),
            "buildsEco": bool(pack.get("buildsEco")),
            "baseSeeder": bool(pack.get("baseSeeder")),
            "factory": pack.get("factory"),
            "canLead": pack.get("canLead") is not False,
            "hireTnb": pack.get("hireTnb") or 0,
            "hireKm": pack.get("hireKm") or 0,
            "cost": {"combined": pack.get("packCombined"), "metal": pack.get("packMetal"), "energy": pack.get("packEnergy")},
            "startXp": pack.get("startXp"),
            "startXpFixed": bool(pack.get("startXpFixed")),
            "sizing": pack.get("sizing"),
            "packMind": pack.get("packMind"),
            "recruit": {"type": rec.get("type"), "blurb": rec.get("blurb"), "home": home},
            "axes": u.get("axes") or {},
            "glyph": u.get("glyph") or "",
            "codexFlags": {k: c.get(k) for k in ("preferDefenses", "allowBail", "allowKite") if k in c},
            "notes": c.get("notes") or "",
            "links": links_for(hid),
            "talk": talk_for(hid),
            "gifts": gifts_for(hid),
            "voice": voices.get(hid),
        })
    heroes.sort(key=lambda h: (order.index(h["id"]) if h["id"] in order else 999, h["name"]))
    data = {
        "builtFrom": "data/story/*.json + va_hero_tags.lua (Verdance's Ashes)",
        "company": {"core": packs.get("core"), "seatCap": packs.get("seatCap"), "startWalletTnb": packs.get("startWalletTnb"),
                    "recommended": ["pavise", "solarium", "halbard"]},
        "rules": {"meetingStance": rules.get("meetingStance"), "presence": rules.get("presence")},
        "polarity": {"ally": ["bond", "attract", "sibling", "mentor", "mirror"], "adversary": ["rivalry", "tension", "friction"]},
        "axes": ["energy", "offense", "mobility", "sight", "pad", "craft", "heat", "fog", "sky", "ledger"],
        "heroes": heroes,
    }
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{len(heroes)} heroes -> {out_path} ({Path(out_path).stat().st_size // 1024} KB)")


def page(data_path: str, out_html: str) -> None:
    tpl = (Path(__file__).with_name("template.html")).read_text(encoding="utf-8")
    data = Path(data_path).read_text(encoding="utf-8").replace("</", "<\\/")
    Path(out_html).write_text(tpl.replace("__DATA__", data), encoding="utf-8")
    print(f"page -> {out_html}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "hero_ledger.json")
    if len(sys.argv) > 2:
        page(sys.argv[1], sys.argv[2])
