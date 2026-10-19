#!/usr/bin/env python3
"""Replay a campaign save through the Verdance Umwelt world and check it comprehends.

This is the blank-slate gate for Verdance: boot blank, prime dark, feed the save's
history as observations with honest eta, and verify that

  1. measured zones track truth (ours / held agree with controllingFaction),
  2. zones nobody measured stay dark,
  3. silence makes a rumoured threat fade (dissipative ease),
  4. the company's six questions land where the readings face put them,
  5. save/load keeps comprehension (field hash equal).

Writes outbox/intel.latest.json (intel/1: dark / stale / current). Never writes state.

    python tools/umwelt_replay_v1.py [--state PATH] [--rest-minutes 720] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import umwelt_world_v1 as W  # noqa: E402
import readings_v1  # noqa: E402

PAIR_TO_QUESTION = {tuple(sorted(spec["pair"])): q for q, spec in W.QUESTIONS.items()}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def zone_truth(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for map_id, zones in (state.get("zoneMemory") or {}).items():
        for zid, z in (zones or {}).items():
            if isinstance(z, dict):
                out[zid] = dict(z, mapId=map_id)
    return out


def drop_observation(z: Dict[str, Any]) -> Dict[str, float]:
    ab = z.get("abstract") or {}
    ctrl = str(z.get("controllingFaction") or ab.get("control") or "neutral")
    strength = max(float(ab.get("baseStrength") or 0), float(ab.get("militaryPressure") or 0), float(ab.get("fortification") or 0))
    return {"ours": 1.0 if ctrl == W.OUR_FACTION else 0.0,
            "held": 0.0 if ctrl == "neutral" else 1.0,
            "strength": _clamp(strength / 0.25),
            "threat": _clamp(float(ab.get("instability") or 0.0))}


def replay(state: Dict[str, Any], workspace: Path, *, rest_minutes: float = 720.0, verbose: bool = True) -> Dict[str, Any]:
    truth0 = zone_truth(state)
    extra = [{"zoneId": zid, "mapId": z.get("mapId"), "label": z.get("label")} for zid, z in truth0.items()]
    world = W.VerdanceWorld(workspace, start_minute=0.0, extra_zones=extra)
    world.prime_dark()
    log: List[str] = []
    say = (lambda s: (log.append(s), print(s) if verbose else None))

    truth = zone_truth(state)
    held_maps = {z["mapId"] for z in truth.values() if z.get("controllingFaction") == W.OUR_FACTION}
    beads = [b for b in (state.get("history") or []) if isinstance(b, dict)]
    fronts = [f for f in (state.get("frontEvents") or []) if isinstance(f, dict)]
    face = readings_v1.project(json.loads(json.dumps(state)), workspace)
    coh_hist: Dict[Any, List[Dict[str, Any]]] = {}
    for c in face.get("coherence") or []:
        for h in c.get("history") or []:
            coh_hist.setdefault(h.get("missionNumber"), []).append(dict(h, pair=c["pair"]))

    last_bead_on_map: Dict[str, int] = {}
    for i, b in enumerate(beads):
        last_bead_on_map[str(b.get("mapId"))] = i

    minute = 0.0
    measured_total = 0
    for i, b in enumerate(beads):
        mission = b.get("missionNumber")
        map_id = str(b.get("mapId"))
        elapsed = float(b.get("elapsedMinutes") or 10.0)
        minute += elapsed
        n_meas = 0
        # 1. Drop telemetry: eta ~1 on zones measured on this map (final memory attributed to the last Drop there).
        if last_bead_on_map.get(map_id) == i:
            for zid, z in truth.items():
                if z.get("mapId") == map_id and z.get("confidence") == "measured":
                    obs = drop_observation(z)
                    world.observe_zone(zid, source=f"drop:m{mission}", eta=1.0, minute=minute, **obs)
                    n_meas += 1
        else:
            dz = b.get("deploymentZoneId")
            if dz in truth:
                world.observe_zone(dz, source=f"drop:m{mission}", eta=0.6, minute=minute, held=1.0, ours=1.0 if truth[dz].get("controllingFaction") == W.OUR_FACTION else 0.0)
                n_meas += 1
        measured_total += n_meas
        # 2. What reached camp from elsewhere: rumours with low eta.
        n_rum = 0
        for f in fronts:
            if f.get("missionNumber") != mission:
                continue
            on_held_map = f.get("mapId") in held_maps
            if f.get("type") == "offscreen_clash":
                eta = 0.25 if on_held_map else 0.1
                for zid in (f.get("zoneA"), f.get("zoneB")):
                    if zid in truth:
                        world.observe_zone(str(zid), source="rumour:clash", eta=eta, minute=minute, threat=0.8)
                        n_rum += 1
            elif f.get("type") == "offscreen_zone_flip":
                zid = f.get("zoneId")
                if zid in truth:
                    world.observe_zone(str(zid), source="rumour:flip", eta=0.35 if on_held_map else 0.15, minute=minute,
                                       held=1.0, ours=1.0 if f.get("toFaction") == W.OUR_FACTION else 0.0, threat=0.6)
                    n_rum += 1
        # 3. The questions: event classes that fired on this bead.
        n_q = 0
        for h in coh_hist.get(mission, []):
            q = PAIR_TO_QUESTION.get(tuple(sorted(h["pair"])))
            if not q:
                continue
            world.observe_question(q, toward=h.get("toward") if h.get("effect") == "distinguish" else None,
                                   strength=float(h.get("strength") or 0.0), source=f"event:{h.get('class')}", minute=minute)
            n_q += 1
        # 4. Named outcomes stamped on the bead (newer saves); legacy saves fall to the snapshot below.
        for o in b.get("namedOutcomes") or []:
            hid = str(o.get("charId"))
            if o.get("outcome") == "dead":
                world.observe({f"obs_hero_{hid}_fit": 0.0, f"obs_hero_{hid}_frame_intact": 0.5}, {f"obs_hero_{hid}_fit": 1.0, f"obs_hero_{hid}_frame_intact": 0.5}, source=f"drop:m{mission}", minute=minute)
            elif o.get("outcome") in ("recovered", "wounded"):
                world.observe({f"obs_hero_{hid}_fit": 0.3}, 1.0, source=f"drop:m{mission}", minute=minute)
        say(f"m{mission} {map_id} {b.get('verdict')}: measured {n_meas} zones, {n_rum} rumours, {n_q} question nudges; clock {minute:.0f} min")
        # rest between Drops: the fog grows
        world.advance(rest_minutes)
        minute += rest_minutes

    # Snapshot-only facts (legacy saves): the roll and the bench.
    chars = {k: v for k, v in (state.get("characters") or {}).items() if isinstance(v, dict)}
    for hid, ch in chars.items():
        if f"hero:{hid}" not in world.host.engine.field.clusters:
            continue
        if ch.get("status") == "dead":
            world.observe({f"obs_hero_{hid}_fit": 0.0, f"obs_hero_{hid}_frame_intact": 0.5}, {f"obs_hero_{hid}_fit": 1.0, f"obs_hero_{hid}_frame_intact": 0.5}, source="roll", minute=minute)
        elif int(ch.get("wounds") or 0) > 0:
            world.observe({f"obs_hero_{hid}_fit": 0.3}, 1.0, source="bench", minute=minute)
    for h in coh_hist.get(None, []):
        q = PAIR_TO_QUESTION.get(tuple(sorted(h["pair"])))
        if q:
            world.observe_question(q, toward=h.get("toward") if h.get("effect") == "distinguish" else None,
                                   strength=float(h.get("strength") or 0.0), source=f"event:{h.get('class')}", minute=minute)

    # ----------------------------------------------------------------- checks
    checks: Dict[str, Any] = {}
    # 1. measured zones track truth
    agree = total = 0
    misses = []
    for zid, z in truth.items():
        if z.get("confidence") != "measured":
            continue
        s = world.zone_summary(zid)
        want_ours = z.get("controllingFaction") == W.OUR_FACTION
        want_held = z.get("controllingFaction") not in (None, "neutral")
        ok_ours = (s["ours"]["value"] > 0.5) == want_ours
        ok_held = (s["held"]["value"] > 0.5) == want_held
        total += 2
        agree += int(ok_ours) + int(ok_held)
        if not (ok_ours and ok_held):
            misses.append({"zone": zid, "truth": z.get("controllingFaction"), "belief": s})
    checks["measured_track_truth"] = {"agree": agree, "of": total, "ok": total > 0 and agree == total, "misses": misses[:5]}
    # 2. unmeasured zones stay dark
    frame = world.frame()
    rows = {r["id"]: r for r in frame["nodes"]}
    unmeasured = [zid for zid, z in truth.items() if z.get("confidence") != "measured"]
    dark = sum(1 for zid in unmeasured if rows.get(f"{zid}.ours", {}).get("state") == "dark")
    checks["unmeasured_dark"] = {"dark": dark, "of": len(unmeasured), "ok": dark >= 0.9 * len(unmeasured)}
    # 3. silence fades a rumour: on a saved copy, advance 3 days without looking and compare
    rumoured = [(r["confidence"], r["id"]) for r in frame["nodes"] if r["role"] == "threat" and (r.get("source") or "").startswith("rumour")]
    fade = None
    if rumoured:
        _, key = max(rumoured)
        zid = key.split(".")[0]
        tmp_fade = workspace / "outbox" / "intel.fade.pkl"
        world.save(tmp_fade)
        copy = W.VerdanceWorld(workspace, extra_zones=extra)
        copy.load(tmp_fade)
        before = copy.zone_summary(zid)["threat"]
        copy.advance(3 * 1440.0, step_minutes=120.0)
        after = copy.zone_summary(zid)["threat"]
        fade = {"zone": zid, "before": before, "after": after, "ok": after["conf"] < before["conf"] or abs(after["value"] - 0.5) < abs(before["value"] - 0.5)}
    checks["silence_fades_rumour"] = fade or {"ok": None, "note": "no rumours in this save"}
    # 4. questions vs readings face
    face_status = {tuple(sorted(c["pair"])): c for c in face.get("coherence") or []}
    qrows = []
    agree_q = 0
    for qr in frame["questions"]:
        fc = face_status.get(tuple(sorted(qr["pair"])), {})
        # No contradiction: the two estimators may differ on open-vs-leaning at the margin,
        # but they must never lean opposite ways on the same evidence.
        same_lean = not (qr["lean"] and fc.get("leaning") and qr["lean"] != fc.get("leaning"))
        agree_q += int(same_lean)
        qrows.append({"question": qr["question"], "icon": qr["icon"], "umwelt": {"status": qr["status"], "lean": qr["lean"], "z": qr["bloch"][2], "r": qr["radius"]},
                      "readings_face": {"status": fc.get("status"), "lean": fc.get("leaning"), "c": fc.get("c")}, "same_lean": same_lean})
    checks["questions_agree_with_face"] = {"agree": agree_q, "of": len(qrows), "rows": qrows, "ok": agree_q == len(qrows)}
    # 5. save/load
    tmp = workspace / "outbox" / "intel.engine.pkl"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    h1 = world.host.field_canon_hash()
    world.save(tmp)
    world2 = W.VerdanceWorld(workspace, extra_zones=extra)
    world2.load(tmp)
    h2 = world2.host.field_canon_hash()
    checks["save_load_roundtrip"] = {"hash_before": h1, "hash_after": h2, "ok": h1 == h2}

    frame["replay"] = {"beads": len(beads), "measuredObservations": measured_total, "restMinutes": rest_minutes, "log": log}
    frame["checks"] = checks
    frame["ok"] = all(v.get("ok") for v in checks.values() if isinstance(v, dict) and v.get("ok") is not None)
    return frame


def readout(frame: Dict[str, Any]) -> str:
    L = [f"VERDANCE UMWELT REPLAY  beads={frame['replay']['beads']}  field={frame['producer']['field_hash'][:12]}  ok={frame['ok']}", ""]
    L.append("The six questions (Bloch):")
    for q in frame["questions"]:
        L.append(f"  {q['icon']} {q['question']:<40} z={q['bloch'][2]:+.2f} r={q['radius']:.2f}  {q['status']:<8} lean={q['lean']}")
    L.append("")
    counts: Dict[str, int] = {}
    for r in frame["nodes"]:
        if r["role"] in ("ours", "held", "strength", "threat"):
            counts[r["state"]] = counts.get(r["state"], 0) + 1
    L.append(f"Zone axes by state: {counts}")
    current = [r for r in frame["nodes"] if r["role"] == "ours" and r["state"] == "current"]
    L.append(f"Zones currently known ({len(current)}):")
    for r in sorted(current, key=lambda r: -r["confidence"])[:12]:
        L.append(f"  {r.get('label') or r['node']:<26} ours={r['value']:.2f} conf={r['confidence']:.2f} age={r['age_min']}min via {r['source']}")
    L.append("")
    L.append("Checks:")
    for k, v in frame["checks"].items():
        L.append(f"  [{'ok' if v.get('ok') else ('--' if v.get('ok') is None else 'FAIL')}] {k}: " + json.dumps({kk: vv for kk, vv in v.items() if kk not in ('rows', 'misses')}, default=str)[:160])
    if frame["checks"].get("questions_agree_with_face", {}).get("rows"):
        L.append("  question agreement:")
        for row in frame["checks"]["questions_agree_with_face"]["rows"]:
            L.append(f"    {row['icon']} {row['question']:<38} umwelt {row['umwelt']['status']}/{row['umwelt']['lean']}  face {row['readings_face']['status']}/{row['readings_face']['lean']}  {'=' if row['same_lean'] else '≠'}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=str(ROOT))
    ap.add_argument("--state", default=None)
    ap.add_argument("--rest-minutes", type=float, default=720.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    ws = Path(args.workspace)
    state = _load(Path(args.state) if args.state else ws / "state" / "campaign_state.json")
    frame = replay(state, ws, rest_minutes=args.rest_minutes, verbose=not args.json)
    out = ws / "outbox" / "intel.latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(frame, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(frame, indent=2, ensure_ascii=False) if args.json else "\n" + readout(frame))
    return 0 if frame["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
