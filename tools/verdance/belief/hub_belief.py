#!/usr/bin/env python3
"""What the hub is allowed to paint (pass six): the company's belief, never the truth.

build_hub_state_v1 used to read zoneMemory.controllingFaction into every zone's colour. This module
replaces that read with the belief frame (outbox/intel.latest.json) and folds the rest of the
interstitial faces the board needs: who is where (camp), what we hold (holdings), what the other side
knows of us (exposure — our side of the mirror only), and the last manifest.

Per zone the board gets:
  believed   ours | held | empty | dark | unsure      (fill)
  faction    who we last SAW holding it, when held    (fill colour: a faction's colour means "we believe
                                                       they hold it", at the held confidence)
  confidence 0..1 (alpha)        state current | stale | dark (ring)        age_min, source
  threat     believed threat 0..1 (hatch weight)     surprise  the last homecoming's contradiction, if any
  people     heroes left in the field / posted here  holding  structures we left here (count)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from verdance.common import load_json

def _believed(ours: Dict[str, Any], held: Dict[str, Any]) -> tuple[str, float]:
    oc, hc = float(ours.get("confidence") or 0), float(held.get("confidence") or 0)
    dark_o = ours.get("state") == "dark" or ours.get("value") is None
    dark_h = held.get("state") == "dark" or held.get("value") is None
    if dark_o and dark_h:
        return "dark", 0.0
    ov = float(ours.get("value") if ours.get("value") is not None else 0.5)
    hv = float(held.get("value") if held.get("value") is not None else 0.5)
    if ov > 0.5 and oc > 0.15:
        return "ours", oc
    if hv > 0.5 and hc > 0.15:
        return "held", hc
    if hv <= 0.5 and hc > 0.15:
        return "empty", hc
    return "unsure", max(oc, hc)


def belief_surface(ws: Path, state: Dict[str, Any], map_id: Optional[str] = None) -> Dict[str, Any]:
    """Zones as the company believes them. Fresh campaign (no frame yet): everything dark."""
    out: Dict[str, Any] = {"schema": "verdance-hub-belief/1", "zones": {}, "counts": {"current": 0, "stale": 0, "dark": 0},
                           "asOfMinute": None, "surprise": [], "source": "none"}
    p = ws / "outbox" / "intel.latest.json"
    frame = None
    if p.is_file():
        try:
            frame = load_json(p)
        except Exception:
            frame = None
    rows: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if frame:
        out["asOfMinute"] = frame.get("as_of_minute")
        out["source"] = "intel.latest.json"
        for r in frame.get("nodes") or []:
            node, role = r.get("node"), r.get("role")
            if not node or not role or not r.get("mapId"):
                continue
            if map_id and r.get("mapId") != map_id:
                continue
            rows.setdefault(str(node), {"_label": r.get("label"), "_map": r.get("mapId")})[str(role)] = r
        for t in (frame.get("surprise") or {}).get("top") or []:
            out["surprise"].append({"zoneId": t.get("zoneId"), "label": t.get("label"), "believed": t.get("believed"), "found": t.get("found"), "surprise": t.get("surprise"), "eta": t.get("eta")})
    # every zone the campaign knows about appears, dark when the frame has nothing
    zm_all = state.get("zoneMemory") or {}
    for m, zones in zm_all.items():
        if map_id and m != map_id:
            continue
        for zid, z in (zones or {}).items():
            if isinstance(z, dict):
                rows.setdefault(str(zid), {"_label": z.get("label"), "_map": m})
    sur = {s["zoneId"]: s for s in out["surprise"] if s.get("zoneId")}
    camp = state.get("camp") or {}
    people_by_zone: Dict[str, list] = {}
    names = {hid: (ch.get("name") or hid) for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict)}
    for hid, rec in (camp.get("people") or {}).items():
        if isinstance(rec, dict) and rec.get("where") in ("field", "posted", "transit") and rec.get("zoneId"):
            people_by_zone.setdefault(str(rec["zoneId"]), []).append({"heroId": hid, "name": names.get(hid, hid), "where": rec.get("where"), "wounded": bool(rec.get("wounded"))})
    footprints = state.get("playerFootprints") or {}
    for zid, rr in rows.items():
        ours, held = rr.get("ours") or {}, rr.get("held") or {}
        bel, conf = _believed(ours, held)
        states = [r.get("state") for r in (ours, held) if r]
        st = "dark" if (not states or all(s == "dark" for s in states)) else ("stale" if all(s in ("stale", "dark") for s in states) else "current")
        m = rr.get("_map")
        fp = 0
        try:
            fp = len([u for u in (footprints.get(m) or []) if isinstance(u, dict) and str(u.get("zoneId")) == zid])
        except Exception:
            fp = 0
        row = {
            "zoneId": zid, "mapId": m, "label": rr.get("_label") or zid,
            "believed": bel, "confidence": round(conf, 3), "state": st,
            "faction": held.get("faction") if bel in ("ours", "held") else None,
            "age_min": held.get("age_min") if held.get("age_min") is not None else ours.get("age_min"),
            "source": held.get("source") or ours.get("source"),
            "threat": (rr.get("threat") or {}).get("value"),
            "threatConfidence": (rr.get("threat") or {}).get("confidence"),
            "surprise": sur.get(zid),
            "people": people_by_zone.get(zid) or [],
            "holding": fp,
        }
        if bel == "ours":
            row["faction"] = "ashwalkers"
        out["zones"][zid] = row
        out["counts"][st if st in out["counts"] else "dark"] += 1
    return out


def believed_holder(row: Optional[Dict[str, Any]]) -> str:
    """One word for who the company believes holds a zone, from a belief_surface row.

    "ashwalkers" (ours) | <faction> (held, when we saw who) | "held" (held, by whom unknown)
    | "empty" | "unknown" (dark / unsure / no row). Never a truth read.
    """
    if not row:
        return "unknown"
    bel = str(row.get("believed") or "dark")
    if bel == "ours":
        return "ashwalkers"
    if bel == "held":
        return str(row.get("faction") or "held").lower()
    if bel == "empty":
        return "empty"
    return "unknown"


def _own_ledger_zones(state: Dict[str, Any]) -> set:
    """Zones the company itself claimed or built on: company knowledge (a stale 'ours'), not truth."""
    out: set = set()
    # claimedNodes: {mapId: {zoneId: rec}}   nodeClaims: {mapId: [rec{zoneId}]}
    for mid, zones in (state.get("claimedNodes") or {}).items():
        if isinstance(zones, dict):
            out.update(str(z) for z, rec in zones.items() if isinstance(rec, dict))
    for mid, items in (state.get("nodeClaims") or {}).items():
        if isinstance(items, list):
            out.update(str(r.get("zoneId")) for r in items if isinstance(r, dict) and r.get("zoneId"))
    for m, units in (state.get("playerFootprints") or {}).items():
        for u in units or []:
            if isinstance(u, dict) and u.get("zoneId"):
                out.add(str(u["zoneId"]))
    return out


def believed_ours(ws: Path, state: Dict[str, Any]) -> set:
    """Zone ids the company believes it holds: the belief frame first, then its own claim ledger
    when no frame has been written yet (a fresh campaign has looked at nothing)."""
    try:
        surf = belief_surface(ws, state, None)
    except Exception:
        surf = {"zones": {}, "source": "none"}
    ours = {zid for zid, r in (surf.get("zones") or {}).items() if r.get("believed") == "ours"}
    if surf.get("source") == "none":
        ours |= _own_ledger_zones(state)
    return ours


def camp_surface(state: Dict[str, Any]) -> Dict[str, Any]:
    camp = state.get("camp") or {}
    names = {hid: (ch.get("name") or hid) for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict)}
    people = []
    for hid, rec in (camp.get("people") or {}).items():
        if isinstance(rec, dict):
            people.append(dict(rec, heroId=hid, name=names.get(hid, hid)))
    return {"clockMinutes": camp.get("clockMinutes") or state.get("campaignClockMinutes") or 0.0,
            "people": people, "nextPadZoneId": camp.get("nextPadZoneId"), "nextPadMapId": camp.get("nextPadMapId"),
            "homeZoneId": camp.get("homeZoneId"), "homeMapId": camp.get("homeMapId"), "lastManifest": camp.get("lastManifest")}


def away_from_camp(state: Dict[str, Any]) -> set:
    return {str(h) for h, r in ((state.get("camp") or {}).get("people") or {}).items() if isinstance(r, dict) and r.get("where") in ("posted", "transit", "field")}


def exposure_surface(ws: Path) -> Dict[str, Any]:
    """Our side of the mirror only: which of OUR holdings Armada has eyes on. Never their beliefs about the world."""
    p = ws / "outbox" / "divergence.latest.json"
    if not p.is_file():
        return {"present": False}
    try:
        d = load_json(p)
    except Exception:
        return {"present": False}
    out: Dict[str, Any] = {"present": True, "asOfMinute": d.get("as_of_minute"), "factions": {}}
    for fac, c in (d.get("crossed") or {}).items():
        a = c.get("aboutCompany") or {}
        out["factions"][fac] = {"known": list(a.get("known") or []), "suspected": list(a.get("suspected") or []), "blind": list(a.get("blind") or []), "ofOurs": a.get("ofOurs")}
    return out


def last_manifest(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    hist = state.get("history") or []
    for b in reversed(hist):
        if isinstance(b, dict) and isinstance(b.get("manifest"), dict):
            return dict(b["manifest"], missionNumber=b.get("missionNumber"), mapId=b.get("mapId"))
    return None
