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
               extracted → victory if the job was done and nobody was stranded, else partial
               The job is done when the primary objective completed OR the company ended the sortie
               holding ground it took from an enemy (ground_taken). Nobody stranded means no hero
               was left on ground the company does not hold: a garrison on held ground is a post,
               not an abandonment. No fixed checklist, no one way to win.
  people left  stay where they stood: camp.people[hid] = {where: "field", zoneId}; they do not board the
               next Drop until recalled or picked up; the dance tape owes "bring <name> back from <zone>"
  things left  structures are already the footprint (result.playerFootprint) and the zone's holdings;
               nothing more to do here — a holding is a holding whoever's it is
  destination  "home" → camp; a zone → the next sortie on that map lands there (camp.nextPadZoneId)
  contested    enemy units on the pad at confirm → extractionStatus "contested"
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from verdance.readings import story_dance as dance


def manifest_of(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    m = result.get("manifest")
    return m if isinstance(m, dict) and m.get("schema", "").startswith("verdance-manifest") else None


def throne_taken(result: Dict[str, Any]) -> Optional[bool]:
    """The kings' showdown, read from the kings gadget's facts: the throne is the company's when
    every rival king fell and ours stands. None when the sortie was not a showdown."""
    kings = result.get("kings")
    if not isinstance(kings, list) or not kings:
        return None
    ours = [k for k in kings if isinstance(k, dict) and str(k.get("faction")) == "ashwalkers"]
    rivals = [k for k in kings if isinstance(k, dict) and str(k.get("faction")) != "ashwalkers"]
    return bool(rivals) and all(k.get("fallen") for k in rivals) and not any(k.get("fallen") for k in ours)


def objective_done(result: Dict[str, Any]) -> bool:
    """The primary objective completed, as the gadget reported it (manifest stamp first; a
    kings' showdown is the throne, read from the kings' facts)."""
    throne = throne_taken(result)
    if throne is not None:
        return throne
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


COMPANY = "ashwalkers"
GROUND_TAKEN = "ground_taken"
# Whose zones the company can take: the factions it fights. Neutral ground has no one to take it
# from; the Mercs are its patron and the Legion its own.
ENEMY_HOLDERS = frozenset({"armada", "cortex", "wild"})


def held_zones(result: Dict[str, Any], workspace=None) -> list:
    """Zones the company holds when it lifts: its presence in the zone leads and meets the claim
    need (verdance.world.claim, the same rule that moves zone control). From result.zoneDv, a fact.
    A result that already carries groundHeld (the campaign read it with the workspace) keeps it."""
    pre = result.get("groundHeld")
    if isinstance(pre, list):
        return [str(z) for z in pre]
    dv = result.get("zoneDv")
    if not isinstance(dv, dict) or not dv:
        return []
    from verdance.world.claim import claim_need, holder
    need = claim_need(result.get("deploymentMapId") or result.get("mapId") or "", workspace)
    out = []
    for zone_id, row in dv.items():
        if isinstance(row, dict) and holder(row, need)[0] == COMPANY:
            out.append(str(zone_id))
    return sorted(out)


def ground_taken(state: Dict[str, Any], result: Dict[str, Any], workspace=None) -> list:
    """Zones the company holds now that an enemy (or the wild) held before it came. Read-only: the
    campaign has not yet moved any zone's control when this is asked. Not for a kings' showdown,
    which has its own end (the throne)."""
    if throne_taken(result) is not None:
        return []
    from verdance.common import canonical_map_id
    from verdance.campaign.zones import canonical_zone_id
    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or "")
    memory = ((state.get("zoneMemory") or {}).get(map_id) or {})
    out = []
    for zone_id in held_zones(result, workspace):
        zid = canonical_zone_id(zone_id, workspace) or zone_id
        before = str((memory.get(zid) or {}).get("controllingFaction") or "").lower()
        if before in ENEMY_HOLDERS:
            out.append(str(zid))
    return sorted(out)


def with_ground(state: Dict[str, Any], result: Dict[str, Any], workspace=None) -> Dict[str, Any]:
    """The result with the two ground facts the campaign reads for it (groundHeld, groundTaken)."""
    out = dict(result)
    out["groundHeld"] = held_zones(result, workspace)
    out["groundTaken"] = ground_taken(state, {**result, "groundHeld": out["groundHeld"]}, workspace)
    return out


def stranded(result: Dict[str, Any], workspace=None) -> list:
    """Hero ids left in the field on ground the company does not hold. A hero staying on ground the
    company holds is a garrison. A result with no zoneDv says nothing about the ground, so everyone
    left counts (the old reading)."""
    left = [h for h in (((manifest_of(result) or {}).get("staying") or {}).get("heroes") or []) if isinstance(h, dict)]
    if not left:
        return []
    dv = result.get("zoneDv")
    if not isinstance(dv, dict) or not dv:
        return [str(h.get("heroId") or "") for h in left]
    held = set(held_zones(result, workspace))
    return [str(h.get("heroId") or "") for h in left if str(h.get("zoneId") or "") not in held]


def dropped(result: Dict[str, Any]) -> Optional[set]:
    """Hero ids of the company on this field (manifest.dropped), or None for an older result."""
    m = manifest_of(result)
    if m is None or not isinstance(m.get("dropped"), list):
        return None
    return {str(h) for h in m["dropped"] if h}


def vanished(result: Dict[str, Any]) -> set:
    """Heroes who dropped but were neither going nor staying when the company lifted: they did not
    survive the field. The headcount is the truth even when the gadget's hero ledger was lost (a
    LuaRules reload emptied it once and a dead Ketha came home)."""
    m = manifest_of(result)
    who = dropped(result)
    if m is None or not who:
        return set()
    present = {str(h.get("heroId") or "") for side in ("going", "staying")
               for h in ((m.get(side) or {}).get("heroes") or []) if isinstance(h, dict)}
    return who - present


def field_people(state: Dict[str, Any], map_id: str, workspace: Optional[Path] = None) -> list:
    """The people the company left standing on this map (camp.people where == "field"): the next
    drop here finds them where they stood, so they can be brought home.

    The spearhead (owner, 2026-10-27): someone left standing on a door the company holds is at the
    mouth of the road, so a drop on the far map finds them on its far door, ready to go on."""
    chars = state.get("characters") or {}
    doors = {}
    if workspace is not None:
        try:
            from verdance.world import roads
            doors = roads.load_doors(Path(workspace))
        except Exception:  # noqa: BLE001
            doors = {}
    out = []
    for hid, rec in sorted(((state.get("camp") or {}).get("people") or {}).items()):
        if not isinstance(rec, dict) or rec.get("where") != "field" or not rec.get("zoneId"):
            continue
        if (chars.get(hid) or {}).get("status") == "dead":
            continue
        zone, at_map = str(rec["zoneId"]), str(rec.get("mapId") or "")
        if at_map == str(map_id):
            out.append({"heroId": str(hid), "zoneId": zone})
            continue
        door = doors.get(zone)
        held = isinstance((state.get("doors") or {}).get(zone), dict) and (state.get("doors") or {})[zone].get("held")
        if door and held and str(door.get("farMapId")) == str(map_id):
            out.append({"heroId": str(hid), "zoneId": str(door["farZoneId"]), "spearhead": True, "fromZoneId": zone})
    return out


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
    done = objective_done(result) or bool(result.get("groundTaken"))
    return "victory" if (done and not stranded(result)) else "partial"


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
