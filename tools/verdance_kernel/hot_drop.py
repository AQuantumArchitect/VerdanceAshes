"""Hot drop: load the field while the player chooses, then drop the company into the running game.

Picking a sortie fixes the map and the enemy; only the company is still open. So the kernel builds
and launches as soon as the sortie is chosen, with every pack the company could send compiled into
the mission, and the game sits loaded and paused with nothing of ours on the field. When the player
presses Drop, the kernel writes the final roster to a small file in BAR's data folder; the
Verdance hot-drop widget reads it, hands it to the campaign gadget (which spawns those packs on the
pad) and leaves the field paused: the fight starts when the player switches over and unpauses.
The load (about 40 seconds) happens while the player reads and chooses.

    outbox/hot_drop.json                       the armed token; the mission builder copies it into
                                               the mission (mission.hotDrop.token)
    <BAR data>/LuaUI/Config/verdance/drop.txt  "token|pack,pack|unitdef:n,unitdef:n" on Drop

The token keeps a stale drop file from a previous game from ever dropping anyone.
"""
from __future__ import annotations

import ctypes
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from verdance.common import utc_now

ARM_FILE = ("outbox", "hot_drop.json")
DROP_REL = ("LuaUI", "Config", "verdance", "drop.txt")


def arm_path(ws: Path) -> Path:
    return Path(ws).joinpath(*ARM_FILE)


def drop_path(bar_root: str | Path) -> Path:
    return Path(bar_root).joinpath(*DROP_REL)


def arm(ws: Path, bar_root: str | Path | None) -> str:
    """A new token for this launch. Clears any drop file a previous game left behind."""
    token = secrets.token_hex(6)
    p = arm_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"token": token, "armedAt": utc_now()}) + "\n", encoding="utf-8")
    if bar_root:
        try:
            drop_path(bar_root).unlink()
        except OSError:
            pass
    return token


def disarm(ws: Path) -> None:
    """An ordinary drop: the mission spawns the company at the start, as before."""
    try:
        arm_path(ws).unlink()
    except OSError:
        pass


def drop_line(token: str, band: Iterable[str], reserve: dict[str, int]) -> str:
    packs = ",".join(str(h) for h in band if str(h))
    units = ",".join(f"{d}:{int(n)}" for d, n in sorted(reserve.items()) if int(n or 0) > 0)
    return f"{token}|{packs}|{units}"


def write_drop(bar_root: str | Path, line: str) -> Path:
    p = drop_path(bar_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(line + "\n", encoding="utf-8")
    os.replace(tmp, p)              # the widget never reads half a line
    return p


def record_roster(ws: Path, band: list[str], aces: list[str]) -> None:
    """The launch compiled every candidate; the files the homecoming reads name who actually went."""
    for rel in (("outbox", "hub_deploy_plan.latest.json"), ("outbox", "next_sortie_order.json"),
                ("outbox", "next_mission_intent.json")):
        p = Path(ws).joinpath(*rel)
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        data["crewBand"] = list(band)
        data["deployAces"] = list(aces)
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---- the engine window (Windows) ---------------------------------------------------------------

def _windows_of(pid: int) -> list[int]:
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    found: list[int] = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def each(hwnd, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(proto(each), 0)
    return found


def keep_behind(pid: int, until: threading.Event, seconds: float = 120.0) -> threading.Thread:
    """While the field loads, keep the engine window minimized so the hub stays in front."""
    def run() -> None:
        if sys.platform != "win32":
            return
        end = time.time() + seconds
        while time.time() < end and not until.is_set():
            for hwnd in _windows_of(pid):
                if not ctypes.windll.user32.IsIconic(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 6)        # SW_MINIMIZE
            until.wait(0.5)
    t = threading.Thread(target=run, name="va-hotdrop-behind", daemon=True)
    t.start()
    return t


def wake_behind(pid: int) -> bool:
    """Un-minimize the engine window without taking the foreground, and park it under the hub:
    BAR draws again (so it reads the drop file at once) while the hub keeps the screen. The
    company lands paused; the player switches over and unpauses when ready."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    ok = False
    for hwnd in _windows_of(pid):
        user32.ShowWindow(hwnd, 4)                                   # SW_SHOWNOACTIVATE
        # HWND_BOTTOM, with SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        ok = bool(user32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)) or ok
    return ok


def stop_engine(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True, timeout=15)
        else:
            os.kill(int(pid), 15)
        return True
    except Exception:  # noqa: BLE001
        return False


def status_of(hot: dict[str, Any] | None, watch_phase: str | None) -> dict[str, Any]:
    """loading → ready (the level is in, paused, waiting) → dropped; none when nothing is armed."""
    if not hot:
        return {"phase": "none"}
    if hot.get("dropped"):
        # once the fight is over (result home, or BAR closed) the drop is history
        phase = "none" if watch_phase in ("home", "closed-without-result") else "dropped"
    elif watch_phase == "in-game":
        phase = "ready"
    elif watch_phase in ("launching", None, "idle"):
        phase = "loading"
    else:
        phase = "closed"
    return {"phase": phase, "mapId": hot.get("mapId"), "token": hot.get("token"), "armedAt": hot.get("at")}
