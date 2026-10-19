"""Deterministic narrative projection and commands; never a second world simulator.

Only accept_result and choose mutate narrative state. project works on a copy.
Narrative trust is deliberately separate from combat bonds and faction reputation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "verdance-narrative/1.0"
VERDICTS = {"victory": "Success", "partial": "Partial success", "defeat": "Defeat",
            "abandon": "Withdrawn", "incomplete": "Result pending"}


def enabled(state):
    return os.environ.get("VERDANCE_NARRATIVE", "1") != "0" and (state.get("features") or {}).get("narrative", True)


def catalog(workspace=None):
    path = Path(workspace or ROOT) / "data/story/narrative_threads.json"
    if not path.exists():
        path = ROOT / "data/story/narrative_threads.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = path.with_name("narrative_scenes.json")
    data["scenes"] = json.loads(scenes.read_text(encoding="utf-8")) if scenes.exists() else []
    voices = path.with_name("leadership_voices.json")
    data["voices"] = json.loads(voices.read_text(encoding="utf-8")) if voices.exists() else {}
    return data


def revision(state):
    # Include all authoritative state, so a purchase or home build also invalidates
    # an old decision. Read-only projections never alter this token.
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def world_snapshot(state):
    return {"reputation": copy.deepcopy(state.get("reputation") or {}),
            "graph": copy.deepcopy(state.get("graph") or {}),
            "frontEventCount": len(state.get("frontEvents") or [])}


def ensure(state):
    n = state.setdefault("narrative", {})
    defaults = {"schemaVersion": SCHEMA, "turn": 0, "threads": {}, "events": [],
                "processedResults": [], "requests": {}, "intelligence": {}, "trust": {}, "leadership": [], "sceneDecisions": {}}
    for key, value in defaults.items():
        n.setdefault(key, copy.deepcopy(value))
    return n


def company_ids(state):
    company = state.get("company") or {}
    if company.get("sealed"):
        ids = set(company.get("core") or []) | set(company.get("band") or []) | set(company.get("joinedLater") or [])
    else:
        ids = {k for k, c in (state.get("characters") or {}).items()
               if c.get("player") and c.get("status") == "active"}
    return {i for i in ids if (state.get("characters", {}).get(i, {}).get("status") not in ("dead", "lost", "unrecruited"))}


def zones(state):
    for mid, entries in (state.get("zoneMemory") or {}).items():
        if isinstance(entries, dict):
            for zid, z in entries.items():
                if isinstance(z, dict):
                    yield mid, zid, z


def eligible(fid, state):
    home = state.get("homeCamp") or {}
    history = state.get("history") or []
    if fid == "place":
        return not (state.get("flags") or {}).get("homeCleared", False)
    if fid == "shelter":
        return any(z.get("controllingFaction") == "ashwalkers" for _, _, z in zones(state))
    if fid == "bring_back":
        return True
    if fid == "friends":
        return bool(history) and "nullmercs" in (state.get("reputation") or {})
    if fid == "dealer":
        return any(b.get("mapId") == "eye_of_horus" for b in history) or float((state.get("reputation") or {}).get("cortex", 70)) < 60
    if fid == "company":
        return bool(history) and len(company_ids(state)) >= 2
    return False


def reconcile(state, data):
    n = ensure(state)
    for spec in data["threads"]:
        fid = spec["id"]
        if fid not in n["threads"] and eligible(fid, state):
            n["threads"][fid] = {"id": fid, "stage": "Available", "openedTurn": n["turn"],
                                  "history": [], "supportingEvents": [], "presentations": 0}
        t = n["threads"].get(fid)
        if not t:
            continue
        if fid != "place" and t["stage"] == "Resolved" and n["turn"] >= t.get("resolvedTurn", n["turn"]) + 3 and eligible(fid, state):
            t.update(stage="Available", cycle=t.get("cycle", 1) + 1, explanation=spec["callback"] + " A new opportunity has emerged.")
            t.pop("deadline", None)
        if fid == "place" and ((state.get("homeCamp") or {}).get("level", 0) > 0 or (state.get("flags") or {}).get("homeCleared")):
            if t["stage"] not in ("Resolved", "Committed"):
                t.update(stage="Resolved", explanation="Your camp is established. The next task is securing the surrounding wilds.")
        elif fid == "shelter" and not eligible(fid, state) and t["stage"] in ("Available", "Committed"):
            t.update(stage="Changed", explanation=spec["changed"])


def operation_summary(choice):
    effect = choice.get("effect") or {}
    kind = effect.get("objectiveArchetype") or effect.get("contractKind") or choice.get("objectiveArchetype") or ""
    required = {
        "seize_lane": "Clear and hold the marked zone until the objective confirms completion.",
        "gate_control": "Clear and hold the marked gate until the objective confirms completion.",
        "hold_plateau": "Hold the marked plateau until the objective confirms completion.",
        "economy_disrupt": "Destroy the marked economic targets; optional targets are separate.",
        "eco_raid": "Destroy the required raid targets. Recover salvage before leaving.",
        "strike_relay": "Destroy the marked relay targets.",
        "destroy_key_structure": "Destroy the marked key structures.",
    }.get(kind, "Complete the required marks shown in the battle briefing; optional marks do not replace them.")
    return {"id": choice.get("id"), "title": choice.get("label", "Operation"),
            "mapId": effect.get("mapId"), "purpose": choice.get("blurb") or "Secure an opportunity for the company.",
            "required": required,
            "bringHome": "Choose Home or Stay in field, then confirm extraction in the battle sidebar. The marked sector must show friendly control and be clear of hostiles. Hold the pad for 10 seconds; interruption resets the hold. The campaign saves the result before returning home or offering the next field mission. Timeout is a separate outcome, not extraction.",
            "risks": "Enemy strength beyond observed ground is unknown. Optional targets add exposure.",
            "consequences": "Territory changes require objective credit or a confirmed node claim. Capturing ground does not create Tenebrium.",
            "disabled": bool(choice.get("disabled"))}


def leadership_reactions(state, data):
    n = state['narrative']
    groups = {'Care':'care', 'Care before profit':'care', 'Care before ambition':'care', 'Solidarity':'care',
              'Resolve':'ambition', 'Defiance':'ambition', 'Calculated ambition':'ambition',
              'Independence':'independence', 'Self-reliance':'independence', 'Freedom of movement':'independence',
              'Prudence':'pragmatism', 'Pragmatism':'pragmatism', 'Restraint':'pragmatism', 'Reciprocity':'pragmatism',
              'Stewardship':'stewardship', 'Holding ground':'stewardship', 'Building a future':'stewardship'}
    recent = n['leadership'][-8:]
    if not recent:
        return []
    weights = {}
    for i, memory in enumerate(recent):
        key = groups.get(memory['stance'], 'pragmatism')
        weights[key] = weights.get(key, 0) + i + 1
    style = max(sorted(weights), key=weights.get)
    memory = next(m for m in reversed(recent) if groups.get(m['stance'], 'pragmatism') == style)
    t = n['threads'].get(memory['choiceId'].split(':')[0], {})
    # Link assessment to the exact promise, including older cycles, never an unrelated return.
    record = next((i for i,h in enumerate(t.get('history', [])) if h.get('eventId') == memory['eventId']), None)
    outcome = None
    if record is not None:
        for entry in t['history'][record+1:]:
            if entry.get('kind') == 'commitment': break
            if entry.get('stage') in ('Resolved', 'Changed'): outcome = entry; break
    kind = 'kept' if outcome and outcome['stage']=='Resolved' else 'unfinished' if outcome else 'words'
    index = {'words':0,'kept':1,'unfinished':2}[kind]
    return [{'speaker':hid, 'style':style, 'basis':kind, 'text':data['voices'][hid][style][index],
             'memory':memory['words'], 'sourceEventId':(outcome or {}).get('eventId', memory['eventId']),
             'turn':memory['turn']} for hid in sorted(company_ids(state)) if hid in data['voices']
             and not state.get('characters',{}).get(hid,{}).get('wounds')]


def scene_evidence(scene, events):
    """Authored reactions require a recorded return with these speakers present."""
    condition = scene.get("when")
    if not condition:
        return None
    for event in reversed(events):
        if not set(scene["pair"]) <= set(event.get("participants", [])):
            continue
        if condition.get("verdicts") and event.get("verdict") not in condition["verdicts"]:
            continue
        if condition.get("continued") and (event.get("chapterIndex") or 0) <= 1:
            continue
        if condition.get("wounded") and not event.get("wounded"):
            continue
        return event["id"]
    return None


def project(state, choices=(), workspace=None):
    if not enabled(state):
        return {"enabled": False, "revision": revision(state), "threads": [], "scenes": [], "chronicle": []}
    snapshot = copy.deepcopy(state)
    data = catalog(workspace)
    reconcile(snapshot, data)
    n = snapshot["narrative"]
    owned = company_ids(snapshot)
    out = []
    for spec in data["threads"]:
        t = n["threads"].get(spec["id"])
        if not t:
            continue
        row = {**copy.deepcopy(spec), **copy.deepcopy(t)}
        row["perspectives"] = [p for p in spec["perspectives"] if p["speaker"] in owned and not snapshot.get("characters", {}).get(p["speaker"], {}).get("wounds")][:2]
        row["remaining"] = max(0, t["deadline"] - n["turn"]) if "deadline" in t else None
        row["trust"] = n["trust"].get(t["id"], 0)
        row["choices"] = [{"id": f"{spec['id']}:{c['id']}", **c} for c in spec["choices"]] if t["stage"] in ("Available", "Changed") else []
        # Prefix after unpacking so an authored local id cannot replace the wire id.
        for c in row["choices"]:
            c["id"] = spec["id"] + ":" + c["id"].split(":")[-1]
        row["operations"] = [c["id"] for c in choices if c.get("kind") == "deploy" and not c.get("disabled") and (c.get("effect") or {}).get("mapId") in spec["maps"]]
        row["operationLabels"] = {c["id"]: c.get("label", "Operation") for c in choices if c.get("id") in row["operations"]}
        recent = 20 if t.get("history") and t["history"][-1].get("turn") == n["turn"] else 0
        row["priority"] = (100 if t["stage"] == "Committed" else 0) + spec["priority"] + recent - t["presentations"] + max(-5, min(5, row["trust"]))
        row["reason"] = t.get("explanation") or spec["reason"]
        out.append(row)
    out.sort(key=lambda t: (-t["priority"], t["id"]))
    scenes = [s for s in data["scenes"] if set(s["pair"]) <= owned and n["turn"] >= s["afterTurn"]
              and sum(set(s["pair"]) <= set(e.get("participants", [])) for e in n["events"]) >= s.get("minSharedDeployments", 1)
              and all(not snapshot.get("characters", {}).get(i, {}).get("wounds") for i in s["pair"])
              and (not s.get("when") or scene_evidence(s, n["events"]))]
    scenes = copy.deepcopy(scenes)
    for scene in scenes:
        scene['sourceEventId'] = scene_evidence(scene, n['events'])
        decision = n['sceneDecisions'].get(scene['id'])
        scene['decision'] = decision
        scene['choices'] = [] if decision else [{**c, 'id':'scene:'+scene['id']+':'+c['id']} for c in scene.get('choices',[])]
    reactions = leadership_reactions(snapshot, data)
    for row in out:
        row['reactions'] = [r for r in reactions if r['speaker'] in {p['speaker'] for p in row['perspectives']}][:2]
    operations = [operation_summary(c) for c in choices if c.get("kind") == "deploy"]
    for op in operations:
        commitments = [t for t in out if t["stage"] == "Committed" and op["id"] in t["operations"]]
        scarce = float((state.get("commerce") or {}).get("tenebrium", 0)) < 3 and op["mapId"] == "greenest_fields"
        op["priority"] = (100 if commitments else 0) + (30 if scarce else 0)
        op["recommendation"] = ("Supports your commitment: " + commitments[0]["title"] if commitments else
                                "Tenebrium reserves are low; a raid can fund construction." if scarce else
                                "Available on this theater. Review the requirements and route.")
    operations.sort(key=lambda o: (o["disabled"], -o["priority"], str(o["id"])))
    intelligence = copy.deepcopy(n["intelligence"])
    for choice in choices:
        effect = choice.get("effect") or {}
        mid, target = effect.get("mapId"), effect.get("targetZoneId")
        if choice.get("kind") == "deploy" and not choice.get("disabled") and mid and target:
            intelligence.setdefault(f"{mid}:{target}", {"status": "Reported", "source": "Operation briefing: " + str(choice.get("label") or choice.get("id")), "lastObservedTurn": None})
    return {"enabled": True, "schemaVersion": SCHEMA, "revision": revision(state), "turn": n["turn"],
            "threads": out, "recommended": [t["id"] for t in out if t["stage"] in ("Available", "Committed", "Changed")][:3],
            "operations": operations,
            "chronicle": list(reversed(n["events"])), "intelligence": intelligence, "scenes": scenes,
            "leadership": copy.deepcopy(n["leadership"]), "reactions": reactions,
            "home": {"level": (state.get("homeCamp") or {}).get("level", 0), "cleared": bool((state.get("flags") or {}).get("homeCleared"))}}


def choose(state, choice_id, expected_revision, request_id, workspace=None):
    if not enabled(state):
        return {"ok": False, "error": "Narrative features are disabled."}
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        return {"ok": False, "error": "A valid request ID is required."}
    prior = (state.get("narrative") or {}).get("requests", {}).get(request_id)
    if prior:
        return copy.deepcopy(prior) if prior["choiceId"] == choice_id else {"ok": False, "error": "Request ID already belongs to another choice."}
    if revision(state) != expected_revision:
        return {"ok": False, "error": "The campaign changed. Refresh before making this commitment.", "stale": True}
    view = project(state, workspace=workspace)
    scene_match = next(((scene,c) for scene in view['scenes'] for c in scene.get('choices',[]) if c['id']==choice_id),None)
    if scene_match:
        scene, choice = scene_match
        n = ensure(state)
        decision = {'choiceId':choice_id, 'stance':choice['stance'], 'words':choice['label'],
                    'response':choice['response'], 'turn':n['turn'], 'eventId':request_id}
        n['sceneDecisions'][scene['id']] = decision
        n['leadership'].append(copy.deepcopy(decision))
        receipt = {'ok':True,'choiceId':choice_id,'requestId':request_id,'cost':0,
                   'obligation':'Conversation response recorded. No sortie deadline or resource effect.'}
        n['requests'][request_id] = receipt
        return copy.deepcopy(receipt)
    match = next(((t, c) for t in view["threads"] for c in t["choices"] if c["id"] == choice_id), None)
    if not match:
        return {"ok": False, "error": "This response is no longer available."}
    row, choice = match
    reconcile(state, catalog(workspace))
    n = state["narrative"]
    t = n["threads"][row["id"]]
    n["leadership"].append({"choiceId": choice_id, "stance": choice.get("stance", ""), "words": choice["label"], "turn": n["turn"], "eventId": request_id})
    t.update(stance=choice.get("stance"), response=choice.get("response"), promise=choice["label"])
    t.update(stage="Committed", commitment=choice_id, goal=choice["goal"], committedTurn=n["turn"],
             explanation=choice["obligation"])
    if choice.get("deadline"):
        t["deadline"] = n["turn"] + int(choice["deadline"])
    else:
        t.pop("deadline", None)
    t["history"].append({"eventId": request_id, "turn": n["turn"], "kind": "commitment", "text": choice["label"]})
    receipt = {"ok": True, "choiceId": choice_id, "requestId": request_id, "cost": 0, "obligation": choice["obligation"]}
    n["requests"][request_id] = receipt
    return copy.deepcopy(receipt)


def goal_met(goal, state, result, credit):
    flags = credit.get("credits") or {}
    clean = bool(flags.get("cleanExtract"))
    victory = credit.get("verdict") == "victory"
    mid = result.get("mapId")
    return {
        "home": (state.get("homeCamp") or {}).get("level", 0) > 0,
        "raid": mid == "greenest_fields" and clean,
        "claim": bool(flags.get("nodeClaimed")),
        "extract": clean,
        "merc": victory and mid != "eye_of_horus",
        "dealer": mid == "eye_of_horus" and clean,
        "recover": clean and bool(result.get("heroResults")) and all(
            isinstance(h, dict) and not h.get("wounds") and h.get("status") not in ("dead", "lost", "wounded")
            and (h.get("alive") is True or h.get("status") in ("active", "alive", "recovered", "survived"))
            for h in (result.get("heroResults") or {}).values()),
    }.get(goal, False)


def accept_result(state, result, credit, workspace=None, before=None):
    if not enabled(state) or not credit.get("advanceMission"):
        return None
    key = str(result.get("resultKey") or credit.get("resultKey") or "")
    if not key or credit.get("verdict") not in ("victory", "partial", "defeat"):
        return None
    n = ensure(state)
    if key in n["processedResults"]:
        return None
    data = catalog(workspace)
    reconcile(state, data)
    n["turn"] += 1
    n["processedResults"].append(key)
    consequences = []
    if before:
        for faction, value in (state.get("reputation") or {}).items():
            old = before["reputation"].get(faction)
            if isinstance(old, (int, float)) and isinstance(value, (int, float)) and value != old:
                consequences.append({"sourceEventId": key, "origin": "campaign_update", "text":
                    f"{faction.title()} standing {'rose' if value > old else 'fell'} from {old:g} to {value:g}."})
        labels = {"q6_contested": ("Conflict pressure increased.", "Conflict pressure eased."),
                  "q7_resource_scarcity": ("Resources are assessed as scarcer.", "Resource pressure eased."),
                  "q6_independent": ("Independent influence grew.", "Independent influence weakened.")}
        for axis, lines in labels.items():
            old = before["graph"].get(axis); new = (state.get("graph") or {}).get(axis)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and abs(new-old) >= 0.01:
                consequences.append({"sourceEventId": key, "origin": "campaign_update", "text": lines[0 if new>old else 1]})
        for change in (state.get("frontEvents") or [])[before["frontEventCount"]:]:
            if change.get("type") == "zone_lost":
                consequences.append({"sourceEventId": key, "origin": "elsewhere", "text":
                    f"The company lost its foothold at {change.get('label') or change.get('zoneId') or 'an unnamed zone'}."})
    for spec in data["threads"]:
        t = n["threads"].get(spec["id"])
        if not t:
            continue
        if t["stage"] == "Committed":
            chosen = next((c for c in spec["choices"] if spec["id"]+":"+c["id"] == t.get("commitment")), {})
            if goal_met(t["goal"], state, result, credit):
                t.update(stage="Resolved", explanation=chosen.get("success", spec["success"]), remembered=chosen.get("callback", spec["callback"]), resolvedTurn=n["turn"])
                n["trust"][t["id"]] = n["trust"].get(t["id"], 0) + 1
            elif "deadline" in t and n["turn"] >= t["deadline"]:
                t.update(stage="Changed", explanation=spec["changed"])
                n["trust"][t["id"]] = n["trust"].get(t["id"], 0) - 1
            else:
                t["explanation"] = spec["failure"] if credit["verdict"] != "victory" else spec["escalation"]
            t["supportingEvents"].append(key)
            t["history"].append({"eventId": key, "turn": n["turn"], "stage": t["stage"], "text": t["explanation"]})
            consequences.append({"sourceEventId": key, "threadId": t["id"], "origin": "your_action", "text": t["explanation"]})
        elif t["stage"] == "Resolved" and t.get("supportingEvents") and n["turn"] == t.get("resolvedTurn", -1) + 1:
            consequences.append({"sourceEventId": t["supportingEvents"][-1], "threadId": t["id"], "origin": "memory", "text": t.get("remembered", spec["callback"])})
    # Confirm only explicit observed zones; never convert zoneMemory into omniscient intel.
    mid = result.get("mapId")
    observed = result.get("observedZoneIds") or []
    for zid in observed if isinstance(observed, list) else []:
        n["intelligence"][f"{mid}:{zid}"] = {"status": "Confirmed", "source": key, "lastObservedTurn": n["turn"]}
    participants = set()
    for field in ("deployAces", "deployedHeroes", "sortieHeroes"):
        for hero in result.get(field) or []:
            hid = (hero.get("heroId") or hero.get("id")) if isinstance(hero, dict) else hero
            if hid:
                participants.add(str(hid))
    participants.update((result.get("heroResults") or {}).keys())
    participants.update(o["charId"] for o in result.get("namedOutcomes") or [] if o.get("charId"))
    event = {"id": key, "turn": n["turn"], "mapId": mid, "verdict": credit["verdict"],
             "chapterIndex": result.get("chapterIndex"),
             "title": VERDICTS[credit["verdict"]], "participants": sorted(participants),
             "consequences": consequences, "credits": copy.deepcopy(credit.get("credits") or {}),
             "resources": {k: result[k] for k in ("tenebriumBank", "tenebriumLooted", "tenebriumSpent", "tenebriumLost") if k in result},
             "wounded": [i for i in company_ids(state) if state.get("characters", {}).get(i, {}).get("wounds")]}
    n["events"].append(event)
    presented = project(state, workspace=workspace).get("recommended", [])
    for tid in presented:
        n["threads"][tid]["presentations"] += 1
    return event
