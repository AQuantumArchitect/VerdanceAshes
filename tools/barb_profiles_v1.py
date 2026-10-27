#!/usr/bin/env python3
"""Verdance's own BARbarian profiles, written into the mod from BAR's `hard` profile.

BARb reads its profiles through the game's VFS (luarules/configs/BARb/stable/{config,script}/<profile>),
and VerdanceAshes.sdd is loaded over BAR, so a profile under the mod's luarules/configs is a profile
BARb can be told to use (`profile=va_dig_in` in a startscript's [AI] block).

    va_dig_in   a hard BARb that fortifies: more and heavier defence at every economy cluster it holds
                (the pickets at the ramps), Guardians switched on, a beam-laser/radar/jammer base ring,
                fewer soldiers and more constructors. Armada's seats on an entrenched map.
    va_warden   a fort builder: constructors only, every cluster gets the full porcupine and its start
                becomes a fort (beam lasers, heavy lasers, flak, radar, jammer, a Guardian, one
                Rattlesnake). Seated one terrace behind the line, it is the main line.

    python tools/barb_profiles_v1.py                       from BAR's install (verdance_config.json)
    python tools/barb_profiles_v1.py --bar PATH/BAR.sdd    from a given BAR game folder
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = Path("luarules") / "configs" / "BARb" / "stable"
OUT = ROOT / "mod" / "VerdanceAshes.sdd" / REL
BASE = "hard"

# porcupine.unit.armada indices (BAR's hard build_chain.json):
LLT, TL, RL, BEAMER, HLT, CLAW, FERRET, CIR, PB, ATL, FLAK, AMB, ANNI, GUARD, AMD, RAD, JAM = range(17)


def strip_json(text: str) -> str:
    """BARb's JSON allows // and /* */ comments and trailing commas; json does not."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1]); i += 2; continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True; out.append(c); i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i); i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2); i = n if j < 0 else j + 2
        else:
            out.append(c); i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load(path: Path) -> dict:
    return json.loads(strip_json(path.read_text(encoding="utf-8-sig")))


def _turn_on(beh: dict, unit: str, **extra) -> None:
    u = beh.setdefault("behaviour", {}).setdefault(unit, {"role": ["static"]})
    u["on"] = True
    u.update(extra)


def tune_factories(fac: dict, builder_share: float) -> None:
    """Shift each lab's mix toward its constructor (column 0): builder_share of every tier."""
    for name, f in (fac.get("factory") or {}).items():
        if not name.startswith("arm"):
            continue
        for terrain in ("land", "air"):
            for tier, probs in (f.get(terrain) or {}).items():
                if not probs:
                    continue
                rest = sum(probs[1:]) or 1.0
                f[terrain][tier] = [round(builder_share, 3)] + [round(p / rest * (1 - builder_share), 3) for p in probs[1:]]


def dig_in(cfg: dict) -> dict:
    cfg = copy.deepcopy(cfg)
    por = cfg["build_chain"]["porcupine"]
    por["land"] = [LLT, BEAMER, BEAMER, RAD, RL, HLT, BEAMER, LLT, BEAMER, PB, FLAK, JAM, BEAMER, GUARD, HLT, BEAMER]
    por["amount"]["factor"] = [f * 2.5 for f in por["amount"]["factor"]]
    por["base"] = [[BEAMER, 180], [RAD, 240], [BEAMER, 300], [RL, 360], [HLT, 480], [BEAMER, 540], [JAM, 600],
                   [GUARD, 840], [FLAK, 900], [BEAMER, 960], [PB, 1100], [HLT, 1200]]
    beh = cfg["behaviour"]
    _turn_on(beh, "armguard", limit=3)
    _turn_on(beh, "corpun", limit=3)  # Cortex's Guardian (the porcupine lists share their slots)
    beh["behaviour"].setdefault("armbeamer", {"role": ["static"]})["since"] = 120
    beh["behaviour"].setdefault("corhllt", {"role": ["static"]})["since"] = 120
    beh["behaviour"].setdefault("armjamt", {"role": ["static"]})["since"] = 300
    tune_factories(cfg["factory"], 0.6)
    return cfg


def warden(cfg: dict) -> dict:
    cfg = copy.deepcopy(cfg)
    por = cfg["build_chain"]["porcupine"]
    por["land"] = [BEAMER, BEAMER, RAD, HLT, RL, FLAK, JAM, PB, GUARD, BEAMER, HLT, AMB, BEAMER]
    por["amount"]["factor"] = [f * 5.0 for f in por["amount"]["factor"]]
    por["base"] = [[BEAMER, 90], [RAD, 120], [BEAMER, 160], [RL, 220], [HLT, 300], [FLAK, 360], [JAM, 420],
                   [BEAMER, 480], [GUARD, 600], [AMB, 720], [PB, 800], [HLT, 900], [FLAK, 1000], [BEAMER, 1100]]
    beh = cfg["behaviour"]
    _turn_on(beh, "armguard", limit=2)
    _turn_on(beh, "armamb", limit=1)  # one Rattlesnake per fort: hard to get through, so few
    _turn_on(beh, "corpun", limit=2)
    _turn_on(beh, "cortoast", limit=1)  # Cortex's Rattlesnake: the Toaster
    beh["behaviour"].setdefault("armbeamer", {"role": ["static"]})["since"] = 0
    beh["behaviour"].setdefault("armjamt", {"role": ["static"]})["since"] = 0
    tune_factories(cfg["factory"], 0.9)
    return cfg


PROFILES = {"va_dig_in": dig_in, "va_warden": warden}
SECTIONS = {"behaviour": "behaviour.json", "build_chain": "build_chain.json", "factory": "factory.json"}


def write_profile(bar_stable: Path, name: str, fn) -> list:
    src_cfg, src_script = bar_stable / "config" / BASE, bar_stable / "script" / BASE
    dst_cfg, dst_script = OUT / "config" / name, OUT / "script" / name
    for d in (dst_cfg, dst_script):
        if d.exists():
            shutil.rmtree(d)
    shutil.copytree(src_cfg, dst_cfg)
    shutil.copytree(src_script, dst_script)
    cfg = {key: load(src_cfg / fname) for key, fname in SECTIONS.items()}
    cfg = fn(cfg)
    for key, fname in SECTIONS.items():
        (dst_cfg / fname).write_text(
            f"// Verdance profile {name}, generated by tools/barb_profiles_v1.py from BAR's {BASE} profile.\n"
            + json.dumps(cfg[key], indent=1) + "\n", encoding="utf-8")
    init = dst_script / "init.as"
    init.write_text(init.read_text(encoding="utf-8").replace(f'AiLog("{BASE} AngelScript Rules!")',
                                                             f'AiLog("{name} AngelScript Rules!")'), encoding="utf-8")
    # BARb resolves #include "../common.as" from script/<profile>/; the shared files are BAR's.
    return [str(p.relative_to(ROOT)) for p in (dst_cfg, dst_script)]


def bar_stable_from_config() -> Path:
    cfg = json.loads((ROOT / "verdance_config.json").read_text(encoding="utf-8-sig"))
    return Path(cfg["barDataRoot"]) / "games" / "BAR.sdd" / REL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bar", type=Path, help="BAR game folder (BAR.sdd)")
    args = ap.parse_args()
    stable = (args.bar / REL) if args.bar else bar_stable_from_config()
    if not (stable / "config" / BASE / "build_chain.json").is_file():
        print("no BARb hard profile under", stable)
        return 2
    for name, fn in PROFILES.items():
        print(name, "->", ", ".join(write_profile(stable, name, fn)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
