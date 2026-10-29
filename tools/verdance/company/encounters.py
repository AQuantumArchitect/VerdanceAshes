#!/usr/bin/env python3
"""Who the company is likely to meet, and where: Verdance on umwelt.foresight.encounter.

Wild heroes no longer sit at one fixed home each. Every time the next sortie is made, the
encounter field places them, from:

  the bond web      support_web.json, typed by polarity and deepened by bond points earned
                    together (state.attachments.pairBonds). A hero bound to someone in the
                    company is drawn toward it: allies onto ground the company believes is
                    its own, rivals and tensions onto ground it believes is disputed;
  the draw          the company's belief that someone is near, held in the Umwelt field
                    (verdance.belief.world, role "draw") and spread along the same bond web by
                    the engine. Homecoming feeds it (a hero who dropped carries word of the
                    people bound to them) and writes the readout to state["encounterBelief"];
  the ground        each zone's character on the hero axes (map_umwelt pressure + zone delta,
                    plus water), and what the company believes about it (ours / disputed / theirs);
  the mood          the company's six questions, read onto the hero axes;
  haunts            the authored homes (DEFAULT_HOMES) as a soft prior, never a cage.

Anchored heroes keep their authored place: the constructor-gated recruits (assist_fortify, a
stash to retrieve, a capture), builders, factory heroes, and heroes that are buildings.

When Umwelt lacks the encounter module (an older clone), every function here returns None and
the campaign keeps the fixed homes (VA_ENCOUNTER_SKIP).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, clamp, load_json

ROOT = WORKSPACE_ROOT
AXES = ["energy", "offense", "mobility", "sight", "pad", "craft", "heat", "fog", "sky", "ledger", "water"]
WATER_TAGS = {"amphibious", "hover", "seaplane", "naval"}
ANCHOR_RECRUITS = {"retrieve_stash", "assist_fortify", "capture"}
OUR_FACTION = "ashwalkers"
# Chassis whose build power only makes more of themselves: not builders (the Infestor).
ONLY_BUILDS_ITSELF = {"leginfestor", "va_infestor"}   # prints Infestors (and Goblins): not a builder
# Who is met where is parametric (owner call, 2026-10-27): data/story/encounter_rules.json holds the
# weights (how hard a home zone pulls, how much a marked zone draws, how many a sortie meets) and the
# one hard rule, the builder at the Rock Jungle's entrance.
RULES_REL = Path("data") / "story" / "encounter_rules.json"
_RULES_DEFAULT = {"perSortie": 2, "markedGround": {"drawBoost": 4.0},
                  "homeZone": {"doesNotWalk": "fixed", "default": 1.0, "homeMapHaunt": 2.4}, "entranceBuilder": {},
                  "meetingStance": {"bias": 0.6, "biasLate": 0.2, "rampFrom": 2, "rampTo": 9, "softness": 0.25},
                  "presence": {"relation": 2.5, "ally": 3.5, "adversary": 2.0}, "fieldFit": {"weight": 0.0}}
ALLY_POLARITY = {"bond", "attract", "sibling", "mentor", "mirror"}
ADVERSARY_POLARITY = {"rivalry", "tension", "friction"}
# Recruit kinds that keep their own way of being met (the constructor-gated ones, a stash).
KEEP_MEETING = {"retrieve_stash", "assist_fortify", "capture"}


def rules(workspace: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(workspace or ROOT) / RULES_REL
    data = load_json(p) if p.exists() else {}
    out = dict(_RULES_DEFAULT)
    out.update({k: v for k, v in (data or {}).items() if k in _RULES_DEFAULT})
    return out


def stance_toward(hid: str, state: Dict[str, Any], workspace: Optional[Path] = None) -> Tuple[float, List[str]]:
    """How a wild hero stands toward the company now: + bonded, - tension. The sum over the bond web's
    edges between them and everyone in the company (support_web.json; an authored edge 1.0, a derived
    one half its score), each deepened by bond points the pair has earned together. Plain Python, so it
    holds with or without Umwelt's encounter module."""
    ws = Path(workspace or ROOT)
    present = set(present_heroes(state))
    bonds = (state.get("attachments") or {}).get("pairBonds") or {}
    score, why = 0.0, []
    for e in _story(ws, "support_web.json").get("edges") or []:
        a, b, pol = str(e.get("a") or ""), str(e.get("b") or ""), str(e.get("polarity") or "")
        if hid not in (a, b):
            continue
        other = b if a == hid else a
        if other not in present:
            continue
        sign = 1.0 if pol in ALLY_POLARITY else (-1.0 if pol in ADVERSARY_POLARITY else 0.0)
        if not sign:
            continue
        w = 1.0 if e.get("authored") else 0.5 * float(e.get("score") or 0.5)
        pts = float((bonds.get("__".join(sorted((a, b)))) or {}).get("points") or 0.0)
        w *= 1.0 + min(1.0, pts / 55.0)
        score += sign * w
        why.append(f"{pol} with {other}")
    return round(score, 3), why


def lateness(state: Dict[str, Any], workspace: Optional[Path] = None) -> float:
    """0 early in the campaign, 1 late: a straight ramp over the missions, no step."""
    st = rules(workspace).get("meetingStance") or {}
    lo, hi = float(st.get("rampFrom", 2)), float(st.get("rampTo", 9))
    m = float(state.get("missionNumber", 1) or 1)
    return 0.0 if hi <= lo else clamp((m - lo) / (hi - lo), 0.0, 1.0)


def p_hostile(score: float, state: Dict[str, Any], workspace: Optional[Path] = None) -> float:
    """The chance a met hero turns up alive and against us: a logistic in their stance toward the
    party, no thresholds. Owner call, 2026-10-28: Umwelt-style continuous parameters.

        p = 1 / (1 + exp((stance + bias) / softness))

    bias slides from meetingStance.bias to biasLate as the campaign goes on (lateness). With the
    defaults a hero with one authored tension in the party is ~83% hostile early and ~96% late; a
    stranger ~8% early and ~31% late; a bonded hero almost never."""
    import math
    st = rules(workspace).get("meetingStance") or {}
    t = lateness(state, workspace)
    bias = (1.0 - t) * float(st.get("bias", 0.6)) + t * float(st.get("biasLate", 0.2))
    soft = max(1e-3, float(st.get("softness", 0.25)))
    x = (float(score) + bias) / soft
    return 1.0 / (1.0 + math.exp(max(-60.0, min(60.0, x))))


def roll(state: Dict[str, Any], *parts: Any) -> float:
    """A seeded uniform in [0, 1) for this campaign, mission and parts: the same sortie rolls the same."""
    import hashlib
    return int(hashlib.md5(seed_for(state, *parts).encode()).hexdigest()[:8], 16) / float(0x100000000)


def meeting(hid: str, state: Dict[str, Any], workspace: Optional[Path] = None, map_id: Any = "") -> Dict[str, Any]:
    """How this hero would turn up on this map this sortie: {score, pHostile, roll, kind, reasons}."""
    score, why = stance_toward(hid, state, workspace)
    p = p_hostile(score, state, workspace)
    u = roll(state, map_id, hid, "stance")
    return {"score": score, "pHostile": round(p, 3), "roll": round(u, 3), "kind": "hostile" if u < p else "authored",
            "reasons": why[:4]}


def apply_meeting_stance(rows: List[Dict[str, Any]], state: Dict[str, Any], workspace: Optional[Path] = None,
                         map_id: Any = "") -> List[Dict[str, Any]]:
    """Stamp each met hero with how they turn up. A seeded roll under pHostile (the logistic in their
    stance, p_hostile) spawns them alive on the enemy team (recruitMode 'hostile', spawnAsWreck False):
    put them down and raise the wreck to sign them on. Otherwise they come the way their recruit entry
    says (a wreck, for most). Constructor-gated recruits, the entrance builder, the heroes who join by
    winning (requiresVictory) and heroes who are buildings keep their own way."""
    for row in rows:
        mode = str(row.get("recruitMode") or "wreck_rez")
        if mode in KEEP_MEETING or row.get("entrance") or row.get("requiresVictory") or row.get("wreckUnitDef"):
            continue
        if (row.get("encounter") or {}).get("anchored"):
            continue
        m = meeting(str(row.get("heroId")), state, workspace, map_id or row.get("mapId") or "")
        row["stance"] = m
        if m["kind"] == "hostile":
            row["recruitMode"] = "hostile"
            row["spawnAsWreck"] = False
    return rows


def per_sortie(workspace: Optional[Path] = None) -> int:
    return max(0, int(rules(workspace).get("perSortie") or 2))

# The company's questions on the hero axes: +1 = leaning toward pole_0, -1 = toward pole_1.
# (axis, weight when the company leans pole_0; the opposite lean gives the negative)
MOOD_AXES = {
    "whose_war": {"offense": 0.5, "ledger": 0.3, "mobility": -0.3},          # sovereign vs auxiliary
    "home_or_hospital": {"pad": 0.5, "craft": 0.3, "heat": -0.3},           # rooted vs bleeding
    "whose_paper": {"ledger": 0.5, "craft": 0.2},                           # sovereign vs indebted
    "go_back": {"pad": 0.3, "sight": 0.4, "fog": -0.3},                     # rooted vs haunted
    "pressure": {"offense": 0.4, "sky": 0.3, "fog": -0.4, "mobility": -0.2},  # armada falling vs hunted
    "creditor": {"mobility": 0.2, "ledger": -0.4},                          # auxiliary vs indebted
}

_SKIP_WARNED = False


def _module():
    """umwelt.foresight.encounter, or None (warn once)."""
    global _SKIP_WARNED
    try:
        from verdance.belief import world as W
        W._umwelt()                      # puts the umwelt clone / vendored snapshot on sys.path
        from umwelt.foresight import encounter as E  # noqa
        return E
    except Exception as exc:  # noqa: BLE001
        if not _SKIP_WARNED:
            _SKIP_WARNED = True
            print(f"VA_ENCOUNTER_SKIP umwelt.foresight.encounter unavailable ({type(exc).__name__}: {exc}); "
                  "wild heroes keep their fixed homes. Pull the Umwelt clone to enable roaming.", file=sys.stderr)
        return None


def available() -> bool:
    return _module() is not None


# ----------------------------------------------------------------------------- the cast

def _story(workspace: Path, name: str) -> Dict[str, Any]:
    p = Path(workspace) / "data" / "story" / name
    return load_json(p) if p.exists() else {}


ANCHOR_LABELS = {"assist_fortify": "found where a constructor is needed", "retrieve_stash": "a stash to retrieve",
                 "capture": "a capture", "factory": "a factory hero", "doesNotWalk": "does not walk",
                 "builder": "a builder"}


def anchor_key(hid: str, pack: Dict[str, Any], roster_row: Dict[str, Any], chassis: Dict[str, Any]) -> Optional[str]:
    """Why a hero is tied to their authored home (a key of encounter_rules.homeZone), or None."""
    from verdance.company.company import WRECK_SEED_PROXY
    recruit = (roster_row or {}).get("recruit") or {}
    kind = str(recruit.get("type") or "")
    if kind in ANCHOR_RECRUITS:
        return kind
    if pack.get("factory"):
        return "factory"
    unit = str(pack.get("unitDef") or "")
    if unit in WRECK_SEED_PROXY:
        return "doesNotWalk"
    if is_builder(pack, chassis):
        return "builder"
    return None


def anchor_reason(hid: str, pack: Dict[str, Any], roster_row: Dict[str, Any], chassis: Dict[str, Any]) -> Optional[str]:
    """Why a hero keeps (or leans to) an authored place, in words (None = they roam)."""
    key = anchor_key(hid, pack, roster_row, chassis)
    return ANCHOR_LABELS.get(key) if key else None


def is_builder(pack: Dict[str, Any], chassis: Dict[str, Any] = None) -> bool:
    """A builder seeds a base: economy, factories, constructors (crew_packs baseSeeder). Owner call,
    2026-10-28: build power alone is not a builder. Ketha's rez bots, nano towers, a defence-only
    constructor (Sister Lumen) and the Infestor all have build power and are not builders."""
    return bool(pack.get("baseSeeder"))


def eco_builders(workspace: Optional[Path] = None) -> List[str]:
    """The base-seeders (crew_packs baseSeeder: they can raise economy, factories and constructors): who can
    wait at the jungle's entrance."""
    packs = _story(Path(workspace or ROOT), "crew_packs.json")
    return sorted(h for h, p in (packs.get("heroes") or {}).items() if isinstance(p, dict) and is_builder(p))


def _traits(hid: str, umwelt_rows: Dict[str, Dict[str, Any]], pack: Dict[str, Any]) -> Dict[str, float]:
    ax = dict((umwelt_rows.get(hid) or {}).get("axes") or {})
    t = {a: float(ax.get(a, 0.0)) for a in AXES if a != "water"}
    tags = {str(x) for x in pack.get("tags") or []}
    t["water"] = 0.8 if tags & WATER_TAGS else 0.0
    return t


def _entry_home(entry: Any) -> Optional[Tuple[str, str]]:
    """(mapId, zoneId) the campaign's own field pool remembers for this hero, if any."""
    if not isinstance(entry, dict):
        return None
    recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
    home = entry.get("home") if isinstance(entry.get("home"), list) else []
    mid = str(recruit.get("mapId") or (home[0] if home else "") or "")
    zid = str(recruit.get("zoneId") or (home[1] if len(home) > 1 else "") or "")
    return (mid, zid) if mid and zid else None


def _home(hid: str) -> Optional[Tuple[str, str]]:
    from verdance.company.company import DEFAULT_HOMES
    h = DEFAULT_HOMES.get(hid)
    return (h[0], h[1]) if h and len(h) > 1 else None


# ----------------------------------------------------------------------------- the ground

def _places(E, state: Dict[str, Any], workspace: Path) -> List[Any]:
    from verdance.world.map_umwelt import load_map_umwelt, pressure_for
    graph = load_json(Path(workspace) / "data" / "zone_maps" / "world_zone_graph.v1.json")
    mdoc = load_map_umwelt(Path(workspace) / "data" / "story" / "map_umwelt.json")
    stance_belief = ((state.get("encounterBelief") or {}).get("ground") or {})
    out = []
    for z in graph.get("nodes") or []:
        zid, mid = str(z.get("zoneId") or ""), str(z.get("mapId") or "")
        if not zid or not mid:
            continue
        feats = {a: float(v) for a, v in pressure_for(mid, zid, doc=mdoc).items()}
        ev = z.get("evidence") or {}
        feats["water"] = clamp(float(ev.get("water") or 0.0) * 2.0)
        b = stance_belief.get(zid)
        if isinstance(b, dict):
            stance, contest, known = float(b.get("stance", 0.0)), float(b.get("contest", 0.0)), float(b.get("known", 0.0))
        else:   # no belief yet: what the campaign's own memory of the ground says, held loosely
            zm = ((state.get("zoneMemory") or {}).get(mid) or {}).get(zid) or {}
            ab = zm.get("abstract") or {} if isinstance(zm, dict) else {}
            ctrl = str((zm or {}).get("controllingFaction") or ab.get("control") or "neutral").lower() if isinstance(zm, dict) else "neutral"
            stance = 1.0 if ctrl == OUR_FACTION else (0.0 if ctrl in ("", "neutral", "none", "contested") else -0.7)
            contest = clamp(float(ab.get("instability") or 0.0) + (0.4 if ctrl == "contested" else 0.0))
            known = 0.4
        out.append(E.Place(zid, mid, features=feats, stance=stance, contest=contest, known=known, label=str(z.get("label") or zid)))
    return out


def ground_belief(frame: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """{zoneId: {stance, contest, known}} from the company's belief frame (intel/1), dark zones omitted."""
    rows: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for n in frame.get("nodes") or []:
        if n.get("state") == "dark" or n.get("value") is None or n.get("role") not in ("ours", "held", "threat"):
            continue
        rows.setdefault(str(n["node"]), {})[n["role"]] = n
    out = {}
    for zid, r in rows.items():
        ours = r.get("ours")
        held = r.get("held")
        threat = r.get("threat")
        o = float(ours["value"]) if ours else 0.0
        h = float(held["value"]) if held else 0.0
        stance = clamp(o * 2.0 - 1.0, -1.0, 1.0) if o > 0.5 else -clamp(h * (1.0 - o) * 1.4)
        conf = max(float((ours or {}).get("confidence") or 0), float((held or {}).get("confidence") or 0))
        out[zid] = {"stance": round(stance, 3), "contest": round(float(threat["value"]) if threat else 0.0, 3), "known": round(clamp(conf), 3)}
    return out


def mood_from_frame(frame: Dict[str, Any]) -> Dict[str, float]:
    mood: Dict[str, float] = {}
    for q in frame.get("questions") or []:
        z = float((q.get("bloch") or [0, 0, 0])[2])
        for axis, w in (MOOD_AXES.get(str(q.get("id"))) or {}).items():
            mood[axis] = mood.get(axis, 0.0) + w * z
    return {a: round(v, 4) for a, v in mood.items()}


# ----------------------------------------------------------------------------- the field

def _aura_reaches(aura: Dict[str, Any], tags: Iterable[str], axes: Dict[str, float]) -> bool:
    """Would this aura reach a hero with these tags and axes? Only targeted auras count: one that
    reaches everyone (match.any), a unit kind or the hero alone says nothing about who fits."""
    m = aura.get("match") or {}
    if not m.get("tags") and not m.get("axes"):
        return False
    if m.get("tags") and not set(m["tags"]) & set(tags):
        return False
    return all(float(axes.get(a, 0.0)) >= float(v) for a, v in (m.get("axes") or {}).items())


def field_fit(a: str, b: str, fx: Dict[str, Any], axes: Dict[str, Dict[str, float]]) -> int:
    """How many of the two heroes' auras reach the other (0, 1 or 2): field effects v2 tags and axes."""
    n = 0
    for x, y in ((a, b), (b, a)):
        hx, hy = fx.get(x) or {}, fx.get(y) or {}
        if any(_aura_reaches(au, hy.get("tags") or [], axes.get(y) or {}) for au in hx.get("auras") or []):
            n += 1
    return n


def _relations(E, state: Dict[str, Any], workspace: Path) -> List[Any]:
    web = _story(workspace, "support_web.json")
    bonds = (state.get("attachments") or {}).get("pairBonds") or {}
    out = []
    authored = set()
    for e in web.get("edges") or []:
        if e.get("authored"):
            authored.add(frozenset((str(e.get("a")), str(e.get("b")))))
    # Field fit (2026-10-29): a wild hero the company's auras would reach, or whose aura would reach
    # the company, is a little likelier to turn up. Weak next to a written tie, so bonds stay the
    # default meeting; it decides which strangers come, not how many. Only for pairs with no
    # written tie, and only toward who is with the company now.
    fit_w = float((rules(workspace).get("fieldFit") or {}).get("weight", 0.0))
    if fit_w > 0:
        fx = _story(workspace, "field_effects.json").get("heroes") or {}
        axes = {str(h.get("heroId")): h.get("axes") or {} for h in _story(workspace, "hero_umwelt.json").get("heroes") or []}
        present = set(present_heroes(state))
        for p in sorted(present):
            for c in sorted(fx):
                if c in present or frozenset((p, c)) in authored:
                    continue
                n = field_fit(p, c, fx, axes)
                if n:
                    out.append(E.Relation(p, c, "field_fit", weight=fit_w * n))
    for e in web.get("edges") or []:
        a, b, pol = str(e.get("a") or ""), str(e.get("b") or ""), str(e.get("polarity") or "")
        if not a or not b or a == b:
            continue
        w = 1.0 if e.get("authored") else 0.5 * float(e.get("score") or 0.5)
        pts = float((bonds.get("__".join(sorted((a, b)))) or {}).get("points") or 0.0)
        w *= 1.0 + min(1.0, pts / 55.0)          # rank A (55 points) doubles the pull
        out.append(E.Relation(a, b, pol, weight=w))
    return out


def present_heroes(state: Dict[str, Any]) -> List[str]:
    """Who is with the company now (core, band, joined later), the dead excluded."""
    company = state.get("company") or {}
    ids = [str(x) for k in ("core", "band", "joinedLater") for x in (company.get(k) or [])]
    dead = set()
    for h in ((state.get("roster") or {}).get("heroes") or []):
        if isinstance(h, dict) and str(h.get("status") or "") in ("dead", "fallen", "lost"):
            dead.add(str(h.get("heroId")))
    return sorted({h for h in ids if h and h not in dead})


def _weights(E, workspace: Path):
    """The encounter field's weights. presence (encounter_rules.json): how much a relation to someone in
    the company raises the chance of meeting, per side. Bonds are the default meeting, rivals the accent,
    strangers uncommon (ally > adversary, both strong). An older Umwelt without the per-side weights
    gets the shared one."""
    pr = rules(workspace).get("presence") or {}
    rel = float(pr.get("relation", 2.5))
    try:
        return E.Weights(presence_relation=rel, presence_ally=float(pr.get("ally", rel)),
                         presence_adversary=float(pr.get("adversary", rel)))
    except TypeError:
        return E.Weights(presence_relation=rel)


def build(state: Dict[str, Any], workspace: Optional[Path] = None):
    """(EncounterField, context) or None when Umwelt lacks the module."""
    E = _module()
    if E is None:
        return None
    ws = Path(workspace or ROOT)
    if not (ws / "data" / "zone_maps" / "world_zone_graph.v1.json").exists() or not (ws / "data" / "story" / "map_umwelt.json").exists():
        return None                      # a workspace without the world's ground: keep the fixed homes
    packs = _story(ws, "crew_packs.json")
    roster = {str(h.get("heroId")): h for h in _story(ws, "hero_roster.json").get("heroes") or [] if isinstance(h, dict)}
    um = {str(h.get("heroId")): h for h in _story(ws, "hero_umwelt.json").get("heroes") or [] if isinstance(h, dict)}
    chassis = packs.get("chassis") or {}
    places = _places(E, state, ws)
    place_ids = {p.id for p in places}
    entities, anchors = [], {}
    pool = state.get("fieldPool") or {}
    present = present_heroes(state)
    home_w = rules(ws).get("homeZone") or {}
    for hid, pack in (packs.get("heroes") or {}).items():
        if str(pack.get("role") or "band") != "band":
            continue
        home = _entry_home(pool.get(hid)) or _home(hid)
        key = anchor_key(hid, pack, roster.get(hid) or {}, chassis)
        weight = home_w.get(key, home_w.get("default", 1.0)) if key else home_w.get("default", 1.0)
        anchored_at = None
        if key and home and home[1] in place_ids:
            anchors[hid] = ANCHOR_LABELS.get(key, key)
            if weight == "fixed":
                anchored_at = home[1]          # cannot be met anywhere else (does not walk)
        haunts = {}
        if home and home[1] in place_ids:
            haunts[home[1]] = 1.0 if weight == "fixed" else float(weight)
            haunts[home[0]] = float(home_w.get("homeMapHaunt", 2.4))
        entities.append(E.Entity(hid, traits=_traits(hid, um, pack), haunts=haunts, anchored_at=anchored_at,
                                 label=str(pack.get("name") or hid)))
    field = E.EncounterField(entities, places, _relations(E, state, ws), weights=_weights(E, ws))
    belief = state.get("encounterBelief") or {}
    ctx = {"present": present, "draw": relative_draw(belief.get("draw") or {}, _wild_ids(state)),
           "mood": dict(belief.get("mood") or {}),
           "anchors": anchors, "labels": {p.id: p.label for p in places}, "maps": {p.id: p.region for p in places}}
    return field, ctx


def relative_draw(draw: Dict[str, float], among: Iterable[str]) -> Dict[str, float]:
    """The draw as standing among the wild: 0.5 + (draw - the median wild draw). Word spreads
    along a dense bond web and lifts everyone over a long campaign; who is LOUDER than the rest
    is what decides a meeting, so the encounter field reads the draw centred on the crowd."""
    vals = sorted(float(draw[h]) for h in among if h in draw)
    if not vals:
        return {}
    mid = vals[len(vals) // 2] if len(vals) % 2 else 0.5 * (vals[len(vals) // 2 - 1] + vals[len(vals) // 2])
    return {h: round(clamp(0.5 + float(v) - mid), 4) for h, v in draw.items()}


def _wild_ids(state: Dict[str, Any]) -> List[str]:
    return sorted(str(h) for h, e in (state.get("fieldPool") or {}).items() if isinstance(e, dict) and str(e.get("status") or "") == "wild")


def seed_for(state: Dict[str, Any], *extra: Any) -> str:
    return "|".join(str(x) for x in (state.get("campaignId") or "verdance_ashes", state.get("seed") or 0,
                                       int(state.get("missionNumber") or 1)) + tuple(extra))


def refresh_whereabouts(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Write fieldPool[hid].roam = the company's best belief of where each wild hero is now
    ({mapId, zoneId, label, p, presence, anchored, reasons}). None when Umwelt lacks the module."""
    built = build(state, workspace)
    if built is None:
        return None
    field, ctx = built
    wild = _wild_ids(state)
    survey = field.survey(present=ctx["present"], draw=ctx["draw"], mood=ctx["mood"], candidates=wild)
    pool = state.get("fieldPool") or {}
    for hid in wild:
        row = survey.get(hid)
        if not row:
            pool[hid].pop("roam", None)
            continue
        zid = row["where"]
        reasons = list(row["reasons"])
        if hid in ctx["anchors"]:
            reasons = [ctx["anchors"][hid]] + [r for r in reasons if r != "anchored here"]
        pool[hid]["roam"] = {"mapId": ctx["maps"].get(zid), "zoneId": zid, "label": ctx["labels"].get(zid, zid),
                             "p": row["p"], "presence": row["presence"], "anchored": row["anchored"],
                             "regions": dict(list(row["regions"].items())[:3]), "reasons": reasons[:5],
                             "asOfMission": int(state.get("missionNumber") or 1)}
    return {"placed": sum(1 for h in wild if "roam" in pool.get(h, {})), "wild": len(wild)}


def entrance_builder(state: Dict[str, Any], map_id: str, workspace: Optional[Path] = None,
                     draw: Optional[Dict[str, float]] = None) -> Optional[Tuple[str, str]]:
    """The one hard rule (encounter_rules.entranceBuilder): on its map, a builder hero waits at the
    entrance. The preferred one (the Consul) while still wild; else a wild eco builder drawn by the
    company's draw, seeded like the rest of the sortie. None off that map or when none is left."""
    rule = rules(workspace).get("entranceBuilder") or {}
    if not rule.get("mapId") or str(map_id) != str(rule["mapId"]) or not rule.get("zoneId"):
        return None
    wild = set(_wild_ids(state))
    present = set(present_heroes(state))
    pool = [h for h in eco_builders(workspace) if h in wild and h not in present]
    if not pool:
        return None
    prefer = str(rule.get("prefer") or "")
    if prefer in pool:
        return prefer, str(rule["zoneId"])
    import hashlib
    weights = [(h, max(0.05, float((draw or {}).get(h, 0.5)))) for h in pool]
    roll = int(hashlib.md5(seed_for(state, map_id, "entrance").encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    total = sum(w for _, w in weights)
    acc = 0.0
    for h, w in weights:
        acc += w / total
        if roll <= acc:
            return h, str(rule["zoneId"])
    return weights[-1][0], str(rule["zoneId"])


def _marked_draw(field, ctx, pool: Dict[str, Any], map_id: str, marked: List[str], boost: float) -> Dict[str, float]:
    """The draw with the company's attention on it: a wild hero believed on a marked zone of this map
    is `boost` times likelier to be met. A weight, not a seat."""
    draw = dict(ctx["draw"])
    if not marked or boost == 1.0:
        return draw
    for hid, ent in field.entities.items():
        roam = (pool.get(hid) or {}).get("roam") or {}
        believed = ent.anchored_at or roam.get("zoneId") or next((z for z, w in ent.haunts.items() if z in ctx["maps"] and w >= 1.0), None)
        if believed in marked and ctx["maps"].get(believed) == str(map_id):
            draw[hid] = float(draw.get(hid, 0.5)) * boost
    return draw


def _meet(field, ctx, state: Dict[str, Any], map_id: str, k: int, marked: List[str], workspace) -> List[Dict[str, Any]]:
    """Who is met on this map: the entrance builder (if the rule applies), then the seeded draw."""
    r = rules(workspace)
    wild = _wild_ids(state)
    draw = _marked_draw(field, ctx, state.get("fieldPool") or {}, map_id, marked, float((r.get("markedGround") or {}).get("drawBoost", 1.0)))
    out: List[Dict[str, Any]] = []
    gate = entrance_builder(state, map_id, workspace, draw) if k > 0 else None
    if gate:
        h, z = gate
        out.append({"heroId": h, "zoneId": z, "label": ctx["labels"].get(z, z), "score": 99.0, "p": 1.0,
                    "anchored": True, "reasons": ["a builder waits at the jungle's entrance"]})
    taken = {o["heroId"] for o in out}
    picks = field.sample(str(map_id), k - len(out), seed=seed_for(state, map_id), present=ctx["present"],
                         draw=draw, mood=ctx["mood"], candidates=[h for h in wild if h not in taken]) if k > len(out) else []
    for e in picks:
        reasons = list(e.reasons)
        if e.entity in ctx["anchors"]:
            reasons = [ctx["anchors"][e.entity]] + [r for r in reasons if r != "anchored here"]
        if e.place in marked:
            reasons = ["we marked this ground"] + reasons
        out.append({"heroId": e.entity, "zoneId": e.place, "label": ctx["labels"].get(e.place, e.place), "score": e.score,
                    "p": e.p_place, "anchored": e.anchored, "reasons": reasons[:5]})
    return out


def encounters_for_map(state: Dict[str, Any], map_id: str, *, workspace: Optional[Path] = None, limit: Optional[int] = None,
                       marked_zone_ids: Optional[Iterable[str]] = None) -> Optional[List[Dict[str, Any]]]:
    """Who the company meets on this map this sortie: [{heroId, zoneId, score, p, anchored, reasons}],
    seeded by campaign + mission + map. Marked zones are the company's attention. None = no module."""
    built = build(state, workspace)
    if built is None:
        return None
    field, ctx = built
    marked = [str(z) for z in (marked_zone_ids or []) if z]
    k = per_sortie(workspace) if limit is None else int(limit)
    return _meet(field, ctx, state, map_id, k, marked, workspace)


def draws_by_map(state: Dict[str, Any], workspace: Optional[Path] = None, *, depth: int = 5) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """{mapId: [{heroId, zoneId, label}]} the seeded unmarked draw on every map, `depth` deep (one
    field build for all maps). The hub's recruit preview reads it; marked heroes seat first."""
    built = build(state, workspace)
    if built is None:
        return None
    field, ctx = built
    out = {}
    for mid in sorted(set(ctx["maps"].values())):
        out[mid] = [{"heroId": e["heroId"], "zoneId": e["zoneId"], "label": e["label"]}
                    for e in _meet(field, ctx, state, mid, depth, [], workspace)]
    return out


# ----------------------------------------------------------------------------- homecoming

def draw_observations(state: Dict[str, Any], result: Dict[str, Any], workspace: Optional[Path] = None) -> List[Tuple[str, float, float, str]]:
    """[(heroId, value, eta, source)] word of the wild this Drop carried home: every hero on the
    field carries word of the wild heroes bound to them; one who joined brings louder word."""
    ws = Path(workspace or ROOT)
    from verdance.belief import manifest
    on_field = set(manifest.dropped(result) or []) | {str(h) for h in result.get("recruitedHeroIds") or [] if h}
    if not on_field:
        on_field = set(present_heroes(state))
    joined = {str(h) for h in result.get("recruitedHeroIds") or [] if h}
    wild = set(_wild_ids(state))
    web = _story(ws, "support_web.json")
    strength = {"bond": 1.0, "attract": 1.0, "sibling": 0.9, "mentor": 0.8, "mirror": 0.6, "rivalry": 0.9, "tension": 0.7, "friction": 0.5}
    out: Dict[str, Tuple[float, str]] = {}
    for e in web.get("edges") or []:
        if not e.get("authored"):
            continue
        for carrier, other in ((e["a"], e["b"]), (e["b"], e["a"])):
            if carrier in on_field and other in wild:
                eta = 0.1 + 0.15 * strength.get(str(e.get("polarity")), 0.5) + (0.1 if carrier in joined else 0.0)
                if eta > out.get(other, (0.0, ""))[0]:
                    out[other] = (round(min(0.35, eta), 3), f"word:{carrier}")
    return [(hid, 1.0, eta, src) for hid, (eta, src) in sorted(out.items())]


def belief_snapshot(world: Any, frame: Dict[str, Any]) -> Dict[str, Any]:
    """What the encounter field reads between Drops: the draw, the ground, the mood."""
    return {"draw": world.draws(), "ground": ground_belief(frame), "mood": mood_from_frame(frame),
            "asOfMinute": frame.get("as_of_minute")}


__all__ = ["available", "build", "refresh_whereabouts", "encounters_for_map", "draw_observations",
           "belief_snapshot", "ground_belief", "mood_from_frame", "present_heroes", "anchor_reason", "anchor_key",
           "eco_builders", "entrance_builder", "per_sortie", "rules"]
