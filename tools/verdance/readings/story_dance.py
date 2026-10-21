#!/usr/bin/env python3
"""The dance tape: story objects evolve by strand-dance verbs (S3 shape), and every bead
carries truth / goodness / beauty.

Vocabulary (strand-dance/1, unchanged from S3):

  ✨ creation   introduce an object with an origin, no evidence      a thread opens, a hero joins, an attractor is entered the first time
  →  push       advance an attributed flow                           a Drop advances the campaign strand; a thread is committed
  Δ  fission    children divide an existing allocation, never mint   a commitment splits a thread into an obligation with a deadline
  ∇  fusion     a summary that retains all its sources as residuals  the roll grows; a chapter folds (chronicle_v1)
  T  transform  content changes without promoting evidence           the dominant reading moves; a question changes status; attractor transition
  ∅  null       terminate with remaining obligations                 a promise lapses (its obligation survives); a death (the frame is still owed)
  ←  pull       recover an ancestor on a new branch                  (reserved: campaign restore)
  ⤳  skip       recover a replay-checked checkpoint                  (reserved)

The tape is append-only on state["dance"]["events"]; every event is content-addressed and
names its parents, so the record is a graph, not a log. Nothing here mutates world truth.

Truth / goodness / beauty per bead (never one score):
  truth     what happened       verdict, extraction, zones measured, surprise, dead, carried
  goodness  what was promised   promises kept / lapsed this bead, obligations still open
  beauty    how it reads        attractor, dominant reading, transition, scene, the opener line

    python -m verdance.readings.story_dance            # print the tape tail
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT

ROOT = WORKSPACE_ROOT
SCHEMA = "verdance-dance/0.1"
VERBS = {"creation": "✨", "push": "→", "fission": "Δ", "fusion": "∇", "transform": "T", "null": "∅", "pull": "←", "skip": "⤳"}
FOLD_NEVER = {"creation", "fission", "null", "fusion"}   # named events: never folded away by the chronicle


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:12]


def tape(state: Dict[str, Any]) -> Dict[str, Any]:
    d = state.setdefault("dance", {})
    d.setdefault("schemaVersion", SCHEMA)
    d.setdefault("events", [])
    d.setdefault("heads", {})          # object key -> last event id (the current revision)
    return d


def append(state: Dict[str, Any], verb: str, kind: str, obj_id: str, *, text: str, icon: str = "•", minute: Optional[float] = None,
           mission: Optional[int] = None, payload: Optional[Dict[str, Any]] = None, extra_parents: Optional[List[str]] = None,
           obligations: Optional[List[str]] = None, once: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """once: a key that may appear on the tape only one time (a commitment, a death, a join);
    a second attempt is the empty dance and returns None."""
    d = tape(state)
    if once:
        seen = d.setdefault("once", {})
        if once in seen:
            return None
        seen[once] = True
    key = f"{kind}:{obj_id}"
    parents = [p for p in ([d["heads"].get(key)] + list(extra_parents or [])) if p]
    body = {"verb": verb, "token": VERBS[verb], "kind": kind, "object": obj_id, "text": text, "icon": icon,
            "minute": None if minute is None else round(float(minute), 1), "missionNumber": mission,
            "payload": payload or {}, "parents": parents}
    if obligations:
        body["obligations"] = obligations
    body["revision"] = _h({k: body[k] for k in ("verb", "kind", "object", "payload", "parents")})
    body["id"] = f"{VERBS[verb]}{len(d['events']) + 1:04d}_{body['revision'][:6]}"
    # idempotent: identical content on the same head is the empty dance
    if d["events"] and d["events"][-1].get("revision") == body["revision"]:
        return d["events"][-1]
    d["events"].append(body)
    d["heads"][key] = body["id"]
    return body


# ----------------------------------------------------------------------------- homecoming fold

def fold_homecoming(state: Dict[str, Any], bead: Dict[str, Any], face: Optional[Dict[str, Any]], occ: Optional[Dict[str, Any]],
                    workspace: Path, *, previous_face: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Emit this homecoming's dance events and stamp bead['tgb']. Deterministic given inputs."""
    mission = bead.get("missionNumber")
    minute = float(state.get("campaignClockMinutes") or 0.0)
    key = bead.get("resultKey") or f"m{mission}"
    names = {hid: (ch.get("name") or hid) for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict)}
    emitted: List[Dict[str, Any]] = []

    def em(*a, **k):
        ev = append(state, *a, minute=minute, mission=mission, **k)
        if ev is not None:
            emitted.append(ev)

    # → the Drop advances the campaign strand
    em("push", "campaign", "strand", text=f"m{mission} {bead.get('mapId')}: {bead.get('verdict')}", icon="🛡" if bead.get("verdict") == "victory" else ("◐" if bead.get("verdict") == "partial" else "✖"),
       payload={"resultKey": key, "verdict": bead.get("verdict"), "extraction": bead.get("extractionStatus"), "surprise": (bead.get("surprise") or {}).get("total")})
    # ✨ joins
    for j in bead.get("joined") or []:
        hid = str(j.get("heroId") or "")
        if hid:
            em("creation", "hero", hid, text=f"{j.get('name') or names.get(hid, hid)} joined after m{mission}", icon="➕", payload={"name": j.get("name")}, once=f"join:{hid}:{key}")
    # ∅ deaths (the frame is still owed); ∇ the roll grows; carried = push on the hero strand
    dead_now, carried_now = [], []
    for o in bead.get("namedOutcomes") or []:
        hid = str(o.get("charId") or "")
        if not hid:
            continue
        if o.get("outcome") == "dead":
            dead_now.append(hid)
            em("null", "hero", hid, text=f"{names.get(hid, hid)} fell at {bead.get('mapId')}", icon="🪦",
               payload={"mapId": bead.get("mapId"), "zoneId": bead.get("deploymentZoneId")},
               obligations=[f"recover the frame of {names.get(hid, hid)} on {bead.get('mapId')}", f"read {names.get(hid, hid)} on the roll"], once=f"dead:{hid}")
        elif o.get("outcome") in ("recovered", "wounded"):
            carried_now.append(hid)
            em("push", "hero", hid, text=f"{names.get(hid, hid)} carried home from {bead.get('mapId')}", icon="🫱", payload={"outcome": o.get("outcome")}, once=f"carried:{hid}:{key}")
    if dead_now:
        roll = [hid for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict) and ch.get("status") == "dead"]
        em("fusion", "roll", "roll", text="the roll: " + ", ".join(names.get(h, h) for h in roll), icon="🪦",
           payload={"names": roll, "n": len(roll)}, extra_parents=[tape(state)["heads"].get(f"hero:{h}") for h in dead_now])
    # threads: ✨ opened, → committed, Δ obligation, ∅ lapsed, → kept
    kept, lapsed, open_obl = [], [], []
    threads = (state.get("narrative") or {}).get("threads") or {}
    turn = (state.get("narrative") or {}).get("turn")
    for tid, t in threads.items():
        hist = t.get("history") or []
        for h in hist:
            if h.get("turn") != turn and h.get("turn") != (turn - 1 if isinstance(turn, int) else None):
                continue
            if h.get("kind") == "commitment":
                cid = h.get("eventId") or f"{tid}:{h.get('turn')}"
                em("push", "thread", tid, text=f"'{tid}' committed: {h.get('text')}", icon="🤝", payload={"stance": t.get("stance"), "goal": t.get("goal")}, once=f"commit:{cid}")
                if t.get("obligation") or t.get("deadline") or t.get("goal"):
                    em("fission", "thread", tid, text=f"'{tid}' obligation: {t.get('goal')}" + (f" by turn {t.get('deadline')}" if t.get("deadline") else ""), icon="Δ",
                       payload={"goal": t.get("goal"), "deadline": t.get("deadline")}, once=f"obl:{cid}")
        if t.get("stage") == "Resolved" and t.get("resolvedTurn") == turn:
            kept.append(tid)
            em("push", "thread", tid, text=f"'{tid}' kept: {t.get('explanation') or ''}".strip(), icon="🤝", payload={"stage": "Resolved"}, once=f"kept:{tid}:{turn}:{t.get('cycle', 1)}")
        elif t.get("stage") == "Changed" and hist and hist[-1].get("turn") == turn and hist[-1].get("stage") == "Changed":
            lapsed.append(tid)
            em("null", "thread", tid, text=f"'{tid}' lapsed: {t.get('explanation') or ''}".strip(), icon="💔",
               payload={"stage": "Changed"}, obligations=[f"the promise '{t.get('promise') or tid}' still stands unkept"], once=f"lapsed:{tid}:{turn}:{t.get('cycle', 1)}")
        if t.get("stage") == "Committed":
            open_obl.append({"thread": tid, "promise": t.get("promise"), "goal": t.get("goal"), "deadline": t.get("deadline")})
    # T: reading / attractor transforms
    dom = (face or {}).get("dominant")
    prev_dom = (previous_face or {}).get("dominant")
    if dom and prev_dom and dom != prev_dom:
        em("transform", "readings", "dominant", text=f"the company reads as {dom} now (was {prev_dom})", icon="T", payload={"from": prev_dom, "to": dom})
    att = (face or {}).get("attractor") or {}
    tr = att.get("transition")
    if tr:
        em("transform", "attractor", "current", text=f"{tr.get('from')} → {tr.get('to')}", icon=att.get("icon") or "T", payload=dict(tr))
    elif att.get("current") and not tape(state)["heads"].get("attractor:current"):
        em("creation", "attractor", "current", text=f"the company stands in {att.get('current')}", icon="🪨", payload={"attractor": att.get("current")}, once="attractor:first")
    for c in (face or {}).get("coherence") or []:
        prev = next((p for p in ((previous_face or {}).get("coherence") or []) if p.get("pair") == c.get("pair")), None)
        if prev and (prev.get("status") != c.get("status")):
            em("transform", "question", "|".join(c["pair"]), text=f"{c.get('question')}: {prev.get('status')} → {c.get('status')}" + (f" ({c.get('leaning')})" if c.get("leaning") else ""),
               icon="?", payload={"from": prev.get("status"), "to": c.get("status"), "leaning": c.get("leaning")})
    # surprise as an observation pushed on the intel strand
    sp = bead.get("surprise") or {}
    if float(sp.get("total") or 0) >= 0.6 and sp.get("top"):
        top = sp["top"][0]
        em("push", "intel", "surprise", text=f"{top.get('label')}: believed {top.get('believed')}, found {top.get('found')}", icon="❗", payload={"total": sp.get("total"), "top": top})

    # truth / goodness / beauty on the bead
    opener = next((r.get("text") for r in ((occ or {}).get("briefing") or []) if r.get("kind") == "opener"), None)
    bead["tgb"] = {
        "truth": {"verdict": bead.get("verdict"), "extraction": bead.get("extractionStatus"), "zonesMeasured": sp.get("zones"),
                  "surprise": sp.get("total"), "dead": [names.get(h, h) for h in dead_now], "carried": [names.get(h, h) for h in carried_now]},
        "goodness": {"kept": kept, "lapsed": lapsed, "open": open_obl},
        "beauty": {"attractor": att.get("current"), "dominant": dom, "transition": tr, "scene": ((tr or {}).get("sceneResolved") or {}).get("id") if tr else None, "opener": opener},
    }
    bead["danceEvents"] = [e["id"] for e in emitted]
    return {"emitted": len(emitted), "tgb": bead["tgb"]}


def fold_camp(state: Dict[str, Any], pauses: List[Dict[str, Any]]) -> int:
    """Camp pauses are pushes on the intel / people strands."""
    n = 0
    for p in pauses or []:
        kind = p.get("pause")
        if kind in ("rumour", "arrival", "contact", "casualty"):
            obj = "people" if kind in ("arrival", "contact", "casualty") else "intel"
            append(state, "push", obj, p.get("heroId") or p.get("zoneId") or "camp", text=str(p.get("witness") or kind), icon={"rumour": "🌫", "arrival": "🚶", "contact": "⚠", "casualty": "🩸"}[kind],
                   minute=p.get("minute"), mission=state.get("missionNumber"), payload={k: v for k, v in p.items() if k not in ("witness",)})
            n += 1
        elif kind == "question":
            append(state, "transform", "question", str(p.get("question")), text=str(p.get("witness") or ""), icon="?", minute=p.get("minute"),
                   mission=state.get("missionNumber"), payload={"from": p.get("from"), "to": p.get("to")})
            n += 1
    return n


def main() -> int:
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    st = json.loads((ws / "state" / "campaign_state.json").read_text(encoding="utf-8-sig"))
    d = tape(st)
    print(f"dance tape: {len(d['events'])} events, {len(d['heads'])} objects")
    for e in d["events"][-20:]:
        print(f"  {e['token']} {e['icon']} m{e.get('missionNumber')} {e['kind']}:{e['object']:<18} {e['text'][:90]}" + (f"  owes: {e['obligations']}" if e.get("obligations") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
