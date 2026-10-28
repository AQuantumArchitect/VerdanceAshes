#!/usr/bin/env python3
"""The chronicle: the φ record folded the brain-ant way.

Consecutive Drops under the same attractor fold into one chapter row carrying n and the
missions it spans; named events never fold: a death, a frame carried home, a promise
kept or lapsed, a claim, a join, a surprise, a transition, the roll. Fewer rows, every
icon of a kept event still present, the last done thing still queryable. The referee is
`check()`; a chronicle that drops a kept icon or loses last_done is rejected.

Reads state.history (beads with tgb) and state.dance; writes outbox/chronicle.latest.json
and .md. DERIVE: never writes state.

    python -m verdance.readings.chronicle [workspace]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, load_json

ROOT = WORKSPACE_ROOT
SCHEMA = "verdance-chronicle/0.1"
from verdance.readings.story_dance import FOLD_NEVER as KEEP_VERBS  # named events never fold
KEEP_ICONS = {"❗", "📍", "🤝", "💔", "🪦", "🫱", "➕"}


def build(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    beads = [b for b in (state.get("history") or []) if isinstance(b, dict)]
    events = [e for e in ((state.get("dance") or {}).get("events") or []) if isinstance(e, dict)]
    by_mission: Dict[Any, List[Dict[str, Any]]] = {}
    for e in events:
        by_mission.setdefault(e.get("missionNumber"), []).append(e)
    att_icons = {}
    try:
        for a in load_json((workspace or ROOT) / "data" / "story" / "attractors.json").get("attractors") or []:
            att_icons[a["id"]] = a.get("icon", "•")
    except Exception:
        pass

    rows: List[Dict[str, Any]] = []
    chapter: Optional[Dict[str, Any]] = None
    for b in beads:
        m = b.get("missionNumber")
        tgb = b.get("tgb") or {}
        att = (tgb.get("beauty") or {}).get("attractor") or "shelf"
        kept = [e for e in by_mission.get(m, []) if e.get("verb") in KEEP_VERBS or e.get("icon") in KEEP_ICONS]
        transition = (tgb.get("beauty") or {}).get("transition")
        if chapter is None or chapter["fold"]["attractor"] != att or transition:
            if chapter is not None:
                rows.append(chapter)
            chapter = {"id": f"chapter.{att}.{m}", "icon": att_icons.get(att, "•"),
                       "fold": {"kind": "chapter", "attractor": att, "n": 0, "missions": [m, m],
                                "verdicts": {"victory": 0, "partial": 0, "defeat": 0}, "surprise": 0.0, "dead": 0, "carried": 0},
                       "keeps": [], "text": ""}
            if transition:
                chapter["entered_from"] = transition.get("from")
                chapter["scene"] = (tgb.get("beauty") or {}).get("scene")
        f = chapter["fold"]
        f["n"] += 1
        f["missions"][1] = m
        f["verdicts"][str(b.get("verdict"))] = f["verdicts"].get(str(b.get("verdict")), 0) + 1
        f["surprise"] = round(f["surprise"] + float((tgb.get("truth") or {}).get("surprise") or 0.0), 3)
        f["dead"] += len((tgb.get("truth") or {}).get("dead") or [])
        f["carried"] += len((tgb.get("truth") or {}).get("carried") or [])
        for e in kept:
            chapter["keeps"].append({"id": e["id"], "token": e["token"], "icon": e.get("icon"), "mission": m, "text": e.get("text"), "obligations": e.get("obligations")})
        chapter["last_done"] = b.get("resultKey") or f"m{m}"
        chapter["text"] = (f"{att_icons.get(att, '•')} {att}: {f['n']} Drop(s) m{f['missions'][0]}–m{f['missions'][1]}, "
                           f"{f['verdicts'].get('victory', 0)}W {f['verdicts'].get('partial', 0)}P {f['verdicts'].get('defeat', 0)}L, "
                           f"{f['dead']} on the roll, {f['carried']} carried, surprise {f['surprise']:.1f}")
    if chapter is not None:
        rows.append(chapter)

    # open obligations: every ∅ / Δ whose obligations have not been answered by a later push on the same object
    heads = (state.get("dance") or {}).get("heads") or {}
    open_obl = []
    for e in events:
        if not e.get("obligations"):
            continue
        key = f"{e.get('kind')}:{e.get('object')}"
        if heads.get(key) == e.get("id"):
            open_obl.append({"event": e["id"], "icon": e.get("icon"), "object": key, "obligations": e["obligations"], "since": e.get("missionNumber")})

    roll = [hid for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict) and ch.get("status") == "dead"]
    out = {"schemaVersion": SCHEMA, "rows": rows, "n_events": len(events), "n_beads": len(beads), "n_rows": len(rows),
           "last_done": rows[-1]["last_done"] if rows else None, "roll": roll, "open_obligations": open_obl,
           "law": "fewer rows than events; every kept icon survives; last_done stays queryable"}
    out["check"] = check(out, events)
    return out


def check(chron: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    kept_icons = {e.get("icon") for e in events if e.get("verb") in KEEP_VERBS or e.get("icon") in KEEP_ICONS}
    present = {k.get("icon") for r in chron["rows"] for k in r.get("keeps") or []}
    missing = sorted(i for i in kept_icons if i and i not in present)
    fewer = chron["n_rows"] <= max(1, chron["n_events"])
    return {"fewer_rows": fewer, "icons_kept": not missing, "missing_icons": missing, "last_done_queryable": bool(chron.get("last_done")) or chron["n_beads"] == 0,
            "ok": fewer and not missing and (bool(chron.get("last_done")) or chron["n_beads"] == 0)}


def markdown(chron: Dict[str, Any]) -> str:
    L = [f"# The φ record — {chron['n_beads']} Drops folded into {chron['n_rows']} chapter(s); {chron['n_events']} dance events", ""]
    for r in chron["rows"]:
        L.append(f"## {r['text']}")
        if r.get("entered_from"):
            L.append(f"_entered from {r['entered_from']}" + (f" · scene `{r['scene']}`" if r.get("scene") else "") + "_")
        for k in r.get("keeps") or []:
            L.append(f"- {k['token']} {k['icon']} m{k['mission']} {k['text']}" + (f"  — owes: {'; '.join(k['obligations'])}" if k.get("obligations") else ""))
        L.append("")
    if chron.get("open_obligations"):
        L.append("## Still owed")
        for o in chron["open_obligations"]:
            L.append(f"- {o['icon']} since m{o['since']}: " + "; ".join(o["obligations"]))
        L.append("")
    c = chron["check"]
    L.append(f"_referee: fewer_rows={c['fewer_rows']} icons_kept={c['icons_kept']} last_done={chron.get('last_done')} → {'ok' if c['ok'] else 'REJECTED'}_")
    return "\n".join(L)


def write(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    chron = build(state, workspace)
    out = workspace / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    (out / "chronicle.latest.json").write_text(json.dumps(chron, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "chronicle.latest.md").write_text(markdown(chron), encoding="utf-8")
    return chron


def main() -> int:
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    st = json.loads((ws / "state" / "campaign_state.json").read_text(encoding="utf-8-sig"))
    print(markdown(write(st, ws)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
