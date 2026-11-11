#!/usr/bin/env python3
"""The engine's hero minds are Umwelt's (plan: docs/PLAN_pathway_and_umwelt_minds.md, Part 2).

va_umwelt_lite.lua claims to be a faithful port of Umwelt's per-role dynamics on the GameHost path with
learning frozen. This holds it to that: the same clusters and the same recorded streams of readings
(irregular gaps, quiet spells longer than the catch-up cap, readings that overwrite one another before an
ingest) run on Umwelt itself, in a fresh process in double precision, and on the Lua port under Lua 5.4.
Every role's value and confidence after every ingest must agree to 1e-9.

Skipped when Umwelt (UMWELT_SRC) or liblua5.4 is missing."""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from verdance.company import hero_mind  # noqa: E402

TOL = 1e-9
LITE = "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_umwelt_lite.lua"


def _umwelt_src() -> str | None:
    src = os.environ.get("UMWELT_SRC")
    if src and (Path(src) / "umwelt").is_dir():
        return src
    cache = ROOT / "export" / "cache" / "umwelt" / "src"
    return str(cache) if (cache / "umwelt").is_dir() else None


def _stream(heroes, seed: int, n: int):
    """Readings at uneven gaps: some quiet beats, some bursts, a long quiet past the catch-up cap, and a
    role read twice before its ingest (the later reading wins)."""
    rng = random.Random(seed)
    gaps = [0.3, 0.6, 0.9, 1.2, 1.8, 2.4, 6.0]
    out = []
    for i in range(n):
        gap = gaps[rng.randrange(len(gaps))]
        if i == n // 2:
            gap = 45.0                                     # 75 holds of quiet: capped at 32 + 1 steps
        seen = []
        for _ in range(rng.randrange(4)):
            seen.append([rng.choice(heroes), rng.choice(hero_mind.ROLES), round(rng.random(), 3), round(rng.random(), 3)])
        if i % 7 == 3 and seen:
            h, r = seen[0][0], seen[0][1]
            seen.append([h, r, round(rng.random(), 3), 1.0])   # the same role again: this one stands
        out.append([gap, seen])
    return out


CASES = [
    # a bonded pair: mood flows both ways
    {"heroes": ["vane", "ketha"], "bridges": [["vane", "ketha", 0.6]]},
    # rivals: their moods pull apart
    {"heroes": ["verse", "halbard"], "bridges": [["verse", "halbard", -0.45]]},
    # a chain of three, bridges in order
    {"heroes": ["veil", "spoke", "solarium"], "bridges": [["veil", "spoke", 0.3], ["spoke", "solarium", 0.8]]},
    # alone on the drop: a cluster of one
    {"heroes": ["pavise"], "bridges": []},
]


def _start(heroes, seed):
    rng = random.Random(seed)
    return {h: {r: (round(rng.uniform(0.05, 0.95), 3) if r in hero_mind.TEMPER_ROLES else 0.5)
                for r in hero_mind.ROLES} for h in heroes}


def _lua_literal(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v))
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "{" + ", ".join(_lua_literal(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"[{json.dumps(str(k))}] = {_lua_literal(x)}" for k, x in v.items()) + "}"
    raise TypeError(type(v))


LUA_CHECK = r"""
local M = dofile("%(lite)s")
local case = %(case)s
local mind = M.new(case.tables)
local frame, worst = 0, 0
for i, entry in ipairs(case.script) do
  frame = frame + math.floor(entry[1] * 30 + 0.5)   -- the gaps are whole tenths of a second: whole frames
  for _, s in ipairs(entry[2]) do assert(M.observe(mind, s[1], s[2], s[3], s[4])) end
  M.ingest(mind, 1, frame)
  for h, roles in pairs(case.expect[i]) do
    for r, want in pairs(roles) do
      local v, c = M.belief(mind, h, r)
      local d = math.max(math.abs(v - want[1]), math.abs(c - want[2]))
      if d > worst then worst = d end
      if d > %(tol)s then
        error(string.format("step %%d %%s.%%s: lua (%%.12f, %%.12f) umwelt (%%.12f, %%.12f)", i, h, r, v, c, want[1], want[2]))
      end
    end
  end
end
print(string.format("ok: %(name)s, %%d ingests, worst difference %%.2e", #case.script, worst))
"""


def test_the_lua_minds_are_umwelts():
    import lua_harness
    if not lua_harness.liblua_paths():
        raise unittest.SkipTest("liblua5.4 is not installed")
    src = _umwelt_src()
    if not src:
        raise unittest.SkipTest("Umwelt is not here (UMWELT_SRC)")
    env = dict(os.environ, UMWELT_FP64="1", UMWELT_SRC=src,
               PYTHONPATH=os.pathsep.join([src, str(ROOT / "tools")]))
    for k in [k for k in env if k.startswith("UMWELT_") and k not in ("UMWELT_FP64", "UMWELT_SRC")]:
        env.pop(k)   # nothing that changes Umwelt's path (the report lists them)
    with tempfile.TemporaryDirectory() as tmp:
        for n, cluster in enumerate(CASES):
            start = _start(cluster["heroes"], 100 + n)
            script = _stream(cluster["heroes"], 200 + n, 60)
            case_in, ref = Path(tmp) / f"case{n}.json", Path(tmp) / f"ref{n}.json"
            case_in.write_text(json.dumps({"cluster": cluster, "start": start, "script": script,
                                           "roleGamma": dict(hero_mind.ROLE_GAMMA)}), encoding="utf-8")
            run = subprocess.run([sys.executable, "-B", "-m", "verdance.company.hero_mind", "reference", str(case_in), str(ref)],
                                 cwd=str(ROOT / "tools"), env=env, capture_output=True, text=True, timeout=600)
            assert run.returncode == 0, run.stderr[-2000:]
            expect = json.loads(ref.read_text(encoding="utf-8"))
            tables = {"roles": list(hero_mind.ROLES), "shared": list(hero_mind.SHARED_ROLES),
                      "clusters": [cluster], "start": start, "umwelt": dict(hero_mind.UMWELT), "holdS": hero_mind.HOLD_S,
                      "roleGamma": dict(hero_mind.ROLE_GAMMA)}
            lua = Path(tmp) / f"check{n}.lua"
            lua.write_text(LUA_CHECK % {"lite": LITE, "tol": repr(TOL), "name": "+".join(cluster["heroes"]),
                                        "case": _lua_literal({"tables": tables, "script": script, "expect": expect})},
                           encoding="utf-8")
            err = lua_harness.run(str(lua))
            assert err is None, err


if __name__ == "__main__":
    test_the_lua_minds_are_umwelts()
    print("ok")
