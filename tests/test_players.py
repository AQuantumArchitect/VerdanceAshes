"""The players, one per hero (owner call, 2026-11-16: "the multiplayer should hook in something like 1
player per hero... shared company co-op"). Single player is one player, the hero you picked."""
import copy
import gzip
import json
import shutil
import tempfile
from pathlib import Path

from verdance.campaign.schema import default_v1_state
from verdance.company import company as C
from verdance.company import players as P
from verdance.mission_builder import build_scenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mission_builder"


def _ws():
    ws = Path(tempfile.mkdtemp(prefix="va_players_"))
    (ws / "data" / "story").mkdir(parents=True)
    for f in ("crew_packs.json", "hero_roster.json"):
        shutil.copy(ROOT / "data" / "story" / f, ws / "data" / "story" / f)
    return ws


def _sealed():
    ws = _ws()
    st = default_v1_state()
    ok, err, _ = C.seal_company(st, ["pavise", "solarium", "halbard"], workspace=ws)
    assert ok, err
    return ws, st


def test_one_player_is_you():
    ws, st = _sealed()
    assert P.players(st) == ["pavise"]
    assert P.mission_players(st) == [{"player": 0, "heroId": "pavise", "name": "VerdanceCommander"}]


def test_more_players_take_the_companys_heroes():
    ws, st = _sealed()
    ok, err, now = P.set_players(st, ["halbard", "ketha"], workspace=ws)
    assert ok, err
    assert now == ["pavise", "halbard", "ketha"] and P.players(st) == now
    assert [p["name"] for p in P.mission_players(st)] == ["VerdanceCommander", "VerdancePlayer2", "VerdancePlayer3"]
    assert P.set_players(st, [], workspace=ws)[0] and P.players(st) == ["pavise"], "[] is single player again"


def test_a_players_hero_is_the_companys_alive_and_walks():
    ws, st = _sealed()
    assert not P.set_players(st, ["vane"], workspace=ws)[0], "vane is not in this company"
    assert not P.set_players(st, ["halbard", "halbard"], workspace=ws)[0]
    assert not P.set_players(st, ["pavise"], workspace=ws)[0], "you are already player 1"
    for h in st["roster"]["heroes"]:
        if h["heroId"] == "halbard":
            h["status"] = "dead"
    assert not P.set_players(st, ["halbard"], workspace=ws)[0]
    st["company"]["players"] = ["halbard"]
    assert P.players(st) == ["pavise"], "a fallen player's hero leaves the list"
    unsealed = default_v1_state()
    assert not P.set_players(unsealed, ["ketha"], workspace=ws)[0]


def test_the_hub_lists_players_and_who_could_be_one():
    ws, st = _sealed()
    P.set_players(st, ["halbard"], workspace=ws)
    surf = C.hub_company_surface(st, ws)
    assert [p["heroId"] for p in surf["players"]] == ["pavise", "halbard"]
    assert "solarium" in surf["playerCandidates"] and "halbard" not in surf["playerCandidates"]


def _load(case, name):
    return json.loads(gzip.decompress((FIXTURE / case / name).read_bytes()).decode("utf-8-sig"))


def test_the_mission_carries_players_only_when_there_are_several():
    intent, state = _load("tour02", "intent.json.gz"), _load("tour02", "state.json.gz")
    sc, _ = build_scenario(ROOT, copy.deepcopy(intent), copy.deepcopy(state), log=lambda _l: None)
    assert "players" not in sc["missionBase"], "one player: the mission keeps its shape"
    you = state["company"]["you"]
    other = next(h for h in P.company_heroes(state) if h != you)
    state["company"]["players"] = [other]
    sc, _ = build_scenario(ROOT, copy.deepcopy(intent), copy.deepcopy(state), log=lambda _l: None)
    assert sc["missionBase"]["players"] == [{"player": 0, "heroId": you, "name": "VerdanceCommander"},
                                            {"player": 1, "heroId": other, "name": "VerdancePlayer2"}]


def test_the_start_script_seats_every_player_on_the_companys_team():
    ps1 = (ROOT / "scripts" / "install_playable_slice.ps1").read_text(encoding="utf-8-sig")
    assert "NumPlayers=$numPlayers;" in ps1 and "HostPort=$hostPort;" in ps1
    assert "[PLAYER$pi]" in ps1 and "Team=$playerTeamID;" in ps1 and "Name=$($coopPlayers[$pi].name);" in ps1


def test_the_engine_publishes_who_is_whom():
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    import lua_harness
    assert lua_harness.run("tools/hud_harness/players_test.lua") is None
