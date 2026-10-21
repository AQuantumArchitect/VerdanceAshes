#!/usr/bin/env python3
"""Perspectives: the same world, seen from several minds, and the truth in the same shape.

  truth        state/zoneMemory projected into the intel/1 node shape, confidence 1, hidden from the player
  company      the player's mind (state/belief/verdance.engine.pkl; fed by belief_homecoming_v1 / camp_clock_v1)
  armada, nullmercs, cortex
               one Umwelt world each (state/belief/<faction>.engine.pkl), fed by an observation POLICY:
                 - zones they control: eta 0.9 (they are standing on them)
                 - zones adjacent to theirs: held/threat at eta 0.4
                 - clashes that touched their zones: threat at eta 0.8
                 - flips from/to them: eta 1.0
                 - a Drop fought on their ground: the irregulars' presence at eta 0.8 (they learn we were there)
  divergence   belief vs truth per perspective (ghost holdings, unknown holdings, dark), and belief vs belief
               (what Armada knows about the company's ground). This is the surprise map, and it is also the
               patrons' honest source: a dispatch is written from what its author believes.

Every perspective is DERIVE over the same truth; none writes world state. The roles are per-mind: a faction
world's `ours` means that faction's. Compare perspectives through truth, never by role name alone.

    python -m verdance.belief.perspectives [workspace]      # fold all faction minds once, print divergence
    python -m verdance.belief.perspectives --worker <ws>    # drain the job queue (what enqueue() spawns)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, clamp, load_json, tools_env
from verdance.belief import world as W

ROOT = WORKSPACE_ROOT

FACTIONS = ("armada", "nullmercs", "cortex")
POLICY = {"own": 0.9, "adjacent": 0.4, "clash": 0.8, "flip": 1.0, "fought_on": 0.8}


def zone_rows(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for map_id, zones in (state.get("zoneMemory") or {}).items():
        for zid, z in (zones or {}).items():
            if isinstance(z, dict):
                out[zid] = dict(z, mapId=map_id)
    return out


def adjacency(workspace: Path) -> Dict[str, List[str]]:
    adj: Dict[str, List[str]] = {}
    try:
        g = load_json(workspace / "data" / "zone_maps" / "world_zone_graph.v1.json")
        for e in g.get("edges") or []:
            a, b = str(e.get("from")), str(e.get("to"))
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
    except Exception:
        pass
    return adj


def obs_for(z: Dict[str, Any], faction: str) -> Dict[str, float]:
    ab = z.get("abstract") or {}
    ctrl = str(z.get("controllingFaction") or ab.get("control") or "neutral")
    strength = max(float(ab.get("baseStrength") or 0), float(ab.get("militaryPressure") or 0), float(ab.get("fortification") or 0))
    return {"ours": 1.0 if ctrl == faction else 0.0, "held": 0.0 if ctrl == "neutral" else 1.0,
            "strength": clamp(strength / 0.25), "threat": clamp(float(ab.get("instability") or 0.0))}


# ----------------------------------------------------------------------------- truth frame

def truth_frame(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    """Truth in the intel/1 node shape. Never shown to the player; the referee for every belief."""
    rows = []
    for zid, z in sorted(zone_rows(state).items()):
        o = obs_for(z, "ashwalkers")
        for role in ("ours", "held", "strength", "threat"):
            rows.append({"id": f"{zid}.{role}", "node": zid, "role": role, "value": round(o[role], 4), "confidence": 1.0,
                         "state": "current", "age_min": 0.0, "source": "truth", "eta": 1.0, "label": z.get("label"), "mapId": z.get("mapId"),
                         "controllingFaction": str(z.get("controllingFaction") or "neutral")})
    return {"schema": "verdance-intel/1", "perspective": "truth", "subject": "what is actually true on Verdance (hidden)",
            "as_of_minute": round(float(state.get("campaignClockMinutes") or 0.0), 2), "law": "truth is never shown; it is what every belief is measured against",
            "producer": {"name": "perspectives_v1", "kind": "log"}, "nodes": rows}


# ----------------------------------------------------------------------------- faction minds

def open_mind(state: Dict[str, Any], workspace: Path, faction: str):
    truth = zone_rows(state)
    extra = [{"zoneId": zid, "mapId": z.get("mapId"), "label": z.get("label")} for zid, z in truth.items()]
    world = W.VerdanceWorld(workspace, start_minute=0.0, extra_zones=extra)
    d = workspace / "state" / "belief"
    d.mkdir(parents=True, exist_ok=True)
    pkl = d / f"{faction}.engine.pkl"
    fresh = True
    if pkl.exists():
        try:
            world.load(pkl)
            fresh = False
        except Exception:
            world.prime_dark()
    else:
        world.prime_dark()
    return world, pkl, fresh


def fold_faction(state: Dict[str, Any], workspace: Path, faction: str, *, new_fronts: Optional[List[Dict[str, Any]]] = None,
                 fought: Optional[Dict[str, Any]] = None, minute: Optional[float] = None) -> Dict[str, Any]:
    """One observation batch for a faction's mind by its policy. `fought` = {mapId, zones: [...], against}
    when a Drop just happened. Advances that mind's clock to `minute` first (the fog grows for them too)."""
    world, pkl, fresh = open_mind(state, workspace, faction)
    truth = zone_rows(state)
    adj = adjacency(workspace)
    now = float(minute if minute is not None else (state.get("campaignClockMinutes") or 0.0))
    gap = max(0.0, min(7 * 1440.0, now - world.minute))
    if gap > 0:
        world.advance(gap, step_minutes=max(60.0, gap / 12.0))
    own = {zid for zid, z in truth.items() if str(z.get("controllingFaction") or "neutral") == faction}
    clusters = world.host.engine.field.clusters
    world.begin_batch()
    n = 0
    for zid in own:
        if zid in clusters:
            world.observe_zone(zid, source=f"{faction}:own", eta=POLICY["own"], minute=now, **obs_for(truth[zid], faction)); n += 1
    for zid in own:
        for nz in adj.get(zid, []):
            if nz in truth and nz not in own and nz in clusters:
                o = obs_for(truth[nz], faction)
                world.observe_zone(nz, source=f"{faction}:adjacent", eta=POLICY["adjacent"], minute=now, held=o["held"], threat=o["threat"], ours=0.0); n += 1
    for f in new_fronts or []:
        if f.get("type") == "offscreen_clash":
            zones = [z for z in (f.get("zoneA"), f.get("zoneB")) if z in truth]
            if any(z in own for z in zones) or faction in (f.get("winnerFaction"), f.get("loserFaction")):
                for z in zones:
                    if z in clusters:
                        world.observe_zone(z, source=f"{faction}:clash", eta=POLICY["clash"], minute=now, threat=0.9); n += 1
        elif f.get("type") == "offscreen_zone_flip":
            zid = f.get("zoneId")
            if zid in truth and zid in clusters and faction in (f.get("fromFaction"), f.get("toFaction")):
                world.observe_zone(zid, source=f"{faction}:flip", eta=POLICY["flip"], minute=now, **obs_for(truth[zid], faction)); n += 1
    if fought:
        against = str(fought.get("against") or "")
        for zid in fought.get("zones") or []:
            z = truth.get(zid)
            if not z or zid not in clusters:
                continue
            was_theirs = str(z.get("controllingFaction") or "") == faction or against == faction
            if was_theirs:
                # they learn the irregulars were there: held by someone not them, loud
                world.observe_zone(zid, source=f"{faction}:fought", eta=POLICY["fought_on"], minute=now,
                                   ours=1.0 if str(z.get("controllingFaction")) == faction else 0.0, held=1.0, threat=0.9); n += 1
    world.flush()
    world.save(pkl)
    frame = world.frame()
    frame["perspective"] = faction
    (workspace / "outbox").mkdir(parents=True, exist_ok=True)
    (workspace / "outbox" / f"intel.{faction}.latest.json").write_text(json.dumps(frame, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"faction": faction, "observations": n, "fresh": fresh, "fieldHash": frame["producer"]["field_hash"]}


def fold_all(state: Dict[str, Any], workspace: Path, **kw) -> List[Dict[str, Any]]:
    return [fold_faction(state, workspace, f, **kw) for f in FACTIONS]


# ----------------------------------------------------------------------------- background worker
#
# Each mind is a full Umwelt world; Umwelt's save/load walks the whole continuation surface, so three
# extra minds cost ~10x the company's own fold. They do not belong on the homecoming's critical path:
# the caller ENQUEUES a job (a truth snapshot + what happened) and a detached worker folds it, then
# rewrites divergence. The hub reads faces lazily, so a face that lands a minute late is still right.
# Set VA_PERSPECTIVES_SYNC=1 to fold inline (tests, replay gates).

def _jobs_dir(workspace: Path) -> Path:
    d = workspace / "state" / "belief" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _truth_slice(state: Dict[str, Any]) -> Dict[str, Any]:
    """The part of the save the minds read: zone truth + clock. Small, and frozen at enqueue time."""
    zm = {}
    for map_id, zones in (state.get("zoneMemory") or {}).items():
        zm[map_id] = {}
        for zid, z in (zones or {}).items():
            if isinstance(z, dict):
                ab = z.get("abstract") or {}
                zm[map_id][zid] = {"label": z.get("label"), "controllingFaction": z.get("controllingFaction"),
                                   "abstract": {k: ab.get(k) for k in ("control", "baseStrength", "militaryPressure", "fortification", "instability") if k in ab}}
    return {"zoneMemory": zm, "campaignClockMinutes": state.get("campaignClockMinutes") or 0.0, "missionNumber": state.get("missionNumber")}


def enqueue(state: Dict[str, Any], workspace: Path, *, new_fronts: Optional[List[Dict[str, Any]]] = None,
            fought: Optional[Dict[str, Any]] = None, minute: Optional[float] = None, spawn: bool = True) -> Dict[str, Any]:
    import os, time
    if os.environ.get("VA_PERSPECTIVES_SYNC") == "1":
        res = fold_all(state, workspace, new_fronts=new_fronts, fought=fought, minute=minute)
        divergence(state, workspace)
        return {"mode": "sync", "folded": res}
    job = {"schema": "verdance-perspectives-job/0.1", "queuedAt": time.time(), "minute": minute,
           "truth": _truth_slice(state), "newFronts": [f for f in (new_fronts or []) if isinstance(f, dict)], "fought": fought}
    d = _jobs_dir(workspace)
    path = d / f"{int(time.time() * 1000):013d}.job.json"
    path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    out = {"mode": "queued", "job": str(path)}
    if os.environ.get("VA_PERSPECTIVES_NOSPAWN") == "1":
        spawn = False  # tests / gates: leave the queue for an explicit `--worker` run
    if spawn:
        out["spawned"] = spawn_worker(workspace)
    return out


def _lock_path(workspace: Path) -> Path:
    return _jobs_dir(workspace) / "worker.lock"


def _lock_alive(lock: Path, stale_s: float = 900.0) -> bool:
    import os, time
    if not lock.exists():
        return False
    try:
        if time.time() - lock.stat().st_mtime > stale_s:
            return False
        pid = int(lock.read_text(encoding="utf-8").strip() or 0)
    except Exception:
        return False
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def spawn_worker(workspace: Path) -> bool:
    """Start a detached worker unless one is alive. Returns True when a new process was started."""
    import os, subprocess, sys as _sys
    if _lock_alive(_lock_path(workspace)):
        return False
    kw: Dict[str, Any] = {"cwd": str(workspace), "stdin": subprocess.DEVNULL,
                          "stdout": open(_jobs_dir(workspace) / "worker.log", "ab"), "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x00004000  # DETACHED | NEW_PROCESS_GROUP | BELOW_NORMAL_PRIORITY
    else:
        kw["start_new_session"] = True
        kw["preexec_fn"] = lambda: os.nice(10)
    # the worker is a background mind: one BLAS thread, low priority, never in the player's way
    env = tools_env(workspace)
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env.setdefault(k, "1")
    try:
        subprocess.Popen([_sys.executable, "-m", "verdance.belief.perspectives", "--worker", str(workspace)], env=env, **kw)
        return True
    except Exception:
        return False


def run_worker(workspace: Path, max_jobs: int = 50) -> int:
    """Drain the queue oldest-first; each job folds all faction minds, then divergence is rewritten once.
    Several jobs queued back to back are coalesced: fronts accumulate, the latest truth and minute win."""
    import os, time
    lock = _lock_path(workspace)
    if _lock_alive(lock):
        return 0
    lock.write_text(str(os.getpid()), encoding="utf-8")
    done = 0
    try:
        while done < max_jobs:
            jobs = sorted(_jobs_dir(workspace).glob("*.job.json"))
            if not jobs:
                break
            merged: Dict[str, Any] = {"truth": None, "newFronts": [], "fought": None, "minute": None}
            for jp in jobs:
                try:
                    j = load_json(jp)
                except Exception:
                    jp.unlink(missing_ok=True)
                    continue
                merged["truth"] = j.get("truth") or merged["truth"]
                merged["newFronts"].extend(j.get("newFronts") or [])
                merged["fought"] = j.get("fought") or merged["fought"]
                merged["minute"] = j.get("minute") if j.get("minute") is not None else merged["minute"]
            if not merged["truth"]:
                for jp in jobs:
                    jp.unlink(missing_ok=True)
                break
            t0 = time.time()
            state = merged["truth"]
            res = fold_all(state, workspace, new_fronts=merged["newFronts"], fought=merged["fought"], minute=merged["minute"])
            rep = divergence(state, workspace)
            print(f"[perspectives worker] {len(jobs)} job(s) folded in {time.time() - t0:.1f}s: " + ", ".join(f"{r['faction']}:{r['observations']}" for r in res), flush=True)
            print(summary(rep), flush=True)
            for jp in jobs:
                jp.unlink(missing_ok=True)
            lock.write_text(str(os.getpid()), encoding="utf-8")
            done += len(jobs)
    finally:
        lock.unlink(missing_ok=True)
    return done


def pending(workspace: Path) -> Dict[str, Any]:
    return {"queued": len(list(_jobs_dir(workspace).glob("*.job.json"))), "workerAlive": _lock_alive(_lock_path(workspace))}


# ----------------------------------------------------------------------------- divergence

def _frame_zones(frame: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in frame.get("nodes") or []:
        node, role = r.get("node"), r.get("role")
        if node and role and not str(node).startswith(("hero:", "map:", "company", "people", "verdance")):
            out.setdefault(str(node), {})[str(role)] = r
    return out


def divergence(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    """belief vs truth for every perspective on disk; belief vs belief for what each faction knows of the company."""
    out_dir = workspace / "outbox"
    truth = zone_rows(state)
    frames: Dict[str, Dict[str, Any]] = {}
    p = out_dir / "intel.latest.json"
    if p.exists():
        try:
            frames["company"] = load_json(p)
        except Exception:
            pass
    for f in FACTIONS:
        q = out_dir / f"intel.{f}.latest.json"
        if q.exists():
            try:
                frames[f] = load_json(q)
            except Exception:
                pass
    report: Dict[str, Any] = {"schema": "verdance-divergence/0.1", "as_of_minute": round(float(state.get("campaignClockMinutes") or 0.0), 2), "perspectives": {}, "crossed": {}}
    faction_of = {"company": "ashwalkers", "armada": "armada", "nullmercs": "nullmercs", "cortex": "cortex"}
    for name, frame in frames.items():
        mine = faction_of[name]
        z = _frame_zones(frame)
        ghost, unknown, dark, right, wrong_holder = [], [], [], 0, []
        total_gap = 0.0
        for zid, t in truth.items():
            ctrl = str(t.get("controllingFaction") or "neutral")
            b = z.get(zid) or {}
            o, h = b.get("ours") or {}, b.get("held") or {}
            if not o or o.get("state") == "dark":
                dark.append(zid)
                continue
            bel_ours = float(o.get("value") or 0) > 0.5
            bel_held = float(h.get("value") or 0) > 0.5
            tru_ours = ctrl == mine
            tru_held = ctrl != "neutral"
            total_gap += float(o.get("confidence") or 0) * abs((1.0 if tru_ours else 0.0) - float(o.get("value") or 0))
            if bel_ours and not tru_ours:
                ghost.append({"zoneId": zid, "label": t.get("label"), "actually": ctrl, "confidence": o.get("confidence")})
            elif tru_ours and not bel_ours:
                unknown.append({"zoneId": zid, "label": t.get("label")})
            elif bel_held != tru_held:
                wrong_holder.append({"zoneId": zid, "label": t.get("label"), "believedHeld": bel_held, "actually": ctrl})
            else:
                right += 1
        report["perspectives"][name] = {"faction": mine, "right": right, "ghostHoldings": ghost, "unknownHoldings": unknown,
                                        "wrongHeld": wrong_holder, "dark": len(dark), "zones": len(truth), "gap": round(total_gap, 3)}
    # what each faction knows about the company's ground (through truth)
    company_zones = {zid for zid, t in truth.items() if str(t.get("controllingFaction")) == "ashwalkers"}
    for name in FACTIONS:
        if name not in frames:
            continue
        z = _frame_zones(frames[name])
        known, suspected, blind = [], [], []
        for zid in sorted(company_zones):
            b = z.get(zid) or {}
            h, o = b.get("held") or {}, b.get("ours") or {}
            if not h or h.get("state") == "dark":
                blind.append(zid)
            elif float(h.get("value") or 0) > 0.5 and float(o.get("value") or 0) < 0.5 and float(h.get("confidence") or 0) >= 0.5:
                known.append(zid)
            elif float(h.get("value") or 0) > 0.5:
                suspected.append(zid)
            else:
                blind.append(zid)
        report["crossed"][name] = {"aboutCompany": {"known": known, "suspected": suspected, "blind": blind, "ofOurs": len(company_zones)}}
    (out_dir).mkdir(parents=True, exist_ok=True)
    (out_dir / "divergence.latest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def write_truth(state: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    fr = truth_frame(state, workspace)
    (workspace / "outbox").mkdir(parents=True, exist_ok=True)
    (workspace / "outbox" / "truth.latest.json").write_text(json.dumps(fr, indent=2, ensure_ascii=False), encoding="utf-8")
    return fr


def summary(report: Dict[str, Any]) -> str:
    L = [f"DIVERGENCE at minute {report.get('as_of_minute')}"]
    for name, p in (report.get("perspectives") or {}).items():
        L.append(f"  {name:<10} right {p['right']:>3}  ghost {len(p['ghostHoldings']):>2}  unknown {len(p['unknownHoldings']):>2}  wrongHeld {len(p['wrongHeld']):>2}  dark {p['dark']:>3}/{p['zones']}  gap {p['gap']}")
        for g in p["ghostHoldings"][:3]:
            L.append(f"      ghost: believes {g['label']} is theirs; actually {g['actually']}")
    for name, c in (report.get("crossed") or {}).items():
        a = c["aboutCompany"]
        L.append(f"  {name:<10} about the company's {a['ofOurs']} zones: knows {len(a['known'])}, suspects {len(a['suspected'])}, blind to {len(a['blind'])}")
    return "\n".join(L)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        ws = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT
        n = run_worker(ws)
        print(f"[perspectives worker] drained {n} job(s)", flush=True)
        sys.exit(0)
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    st = load_json(ws / "state" / "campaign_state.json")
    write_truth(st, ws)
    for r in fold_all(st, ws):
        print(r)
    print(summary(divergence(st, ws)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
