"""The BAR boundary, kernel-owned (pass five).

One way in:  build (installer writes the seed + startscript) → launch spring.exe ourselves → remember the
             spring pid and the infolog offset.
One way out: tail the infolog from that offset; when a VA_RESULT_JSON_BEGIN..END block completes, reassemble
             it in Python, write inbox/<resultKey>.json (+ latest_va_result.json for the engine), and hand it
             to CampaignKernel.bring_home(extract=False). Spring exit with no result → incomplete.

No PowerShell between the gadget and the campaign state; no receipts file; no live-command channel.
The gadget writes facts once (the manifest is the ending); the kernel reads them once.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_CHUNK = re.compile(r"VA_RESULT_JSON_CHUNK (\d+)/(\d+) (.*)$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- where BAR lives

def bar_config(ws: Path) -> dict[str, Any]:
    """Mirror of scripts/_common.ps1 Get-VerdanceConfig, the parts the kernel needs."""
    cfg: dict[str, Any] = {}
    p = ws / "verdance_config.json"
    if p.is_file():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8-sig")) or {}
        except Exception:  # noqa: BLE001
            cfg = {}
    root = cfg.get("barDataRoot") or os.environ.get("BAR_DATA_ROOT")
    if not root or not Path(root).is_dir():
        cands = []
        la = os.environ.get("LOCALAPPDATA")
        if la:
            cands.append(Path(la) / "Programs" / "Beyond-All-Reason" / "data")
        cands.append(Path.home() / "AppData" / "Local" / "Programs" / "Beyond-All-Reason" / "data")
        root = next((str(c) for c in cands if c.is_dir()), None)
    if not root:
        raise RuntimeError("Could not locate a Beyond All Reason data directory. Set barDataRoot in verdance_config.json or BAR_DATA_ROOT.")
    rootp = Path(root)
    cfg["barDataRoot"] = str(rootp)
    cfg.setdefault("infolog", str(rootp / "infolog.txt"))
    cfg.setdefault("modSdd", str(rootp / "games" / "VerdanceAshes.sdd"))
    cfg.setdefault("seedDestination", str(Path(cfg["modSdd"]) / "singleplayer" / "verdance_ashes" / "generated" / "va_current.lua"))
    return cfg


def engine_exe(cfg: dict[str, Any], name: str = "spring.exe") -> Path:
    ed = cfg.get("engineDir")
    if ed and (Path(ed) / name).is_file():
        return Path(ed) / name
    root = Path(cfg["barDataRoot"]) / "engine"
    if not root.is_dir():
        raise RuntimeError(f"No engine directory under {cfg['barDataRoot']}")
    dirs = sorted((d for d in root.iterdir() if (d / name).is_file()), key=lambda d: d.name, reverse=True)
    if not dirs:
        raise RuntimeError(f"No engine folder containing {name} under {root}")
    return dirs[0] / name


def startscript_from_manifest(ws: Path) -> Optional[Path]:
    """The installer records the startscript it wrote (playable_runs/latest_playable_variant_manifest.json)."""
    for cand in (ws / "playable_runs" / "latest_playable_variant_manifest.json",):
        if cand.is_file():
            try:
                d = json.loads(cand.read_text(encoding="utf-8-sig"))
                p = d.get("startScriptPath")
                if p and Path(p).is_file():
                    return Path(p)
            except Exception:  # noqa: BLE001
                pass
    return None


# ----------------------------------------------------------------------------- process helpers

def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        SYNCHRONIZE = 0x00100000
        h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not h:
            return False
        try:
            # WAIT_TIMEOUT (258) means still running
            return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == 258
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def spring_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return False
    for line in (r.stdout or "").splitlines():
        name = line.split(",", 1)[0].strip().strip('"').lower()
        if name in ("spring.exe", "spring-headless.exe"):
            return True
    return False


# ----------------------------------------------------------------------------- launch

def provision_map(ws: Path, cfg: dict[str, Any], map_name: str) -> dict[str, Any]:
    """A map the player does not own is a fatal content_error before the mutator loads."""
    prov = ws / "tools" / "map_provisioner_v1.py"
    if not prov.is_file() or not map_name:
        return {"skipped": True}
    try:
        r = subprocess.run([sys.executable, str(prov), "--workspace", str(ws), "--bar-data-root", cfg["barDataRoot"], "--map", map_name, "--quiet"],
                           cwd=str(ws), capture_output=True, text=True, timeout=600)
        return {"ok": r.returncode == 0, "returncode": r.returncode, "tail": (r.stdout or r.stderr or "")[-600:]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def launch(ws: Path) -> dict[str, Any]:
    """Start spring.exe on the startscript the build wrote. Returns pid + infolog baseline."""
    try:
        return _launch(ws)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _launch(ws: Path) -> dict[str, Any]:
    cfg = bar_config(ws)
    script = startscript_from_manifest(ws)
    if script is None:
        return {"ok": False, "reason": "no startscript: the build did not run (playable_runs/latest_playable_variant_manifest.json missing)"}
    seed = Path(cfg["seedDestination"])
    if not seed.is_file():
        return {"ok": False, "reason": f"seed missing at {seed}; the installer did not write va_current.lua into BAR"}
    map_name = None
    try:
        for line in script.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*MapName=(.+);", line)
            if m:
                map_name = m.group(1).strip()
                break
    except Exception:  # noqa: BLE001
        pass
    prov = provision_map(ws, cfg, map_name or "")
    if prov.get("ok") is False:
        return {"ok": False, "reason": f"map '{map_name}' could not be provisioned", "provision": prov}
    # the pad and the belief ride beside the seed, wherever the installer put the seed
    gen_src = ws / "mod" / "VerdanceAshes.sdd" / "singleplayer" / "verdance_ashes" / "generated"
    for name in ("va_pad_current.lua", "va_intel_current.lua"):
        src = gen_src / name
        if src.is_file():
            try:
                dst = seed.parent / name
                if dst.resolve() != src.resolve():
                    dst.write_bytes(src.read_bytes())
            except Exception:  # noqa: BLE001
                pass
    exe = engine_exe(cfg)
    infolog = Path(cfg["infolog"])
    baseline = infolog.stat().st_size if infolog.is_file() else 0
    args = [str(exe), "--write-dir", cfg["barDataRoot"], "--only-local", str(script)]
    try:
        proc = subprocess.Popen(args, cwd=cfg["barDataRoot"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=(0x00000008 if sys.platform == "win32" else 0))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "engine": str(exe)}
    report = {"ok": True, "pid": proc.pid, "engine": str(exe), "startScriptPath": str(script), "infologPath": str(infolog),
              "infologBaseline": baseline, "mapName": map_name, "provision": prov, "at": _now(), "schemaVersion": "verdance-launch/2.0"}
    try:
        out = ws / "playable_runs" / "latest_launch.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return report


# ----------------------------------------------------------------------------- the way out

class InfologTail:
    """Reads new bytes of the infolog (shared read; Spring keeps it open) and reassembles result blocks."""

    def __init__(self, path: Path, offset: int = 0) -> None:
        self.path = path
        self.offset = offset
        self._carry = ""
        self._block: Optional[dict[str, Any]] = None
        self.results: list[dict[str, Any]] = []
        self.saw_game_id = False
        self.errors: list[str] = []

    def poll(self) -> list[dict[str, Any]]:
        """Returns newly completed results (parsed JSON dicts, with _raw for archive)."""
        if not self.path.is_file():
            return []
        try:
            size = self.path.stat().st_size
            if size < self.offset:        # Spring truncated it (new launch)
                self.offset = 0
                self._carry = ""
            if size == self.offset:
                return []
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                data = f.read(size - self.offset)
            self.offset = size
        except OSError as e:
            self.errors.append(str(e))
            return []
        text = self._carry + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self._carry = lines.pop()  # partial last line
        out = []
        for line in lines:
            line = line.rstrip("\r")
            if "GameID:" in line:
                self.saw_game_id = True
            if "VA_RESULT_JSON_BEGIN" in line:
                self._block = {"chunks": {}, "total": None}
                continue
            if self._block is not None:
                m = _CHUNK.search(line)
                if m:
                    i, n, body = int(m.group(1)), int(m.group(2)), m.group(3)
                    self._block["chunks"][i] = body
                    self._block["total"] = n
                    continue
                if "VA_RESULT_JSON_END" in line:
                    blk, self._block = self._block, None
                    n = blk["total"] or 0
                    if n and all(k in blk["chunks"] for k in range(1, n + 1)):
                        raw = "".join(blk["chunks"][k] for k in range(1, n + 1))
                        try:
                            obj = json.loads(raw)
                            obj["_raw"] = raw
                            out.append(obj)
                        except Exception as e:  # noqa: BLE001
                            self.errors.append(f"result json parse: {e}")
                    else:
                        self.errors.append(f"result block incomplete: {len(blk['chunks'])}/{n}")
        self.results.extend(out)
        return out


def store_result(ws: Path, obj: dict[str, Any]) -> dict[str, Any]:
    """inbox/<resultKey>.json is the archive; latest_va_result.json is what the engine reads."""
    raw = obj.pop("_raw", None)
    key = str(obj.get("resultKey") or f"unknown_{int(time.time())}")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)
    inbox = ws / "inbox"
    (inbox / "archive").mkdir(parents=True, exist_ok=True)
    text = raw if raw is not None else json.dumps(obj, ensure_ascii=False)
    (inbox / "archive" / f"{safe}.json").write_text(text, encoding="utf-8")
    (inbox / "latest_va_result.json").write_text(text, encoding="utf-8")
    return {"resultKey": key, "path": str(inbox / "archive" / f"{safe}.json")}


def processed_keys(ws: Path) -> set[str]:
    p = ws / "state" / "campaign_state.json"
    try:
        st = json.loads(p.read_text(encoding="utf-8-sig"))
        pr = st.get("processedResults") or []
        if isinstance(pr, dict):
            return set(map(str, pr.keys()))
        return {str(x.get("resultKey") if isinstance(x, dict) else x) for x in pr}
    except Exception:  # noqa: BLE001
        return set()


class SortieWatch:
    """One launch's watcher: tails the infolog, applies new results once, notices the engine closing."""

    def __init__(self, ws: Path, bring_home: Callable[..., dict[str, Any]], incomplete: Callable[..., dict[str, Any]],
                 poll_seconds: float = 2.0, on_event: Optional[Callable[[dict[str, Any]], None]] = None) -> None:
        self.ws = ws
        self.bring_home = bring_home
        self.incomplete = incomplete
        self.poll_seconds = poll_seconds
        self.on_event = on_event
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.phase = "idle"
        self.pid: Optional[int] = None
        self.tail: Optional[InfologTail] = None
        self.applied: list[str] = []
        self.seen: list[str] = []          # every resultKey the log produced this launch (applied or duplicate)
        self.last: Optional[dict[str, Any]] = None
        self.started_at: Optional[str] = None

    def status(self) -> dict[str, Any]:
        return {"schemaVersion": "verdance-sortie-watch/1.0", "phase": self.phase, "pid": self.pid, "applied": self.applied[-5:],
                "startedAt": self.started_at, "last": self.last, "errors": (self.tail.errors[-3:] if self.tail else [])}

    def watch(self, launch_report: dict[str, Any]) -> None:
        self.stop()
        self.pid = launch_report.get("pid")
        self.tail = InfologTail(Path(launch_report.get("infologPath") or ""), int(launch_report.get("infologBaseline") or 0))
        self.applied = []
        self.seen = []
        self.phase = "launching"
        self.started_at = _now()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="va-sortie-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)

    def _emit(self, ev: dict[str, Any]) -> None:
        self.last = dict(ev, at=_now())
        if self.on_event:
            try:
                self.on_event(self.last)
            except Exception:  # noqa: BLE001
                pass

    def _loop(self) -> None:
        quiet_after_exit = 0
        while not self._stop.is_set():
            try:
                new = self.tail.poll() if self.tail else []
                if self.phase == "launching" and self.tail and self.tail.saw_game_id:
                    self.phase = "in-game"
                    self._emit({"event": "in-game"})
                done = processed_keys(self.ws)
                for obj in new:
                    key = str(obj.get("resultKey") or "")
                    if key:
                        self.seen.append(key)
                    if key and key in done:
                        self._emit({"event": "duplicate", "resultKey": key})
                        continue
                    stored = store_result(self.ws, obj)
                    self.phase = "bringing-home"
                    self._emit({"event": "result", "resultKey": stored["resultKey"]})
                    report = self.bring_home(extract=False, skip_advance=False, mode="auto")
                    self.applied.append(stored["resultKey"])
                    self._emit({"event": "applied", "resultKey": stored["resultKey"], "ok": report.get("ok"), "verdict": report.get("verdict")})
                    self.phase = "in-game"
                alive = pid_alive(self.pid)
                if not alive:
                    quiet_after_exit += 1
                    # one more read after exit so a result written on the way out is not missed
                    if quiet_after_exit >= 2:
                        if self.tail:
                            for obj in self.tail.poll():
                                key = str(obj.get("resultKey") or "")
                                if key:
                                    self.seen.append(key)
                                if key and key not in processed_keys(self.ws):
                                    store_result(self.ws, obj)
                                    report = self.bring_home(extract=False, skip_advance=False, mode="auto")
                                    self.applied.append(key)
                                    self._emit({"event": "applied", "resultKey": key, "ok": report.get("ok")})
                        if not self.applied and not self.seen:
                            self.phase = "closed-without-result"
                            rep = self.incomplete(reason="closed_without_result", extract_info={"watch": self.status()}, mode="auto")
                            self._emit({"event": "incomplete", "ok": False, "headline": rep.get("headline")})
                        else:
                            self.phase = "home"
                            self._emit({"event": "home", "applied": list(self.applied)})
                        return
            except Exception as e:  # noqa: BLE001
                self._emit({"event": "error", "error": f"{type(e).__name__}: {e}"})
            self._stop.wait(self.poll_seconds)
