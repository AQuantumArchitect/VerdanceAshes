#!/usr/bin/env python3
"""End-to-end campaign regression without BAR.

Copies the workspace to a scratch dir, starts a fresh campaign, stamps a plan, materialises the
intent (what the Drop would carry into BAR), fakes the sortie's result with a manifest, brings it
home, and checks the belief lane did its job. Run it before and after any refactor:

    UMWELT_SRC=/path/to/umwelt/src python3 tests/e2e_campaign.py

Exit code 0 = every check passed. Prints one line per check.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
FAILED = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global FAILED
    print(("ok   " if ok else "FAIL ") + label + (("  " + detail) if detail else ""))
    if not ok:
        FAILED += 1


def fresh_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="va_e2e_"))
    for name in ("tools", "data", "app", "mod", "scripts", "docs", "VERSION"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, ws / name, ignore=shutil.ignore_patterns("__pycache__", "runtime_cache", "fx", "out"))
        elif src.is_file():
            shutil.copy2(src, ws / name)
    for d in ("state", "inbox", "outbox", "ledger", "export"):
        (ws / d).mkdir(exist_ok=True)
    cfg = {"barDataRoot": str(ws / "fake_bar" / "data"), "devMode": False}
    (ws / "verdance_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return ws


def main() -> int:
    os.environ.setdefault("VA_PERSPECTIVES_SYNC", "1")
    os.environ.setdefault("VA_PERSPECTIVES_NOSPAWN", "1")
    ws = fresh_workspace()
    sys.path.insert(0, str(ws / "tools"))
    os.chdir(ws)
    t0 = time.time()

    # 1. fresh state
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ws / "tools"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    r = subprocess.run([sys.executable, "-m", "verdance.campaign.engine", "init-state", "--workspace", str(ws), "--write-state"],
                       capture_output=True, text=True, timeout=300, cwd=str(ws), env=env)
    state_path = ws / "state" / "campaign_state.json"
    check("init-state writes mission 1", state_path.is_file() and json.loads(state_path.read_text(encoding="utf-8-sig")).get("missionNumber") in (1, None), (r.stderr or r.stdout)[-300:] if r.returncode else "")
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))

    # 2. kernel: hub state, stamp, intent
    from verdance_kernel.api import CampaignKernel  # type: ignore
    k = CampaignKernel(ws)
    hub = k.rebuild_hub(skip_apply=True)
    hs_path = ws / "app" / "showoff" / "hub_state.json"
    hs = json.loads(hs_path.read_text(encoding="utf-8-sig")) if hs_path.is_file() else {}
    check("hub_state has belief/camp/exposure", all(key in hs for key in ("belief", "camp", "exposure")), str(sorted(hs.keys()))[:200])
    leak = json.dumps(hs)
    check("hub_state carries no truth", "controllingFaction" not in leak and '"actually"' not in leak
          and not any(k in hs for k in ("graph", "campaignRho", "spectral", "graphPressure")), "true world graph on the hub")
    check("hub shows the story state", bool((hs.get("storyState") or {}).get("nodes")))
    theater = hs.get("theater") or {}
    zones = theater.get("zones") or []
    map_id = theater.get("mapId") or state.get("sessionHomeMap")
    # a pad is a door the company holds (or ground believed ours); never open ground
    held = {end["zoneId"] for r in ((hs.get("world") or {}).get("roads") or []) for end in (r["a"], r["b"])
            if end.get("held") and end.get("mapId") == map_id}
    legal = [z for z in zones if z.get("zoneId") in held or z.get("believed") == "ours"]
    pad = (legal[0] if legal else (zones[0] if zones else {})).get("zoneId")
    target = next((z.get("zoneId") for z in zones if z.get("openTarget")), None) or (zones[-1].get("zoneId") if zones else None)
    check("theater offers a pad and a target", bool(pad and target), f"pad={pad} target={target} zones={len(zones)}")
    # the hub preamble: Ketha always; three picks, the first is you and must walk
    bad = k.seal_company(band=["anvil", "solarium", "halbard"])
    check("only starters can be picked (Anvil unlocks by rescue)", not bad.get("ok") and "not unlocked" in str(bad.get("error")), json.dumps(bad)[:200])
    seal = k.seal_company(band=["pavise", "solarium", "halbard"])
    check("company sealed (preamble)", bool(seal.get("ok")), json.dumps(seal)[:300])
    st_sealed = json.loads(state_path.read_text(encoding="utf-8-sig"))
    you_row = next((h for h in (st_sealed.get("roster") or {}).get("heroes") or [] if h.get("heroId") == "pavise"), {})
    check("you are Pavise, mission-critical; Ketha is core", (st_sealed.get("company") or {}).get("you") == "pavise" and you_row.get("missionCritical") is True
          and (st_sealed.get("company") or {}).get("core") == ["ketha"], json.dumps(st_sealed.get("company"))[:200])
    hub = k.rebuild_hub(skip_apply=True)
    hs = json.loads(hs_path.read_text(encoding="utf-8-sig"))
    plan = {"schemaVersion": "verdance-deploy-plan/1.0", "mapId": map_id, "deployAces": [a["id"] for a in (hs.get("aces") or []) if a.get("deployable")][:2],
            "marks": {"deployZoneId": pad, "captureZoneIds": [target], "secondaryCaptureZoneIds": []}}
    dep = k.commit_deploy(plan, launch=False) if "launch" in k.commit_deploy.__code__.co_varnames else k.commit_deploy(plan)
    intent_path = ws / "outbox" / "next_mission_intent.json"
    # the kernel may run the deploy asynchronously; wait for the intent
    for _ in range(120):
        if intent_path.is_file():
            break
        time.sleep(0.5)
    check("stamp + intent written", intent_path.is_file(), json.dumps(dep)[:300] if not intent_path.is_file() else "")
    intent = json.loads(intent_path.read_text(encoding="utf-8-sig")) if intent_path.is_file() else {}
    check("intent carries company intel (belief, not truth)", isinstance(intent.get("intel"), dict) and intent["intel"].get("perspective") == "company")
    check("intent says where each faction may reinforce from (its own zones)", isinstance(intent.get("entryZones"), dict), str(intent.get("entryZones"))[:160])
    check("one pad: extraction == deployment", (intent.get("extractionZoneId") in (None, intent.get("deploymentZoneId"))), f"{intent.get('deploymentZoneId')} vs {intent.get('extractionZoneId')}")
    check("intent honours the chosen pad", str(intent.get("deploymentZoneId")) == str(pad), f"plan={pad} intent={intent.get('deploymentZoneId')}")

    # hot drop: the field is loaded with every candidate pack; the Drop names who goes
    from verdance_kernel import hot_drop, sortie as _sortie  # type: ignore
    bar_root = ws / "fake_bar" / "data"
    bar_root.mkdir(parents=True, exist_ok=True)
    token = hot_drop.arm(ws, bar_root)
    k._hot = {"token": token, "pid": 4242, "mapId": map_id, "plan": "", "dropped": False}
    real_alive, real_status = _sortie.pid_alive, k.hot_drop_status
    _sortie.pid_alive = lambda pid: True
    try:
        k.hot_drop_status = lambda: {"phase": "loading"}
        early = k.drop({"crewBand": ["solarium"], "reserveBring": {}})
        check("no drop while the field is still loading", not early.get("ok"), json.dumps(early)[:200])
        k.hot_drop_status = lambda: {"phase": "ready"}
        dropped = k.drop({"crewBand": ["solarium"], "reserveBring": {}})
        line = (bar_root / "LuaUI" / "Config" / "verdance" / "drop.txt").read_text(encoding="utf-8").strip() if dropped.get("ok") else ""
        check("the drop file carries the token and the chosen pack", line.startswith(token + "|") and line.split("|")[1] == ",".join(dropped.get("crewBand") or []) and "solarium" in line.split("|")[1], line or json.dumps(dropped)[:200])
        intent_after = json.loads(intent_path.read_text(encoding="utf-8-sig"))
        check("the homecoming reads who actually went", intent_after.get("deployAces") == dropped.get("deployAces") and intent_after.get("crewBand") == dropped.get("crewBand"), json.dumps(intent_after.get("deployAces")))
        check("a second drop changes nothing", k.drop({"crewBand": []}).get("already") is True)
    finally:
        _sortie.pid_alive = real_alive
        k.hot_drop_status = real_status
        k._clear_hot()
        hot_drop.disarm(ws)
    if "--stop-after-intent" in sys.argv:
        print(f"-- stopped after intent · workspace {ws}")
        return 1 if FAILED else 0
    gen = ws / "mod" / "VerdanceAshes.sdd" / "singleplayer" / "verdance_ashes" / "generated"
    check("va_intel_current.lua + va_pad_current.lua written", (gen / "va_intel_current.lua").is_file() and (gen / "va_pad_current.lua").is_file())

    # 3. fake the sortie: extracted, objective done, one hero left behind, one zone seen
    hero_ids = [a["id"] for a in (hs.get("aces") or [])]
    going = hero_ids[:1]
    left = hero_ids[1:2]
    seen = {str(target): 0.8, str(pad): 0.95}
    result = {
        "schemaVersion": "verdance-match-result/2.0",
        "campaignId": state.get("campaignId") or "verdance_ashes",
        "resultKey": f"e2e|{intent.get('missionId')}|{int(time.time())}",
        "missionId": intent.get("missionId") or "va_001",
        "missionNumber": int(intent.get("missionNumber") or state.get("missionNumber") or 1),
        "mapId": map_id, "deploymentMapId": map_id,
        "status": "extracted", "verdict": "extracted",
        "objectiveComplete": True, "allObjectivesDone": True,
        "objectiveResults": [{"kind": (intent.get("objectiveTarget") or {}).get("kind") or "eco_raid", "targetZoneId": target, "done": True}],
        "secondaryResults": [],
        "playerSurvivors": {"corthud": 4},
        "heroResults": {h: {"heroId": h, "name": h, "state": "alive", "outcome": "alive"} for h in hero_ids},
        "tenebriumBank": 2, "tenebriumLooted": 2, "tenebriumSpent": 0,
        "observedZones": dict(seen), "beliefExport": {z: {"eta": e, "enemyNow": 0 if z == pad else 4, "friendNow": 3 if z == pad else 0} for z, e in seen.items()},
        "manifest": {
            "schema": "verdance-manifest/1", "kind": "extracted", "destination": "home",
            "pad": {"zoneId": pad, "label": pad, "x": 1000, "z": 1000, "radius": 560},
            "going": {"heroes": [{"heroId": h, "name": h} for h in going], "units": {"corthud": 4}, "unitCount": 4, "metal": 800},
            "staying": {"heroes": [{"heroId": h, "name": h, "zoneId": target, "label": target} for h in left], "units": {}, "unitCount": 0,
                        "structures": {str(pad): {"count": 2, "metal": 400, "label": pad}}, "structureCount": 2, "metal": 400},
            "enemyOnPad": 0, "seen": seen, "tenebrium": 2, "objectiveComplete": True,
        },
    }
    (ws / "inbox").mkdir(exist_ok=True)
    (ws / "inbox" / "latest_va_result.json").write_text(json.dumps(result), encoding="utf-8")
    home = k.bring_home() if "extract" not in k.bring_home.__code__.co_varnames else k.bring_home(extract=False)
    state2 = json.loads(state_path.read_text(encoding="utf-8-sig"))
    hr = ws / "outbox" / "hub_result.latest.json"
    check("the open hub can see the homecoming (hub_result kept, with at)",
          hr.is_file() and bool(json.loads(hr.read_text(encoding="utf-8-sig")).get("at")))
    check("homecoming advanced the campaign", int(state2.get("missionNumber") or 0) >= 2, json.dumps(home)[:300])
    bead = (state2.get("history") or [{}])[-1]
    check("bead carries the manifest", isinstance(bead.get("manifest"), dict))
    check("what lifted is in the reserve", ((state2.get("roster") or {}).get("reserve") or {}).get("corthud") == 4,
          json.dumps((state2.get("roster") or {}).get("reserve"))[:200])
    verdict = (bead.get("verdict") or (bead.get("manifest") or {}).get("verdict") or "").lower()
    check("verdict derived from manifest (partial: a person left)", verdict in ("partial", "hinge"), f"verdict={verdict!r}")
    people = ((state2.get("camp") or {}).get("people") or {})
    check("left hero is in the field", bool(left) and people.get(left[0], {}).get("where") == "field", json.dumps(people)[:200])
    intel = ws / "outbox" / "intel.latest.json"
    check("belief frame written", intel.is_file())
    if intel.is_file():
        fr = json.loads(intel.read_text(encoding="utf-8-sig"))
        rows = [n for n in fr.get("nodes") or [] if n.get("node") == target and n.get("role") == "held"]
        # an observation at eta 0.8 moves belief toward what the ground showed; the row must be current and carry the eta
        check("seen zone observed into belief (current, eta 0.8)", bool(rows) and rows[0].get("state") == "current" and abs(float(rows[0].get("eta") or 0) - 0.8) < 0.05, json.dumps(rows[:1])[:200])
    hs2 = json.loads(hs_path.read_text(encoding="utf-8-sig"))
    lr = hs2.get("lastResult") or {}
    check("hub shows the reserve and the lift limit", bool((hs2.get("reserve") or {}).get("liftCap")) and any(u.get("unitDef") == "corthud" for u in (hs2.get("reserve") or {}).get("units") or []))
    check("hub lastResult has the manifest and a verdict word", isinstance(lr.get("manifest"), dict) and bool(lr.get("verdict")))
    aces = {a["id"]: a for a in hs2.get("aces") or []}
    check("left hero not deployable on the hub", bool(left) and aces.get(left[0], {}).get("deployable") is False)
    print(f"-- {time.time() - t0:.1f}s · workspace {ws}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
