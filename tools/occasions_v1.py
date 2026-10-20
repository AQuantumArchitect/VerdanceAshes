#!/usr/bin/env python3
"""Occasions: who says what, given the readings face (DERIVE; never writes campaign state).

Reads outbox/readings.latest.json (or projects it) plus data/story/voices/*.json and
produces outbox/occasions.latest.json + .md:

  briefing   the leading voice's opener for the current attractor, then the owned witnesses
  debrief    reactions to the latest bead's fired event classes, in the owner's voice
  camp       reading shifts, coherence settled/torn, 'nobody has asked' lines
  roll       the roll document: the dead by name, the carried by name
  dispatches the other side's voices (patrons), one or two per bead
  blades     named-blade reactions for participants in the latest bead

The generator contract: this tool never composes a sentence. It selects an authored
line for a (speaker, event class, occasion, reading, attractor) tuple and fills the
nouns. If no authored line fits, the witness string is shown as narrator text.

    python tools/occasions_v1.py            # readout + outbox faces
    python tools/occasions_v1.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "verdance-occasions-face/0.1"
sys.path.insert(0, str(ROOT / "tools"))
import readings_v1  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class _Strict(dict):
    class Missing(Exception):
        pass

    def __missing__(self, key: str) -> str:
        raise _Strict.Missing(key)


def render(template: str, fields: Dict[str, Any]) -> Optional[str]:
    try:
        return template.format_map(_Strict(fields))
    except (_Strict.Missing, Exception):
        return None


def stable(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16)


# ----------------------------------------------------------------------------- voices

def load_voices(workspace: Path) -> Dict[str, Dict[str, Any]]:
    out = {}
    vdir = workspace / "data" / "story" / "voices"
    if not vdir.exists():
        return out
    for path in sorted(vdir.glob("*.json")):
        doc = _load(path)
        if doc.get("speaker"):
            out[doc["speaker"]] = doc
    return out


def load_named(workspace: Path, name: str) -> Dict[str, Any]:
    path = workspace / "data" / "story" / "voices" / f"{name}.json"
    return _load(path) if path.exists() else {}


# ----------------------------------------------------------------------------- selection

class Selector:
    def __init__(self, face: Dict[str, Any], state: Dict[str, Any], voices: Dict[str, Dict[str, Any]], previous: Optional[Dict[str, Any]]):
        self.face = face
        self.state = state
        self.voices = voices
        self.previous = previous or {}
        self.said_once = set(self.previous.get("saidOnce") or [])
        self.recent = list(self.previous.get("recentLines") or [])[-40:]
        self.company = readings_v1.company_ids(state)
        self.chars = {hid: ch for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict)}
        self.dominant = face.get("dominant")
        self.attractor = (face.get("attractor") or {}).get("current")
        self.leads = (face.get("attractor") or {}).get("leads") or []
        self.key = face.get("generatedFrom", {}).get("missionNumber")
        self.used_now: set = set()

    def present(self, hid: str) -> bool:
        ch = self.chars.get(hid) or {}
        return hid in self.company and ch.get("status") not in ("dead", "wounded", "locked")

    def _matches(self, line: Dict[str, Any], on: Dict[str, Any]) -> bool:
        want = line.get("on") or {}
        for k, v in want.items():
            if k == "attractor":
                if v != "*" and on.get("attractor") != v:
                    return False
            elif k in ("coherenceSettled", "coherenceTorn"):
                got = on.get(k)
                if not got:
                    return False
                if sorted(v.get("pair") or []) != sorted(got.get("pair") or []):
                    return False
                if v.get("toward") and v.get("toward") != got.get("toward"):
                    return False
            elif on.get(k) != v:
                return False
        rd = line.get("reading") or {}
        if rd.get("dominant") and self.dominant not in rd["dominant"]:
            return False
        if line.get("occasion") and on.get("occasion") and line["occasion"] != on["occasion"]:
            return False
        if line.get("once") and line["id"] in self.said_once:
            return False
        return True

    def pick(self, speaker: str, on: Dict[str, Any], fields: Dict[str, Any], seed: Any) -> Optional[Dict[str, Any]]:
        voice = self.voices.get(speaker)
        if not voice:
            return None
        candidates = []
        for line in voice.get("lines") or []:
            if not self._matches(line, on):
                continue
            text = render(line["text"], fields)
            if text is None:
                continue
            # Prefer specific lines (more conditions) and unused ones.
            specificity = len(line.get("on") or {}) + (2 if line.get("reading") else 0)
            recency = self.recent[::-1].index(line["id"]) if line["id"] in self.recent else 99
            candidates.append((specificity, min(recency, 99), float(line.get("weight", 1.0)), line, text))
        if not candidates:
            return None
        # Most specific line that has not been said recently; fall back level by level,
        # and only repeat a recent line when every level is exhausted.
        pool: List[Any] = []
        for spec in sorted({c[0] for c in candidates}, reverse=True):
            pool = [c for c in candidates if c[0] == spec and c[1] >= 3]
            if pool:
                break
        if not pool:
            pool = sorted(candidates, key=lambda c: (-c[1], -c[0]))
            pool = [c for c in pool if c[1] == pool[0][1]]
        chosen = pool[stable(seed, speaker, on.get("class"), self.key) % len(pool)]
        line, text = chosen[3], chosen[4]
        if line.get("once"):
            self.said_once.add(line["id"])
        self.recent.append(line["id"])
        self.used_now.add(line["id"])
        return {"speaker": speaker, "lineId": line["id"], "text": text}

    def speak(self, owner: str, on: Dict[str, Any], fields: Dict[str, Any], witness: Optional[str], seed: Any, allow_fallback: bool = True) -> Dict[str, Any]:
        order = [owner]
        if allow_fallback:
            order += [l for l in self.leads if l != owner] + ["ketha"]
        for hid in order:
            if not self.present(hid):
                continue
            got = self.pick(hid, on, fields, seed)
            if got:
                return dict(got, owner=owner, fallback=(hid != owner))
        return {"speaker": "narrator", "lineId": None, "text": witness or "", "owner": owner, "fallback": True}


# ----------------------------------------------------------------------------- build

def build(face: Dict[str, Any], state: Dict[str, Any], workspace: Path, previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    voices = load_voices(workspace)
    blades = (load_named(workspace, "blades") or {}).get("blades") or {}
    patrons = (load_named(workspace, "patrons") or {}).get("patrons") or {}
    sel = Selector(face, state, voices, previous)
    ctx = readings_v1.Context(state, workspace)
    names = {hid: (ch.get("name") or hid) for hid, ch in sel.chars.items()}

    beads = face.get("events", {}).get("beads") or []
    latest = beads[-1] if beads else None
    dead = [hid for hid, ch in sorted(sel.chars.items()) if ch.get("status") == "dead"]
    wounded = [hid for hid, ch in sorted(sel.chars.items()) if int(ch.get("wounds") or 0) > 0 or ch.get("status") == "wounded"]
    held_count = sum(1 for zs in (state.get("zoneMemory") or {}).values() if isinstance(zs, dict)
                     for z in zs.values() if isinstance(z, dict) and z.get("controllingFaction") == readings_v1.OUR_FACTION)
    common = {
        "wounded": ", ".join(names[h] for h in wounded) or "nobody",
        "dead": ", ".join(names[h] for h in dead) or "nobody yet",
        "heldCount": held_count,
        "tenebrium": (state.get("commerce") or {}).get("tenebrium", 0),
        "atTable": len([h for h in sel.company if sel.present(h)]),
        "map": ctx.map_name((latest or {}).get("mapId")),
        "mapId": (latest or {}).get("mapId"),
    }

    # what the other side believes about us (divergence face), so a dispatch is written from its author's mind
    div_path = workspace / "outbox" / "divergence.latest.json"
    if div_path.exists():
        try:
            div = _load(div_path)
            crossed = (div.get("crossed") or {})
            persp = (div.get("perspectives") or {})
            for fac, c in crossed.items():
                a = c.get("aboutCompany") or {}
                common[f"{fac}Knows"] = len(a.get("known") or [])
                common[f"{fac}Blind"] = len(a.get("blind") or [])
                common[f"{fac}OfOurs"] = a.get("ofOurs")
                common[f"{fac}Ghost"] = len((persp.get(fac) or {}).get("ghostHoldings") or [])
        except Exception:
            pass
    out: Dict[str, Any] = {"schemaVersion": SCHEMA, "missionNumber": face.get("generatedFrom", {}).get("missionNumber"),
                           "attractor": sel.attractor, "dominant": sel.dominant,
                           "briefing": [], "debrief": [], "camp": [], "roll": {}, "dispatches": [], "blades": [], "transition": None}

    # --- briefing opener: first present lead with an attractor line
    for lead in sel.leads + ["ketha"]:
        if not sel.present(lead):
            continue
        got = sel.pick(lead, {"attractor": sel.attractor, "occasion": "briefing"}, common, "open")
        if got:
            out["briefing"].append(dict(got, kind="opener"))
            break
    # briefing-occasion witnesses from the latest bead + snapshot
    fired_rows = list((latest or {}).get("fired") or []) + list(face.get("events", {}).get("snapshot") or [])
    seen_classes_brief = set()
    for row in fired_rows:
        if row.get("occasion") != "briefing" or row["class"] in seen_classes_brief:
            continue
        seen_classes_brief.add(row["class"])
        on = {"class": row.get("aliasOf") or row["class"], "occasion": "briefing"}
        fields = dict(common, **(row.get("fields") or {}))
        if fields.get("thread"):
            on["thread"] = fields["thread"]
        out["briefing"].append(dict(sel.speak(row["owner"], on, fields, row.get("witness"), row.get("witness")), kind="witness", eventClass=row["class"]))

    # --- debrief: the latest bead's fired classes with debrief/camp/roll occasions
    if latest:
        for row in latest.get("fired") or []:
            if row.get("occasion") not in ("debrief", "camp"):
                continue
            on = {"class": row.get("aliasOf") or row["class"], "occasion": row.get("occasion")}
            fields = dict(common, **(row.get("fields") or {}))
            if fields.get("thread"):
                on["thread"] = fields["thread"]
            target = "debrief" if row.get("occasion") == "debrief" else "camp"
            out[target].append(dict(sel.speak(row["owner"], on, fields, row.get("witness"), row.get("witness")), kind="witness", eventClass=row["class"]))

    # --- camp: snapshot camp classes, reading shifts, coherence changes
    for row in face.get("events", {}).get("snapshot") or []:
        if row.get("occasion") != "camp":
            continue
        on = {"class": row.get("aliasOf") or row["class"], "occasion": "camp"}
        fields = dict(common, **(row.get("fields") or {}))
        out["camp"].append(dict(sel.speak(row["owner"], on, fields, row.get("witness"), row.get("witness")), kind="witness", eventClass=row["class"]))
    prev_face = (previous or {}).get("faceSummary") or {}
    if prev_face.get("dominant") and prev_face.get("dominant") != sel.dominant:
        spec = next((r for r in face["readings"] if r["id"] == sel.dominant), {})
        for hid in [spec.get("argues"), spec.get("resists")] + sorted(voices):
            if hid and sel.present(hid):
                got = sel.pick(hid, {"dominantBecame": sel.dominant, "occasion": "camp"}, common, "shift")
                if got:
                    out["camp"].append(dict(got, kind="shift", reading=sel.dominant))
                    break
    prev_coh = {tuple(c["pair"]): c for c in prev_face.get("coherence") or []}
    for c in face.get("coherence") or []:
        before = prev_coh.get(tuple(c["pair"])) or {}
        if c["status"] in ("settled", "leaning") and c.get("leaning") and (before.get("status") != c["status"] or before.get("leaning") != c.get("leaning")):
            on = {"coherenceSettled": {"pair": c["pair"], "toward": c["leaning"]}, "occasion": "camp"}
            for hid in sorted(voices):
                if sel.present(hid):
                    got = sel.pick(hid, on, common, "settled")
                    if got:
                        out["camp"].append(dict(got, kind="settled", pair=c["pair"], toward=c["leaning"]))
                        break
        if c["status"] == "torn" and before.get("status") != "torn":
            on = {"coherenceTorn": {"pair": c["pair"]}, "occasion": "camp"}
            for hid in sorted(voices):
                if sel.present(hid):
                    got = sel.pick(hid, on, common, "torn")
                    if got:
                        out["camp"].append(dict(got, kind="torn", pair=c["pair"]))
                        break

    # --- roll occasions placed on this bead (the moment it happened, in the owner's voice)
    if latest:
        for row in latest.get("fired") or []:
            if row.get("occasion") != "roll":
                continue
            on = {"class": row.get("aliasOf") or row["class"], "occasion": "roll"}
            fields = dict(common, **(row.get("fields") or {}))
            if fields.get("heroId") == "pavise":
                on["heroId"] = "pavise"
            out["debrief"].append(dict(sel.speak(row["owner"], on, fields, row.get("witness"), row.get("witness")), kind="roll", eventClass=row["class"]))

    # --- roll
    pavise_doc = load_named(workspace, "pavise")
    entries = []
    for hid in dead:
        fields = dict(common, hero=names[hid], heroId=hid)
        line = sel.speak("ketha", {"class": "named_dead", "occasion": "roll", "heroId": hid} if hid == "pavise" else {"class": "named_dead", "occasion": "roll"},
                         fields, f"{names[hid]}. The frame was not brought back.", hid, allow_fallback=False)
        aside = None
        if sel.present("rusk"):
            aside = sel.pick("rusk", {"class": "named_dead", "occasion": "roll"}, fields, hid)
        blade_death = (blades.get(hid) or {}).get("death") or (voices.get(hid) or {}).get("deathLine")
        entries.append({"heroId": hid, "name": names[hid], "status": "roll", "line": line, "aside": aside, "lastWords": blade_death,
                        "entry": (pavise_doc.get("posthumous") or {}).get("rollEntry") if hid == "pavise" else f"{names[hid]}. The frame was not brought back."})
    carried = []
    for hid in wounded:
        fields = dict(common, hero=names[hid], heroId=hid, wounds=int((sel.chars.get(hid) or {}).get("wounds") or 0))
        line = sel.speak("rusk", {"class": "frame_recovered", "occasion": "roll"}, fields, f"{names[hid]} came back on someone's shoulders.", hid)
        carried.append({"heroId": hid, "name": names[hid], "wounds": fields["wounds"], "line": line})
    out["roll"] = {"dead": entries, "carried": carried,
                   "header": "The roll. In the order they went. Where the frame was left, if it was left.",
                   "walker": "scrap" if not (state.get("roster") or {}).get("commander", {}).get("unlocked") else "fielded"}

    # --- dispatches (patrons)
    fired_classes = {(r.get("aliasOf") or r["class"]): r for r in fired_rows}
    cands = []
    for pid, p in patrons.items():
        for d in p.get("dispatches") or []:
            on = d.get("on") or {}
            ok = False
            fields = dict(common)
            if "class" in on and on["class"] in fired_classes:
                row = fired_classes[on["class"]]
                fields.update(row.get("fields") or {})
                if on.get("thread") and fields.get("thread") != on["thread"]:
                    continue
                if on.get("map") and fields.get("mapId") != on["map"]:
                    continue
                ok = True
            elif "attractor" in on and on["attractor"] == sel.attractor:
                ok = True
            elif "dominantBecame" in on and prev_face.get("dominant") and prev_face.get("dominant") != sel.dominant and on["dominantBecame"] == sel.dominant:
                ok = True
            elif "belief" in on:
                # the author's OWN mind about us (divergence face): blind = our holdings it has never seen,
                # ghost = holdings it still believes are its own. Only patrons of that faction may use it.
                fac = p.get("faction")
                want = on["belief"]
                if want.get("blindGte") is not None and (common.get(f"{fac}Blind") or 0) >= want["blindGte"]:
                    ok = True
                if want.get("ghostGte") is not None and (common.get(f"{fac}Ghost") or 0) >= want["ghostGte"]:
                    ok = True
                if want.get("knowsAll") and (common.get(f"{fac}Blind") == 0) and (common.get(f"{fac}Knows") or 0) > 0:
                    ok = True
            elif "coherenceSettled" in on:
                want = on["coherenceSettled"]
                for c in face.get("coherence") or []:
                    before = prev_coh.get(tuple(c["pair"])) or {}
                    if sorted(c["pair"]) == sorted(want["pair"]) and c.get("leaning") == want.get("toward") and c["status"] in ("settled", "leaning") and before.get("leaning") != c.get("leaning"):
                        ok = True
            if not ok:
                continue
            text = render(d["text"], fields)
            if text:
                cands.append({"from": pid, "name": p.get("name"), "faction": p.get("faction"), "text": text, "on": on})
    cands.sort(key=lambda c: (stable(c["from"], c["text"], sel.key)))
    # at most two dispatches a bead, and never two from the same desk
    picked: List[Dict[str, Any]] = []
    for c in cands:
        if any(p["from"] == c["from"] for p in picked):
            continue
        picked.append(c)
        if len(picked) == 2:
            break
    out["dispatches"] = picked

    # --- blades: participants in the latest bead
    if latest:
        ev = next((e for e in (state.get("narrative", {}).get("events") or []) if e.get("turn") == len(beads)), None)
        participants = (ev or {}).get("participants") or []
        verdict = latest.get("verdict")
        clean = latest.get("extraction") == "clean"
        for hid in participants:
            b = blades.get(hid)
            if not b or hid in voices:
                continue
            ch = sel.chars.get(hid) or {}
            hurt = ch.get("status") == "wounded" or int(ch.get("wounds") or 0) > 0
            key = "held" if verdict == "victory" and clean and not hurt else "costly"
            text = render(b.get(key, ""), dict(common, map=ctx.map_name(latest.get("mapId"))))
            if text:
                out["blades"].append({"speaker": hid, "name": names.get(hid, hid), "text": text, "kind": key})

    # --- transition scene passthrough
    tr = (face.get("attractor") or {}).get("transition")
    if tr:
        out["transition"] = {"from": tr["from"], "to": tr["to"], "scene": (tr.get("sceneResolved") or {}).get("id") or tr.get("scene")}

    out["saidOnce"] = sorted(sel.said_once)
    out["recentLines"] = sel.recent[-40:]
    out["faceSummary"] = {"dominant": sel.dominant, "attractor": sel.attractor,
                          "coherence": [{"pair": c["pair"], "status": c["status"], "leaning": c.get("leaning")} for c in face.get("coherence") or []]}
    return out


def markdown(occ: Dict[str, Any]) -> str:
    L = [f"# Occasions — mission {occ.get('missionNumber')} · {occ.get('attractor')} · dominant {occ.get('dominant')}", ""]
    if occ.get("transition"):
        t = occ["transition"]
        L += [f"**Transition** {t['from']} → {t['to']} — scene `{t['scene']}`", ""]
    def block(title: str, rows: List[Dict[str, Any]]):
        if not rows:
            return
        L.append(f"## {title}")
        for r in rows:
            who = r.get("speaker") or r.get("name") or r.get("from")
            tag = f" _({r.get('eventClass') or r.get('kind') or ''})_" if (r.get("eventClass") or r.get("kind")) else ""
            fb = " ⟵fallback" if r.get("fallback") and r.get("speaker") != "narrator" else ""
            L.append(f"- **{who}**: {r.get('text')}{tag}{fb}")
        L.append("")
    block("Briefing", occ.get("briefing") or [])
    block("Debrief", occ.get("debrief") or [])
    block("Camp", occ.get("camp") or [])
    roll = occ.get("roll") or {}
    if roll:
        L.append("## The roll")
        L.append(f"_{roll.get('header')}_  · walker: {roll.get('walker')}")
        for e in roll.get("dead") or []:
            L.append(f"- **{e['name']}** — {e['entry']}")
            if e.get("line"):
                L.append(f"    - {e['line']['speaker']}: {e['line']['text']}")
            if e.get("aside"):
                L.append(f"    - {e['aside']['speaker']}: {e['aside']['text']}")
            if e.get("lastWords"):
                L.append(f"    - last words: _{e['lastWords']}_")
        for c in roll.get("carried") or []:
            L.append(f"- {c['name']} — carried ({c['wounds']}): {c['line']['speaker']}: {c['line']['text']}")
        L.append("")
    block("Dispatches", [dict(d, speaker=d["name"]) for d in occ.get("dispatches") or []])
    block("Blades", occ.get("blades") or [])
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=str(ROOT))
    ap.add_argument("--state", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="ignore previous occasions face (once-lines, recency, shift detection)")
    args = ap.parse_args(argv)
    ws = Path(args.workspace)
    state_path = Path(args.state) if args.state else ws / "state" / "campaign_state.json"
    state = _load(state_path)
    face_path = ws / "outbox" / "readings.latest.json"
    prev_readings = _load(face_path) if face_path.exists() and not args.fresh else None
    face = readings_v1.project(json.loads(json.dumps(state)), ws, prev_readings)
    occ_path = ws / "outbox" / "occasions.latest.json"
    previous = None
    if occ_path.exists() and not args.fresh:
        try:
            previous = _load(occ_path)
        except Exception:
            previous = None
    occ = build(face, state, ws, previous)
    if not args.no_write:
        occ_path.parent.mkdir(parents=True, exist_ok=True)
        occ_path.write_text(json.dumps(occ, indent=2, ensure_ascii=False), encoding="utf-8")
        (ws / "outbox" / "occasions.latest.md").write_text(markdown(occ), encoding="utf-8")
        face_path.write_text(json.dumps(face, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(occ, indent=2, ensure_ascii=False) if args.json else markdown(occ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
