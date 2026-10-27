#!/usr/bin/env python3
"""Verdance as an Umwelt world (DERIVE; never world truth).

The company's comprehension of Verdance is a belief field, not a record:

  zones     ours / held (unitary: stick until contradicted)
            strength / threat (dissipative: forget toward the fog when nobody looks)
  people    fit / pressure / frame_intact (dissipative)
  company   the six questions as icon-axes (dissipative, slow: an unforced question reopens)
  clock     the Verdance day as a DriverSpec (in-universe time, not compute time)

Every observation carries eta. Drop telemetry is ~1.0; a scout patrol 0.5-0.7; a report
inferred from an adjacent measured zone 0.2; a patron dispatch 0.3 and biased. eta=0 is a
no-op. A value nobody measured renders dark, never zero (frame/1 law).

Depends on Umwelt (AQuantumArchitect/umwelt): set UMWELT_SRC to its src/ dir, or install it.
Pure data in, pure data out: build_spec() reads data/zone_maps/world_zone_graph.v1.json,
data/story/hero_codex.json and data/story/readings.json.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from verdance.common import TOOLS_DIR, WORKSPACE_ROOT, load_json

ROOT = WORKSPACE_ROOT
SCHEMA = "verdance-intel/1"
OUR_FACTION = "ashwalkers"
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)   # campaign minute 0
DAY_S = 86400.0

ZONE_ROLES = ("ours", "held", "strength", "threat")
ZONE_MODES = {"ours": "unitary", "held": "unitary", "strength": "dissipative", "threat": "dissipative"}
HERO_ROLES = ("fit", "pressure", "frame_intact")
# draw: the company's sense that someone is near (word of them, a bonded companion joining). The
# bond web couples it between hero nodes, so the field itself spreads the word; it fades when
# nobody hears of them. Read by verdance.company.encounters through umwelt.foresight.encounter.
DRAW_ROLE = "draw"

# Axis faces for the company's questions. pole_0 is +z (value 1.0), pole_1 is -z (value 0.0).
QUESTIONS = {
    "whose_war":        {"pair": ("auxiliary", "sovereign"), "pole_0": "sovereign", "pole_1": "auxiliary", "icon": "\U0001F3F3",  "question": "Whose war is this?"},
    "home_or_hospital": {"pair": ("rooted", "bleeding"),     "pole_0": "rooted",    "pole_1": "bleeding",  "icon": "\U0001F525",  "question": "Is the camp a home or a hospital?"},
    "whose_paper":      {"pair": ("indebted", "sovereign"),  "pole_0": "sovereign", "pole_1": "indebted",  "icon": "\U0001F4DC",  "question": "Who holds the paper?"},
    "go_back":          {"pair": ("haunted", "rooted"),      "pole_0": "rooted",    "pole_1": "haunted",   "icon": "\U0001FAA6",  "question": "Do we go back for them?"},
    "pressure":         {"pair": ("hunted", "armada_falling"), "pole_0": "armada_falling", "pole_1": "hunted", "icon": "\U0001F441", "question": "Is the pressure coming or going?"},
    "creditor":         {"pair": ("auxiliary", "indebted"),  "pole_0": "auxiliary", "pole_1": "indebted",  "icon": "\U0001FA99",  "question": "Which creditor?"},
}


# The finale paths, read off the company's own questions. Each path is the story the company has
# come to believe about itself; its signal is how far the two questions lean its way (0..1).
#   A overthrow   we fight as someone's blade, and Armada is falling
#   B sovereignty the war and the paper are ours
#   C spire jump  the camp is home, and we go back for our own
PATH_READS = {
    "A": (("whose_war", "auxiliary"), ("pressure", "armada_falling")),
    "B": (("whose_war", "sovereign"), ("whose_paper", "sovereign")),
    "C": (("home_or_hospital", "rooted"), ("go_back", "rooted")),
}


def path_signals(frame: Dict[str, Any]) -> Dict[str, float]:
    """A/B/C from the belief frame's questions: the mean lean toward each path's two poles."""
    by_id = {q.get("id"): q for q in frame.get("questions") or []}
    out = {}
    for path, reads in PATH_READS.items():
        total = 0.0
        for qid, pole in reads:
            q = by_id.get(qid) or {}
            z = float((q.get("bloch") or [0, 0, 0])[2])
            toward = z if pole == q.get("pole_0") else -z  # pole_0 is +z
            total += max(0.0, toward)
        out[path] = round(total / len(reads), 4)
    return out


class UmweltUnavailable(RuntimeError):
    """Raised by build_spec / VerdanceWorld when the umwelt package cannot be imported.

    A plain Exception (never SystemExit): every caller folds belief inside try/except
    Exception and reports VA_BELIEF_SKIP / VA_BELIEF_FAIL; a SystemExit would have
    escaped those handlers and killed the homecoming it was meant to decorate."""


_UMWELT_WARNED = False


def umwelt_search_paths() -> List[Path]:
    """Where the umwelt package may live, first match wins (sys.path order):
    UMWELT_SRC, a sibling clone, ~/umwelt, ~/ws-win/umwelt, then LAST the shipped
    snapshot tools/_vendor and the embedded runtime's runtime/site-packages."""
    out: List[Path] = []
    src = os.environ.get("UMWELT_SRC")
    if src:
        out.append(Path(src))
    out += [ROOT.parent / "umwelt" / "src",
            Path.home() / "umwelt" / "src",
            Path.home() / "ws-win" / "umwelt" / "src",
            TOOLS_DIR / "_vendor",
            ROOT / "runtime" / "site-packages"]
    return out


def _umwelt():
    """(umwelt.spec.schema, umwelt.host.api) or None when Umwelt is not importable.

    Never raises SystemExit. A failed import logs one line to stderr (once per process)
    and returns None; the campaign then runs without the belief world (VA_BELIEF_SKIP)."""
    global _UMWELT_WARNED
    # Last candidates are appended, not inserted: a developer clone must beat the vendored snapshot.
    for cand in umwelt_search_paths():
        try:
            if cand.is_dir() and (cand / "umwelt" / "__init__.py").is_file() and str(cand) not in sys.path:
                sys.path.append(str(cand))
        except OSError:
            continue
    try:
        from umwelt.spec.schema import DomainSpec, NodeSpec, BridgeSpec, BindingSpec, DriverSpec, AxisFace  # noqa
        from umwelt.host.api import GameHost  # noqa
    except Exception as exc:  # noqa: BLE001 - ImportError, or numpy/scipy missing under it
        if not _UMWELT_WARNED:
            _UMWELT_WARNED = True
            print(f"verdance.belief.world: Umwelt not importable ({type(exc).__name__}: {exc}); belief world off. "
                  "Set UMWELT_SRC=<umwelt>/src, or ship with numpy/scipy + tools/_vendor.", file=sys.stderr)
        return None
    return sys.modules["umwelt.spec.schema"], sys.modules["umwelt.host.api"]


def umwelt_available() -> bool:
    return _umwelt() is not None


def _require_umwelt():
    mods = _umwelt()
    if mods is None:
        raise UmweltUnavailable("Umwelt not importable; belief world skipped (VA_BELIEF_SKIP)")
    return mods


def minute_to_time(campaign_minute: float) -> datetime:
    return EPOCH + timedelta(minutes=float(campaign_minute or 0.0))


# ----------------------------------------------------------------------------- spec

def world_graph(workspace: Path) -> Dict[str, Any]:
    return load_json(workspace / "data" / "zone_maps" / "world_zone_graph.v1.json")


def hero_ids(workspace: Path) -> List[str]:
    codex = workspace / "data" / "story" / "hero_codex.json"
    if not codex.exists():
        return []
    return sorted(str(h["heroId"]) for h in load_json(codex).get("heroes") or [] if h.get("heroId"))


def bond_pairs(workspace: Path) -> List[Tuple[str, str]]:
    """The authored bonds and tensions (support_web), one sorted pair each."""
    path = workspace / "data" / "story" / "support_web.json"
    if not path.exists():
        return []
    out = set()
    for e in load_json(path).get("edges") or []:
        if e.get("authored") and e.get("a") and e.get("b") and e["a"] != e["b"]:
            out.add(tuple(sorted((str(e["a"]), str(e["b"])))))
    return sorted(out)


def build_spec(workspace: Path, extra_zones: Optional[Iterable[Dict[str, Any]]] = None):
    """extra_zones: [{zoneId, mapId, label}] present in a save but missing from the zone
    graph (the graph is older than zoneMemory). They get nodes but no bridges, and a
    data-gap note; regenerate world_zone_graph to retire the parameter."""
    schema, _ = _require_umwelt()
    graph = world_graph(workspace)
    zones = [n for n in graph.get("nodes") or [] if n.get("zoneId")]
    known = {str(z["zoneId"]) for z in zones}
    for z in extra_zones or []:
        if z.get("zoneId") and str(z["zoneId"]) not in known:
            zones.append({"zoneId": str(z["zoneId"]), "mapId": str(z.get("mapId") or "unknown"), "label": z.get("label"), "tags": ["unmapped"], "anchor": {}})
            known.add(str(z["zoneId"]))
    nodes = [schema.NodeSpec("verdance", parent=None, kind="root", roles=("threat",))]
    # Maps as regions: zones hang under their map so the tree reads like the theater.
    maps = sorted({str(z["mapId"]) for z in zones})
    for m in maps:
        nodes.append(schema.NodeSpec(f"map:{m}", parent="verdance", kind="region", roles=("threat",), reduce="max"))
    for z in zones:
        zid = str(z["zoneId"])
        nodes.append(schema.NodeSpec(
            zid, parent=f"map:{z['mapId']}", kind="region", roles=ZONE_ROLES, role_modes=dict(ZONE_MODES),
            features=tuple(str(t) for t in (z.get("tags") or [])),
            grid_pos=(int(round(float((z.get("anchor") or {}).get("x", 0.5)) * 100)), int(round(float((z.get("anchor") or {}).get("z", 0.5)) * 100))),
            params={"gamma_diss": (0.03, 0.01, 0.001, 0.3), "gamma_diss_threat": (0.08, 0.02, 0.001, 0.5), "gamma_diss_strength": (0.03, 0.01, 0.001, 0.3)},
            faces=(schema.AxisFace("ours", axis_id=f"{zid}.ours", pole_0="ours", pole_1="not ours"),
                   schema.AxisFace("held", axis_id=f"{zid}.held", pole_0="held", pole_1="empty"),
                   schema.AxisFace("strength", axis_id=f"{zid}.strength", pole_0="dug in", pole_1="thin"),
                   schema.AxisFace("threat", axis_id=f"{zid}.threat", pole_0="guns heard", pole_1="quiet")),
        ))
    # People: the company's comprehension of its own, which is also partial.
    nodes.append(schema.NodeSpec("people", parent="verdance", kind="region", roles=("fit",), reduce="mean"))
    for hid in hero_ids(workspace):
        nodes.append(schema.NodeSpec(
            f"hero:{hid}", parent="people", kind="entity", roles=HERO_ROLES + (DRAW_ROLE,),
            role_modes={"fit": "dissipative", "pressure": "dissipative", "frame_intact": "dissipative", DRAW_ROLE: "dissipative"},
            params={"gamma_diss": (0.01, 0.005, 0.0005, 0.1), "gamma_diss_pressure": (0.02, 0.01, 0.001, 0.2),
                    "gamma_diss_draw": (0.03, 0.01, 0.001, 0.3)},
        ))
    # The company: six questions as icon-axes. Dissipative and slow: silence reopens a question.
    nodes.append(schema.NodeSpec(
        "company", parent="verdance", kind="entity", roles=tuple(QUESTIONS),
        role_modes={q: "dissipative" for q in QUESTIONS},
        params={"gamma_diss": (0.004, 0.002, 0.0002, 0.05)},
        faces=tuple(schema.AxisFace(q, axis_id=f"company.{q}", pole_0=spec["pole_0"], pole_1=spec["pole_1"]) for q, spec in QUESTIONS.items()),
    ))
    bridges = []
    for e in graph.get("edges") or []:
        a, b = str(e.get("from")), str(e.get("to"))
        kind = "open" if e.get("kind") == "same_map" else "gated"
        bridges.append(schema.BridgeSpec(a, b, shared_roles=("threat",), kind=kind))
    # the bond web: word of someone travels to the people they are bound to (one bridge per pair)
    heroes = set(hero_ids(workspace))
    for a, b in bond_pairs(workspace):
        if a in heroes and b in heroes:
            bridges.append(schema.BridgeSpec(f"hero:{a}", f"hero:{b}", shared_roles=(DRAW_ROLE,), kind="open"))
    bindings = []
    norm = {"type": "range", "lo": 0.0, "hi": 1.0}
    for z in zones:
        for r in ZONE_ROLES:
            bindings.append(schema.BindingSpec(f"obs_{z['zoneId']}_{r}", zone=str(z["zoneId"]), role=r, normalizer=norm,
                                               force_observe=True, efficiency=1.0, strength=0.8))
    for hid in hero_ids(workspace):
        for r in HERO_ROLES + (DRAW_ROLE,):
            bindings.append(schema.BindingSpec(f"obs_hero_{hid}_{r}", zone=f"hero:{hid}", role=r, normalizer=norm,
                                               force_observe=True, efficiency=1.0, strength=0.8))
    for q in QUESTIONS:
        # A question moves by the event's full admitted strength: eta IS the push.
        bindings.append(schema.BindingSpec(f"obs_company_{q}", zone="company", role=q, normalizer=norm,
                                           force_observe=True, efficiency=1.0, strength=1.0))
    return schema.DomainSpec(
        name="verdance-ashes",
        nodes=tuple(nodes), bridges=tuple(bridges), bindings=tuple(bindings),
        drivers=(schema.DriverSpec("day", period_s=DAY_S),),
        anchors={},
    )


# ----------------------------------------------------------------------------- host

class VerdanceWorld:
    """One company, one mind. Wraps GameHost with the Verdance vocabulary."""

    def __init__(self, workspace: Path, start_minute: float = 0.0, extra_zones: Optional[Iterable[Dict[str, Any]]] = None):
        _, api = _require_umwelt()
        self.workspace = Path(workspace)
        self.extra_zones = list(extra_zones or [])
        self.spec = build_spec(self.workspace, self.extra_zones)
        self.pushes: Dict[str, Dict[str, float]] = {q: {"pole_0": 0.0, "pole_1": 0.0, "renew": 0.0} for q in QUESTIONS}
        self.host = api.GameHost().register_world(self.spec, population=False, start=minute_to_time(start_minute))
        self.last_seen: Dict[str, Dict[str, Any]] = {}     # "node.role" -> {minute, source, eta}
        # who we last SAW holding a zone (a label, not a quantity): the board's faction colour is
        # this, at the held row's confidence. Nobody-looked zones have no entry.
        self.seen_faction: Dict[str, Dict[str, Any]] = {}  # zoneId -> {faction, minute, eta, source}
        self._batch: Optional[Dict[str, Any]] = None
        self.zone_meta = {str(z["zoneId"]): z for z in world_graph(self.workspace).get("nodes") or [] if z.get("zoneId")}
        for z in self.extra_zones:
            self.zone_meta.setdefault(str(z.get("zoneId")), dict(z, unmapped=True))
        self._primed = False

    # -- time
    @property
    def minute(self) -> float:
        return (self.host.now - EPOCH).total_seconds() / 60.0

    def advance(self, minutes: float, step_minutes: float = 30.0) -> None:
        """Let the fog grow: empty ticks in bounded steps (in-universe time)."""
        remaining = float(minutes)
        while remaining > 1e-9:
            dt = min(step_minutes, remaining)
            self.host.step(dt_s=dt * 60.0)
            remaining -= dt

    # -- priming: nobody has looked
    def prime_dark(self, passes: int = 4) -> None:
        """Boot is a pure pole; the honest start is 'nobody has looked'. Observing 0.5 at
        full eta pulls every axis toward the mixed centre without stamping a source."""
        readings = {b.sensor_id: 0.5 for b in self.spec.bindings}
        conf = {k: 1.0 for k in readings}
        for _ in range(passes):
            self.host.observe_many("prime", readings, conf, t=self.host.now)
        self._primed = True

    # -- observations
    # Batching: one engine ingest costs the same whether it carries 1 channel or 500,
    # so a homecoming gathers its observations and flushes once per time point.
    def begin_batch(self) -> None:
        self._batch = {"readings": {}, "conf": {}, "source": {}, "minute": None}

    def flush(self) -> Optional[Dict[str, Any]]:
        b = getattr(self, "_batch", None)
        self._batch = None
        if not b or not b["readings"]:
            return None
        return self._ingest(b["readings"], b["conf"], b["source"], b["minute"])

    def observe(self, readings: Dict[str, float], eta: float | Dict[str, float], *, source: str, minute: Optional[float] = None) -> Optional[Dict[str, Any]]:
        conf = {k: float(eta if not isinstance(eta, dict) else eta.get(k, 1.0)) for k in readings}
        b = getattr(self, "_batch", None)
        if b is not None:
            for k, v in readings.items():
                e = conf[k]
                if e <= 0:
                    continue
                if k not in b["readings"] or e >= b["conf"][k]:
                    b["readings"][k] = float(v)
                    b["conf"][k] = e
                    b["source"][k] = source
            if minute is not None:
                b["minute"] = max(float(minute), float(b["minute"] or 0.0))
            return None
        return self._ingest({k: float(v) for k, v in readings.items()}, conf, {k: source for k in readings}, minute)

    def _ingest(self, readings: Dict[str, float], conf: Dict[str, float], source: Dict[str, str], minute: Optional[float]) -> Dict[str, Any]:
        t = minute_to_time(minute) if minute is not None else self.host.now
        if t < self.host.now:
            t = self.host.now
        res = self.host.observe_many("company", readings, conf, t=t)
        m = (t - EPOCH).total_seconds() / 60.0
        for k, e in conf.items():
            if e > 0:
                node_role = self._channel_to_key(k)
                prev = self.last_seen.get(node_role)
                if prev is None or e >= 0.5 * float(prev.get("eta", 0)) or m > float(prev.get("minute", -1)):
                    self.last_seen[node_role] = {"minute": round(m, 3), "source": source.get(k, "?"), "eta": round(e, 3)}
        return res

    @staticmethod
    def _channel_to_key(channel: str) -> str:
        # obs_<zone>_<role> / obs_hero_<id>_<role> / obs_company_<q>
        if channel.startswith("obs_company_"):
            return "company." + channel[len("obs_company_"):]
        if channel.startswith("obs_hero_"):
            rest = channel[len("obs_hero_"):]
            hid, role = rest.rsplit("_", 1)
            return f"hero:{hid}.{role}"
        rest = channel[len("obs_"):]
        zid, role = rest.rsplit("_", 1)
        return f"{zid}.{role}"

    def observe_zone(self, zone_id: str, *, source: str, eta: float, minute: Optional[float] = None,
                     ours: Optional[float] = None, held: Optional[float] = None,
                     strength: Optional[float] = None, threat: Optional[float] = None,
                     faction: Optional[str] = None) -> None:
        if faction is not None and held is not None:
            prev = self.seen_faction.get(zone_id)
            m = float(minute if minute is not None else self.minute)
            # a louder look overrides a quieter rumour; a newer look overrides an older one of the same weight
            if prev is None or float(eta) >= 0.5 * float(prev.get("eta") or 0) or m - float(prev.get("minute") or 0) > 720:
                self.seen_faction[zone_id] = {"faction": str(faction), "minute": round(m, 3), "eta": round(float(eta), 3), "source": source}
        readings = {}
        for r, v in (("ours", ours), ("held", held), ("strength", strength), ("threat", threat)):
            if v is not None:
                readings[f"obs_{zone_id}_{r}"] = max(0.0, min(1.0, float(v)))
        if readings:
            self.observe(readings, eta, source=source, minute=minute)

    def observe_question(self, question: str, *, toward: Optional[str], strength: float, source: str, minute: Optional[float] = None) -> None:
        """A distinguishing event pushes toward a pole (toward=reading id); a renewing event
        (toward=None) pulls toward the open centre. eta is the event's strength."""
        spec = QUESTIONS[question]
        if toward is None:
            value = 0.5
            self.pushes[question]["renew"] += float(strength)
        elif toward == spec["pole_0"]:
            value = 1.0
            self.pushes[question]["pole_0"] += float(strength)
        elif toward == spec["pole_1"]:
            value = 0.0
            self.pushes[question]["pole_1"] += float(strength)
        else:
            return
        self.observe({f"obs_company_{question}": value}, max(0.0, min(1.0, float(strength))), source=source, minute=minute)

    def observe_draw(self, hero_id: str, *, value: float, eta: float, source: str, minute: Optional[float] = None) -> None:
        """Word of a hero: value 1.0 = they are near / heard of; eta = how loud the word is."""
        c = self.host.engine.field.clusters.get(f"hero:{hero_id}")
        if c is None or eta <= 0:
            return
        try:
            c.role_bloch(DRAW_ROLE)      # a field saved before draw existed has no such role: skip
        except Exception:
            return
        if True:
            self.observe({f"obs_hero_{hero_id}_{DRAW_ROLE}": max(0.0, min(1.0, float(value)))}, max(0.0, min(1.0, float(eta))),
                         source=source, minute=minute)

    def draws(self) -> Dict[str, float]:
        """{heroId: draw in [0, 1]}; 0.5 = nobody has heard. A field saved before draw existed reads 0.5."""
        out = {}
        for hid in hero_ids(self.workspace):
            c = self.host.engine.field.clusters.get(f"hero:{hid}")
            try:
                z = float(c.role_bloch(DRAW_ROLE)[2]) if c is not None else 0.0
            except Exception:
                z = 0.0
            out[hid] = round((z + 1.0) / 2.0, 4)
        return out

    # -- readout
    def bloch(self, node: str, role: str) -> Tuple[float, float, float]:
        c = self.host.engine.field.clusters.get(node)
        if c is None:
            return (0.0, 0.0, 0.0)
        b = c.role_bloch(role)
        return (float(b[0]), float(b[1]), float(b[2]))

    def question_status(self, question: str, x: float, y: float, z: float) -> str:
        """open: not yet forced. leaning / settled: forced one way. torn: forced both
        ways with comparable weight and the vector short (mixed), i.e. the company has
        answered the question twice, differently."""
        p = self.pushes.get(question) or {}
        a, b = float(p.get("pole_0", 0)), float(p.get("pole_1", 0))
        forced = a + b
        if forced < 0.15:
            return "open"
        if forced >= 1.0 and min(a, b) >= 0.4 * max(a, b) and abs(z) < 0.35:
            return "torn"
        if abs(z) < 0.1:
            return "open"
        return "settled" if abs(z) > 0.5 else "leaning"

    def frame(self, *, stale_after_minutes: float = 720.0, dark_below: float = 0.15) -> Dict[str, Any]:
        """intel/1: what the company knows. A value nobody measured is dark, never zero."""
        now_m = self.minute
        beliefs = self.host.beliefs()
        nodes = []
        for key, b in beliefs.items():
            node, role = key.split(".", 1) if "." in key else (key, "")
            if node.startswith("_") or role.startswith("_"):
                continue
            seen = self.last_seen.get(key)
            age = (now_m - float(seen["minute"])) if seen else None
            if seen is None or b.confidence < dark_below:
                state = "dark"
            elif age is not None and age > stale_after_minutes:
                state = "stale"
            else:
                state = "current"
            row = {"id": key, "node": node, "role": role,
                   "value": None if state == "dark" else round(b.value, 4),
                   "confidence": round(b.confidence, 4),
                   "state": state,
                   "age_min": None if age is None else round(age, 1),
                   "source": (seen or {}).get("source"),
                   "eta": (seen or {}).get("eta")}
            if node in self.zone_meta:
                row["label"] = self.zone_meta[node].get("label")
                row["mapId"] = self.zone_meta[node].get("mapId")
                if role == "held" and state != "dark":
                    sf = self.seen_faction.get(node)
                    if sf:
                        row["faction"] = sf.get("faction")
                        row["factionSeenMinute"] = sf.get("minute")
            nodes.append(row)
        questions = []
        for q, spec in QUESTIONS.items():
            x, y, z = self.bloch("company", q)
            r = math.sqrt(x * x + y * y + z * z)
            lean = spec["pole_0"] if z > 0.1 else (spec["pole_1"] if z < -0.1 else None)
            questions.append({"id": q, "icon": spec["icon"], "question": spec["question"], "pair": list(spec["pair"]),
                              "pole_0": spec["pole_0"], "pole_1": spec["pole_1"],
                              "bloch": [round(x, 4), round(y, 4), round(z, 4)], "radius": round(r, 4),
                              "lean": lean, "status": self.question_status(q, x, y, z), "pushes": {k: round(v, 3) for k, v in self.pushes[q].items()}})
        return {"schema": SCHEMA, "subject": "the company's comprehension of Verdance",
                "as_of_minute": round(now_m, 2), "stale_after_minutes": stale_after_minutes,
                "law": "a value nobody measured is null and renders dark, never zero",
                "producer": {"name": "umwelt_world_v1", "kind": "engine", "field_hash": self.host.field_canon_hash()},
                "questions": questions, "nodes": nodes}

    def zone_summary(self, zone_id: str) -> Dict[str, Any]:
        out = {}
        for r in ZONE_ROLES:
            x, y, z = self.bloch(zone_id, r)
            out[r] = {"value": round((z + 1) / 2, 3), "conf": round(math.sqrt(x * x + y * y + z * z), 3)}
        return out

    def save(self, path: Path) -> None:
        self.host.save(str(path))
        Path(str(path) + ".seen.json").write_text(json.dumps({"minute": self.minute, "last_seen": self.last_seen, "pushes": self.pushes, "seen_faction": self.seen_faction}, indent=1), encoding="utf-8")

    def load(self, path: Path) -> None:
        self.host.load(str(path))
        meta = Path(str(path) + ".seen.json")
        if meta.exists():
            d = json.loads(meta.read_text(encoding="utf-8"))
            self.last_seen = d.get("last_seen") or {}
            self.seen_faction = d.get("seen_faction") or {}
            self.pushes = d.get("pushes") or self.pushes
            # The engine pickle restores the field; the host's clock is ours to restore,
            # or every reload would start the fog again from minute zero.
            try:
                self.host._t = minute_to_time(float(d.get("minute") or 0.0))
            except Exception:
                pass


def main() -> int:
    ws = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    spec = build_spec(ws)
    print(f"{spec.name}: {len(spec.nodes)} nodes, {len(spec.bridges)} bridges, {len(spec.bindings)} bindings, {len(spec.drivers)} drivers")
    return 0


# Concrete instance for `python -m umwelt.spec.validate verdance.belief.world:VERDANCE_SPEC`
try:
    VERDANCE_SPEC = build_spec(ROOT)
except Exception:  # pragma: no cover - validator convenience only
    VERDANCE_SPEC = None


if __name__ == "__main__":
    raise SystemExit(main())
