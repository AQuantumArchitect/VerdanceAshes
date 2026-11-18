"""Co-op over the network (verdance_kernel.coop): the host's launcher hands out the sortie it is
playing, byte for byte, and a friend's launcher picks a player, installs the sortie and joins."""
import hashlib
import io
import json
import os
import socket
import tempfile
import time
import zipfile
from pathlib import Path

from verdance_kernel import coop

PLAYERS = [{"player": 0, "heroId": "pavise", "name": "VerdanceCommander"},
           {"player": 1, "heroId": "halbard", "name": "VerdancePlayer2"},
           {"player": 2, "heroId": "ketha", "name": "VerdancePlayer3"}]


def _host_ws(players=PLAYERS, up=True):
    root = Path(tempfile.mkdtemp(prefix="va_coop_"))
    ws, bar = root / "ws", root / "bar"
    game = bar / "games" / "VerdanceAshes.sdd"
    (game / "singleplayer" / "verdance_ashes" / "generated").mkdir(parents=True)
    (game / "modinfo.lua").write_text("return { name = 'Verdance Ashes' }\n", encoding="utf-8")
    (game / "singleplayer" / "verdance_ashes" / "generated" / "va_current.lua").write_text("return { missionId = 'm7' }\n", encoding="utf-8")
    (bar / "engine" / "recoil_2026.07.04").mkdir(parents=True)
    (ws / "playable_runs").mkdir(parents=True)
    script = ws / "playable_runs" / "start.txt"
    script.write_text("[GAME]\n{\n  MapName=Greenest Fields 1.3;\n  HostIP=;\n  HostPort=8452;\n}\n", encoding="ascii")
    (ws / "verdance_config.json").write_text(json.dumps({"barDataRoot": str(bar)}), encoding="utf-8")
    (ws / "playable_runs" / "latest_playable_variant_manifest.json").write_text(
        json.dumps({"startScriptPath": str(script), "players": players}), encoding="utf-8")
    log = bar / "infolog.txt"
    (ws / "playable_runs" / "latest_launch.json").write_text(json.dumps(
        {"engine": str(bar / "engine" / "recoil_2026.07.04" / "spring.exe"), "infologPath": str(log), "at": "t1"}), encoding="utf-8")
    time.sleep(0.05)
    log.write_text("loading...\n" + (coop.HOST_UP + "\n" if up else ""), encoding="utf-8")
    return ws, game


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_same_folder_packs_the_same_bytes():
    _, game = _host_ws()
    a, b = coop.package(game), coop.package(game)
    assert a == b and zipfile.ZipFile(io.BytesIO(a)).namelist() == sorted(zipfile.ZipFile(io.BytesIO(a)).namelist())


def test_the_host_says_who_plays_and_when_it_is_up():
    ws, game = _host_ws()
    meta = coop.sortie_meta(ws, coop.package(game))
    assert meta["ok"] and meta["hostUp"] and meta["mapName"] == "Greenest Fields 1.3" and meta["port"] == 8452
    assert meta["engine"] == "recoil_2026.07.04" and [p["heroId"] for p in meta["players"]] == ["pavise", "halbard", "ketha"]
    assert not coop.sortie_meta(_host_ws(up=False)[0])["hostUp"], "still loading"
    assert not coop.sortie_meta(_host_ws(players=PLAYERS[:1])[0])["ok"], "one player: nothing to join"


def test_an_old_log_is_not_the_host_up():
    ws, _ = _host_ws()
    log = Path(json.loads((ws / "playable_runs" / "latest_launch.json").read_text())["infologPath"])
    old = time.time() - 3600
    os.utime(log, (old, old))
    assert not coop.host_up(ws), "the last sortie's log says nothing about this one"


def test_a_friend_picks_a_player():
    meta = {"players": PLAYERS}
    assert coop.pick_player(meta, None)["heroId"] == "halbard", "the first after the host"
    assert coop.pick_player(meta, "3")["heroId"] == "ketha"
    assert coop.pick_player(meta, "Ketha")["name"] == "VerdancePlayer3"
    for bad in ("1", "pavise", "vane"):
        try:
            coop.pick_player(meta, bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} is not a seat for a friend")


def test_the_sortie_server_hands_out_the_sortie_and_nothing_else():
    ws, game = _host_ws()
    port = _free_port()
    srv = coop.SortieServer(ws, port=port, bind="127.0.0.1").start()
    try:
        meta = coop.fetch_meta("127.0.0.1", port)
        zipped = coop._get(f"http://127.0.0.1:{port}/coop/sortie.zip")
        assert meta["sha256"] == hashlib.sha256(zipped).hexdigest()
        try:
            coop._get(f"http://127.0.0.1:{port}/api/hub-state")
            raise AssertionError("the sortie server serves nothing but the sortie")
        except Exception as e:  # noqa: BLE001
            assert "404" in str(e)
        dest = Path(tempfile.mkdtemp()) / "games" / "VerdanceAshes.sdd"
        dest.parent.mkdir(parents=True)
        (dest).mkdir()
        (dest / "stale.lua").write_text("old", encoding="utf-8")
        coop.install(zipped, dest)
        assert (dest / "singleplayer" / "verdance_ashes" / "generated" / "va_current.lua").read_text(encoding="utf-8") == \
            "return { missionId = 'm7' }\n"
        assert not (dest / "stale.lua").exists(), "the friend's game folder is the host's sortie, nothing more"
    finally:
        srv.stop()


def test_a_sortie_with_an_unsafe_path_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.lua", "x")
    dest = Path(tempfile.mkdtemp()) / "VerdanceAshes.sdd"
    try:
        coop.install(buf.getvalue(), dest)
    except ValueError:
        return
    raise AssertionError("a path out of the game folder must not install")


def test_the_join_script_names_the_player():
    s = coop.join_script("192.168.0.17", 8452, "VerdancePlayer2")
    assert "HostIP=192.168.0.17;" in s and "HostPort=8452;" in s and "IsHost=0;" in s and "MyPlayerName=VerdancePlayer2;" in s


def test_a_client_is_in_once_it_logs_a_game_frame():
    assert not coop.in_game("[t=00:06:54][f=-000001] VA_PLAYERS n=2 ...\n[t=00:07:12][f=-000001] Error: [GameEnd] lost connection to server")
    assert coop.in_game("[t=00:07:18][f=0000030] [Verdance] VA_PLAYERS_ALL_IN")
