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
# The constructor-gated jungle find (owner, 2026-10-26): a Consul, or, when the Consul is already
# with the company, a Twitcher found in the same place.
CONSTRUCTOR_FIND = ("consul", "twitch")

# A hero's authored home map as a haunt: about half of their meetings happen there (measured over
# 30 seeded sorties x 7 maps on a fresh campaign), the rest wherever the bond web and the ground
# pull them. The authored home zone itself is a smaller prior on top.
HOME_MAP_HAUNT = 2.4

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


def anchor_reason(hid: str, pack: Dict[str, Any], roster_row: Dict[str, Any], chassis: Dict[str, Any]) -> Optional[str]:
    """Why a hero keeps an authored place (None = they roam)."""
    from verdance.company.company import WRECK_SEED_PROXY
    recruit = (roster_row or {}).get("recruit") or {}
    kind = str(recruit.get("type") or "")
    if kind in ANCHOR_RECRUITS:
        return {"assist_fortify": "found where a constructor is needed", "retrieve_stash": "a stash to retrieve",
                "capture": "a capture"}[kind]
    if pack.get("factory"):
        return "a factory hero"
    unit = str(pack.get("unitDef") or "")
    if unit in WRECK_SEED_PROXY:
        return "does not walk"
    if (chassis.get(unit) or {}).get("hasBuildPower") and unit not in ONLY_BUILDS_ITSELF:
        return "a builder"
    return None


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

def _relations(E, state: Dict[str, Any], workspace: Path) -> List[Any]:
    web = _story(workspace, "support_web.json")
    bonds = (state.get("attachments") or {}).get("pairBonds") or {}
    out = []
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
    first, second = CONSTRUCTOR_FIND
    find_at = _entry_home(pool.get(first)) or _home(first)
    for hid, pack in (packs.get("heroes") or {}).items():
        if str(pack.get("role") or "band") != "band":
            continue
        home = _entry_home(pool.get(hid)) or _home(hid)
        reason = anchor_reason(hid, pack, roster.get(hid) or {}, chassis)
        if hid == second and first in present and find_at:
            home, reason = find_at, f"found where a constructor is needed (the {first.capitalize()} is already with you)"
        anchored_at = None
        if reason:
            anchored_at = home[1] if home else None
            if anchored_at not in place_ids:
                anchored_at = home[1] if home and home[1] in place_ids else None
            if anchored_at:
                anchors[hid] = reason
        haunts = {}
        if home and home[1] in place_ids:
            haunts[home[1]] = 1.0
            haunts[home[0]] = HOME_MAP_HAUNT
        entities.append(E.Entity(hid, traits=_traits(hid, um, pack), haunts=haunts, anchored_at=anchored_at,
                                 label=str(pack.get("name") or hid)))
    field = E.EncounterField(entities, places, _relations(E, state, ws), weights=E.Weights(presence_relation=0.7))
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


def encounters_for_map(state: Dict[str, Any], map_id: str, *, workspace: Optional[Path] = None, limit: int = 2,
                       marked_zone_ids: Optional[Iterable[str]] = None) -> Optional[List[Dict[str, Any]]]:
    """Who the company meets on this map this sortie: [{heroId, zoneId, score, p, anchored, reasons}],
    seeded by campaign + mission + map. Marked zones are the company's attention. None = no module."""
    built = build(state, workspace)
    if built is None:
        return None
    field, ctx = built
    marked = [str(z) for z in (marked_zone_ids or []) if z]
    wild = _wild_ids(state)
    pool = state.get("fieldPool") or {}
    # Attention collapse (the hub's target click is the sortie -> character link): a wild hero the
    # company believes is on a zone it marked is met there, up to three, before the draw.
    must = []
    for hid in wild:
        if len(must) >= 3:
            break
        ent = field.entities.get(hid)
        if ent is None:
            continue
        roam = (pool.get(hid) or {}).get("roam") or {}
        believed = ent.anchored_at or roam.get("zoneId") or next((z for z, w in ent.haunts.items() if z in ctx["maps"] and w >= 1.0), None)
        if believed in marked and ctx["maps"].get(believed) == str(map_id):
            must.append((hid, believed))
    k = max(int(limit), len(must))
    taken = {h for h, _ in must}
    # The rest is the map's own draw, unmarked, so the hub can show it before the Drop
    # (company_surface "encounterDraw": the same seeded order, minus who was marked).
    picks = field.sample(str(map_id), k - len(must), seed=seed_for(state, map_id), present=ctx["present"],
                         draw=ctx["draw"], mood=ctx["mood"], candidates=[h for h in wild if h not in taken])
    out = [{"heroId": h, "zoneId": z, "label": ctx["labels"].get(z, z), "score": 99.0, "p": 1.0,
            "anchored": h in ctx["anchors"], "reasons": ["we marked this ground"]} for h, z in must]
    for e in picks:
        reasons = list(e.reasons)
        if e.entity in ctx["anchors"]:
            reasons = [ctx["anchors"][e.entity]] + [r for r in reasons if r != "anchored here"]
        out.append({"heroId": e.entity, "zoneId": e.place, "label": ctx["labels"].get(e.place, e.place), "score": e.score,
                    "p": e.p_place, "anchored": e.anchored, "reasons": reasons[:5]})
    return out


def draws_by_map(state: Dict[str, Any], workspace: Optional[Path] = None, *, depth: int = 5) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """{mapId: [{heroId, zoneId, label}]} the seeded unmarked draw on every map, `depth` deep (one
    field build for all maps). The hub's recruit preview reads it; marked heroes seat first."""
    built = build(state, workspace)
    if built is None:
        return None
    field, ctx = built
    wild = _wild_ids(state)
    out = {}
    for mid in sorted(set(ctx["maps"].values())):
        picks = field.sample(mid, depth, seed=seed_for(state, mid), present=ctx["present"], draw=ctx["draw"],
                             mood=ctx["mood"], candidates=wild)
        out[mid] = [{"heroId": e.entity, "zoneId": e.place, "label": ctx["labels"].get(e.place, e.place)} for e in picks]
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
           "belief_snapshot", "ground_belief", "mood_from_frame", "present_heroes", "anchor_reason"]
