#!/usr/bin/env python3
"""The manifest, read by the campaign (pass five).

The gadget writes facts: who was on the pad, who and what was not, where the company extracted to,
what it looked at. This module is the only place those facts become campaign meaning:

  facts in     result.status        terminal KIND: extracted | wiped | closed (never a verdict)
               result.manifest      {kind, destination, going, staying, enemyOnPad, objectiveComplete, seen}
               result.objectiveComplete / objectiveCompleteHow / allObjectivesDone / requiredMarksLeft
               (pass nine: the gadget no longer writes verdict, zoneFlipped, cleanExtract,
               extractionStatus, credits or freeTnbMint — those are computed here and in
               match_credit_v1 from the facts above)
  verdict      wiped → defeat · closed (engine ended without a manifest) → abandon ·
               extracted → victory if the objective was done and nobody was left, else partial
  people left  stay where they stood: camp.people[hid] = {where: "field", zoneId}; they do not board the
               next Drop until recalled or picked up; the dance tape owes "bring <name> back from <zone>"
  things left  structures are already the footprint (result.playerFootprint) and the zone's holdings;
               nothing more to do here — a holding is a holding whoever's it is
  destination  "home" → camp; a zone → the next sortie on that map lands there (camp.nextPadZoneId)
  contested    enemy units on the pad at confirm → extractionStatus "contested"
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def manifest_of(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    m = result.get("manifest")
    return m if isinstance(m, dict) and m.get("schema", "").startswith("verdance-manifest") else None


def objective_done(result: Dict[str, Any]) -> bool:
    """The primary objective completed, as the gadget reported it (manifest stamp first)."""
    m = manifest_of(result)
    if m is not None and m.get("objectiveComplete") is not None:
        return bool(m.get("objectiveComplete"))
    if result.get("objectiveComplete") is not None:
        return bool(result.get("objectiveComplete"))
    # older results: an objective row that says complete / destroyed / claimed
    for row in result.get("objectiveResults") or []:
        if isinstance(row, dict) and row.get("status") in ("complete", "destroyed", "claimed"):
            return True
    return bool(result.get("destroyedObjectiveIds"))


def heroes_left(result: Dict[str, Any]) -> list:
    """Hero ids the company left standing in the field when it lifted (manifest.staying)."""
    m = manifest_of(result)
    if m is None:
        return []
    return [str(h.get("heroId") or "") for h in (m.get("staying") or {}).get("heroes") or [] if isinstance(h, dict)]


def verdict_from(result: Dict[str, Any]) -> Optional[str]:
    """None when the result carries no manifest and no terminal kind (legacy results keep
    their own status).

    extracted → victory when the objective was done and nobody was left, else partial
    wiped     → defeat
    closed    → abandon (the engine ended the game without a manifest)
    A result without a manifest but with a terminal kind (fallback blob, old gadget) is
    read the same way, with extracted → partial since the headcount is unknown.
    """
    m = manifest_of(result)
    status = str(result.get("status") or "")
    if m is None:
        if status in ("extracted", "wiped", "closed"):
            return {"extracted": "partial", "wiped": "defeat", "closed": "abandon"}[status]
        return None
    kind = str(m.get("kind") or status or "extracted")
    if kind == "wiped":
        return "defeat"
    if kind == "closed":
        return "abandon"
    return "victory" if (objective_done(result) and not heroes_left(result)) else "partial"


def extraction_status_from(result: Dict[str, Any]) -> Optional[str]:
    m = manifest_of(result)
    if m is None:
        return None
    if str(m.get("kind") or "") != "extracted":
        return ""
    return "contested" if int(m.get("enemyOnPad") or 0) > 0 else "clean"


def fold_manifest(state: Dict[str, Any], result: Dict[str, Any], bead: Dict[str, Any], workspace=None) -> Dict[str, Any]:
    m = manifest_of(result)
    if m is None:
        return {"skipped": True}
    going, staying = m.get("going") or {}, m.get("staying") or {}
    camp = state.setdefault("camp", {})
    people = camp.setdefault("people", {})
    minute = float(state.get("campaignClockMinutes") or 0.0)
    mission = int(state.get("missionNumber") or 0)
    map_id = result.get("mapId") or bead.get("mapId")
    summary = {
        "kind": m.get("kind"), "destination": m.get("destination"), "pad": (m.get("pad") or {}).get("zoneId"),
        "going": {"heroes": [h.get("heroId") for h in going.get("heroes") or []], "units": int(going.get("unitCount") or 0)},
        "staying": {"heroes": [{"heroId": h.get("heroId"), "zoneId": h.get("zoneId")} for h in staying.get("heroes") or []],
                    "units": int(staying.get("unitCount") or 0), "structures": int(staying.get("structureCount") or 0)},
        "enemyOnPad": int(m.get("enemyOnPad") or 0), "seen": len(m.get("seen") or {}),
    }
    bead["manifest"] = summary
    # people who came home are home
    for h in going.get("heroes") or []:
        hid = str(h.get("heroId") or "")
        if hid and (people.get(hid) or {}).get("where") in ("field", "posted", "transit"):
            people.pop(hid, None)
    # people left stand where they stood
    chars = state.get("characters") or {}
    left_rows = []
    for h in staying.get("heroes") or []:
        hid = str(h.get("heroId") or "")
        if not hid:
            continue
        ch = chars.get(hid) or {}
        if ch.get("status") == "dead":
            continue
        people[hid] = {"where": "field", "zoneId": h.get("zoneId"), "mapId": map_id, "label": h.get("label"), "since": round(minute, 1), "sinceMission": mission}
        left_rows.append(hid)
        try:
            import story_dance_v1 as dance
            name = ch.get("name") or hid
            dance.append(state, "null", "hero", hid, text=f"{name} was left at {h.get('label') or h.get('zoneId')} when the company lifted",
                         icon="🫥", minute=minute, mission=mission, payload={"zoneId": h.get("zoneId"), "mapId": map_id},
                         obligations=[f"bring {name} back from {h.get('label') or h.get('zoneId')}"], once=f"left:{hid}:m{mission}")
        except Exception:
            pass
    # where the company went
    dest = str(m.get("destination") or "home")
    if dest not in ("home", "none", ""):
        camp["nextPadZoneId"] = dest
        camp["nextPadMapId"] = next((d.get("mapId") for d in m.get("destinations") or [] if str(d.get("id")) == dest), None) or map_id
    else:
        camp.pop("nextPadZoneId", None)
        camp.pop("nextPadMapId", None)
    camp["lastManifest"] = summary
    return {"skipped": False, "left": left_rows, "destination": dest, "verdict": verdict_from(result)}
