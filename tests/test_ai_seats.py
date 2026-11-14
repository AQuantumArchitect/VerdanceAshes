#!/usr/bin/env python3
"""Every AI seat on the field has an AI that starts, on its own seat (Luke, Koom Valley, 2026-11-13:
"half the teams are confused? it looks like my allies are not active", then: the enemy too).

Two faults stood behind it:
- Every BARb seat went out as ``Version=<not-versioned>``. BARb is a native AI; the engine matches a
  native AI's version exactly (RecoilEngine AILibraryManager::FittingSkirmishAIKeys) and BAR ships
  it as ``stable``, so no BARb was ever found and every BARbarian seat (Koom's whole war, both sides)
  stood idle. ``<not-versioned>`` is only a Lua AI's word (SimpleAI, RaptorsAI).
- StartPosType 1 put each team's engine commander on one of the map's own start points in random
  order, so a war seat's commander could stand in the company's pad. Every team now starts on its
  seat (StartPosType 3 reads StartPosX/Z).
"""
from __future__ import annotations

import copy
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.mission_builder import build_scenario  # noqa: E402
from verdance.mission_builder.builder import ai_version  # noqa: E402
from verdance.world import theaters  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "mission_builder"
LUA_AIS = {"SimpleAI", "SimpleDefenderAI", "SimpleConstructorAI", "RaptorsAI", "ScavengersAI"}
# (map, pad, target, theater) -- the standing wars and the kings' showdown
SET_PIECES = [
    ("koom_valley", "KV_NW_MUSTER", "KV_SE_MUSTER", "war"),
    ("koom_valley", "KV_SE_MUSTER", "KV_NW_SPILLWAY", "war"),
    ("tabula", "T_NW_MUSTER", "T_SE_MUSTER", "war"),
    ("ancient_bastion", "AB_NW_TOR", "AB_W_KEEP", "war"),
    ("eye_of_horus", "EOH_NW_MUSTER", "EOH_C_GATE", "war"),
    ("all_that_simmers", "ATS_NW_SPILLWAY", "ATS_C_BASTION", "kings"),
]


def _load(case: str, name: str):
    return json.loads(gzip.decompress((FIXTURE / case / name).read_bytes()).decode("utf-8-sig"))


def _set_piece_intent(map_id: str, pad: str, target: str, kind: str):
    intent, state = copy.deepcopy(_load("tour02", "intent.json.gz")), _load("tour02", "state.json.gz")
    theater = (theaters.standing_war(map_id, ROOT, pad) if kind == "war"
               else theaters.kings_showdown(map_id, ROOT, pad))
    assert theater, f"{map_id}: no {kind} theater"
    intent.update(mapId=map_id, deploymentZoneId=pad, extractionZoneId=pad, targetZoneId=target,
                  captureZoneIds=[target], fromZoneIds=[pad], theater=theater, visitTier=None, doors=[],
                  safeZoneIds=[pad], hubChoiceId="door_" + target, exitDoorZoneId=target, wildDens=[])
    intent["objectiveTarget"] = dict(intent["objectiveTarget"], id=target, targetZoneId=target, fromZoneIds=[pad])
    return intent, state


def _scenarios():
    for case in sorted(p.name for p in FIXTURE.iterdir() if p.is_dir()):
        yield case, _load(case, "intent.json.gz"), _load(case, "state.json.gz")
    for map_id, pad, target, kind in SET_PIECES:
        intent, state = _set_piece_intent(map_id, pad, target, kind)
        yield f"{map_id}@{pad}", intent, state


def _build(intent, state, **kw):
    sc, _ = build_scenario(ROOT, intent, state, log=lambda _l: None, **kw)
    return json.loads(json.dumps(sc))


def test_ai_versions_follow_the_short_name():
    assert ai_version("BARb") == "stable"
    for short in LUA_AIS:
        assert ai_version(short) == "<not-versioned>"


def test_every_ai_seat_has_an_ai_that_starts_on_its_own_seat():
    for name, intent, state in _scenarios():
        sc = _build(intent, state)
        v = sc["variants"][0]
        lay = sc["layout"]
        teams = {t["id"]: t for t in lay["teams"]}
        rects = {a["id"]: a["startRect"] for a in lay["allyTeams"]}
        player = v["playerTeamID"]
        assert v["startPosType"] == 3, f"{name}: teams must start on their seats, not the map's start points"
        ai_teams = [a["team"] for a in v["ai"]]
        assert len(ai_teams) == len(set(ai_teams)), f"{name}: two AIs on one team"
        assert player not in ai_teams, f"{name}: an AI on the company's team"
        # The living shell is the one team without an AI by design: game_verdance_living_shell grows it.
        gadget_run = {tid for tid, t in teams.items() if str(t.get("label", "")).endswith("Living Shell")}
        assert set(ai_teams) == set(teams) - {player} - gadget_run, f"{name}: a team with no AI (it would stand idle)"
        for a in v["ai"]:
            short = a["shortName"]
            if short == "BARb":
                assert a["version"] == "stable", f"{name}: {a['name']} would never start ({a['version']})"
            else:
                assert short in LUA_AIS, f"{name}: unknown AI {short}"
                assert a["version"] == "<not-versioned>", f"{name}: {a['name']}"
        for tid, t in teams.items():
            x, z = t["base"]
            assert 0.0 <= x <= 1.0 and 0.0 <= z <= 1.0, f"{name}: team {tid} seat off the map"
            r = rects[t["allyTeam"]]
            assert r[0] - 1e-9 <= x <= r[2] + 1e-9 and r[1] - 1e-9 <= z <= r[3] + 1e-9, \
                f"{name}: team {tid}'s seat is outside its own start box"


def test_koom_the_war_is_two_sides_and_the_company_seat_is_its_pad():
    intent, state = _set_piece_intent("koom_valley", "KV_NW_MUSTER", "KV_SE_MUSTER", "war")
    sc = _build(intent, state)
    lay, v = sc["layout"], sc["variants"][0]
    teams = {t["id"]: t for t in lay["teams"]}
    pad = theaters._point(theaters._zones("koom_valley", ROOT)["KV_NW_MUSTER"])
    you = teams[v["playerTeamID"]]
    assert abs(you["base"][0] - pad[0]) < 0.12 and abs(you["base"][1] - pad[1]) < 0.12, "the company starts on its pad"
    pacts = {frozenset((p["allyTeamA"], p["allyTeamB"])) for p in lay["alliances"] if p["allied"]}
    allied = lambda a, b: a == b or frozenset((a, b)) in pacts
    by_fac = {}
    for t in teams.values():
        by_fac.setdefault(t["faction"], []).append(t["allyTeam"])
    for fac, ally_ids in by_fac.items():
        assert all(allied(a, b) for a in ally_ids for b in ally_ids), f"{fac}'s seats are one side"
    for m in by_fac.get("nullmercs", []):
        assert not any(allied(m, a) for a in by_fac.get("armada", [])), "Mercs and Armada are at war"
    # no war seat stands in the company's pad: an enemy commander there is the confusion Luke saw
    for t in teams.values():
        if t["id"] != you["id"]:
            d = ((t["base"][0] - you["base"][0]) ** 2 + (t["base"][1] - you["base"][1]) ** 2) ** 0.5
            assert d >= 0.1, f"{t['label']} sits in the company's pad"


def test_the_ps1_faults_still_reproduce_for_the_parity_corpus():
    intent, state = _set_piece_intent("koom_valley", "KV_NW_MUSTER", "KV_SE_MUSTER", "war")
    sc = _build(intent, state, ps1_faults=True)
    v = sc["variants"][0]
    assert v["startPosType"] == 1
    assert {a["version"] for a in v["ai"] if a["shortName"] == "BARb"} == {"<not-versioned>"}


def test_the_installer_never_writes_barb_unversioned():
    text = (ROOT / "scripts" / "install_playable_slice.ps1").read_text(encoding="utf-8-sig")
    assert '$Ai.shortName -eq "BARb"' in text and '$version = "stable"' in text


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]:
        fn()
        print("ok  ", fn.__name__)
