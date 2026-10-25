#!/usr/bin/env python3
"""Play a map's standing war and save it as the map's starting conditions.

Each war is BARbarians fighting on the map, dry, from the seats in
data/base_templates/<map>/war_recipe.json. After the recipe's game minutes the engine dumps the field
(every unit, its owner, how hurt it is, each bank); the company's seat is pulled out with all its
units, and the rest is written to data/base_templates/<map>/war_snapshot_v1.json, which the mission
builder reads for every drop onto that map (verdance.world.war_snapshot, verdance.world.theaters).

    python tools\\war_bake_v1.py                       every map that has a recipe and no snapshot yet
    python tools\\war_bake_v1.py --map tabula          one map (again, if it was baked already)
    python tools\\war_bake_v1.py --all                 every map, re-baked
    python tools\\war_bake_v1.py --map koom_valley --minutes 30     a longer war
    python tools\\war_bake_v1.py --windowed            watch it in spring.exe
    python tools\\war_bake_v1.py --map tabula --from-log PATH       build the snapshot from an infolog you already have

Your own campaign is untouched, but BAR's infolog and data\\games\\VerdanceAshes.sdd are shared: don't
play BAR while it runs. A run is kept in headless_runs\\war_<map>_<stamp>\\ (startscript, engine output,
the dump, a summary). Maps run one after another; one failing does not stop the rest.
"""
from __future__ import annotations

import argparse
import json
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
        rows.append(f"  {t['key']:>7} {t['side']:<7} {t['profile']:<15} {t['unitCount']:>4} units "
                    f"({structs} structures, {coms} commander{'s' if coms != 1 else ''})  bank {t['bank']['metal']}m {t['bank']['energy']}e")
    pulled = snap.get("pulled") or {}
    if pulled:
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
    print(f"[war] {recipe['mapId']}, frozen:")
    print("\n".join(summary(snap)))
    if out_dir:
        (out_dir / "snapshot.preview.json").write_text(json.dumps({k: v for k, v in snap.items() if k != "teams"}, indent=2), encoding="utf-8")
    if no_install:
        print("[war] --no-install: not written")
        return 0
    path = W.write_snapshot(ROOT, snap)
    print(f"[war] saved as the starting conditions: {path}")
    return 0


def bake(map_id: str, args, cfg, S) -> int:
    recipe = W.load_recipe(ROOT, map_id)
    if not recipe:
        print("[war] no recipe at", W.recipe_rel(map_id))
        return 2
    minutes = float(args.minutes or recipe.get("minutes") or 20)
    exe = S.engine_exe(cfg, "spring.exe" if args.windowed else "spring-headless.exe")
    prov = S.provision_map(ROOT, cfg, recipe["mapName"])
    if prov.get("ok") is False:
        print("[war] map not available:", prov)
        return 2
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "headless_runs" / f"war_{map_id}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = int(minutes * 60 * 30)
    script = out_dir / "startscript.txt"
    script.write_text(W.startscript(recipe, game_type=str(cfg.get("gameType") or "Verdance Ashes $VERSION"), frames=frames),
                      encoding="ascii")
    infolog = Path(cfg["infolog"])
    baseline = infolog.stat().st_size if infolog.is_file() else 0
    argv = [str(exe), "--write-dir", cfg["barDataRoot"]] + (["--isolation"] if args.isolation else []) + ["--only-local", str(script)]
    print(f"[war] {map_id}: {len(recipe['teams'])} BARbs, {minutes:g} game minutes ({frames} frames)")
    print("[war] engine:", exe)
    print("[war] don't play BAR until this finishes. Log:", out_dir, flush=True)
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
                print(f"[war] {map_id} game minute {tick['frame'] / 1800:.1f} of {minutes:g} · wall {int(time.time() - t0)}s · units {tick['units']}", flush=True)
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
    (out_dir / "summary.json").write_text(json.dumps({"exit": rc, "wallSeconds": int(time.time() - t0), "minutes": minutes, "map": map_id}), encoding="utf-8")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", default=[], help="a map id (repeat, or comma-separate)")
    ap.add_argument("--all", action="store_true", help="every map that has a recipe, baked again")
    ap.add_argument("--minutes", type=float, default=None, help="game minutes before the field is frozen (recipe's own by default)")
    ap.add_argument("--windowed", action="store_true", help="spring.exe instead of spring-headless.exe")
    ap.add_argument("--isolation", action="store_true", help="pass --isolation to the engine (the old bake script did)")
    ap.add_argument("--timeout-min", type=float, default=90.0, help="wall minutes per map before its run is stopped")
    ap.add_argument("--no-install", action="store_true", help="build and show the snapshot, do not write it")
    ap.add_argument("--from-log", help="skip the sim: read the dump out of this infolog (needs one --map)")
    args = ap.parse_args()

    known = W.war_maps(ROOT)
    wanted = [m for chunk in args.map for m in chunk.split(",") if m]
    if args.all:
        wanted = known
    elif not wanted:
        wanted = [m for m in known if W.load_snapshot(ROOT, m) is None]
        if not wanted:
            print("[war] every map with a recipe already has a war; --map NAME or --all to bake again")
            return 0
    unknown = [m for m in wanted if m not in known]
    if unknown:
        print("[war] no recipe for", ", ".join(unknown), "- maps with one:", ", ".join(known))
        return 2

    if args.from_log:
        if len(wanted) != 1:
            print("[war] --from-log needs exactly one --map")
            return 2
        recipe = W.load_recipe(ROOT, wanted[0])
        minutes = float(args.minutes or recipe.get("minutes") or 20)
        return finish(Path(args.from_log).read_text(encoding="utf-8", errors="replace"), recipe, minutes, None, args.no_install)

    from verdance_kernel import sortie as S  # type: ignore

    cfg = S.bar_config(ROOT)
    results = {}
    for m in wanted:
        print(f"\n[war] ===== {m} ({len(results) + 1} of {len(wanted)}) =====", flush=True)
        try:
            results[m] = bake(m, args, cfg, S)
        except Exception as e:  # noqa: BLE001
            print(f"[war] {m} failed: {e}")
            results[m] = 1
    print("\n[war] done:", ", ".join(f"{m} {'ok' if rc == 0 else 'FAILED (' + str(rc) + ')'}" for m, rc in results.items()))
    return 0 if all(rc == 0 for rc in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
