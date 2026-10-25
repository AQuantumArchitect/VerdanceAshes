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
from verdance.world import war_snapshot as _war  # noqa: E402
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


def test_koom_is_a_standing_war_three_a_side_with_the_company_seat_left_empty():
    war = theaters.standing_war("koom_valley", ROOT, "KV_NW_MUSTER")
    camps = war["camps"]
    assert [c["faction"] for c in camps] == ["nullmercs", "nullmercs", "armada", "armada", "armada"]
    assert "KV_NW_MUSTER" not in {c["zoneId"] for c in camps}            # the company's seat
    west, east = [c for c in camps if c["faction"] == "nullmercs"], [c for c in camps if c["faction"] == "armada"]
    assert max(c["x"] for c in west) < 0.5 < min(c["x"] for c in east)   # Armada on the far side
    assert all(c["profile"] == "hard" and c["bank"] and c["units"] for c in camps)
    for c in camps:                                                      # the engine gives each start commander
        assert all(u[5] != "C" for u in c["units"])
    # the seats are the recipe's
    rec = _war.load_recipe(ROOT)
    assert {(t["key"], t["zoneId"]) for t in rec["teams"] if t["key"] != rec["playerSeat"]} == \
        {(c["key"], c["zoneId"]) for c in theaters.KOOM_WAR}


def test_koom_war_makes_room_where_the_company_lands():
    nw = theaters.standing_war("koom_valley", ROOT, "KV_NW_MUSTER")
    se = theaters.standing_war("koom_valley", ROOT, "KV_SE_MUSTER")
    pad = _anchor("koom_valley", "KV_SE_MUSTER")
    n = lambda w: sum(len(c["units"]) for c in w["camps"])  # noqa: E731
    assert n(se) < n(nw)
    for c in se["camps"]:
        assert all(math.hypot(u[1] - pad[0], u[2] - pad[1]) >= theaters.PAD_CLEARANCE for u in c["units"])


def test_a_war_not_yet_baked_leaves_an_ordinary_field():
    with tempfile.TemporaryDirectory() as tmp:
        rel = "data/zone_maps/authored/koom_valley.authored.zone_map.json"
        dst = Path(tmp) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
        assert theaters.standing_war("koom_valley", Path(tmp), "KV_NW_MUSTER") is None
    assert theaters.standing_war("the_rock_jungle", ROOT) is None and theaters.standing_war("all_that_simmers", ROOT) is None


def test_the_war_table_is_the_recipes_seats():
    assert sorted(theaters.WARS) == sorted(_war.war_maps(ROOT))
    for map_id, seats in theaters.WARS.items():
        rec = _war.load_recipe(ROOT, map_id)
        assert {(t["key"], rec["sides"][t["ally"]]["faction"], t["zoneId"]) for t in rec["teams"] if t["key"] != rec["playerSeat"]} == \
            {(c["key"], c["faction"], c["zoneId"]) for c in seats}, map_id
        assert theaters.STANDING_CONTROL[map_id] == {c["zoneId"]: c["faction"] for c in seats
                                                      if not (map_id == "eye_of_horus" and c["zoneId"] in theaters.EYE_RIM_ZONES)}
        zones = theaters._zones(map_id, ROOT)
        assert {c["zoneId"] for c in seats} <= set(zones), map_id


def test_every_baked_war_has_two_sides_and_the_company_seat_empty():
    baked = [m for m in theaters.WARS if _war.load_snapshot(ROOT, m)]
    assert "koom_valley" in baked
    for map_id in baked:
        rec = _war.load_recipe(ROOT, map_id)
        pad = next(t for t in rec["teams"] if t["key"] == rec["playerSeat"])
        war = theaters.standing_war(map_id, ROOT, "KV_NW_MUSTER" if map_id == "koom_valley" else pad["zoneId"])
        assert {c["faction"] for c in war["camps"]} >= {"armada"} or {c["faction"] for c in war["camps"]} >= {"cortex"}, map_id
        assert len({c["faction"] for c in war["camps"]}) == 2, map_id
        assert pad["zoneId"] not in {c["zoneId"] for c in war["camps"]} or map_id == "ancient_bastion", map_id
        assert all(c["units"] and c["bank"] for c in war["camps"]), map_id


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
    war = _probe({"theater": theaters.standing_war("koom_valley", ROOT, "KV_NW_MUSTER"), "wildDens": []})
    assert sorted(t["faction"] for t in war["teams"]) == ["armada"] * 3 + ["nullmercs"] * 2
    assert {a["shortName"] for a in war["ai"]} == {"BARb"} and {a["options"]["profile"] for a in war["ai"]} == {"hard"}
    fields = [f for f in war["forces"] if f["role"] == "standing_war"]
    assert len(fields) == 5 and all(f["bank"]["energy"] > 0 for f in fields)
    # every baked unit (a commander never) is placed: one spec per unit type, positions flat x z facing hp
    placed = sum(len(s["at"]) // 4 for f in fields for s in war["recipes"][f["recipe"]])
    assert placed == sum(len(c["units"]) for c in theaters.standing_war("koom_valley", ROOT, "KV_NW_MUSTER")["camps"])
    assert all(s["exact"] and len(s["at"]) == 4 * s["count"] for f in fields for s in war["recipes"][f["recipe"]])
    # seats on a side are allies of each other (the war is two sides, not six); the Mercs are the company's only by standing
    pacts = {tuple(sorted((a["allyTeamA"], a["allyTeamB"]))) for a in war["alliances"]}
    assert len(pacts) == 1 + 3 and all(a["allied"] for a in war["alliances"])
    assert not any(0 in p for p in pacts)

    kings = _probe({"theater": theaters.kings_showdown("all_that_simmers", ROOT, "ATS_NW_SHORE"), "wildDens": []})
    assert [k["faction"] for k in kings["kings"]] == ["ashwalkers", "armada", "nullmercs"]
    assert kings["forces"] == [] and kings["alliances"] == []     # commanders only, everyone at war

    dens = theaters.wild_dens(_state(), "eye_of_horus", ROOT, "EOH_NW_BASTION")
    eye = _probe({"wildDens": dens})
    assert sum(1 for f in eye["forces"] if f["id"].startswith("wild_den_")) == len(dens)
    assert [t["faction"] for t in eye["teams"]] == ["wild"]


def test_a_new_campaign_has_its_bases_standing():
    # The mission builder fields a template's units only where zone memory says their faction
    # holds the ground. A fresh world must say so, or Greenest Fields drops onto an empty map.
    s = _state()
    gf = {z: v["controllingFaction"] for z, v in s["zoneMemory"]["greenest_fields"].items()}
    assert {"GF_SE_PLATEAU", "GF_NW_BASTION", "GF_C_GATE"} <= {z for z, f in gf.items() if f == "armada"}
    for map_id, held in engine.template_holdings(ROOT).items():
        mem = s["zoneMemory"][map_id]
        for zid, fac in held.items():
            if zid in theaters.STANDING_CONTROL.get(map_id, {}):
                continue                                          # a standing war owns its seats' ground
            assert mem[zid]["controllingFaction"] in (fac, "wild"), (map_id, zid)


def test_base_templates_name_live_zones():
    for path in sorted((ROOT / "data" / "base_templates").glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not data.get("units"):
            continue
        live = set(theaters._zones(data["mapId"], ROOT))
        stale = {u.get("zoneId") for u in data["units"]} - live
        assert not stale, (path.name, sorted(stale)[:4])
