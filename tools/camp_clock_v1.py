#!/usr/bin/env python3
"""The camp clock: interstitial time, weak measurements, surprise pauses.

Between Drops the clock runs. Camp actions have durations; while they run the world
evolves (offscreen ticks and clashes, truth only), the company's belief world eases
toward the fog, posted people keep measuring the ground they stand on (looking is
keeping), and anything that reaches camp arrives as intel with provenance. Time runs
until something is worth a line: a pause. A pause is a minor bead on state["campLog"],
and the cast speaks to it through the same occasions machinery as a homecoming.

Actions (all advance campaignClockMinutes):
  rest    {hours}                 the fog grows; a wounded hero stands up after 12h
  scout   {zoneId}                a patrol: 4h + travel; eta 0.55 on the zone, 0.2 on neighbours
  post    {heroId, zoneId}        send someone to stand on ground; they measure it every hour (eta 0.7)
  recall  {heroId}                bring them home (travel time)
  wait    {hours}                 like rest, but nobody heals; the explicit "let it run"

Pause conditions (checked each clock step):
  contact   a posted hero's ground is no longer ours / is held by someone else
  rumour    a flip or shelling reached camp on a map we hold (eta >= 0.3)
  question  one of the six questions changed status
  arrival   a posted hero / patrol arrived
  done      the action's duration elapsed

Truth is mutated only through the engine's own offscreen functions (tick_offscreen_zones,
run_offscreen_clashes, record_front_event). Belief is mutated only through the Umwelt world.
Nothing here writes outbox faces except camp.latest.json and intel.latest.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

STEP_MINUTES = 60.0
TRAVEL_MINUTES_PER_HOP = 45.0
TRAVEL_MINUTES_CROSS_MAP = 240.0
SCOUT_MINUTES = 240.0
HEAL_AFTER_REST_MINUTES = 720.0
POST_ETA = 0.7
SCOUT_ETA = 0.55
NEIGHBOUR_ETA = 0.2


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# ----------------------------------------------------------------------------- graph helpers

class ZoneGraph:
    def __init__(self, workspace: Path, state: Dict[str, Any]):
        g = _load(workspace / "data" / "zone_maps" / "world_zone_graph.v1.json")
        self.map_of: Dict[str, str] = {}
        self.label: Dict[str, str] = {}
        self.adj: Dict[str, List[str]] = {}
        for n in g.get("nodes") or []:
            zid = str(n.get("zoneId"))
            self.map_of[zid] = str(n.get("mapId"))
            self.label[zid] = str(n.get("label") or zid)
            self.adj.setdefault(zid, [])
        for e in g.get("edges") or []:
            a, b = str(e.get("from")), str(e.get("to"))
            self.adj.setdefault(a, []).append(b)
            self.adj.setdefault(b, []).append(a)
        # zones only in the save
        for map_id, zones in (state.get("zoneMemory") or {}).items():
            for zid, z in (zones or {}).items():
                self.map_of.setdefault(zid, str(map_id))
                self.label.setdefault(zid, str((z or {}).get("label") or zid))
                self.adj.setdefault(zid, [])

    def hops(self, a: str, b: str, cap: int = 12) -> Optional[int]:
        if a == b:
            return 0
        seen = {a}
        frontier = [a]
        for d in range(1, cap + 1):
            nxt = []
            for x in frontier:
                for y in self.adj.get(x, []):
                    if y == b:
                        return d
                    if y not in seen:
                        seen.add(y)
                        nxt.append(y)
            frontier = nxt
            if not frontier:
                break
        return None

    def travel_minutes(self, from_zone: Optional[str], to_zone: Optional[str], *, home_map: Optional[str] = None) -> float:
        """Hops on the same map, a fixed crossing between maps. A missing end (the camp
        has no zone of its own yet) counts as that map's edge: 90 min on the home map."""
        if not to_zone or not from_zone:
            known = to_zone or from_zone
            if known and home_map and self.map_of.get(known) == home_map:
                return 90.0
            return TRAVEL_MINUTES_CROSS_MAP
        if self.map_of.get(from_zone) != self.map_of.get(to_zone):
            return TRAVEL_MINUTES_CROSS_MAP
        h = self.hops(from_zone, to_zone)
        return TRAVEL_MINUTES_PER_HOP * (h if h is not None else 6)


# ----------------------------------------------------------------------------- camp state

def camp_state(state: Dict[str, Any]) -> Dict[str, Any]:
    camp = state.setdefault("camp", {})
    camp.setdefault("schemaVersion", "verdance-camp/0.1")
    camp.setdefault("restMinutes", 720.0)
    camp.setdefault("people", {})          # heroId -> {where, zoneId, eta, since}
    camp.setdefault("pauses", [])          # minor beads
    camp.setdefault("clockMinutes", float(state.get("campaignClockMinutes") or 0.0))
    camp.setdefault("homeZoneId", (state.get("homeCamp") or {}).get("zoneId"))
    camp.setdefault("homeMapId", (state.get("homeCamp") or {}).get("mapId") or state.get("sessionHomeMap"))
    return camp


def where(state: Dict[str, Any], hero_id: str) -> Dict[str, Any]:
    camp = camp_state(state)
    rec = camp["people"].get(hero_id)
    if rec:
        return rec
    ch = (state.get("characters") or {}).get(hero_id) or {}
    if ch.get("status") == "dead":
        return {"where": "field", "zoneId": ch.get("fellAt"), "note": "frame on the field"}
    return {"where": "camp"}


def roster_locations(state: Dict[str, Any], graph: ZoneGraph) -> List[Dict[str, Any]]:
    rows = []
    for hid, ch in sorted((state.get("characters") or {}).items()):
        if not isinstance(ch, dict):
            continue
        w = where(state, hid)
        rows.append({"heroId": hid, "name": ch.get("name") or hid, "status": ch.get("status"), "wounds": int(ch.get("wounds") or 0),
                     "where": w.get("where"), "zoneId": w.get("zoneId"), "label": graph.label.get(str(w.get("zoneId")), None) if w.get("zoneId") else None,
                     "eta": w.get("eta"), "inCompany": bool(ch.get("player"))})
    return rows


# ----------------------------------------------------------------------------- the clock

class Clock:
    def __init__(self, state: Dict[str, Any], workspace: Path):
        self.state = state
        self.ws = Path(workspace)
        self.graph = ZoneGraph(self.ws, state)
        self.camp = camp_state(state)
        self.world = None
        self.pauses: List[Dict[str, Any]] = []
        self._open_world()
        try:
            import verdance_story_engine_v1 as engine  # noqa
            self.engine = engine
        except Exception:
            self.engine = None
        try:
            import offscreen_clash_v1 as clashes  # noqa
            self.clashes = clashes
        except Exception:
            self.clashes = None

    def _open_world(self) -> None:
        try:
            import belief_homecoming_v1 as B
            self.world, _fresh = B._open_world(self.state, self.ws)
            self._B = B
        except Exception as exc:
            self.world = None
            self._B = None
            self.world_error = repr(exc)

    @property
    def minute(self) -> float:
        return float(self.state.get("campaignClockMinutes") or 0.0)

    def _truth(self, zid: str) -> Optional[Dict[str, Any]]:
        for map_id, zones in (self.state.get("zoneMemory") or {}).items():
            if zid in (zones or {}):
                return dict(zones[zid], mapId=map_id)
        return None

    def _questions(self) -> Dict[str, Tuple[str, Optional[str]]]:
        if not self.world:
            return {}
        return {q["id"]: (q["status"], q["lean"]) for q in self.world.frame()["questions"]}

    # -- one hour of the world
    def _step(self, dt: float, active_map: Optional[str]) -> List[Dict[str, Any]]:
        st = self.state
        before_fronts = len(st.get("frontEvents") or [])
        st["campaignClockMinutes"] = round(self.minute + dt, 3)
        # truth evolves through the engine's own functions
        if self.engine is not None:
            try:
                self.engine.tick_offscreen_zones(st, active_map or st.get("sessionHomeMap") or "", [], dt, self.ws)
            except Exception:
                pass
        if self.clashes is not None:
            try:
                self.clashes.run_offscreen_clashes(st, self.ws, active_map_id=active_map, dt_minutes=dt,
                                                   seed_key=f"camp|{st['campaignClockMinutes']}|{st.get('missionNumber')}")
            except Exception:
                pass
        new_fronts = [f for f in (st.get("frontEvents") or [])[before_fronts:] if isinstance(f, dict)]
        # belief: the fog grows, posted people keep looking, rumours arrive
        found = []
        if self.world is not None:
            self.world.advance(dt, step_minutes=dt)
            self.world.begin_batch()
            held_maps = {z["mapId"] for z in (self._all_zones()) if z.get("controllingFaction") == "ashwalkers"}
            intel = st.setdefault("intel", [])
            for f in new_fronts:
                on_held = f.get("mapId") in held_maps
                if f.get("type") == "offscreen_clash":
                    eta = 0.25 if on_held else 0.1
                    for zid in (f.get("zoneA"), f.get("zoneB")):
                        if zid and zid in self.world.host.engine.field.clusters:
                            self.world.observe_zone(str(zid), source="rumour:clash", eta=eta, minute=self.minute, threat=0.8)
                    if on_held:
                        row = {"kind": "rumour", "about": "shelling", "mapId": f.get("mapId"), "zones": [f.get("zoneA"), f.get("zoneB")], "eta": eta, "source": "scouts heard guns", "minute": round(self.minute, 1)}
                        intel.append(row)
                        found.append({"pause": "rumour", "witness": f"guns heard near {self.graph.label.get(str(f.get('zoneA')), f.get('zoneA'))} on {f.get('mapId')}", "row": row})
                elif f.get("type") == "offscreen_zone_flip":
                    zid = f.get("zoneId")
                    eta = 0.35 if on_held else 0.15
                    if zid and zid in self.world.host.engine.field.clusters:
                        self.world.observe_zone(str(zid), source="rumour:flip", eta=eta, minute=self.minute, held=1.0,
                                                ours=1.0 if f.get("toFaction") == "ashwalkers" else 0.0, threat=0.6)
                    if on_held:
                        row = {"kind": "rumour", "about": "flip", "mapId": f.get("mapId"), "zoneId": zid, "label": f.get("label"), "toFaction": f.get("toFaction"), "eta": eta, "source": "word from the road", "minute": round(self.minute, 1)}
                        intel.append(row)
                        found.append({"pause": "rumour", "witness": f"{f.get('label') or zid} is said to be {f.get('toFaction')}'s now", "row": row})
            # posted people: looking is keeping
            for hid, rec in list(self.camp["people"].items()):
                if rec.get("where") == "posted" and rec.get("zoneId"):
                    zid = str(rec["zoneId"])
                    truth = self._truth(zid)
                    if truth and zid in self.world.host.engine.field.clusters:
                        obs = self._B._drop_obs(truth)
                        self.world.observe_zone(zid, source=f"posted:{hid}", eta=POST_ETA, minute=self.minute, **obs)
                        ctrl = str(truth.get("controllingFaction") or "neutral")
                        if ctrl not in ("ashwalkers", "neutral") and not rec.get("contactFlagged"):
                            rec["contactFlagged"] = True
                            found.append({"pause": "contact", "heroId": hid, "zoneId": zid,
                                          "witness": f"{(self.state.get('characters') or {}).get(hid, {}).get('name', hid)} reports {self.graph.label.get(zid, zid)} is {ctrl}'s now"})
                        elif ctrl in ("ashwalkers", "neutral"):
                            rec.pop("contactFlagged", None)
                elif rec.get("where") == "transit" and float(rec.get("eta") or 0) <= self.minute:
                    rec["where"] = "posted" if rec.get("then") == "post" else "camp"
                    rec.pop("eta", None)
                    if rec["where"] == "camp":
                        rec.pop("zoneId", None)
                    found.append({"pause": "arrival", "heroId": hid, "zoneId": rec.get("zoneId"),
                                  "witness": f"{(self.state.get('characters') or {}).get(hid, {}).get('name', hid)} {'is on' if rec['where'] == 'posted' else 'is back from'} {self.graph.label.get(str(rec.get('zoneId') or rec.get('fromZoneId')), rec.get('zoneId') or 'the road')}"})
            self.world.flush()
        return found

    def _all_zones(self) -> List[Dict[str, Any]]:
        out = []
        for map_id, zones in (self.state.get("zoneMemory") or {}).items():
            for zid, z in (zones or {}).items():
                if isinstance(z, dict):
                    out.append(dict(z, zoneId=zid, mapId=map_id))
        return out

    def run(self, minutes: float, *, active_map: Optional[str] = None, until_pause: bool = True, reason: str = "wait") -> Dict[str, Any]:
        q_before = self._questions()
        elapsed = 0.0
        pauses: List[Dict[str, Any]] = []
        while elapsed < minutes - 1e-9:
            dt = min(STEP_MINUTES, minutes - elapsed)
            found = self._step(dt, active_map)
            elapsed += dt
            q_after = self._questions()
            for qid, (status, lean) in q_after.items():
                b = q_before.get(qid)
                if b and (b[0] != status or b[1] != lean):
                    found.append({"pause": "question", "question": qid, "from": list(b), "to": [status, lean],
                                  "witness": f"the question {qid.replace('_', ' ')} moved: {b[0]}/{b[1]} -> {status}/{lean}"})
            q_before = q_after
            if found:
                for f in found:
                    f["minute"] = round(self.minute, 1)
                    f["during"] = reason
                pauses.extend(found)
                if until_pause:
                    break
        self.camp["clockMinutes"] = self.minute
        for p in pauses:
            self.camp["pauses"].append(p)
        if len(self.camp["pauses"]) > 200:
            del self.camp["pauses"][:len(self.camp["pauses"]) - 200]
        return {"elapsedMinutes": round(elapsed, 1), "requestedMinutes": minutes, "paused": bool(pauses) and until_pause, "pauses": pauses}

    # -- actions
    def rest(self, hours: float) -> Dict[str, Any]:
        out = self.run(hours * 60.0, reason="rest")
        if out["elapsedMinutes"] >= HEAL_AFTER_REST_MINUTES:
            healed = []
            for hid, ch in (self.state.get("characters") or {}).items():
                if isinstance(ch, dict) and ch.get("status") == "wounded":
                    ch["status"] = "active"
                    healed.append(hid)
                    if self.world and f"hero:{hid}" in self.world.host.engine.field.clusters:
                        self.world.observe({f"obs_hero_{hid}_fit": 0.8}, 0.8, source="rest", minute=self.minute)
            out["healed"] = healed
        return out

    def wait(self, hours: float) -> Dict[str, Any]:
        return self.run(hours * 60.0, reason="wait")

    def scout(self, zone_id: str) -> Dict[str, Any]:
        truth = self._truth(zone_id)
        if truth is None:
            return {"ok": False, "error": f"unknown zone {zone_id}"}
        travel = self.graph.travel_minutes(self.camp.get("homeZoneId"), zone_id, home_map=self.camp.get("homeMapId"))
        out = self.run(travel + SCOUT_MINUTES, active_map=self.graph.map_of.get(zone_id), until_pause=False, reason=f"scout:{zone_id}")
        if self.world is not None and zone_id in self.world.host.engine.field.clusters:
            before = self.world.zone_summary(zone_id)
            obs = self._B._drop_obs(truth)
            self.world.begin_batch()
            self.world.observe_zone(zone_id, source="scout", eta=SCOUT_ETA, minute=self.minute, **obs)
            for nz in self.graph.adj.get(zone_id, []):
                nt = self._truth(nz)
                if nt and nz in self.world.host.engine.field.clusters:
                    nobs = self._B._drop_obs(nt)
                    self.world.observe_zone(nz, source="scout:adjacent", eta=NEIGHBOUR_ETA, minute=self.minute, held=nobs["held"], threat=nobs["threat"])
            self.world.flush()
            after = self.world.zone_summary(zone_id)
            # surprisal: how wrong we were, weighted by how sure we were
            s = before["ours"]["conf"] * abs(obs["ours"] - before["ours"]["value"]) + before["held"]["conf"] * abs(obs["held"] - before["held"]["value"])
            out["scouted"] = {"zoneId": zone_id, "label": self.graph.label.get(zone_id, zone_id), "found": str(truth.get("controllingFaction") or "neutral"),
                              "believed": ("ours" if before["ours"]["value"] > 0.5 else ("held" if before["held"]["value"] > 0.5 else "empty")) if max(before["ours"]["conf"], before["held"]["conf"]) >= 0.15 else "nobody had looked",
                              "surprise": round(s, 3), "before": before, "after": after}
            self.state.setdefault("intel", []).append({"kind": "scout", "zoneId": zone_id, "label": self.graph.label.get(zone_id, zone_id), "found": out["scouted"]["found"], "eta": SCOUT_ETA, "source": "patrol", "minute": round(self.minute, 1)})
            out["pauses"].append({"pause": "arrival", "minute": round(self.minute, 1), "during": f"scout:{zone_id}", "zoneId": zone_id,
                                  "witness": f"patrol back from {self.graph.label.get(zone_id, zone_id)}: {out['scouted']['found']}" + (f" (we believed {out['scouted']['believed']})" if s > 0.3 else "")})
            self.camp["pauses"].append(out["pauses"][-1])
        out["ok"] = True
        return out

    def post(self, hero_id: str, zone_id: str) -> Dict[str, Any]:
        ch = (self.state.get("characters") or {}).get(hero_id)
        if not isinstance(ch, dict) or ch.get("status") in ("dead", "locked"):
            return {"ok": False, "error": f"{hero_id} cannot be posted"}
        if self._truth(zone_id) is None:
            return {"ok": False, "error": f"unknown zone {zone_id}"}
        rec = self.camp["people"].get(hero_id) or {"where": "camp"}
        travel = self.graph.travel_minutes(rec.get("zoneId") or self.camp.get("homeZoneId"), zone_id, home_map=self.camp.get("homeMapId"))
        self.camp["people"][hero_id] = {"where": "transit", "zoneId": zone_id, "fromZoneId": rec.get("zoneId"), "eta": round(self.minute + travel, 1), "then": "post", "since": round(self.minute, 1)}
        out = self.run(travel, reason=f"post:{hero_id}:{zone_id}")
        out["ok"] = True
        out["person"] = self.camp["people"][hero_id]
        return out

    def recall(self, hero_id: str) -> Dict[str, Any]:
        rec = self.camp["people"].get(hero_id)
        if not rec or rec.get("where") == "camp":
            return {"ok": False, "error": f"{hero_id} is already in camp"}
        travel = self.graph.travel_minutes(rec.get("zoneId"), self.camp.get("homeZoneId"), home_map=self.camp.get("homeMapId"))
        self.camp["people"][hero_id] = {"where": "transit", "fromZoneId": rec.get("zoneId"), "eta": round(self.minute + travel, 1), "then": "camp", "since": round(self.minute, 1)}
        out = self.run(travel, reason=f"recall:{hero_id}")
        out["ok"] = True
        out["person"] = self.camp["people"][hero_id]
        return out

    # -- persistence + face
    def close(self) -> Dict[str, Any]:
        face: Dict[str, Any] = {"schemaVersion": "verdance-camp-face/0.1", "clockMinutes": self.minute,
                                "day": int(self.minute // 1440), "hourOfDay": round((self.minute % 1440) / 60.0, 1),
                                "people": roster_locations(self.state, self.graph), "pauses": self.camp["pauses"][-20:]}
        if self.world is not None:
            pkl, _ = self._B._world_paths(self.ws)
            self.world.save(pkl)
            frame = self.world.frame()
            frame["intel"] = (self.state.get("intel") or [])[-40:]
            (self.ws / "outbox").mkdir(parents=True, exist_ok=True)
            (self.ws / "outbox" / "intel.latest.json").write_text(json.dumps(frame, indent=2, ensure_ascii=False), encoding="utf-8")
            face["questions"] = frame["questions"]
            face["known"] = sum(1 for r in frame["nodes"] if r["role"] == "ours" and r["state"] == "current")
            face["stale"] = sum(1 for r in frame["nodes"] if r["role"] == "ours" and r["state"] == "stale")
            face["dark"] = sum(1 for r in frame["nodes"] if r["role"] == "ours" and r["state"] == "dark")
        else:
            face["belief"] = "unavailable: " + getattr(self, "world_error", "Umwelt not importable")
        (self.ws / "outbox" / "camp.latest.json").write_text(json.dumps(face, indent=2, ensure_ascii=False), encoding="utf-8")
        return face


def act(state: Dict[str, Any], workspace: Path, action: str, **params) -> Dict[str, Any]:
    clock = Clock(state, workspace)
    if action == "rest":
        out = clock.rest(float(params.get("hours", 8)))
    elif action == "wait":
        out = clock.wait(float(params.get("hours", 1)))
    elif action == "scout":
        out = clock.scout(str(params.get("zoneId")))
    elif action == "post":
        out = clock.post(str(params.get("heroId")), str(params.get("zoneId")))
    elif action == "recall":
        out = clock.recall(str(params.get("heroId")))
    else:
        return {"ok": False, "error": f"unknown camp action {action!r}"}
    out.setdefault("ok", True)
    out["camp"] = clock.close()
    return out


def surface(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    clock = Clock(state, workspace)
    return clock.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["surface", "rest", "wait", "scout", "post", "recall"])
    ap.add_argument("--workspace", default=str(ROOT))
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--zone")
    ap.add_argument("--hero")
    ap.add_argument("--write", action="store_true", help="write the mutated campaign state back (default: dry run)")
    a = ap.parse_args()
    ws = Path(a.workspace)
    sp = ws / "state" / "campaign_state.json"
    st = _load(sp)
    if a.action == "surface":
        out = surface(st, ws)
    else:
        out = act(st, ws, a.action, hours=a.hours, zoneId=a.zone, heroId=a.hero)
    if a.write and a.action != "surface":
        sp.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "camp"}, indent=1, ensure_ascii=False)[:4000])
    camp = out.get("camp") or out
    print("clock day", camp.get("day"), "hour", camp.get("hourOfDay"), "| known/stale/dark", camp.get("known"), camp.get("stale"), camp.get("dark"))
