#!/usr/bin/env python3
"""A return sortie finds the whole base, build turrets included (Luke, Rock Jungle, 2026-11-13:
"my buildings are all here, but ... my build turrets are gone. So are most of my build units").

Two faults:
- A pack mentor in the field (Solarium, Consul, Twitch, Spoke, Tick, Noctua) stamps every new
  player unit of its product list as a pack mate (va_pack_id), whoever built it. Solarium's and
  Consul's lists hold the nano turret (armnanotc), Solarium's the converter and storages; the
  footprint left every pack-marked structure out as "travels with the hero", so those turrets never
  came back. A mentor's mint is now marked (va_mentor_mint) and stays with the base.
- The mission builder left out every footprint structure whose def any company hero or escort used
  (a player-built Legion vehicle plant or metal storage while Spoke rides along). It now leaves out
  only as many as the packs account for.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.mission_builder import shell as S  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lua_harness import run as run_lua  # noqa: E402

GADGETS = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets"


def _state(units):
    return {"company": {"core": ["ketha"], "band": ["spoke", "solarium"], "joinedLater": []},
            "playerFootprints": {"the_rock_jungle": {"deploymentZoneId": "TRJ_NW_OUTER_MUSTER", "units": units}}}


def _u(d, x, z):
    return {"unitDefName": d, "x": x, "z": z, "facing": 0, "zoneId": "TRJ_NW_GATE"}


def test_nano_turrets_and_own_builds_rehydrate_with_the_base():
    units = [_u("legnanotc", 1000 + 40 * i, 2000) for i in range(3)] + [_u("armnanotc", 1300, 2100)]
    units += [_u("legvp", 900, 1800), _u("legvp", 1200, 1800), _u("legmstor", 1100, 1700),
              _u("legmstor", 1150, 1700), _u("armmakr", 1500, 2200)]
    payload = S.merge_player_footprint(_state(units), "the_rock_jungle", None, ROOT, log=lambda *_: None)
    got = [u["unitDefName"] for u in payload["units"] if u.get("forceRole") == "player_footprint"]
    assert got.count("legnanotc") == 3 and got.count("armnanotc") == 1, got
    # Spoke's pack is a legvp and a legmstor; Solarium's an armmakr: one of each is the pack's.
    assert got.count("legvp") == 1 and got.count("legmstor") == 1 and got.count("armmakr") == 0, got
    assert payload["spawnLimit"] >= len(payload["units"])


def test_a_mentors_mint_is_marked_and_kept_in_the_footprint():
    mentors = (GADGETS / "include" / "campaign" / "mentors.lua").read_text(encoding="utf-8")
    company = (GADGETS / "include" / "campaign" / "result_company.lua").read_text(encoding="utf-8")
    assert 'SetUnitRulesParam(unitID, "va_mentor_mint", 1' in mentors
    assert 'GetUnitRulesParam(uID, "va_mentor_mint")' in company
    assert "((not minted) and packMark" in company


def test_the_footprint_walk_keeps_the_mint_and_leaves_the_pack_kit():
    err = run_lua("tools/hud_harness/footprint_mint_test.lua")
    assert err is None, err


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
