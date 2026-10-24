#!/usr/bin/env python3
"""Can a campaign be finished? Plays one from the preamble to the end without BAR.

Each sortie does what the hub does: take the node's recommended choice (else the first deploy
choice), plan it the way ensureTheaterPlan does (the camp's next pad when it is on this map, else
the choice's pad, else a legal zone; the choice's target, else an open target), commit the drop,
fake a clean extraction of everyone who went, and bring it home. It stops when the campaign is
complete, or reports where it stalled.

    UMWELT_SRC=/path/to/umwelt/src python3 tests/playthrough_campaign.py [--sorties 20] [--seed 1]

Exit 0 = the campaign completed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_campaign import fresh_workspace  # noqa: E402
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from verdance.world.claim import claim_need  # noqa: E402


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.is_file() else {}


def pick_choice(hs):
    choices = [c for c in ((hs.get("node") or {}).get("choices") or []) if c.get("kind") == "deploy"]
    return next((c for c in choices if c.get("recommended")), choices[0] if choices else None), len(choices)


def plan_for(hs, choice, boards):
    eff = (choice or {}).get("effect") or {}
    camp = hs.get("camp") or {}
    map_id = eff.get("mapId") or hs.get("sessionHomeMap") or "the_rock_jungle"
    zones = {z["zoneId"]: z for z in (boards.get(map_id) or {}).get("zones") or []}
    theater = hs.get("theater") or {}
    tz = theater.get("zones") or [] if theater.get("mapId") == map_id else []
    pad = None
    if camp.get("nextPadZoneId") in zones and camp.get("nextPadMapId") in (None, map_id):
        pad = camp["nextPadZoneId"]
    pad = pad or eff.get("preferredDeployZoneId") or eff.get("deploymentZoneId")
    if not pad:
        legal = [z for z in tz if z.get("preferred") or z.get("believed") in ("ours", "empty", "dark", "unsure")]
        pad = (legal[0] if legal else (tz[0] if tz else {})).get("zoneId") or next(iter(zones), None)
    target = eff.get("preferredCaptureZoneId") or eff.get("targetZoneId") or (eff.get("captureZoneIds") or [None])[0]
    target = target or next((z.get("zoneId") for z in tz if z.get("openTarget")), None) or next((z for z in zones if z != pad), None)
    return {
        "schemaVersion": "verdance-deploy-plan/1.0", "mapId": map_id, "choiceId": (choice or {}).get("id"),
        "contractKind": eff.get("contractKind"), "against": eff.get("against"),
        "deployAces": [a["id"] for a in hs.get("aces") or [] if a.get("deployable")],
        "marks": {"deployZoneId": pad, "extractZoneId": pad, "captureZoneIds": [target] if target else [], "secondaryCaptureZoneIds": []},
        "repDelta": eff.get("repDelta") or {},
    }


def fake_result(state, intent, plan, hs, n, brought):
    pad, target = plan["marks"]["deployZoneId"], (plan["marks"]["captureZoneIds"] or [None])[0]
    heroes = [a["id"] for a in hs.get("aces") or [] if a.get("deployable")]
    seen = {str(target): 0.9, str(pad): 0.95}
    lifted = dict(brought)  # everything that dropped gets back onto the pad, plus what was built
    for d, c in {"corthud": 6, "armwar": 3}.items():
        lifted[d] = lifted.get(d, 0) + c
    return {
        "schemaVersion": "verdance-match-result/2.0", "campaignId": state.get("campaignId") or "verdance_ashes",
        "resultKey": f"play|{intent.get('missionId')}|{n}|{time.time()}",
        "missionId": intent.get("missionId"), "missionNumber": int(intent.get("missionNumber") or state.get("missionNumber") or 1),
        "mapId": plan["mapId"], "deploymentMapId": plan["mapId"], "against": plan.get("against"),
        "status": "extracted", "verdict": "extracted", "objectiveComplete": True, "allObjectivesDone": True,
        "objectiveResults": [{"kind": (intent.get("objectiveTarget") or {}).get("kind") or plan.get("contractKind") or "eco_raid", "targetZoneId": target, "done": True}],
        "secondaryResults": [], "playerSurvivors": dict(lifted),
        "heroResults": {h: {"heroId": h, "name": h, "state": "alive", "outcome": "alive"} for h in heroes},
        "tenebriumBank": 4, "tenebriumLooted": 4, "tenebriumSpent": 0,
        # a kings' showdown reports its kings: both rivals fell, ours stands
        "kings": ([{"faction": "ashwalkers", "teamID": 0, "fallen": False}]
                  + [{"faction": k["faction"], "teamID": i + 1, "fallen": True, "minute": 20.0 + i, "by": "ashwalkers"}
                     for i, k in enumerate((intent.get("theater") or {}).get("kings") or [])])
                 if (intent.get("theater") or {}).get("kind") == "kings_showdown" else None,
        "observedZones": dict(seen),
        # the company dug in at its pad and its target with the claim presence (the objective will
        # not complete without it): it holds both at homecoming (doors too)
        "zoneDv": {str(pad): {"ashwalkers": claim_need(plan["mapId"], REPO)},
                   str(target): {"ashwalkers": claim_need(plan["mapId"], REPO) + 100}},
        "beliefExport": {z: {"eta": e, "enemyNow": 0, "friendNow": 3 if z == pad else 0} for z, e in seen.items()},
        "manifest": {
            "schema": "verdance-manifest/1", "kind": "extracted", "destination": "home",
            "pad": {"zoneId": pad, "label": pad, "x": 1000, "z": 1000, "radius": 560},
            "going": {"heroes": [{"heroId": h, "name": h} for h in heroes], "units": dict(lifted), "packUnits": {},
                      "unitCount": sum(lifted.values()), "metal": 1500},
            "staying": {"heroes": [], "units": {}, "unitCount": 0, "structures": {}, "structureCount": 0, "metal": 0},
            "enemyOnPad": 0, "seen": seen, "tenebrium": 4, "objectiveComplete": True, "dropped": list(heroes),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sorties", type=int, default=20)
    args = ap.parse_args()
    os.environ.setdefault("VA_PERSPECTIVES_SYNC", "1")
    os.environ.setdefault("VA_PERSPECTIVES_NOSPAWN", "1")
    ws = fresh_workspace()
    sys.path.insert(0, str(ws / "tools"))
    os.chdir(ws)
    import subprocess
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ws / "tools"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    subprocess.run([sys.executable, "-m", "verdance.campaign.engine", "init-state", "--workspace", str(ws), "--write-state"],
                   capture_output=True, text=True, timeout=300, cwd=str(ws), env=env)
    from verdance_kernel.api import CampaignKernel  # type: ignore
    k = CampaignKernel(ws)
    sp, hp, ip = ws / "state" / "campaign_state.json", ws / "app" / "showoff" / "hub_state.json", ws / "outbox" / "next_mission_intent.json"
    boards = {}
    for f in (ws / "data" / "zone_maps").glob("*.json"):
        try:
            d = jload(f)
            boards[d.get("mapId") or f.stem] = d
        except Exception:  # noqa: BLE001
            pass
    k.rebuild_hub(skip_apply=True)
    seal = k.seal_company(band=["pavise", "solarium", "halbard"])
    if not seal.get("ok"):
        print("STALL seal", seal)
        return 1
    log = []
    for n in range(1, args.sorties + 1):
        k.rebuild_hub(skip_apply=True)
        hs, st = jload(hp), jload(sp)
        if st.get("campaignComplete"):
            break
        choice, nchoices = pick_choice(hs)
        row = {"n": n, "mission": st.get("missionNumber"), "act": (hs.get("arc") or {}).get("id"), "choices": nchoices,
               "choice": (choice or {}).get("id"), "deployable": sum(1 for a in hs.get("aces") or [] if a.get("deployable"))}
        if not choice:
            row["stall"] = "no deploy choice on the node"
            log.append(row)
            break
        plan = plan_for(hs, choice, boards)
        row.update(map=plan["mapId"], pad=plan["marks"]["deployZoneId"], target=(plan["marks"]["captureZoneIds"] or [None])[0])
        if ip.exists():
            ip.unlink()
        dep = k.commit_deploy(plan, launch=False)
        for _ in range(240):
            if ip.is_file():
                break
            time.sleep(0.25)
        if not ip.is_file():
            row["stall"] = "deploy refused: " + json.dumps(dep)[:300]
            log.append(row)
            break
        intent = jload(ip)
        row["objective"] = (intent.get("objectiveTarget") or {}).get("kind")
        row["setPiece"] = (intent.get("theater") or {}).get("kind")
        if row["setPiece"] == "kings_showdown" and not (intent.get("soloCommand") and not intent.get("deployAces")):
            row["stall"] = "kings' showdown without a solo commander"
            log.append(row)
            break
        row["enemyAI"] = intent.get("enemyAI") or (intent.get("arcProfile") or {}).get("enemyAI")
        (ws / "inbox").mkdir(exist_ok=True)
        (ws / "inbox" / "latest_va_result.json").write_text(json.dumps(fake_result(st, intent, plan, hs, n, (jload(sp).get("roster") or {}).get("cadre") or {})), encoding="utf-8")
        home = k.bring_home(extract=False) if "extract" in k.bring_home.__code__.co_varnames else k.bring_home()
        st2 = jload(sp)
        bead = (st2.get("history") or [{}])[-1]
        row.update(verdict=bead.get("verdict"), after=st2.get("missionNumber"), reserve=sum(((st2.get("roster") or {}).get("reserve") or {}).values()),
                   doors=sorted(z for z, d in (st2.get("doors") or {}).items() if d.get("held")))
        if int(st2.get("missionNumber") or 0) <= int(st.get("missionNumber") or 0) and not st2.get("campaignComplete"):
            row["stall"] = "mission did not advance: " + json.dumps(home)[:300]
            log.append(row)
            break
        log.append(row)
    for r in log:
        print(json.dumps(r))
    st = jload(sp)
    done = bool(st.get("campaignComplete"))
    ok = done
    if done:
        k.rebuild_hub(skip_apply=True)
        node = jload(hp).get("node") or {}
        ending = node.get("kind") == "epilogue" and not node.get("choices")
        refused = not k.commit_deploy(plan_for(jload(hp), None, boards), launch=False).get("ok")
        granted = {"legshot", "legkeres"} <= set(((st.get("roster") or {}).get("reserve") or {}))
        print("epilogue, no more drops:", ending and refused, "· act II rewards in the reserve:", granted)
        ok = ending and refused and granted
    print(("COMPLETE " + json.dumps(st.get("campaignComplete"))) if done else "NOT COMPLETE", "· workspace", ws)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
