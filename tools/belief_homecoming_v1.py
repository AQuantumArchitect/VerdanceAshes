#!/usr/bin/env python3
"""Fold one homecoming into the company's belief world (Umwelt) and split truth from intel.

Called by process_result after the bead exists and before the readings face is derived:

  1. load state/belief/verdance.engine.pkl (or boot blank, prime dark, replay prior beads)
  2. let the fog grow from the world's clock to the campaign clock (explicit steps)
  3. SURPRISE: before looking, read what the company believed about the zones this Drop
     measured; stamp bead["surprise"] (the gap between briefed and found)
  4. observe: Drop telemetry eta~1 on measured zones; new offscreen events reach camp as
     rumours with low eta and are appended to state["intel"] (what the company knows,
     with provenance); the questions take the event classes' pushes; named outcomes
  5. save the world; write outbox/intel.latest.json (intel/1)

`frontEvents` stays the world's truth and is not shown to the player; `state["intel"]` is
what reached camp. The belief world is the company's knowledge: it is persisted under
state/belief/ because it is a second, legitimate source of truth (about the company's
mind), never about the world.

Safe to skip: if Umwelt is not importable the fold returns {"skipped": True}.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

MAX_FOG_MINUTES = 7 * 1440.0
REST_MINUTES_DEFAULT = 720.0


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _world_paths(workspace: Path):
    d = workspace / "state" / "belief"
    d.mkdir(parents=True, exist_ok=True)
    return d / "verdance.engine.pkl", d / "verdance.engine.pkl.seen.json"


def _zone_rows(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for map_id, zones in (state.get("zoneMemory") or {}).items():
        for zid, z in (zones or {}).items():
            if isinstance(z, dict):
                out[zid] = dict(z, mapId=map_id)
    return out


def _drop_obs(z: Dict[str, Any]) -> Dict[str, float]:
    ab = z.get("abstract") or {}
    ctrl = str(z.get("controllingFaction") or ab.get("control") or "neutral")
    strength = max(float(ab.get("baseStrength") or 0), float(ab.get("militaryPressure") or 0), float(ab.get("fortification") or 0))
    return {"ours": 1.0 if ctrl == "ashwalkers" else 0.0, "held": 0.0 if ctrl == "neutral" else 1.0,
            "strength": _clamp(strength / 0.25), "threat": _clamp(float(ab.get("instability") or 0.0)),
            "faction": ctrl}


def _open_world(state: Dict[str, Any], workspace: Path):
    import umwelt_world_v1 as W
    truth = _zone_rows(state)
    extra = [{"zoneId": zid, "mapId": z.get("mapId"), "label": z.get("label")} for zid, z in truth.items()]
    pkl, _seen = _world_paths(workspace)
    world = W.VerdanceWorld(workspace, start_minute=0.0, extra_zones=extra)
    if pkl.exists():
        try:
            world.load(pkl)
            return world, False
        except Exception:
            pass
    world.prime_dark()
    return world, True


def observed_etas(state: Dict[str, Any], result: Dict[str, Any], bead: Dict[str, Any], truth: Dict[str, Dict[str, Any]],
                  map_id: str, workspace: Path) -> Dict[str, float]:
    """eta per zone for this Drop.

    Preferred: result.observedZones {zoneId: eta} from the gadget (line-of-sight share per zone,
    recency-weighted; pass 4). Fallback: a footprint proxy — zones where the player had units, deployed,
    extracted or struck the objective are 1.0; zones adjacent to those 0.5; the rest of the map 0.15
    (minimap-level awareness). Zones never seen stay dark even on a fought map."""
    on_map = {zid for zid, z in truth.items() if z.get("mapId") == map_id}
    given = result.get("observedZones")
    if isinstance(given, dict) and given:
        return {str(z): _clamp(e) for z, e in given.items() if str(z) in on_map and _clamp(e) > 0}
    strong = set()
    for key in ("deploymentZoneId", "extractionZoneId", "targetZoneId"):
        v = result.get(key) or bead.get(key)
        if v in on_map:
            strong.add(str(v))
    for fp in result.get("playerFootprint") or []:
        if isinstance(fp, dict) and fp.get("zoneId") in on_map:
            strong.add(str(fp["zoneId"]))
    for o in result.get("objectiveResults") or []:
        if isinstance(o, dict) and o.get("zoneId") in on_map:
            strong.add(str(o["zoneId"]))
    for ev in result.get("tenebriumClaimEvents") or []:
        if isinstance(ev, dict) and ev.get("zoneId") in on_map:
            strong.add(str(ev["zoneId"]))
    if not strong:
        # legacy result: everything measured on the map at 0.6 (we were there, we did not look everywhere)
        return {zid: 0.6 for zid in on_map if truth[zid].get("confidence") == "measured"}
    adj: Dict[str, List[str]] = {}
    try:
        g = _load(workspace / "data" / "zone_maps" / "world_zone_graph.v1.json")
        for e in g.get("edges") or []:
            a, b = str(e.get("from")), str(e.get("to"))
            adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    except Exception:
        pass
    out = {z: 1.0 for z in strong}
    for z in strong:
        for nz in adj.get(z, []):
            if nz in on_map and nz not in out:
                out[nz] = 0.5
    for zid in on_map:
        out.setdefault(zid, 0.15)
    return out


def _rest_minutes(state: Dict[str, Any]) -> float:
    camp = state.get("camp") or {}
    try:
        return float(camp.get("restMinutes") or REST_MINUTES_DEFAULT)
    except (TypeError, ValueError):
        return REST_MINUTES_DEFAULT


def fold_homecoming(state: Dict[str, Any], result: Dict[str, Any], bead: Dict[str, Any], workspace: Path,
                    *, before_front_count: int = 0, readings_face: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        import umwelt_world_v1 as W
    except SystemExit as exc:
        return {"skipped": True, "reason": str(exc)}
    except Exception as exc:  # pragma: no cover
        return {"skipped": True, "reason": repr(exc)}

    workspace = Path(workspace)
    world, fresh = _open_world(state, workspace)
    pkl, _ = _world_paths(workspace)
    truth = _zone_rows(state)
    held_maps = {z["mapId"] for z in truth.values() if z.get("controllingFaction") == "ashwalkers"}
    map_id = str(bead.get("mapId") or result.get("mapId") or "")
    mission = bead.get("missionNumber")
    now_minute = float(state.get("campaignClockMinutes") or 0.0)
    elapsed = float(bead.get("elapsedMinutes") or 0.0)
    drop_start = max(world.minute, now_minute - elapsed)

    # 2. the fog grows between the last homecoming and this Drop's start
    gap = max(0.0, min(MAX_FOG_MINUTES, drop_start - world.minute))
    if gap > 0:
        world.advance(gap, step_minutes=max(60.0, gap / 12.0))

    # which zones this Drop measured, and how well (eta per zone)
    eta_by_zone = observed_etas(state, result, bead, truth, map_id, workspace)
    measured = sorted(eta_by_zone)
    bead["observedZones"] = {z: round(e, 3) for z, e in sorted(eta_by_zone.items())}

    # 3. SURPRISE: what we believed before we looked
    per_zone = []
    total = 0.0
    for zid in measured:
        if zid not in world.host.engine.field.clusters:
            continue
        want = _drop_obs(truth[zid])
        b = world.zone_summary(zid)
        eta = float(eta_by_zone.get(zid, 1.0))
        gap_ours = b["ours"]["conf"] * abs(want["ours"] - b["ours"]["value"])
        gap_held = b["held"]["conf"] * abs(want["held"] - b["held"]["value"])
        gap_strength = 0.5 * b["strength"]["conf"] * abs(want["strength"] - b["strength"]["value"])
        # you can only be surprised by what you actually saw
        s = eta * (gap_ours + gap_held + gap_strength)
        total += s
        believed = ("ours" if b["ours"]["value"] > 0.5 else ("held by someone" if b["held"]["value"] > 0.5 else "empty")) if max(b["ours"]["conf"], b["held"]["conf"]) >= 0.15 else "nobody had looked"
        found = str(truth[zid].get("controllingFaction") or "neutral")
        found = "empty" if found == "neutral" else found
        per_zone.append({"zoneId": zid, "label": truth[zid].get("label") or zid, "surprise": round(s, 4), "eta": round(eta, 3),
                         "believed": believed, "found": found,
                         "belief": {k: v for k, v in b.items() if k in ("ours", "held", "strength")}})
    per_zone.sort(key=lambda r: -r["surprise"])
    bead["surprise"] = {"total": round(total, 4), "zones": len(measured), "top": per_zone[:3]}

    # 4a. Drop telemetry at each zone's own eta (one ingest for the whole homecoming)
    world.begin_batch()
    for zid in measured:
        if zid in world.host.engine.field.clusters:
            world.observe_zone(zid, source=f"drop:m{mission}", eta=float(eta_by_zone[zid]), minute=now_minute, **_drop_obs(truth[zid]))
    # 4a'. an in-match belief export (pass 4: the Lua belief field) lands directly at its own eta
    for zid, row in (result.get("beliefExport") or {}).items() if isinstance(result.get("beliefExport"), dict) else []:
        if zid in world.host.engine.field.clusters and isinstance(row, dict):
            world.observe_zone(str(zid), source=f"match:m{mission}", eta=_clamp(row.get("eta", 0.8)), minute=now_minute,
                               ours=row.get("ours"), held=row.get("held"), strength=row.get("strength"), threat=row.get("threat"))
    # 4b. what reached camp from elsewhere: rumours, with provenance, into state["intel"]
    intel = state.setdefault("intel", [])
    new_fronts = [f for f in (state.get("frontEvents") or [])[before_front_count:] if isinstance(f, dict)]
    for f in new_fronts:
        on_held = f.get("mapId") in held_maps
        if f.get("type") == "offscreen_clash":
            eta = 0.25 if on_held else 0.1
            zones = [z for z in (f.get("zoneA"), f.get("zoneB")) if z in truth]
            for zid in zones:
                if zid in world.host.engine.field.clusters:
                    world.observe_zone(str(zid), source="rumour:clash", eta=eta, minute=now_minute, threat=0.8)
            if zones and eta >= 0.25:
                intel.append({"kind": "rumour", "about": "shelling", "mapId": f.get("mapId"), "zones": zones, "eta": eta,
                              "source": "scouts heard guns", "missionNumber": mission, "minute": round(now_minute, 1)})
        elif f.get("type") == "offscreen_zone_flip":
            zid = f.get("zoneId")
            if zid in truth and zid in world.host.engine.field.clusters:
                eta = 0.35 if on_held else 0.15
                world.observe_zone(str(zid), source="rumour:flip", eta=eta, minute=now_minute, held=1.0, faction=str(f.get("toFaction") or "") or None,
                                   ours=1.0 if f.get("toFaction") == "ashwalkers" else 0.0, threat=0.6)
                if eta >= 0.3:
                    intel.append({"kind": "rumour", "about": "flip", "mapId": f.get("mapId"), "zoneId": zid, "label": f.get("label"),
                                  "toFaction": f.get("toFaction"), "fromFaction": f.get("fromFaction"), "eta": eta, "source": "word from the road", "missionNumber": mission, "minute": round(now_minute, 1)})
    if len(intel) > 400:
        del intel[:len(intel) - 400]
    # 4c. the questions: pushes from the event classes that fired on this bead (and unplaced snapshot ones once)
    seen_path = Path(str(pkl) + ".pushes_applied.json")
    applied = set()
    if seen_path.exists():
        try:
            applied = set(json.loads(seen_path.read_text(encoding="utf-8")))
        except Exception:
            applied = set()
    if readings_face is None:
        try:
            import readings_v1
            readings_face = readings_v1.project(json.loads(json.dumps(state)), workspace)
        except Exception:
            readings_face = None
    pair_to_q = {tuple(sorted(spec["pair"])): q for q, spec in W.QUESTIONS.items()}
    if readings_face:
        for c in readings_face.get("coherence") or []:
            q = pair_to_q.get(tuple(sorted(c["pair"])))
            if not q:
                continue
            for h in c.get("history") or []:
                if h.get("missionNumber") not in (mission, None):
                    continue
                key = f"{q}|{h.get('missionNumber')}|{h.get('class')}|{h.get('witness')}"
                if key in applied:
                    continue
                world.observe_question(q, toward=h.get("toward") if h.get("effect") == "distinguish" else None,
                                       strength=float(h.get("strength") or 0.0), source=f"event:{h.get('class')}", minute=now_minute)
                applied.add(key)
        seen_path.write_text(json.dumps(sorted(applied)), encoding="utf-8")
    # 4d. named outcomes
    for o in bead.get("namedOutcomes") or []:
        hid = str(o.get("charId"))
        if f"hero:{hid}" not in world.host.engine.field.clusters:
            continue
        if o.get("outcome") == "dead":
            world.observe({f"obs_hero_{hid}_fit": 0.0, f"obs_hero_{hid}_frame_intact": 0.5},
                          {f"obs_hero_{hid}_fit": 1.0, f"obs_hero_{hid}_frame_intact": 0.5}, source=f"drop:m{mission}", minute=now_minute)
        elif o.get("outcome") in ("recovered", "wounded"):
            world.observe({f"obs_hero_{hid}_fit": 0.3}, 1.0, source=f"drop:m{mission}", minute=now_minute)
        elif o.get("outcome") == "survived":
            world.observe({f"obs_hero_{hid}_fit": 0.9}, 0.6, source=f"drop:m{mission}", minute=now_minute)

    world.flush()
    # 4e. the other minds: truth frame (hidden), faction beliefs by policy, divergence
    try:
        import perspectives_v1 as P
        P.write_truth(state, workspace)
        fought = {"mapId": map_id, "zones": [z for z, e in eta_by_zone.items() if e >= 0.5], "against": str(result.get("against") or result.get("enemyFaction") or "")}
        P.enqueue(state, workspace, new_fronts=new_fronts, fought=fought, minute=now_minute)
    except Exception as exc:  # perspectives are optional; never block the company's fold
        try:
            print(f"VA_PERSPECTIVES_FAIL {exc}")
        except Exception:
            pass
    # 5. persist + face
    world.save(pkl)
    frame = world.frame()
    frame["surprise"] = bead["surprise"]
    frame["intel"] = intel[-40:]
    frame["fresh"] = fresh
    out = workspace / "outbox" / "intel.latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(frame, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        import perspectives_v1 as P
        P.divergence(state, workspace)
    except Exception:
        pass
    return {"skipped": False, "measured": len(measured), "surprise": bead["surprise"]["total"], "rumours": len(new_fronts),
            "fresh": fresh, "fieldHash": frame["producer"]["field_hash"]}


def intel_for_intent(state: Dict[str, Any], workspace: Path, map_id: Optional[str]) -> Dict[str, Any]:
    """What the sortie stamp carries INTO the Drop: the company's belief about the planned map (not
    truth), who is posted where, and which frames lie where. The HUD shows belief until line of
    sight confirms (pass 4); the surprise then happens live."""
    out: Dict[str, Any] = {"schema": "verdance-intent-intel/0.1", "perspective": "company", "mapId": map_id, "zones": {}, "posted": [], "frames": [], "asOfMinute": None}
    frame_path = Path(workspace) / "outbox" / "intel.latest.json"
    if frame_path.exists():
        try:
            frame = _load(frame_path)
            out["asOfMinute"] = frame.get("as_of_minute")
            for r in frame.get("nodes") or []:
                if r.get("mapId") != map_id or not r.get("role"):
                    continue
                z = out["zones"].setdefault(str(r["node"]), {"label": r.get("label")})
                z[str(r["role"])] = {"value": r.get("value"), "confidence": r.get("confidence"), "state": r.get("state"), "age_min": r.get("age_min"), "source": r.get("source")}
            out["questions"] = [{"id": q["id"], "icon": q.get("icon"), "status": q.get("status"), "lean": q.get("lean")} for q in frame.get("questions") or []]
        except Exception:
            pass
    camp = state.get("camp") or {}
    names = {hid: (ch.get("name") or hid) for hid, ch in (state.get("characters") or {}).items() if isinstance(ch, dict)}
    for hid, rec in (camp.get("people") or {}).items():
        if rec.get("where") in ("posted", "transit") and rec.get("zoneId"):
            out["posted"].append({"heroId": hid, "name": names.get(hid, hid), "zoneId": rec.get("zoneId"), "where": rec.get("where"), "eta": rec.get("eta")})
    for e in ((state.get("dance") or {}).get("events") or []):
        if e.get("verb") == "null" and e.get("kind") == "hero" and e.get("obligations"):
            heads = (state.get("dance") or {}).get("heads") or {}
            if heads.get(f"hero:{e.get('object')}") == e.get("id"):
                pl = e.get("payload") or {}
                out["frames"].append({"heroId": e.get("object"), "name": names.get(e.get("object"), e.get("object")), "mapId": pl.get("mapId"), "zoneId": pl.get("zoneId"), "since": e.get("missionNumber")})
    return out


if __name__ == "__main__":
    # Manual fold of the last bead in a save: python tools/belief_homecoming_v1.py [workspace]
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    st = _load(ws / "state" / "campaign_state.json")
    beads = st.get("history") or []
    if not beads:
        print("no beads")
        sys.exit(0)
    print(json.dumps(fold_homecoming(st, {"mapId": beads[-1].get("mapId")}, beads[-1], ws), indent=1))
