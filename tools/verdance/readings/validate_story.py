#!/usr/bin/env python3
"""Lint the comprehension-graph content: readings, event classes, attractors, scenes, voices.

Every reference must resolve: probes to the projector's vocabulary, coherence pairs to
readings.json, event-class effects to listed pairs, attractor signatures and edges to
readings and attractors, edge scenes to attractor_scenes.json, voice lines to event
classes / attractors / readings, speakers to the codex or campaign characters, and
every {field} in a template to a field some detector or the occasions builder can fill.

Exit status 1 on any error. Warnings do not fail.

    python -m verdance.readings.validate_story
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from verdance.common import WORKSPACE_ROOT

ROOT = WORKSPACE_ROOT
from verdance.readings import readings

FIELD_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")

PROBES = {"const", "rep", "rep_inverse", "graph", "tag_rate", "verdict_rate", "commitment", "holdings_ratio",
          "holdings_count", "holdings_share_inverse", "claimed_nodes", "thread_resolved", "thread_stage",
          "thread_trust", "thread_distrust", "flag", "number", "ledger_ops", "tenebrium_low", "wounded_named",
          "dead_named", "scars_total", "home_level", "walker_locked", "front_flips", "clashes_near_held",
          "unobserved_held_maps", "belief_holdings_count", "belief_holdings_ratio", "belief_dark_share",
          "belief_threat_near_held", "intel_count", "question"}
PROBE_FIELDS = {"pct", "value", "count", "window", "a", "b", "names", "n", "m", "threshold", "source", "status"}
BEAD_FIELDS = {"map", "mapId", "ourMap", "verdict", "extraction", "extractionText", "thread", "threadTitle", "text",
               "count", "label", "toFaction", "fromFaction", "level", "hero", "heroId", "wounds", "outcome", "names", "joinedIds",
               "surprise", "believed", "found", "zonesMeasured", "eta", "source"}
SNAPSHOT_FIELDS = {"hero", "heroId", "wounds", "value", "n", "m"}
COMMON_FIELDS = {"wounded", "dead", "heldCount", "tenebrium", "atTable", "map", "mapId",
                 "armadaKnows", "armadaBlind", "armadaGhost", "armadaOfOurs", "nullmercsKnows", "nullmercsBlind", "nullmercsGhost", "nullmercsOfOurs", "cortexKnows", "cortexBlind", "cortexGhost", "cortexOfOurs"}
STANCES = {"care", "ambition", "independence", "pragmatism", "stewardship"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    errors: List[str] = []
    warnings: List[str] = []
    story = ROOT / "data" / "story"

    readings = load(story / "readings.json")
    classes = load(story / "event_classes.json")
    attractors = load(story / "attractors.json") if (story / "attractors.json").exists() else {"attractors": []}
    scenes = load(story / "attractor_scenes.json") if (story / "attractor_scenes.json").exists() else {"scenes": []}
    codex = load(story / "hero_codex.json") if (story / "hero_codex.json").exists() else {"heroes": []}
    state_path = ROOT / "state" / "campaign_state.json"
    state = load(state_path) if state_path.exists() else {}

    reading_ids = [r["id"] for r in readings["readings"]]
    if len(set(reading_ids)) != len(reading_ids):
        errors.append("readings: duplicate ids")
    pairs: Set[tuple] = set()
    for p in readings["coherencePairs"]:
        a, b = p["pair"]
        for x in (a, b):
            if x not in reading_ids:
                errors.append(f"coherencePairs: unknown reading {x!r}")
        pairs.add(tuple(sorted((a, b))))
    for r in readings["readings"]:
        if not r.get("icon"):
            warnings.append(f"reading {r['id']}: no icon")
        for ev in r["evidence"]:
            if ev.get("probe") not in PROBES:
                errors.append(f"reading {r['id']}: unknown probe {ev.get('probe')!r}")
            for f in FIELD_RE.findall(ev.get("witness") or ""):
                if f not in PROBE_FIELDS:
                    errors.append(f"reading {r['id']}: witness field {{{f}}} not produced by any probe")
        for who in ("argues", "resists"):
            if r.get(who) and r[who] not in {h["heroId"] for h in codex["heroes"]}:
                warnings.append(f"reading {r['id']}: {who}={r[who]} not in codex")

    class_ids = set()
    for c in classes["classes"]:
        class_ids.add(c["id"])
        if not c.get("icon"):
            warnings.append(f"class {c['id']}: no icon")
        scope = c["detect"].get("scope")
        if scope not in ("bead", "snapshot"):
            errors.append(f"class {c['id']}: bad scope {scope!r}")
        allowed = (BEAD_FIELDS if scope == "bead" else SNAPSHOT_FIELDS)
        for tmpl in (c.get("witness"), c.get("witnessNamed")):
            for f in FIELD_RE.findall(tmpl or ""):
                if f not in allowed:
                    errors.append(f"class {c['id']}: witness field {{{f}}} not produced by a {scope} detector")
        effects = list(c.get("coherence") or [])
        for lst in (c.get("threadCoherence") or {}).values():
            effects += lst
        for eff in effects:
            key = tuple(sorted(eff["pair"]))
            if key not in pairs:
                errors.append(f"class {c['id']}: coherence effect on unlisted pair {eff['pair']}")
            if eff.get("effect") not in ("distinguish", "renew"):
                errors.append(f"class {c['id']}: bad effect {eff.get('effect')!r}")
            if eff.get("effect") == "distinguish" and eff.get("toward") not in eff["pair"]:
                errors.append(f"class {c['id']}: distinguish toward {eff.get('toward')!r} not in pair")
        if c.get("aliasOf") and c["aliasOf"] not in {x["id"] for x in classes["classes"]}:
            errors.append(f"class {c['id']}: aliasOf unknown class {c['aliasOf']}")
        if c.get("owner") == "by_thread" and not c.get("threadOwners"):
            errors.append(f"class {c['id']}: by_thread owner without threadOwners")

    att_ids = {a["id"] for a in attractors.get("attractors") or []}
    scene_ids = {s["id"] for s in scenes.get("scenes") or []}
    for a in attractors.get("attractors") or []:
        for k in (a.get("signature") or {}):
            if k not in reading_ids:
                errors.append(f"attractor {a['id']}: signature names unknown reading {k!r}")
        for req in a.get("requires") or []:
            if "pair" in req and tuple(sorted(req["pair"])) not in pairs:
                errors.append(f"attractor {a['id']}: requires unlisted pair {req['pair']}")
        for e in a.get("edges") or []:
            if e.get("to") not in att_ids:
                errors.append(f"attractor {a['id']}: edge to unknown attractor {e.get('to')!r}")
            if e.get("scene") and e["scene"] not in scene_ids:
                errors.append(f"attractor {a['id']}: edge scene {e['scene']!r} not in attractor_scenes.json")
        if not a.get("terminal") and f"enter:{a['id']}" not in scene_ids and a["id"] != "shelf":
            warnings.append(f"attractor {a['id']}: no enter:{a['id']} scene")

    known_speakers = {h["heroId"] for h in codex["heroes"]} | set((state.get("characters") or {}).keys()) | {"narrator", "commander"}
    for s in scenes.get("scenes") or []:
        when = s.get("when") or {}
        if when.get("enterAttractor") and when["enterAttractor"] not in att_ids:
            errors.append(f"scene {s['id']}: enterAttractor {when['enterAttractor']!r} unknown")
        for hid in s.get("pair") or []:
            if hid not in known_speakers:
                errors.append(f"scene {s['id']}: unknown speaker {hid!r}")
        for b in s.get("beats") or []:
            if b.get("speaker") not in known_speakers:
                errors.append(f"scene {s['id']}: beat speaker {b.get('speaker')!r} unknown")
        for ch in s.get("choices") or []:
            if ch.get("stance") not in STANCES:
                warnings.append(f"scene {s['id']}: choice {ch.get('id')} stance {ch.get('stance')!r} not a leadership_voices style")
        if s.get("fallback") and s["fallback"] not in scene_ids:
            errors.append(f"scene {s['id']}: fallback {s['fallback']!r} unknown")

    vdir = story / "voices"
    line_ids: Set[str] = set()
    all_fields = PROBE_FIELDS | BEAD_FIELDS | SNAPSHOT_FIELDS | COMMON_FIELDS
    for path in sorted(vdir.glob("*.json")) if vdir.exists() else []:
        doc = load(path)
        if doc.get("blades"):
            for hid, b in doc["blades"].items():
                if hid not in known_speakers:
                    errors.append(f"blades: unknown hero {hid!r}")
                for k in ("join", "held", "costly", "death"):
                    for f in FIELD_RE.findall(b.get(k) or ""):
                        if f not in all_fields:
                            errors.append(f"blades {hid}.{k}: unknown field {{{f}}}")
            continue
        if doc.get("patrons"):
            for pid, p in doc["patrons"].items():
                if pid not in known_speakers:
                    warnings.append(f"patrons: {pid!r} not in campaign characters")
                for d in p.get("dispatches") or []:
                    on = d.get("on") or {}
                    if on.get("class") and on["class"] not in class_ids:
                        errors.append(f"patron {pid}: dispatch on unknown class {on['class']!r}")
                    if on.get("attractor") and on["attractor"] not in att_ids:
                        errors.append(f"patron {pid}: dispatch on unknown attractor {on['attractor']!r}")
                    if on.get("dominantBecame") and on["dominantBecame"] not in reading_ids:
                        errors.append(f"patron {pid}: dispatch on unknown reading {on['dominantBecame']!r}")
                    for f in FIELD_RE.findall(d.get("text") or ""):
                        if f not in all_fields:
                            errors.append(f"patron {pid}: unknown field {{{f}}}")
            continue
        speaker = doc.get("speaker")
        if speaker not in known_speakers:
            errors.append(f"voice {path.name}: speaker {speaker!r} unknown")
        for owned in doc.get("owns") or []:
            base = owned.split(":")[0]
            if base not in class_ids:
                errors.append(f"voice {speaker}: owns unknown class {owned!r}")
        for line in doc.get("lines") or []:
            if line["id"] in line_ids:
                errors.append(f"voice {speaker}: duplicate line id {line['id']}")
            line_ids.add(line["id"])
            on = line.get("on") or {}
            if on.get("class") and on["class"] not in class_ids:
                errors.append(f"voice {speaker}: line {line['id']} on unknown class {on['class']!r}")
            if on.get("attractor") and on["attractor"] != "*" and on["attractor"] not in att_ids:
                errors.append(f"voice {speaker}: line {line['id']} on unknown attractor {on['attractor']!r}")
            if on.get("dominantBecame") and on["dominantBecame"] not in reading_ids:
                errors.append(f"voice {speaker}: line {line['id']} on unknown reading {on['dominantBecame']!r}")
            for k in ("coherenceSettled", "coherenceTorn"):
                if on.get(k) and tuple(sorted(on[k]["pair"])) not in pairs:
                    errors.append(f"voice {speaker}: line {line['id']} on unlisted pair {on[k]['pair']}")
            for rd in (line.get("reading") or {}).get("dominant") or []:
                if rd not in reading_ids:
                    errors.append(f"voice {speaker}: line {line['id']} reading {rd!r} unknown")
            for f in FIELD_RE.findall(line.get("text") or ""):
                if f not in all_fields:
                    errors.append(f"voice {speaker}: line {line['id']} unknown field {{{f}}}")
            if len(line.get("text") or "") > 160:
                warnings.append(f"voice {speaker}: line {line['id']} is {len(line['text'])} chars (translators asked for short)")

    # Coverage: every event class should have at least one owner line or a Ketha fallback.
    covered: Dict[str, Set[str]] = {}
    for path in sorted(vdir.glob("*.json")) if vdir.exists() else []:
        doc = load(path)
        if not doc.get("speaker"):
            continue
        for line in doc.get("lines") or []:
            cls = (line.get("on") or {}).get("class")
            if cls:
                covered.setdefault(cls, set()).add(doc["speaker"])
    for c in classes["classes"]:
        cid = c.get("aliasOf") or c["id"]
        owners = covered.get(cid, set())
        owner = c.get("owner")
        if not owners:
            warnings.append(f"class {c['id']}: no voice line anywhere (will read as narrator witness)")
        elif owner != "by_thread" and owner not in owners:
            warnings.append(f"class {c['id']}: owner {owner} has no line for it (covered by {sorted(owners)})")
        if "ketha" not in owners and cid not in ("walker_rebuilt",):
            warnings.append(f"class {c['id']}: no Ketha fallback line")

    # Determinism of the projector on the live save.
    if state:
        a = json.dumps(readings.project(json.loads(json.dumps(state)), ROOT), sort_keys=True)
        b = json.dumps(readings.project(json.loads(json.dumps(state)), ROOT), sort_keys=True)
        if a != b:
            errors.append("projector is not deterministic on the live save")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s); {len(reading_ids)} readings, {len(class_ids)} event classes, "
          f"{len(att_ids)} attractors, {len(scene_ids)} scenes, {len(line_ids)} voice lines")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
