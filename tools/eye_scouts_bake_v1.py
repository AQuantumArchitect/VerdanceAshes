#!/usr/bin/env python3
"""Bake the Eye of Horus's Armada scout camps: what each corner's party builds in five minutes.

Four Simple AI teams stand on the Eye's corners (the war recipe's 'corners' seats) with the scout party
from data/base_templates/eye_of_horus/scouts.json and no commander (game_verdance_scouts.lua takes it
away and stands the party in); headless, nobody else on the map, for campBakeMinutes. The structures
each team has standing at the freeze are written back into scouts.json as that corner's camp, which
the mission builder places for every drop onto the Eye (verdance.world.eye_story).

    python tools/eye_scouts_bake_v1.py                         BAR from verdance_config.json
    python tools/eye_scouts_bake_v1.py --engine DIR --write-dir DIR   a given engine and BAR data dir
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import eye_story as E, war_snapshot as W  # noqa: E402

SEED_REL = Path("singleplayer") / "verdance_ashes" / "generated" / "va_current.lua"


def lua(v) -> str:
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {lua(x)}" for k, x in v.items()) + " }"
    if isinstance(v, (list, tuple)):
        return "{ " + ", ".join(lua(x) for x in v) + " }"
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    return repr(v)


def build(cfg: dict, minutes: float) -> tuple[str, str]:
    rec = W.load_recipe(ROOT, E.MAP_ID)
    corners = [t for t in rec["teams"] if t["ally"] == "corners"]
    bake = dict(rec, teams=[dict(t, profile="simple") for t in corners], playerSeat="__none__",
                sides={"corners": rec["sides"]["corners"]}, fieldSides=None)
    script = W.startscript(bake, game_type="Verdance Ashes $VERSION", frames=int(minutes * 1800))
    for i in range(len(corners)):
        script = re.sub(r"(\[AI%d\]\s*\{\s*Name=)[^;]*;\s*ShortName=BARb;" % i,
                        r"\1Scouts%d;\n    ShortName=SimpleAI;" % i, script)
    mx, mz = rec["mapSize"]
    parties = [{"teamID": i, "zoneId": t["zoneId"], "x": round(t["startElmos"][0] / mx, 4),
                "z": round(t["startElmos"][1] / mz, 4), "arriveSeconds": 0, "units": cfg.get("party") or []}
               for i, t in enumerate(corners)]
    seed = "return " + lua({"objective": {"kind": "scout_bake"}, "scoutParties": parties}) + "\n"
    return script, seed


def camps_from(text: str, rec: dict) -> dict:
    dump = W.parse_dump(text)
    mx, mz = dump.get("map") or rec["mapSize"]
    corners = [t for t in rec["teams"] if t["ally"] == "corners"]
    out = {}
    for i, t in enumerate(corners):
        out[t["key"]] = [[u["def"], round(u["x"] / mx, 4), round(u["z"] / mz, 4), u["facing"], int(round(u["hp"] * 100)), u["kind"]]
                         for u in dump["units"] if u["team"] == i and u["kind"] == "S" and u["built"] >= 0.5]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", help="engine folder (spring-headless[.exe])")
    ap.add_argument("--write-dir", help="BAR data folder (games/, maps/)")
    ap.add_argument("--from-log", help="skip the sim: read the dump out of this log")
    args = ap.parse_args()
    cfg_path = ROOT / E.SCOUTS_REL
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    rec = W.load_recipe(ROOT, E.MAP_ID)
    minutes = float(cfg.get("campBakeMinutes") or 5)
    if args.from_log:
        text = Path(args.from_log).read_text(encoding="utf-8", errors="replace")
    else:
        if args.engine and args.write_dir:
            data = Path(args.write_dir)
            exes = [p for p in (Path(args.engine) / "spring-headless", Path(args.engine) / "spring-headless.exe") if p.exists()]
            exe = exes[0]
        else:
            from verdance_kernel import sortie as S  # type: ignore
            kcfg = S.bar_config(ROOT)
            data = Path(kcfg["barDataRoot"])
            exe = Path(S.engine_exe(kcfg, "spring-headless.exe"))
        seed_path = data / "games" / "VerdanceAshes.sdd" / SEED_REL
        script, seed = build(cfg, minutes)
        out = ROOT / "headless_runs" / f"eye_scouts_{time.strftime('%Y%m%d_%H%M%S')}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "startscript.txt").write_text(script, encoding="ascii")
        old = seed_path.read_bytes() if seed_path.is_file() else None
        seed_path.write_text(seed, encoding="utf-8")
        try:
            print(f"[scouts] {len(cfg.get('party') or [])} unit kinds a corner, {minutes:g} game minutes; engine {exe}", flush=True)
            with open(out / "engine.txt", "wb") as eng:
                subprocess.run([str(exe), "--write-dir", str(data), "--isolation", "--only-local", str(out / "startscript.txt")],
                               cwd=str(data), stdout=eng, stderr=subprocess.STDOUT, timeout=3600)
        finally:
            if old is None:
                seed_path.unlink(missing_ok=True)
            else:
                seed_path.write_bytes(old)
        text = (out / "engine.txt").read_text(encoding="utf-8", errors="replace")
    camps = camps_from(text, rec)
    if not any(camps.values()):
        print("[scouts] no structures in the dump; scouts.json left as it was")
        return 3
    cfg["camps"] = camps
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    for k, units in camps.items():
        print(f"[scouts] {k}: {len(units)} structures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
