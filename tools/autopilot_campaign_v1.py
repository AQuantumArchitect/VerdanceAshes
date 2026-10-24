#!/usr/bin/env python3
"""Autopilot: a BARbarian AI plays the company's seat, sortie after sortie, through the real kernel.

Each sortie does what playthrough_campaign.py does (take the node's recommended card, plan it the
way the hub does, commit the drop), then patches the startscript so the company's team is BARb
(profile hard_aggressive by default) with a spectator host, launches spring-headless, and lets the
kernel's own SortieWatch bring the result home. The autopilot gadget calls the extraction (the pad
moves to wherever most of the company stands: extract anywhere).

It runs on a COPY of the workspace (autopilot_runs/<stamp>/ws), so your own campaign is untouched.
BAR's data\\games\\VerdanceAshes.sdd and infolog.txt are shared: don't play while it runs.

    python tools\\autopilot_campaign_v1.py --sorties 20
    python tools\\autopilot_campaign_v1.py --band verse,vane,halbard --boost verse=4.0 --prefer simmers --speed 10
    python tools\\autopilot_campaign_v1.py --windowed          (watch it in spring.exe)

Writes autopilot_runs/<stamp>/log.jsonl (one row per sortie), sortie_<n>.infolog.txt (this sortie's
slice of the infolog), and summary.json. Exit 0 = the campaign completed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def jload(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig")) if p.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


# ----------------------------------------------------------------------------- workspace copy

def copy_workspace(dest: Path, bar_root: str) -> Path:
    ws = dest / "ws"
    for name in ("tools", "data", "app", "mod", "scripts", "docs", "VERSION"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, ws / name, ignore=shutil.ignore_patterns("__pycache__", "runtime_cache", "fx", "out"))
        elif src.is_file():
            shutil.copy2(src, ws / name)
    for d in ("state", "inbox", "outbox", "ledger", "export", "playable_runs"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    cfg = jload(ROOT / "verdance_config.json")
    cfg.update({"barDataRoot": bar_root, "workspace": str(ws), "devMode": False})
    (ws / "verdance_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return ws


# ----------------------------------------------------------------------------- the startscript

def patch_startscript(text: str, *, profile: str, speed: int, minutes: float, settle: int) -> tuple[str, int]:
    """Company team -> BARb; the human becomes a spectator; autopilot modoptions in."""
    m = re.search(r"\[PLAYER0\]\s*\{(.*?)\}", text, re.S)
    if not m:
        raise RuntimeError("startscript has no [PLAYER0]")
    body = m.group(1)
    team = int((re.search(r"Team=(\d+);", body) or [None, "0"])[1])
    body2 = re.sub(r"Spectator=\d+;", "Spectator=1;", body)
    if "Spectator=" not in body2:
        body2 += "    Spectator=1;\n"
    text = text[:m.start(1)] + body2 + text[m.end(1):]
    n_ai = len(re.findall(r"\[AI\d+\]", text))
    ai = (f"  [AI{n_ai}]\n  {{\n    Host=0;\n    IsFromDemo=0;\n    Name=Autopilot(BARb {profile});\n    ShortName=BARb;\n"
          f"    Team={team};\n    Version=stable;\n    [Options]\n    {{\n      profile={profile};\n    }}\n  }}\n\n")
    i = text.index("[PLAYER0]")
    text = text[:i] + ai[2:] + "  " + text[i:]
    text = re.sub(r"NumUsers=(\d+);", lambda mm: f"NumUsers={int(mm.group(1)) + 1};", text, count=1)
    text = re.sub(r"RecordDemo=\d+;", "RecordDemo=0;", text, count=1)
    mods = (f"va_autopilot=1;\n    va_extract_anywhere=1;\n    va_headless_autostart=1;\n    va_headless_fastwin=0;\n    va_headless_quit=1;\n    va_headless_speed={speed};\n    va_autopilot_speed={speed};\n"
            f"    va_autopilot_minutes={minutes};\n    va_autopilot_settle={settle};\n    ")
    text = text.replace("va_campaign=1;", "va_campaign=1;\n    " + mods.rstrip(), 1)
    return text, team


# ----------------------------------------------------------------------------- launch + watch

def launch(ws: Path, *, headless: bool, run_dir: Path, n: int):
    from verdance_kernel import sortie as S  # type: ignore
    cfg = S.bar_config(ws)
    script = S.startscript_from_manifest(ws)
    if script is None:
        return {"ok": False, "reason": "no startscript"}
    map_name = None
    for line in script.read_text(encoding="utf-8", errors="replace").splitlines():
        mm = re.match(r"\s*MapName=(.+);", line)
        if mm:
            map_name = mm.group(1).strip()
            break
    prov = S.provision_map(ws, cfg, map_name or "")
    if prov.get("ok") is False:
        return {"ok": False, "reason": f"map {map_name} not provisioned", "provision": prov}
    seed = Path(cfg["seedDestination"])
    gen_src = ws / "mod" / "VerdanceAshes.sdd" / "singleplayer" / "verdance_ashes" / "generated"
    for name in ("va_pad_current.lua", "va_intel_current.lua"):
        src = gen_src / name
        if src.is_file() and seed.parent.is_dir():
            try:
                (seed.parent / name).write_bytes(src.read_bytes())
            except Exception:  # noqa: BLE001
                pass
    exe = S.engine_exe(cfg, "spring-headless.exe" if headless else "spring.exe")
    infolog = Path(cfg["infolog"])
    baseline = infolog.stat().st_size if infolog.is_file() else 0
    out = open(run_dir / f"sortie_{n:02d}.engine.txt", "wb")
    args = [str(exe), "--write-dir", cfg["barDataRoot"], "--only-local", str(script)]
    proc = subprocess.Popen(args, cwd=cfg["barDataRoot"], stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
    return {"ok": True, "pid": proc.pid, "proc": proc, "engine": str(exe), "startScriptPath": str(script),
            "infologPath": str(infolog), "infologBaseline": baseline, "mapName": map_name}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sorties", type=int, default=20)
    ap.add_argument("--band", default="verse,vane,halbard", help="three packs (hero ids); the first is you")
    ap.add_argument("--boost", default="verse=4.0", help="hero=xp,... set before sealing (unlocks them); '' for none")
    ap.add_argument("--profile", default="hard_aggressive", help="BARb profile: hard_aggressive | hard | medium | easy")
    ap.add_argument("--speed", type=int, default=8)
    ap.add_argument("--minutes", type=float, default=15.0, help="game minutes before the company leaves regardless")
    ap.add_argument("--settle", type=int, default=40, help="game seconds held after the objective completes")
    ap.add_argument("--windowed", action="store_true", help="spring.exe instead of spring-headless.exe")
    ap.add_argument("--prefer", default="simmers", help="take a deploy card whose map id contains this when the node offers one ('' = recommended)")
    ap.add_argument("--max-stalls", type=int, default=3, help="stop after this many sorties in a row that did not advance")
    args = ap.parse_args()

    os.environ.setdefault("VA_PERSPECTIVES_SYNC", "1")
    os.environ.setdefault("VA_PERSPECTIVES_NOSPAWN", "1")
    sys.path.insert(0, str(ROOT / "tests"))
    from playthrough_campaign import pick_choice, plan_for  # noqa: E402

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / "autopilot_runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "tools"))
    from verdance_kernel import sortie as S  # type: ignore
    bar_root = S.bar_config(ROOT)["barDataRoot"]
    print(f"[autopilot] run {run_dir}")
    print(f"[autopilot] copying the workspace (your campaign is untouched)")
    ws = copy_workspace(run_dir, bar_root)
    sys.path.insert(0, str(ws / "tools"))
    os.chdir(ws)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ws / "tools"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    r = subprocess.run([sys.executable, "-m", "verdance.campaign.engine", "init-state", "--workspace", str(ws), "--write-state"],
                       capture_output=True, text=True, timeout=600, cwd=str(ws), env=env)
    if r.returncode:
        print("[autopilot] init-state failed:", (r.stderr or r.stdout)[-800:])
        return 2
    for mod in [k for k in sys.modules if k.startswith(("verdance_kernel", "verdance"))]:
        del sys.modules[mod]  # import from the copy from here on
    from verdance_kernel.api import CampaignKernel  # type: ignore
    from verdance_kernel import sortie as S  # type: ignore # noqa: F811
    k = CampaignKernel(ws)
    sp, hp, ip = ws / "state" / "campaign_state.json", ws / "app" / "showoff" / "hub_state.json", ws / "outbox" / "next_mission_intent.json"
    boards = {}
    for f in (ws / "data" / "zone_maps").glob("*.json"):
        d = jload(f)
        if d:
            boards[d.get("mapId") or f.stem] = d

    band = [b.strip() for b in args.band.split(",") if b.strip()]
    boosts = {}
    for part in filter(None, (args.boost or "").split(",")):
        h, _, x = part.partition("=")
        boosts[h.strip()] = float(x or 4.0)
    k.rebuild_hub(skip_apply=True)
    st = jload(sp)
    sys.path.insert(0, str(ws / "tools"))
    from verdance.company.company import unlock_pool_ids, load_crew_packs  # type: ignore
    pool = set(unlock_pool_ids(st, load_crew_packs(ws)))
    if not set(band) <= pool or boosts:
        # the autopilot's company: put its band (and anyone boosted) on the hire board
        st["unlockPool"] = sorted(pool | set(band) | set(boosts))
    for h in (st.get("roster") or {}).get("heroes") or []:
        if h.get("heroId") in boosts:
            h["xp"] = h["peakBarXp"] = boosts[h["heroId"]]
    sp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    seal = k.seal_company(band=band)
    print(f"[autopilot] company {band} boost {boosts} -> {'sealed' if seal.get('ok') else seal}")
    if not seal.get("ok"):
        return 2

    log_path = run_dir / "log.jsonl"
    stalls, rows = 0, []
    for n in range(1, args.sorties + 1):
        k.rebuild_hub(skip_apply=True)
        hs, st = jload(hp), jload(sp)
        if st.get("campaignComplete"):
            break
        choice, nchoices = pick_choice(hs)
        if args.prefer:
            deck = [c for c in ((hs.get("node") or {}).get("choices") or []) if c.get("kind") == "deploy"]
            liked = [c for c in deck if args.prefer in str(((c.get("effect") or {}).get("mapId")) or "")]
            choice = liked[0] if liked else choice
        row = {"n": n, "mission": st.get("missionNumber"), "act": (hs.get("arc") or {}).get("id"), "choice": (choice or {}).get("id")}
        if not choice:
            row["stall"] = "no deploy choice"
            rows.append(row)
            break
        plan = plan_for(hs, choice, boards)
        row.update(map=plan["mapId"], pad=plan["marks"]["deployZoneId"], target=(plan["marks"]["captureZoneIds"] or [None])[0])
        if ip.exists():
            ip.unlink()
        t0 = time.time()
        dep = k.commit_deploy(plan, launch=False)
        intent = jload(ip)
        row["objective"] = (intent.get("objectiveTarget") or {}).get("kind")
        row["setPiece"] = (intent.get("theater") or {}).get("kind")
        if not dep.get("ok"):
            row["stall"] = "deploy refused: " + str(dep.get("error") or "")[:300]
            rows.append(row)
            print(json.dumps(row))
            break
        script = S.startscript_from_manifest(ws)
        text, team = patch_startscript(script.read_text(encoding="utf-8", errors="replace"), profile=args.profile,
                                       speed=args.speed, minutes=args.minutes, settle=args.settle)
        script.write_text(text, encoding="utf-8")
        shutil.copy2(script, run_dir / f"sortie_{n:02d}.startscript.txt")
        rep = launch(ws, headless=not args.windowed, run_dir=run_dir, n=n)
        if not rep.get("ok"):
            row["stall"] = "launch failed: " + str(rep.get("reason"))
            rows.append(row)
            print(json.dumps(row))
            break
        print(f"[autopilot] sortie {n}: {row['map']} {row['objective']} pad={row['pad']} target={row['target']} (pid {rep['pid']})")
        proc = rep.pop("proc")
        watch = S.SortieWatch(ws, k.bring_home, k._incomplete_home)
        watch.watch(rep)
        wall_cap = 60 * 60
        while watch.phase not in ("home", "closed-without-result") and time.time() - t0 < wall_cap:
            time.sleep(3)
        if proc.poll() is None:
            proc.kill()
            row["killed"] = True
        time.sleep(1)
        watch.stop()
        try:
            with open(rep["infologPath"], "rb") as fh:
                fh.seek(int(rep["infologBaseline"]))
                (run_dir / f"sortie_{n:02d}.infolog.txt").write_bytes(fh.read())
        except Exception:  # noqa: BLE001
            pass
        crash = None
        try:
            txt = (run_dir / f"sortie_{n:02d}.infolog.txt").read_text(encoding="utf-8", errors="replace")
            if "has crashed" in txt:
                lines = [l for l in txt.splitlines() if "VA_" in l and "has crashed" not in l]
                crash = {"lastVerdanceLine": (lines[-1][:240] if lines else None)}
        except Exception:  # noqa: BLE001
            pass
        st2 = jload(sp)
        bead = (st2.get("history") or [{}])[-1]
        heroes = {h.get("heroId"): h.get("status") for h in ((st2.get("roster") or {}).get("heroes") or [])
                  if h.get("heroId") in set(band) | {"ketha"} | set(boosts)}
        row.update(watch=watch.phase, wallSeconds=round(time.time() - t0), verdict=bead.get("verdict"),
                   extraction=bead.get("extractionStatus"), after=st2.get("missionNumber"), heroes=heroes,
                   doors=sorted(z for z, d in (st2.get("doors") or {}).items() if d.get("held")),
                   complete=bool(st2.get("campaignComplete")))
        advanced = int(st2.get("missionNumber") or 0) > int(st.get("missionNumber") or 0) or st2.get("campaignComplete")
        stalls = 0 if advanced else stalls + 1
        rows.append(row)
        print(json.dumps(row))
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        if crash:
            row["crashed"] = crash
            print("[autopilot] the engine CRASHED; stopping. Last Verdance line:", crash["lastVerdanceLine"])
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"n": n, "crashed": crash}) + "\n")
            break
        if st2.get("campaignComplete") or stalls >= args.max_stalls:
            break

    st = jload(sp)
    summary = {"complete": bool(st.get("campaignComplete")), "outcome": st.get("campaignComplete"), "sorties": rows,
               "band": band, "boost": boosts, "profile": args.profile, "workspace": str(ws)}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("[autopilot]", "COMPLETE " + json.dumps(st.get("campaignComplete")) if summary["complete"] else "NOT COMPLETE", "·", run_dir)
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
