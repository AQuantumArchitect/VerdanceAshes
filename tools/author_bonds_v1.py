#!/usr/bin/env python3
"""Merge authored relationships into the support web and the camp talks.

    data/story/sky_bonds.json (and any data/story/*_bonds.json)  ->  support_web.json edges (authored)
                                                                  ->  camp_talks.json + camp_talks_authored.json
                                                                  ->  app/showoff/camp_talks.embed.js

An authored pair replaces whatever edge the web had for those two heroes, and its talks replace
that pair's talks (written ones are generated=false, so later merges keep them). Run after
editing a *_bonds.json file:

    python3 tools/author_bonds_v1.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "data" / "story"
UNLOCK = {"C": {"coDeploy": 1, "campLevelMin": 0, "bondMin": 0},
          "B": {"coDeploy": 2, "campLevelMin": 1, "bondMin": 25},
          "A": {"coDeploy": 3, "campLevelMin": 2, "bondMin": 55}}


def load(name: str) -> dict:
    return json.loads((STORY / name).read_text(encoding="utf-8-sig"))


def save(name: str, data: dict) -> None:
    """Keep each file's own line endings (some are CRLF)."""
    path = STORY / name
    crlf = b"\r\n" in path.read_bytes()[:200]
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def pair_id(a: str, b: str) -> str:
    x, y = sorted([a, b])
    return f"{x}__{y}"


def main() -> int:
    web, talks, written = load("support_web.json"), load("camp_talks.json"), load("camp_talks_authored.json")
    codex = {h["heroId"]: h for h in load("hero_codex.json")["heroes"]}
    umwelt = {h["heroId"]: h for h in load("hero_umwelt.json")["heroes"]}
    authored = []
    for path in sorted(STORY.glob("*_bonds.json")):
        authored += json.loads(path.read_text(encoding="utf-8-sig")).get("pairs") or []
    edges = {pair_id(e["a"], e["b"]): e for e in web["edges"]}
    talk_rows = {t["id"]: t for t in talks["talks"]}
    written_rows = {t["id"]: t for t in written["talks"]}
    for p in authored:
        a, b = p["a"], p["b"]
        for hid in (a, b):
            if hid not in codex:
                print(f"unknown hero {hid}", file=sys.stderr)
                return 1
        pid = pair_id(a, b)
        ca, cb = codex[a], codex[b]
        edges[pid] = {
            "id": pid, "a": a, "b": b, "score": 1.0, "polarity": p["polarity"], "motifs": list(p["motifs"]),
            "sharedTemperament": sorted(set(ca.get("temperament") or []) & set(cb.get("temperament") or [])),
            "reasons": ["authored seed"], "authored": True,
            "aName": ca["name"], "bName": cb["name"], "aHook": ca["voice"]["hook"], "bHook": cb["voice"]["hook"],
            "aGlyph": (umwelt.get(a) or {}).get("glyph", ""), "bGlyph": (umwelt.get(b) or {}).get("glyph", ""),
            "talkIds": {r: f"{pid}:{r}" for r in p["talks"]},
        }
        for tid in [k for k, t in talk_rows.items() if t.get("pairId") == pid]:
            talk_rows.pop(tid)
        for rank, t in p["talks"].items():
            row = {"id": f"{pid}:{rank}", "pairId": pid, "a": a, "b": b, "rank": rank, "title": t["title"],
                   "polarity": p["polarity"], "motif": p["motifs"][0], "generated": False, "unlock": UNLOCK[rank],
                   "beats": [{"speaker": s, "line": line} for s, line in t["beats"]]}
            talk_rows[row["id"]] = row
            written_rows[row["id"]] = row
    web["edges"] = sorted(edges.values(), key=lambda e: (-float(e.get("score") or 0), e["id"]))
    degree: dict = {}
    for e in web["edges"]:
        for h in (e["a"], e["b"]):
            degree[h] = degree.get(h, 0) + 1
    nodes = web.setdefault("nodes", [])
    have = {n["heroId"] for n in nodes}
    for hid, ch in codex.items():          # every codex hero is a node, however late it joined
        if hid in have:
            continue
        um = umwelt.get(hid) or {}
        nodes.append({"heroId": hid, "name": ch["name"], "position": ch["position"], "temperament": list(ch.get("temperament") or []),
                      "doctrine": ch.get("doctrine"), "hook": ch["voice"]["hook"], "degree": 0,
                      "umweltGlyph": um.get("glyph", ""), "umweltMarks": list(um.get("marks") or [])})
    for n in nodes:
        n["degree"] = degree.get(n["heroId"], 0)
    params = web.setdefault("params", {})
    params.update(heroCount=len(nodes), edgeCount=len(web["edges"]), talkCount=len(talk_rows),
                  authoredSeeds=sum(1 for e in web["edges"] if e.get("authored")))
    talks["talks"] = list(talk_rows.values())
    written["talks"] = list(written_rows.values())
    talks["authoredCount"] = sum(1 for t in talks["talks"] if t.get("generated") is False)
    save("support_web.json", web)
    save("camp_talks.json", talks)
    save("camp_talks_authored.json", written)
    embed = ROOT / "app" / "showoff" / "camp_talks.embed.js"
    embed.write_text("window.VA_CAMP_TALKS = " + json.dumps({"schemaVersion": talks.get("schemaVersion"), "talks": talks["talks"]},
                                                            ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"{len(authored)} authored pairs · {len(web['edges'])} edges · {len(talk_rows)} talks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
