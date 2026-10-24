#!/usr/bin/env python3
"""The fields' standing set pieces, the wild's dens, the waterline the hub shows, and the throne."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine  # noqa: E402
from verdance.belief import manifest  # noqa: E402
from verdance.campaign.hydrology import waterline_surface  # noqa: E402
from verdance.world import roads, theaters  # noqa: E402

PWSH = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if Path("/opt/pwsh/pwsh").exists() else None)


def _state():
    s = engine.default_v1_state()
    engine.ensure_zone_memory(s, ROOT)
    return s


def _anchor(map_id, zone_id):
    z = theaters._zones(map_id, ROOT)[zone_id]
    return theaters._point(z)


def test_the_eye_rim_is_wild_and_the_eye_is_not():
    wild = theaters._wild(_state(), "eye_of_horus")
    assert set(theaters.EYE_RIM_ZONES) <= wild
    assert not {"EOH_C_GATE", "EOH_C_LANE", "EOH_C_INNER_GATE", "EOH_C_INNER_LANE"} & wild


def test_eye_dens_sit_on_the_rim_and_clear_of_the_pad():
    dens = theaters.wild_dens(_state(), "eye_of_horus", ROOT, "EOH_NW_BASTION")
    assert len(dens) >= 6
    pad = _anchor("eye_of_horus", "EOH_NW_BASTION")
    for d in dens:
        assert min(d["x"], 1 - d["x"], d["z"], 1 - d["z"]) <= 0.08, d       # on the edge
        assert math.hypot(d["x"] - pad[0], d["z"] - pad[1]) >= theaters.PAD_CLEARANCE


def test_jungle_dens_skip_the_hive_and_the_pad():
    dens = theaters.wild_dens(_state(), "the_rock_jungle", ROOT, "TRJ_NW_OUTER_MUSTER")
    ids = {d["zoneId"] for d in dens}
    assert theaters.JUNGLE_HIVE_ZONE not in ids and "TRJ_NW_OUTER_MUSTER" not in ids
    assert len(dens) >= 8


def test_koom_is_a_standing_war_off_the_doors():
    war = theaters.standing_war("koom_valley", ROOT)
    factions = {c["faction"] for c in war["camps"]}
    assert factions == {"nullmercs", "armada"}
    doors = {z for z, d in roads.load_doors(ROOT).items() if d["mapId"] == "koom_valley"}
    assert not {c["zoneId"] for c in war["camps"]} & doors
    a, b = war["camps"]
    # the two lines face each other across the valley
    assert math.hypot(a["front"]["x"] - b["front"]["x"], a["front"]["z"] - b["front"]["z"]) > 0.3


def test_simmers_is_a_kings_showdown_from_any_door():
    for pad in ("ATS_NW_SHORE", "ATS_SW_MUSTER"):
        show = theaters.kings_showdown("all_that_simmers", ROOT, pad)
        kings = show["kings"]
        assert [k["faction"] for k in kings] == ["armada", "nullmercs"]
        assert pad not in {k["zoneId"] for k in kings}
        assert show["throne"]["zoneId"] == theaters.SIMMERS_THRONE


def test_the_commander_walks_out_alone():
    intent = {"roster": {"heroes": [{"heroId": "pavise"}], "cadre": {"legcen": 4}}, "deployAces": ["ketha"],
              "crewBand": ["pavise"], "objective": "seize_lane", "objectiveTarget": {"kind": "seize_lane"},
              "theater": theaters.kings_showdown("all_that_simmers", ROOT, "ATS_NW_SHORE")}
    theaters.solo_command(intent)
    assert theaters.is_solo(intent)
    assert intent["roster"]["heroes"] == [] and intent["roster"]["cadre"] == {}
    assert intent["deployAces"] == [] and intent["crewBand"] == []
    assert intent["objective"] == "kings_showdown" and intent["targetZoneId"] == theaters.SIMMERS_THRONE


def test_the_throne_is_read_from_the_kings():
    won = {"kings": [{"faction": "ashwalkers", "fallen": False}, {"faction": "armada", "fallen": True},
                     {"faction": "nullmercs", "fallen": True}]}
    assert manifest.throne_taken(won) is True and manifest.objective_done(won)
    lost = {"kings": [{"faction": "ashwalkers", "fallen": True}, {"faction": "armada", "fallen": True},
                      {"faction": "nullmercs", "fallen": True}]}
    assert manifest.throne_taken(lost) is False
    standing = {"kings": [{"faction": "ashwalkers", "fallen": False}, {"faction": "armada", "fallen": True},
                          {"faction": "nullmercs", "fallen": False}]}
    assert not manifest.objective_done(standing)
    assert manifest.throne_taken({"objectiveComplete": True}) is None


def test_the_sovereignty_finale_is_the_showdown_on_a_door():
    plan = engine.FINALE_PLANS["B"]
    assert plan["mapId"] == "all_that_simmers" and plan["objective"]["kind"] == "kings_showdown"
    for p in engine.FINALE_PLANS.values():
        assert roads.is_door(p["deploymentZoneId"], ROOT), p["deploymentZoneId"]


def test_the_waterline_the_hub_shows():
    s = _state()
    gf = waterline_surface(s, "greenest_fields", ROOT)
    assert gf["assault"] == "dry" and gf["level"] == 0.0
    for n in range(1, 13):
        s["missionNumber"] = n
        engine.advance_planet_hydrology(s, ROOT)
        kv = waterline_surface(s, "koom_valley", ROOT)
        assert kv["level"] <= 0.45 + 1e-9                     # Koom's flats stay dry ground
        assert kv["assault"] in ("dry bed", "shallows", "amphibious")
        assert set(kv["zones"]) <= {z["zoneId"] for z in theaters._zones("koom_valley", ROOT).values()}


def _probe(intent):
    if not PWSH:
        raise unittest.SkipTest("pwsh is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "intent.json"
        p.write_text(json.dumps(intent), encoding="utf-8")
        r = subprocess.run([PWSH, "-NoProfile", "-File", str(ROOT / "tools" / "hud_harness" / "set_piece_probe.ps1"),
                            "-Script", str(ROOT / "scripts" / "build_next_mission_v1.ps1"), "-IntentPath", str(p)],
                           capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_builder_fields_the_war_the_kings_and_the_dens():
    war = _probe({"theater": theaters.standing_war("koom_valley", ROOT), "wildDens": []})
    assert sorted(t["faction"] for t in war["teams"]) == ["armada", "nullmercs"]
    assert {a["shortName"] for a in war["ai"]} == {"BARb"}
    assert sum(1 for f in war["forces"] if f["role"] == "standing_war") == 2
    assert war["alliances"] == []                       # the Mercs are allies only by standing

    kings = _probe({"theater": theaters.kings_showdown("all_that_simmers", ROOT, "ATS_NW_SHORE"), "wildDens": []})
    assert [k["faction"] for k in kings["kings"]] == ["ashwalkers", "armada", "nullmercs"]
    assert kings["forces"] == [] and kings["alliances"] == []     # commanders only, everyone at war

    dens = theaters.wild_dens(_state(), "eye_of_horus", ROOT, "EOH_NW_BASTION")
    eye = _probe({"wildDens": dens})
    assert sum(1 for f in eye["forces"] if f["id"].startswith("wild_den_")) == len(dens)
    assert [t["faction"] for t in eye["teams"]] == ["wild"]
