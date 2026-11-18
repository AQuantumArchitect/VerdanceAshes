"""Co-op over the network: the host's launcher hands out the sortie, a friend's launcher joins it.

One player per hero (verdance.company.players). The campaign lives on the host's PC: it builds the
sortie, the start script seats every player on the company's team, and the host's game listens on
Recoil's port. A joining PC needs exactly what the host loaded, byte for byte (Recoil compares the
game's checksum), and the sortie is generated fresh each time, so:

  host   while a co-op sortie runs, a small read-only server hands out the sortie: what it is
         (GET /coop/sortie.json) and the game folder the host loaded, seed and all
         (GET /coop/sortie.zip). Nothing else of the host's is served.
  join   on the friend's PC (JOIN.bat): wait until the host's game is up, fetch the sortie, install
         it as the friend's own Verdance game folder, fetch the map, and start the engine as that
         player. Recoil gives a joining client 30 s to reach a server that is up
         (PreGame::UpdateClientNet), so a join that misses it tries again while the host still plays.

The port: the game's is Recoil's default, UDP 8452. The sortie server takes the same number over
TCP, so a host behind a router forwards one number (UDP for the game, TCP for the files).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

from verdance_kernel import sortie as S

PORT = 8452                       # Recoil's default game port (UDP); the sortie server uses it over TCP
HOST_UP = "Connection established (given id 0)"   # the host's own client is in: its server takes joins
JOIN_MISSED = ("server connection timeout",       # a client that started before the host's server was up
               "lost connection to server")       # ...or that the host dropped while it loaded
IN_GAME = re.compile(r"\[f=0\d{6}\]")             # a log line at a game frame: this client is playing


def in_game(log_text: str) -> bool:
    """The client got into the game: it logged at a game frame (the pre-game logs at f=-000001)."""
    return bool(IN_GAME.search(log_text))


# ----------------------------------------------------------------------------- the host

def _launch_record(ws: Path) -> dict[str, Any]:
    p = ws / "playable_runs" / "latest_launch.json"
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def _since(log: Path, t: float) -> str:
    """The engine's log, if it was written after t (Recoil starts infolog.txt afresh each launch)."""
    try:
        if log.stat().st_mtime < t:
            return ""
        return log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def host_up(ws: Path) -> bool:
    """The host's game has loaded and its server takes joins (its infolog since this launch says so)."""
    rec_path = ws / "playable_runs" / "latest_launch.json"
    rec = _launch_record(ws)
    try:
        launched = rec_path.stat().st_mtime - 5.0   # the record is written just after the engine starts
    except OSError:
        return False
    return HOST_UP in _since(Path(rec.get("infologPath") or S.bar_config(ws)["infolog"]), launched)


def package(game_dir: Path) -> bytes:
    """The game folder as a zip, in a fixed order (the same folder makes the same bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in Path(game_dir).rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f.relative_to(game_dir).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())
    return buf.getvalue()


def sortie_meta(ws: Path, zipped: Optional[bytes] = None) -> dict[str, Any]:
    """What a joining PC needs to know: who plays, the map, the engine, the game's hash, whether the
    host's game is up yet."""
    players = S.players_from_manifest(ws)
    if len(players) <= 1:
        return {"ok": False, "error": "no co-op sortie on this PC (one player)"}
    cfg = S.bar_config(ws)
    script = S.startscript_from_manifest(ws)
    text = script.read_text(encoding="utf-8", errors="replace") if script else ""
    m = re.search(r"MapName=([^;]+);", text)
    port = int((re.search(r"HostPort=(\d+);", text) or [None, str(PORT)])[1]) or PORT
    rec = _launch_record(ws)
    engine = Path(rec.get("engine") or "").parent.name
    out = {"ok": True, "players": players, "mapName": m.group(1).strip() if m else None, "port": port,
           "engine": engine, "hostUp": host_up(ws), "launchedAt": rec.get("at")}
    if zipped is not None:
        out["sha256"] = hashlib.sha256(zipped).hexdigest()
        out["bytes"] = len(zipped)
    return out


class SortieServer:
    """The read-only sortie server: /coop/sortie.json and /coop/sortie.zip, nothing else."""

    def __init__(self, ws: Path, port: int = PORT, bind: str = ""):
        self.ws, self.port, self.bind = Path(ws), int(port), bind
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._zip: Optional[bytes] = None
        self._zip_for: Optional[str] = None
        self._lock = threading.Lock()

    def _current_zip(self) -> bytes:
        key = str(_launch_record(self.ws).get("at") or "")
        with self._lock:
            if self._zip is None or self._zip_for != key:
                self._zip = package(Path(S.bar_config(self.ws)["modSdd"]))
                self._zip_for = key
            return self._zip

    def start(self) -> "SortieServer":
        if self._httpd is not None:
            return self
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a: Any) -> None:  # quiet: the launcher's window is the player's
                return

            def do_GET(self) -> None:  # noqa: N802
                try:
                    if self.path.split("?")[0] == "/coop/sortie.json":
                        meta = sortie_meta(outer.ws, outer._current_zip() if S.players_from_manifest(outer.ws)[1:] else None)
                        body, ctype = json.dumps(meta).encode("utf-8"), "application/json"
                    elif self.path.split("?")[0] == "/coop/sortie.zip":
                        if len(S.players_from_manifest(outer.ws)) <= 1:
                            self.send_error(404, "no co-op sortie")
                            return
                        body, ctype = outer._current_zip(), "application/zip"
                    else:
                        self.send_error(404)
                        return
                except Exception as e:  # noqa: BLE001
                    body, ctype = json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}).encode("utf-8"), "application/json"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer((self.bind, self.port), Handler)
        threading.Thread(target=self._httpd.serve_forever, name="verdance-coop", daemon=True).start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


_SERVER: Optional[SortieServer] = None


def local_addresses() -> list:
    """This PC's IPv4 addresses a friend could reach (LAN or VPN), loopback left out."""
    import socket
    found: list = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def info(ws: Path) -> dict:
    """For the hub: how a friend reaches this PC, and whether the sortie server is up."""
    return {"ok": True, "addresses": local_addresses(), "port": PORT, "serving": _SERVER is not None,
            "players": len(S.players_from_manifest(Path(ws))) or 1}


def serve_sortie(ws: Path) -> dict[str, Any]:
    """Start the sortie server once, for a co-op sortie (the kernel's launch calls it)."""
    global _SERVER
    try:
        if _SERVER is None:
            _SERVER = SortieServer(ws).start()
        return {"ok": True, "port": _SERVER.port}
    except OSError as e:
        return {"ok": False, "error": f"the sortie server could not open port {PORT}: {e}"}


# ----------------------------------------------------------------------------- the join

def _get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "VerdanceAshes-join"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (the host the player typed)
        return r.read()


def fetch_meta(host: str, port: int = PORT) -> dict[str, Any]:
    return json.loads(_get(f"http://{host}:{port}/coop/sortie.json").decode("utf-8"))


def install(zipped: bytes, game_dir: Path) -> None:
    """The host's sortie becomes this PC's Verdance game folder (the next solo Drop writes its own)."""
    game_dir = Path(game_dir)
    tmp = game_dir.with_name(game_dir.name + ".joining")
    if tmp.exists():
        shutil.rmtree(tmp)
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        for name in z.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe path in the sortie: {name}")
        z.extractall(tmp)
    if game_dir.exists():
        shutil.rmtree(game_dir)
    tmp.rename(game_dir)


def join_script(host: str, port: int, name: str) -> str:
    return f"[GAME]\n{{\n  HostIP={host};\n  HostPort={port};\n  IsHost=0;\n  MyPlayerName={name};\n}}\n"


def pick_player(meta: dict[str, Any], want: Optional[str]) -> dict[str, Any]:
    """The player to join as: by number (2, 3...), hero id or name; else the first after the host."""
    rows = list(meta.get("players") or [])[1:]
    if not rows:
        raise ValueError("the host's sortie has no seat for another player")
    if want:
        w = str(want).strip().lower()
        for r in rows:
            if w in (str(int(r.get("player", -9)) + 1), str(r.get("heroId", "")).lower(), str(r.get("name", "")).lower()):
                return r
        raise ValueError(f"no player {want} in the host's sortie: " + ", ".join(
            f"{int(r['player']) + 1} ({r['heroId']})" for r in rows))
    return rows[0]


def join(cfg: dict[str, Any], host: str, *, player: Optional[str] = None, port: int = PORT, exe: Optional[Path] = None,
         extra_args: Optional[list] = None, provision: Optional[Callable[[str], dict]] = None,
         say: Callable[[str], None] = print, wait_s: float = 3.0, give_up_s: float = 3600.0,
         on_start: Optional[Callable[[Any], None]] = None) -> dict[str, Any]:
    """Join the host's co-op sortie from this PC: wait for it, fetch it, install it, get the map,
    start the engine as the chosen player, and try again if the join missed the host's server."""
    t0 = time.time()
    said_wait = False
    meta: dict[str, Any] = {}
    while time.time() - t0 < give_up_s:
        try:
            meta = fetch_meta(host, port)
        except (urllib.error.URLError, OSError, ValueError) as e:
            if not said_wait:
                say(f"Can't reach {host}:{port} yet ({e}). Is the host's launcher running a co-op sortie?")
                said_wait = True
            time.sleep(wait_s)
            continue
        if meta.get("ok") and meta.get("hostUp"):
            break
        if not said_wait:
            say("The host's sortie is loading; waiting for it." if meta.get("ok") else f"The host says: {meta.get('error')}")
            said_wait = True
        time.sleep(wait_s)
    else:
        return {"ok": False, "reason": "gave up waiting for the host"}
    me = pick_player(meta, player)
    say(f"Joining as player {int(me['player']) + 1}, {me['heroId']} ({me['name']}), on {meta.get('mapName')}.")
    zipped = _get(f"http://{host}:{port}/coop/sortie.zip", timeout=300)
    if meta.get("sha256") and hashlib.sha256(zipped).hexdigest() != meta["sha256"]:
        return {"ok": False, "reason": "the sortie changed while it downloaded; run the join again"}
    install(zipped, Path(cfg["modSdd"]))
    if provision and meta.get("mapName"):
        prov = provision(str(meta["mapName"]))
        if prov.get("ok") is False:
            return {"ok": False, "reason": f"map {meta['mapName']} could not be downloaded", "provision": prov}
    exe = exe or S.engine_exe(cfg)
    if meta.get("engine") and exe.parent.name != meta["engine"]:
        say(f"Note: the host runs engine {meta['engine']} and this PC {exe.parent.name}. If the join fails, start BAR once to update it.")
    bar = Path(cfg["barDataRoot"])
    script = bar / "verdance_join.txt"
    script.write_text(join_script(host, int(meta.get("port") or PORT), str(me["name"])), encoding="ascii")
    log = Path(cfg.get("infolog") or (bar / "infolog.txt"))
    tries = 0
    while True:
        tries += 1
        started = time.time()
        args = [str(exe)] + list(extra_args or []) + ["--write-dir", str(bar), str(script)]
        proc = subprocess.Popen(args, cwd=str(bar), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if on_start:
            on_start(proc)
        got_in = False
        while proc.poll() is None:
            time.sleep(wait_s)
            if not got_in:
                got_in = in_game(_since(log, started))
        txt = _since(log, started)
        got_in = got_in or in_game(txt)
        if got_in or not any(k in txt for k in JOIN_MISSED):
            return {"ok": got_in, "tries": tries, "player": me, "exit": proc.returncode,
                    **({} if got_in else {"reason": "the engine closed before it joined; see infolog.txt"})}
        # it missed the host's server: again, while the host still plays this sortie
        try:
            again = fetch_meta(host, port)
        except (urllib.error.URLError, OSError, ValueError):
            again = {}
        if not again.get("ok") or again.get("launchedAt") != meta.get("launchedAt"):
            return {"ok": False, "tries": tries, "reason": "the host's sortie ended before this PC got in"}
        say("Missed the host's game starting; trying again.")

