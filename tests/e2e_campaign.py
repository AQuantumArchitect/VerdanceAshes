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
    r = subprocess.run([sys.executable, str(ws / "tools" / "verdance_story_engine_v1.py"), "init-state", "--workspace", str(ws), "--write-state"], capture_output=True, text=True, timeout=300)
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
    check("hub_state carries no truth", "controllingFaction" not in leak and '"actually"' not in leak)
    theater = hs.get("theater") or {}
    zones = theater.get("zones") or []
    map_id = theater.get("mapId") or state.get("sessionHomeMap")
    legal = [z for z in zones if z.get("preferred") or z.get("believed") in ("ours", "empty", "dark", "unsure")]
    pad = (legal[0] if legal else (zones[0] if zones else {})).get("zoneId")
    target = next((z.get("zoneId") for z in zones if z.get("openTarget")), None) or (zones[-1].get("zoneId") if zones else None)
    check("theater offers a pad and a target", bool(pad and target), f"pad={pad} target={target} zones={len(zones)}")
    # the hub preamble: seal the company with three band packs from the crew roster
    packs = []
    cp = ws / "data" / "story" / "crew_packs.json"
    if cp.is_file():
        raw = json.loads(cp.read_text(encoding="utf-8-sig"))
        heroes = raw.get("heroes") or {}
        items = heroes.items() if isinstance(heroes, dict) else [(h.get("id"), h) for h in heroes]
        packs = [str(hid) for hid, h in items if isinstance(h, dict) and h.get("role") == "band"][: int(raw.get("seatCap") or 3)]
    seal = k.seal_company(band=packs)
    check("company sealed (preamble)", bool(seal.get("ok")), json.dumps(seal)[:300])
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
    check("one pad: extraction == deployment", (intent.get("extractionZoneId") in (None, intent.get("deploymentZoneId"))), f"{intent.get('deploymentZoneId')} vs {intent.get('extractionZoneId')}")
    check("intent honours the chosen pad", str(intent.get("deploymentZoneId")) == str(pad), f"plan={pad} intent={intent.get('deploymentZoneId')}")
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
    check("homecoming advanced the campaign", int(state2.get("missionNumber") or 0) >= 2, json.dumps(home)[:300])
    bead = (state2.get("history") or [{}])[-1]
    check("bead carries the manifest", isinstance(bead.get("manifest"), dict))
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
    check("hub lastResult has the manifest and a verdict word", isinstance(lr.get("manifest"), dict) and bool(lr.get("verdict")))
    aces = {a["id"]: a for a in hs2.get("aces") or []}
    check("left hero not deployable on the hub", bool(left) and aces.get(left[0], {}).get("deployable") is False)
    print(f"-- {time.time() - t0:.1f}s · workspace {ws}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
