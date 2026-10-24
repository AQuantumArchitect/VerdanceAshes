#!/usr/bin/env python3
"""Play Koom Valley's standing war and save it as the map's starting conditions.

Six BARbarians fight a 3v3 on Koom Valley (dry): three Armada on the east flank, three Null Mercs
(Legion) on the west. The Mercs' north-west seat is the company's, played by a BARb hard_aggressive
for the sim. After twenty game minutes the engine dumps the field (every unit, its owner, how hurt it
is, each bank); the company's seat is pulled out with all its units, and the rest is written to
data/base_templates/koom_valley/war_snapshot_v1.json, which the mission builder reads for every Koom
drop (verdance.world.war_snapshot, verdance.world.theaters).

    python tools\\koom_war_bake_v1.py                  headless, 20 game minutes
    python tools\\koom_war_bake_v1.py --minutes 13     a shorter war
    python tools\\koom_war_bake_v1.py --windowed       watch it in spring.exe
    python tools\\koom_war_bake_v1.py --from-log PATH  build the snapshot from an infolog you already have

Your own campaign is untouched, but BAR's infolog and data\\games\\VerdanceAshes.sdd are shared: don't
play BAR while it runs. A run is kept in headless_runs\\koom_war_<stamp>\\ (startscript, engine output,
the dump, a summary).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import war_snapshot as W  # noqa: E402


def _costs() -> dict:
    try:
        return json.loads((ROOT / "data" / "story" / "unit_costs.json").read_text(encoding="utf-8-sig")).get("units") or {}
    except Exception:  # noqa: BLE001
        return {}


def summary(snap: dict) -> list[str]:
    rows = []
    for t in snap["teams"]:
        coms = sum(1 for u in t["units"] if u[5] == "C")
        structs = sum(1 for u in t["units"] if u[5] == "S")
        rows.append(f"  {t['key']:>3} {t['side']:<7} {t['profile']:<15} {t['unitCount']:>4} units "
                    f"({structs} structures, {coms} commander{'s' if coms != 1 else ''})  bank {t['bank']['metal']}m {t['bank']['energy']}e")
    pulled = snap.get("pulled") or {}
    rows.append(f"  pulled out: the company's seat ({pulled.get('key')}), {pulled.get('units', 0)} units, "
                f"{pulled.get('commanders', 0)} commander(s)")
    rows.append(f"  total {snap['unitCount']} units")
    return rows


def finish(infolog_text: str, recipe: dict, minutes: float, out_dir: Path | None, no_install: bool) -> int:
    dump = W.parse_dump(infolog_text)
    if not dump["units"]:
        print("[war] no VA_SHELL_UNIT lines in the infolog: the bake gadget did not dump. See", out_dir or "the log")
        return 3
    snap = W.build_snapshot(recipe, dump, costs=_costs(), minutes=minutes,
                            baked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print("[war] the war, frozen:")
    print("\n".join(summary(snap)))
    if out_dir:
        (out_dir / "snapshot.preview.json").write_text(json.dumps({k: v for k, v in snap.items() if k != "teams"}, indent=2), encoding="utf-8")
    if no_install:
        print("[war] --no-install: not written")
        return 0
    path = W.write_snapshot(ROOT, snap)
    print(f"[war] saved as Koom's starting conditions: {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=None, help="game minutes before the field is frozen (recipe: 20)")
    ap.add_argument("--windowed", action="store_true", help="spring.exe instead of spring-headless.exe")
    ap.add_argument("--isolation", action="store_true", help="pass --isolation to the engine (the old bake script did)")
    ap.add_argument("--timeout-min", type=float, default=120.0, help="wall minutes before the run is stopped")
    ap.add_argument("--no-install", action="store_true", help="build and show the snapshot, do not write it")
    ap.add_argument("--from-log", help="skip the sim: read the dump out of this infolog")
    args = ap.parse_args()

    recipe = W.load_recipe(ROOT)
    if not recipe:
        print("[war] no recipe at", W.RECIPE_REL)
        return 2
    minutes = float(args.minutes or recipe.get("minutes") or 20)
    if args.from_log:
        return finish(Path(args.from_log).read_text(encoding="utf-8", errors="replace"), recipe, minutes, None, args.no_install)

    from verdance_kernel import sortie as S  # type: ignore

    cfg = S.bar_config(ROOT)
    exe = S.engine_exe(cfg, "spring.exe" if args.windowed else "spring-headless.exe")
    prov = S.provision_map(ROOT, cfg, recipe["mapName"])
    if prov.get("ok") is False:
        print("[war] map not available:", prov)
        return 2
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "headless_runs" / f"koom_war_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = int(minutes * 60 * 30)
    script = out_dir / "startscript.txt"
    script.write_text(W.startscript(recipe, game_type=str(cfg.get("gameType") or "Verdance Ashes $VERSION"), frames=frames),
                      encoding="ascii")
    infolog = Path(cfg["infolog"])
    baseline = infolog.stat().st_size if infolog.is_file() else 0
    argv = [str(exe), "--write-dir", cfg["barDataRoot"]] + (["--isolation"] if args.isolation else []) + ["--only-local", str(script)]
    print(f"[war] {len(recipe['teams'])} BARbs on {recipe['mapName']}, {minutes:g} game minutes ({frames} frames)")
    print("[war] engine:", exe)
    print("[war] don't play BAR until this finishes. Log:", out_dir)
    t0 = time.time()
    with open(out_dir / "engine.txt", "wb") as eng:
        proc = subprocess.Popen(argv, cwd=cfg["barDataRoot"], stdin=subprocess.DEVNULL, stdout=eng, stderr=subprocess.STDOUT)
        shown = -1
        while proc.poll() is None and time.time() - t0 < args.timeout_min * 60:
            time.sleep(10)
            try:
                with open(infolog, "rb") as fh:
                    fh.seek(baseline)
                    tick = W.progress(fh.read().decode("utf-8", errors="replace"))
            except OSError:
                tick = None
            if tick and tick["frame"] != shown:
                shown = tick["frame"]
                print(f"[war] game minute {tick['frame'] / 1800:.1f} of {minutes:g} · wall {int(time.time() - t0)}s · units {tick['units']}", flush=True)
        if proc.poll() is None:
            print("[war] timed out; stopping the engine")
            proc.kill()
    time.sleep(1)
    try:
        with open(infolog, "rb") as fh:
            fh.seek(baseline)
            text = fh.read().decode("utf-8", errors="replace")
    except OSError:
        text = ""
    (out_dir / "infolog.txt").write_text(text, encoding="utf-8")
    rc = finish(text, recipe, minutes, out_dir, args.no_install)
    (out_dir / "summary.json").write_text(json.dumps({"exit": rc, "wallSeconds": int(time.time() - t0), "minutes": minutes}), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
