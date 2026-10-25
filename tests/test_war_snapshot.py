#!/usr/bin/env python3
"""The Koom Valley war: the recipe becomes a startscript, the engine's dump becomes a snapshot with the
company's seat pulled out (owner, 2026-10-24)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import war_snapshot as W  # noqa: E402

RECIPE = W.load_recipe(ROOT, "koom_valley")


def test_the_recipe_is_a_3v3_with_the_company_seat_on_the_entry_side():
    teams = RECIPE["teams"]
    assert len(teams) == 6
    by = {t["ally"]: [x for x in teams if x["ally"] == t["ally"]] for t in teams}
    assert {k: len(v) for k, v in by.items()} == {"left": 3, "right": 3}
    assert RECIPE["sides"]["right"]["side"] == "Armada" and RECIPE["sides"]["left"]["side"] == "Legion"
    seat = next(t for t in teams if t["key"] == RECIPE["playerSeat"])
    assert seat["ally"] == "left" and seat["profile"] == "hard_aggressive"
    assert [t["profile"] for t in teams if t["key"] != seat["key"]] == ["hard"] * 5
    # Armada on the far (east) side, the Legion in the bottom left
    assert all(t["startElmos"][0] > 6144 for t in by["right"]) and all(t["startElmos"][0] < 6144 for t in by["left"])
    assert max(by["left"], key=lambda t: t["startElmos"][1])["key"] == "sw"


def test_the_startscript_has_two_ally_teams_six_barbs_and_a_spectator_host():
    s = W.startscript(RECIPE, game_type="Verdance Ashes $VERSION")
    assert s.count("[ALLYTEAM") == 2 and s.count("[TEAM") == 6 and s.count("ShortName=BARb;") == 6
    assert "StartPosType=3;" in s and "NumUsers=7;" in s
    assert "va_shell_bake=1;" in s and "va_shell_bake_frames=36000;" in s and "deathmode=neverend;" in s
    assert re.search(r"\[PLAYER0\]\s*\{[^}]*Spectator=1;", s)
    assert s.count("profile=hard;") == 5 and s.count("profile=hard_aggressive;") == 1
    assert s.count("Side=Legion;") == 3 and s.count("Side=Armada;") == 3
    sides = re.findall(r"\[TEAM(\d)\]\s*\{[^}]*AllyTeam=(\d);", s)
    assert sorted(set(a for _, a in sides)) == ["0", "1"]
    # each team starts on its own seat
    for i, t in enumerate(RECIPE["teams"]):
        assert f"StartPosX={t['startElmos'][0]};" in s


def _dump():
    lines = ["VA_SHELL_MAP 12288 8192"]
    for team, n in ((0, 5), (1, 4), (3, 3)):
        for k in range(n):
            lines.append(f"[f=0036000] VA_SHELL_UNIT armsolar {2000 + k * 40}.0 {2400 + team * 100}.5 1 {team} 0.{50 + k} 1.00 S")
        lines.append(f"VA_SHELL_UNIT leggat {2100 + team}.0 2500.0 0 {team} 1.000 1.00 M")
        lines.append(f"VA_SHELL_UNIT legcom {2000 + team}.0 2300.0 2 {team} 0.900 1.00 C")
    lines.append("VA_SHELL_UNIT armsolar 9000.0 4000.0 0 4 1.000 0.20 S")        # a team-4 structure, barely begun
    lines.append("VA_SHELL_UNIT armwin 9000.0 4040.0 0 4 1.000 1.00 S")
    for t in range(6):
        lines.append(f"VA_SHELL_TEAM {t} Legion {0 if t < 3 else 1} {100 + t} 1000 {200 + t} 2000")
    lines.append("VA_SHELL_DUMP_END count=0")
    return "\n".join(lines)


def test_the_dump_is_read_back_with_owner_health_and_banks():
    d = W.parse_dump(_dump())
    assert d["map"] == (12288.0, 8192.0)
    assert len(d["units"]) == 5 + 4 + 3 + 3 * 2 + 2
    u = next(x for x in d["units"] if x["def"] == "legcom")
    assert (u["team"], u["kind"], u["facing"]) == (0, "C", 2)
    assert d["teams"][3]["metal"] == 103 and d["teams"][3]["estor"] == 2000


def test_the_snapshot_pulls_the_company_seat_out_and_normalises():
    snap = W.build_snapshot(RECIPE, W.parse_dump(_dump()), costs={}, baked_at="t")
    keys = [t["key"] for t in snap["teams"]]
    assert "nw" not in keys and keys == ["w", "sw", "ne", "e", "se"]
    assert snap["pulled"]["key"] == "nw" and snap["pulled"]["units"] == 7 and snap["pulled"]["commanders"] == 1
    w = next(t for t in snap["teams"] if t["key"] == "w")        # team 1
    assert w["faction"] == "nullmercs" and w["side"] == "Legion" and w["profile"] == "hard"
    assert all(0 <= u[1] <= 1 and 0 <= u[2] <= 1 for u in w["units"])
    assert any(u[0] == "legcom" and u[5] == "C" for u in w["units"])
    assert w["units"][0][4] in range(0, 101)
    assert snap["mapSize"] == [12288.0, 8192.0] and snap["dry"] is True


def test_unfinished_work_is_left_behind():
    snap = W.build_snapshot(RECIPE, W.parse_dump(_dump()), costs={})
    e = next(t for t in snap["teams"] if t["key"] == "e")
    assert [u[0] for u in e["units"]] == ["armwin"]


def test_past_the_cap_the_cheapest_mobiles_go_first():
    lines = ["VA_SHELL_MAP 12288 8192"]
    for k in range(5):
        lines.append(f"VA_SHELL_UNIT armfus 3000.0 3000.0 0 1 1.0 1.0 S")
    lines.append("VA_SHELL_UNIT armpw 3000.0 3000.0 0 1 1.0 1.0 M")
    lines.append("VA_SHELL_UNIT armbull 3000.0 3000.0 0 1 1.0 1.0 M")
    lines.append("VA_SHELL_UNIT armcom 3000.0 3000.0 0 1 1.0 1.0 C")
    rec = dict(RECIPE, snapshot={"maxUnitsPerTeam": 7})
    snap = W.build_snapshot(rec, W.parse_dump("\n".join(lines)), costs={"armpw": [54, 0], "armbull": [500, 0]})
    w = next(t for t in snap["teams"] if t["key"] == "w")
    defs = [u[0] for u in w["units"]]
    assert len(defs) == 7 and "armpw" not in defs and "armbull" in defs and "armcom" in defs


def test_progress_ticks_can_be_read_while_the_sim_runs():
    t = "VA_SHELL_BAKE_TICK frame=1800 target=36000 units=0:12,1:9\nVA_SHELL_BAKE_TICK frame=3600 target=36000 units=0:30,1:25"
    assert W.progress(t) == {"frame": 3600, "target": 36000, "units": {0: 30, 1: 25}}


def test_the_snapshot_file_round_trips():
    import tempfile, json
    snap = W.build_snapshot(RECIPE, W.parse_dump(_dump()), costs={}, baked_at="t")
    with tempfile.TemporaryDirectory() as d:
        p = W.write_snapshot(Path(d), snap)
        back = json.loads(p.read_text(encoding="utf-8"))
        assert back == snap
        assert W.load_snapshot(Path(d))["unitCount"] == snap["unitCount"]


def test_every_map_has_a_sound_recipe():
    maps = W.war_maps(ROOT)
    # Greenest Fields' war was retired 2026-10-25 (its living shell is the field again)
    assert set(maps) == {"koom_valley", "tabula", "ancient_bastion", "eye_of_horus"}
    for m in maps:
        rec = W.load_recipe(ROOT, m)
        terrain = __import__("json").loads((ROOT / "data" / "terrain" / f"{m}.terrain.json").read_text(encoding="utf-8-sig"))
        mx, mz = rec["mapSize"]
        assert (mx, mz) == (terrain["size"]["x"], terrain["size"]["z"]), m
        assert rec["mapName"] == terrain["mapName"], m
        keys = [t["key"] for t in rec["teams"]]
        assert len(keys) == len(set(keys)) and rec["playerSeat"] in keys, m
        assert set(t["ally"] for t in rec["teams"]) == set(rec["sides"]) and len(rec["sides"]) == 2, m
        for t in rec["teams"]:
            x, z = t["startElmos"]
            assert 0 < x < mx and 0 < z < mz, (m, t["key"])
            assert t["profile"] in ("hard", "hard_aggressive"), (m, t["key"])
        assert next(t for t in rec["teams"] if t["key"] == rec["playerSeat"])["profile"] == "hard_aggressive", m
        # the sides are stacked apart: their centroids are far across the map
        cen = {}
        for ally in rec["sides"]:
            pts = [t["startElmos"] for t in rec["teams"] if t["ally"] == ally]
            cen[ally] = (sum(p[0] for p in pts) / len(pts) / mx, sum(p[1] for p in pts) / len(pts) / mz)
        a, b = cen.values()
        assert ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 > 0.4, m
        # native seats are the terrain's own start positions; the rest say so
        native = {(p["x"], p["z"]) for p in terrain["startPositions"]}
        for t in rec["teams"]:
            assert (tuple(t["startElmos"]) in native) != bool(t.get("virtual")), (m, t["key"])
        s = W.startscript(rec, game_type="Verdance Ashes $VERSION")
        assert s.count("[TEAM") == len(rec["teams"]) and s.count("[ALLYTEAM") == 2, m
        assert f"va_shell_bake_mapid={m};" in s and f"MapName={rec['mapName']};" in s, m

