#!/usr/bin/env python3
"""Narrative density matrix projector (DERIVE face; never writes campaign state).

rho_N is a density matrix over *readings* — competing interpretations of the
company's situation — rather than over zones.

  diagonal      how much the evidence supports each reading
                (probes over state/campaign_state.json; see data/story/readings.json)
  off-diagonal  coherence: two readings no event has yet forced apart
                (event classes over history beads; see data/story/event_classes.json)

Levels come from state. Coherence comes from history. Nothing here is world truth,
nothing here is written back, and the whole face can be rebuilt from the save.

    python tools/readings_v1.py                 # pretty readout + outbox/readings.latest.json
    python tools/readings_v1.py --json          # JSON only
    python tools/readings_v1.py --state PATH    # another save
    python tools/readings_v1.py --no-write      # do not touch outbox

Pure standard library on purpose: the kernel runs where numpy may not.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "verdance-readings-face/0.1"
OUR_FACTION = "ashwalkers"


# ----------------------------------------------------------------------------- io

def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _clamp(x: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return lo
    if math.isnan(v):
        return lo
    return max(lo, min(hi, v))


def _path(obj: Any, dotted: str, default: Any = None) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


class _Safe(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return "?"


def _render(template: Optional[str], fields: Dict[str, Any]) -> Optional[str]:
    if not template:
        return None
    try:
        return template.format_map(_Safe(fields))
    except Exception:
        return template


# ----------------------------------------------------------------------------- context

class Context:
    """Everything a probe or detector may look at, computed once."""

    def __init__(self, state: Dict[str, Any], workspace: Path):
        self.state = state
        self.workspace = workspace
        self.names = self._hero_names()
        self.zone_control: Dict[Tuple[str, str], str] = {}
        self.zone_conf: Dict[Tuple[str, str], str] = {}
        self.holdings: Dict[str, int] = defaultdict(int)
        for map_id, zones in (state.get("zoneMemory") or {}).items():
            if not isinstance(zones, dict):
                continue
            for zone_id, zone in zones.items():
                if not isinstance(zone, dict):
                    continue
                fac = str(zone.get("controllingFaction") or (zone.get("abstract") or {}).get("control") or "neutral").lower()
                self.zone_control[(map_id, zone_id)] = fac
                self.zone_conf[(map_id, zone_id)] = str(zone.get("confidence") or "estimated")
                self.holdings[fac] += 1
        self.held_maps = sorted({m for (m, _z), f in self.zone_control.items() if f == OUR_FACTION})
        self.map_titles = self._map_titles()
        self.beads = self._beads()
        self.thread_titles = self._thread_titles()
        # Heroes whose fate is already placed on the timeline by a bead; snapshot
        # classes only speak for the ones legacy saves never stamped.
        self.placed: Dict[str, set] = defaultdict(set)
        for b in self.beads:
            for o in b["namedOutcomes"]:
                self.placed[str(o["charId"])].add(str(o.get("outcome")))

    def _map_titles(self) -> Dict[str, str]:
        titles: Dict[str, str] = {}
        pool = self.workspace / "data" / "map_pool" / "seven_maps.json"
        if pool.exists():
            try:
                for m in _load(pool).get("maps") or []:
                    if m.get("id"):
                        titles[str(m["id"])] = str(m.get("title") or m["id"])
            except Exception:
                pass
        return titles

    def map_name(self, map_id: Any) -> str:
        return self.map_titles.get(str(map_id), str(map_id).replace("_", " ").title() if map_id else "?")

    def _hero_names(self) -> Dict[str, str]:
        names: Dict[str, str] = {}
        codex = self.workspace / "data" / "story" / "hero_codex.json"
        if codex.exists():
            try:
                for h in _load(codex).get("heroes") or []:
                    names[str(h.get("heroId"))] = str(h.get("name") or h.get("heroId"))
            except Exception:
                pass
        for hid, ch in (self.state.get("characters") or {}).items():
            if isinstance(ch, dict):
                names.setdefault(hid, str(ch.get("name") or hid))
        return names

    def _thread_titles(self) -> Dict[str, str]:
        path = self.workspace / "data" / "story" / "narrative_threads.json"
        if not path.exists():
            return {}
        try:
            return {t["id"]: t.get("title", t["id"]) for t in _load(path).get("threads") or []}
        except Exception:
            return {}

    def _beads(self) -> List[Dict[str, Any]]:
        """One bead per completed Drop: history entry + narrative event + fronts + thread history."""
        history = [b for b in (self.state.get("history") or []) if isinstance(b, dict)]
        events = {e.get("id"): e for e in (_path(self.state, "narrative.events") or []) if isinstance(e, dict)}
        fronts = [f for f in (self.state.get("frontEvents") or []) if isinstance(f, dict)]
        ledger = [l for l in (_path(self.state, "commerce.ledger") or []) if isinstance(l, dict)]
        threads = _path(self.state, "narrative.threads") or {}
        # Reconstruct the graph after each bead from final graph minus later additive deltas.
        # Approximate: measure_graph_from_world easing is not recorded per bead.
        graph_after: List[Dict[str, float]] = []
        running = {k: float(v) for k, v in (self.state.get("graph") or {}).items() if isinstance(v, (int, float))}
        for bead in reversed(history):
            graph_after.append(dict(running))
            for axis, delta in (bead.get("graphDelta") or {}).items():
                if axis in running and isinstance(delta, (int, float)):
                    running[axis] -= float(delta)
        graph_after.reverse()
        graph_before = [dict(running)] + graph_after[:-1] if history else []
        out = []
        for idx, bead in enumerate(history):
            key = bead.get("resultKey")
            ev = events.get(key) or {}
            mission = bead.get("missionNumber")
            turn = ev.get("turn")
            th_hist = []
            for tid, t in threads.items():
                for h in (t.get("history") or []):
                    if turn is not None and h.get("turn") == turn and h.get("stage"):
                        th_hist.append({"thread": tid, "stage": h["stage"], "text": h.get("text", "")})
            out.append({
                "index": idx,
                "missionNumber": mission,
                "mapId": bead.get("mapId"),
                "verdict": bead.get("verdict") or bead.get("status"),
                "extraction": bead.get("extractionStatus") or "",
                "tags": list(bead.get("storyTags") or []),
                "pathSignal": bead.get("pathSignal"),
                "credits": dict(ev.get("credits") or {}),
                "participants": list(ev.get("participants") or []),
                "fronts": [f for f in fronts if f.get("missionNumber") == mission],
                "ledger": [l for l in ledger if l.get("missionNumber") == mission],
                "threadHistory": th_hist,
                "namedOutcomes": [o for o in (bead.get("namedOutcomes") or []) if isinstance(o, dict) and o.get("charId")],
                "joined": [j for j in (bead.get("joined") or []) if isinstance(j, dict)],
                "graphBefore": graph_before[idx] if idx < len(graph_before) else {},
                "graphAfter": graph_after[idx] if idx < len(graph_after) else {},
                "resultKey": key,
            })
        return out

    # -- character helpers
    def named(self) -> Dict[str, Dict[str, Any]]:
        return {hid: ch for hid, ch in (self.state.get("characters") or {}).items() if isinstance(ch, dict)}

    def display(self, hid: str) -> str:
        return self.names.get(hid, hid)

    def zone_held(self, map_id: Any, zone_id: Any) -> bool:
        return self.zone_control.get((str(map_id), str(zone_id))) == OUR_FACTION


# ----------------------------------------------------------------------------- probes

def probe(spec: Dict[str, Any], ctx: Context) -> Tuple[float, Dict[str, Any]]:
    kind = spec.get("probe")
    st = ctx.state
    f: Dict[str, Any] = {}
    if kind == "const":
        return _clamp(spec.get("value", 0.0)), f
    if kind in ("rep", "rep_inverse"):
        rep = float((st.get("reputation") or {}).get(spec["faction"], 0) or 0)
        f["pct"] = f"{rep:.0f}"
        v = _clamp(rep / 100.0)
        return (1.0 - v if kind == "rep_inverse" else v), f
    if kind == "graph":
        x = _clamp((st.get("graph") or {}).get(spec["axis"], 0.0))
        f["value"] = f"{x:.2f}"
        return x, f
    if kind in ("tag_rate", "verdict_rate"):
        window = int(spec.get("window", 6))
        beads = ctx.beads[-window:]
        denom = max(1, len(beads))
        if kind == "tag_rate":
            count = sum(1 for b in beads if spec["tag"] in b["tags"])
        else:
            count = sum(1 for b in beads if b["verdict"] in spec["verdicts"])
        f.update(count=count, window=denom)
        return _clamp(count / denom), f
    if kind == "commitment":
        t = (_path(st, "narrative.threads") or {}).get(spec["thread"]) or {}
        return (1.0 if t.get("commitment") == f"{spec['thread']}:{spec['choice']}" else 0.0), f
    if kind == "holdings_ratio":
        a = ctx.holdings.get(spec["faction"], 0)
        b = ctx.holdings.get(spec["against"], 0)
        f.update(a=a, b=b)
        return (_clamp(a / (a + b)) if (a + b) else 0.0), f
    if kind == "holdings_count":
        n = ctx.holdings.get(spec["faction"], 0)
        f["count"] = n
        return _clamp(n / float(spec.get("scale", 8))), f
    if kind == "holdings_share_inverse":
        total = sum(v for k, v in ctx.holdings.items() if k != "neutral")
        n = ctx.holdings.get(spec["faction"], 0)
        share = (n / total) if total else 0.0
        f["pct"] = f"{share * 100:.0f}%"
        return _clamp(1.0 - share), f
    if kind == "claimed_nodes":
        claimed = st.get("claimedNodes") or {}
        n = 0
        if isinstance(claimed, dict):
            for v in claimed.values():
                n += len(v) if isinstance(v, (dict, list)) else 1
        elif isinstance(claimed, list):
            n = len(claimed)
        f["count"] = n
        return _clamp(n / float(spec.get("scale", 2))), f
    if kind == "thread_resolved":
        t = (_path(st, "narrative.threads") or {}).get(spec["thread"]) or {}
        return (1.0 if (t.get("stage") == "Resolved" or t.get("resolvedTurn") is not None) else 0.0), f
    if kind == "thread_stage":
        t = (_path(st, "narrative.threads") or {}).get(spec["thread"]) or {}
        return (1.0 if t.get("stage") in spec.get("stages", []) else 0.0), f
    if kind in ("thread_trust", "thread_distrust"):
        trust = float((_path(st, "narrative.trust") or {}).get(spec["thread"], 0) or 0)
        f["value"] = trust
        scale = float(spec.get("scale", 2))
        return (_clamp(trust / scale) if kind == "thread_trust" else _clamp(-trust / scale)), f
    if kind == "flag":
        return (1.0 if _path(st, spec["path"]) else 0.0), f
    if kind == "number":
        x = float(_path(st, spec["path"], 0.0) or 0.0)
        f["value"] = f"{x:.2f}"
        return _clamp((x - float(spec.get("center", 0.0))) / float(spec.get("scale", 1.0))), f
    if kind == "ledger_ops":
        n = sum(1 for l in (_path(st, "commerce.ledger") or []) if isinstance(l, dict) and spec["match"] in str(l.get("op", "")).lower())
        f["count"] = n
        return _clamp(n / float(spec.get("scale", 2))), f
    if kind == "tenebrium_low":
        tnb = float(_path(st, "commerce.tenebrium", 0) or 0)
        thr = float(spec.get("threshold", 6))
        f.update(value=f"{tnb:g}", threshold=f"{thr:g}")
        return _clamp(1.0 - tnb / thr), f
    if kind in ("wounded_named", "dead_named"):
        hits = []
        for hid, ch in sorted(ctx.named().items()):
            if kind == "dead_named" and ch.get("status") == "dead":
                hits.append(hid)
            if kind == "wounded_named" and (ch.get("status") == "wounded" or int(ch.get("wounds") or 0) > 0):
                hits.append(hid)
        f.update(count=len(hits), names=", ".join(ctx.display(h) for h in hits) or "none")
        return _clamp(len(hits) / float(spec.get("scale", 2))), f
    if kind == "scars_total":
        n = sum(len(ch.get("scars") or []) for ch in ctx.named().values())
        f["count"] = n
        return _clamp(n / float(spec.get("scale", 4))), f
    if kind == "home_level":
        lvl = int(_path(st, "homeCamp.level", 0) or 0)
        f["value"] = lvl
        return _clamp(lvl / float(spec.get("scale", 2))), f
    if kind == "walker_locked":
        return (0.0 if _path(st, "roster.commander.unlocked") else 1.0), f
    if kind == "front_flips":
        n = 0
        for ev in st.get("frontEvents") or []:
            if not isinstance(ev, dict) or ev.get("type") != "offscreen_zone_flip":
                continue
            if "from" in spec and ev.get("fromFaction") != spec["from"]:
                continue
            if "to" in spec and ev.get("toFaction") != spec["to"]:
                continue
            n += 1
        f["count"] = n
        return _clamp(n / float(spec.get("scale", 2))), f
    if kind == "clashes_near_held":
        n = sum(1 for ev in st.get("frontEvents") or [] if isinstance(ev, dict) and ev.get("type") == "offscreen_clash"
                and (ctx.zone_held(ev.get("mapId"), ev.get("zoneA")) or ctx.zone_held(ev.get("mapId"), ev.get("zoneB"))))
        f["count"] = n
        return _clamp(n / float(spec.get("scale", 6))), f
    if kind == "unobserved_held_maps":
        zones = [(k, c) for k, c in ctx.zone_conf.items() if k[0] in ctx.held_maps]
        m = len(zones)
        n = sum(1 for _k, c in zones if c != "measured")
        f.update(n=n, m=m)
        return (_clamp(n / m) if m else 0.0), f
    raise KeyError(f"unknown probe {kind!r}")


# ----------------------------------------------------------------------------- detectors

EXTRACTION_WORDS = {
    "clean": "clean",
    "extracted": "extracted",
    "extracted_side_raid_damage": "extracted under fire",
    "extracted_damaged": "extracted, carrying damage",
    "lost": "lost",
    "timeout": "timed out",
    "abandon": "abandoned",
    "": "unrecorded",
}


def humanize_extraction(token: Any) -> str:
    key = str(token or "")
    return EXTRACTION_WORDS.get(key, key.replace("_", " "))


def _front_matches(ev: Dict[str, Any], spec: Dict[str, Any], ctx: Context) -> bool:
    if ev.get("type") != spec.get("type"):
        return False
    for key in ("fromFaction", "toFaction"):
        if key in spec and ev.get(key) != spec[key]:
            return False
    for neg, key in (("notFromFaction", "fromFaction"), ("notToFaction", "toFaction")):
        if neg in spec and ev.get(key) == spec[neg]:
            return False
    if spec.get("onHeldMap") and ev.get("mapId") not in ctx.held_maps:
        return False
    if spec.get("nearHeld") and not (ctx.zone_held(ev.get("mapId"), ev.get("zoneA")) or ctx.zone_held(ev.get("mapId"), ev.get("zoneB"))):
        return False
    return True


def detect_bead(cls: Dict[str, Any], bead: Dict[str, Any], ctx: Context) -> List[Dict[str, Any]]:
    """Return a list of firings (each with fields for the witness) for one bead."""
    d = cls["detect"]
    base = {"map": ctx.map_name(bead["mapId"]), "mapId": bead["mapId"], "ourMap": ctx.map_name(bead["mapId"]),
            "verdict": bead["verdict"], "extraction": bead["extraction"] or "unrecorded",
            "extractionText": humanize_extraction(bead["extraction"])}
    if "verdict" in d and bead["verdict"] not in d["verdict"]:
        return []
    if "tag" in d and d["tag"] not in bead["tags"]:
        return []
    if "not_tag" in d and d["not_tag"] in bead["tags"]:
        return []
    if "all_tags" in d and not all(t in bead["tags"] for t in d["all_tags"]):
        return []
    if "extraction_not" in d and (not bead["extraction"] or bead["extraction"] in d["extraction_not"]):
        return []
    if "credit" in d:
        return [dict(base)] if bead["credits"].get(d["credit"]) else []
    if "outcome" in d:
        wanted = d["outcome"] if isinstance(d["outcome"], list) else [d["outcome"]]
        out = []
        for o in bead["namedOutcomes"]:
            if str(o.get("outcome")) in wanted:
                hid = str(o["charId"])
                ch = ctx.named().get(hid) or {}
                out.append(dict(base, hero=ctx.display(hid), heroId=hid, wounds=int(ch.get("wounds") or 0), outcome=str(o.get("outcome"))))
        return out
    if d.get("tag") == "hero-joined" and bead["joined"]:
        names = ", ".join(str(j.get("name") or j.get("heroId")) for j in bead["joined"])
        return [dict(base, names=names, joinedIds=[str(j.get("heroId")) for j in bead["joined"]])]
    if "thread_stage" in d:
        out = []
        for h in bead["threadHistory"]:
            if h["stage"] == d["thread_stage"]:
                out.append(dict(base, thread=h["thread"], threadTitle=ctx.thread_titles.get(h["thread"], h["thread"]), text=h["text"]))
        return out
    if "front" in d:
        hits = [ev for ev in bead["fronts"] if _front_matches(ev, d["front"], ctx)]
        if not hits:
            return []
        if d["front"].get("type") == "offscreen_clash":
            return [dict(base, count=len(hits), map=ctx.map_name(hits[0].get("mapId")), mapId=hits[0].get("mapId"))]
        return [dict(base, label=ev.get("label") or ev.get("zoneId"), map=ctx.map_name(ev.get("mapId")), mapId=ev.get("mapId"),
                     toFaction=ev.get("toFaction"), fromFaction=ev.get("fromFaction")) for ev in hits]
    if "crossing" in d:
        c = d["crossing"]
        before = bead["graphBefore"].get(c["axis"])
        after = bead["graphAfter"].get(c["axis"])
        if before is None or after is None:
            return []
        lvl = float(c["level"])
        up = c.get("direction", "up") == "up"
        crossed = (before < lvl <= after) if up else (before > lvl >= after)
        return [dict(base, level=f"{lvl:.2f}", approx=True)] if crossed else []
    if "ledger_op" in d:
        hits = [l for l in bead["ledger"] if d["ledger_op"] in str(l.get("op", "")).lower()]
        return [dict(base)] if hits else []
    # verdict / tag-only detectors fall through here
    return [dict(base)]


def detect_snapshot(cls: Dict[str, Any], ctx: Context) -> List[Dict[str, Any]]:
    d = cls["detect"]
    st = ctx.state
    if "character_status" in d:
        return [{"hero": ctx.display(h), "heroId": h} for h, ch in sorted(ctx.named().items())
                if ch.get("status") == d["character_status"] and not (d.get("unplacedOnly") and d["character_status"] in ctx.placed.get(h, set()))]
    if "character_wounds_gt" in d:
        return [{"hero": ctx.display(h), "heroId": h, "wounds": int(ch.get("wounds") or 0)} for h, ch in sorted(ctx.named().items())
                if int(ch.get("wounds") or 0) > int(d["character_wounds_gt"])
                and not (d.get("unplacedOnly") and ctx.placed.get(h, set()) & {"recovered", "wounded"})]
    if "path" in d:
        x = _path(st, d["path"])
        if "equals" in d:
            return [{"value": x}] if x == d["equals"] else []
        if "gt" in d:
            try:
                return [{"value": f"{float(x):.2f}"}] if float(x) > float(d["gt"]) else []
            except (TypeError, ValueError):
                return []
    if "unobserved_held_maps_gt" in d:
        v, f = probe({"probe": "unobserved_held_maps"}, ctx)
        return [f] if v > float(d["unobserved_held_maps_gt"]) else []
    return []


# ----------------------------------------------------------------------------- coherence

class Coherence:
    def __init__(self, pairs: List[Dict[str, Any]], floor: float):
        self.c: Dict[Tuple[str, str], float] = {}
        self.meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.log: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        self.floor = floor
        for p in pairs:
            key = tuple(sorted(p["pair"]))
            self.c[key] = _clamp(p.get("initial", 1.0))
            self.meta[key] = p

    def apply(self, effect: Dict[str, Any], where: Dict[str, Any]) -> None:
        key = tuple(sorted(effect["pair"]))
        if key not in self.c:
            return
        s = _clamp(effect.get("strength", 0.0))
        if effect.get("effect") == "distinguish":
            self.c[key] = max(self.floor, self.c[key] * (1.0 - s))
        else:  # renew
            self.c[key] = min(1.0, self.c[key] + (1.0 - self.c[key]) * s)
        self.log[key].append(dict(where, effect=effect.get("effect"), toward=effect.get("toward"), strength=s, c_after=round(self.c[key], 4)))

    def leaning(self, key: Tuple[str, str]) -> Optional[str]:
        score: Dict[str, float] = defaultdict(float)
        for entry in self.log[key]:
            if entry["effect"] == "distinguish" and entry.get("toward"):
                score[entry["toward"]] += entry["strength"]
        if not score:
            return None
        ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(score.values()) or 1.0
        margin = (ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0)) / total
        # Forced both ways by comparable weight is not a lean; it is a torn company.
        return ranked[0][0] if margin >= 0.15 else None

    def status(self, key: Tuple[str, str]) -> str:
        c = self.c[key]
        if c > 0.66:
            return "open"
        if self.leaning(key) is None:
            return "torn"
        return "leaning" if c > 0.33 else "settled"


# ----------------------------------------------------------------------------- linear algebra (stdlib)

def jacobi_eigenvalues(a: List[List[float]], sweeps: int = 60) -> List[float]:
    n = len(a)
    m = [row[:] for row in a]
    for _ in range(sweeps):
        off = sum(m[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < 1e-18:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(m[p][q]) < 1e-15:
                    continue
                theta = (m[q][q] - m[p][p]) / (2.0 * m[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    mkp, mkq = m[k][p], m[k][q]
                    m[k][p] = c * mkp - s * mkq
                    m[k][q] = s * mkp + c * mkq
                for k in range(n):
                    mpk, mqk = m[p][k], m[q][k]
                    m[p][k] = c * mpk - s * mqk
                    m[q][k] = s * mpk + c * mqk
    return sorted((m[i][i] for i in range(n)), reverse=True)


def bhattacharyya(p: Dict[str, float], q: Dict[str, float]) -> float:
    keys = set(p) | set(q)
    return sum(math.sqrt(max(0.0, p.get(k, 0.0)) * max(0.0, q.get(k, 0.0))) for k in keys) ** 2


# ----------------------------------------------------------------------------- scenes

def company_ids(state: Dict[str, Any]) -> set:
    """Mirror of narrative_v1.company_ids: who can speak in camp."""
    company = state.get("company") or {}
    if company.get("sealed"):
        return set(company.get("core") or []) | set(company.get("band") or []) | set(company.get("joinedLater") or [])
    return {hid for hid, ch in (state.get("characters") or {}).items()
            if isinstance(ch, dict) and ch.get("player") and ch.get("status") not in ("dead", "locked")}


def resolve_scene(scene_id: Optional[str], ctx: Context, workspace: Path, depth: int = 0) -> Optional[Dict[str, Any]]:
    """Find the transition scene that can actually be staged with the people in camp."""
    if not scene_id or depth > 4:
        return None
    path = workspace / "data" / "story" / "attractor_scenes.json"
    if not path.exists():
        return None
    try:
        scenes = {s["id"]: s for s in _load(path).get("scenes") or []}
    except Exception:
        return None
    scene = scenes.get(scene_id)
    if not scene:
        return None
    owned = company_ids(ctx.state)
    chars = ctx.named()
    ok = True
    for hid in scene.get("pair") or []:
        ch = chars.get(hid) or {}
        if hid not in owned or ch.get("status") in ("dead", "wounded", "locked"):
            ok = False
    when = scene.get("when") or {}
    for hid in when.get("dead") or []:
        if (chars.get(hid) or {}).get("status") != "dead":
            ok = False
    if ok:
        return {"id": scene["id"], "title": scene.get("title"), "pair": scene.get("pair")}
    return resolve_scene(scene.get("fallback"), ctx, workspace, depth + 1)


# ----------------------------------------------------------------------------- projection

def project(state: Dict[str, Any], workspace: Path, previous_face: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = Context(state, workspace)
    readings_doc = _load(workspace / "data" / "story" / "readings.json")
    classes_doc = _load(workspace / "data" / "story" / "event_classes.json")
    attractors_path = workspace / "data" / "story" / "attractors.json"
    attractors_doc = _load(attractors_path) if attractors_path.exists() else None
    order = [r["id"] for r in readings_doc["readings"]]

    # --- diagonal: levels from state
    supports: Dict[str, float] = {}
    witnesses: Dict[str, List[Dict[str, Any]]] = {}
    for r in readings_doc["readings"]:
        total = 0.0
        rows = []
        for ev in r["evidence"]:
            v, fields = probe(ev, ctx)
            w = float(ev.get("weight", 1.0))
            contrib = w * v
            total += contrib
            text = _render(ev.get("witness"), fields)
            if text:
                rows.append({"text": text, "contribution": round(contrib, 4), "value": round(v, 4), "probe": ev["probe"]})
        rows.sort(key=lambda x: (-x["contribution"], x["text"]))
        supports[r["id"]] = total
        witnesses[r["id"]] = rows
    z = sum(supports.values()) or 1.0
    diag = {k: supports[k] / z for k in order}

    # --- coherence: history through the event surface
    coh = Coherence(readings_doc["coherencePairs"], float(_path(readings_doc, "dynamics.floor", 0.02) or 0.02))
    last_fired: Dict[str, int] = {}
    bead_rows = []
    occasions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def owner_for(cls: Dict[str, Any], fields: Dict[str, Any]) -> str:
        if cls.get("owner") == "by_thread":
            return (cls.get("threadOwners") or {}).get(fields.get("thread"), "ketha")
        return cls.get("owner", "narrator")

    def effects_for(cls: Dict[str, Any], fields: Dict[str, Any]) -> List[Dict[str, Any]]:
        if cls.get("owner") == "by_thread":
            return (cls.get("threadCoherence") or {}).get(fields.get("thread"), [])
        return cls.get("coherence") or []

    for bead in ctx.beads:
        fired = []
        for cls in classes_doc["classes"]:
            if cls["detect"].get("scope") != "bead":
                continue
            cooldown = int(cls.get("cooldownBeads", 0))
            if cls["id"] in last_fired and (bead["index"] - last_fired[cls["id"]]) <= cooldown and cooldown > 0:
                continue
            hits = detect_bead(cls, bead, ctx)
            if not hits:
                continue
            last_fired[cls["id"]] = bead["index"]
            for fields in hits:
                owner = owner_for(cls, fields)
                template = cls.get("witnessNamed") if (fields.get("names") and cls.get("witnessNamed")) else cls.get("witness")
                row = {"class": cls["id"], "label": cls["label"], "owner": owner, "occasion": cls.get("occasion"),
                       "witness": _render(template, fields), "fields": fields}
                if cls.get("aliasOf"):
                    row["aliasOf"] = cls["aliasOf"]
                if fields.get("approx"):
                    row["approx"] = True
                fired.append(row)
                occasions[owner].append(dict(row, missionNumber=bead["missionNumber"]))
                for eff in effects_for(cls, fields):
                    coh.apply(eff, {"missionNumber": bead["missionNumber"], "class": cls["id"], "witness": row["witness"]})
        bead_rows.append({
            "missionNumber": bead["missionNumber"], "mapId": bead["mapId"], "verdict": bead["verdict"],
            "extraction": bead["extraction"], "fired": fired,
            "coherenceAfter": {" | ".join(k): round(v, 3) for k, v in sorted(coh.c.items())},
        })

    snapshot_rows = []
    for cls in classes_doc["classes"]:
        if cls["detect"].get("scope") != "snapshot":
            continue
        hits = detect_snapshot(cls, ctx)
        if not hits:
            continue
        for fields in hits:
            owner = owner_for(cls, fields)
            row = {"class": cls["id"], "label": cls["label"], "owner": owner, "occasion": cls.get("occasion"),
                   "witness": _render(cls.get("witness"), fields), "fields": fields}
            if cls.get("aliasOf"):
                row["aliasOf"] = cls["aliasOf"]
            if cls.get("dataGap"):
                row["dataGap"] = cls["dataGap"]
            snapshot_rows.append(row)
            occasions[owner].append(dict(row, missionNumber=None))
        # Coherence is applied once per class, with diminishing returns over the number of hits,
        # so three recovered frames do not outvote two dead ones three-to-two by repetition.
        count = len(hits)
        summary = "; ".join(filter(None, (_render(cls.get("witness"), f) for f in hits)))
        for eff in effects_for(cls, hits[0]):
            s = _clamp(eff.get("strength", 0.0))
            agg = dict(eff, strength=1.0 - (1.0 - s) ** count)
            coh.apply(agg, {"missionNumber": None, "class": cls["id"], "count": count, "witness": summary})

    # --- rho
    n = len(order)
    idx = {k: i for i, k in enumerate(order)}
    rho = [[0.0] * n for _ in range(n)]
    for k in order:
        rho[idx[k]][idx[k]] = diag[k]
    for key, c in coh.c.items():
        a, b = key
        if a in idx and b in idx:
            v = c * math.sqrt(diag[a] * diag[b])
            rho[idx[a]][idx[b]] = v
            rho[idx[b]][idx[a]] = v
    eig = jacobi_eigenvalues(rho)
    purity = sum(sum(rho[i][j] * rho[j][i] for j in range(n)) for i in range(n))
    entropy = -sum(e * math.log(e) for e in eig if e > 1e-12)
    diag_entropy = -sum(p * math.log(p) for p in diag.values() if p > 1e-12)

    # --- attractors
    attractor_out = None
    if attractors_doc:
        settled_pairs = sum(1 for key in coh.c if coh.c[key] <= 0.33)
        sharpen = float(attractors_doc.get("sharpen", 1.0))

        def _sharp(d: Dict[str, float]) -> Dict[str, float]:
            s = {k: max(0.0, v) ** sharpen for k, v in d.items()}
            zs = sum(s.values()) or 1.0
            return {k: v / zs for k, v in s.items()}

        scored = []
        for att in attractors_doc.get("attractors") or []:
            sig = {k: float(v) for k, v in (att.get("signature") or {}).items()}
            base = float(att.get("baseline", 0.02))
            q = {k: sig.get(k, base) for k in order}
            fid = bhattacharyya(_sharp(diag), _sharp(q))
            unmet = []
            for req in att.get("requires") or []:
                if "settledPairsMin" in req and settled_pairs < int(req["settledPairsMin"]):
                    unmet.append(f"only {settled_pairs} question(s) forced; needs {req['settledPairsMin']}")
                if "purityMin" in req and purity < float(req["purityMin"]):
                    unmet.append(f"purity {purity:.2f} < {req['purityMin']}")
                if "pair" not in req:
                    continue
                key = tuple(sorted(req["pair"]))
                c = coh.c.get(key)
                if c is None:
                    continue
                label = " | ".join(key)
                if "minCoherence" in req and c < float(req["minCoherence"]):
                    unmet.append(f"{label} coherence {c:.2f} < {req['minCoherence']}")
                if "maxCoherence" in req and c > float(req["maxCoherence"]):
                    unmet.append(f"{label} coherence {c:.2f} > {req['maxCoherence']}")
                if "leaning" in req:
                    lean = coh.leaning(key)
                    allowed = req["leaning"] if isinstance(req["leaning"], list) else [req["leaning"]]
                    if lean not in allowed:
                        unmet.append(f"{label} leans {lean or 'nowhere'}; needs {allowed}")
            scored.append({"id": att["id"], "title": att.get("title"), "fidelity": round(fid, 4),
                           "inside": fid >= float(att.get("tolerance", 0.8)) and not unmet,
                           "unmet": unmet, "leads": att.get("leads") or [], "terminal": bool(att.get("terminal"))})
        scored.sort(key=lambda s: (-s["fidelity"], s["id"]))
        eligible = [s for s in scored if not s["unmet"]] or scored
        nearest = eligible[0]["id"] if eligible else None
        # Stickiness: stay in the previous attractor unless a rival clears it by a margin.
        previous = (previous_face or {}).get("attractor") or {}
        prev_id = previous.get("current")
        if prev_id and nearest and prev_id != nearest:
            prev_row = next((s for s in eligible if s["id"] == prev_id), None)
            margin = float(attractors_doc.get("stickiness", 0.05))
            if prev_row and eligible[0]["fidelity"] - prev_row["fidelity"] < margin:
                nearest = prev_id
        transition = None
        if prev_id and nearest and prev_id != nearest:
            att_prev = next((a for a in attractors_doc["attractors"] if a["id"] == prev_id), {})
            edge = next((e for e in att_prev.get("edges") or [] if e.get("to") == nearest), None)
            transition = {"from": prev_id, "to": nearest, "scene": (edge or {}).get("scene") or f"enter:{nearest}",
                          "edgeAuthored": edge is not None}
        current = next((a for a in attractors_doc["attractors"] if a["id"] == nearest), {})
        if transition:
            transition["sceneResolved"] = resolve_scene(transition["scene"], ctx, workspace)
        attractor_out = {"current": nearest, "nearest": eligible[0]["id"] if eligible else None,
                         "entryScene": resolve_scene(f"enter:{nearest}", ctx, workspace) if nearest else None,
                         "inside": bool(eligible and eligible[0]["id"] == nearest and eligible[0]["inside"]),
                         "leads": current.get("leads") or [], "framing": current.get("framing"),
                         "favorThreads": current.get("favorThreads") or [],
                         "settledPairs": settled_pairs, "transition": transition, "previous": prev_id, "all": scored}

    fired_ids = {r["class"] for b in bead_rows for r in b["fired"]} | {r["class"] for r in snapshot_rows}
    gaps = sorted({cls["dataGap"] for cls in classes_doc["classes"] if cls.get("dataGap") and cls["id"] in fired_ids})
    gaps.append("graph crossings are reconstructed from additive graphDelta only; measure_graph_from_world easing is not stamped per bead")

    readings_out = []
    for k in order:
        spec = next(r for r in readings_doc["readings"] if r["id"] == k)
        readings_out.append({"id": k, "title": spec["title"], "gloss": spec["gloss"], "argues": spec.get("argues"), "resists": spec.get("resists"),
                             "weight": round(diag[k], 4), "support": round(supports[k], 4), "witnesses": witnesses[k][:5]})
    readings_out.sort(key=lambda r: (-r["weight"], r["id"]))

    coherence_out = []
    for key in sorted(coh.c):
        meta = coh.meta[key]
        coherence_out.append({"pair": list(key), "question": meta.get("question"), "c": round(coh.c[key], 4),
                              "status": coh.status(key), "leaning": coh.leaning(key), "history": coh.log[key]})

    return {
        "schemaVersion": SCHEMA,
        "generatedFrom": {"missionNumber": state.get("missionNumber"), "beads": len(ctx.beads), "campaignId": state.get("campaignId")},
        "dominant": readings_out[0]["id"] if readings_out else None,
        "readings": readings_out,
        "coherence": coherence_out,
        "rho": {"order": order, "matrix": [[round(v, 4) for v in row] for row in rho], "eigenvalues": [round(e, 4) for e in eig],
                "purity": round(purity, 4), "entropy": round(entropy, 4), "diagonalEntropy": round(diag_entropy, 4),
                "maxEntropy": round(math.log(n), 4)},
        "events": {"beads": bead_rows, "snapshot": snapshot_rows},
        "occasions": {k: v for k, v in sorted(occasions.items())},
        "attractor": attractor_out,
        "dataGaps": gaps,
    }


# ----------------------------------------------------------------------------- readout

def readout(face: Dict[str, Any]) -> str:
    L: List[str] = []
    g = face["generatedFrom"]
    L.append(f"READINGS  mission {g.get('missionNumber')}  beads {g.get('beads')}  campaign {g.get('campaignId')}")
    L.append("")
    L.append("Diagonal (what the evidence says the company is):")
    for r in face["readings"]:
        bar = "#" * int(round(r["weight"] * 40))
        L.append(f"  {r['weight']:.3f} {bar:<40} {r['title']}  [{r['id']}]  argues={r['argues']}")
        for w in r["witnesses"][:3]:
            L.append(f"           - {w['text']}  (+{w['contribution']:.2f})")
    L.append("")
    L.append("Coherence (what no event has yet forced apart):")
    for c in face["coherence"]:
        lean = f" -> leaning {c['leaning']}" if c["leaning"] else ""
        L.append(f"  c={c['c']:.2f} {c['status']:<8} {c['pair'][0]} | {c['pair'][1]}   \"{c['question']}\"{lean}")
        for h in c["history"][-2:]:
            L.append(f"           - m{h.get('missionNumber')}: {h['class']} {h['effect']} {h.get('toward') or ''} (c={h['c_after']})  {h.get('witness') or ''}")
    rho = face["rho"]
    L.append("")
    L.append(f"rho_N  purity {rho['purity']:.3f}  entropy {rho['entropy']:.3f} (diag {rho['diagonalEntropy']:.3f}, max {rho['maxEntropy']:.3f})  eigen {rho['eigenvalues'][:4]}")
    if face.get("attractor"):
        a = face["attractor"]
        L.append("")
        L.append(f"Attractor: {a['current']}  (nearest {a['nearest']}, inside={a['inside']}, questions forced {a['settledPairs']})  leads={','.join(a.get('leads') or [])}")
        if a.get("framing"):
            L.append(f"  framing: {a['framing']}")
        if a.get("transition"):
            t = a["transition"]
            staged = (t.get("sceneResolved") or {}).get("id") or "none stageable"
            L.append(f"  TRANSITION {t['from']} -> {t['to']}  scene={t['scene']} -> {staged}" + ("" if t["edgeAuthored"] else "  (no authored edge)"))
        elif a.get("entryScene"):
            L.append(f"  entry scene stageable: {a['entryScene']['id']}  ({', '.join(a['entryScene'].get('pair') or [])})")
        for s in a["all"]:
            flag = "*" if s["id"] == a["current"] else " "
            L.append(f"  {flag} {s['fidelity']:.3f} {s['id']:<20} {(s.get('title') or ''):<28}" + (f"  UNMET: {'; '.join(s['unmet'])}" if s["unmet"] else ""))
    L.append("")
    L.append("Event surface by bead:")
    for b in face["events"]["beads"]:
        L.append(f"  m{b['missionNumber']} {b['mapId']} {b['verdict']} [{b['extraction'] or 'unrecorded'}]")
        for f in b["fired"]:
            L.append(f"      {f['owner']:<8} {f['class']:<26} {f['witness'] or ''}" + ("  (approx)" if f.get("approx") else ""))
    L.append("  snapshot:")
    for f in face["events"]["snapshot"]:
        L.append(f"      {f['owner']:<8} {f['class']:<26} {f['witness'] or ''}")
    L.append("")
    L.append("Occasions per voice:")
    for owner, rows in face["occasions"].items():
        L.append(f"  {owner}: {len(rows)}  " + "; ".join(sorted({r['class'] for r in rows})))
    if face.get("dataGaps"):
        L.append("")
        L.append("Data gaps:")
        for gline in face["dataGaps"]:
            L.append(f"  - {gline}")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", default=str(ROOT))
    ap.add_argument("--state", default=None)
    ap.add_argument("--json", action="store_true", help="print JSON instead of the readout")
    ap.add_argument("--no-write", action="store_true", help="do not write outbox/readings.latest.json")
    ap.add_argument("--fresh", action="store_true", help="ignore the previous face (no attractor stickiness / transition)")
    args = ap.parse_args(argv)
    workspace = Path(args.workspace)
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    state = _load(state_path)
    out = workspace / "outbox" / "readings.latest.json"
    previous = None
    if out.exists() and not args.fresh:
        try:
            previous = _load(out)
            if previous.get("generatedFrom", {}).get("campaignId") != state.get("campaignId"):
                previous = None
        except Exception:
            previous = None
    face = project(copy.deepcopy(state), workspace, previous)
    face["generatedFrom"]["statePath"] = str(state_path)
    if not args.no_write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(face, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(face, indent=2, ensure_ascii=False))
    else:
        print(readout(face))
    return 0


if __name__ == "__main__":
    sys.exit(main())
