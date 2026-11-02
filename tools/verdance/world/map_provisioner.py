#!/usr/bin/env python3
"""Make sure the map a mission needs is on disk before BAR is asked to load it.

Why this exists
---------------
A missing map is not a soft failure. The engine dies in PreGame before the
mutator ever loads:

    [PreGame::AddMapArchivesToVFS] using map "Greenest Fields 1.3.1" (loaded=0 cached=0)
    Fatal: [ExitSpringProcess] errorMsg="Dependent archive ... not found"

To a player that reads as "the game crashed on launch," with nothing naming the
cause. Auto-download in BAR is a *lobby* behaviour -- Chobby calls
VFS.DownloadArchive -- and a direct start-script launch does not inherit it. So
nothing in the campaign path acquires maps, and a fresh install has none of the
seven.

BAR runs its own content service, and it is a plain JSON API:

    GET https://files-cdn.beyondallreason.dev/find?category=map&springname=The+Rock+Jungle+2.1.1
    -> [{"filename": "...sd7", "md5": "...", "size": 106567121, "mirrors": ["https://..."]}]

That is what this uses, accepting the answer as a list or as a single object (2026-11-01: the
service answered Greenest Fields with an object, and a fresh install on a friend's PC could not
get its first map). Every mirror is tried, and when the service or its mirrors fail, the engine's
own pr-downloader (shipped in every BAR engine folder, the tool BAR's launcher fetches maps with)
gets the map instead. Not bundling: the seven campaign maps total ~673 MB
against a 12 MB dist, and shipping them would redistribute seven map authors'
work -- throwing away the whole reason this project has a clean legal posture.
The player's own client downloads them from the project that hosts them.

Stdlib only, so the embedded CPython in the dist can run it with no extra deps.

  python -m verdance.world.map_provisioner --map "The Rock Jungle 2.1.1"
  python -m verdance.world.map_provisioner --check-all        # every campaign map
  python -m verdance.world.map_provisioner --check-all --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, load_json

FIND_URL = "https://files-cdn.beyondallreason.dev/find"
USER_AGENT = "VerdanceAshes-map-provisioner/1.0 (+campaign mutator)"
TIMEOUT = 60
CHUNK = 1 << 20  # 1 MiB


class MapProvisionError(RuntimeError):
    pass


def workspace_root(explicit: str = "") -> Path:
    return Path(explicit).resolve() if explicit else WORKSPACE_ROOT


def bar_data_root(workspace: Path, explicit: str = "") -> Path:
    if explicit:
        return Path(explicit)
    cfg = workspace / "verdance_config.json"
    if not cfg.exists():
        raise MapProvisionError(
            f"No {cfg} -- run SETUP.bat first, or pass --bar-data-root.")
    root = (load_json(cfg) or {}).get("barDataRoot")
    if not root:
        raise MapProvisionError(f"No barDataRoot in {cfg}.")
    return Path(root)


def campaign_maps(workspace: Path) -> List[Dict[str, str]]:
    pool = load_json(workspace / "data" / "map_pool" / "seven_maps.json")
    out = []
    for m in pool.get("maps") or []:
        name = str(m.get("mapName") or "").strip()
        if name:
            out.append({"id": str(m.get("id")), "mapName": name,
                        "title": str(m.get("title") or m.get("id")),
                        "archive": str(m.get("archivePattern") or "")})
    return out


def resolve(map_name: str) -> Dict[str, Any]:
    """Ask BAR's content service where this map lives."""
    q = urllib.parse.urlencode({"category": "map", "springname": map_name})
    req = urllib.request.Request(f"{FIND_URL}?{q}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced to the player verbatim
        raise MapProvisionError(f"could not reach BAR's map service: {exc}") from exc

    # The service answers a list of matches, or (2026-11) a single object.
    entry = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(entry, dict) or not entry.get("filename"):
        raise MapProvisionError(
            f"BAR's map service does not know a map named {map_name!r}. "
            "Check the mapName in data/map_pool/seven_maps.json.")
    mirrors = [m for m in (entry.get("mirrors") or []) if isinstance(m, str) and m]
    if entry.get("md5"):
        mirrors.append(f"https://files-cdn.beyondallreason.dev/file/{entry['md5']}/{entry['filename']}")
    entry["mirrors"] = list(dict.fromkeys(mirrors))
    if not entry["mirrors"]:
        raise MapProvisionError(f"no download mirror listed for {map_name!r}.")
    return entry


def pr_downloader(bar_root: Path) -> Optional[Path]:
    """The engine's own downloader (engine/<version>/pr-downloader.exe), newest engine first."""
    eng = Path(bar_root) / "engine"
    if not eng.is_dir():
        return None
    for d in sorted((p for p in eng.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        for name in ("pr-downloader.exe", "pr-downloader"):
            if (d / name).is_file():
                return d / name
    return None


def _engine_fetch(map_name: str, bar_root: Path, archive: Optional[str], quiet: bool) -> Optional[Path]:
    """Let BAR's pr-downloader fetch the map into <bar_root>/maps, as BAR's launcher does. Returns the
    archive on disk, or None when there is no pr-downloader or it did not produce the map."""
    exe = pr_downloader(bar_root)
    if exe is None:
        return None
    maps_dir = Path(bar_root) / "maps"
    before = {p.name for p in maps_dir.glob("*.sd7")} if maps_dir.is_dir() else set()
    if not quiet:
        print(f"  Fetching {map_name} with BAR's own downloader...", flush=True)
    try:
        subprocess.run([str(exe), "--filesystem-writepath", str(bar_root), "--download-map", map_name],
                       cwd=str(exe.parent), capture_output=True, text=True, timeout=1800)
    except Exception:  # noqa: BLE001 - None tells the caller it did not work
        return None
    if archive and (maps_dir / archive).exists():
        return maps_dir / archive
    new = [p for p in maps_dir.glob("*.sd7") if p.name not in before] if maps_dir.is_dir() else []
    return new[0] if new else None


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest: Path, expect_md5: str, expect_size: int,
              on_progress: Optional[Callable[[int, int], None]]) -> None:
    """Stream to <dest>.part, verify, then rename.

    Never writes dest directly: a half-finished .sd7 in BAR's maps folder is
    indistinguishable from a real one and produces the same fatal error later,
    at a point where nobody would suspect the download.
    """
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    h = hashlib.md5()
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(part, "wb") as out:
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                out.write(block)
                h.update(block)
                done += len(block)
                if on_progress:
                    on_progress(done, expect_size)
    except Exception as exc:  # noqa: BLE001
        part.unlink(missing_ok=True)
        raise MapProvisionError(f"download failed: {exc}") from exc

    got = h.hexdigest()
    if expect_md5 and got != expect_md5:
        part.unlink(missing_ok=True)
        raise MapProvisionError(
            f"checksum mismatch (expected {expect_md5}, got {got}). Not installing.")
    os.replace(part, dest)


class ProgressFile:
    """Writes {map, bytes, total, percent, state, error} to a small JSON file the hub can poll.

    state is one of downloading | done | failed. Rewritten at most every `every` seconds
    while bytes arrive (and always on a state change), atomically via os.replace so a
    reader never sees a half-written file.
    """

    def __init__(self, path: Path, map_name: str, every: float = 2.0) -> None:
        self.path = Path(path)
        self.map_name = map_name
        self.every = every
        self._last = 0.0
        self._bytes = 0
        self._total = 0

    def _write(self, state: str, error: Optional[str] = None) -> None:
        pct = int(self._bytes * 100 / self._total) if self._total else (100 if state == "done" else 0)
        rec = {"schemaVersion": "verdance-provision/1.0", "map": self.map_name, "bytes": self._bytes,
               "total": self._total, "percent": max(0, min(100, pct)), "state": state, "error": error,
               "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(rec), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass
        self._last = time.monotonic()

    def start(self, total: int = 0) -> None:
        self._bytes, self._total = 0, int(total or 0)
        self._write("downloading")

    def progress(self, done: int, total: int) -> None:
        self._bytes, self._total = int(done), int(total or self._total)
        if time.monotonic() - self._last >= self.every or (self._total and done >= self._total):
            self._write("downloading")

    def done(self, total: int = 0) -> None:
        if total:
            self._bytes = self._total = int(total)
        elif self._total:
            self._bytes = self._total
        self._write("done")

    def failed(self, error: str) -> None:
        self._write("failed", error=str(error))


def _chain_progress(*callbacks: Optional[Callable[[int, int], None]]) -> Optional[Callable[[int, int], None]]:
    live = [cb for cb in callbacks if cb]
    if not live:
        return None

    def report(done: int, total: int) -> None:
        for cb in live:
            cb(done, total)

    return report


def _default_progress(name: str) -> Callable[[int, int], None]:
    state = {"pct": -1}

    def report(done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 0
        if pct >= state["pct"] + 5:
            state["pct"] = pct
            mb, tot = done / 1048576, (total or 0) / 1048576
            print(f"    {name}: {pct:3d}%  ({mb:.0f}/{tot:.0f} MB)", flush=True)

    return report


def archive_for(workspace: Optional[Path], map_name: str) -> Optional[str]:
    """The .sd7 filename this map is known by, from the pool -- no network."""
    if workspace is None:
        return None
    try:
        for m in campaign_maps(workspace):
            if m["mapName"].strip() == map_name.strip():
                return m["archive"].strip() or None
    except Exception:  # noqa: BLE001 - a missing pool is not fatal here
        return None
    return None


def ensure(map_name: str, bar_root: Path, workspace: Optional[Path] = None,
           dry_run: bool = False, verify: bool = False,
           quiet: bool = False, progress: Optional[ProgressFile] = None) -> Dict[str, Any]:
    """Guarantee <bar_root>/maps/<archive> exists. Returns a status dict.

    Disk is checked BEFORE the network, which matters more than it looks. This
    runs on the launch path of every mission, and the first version asked BAR's
    CDN where the map lived before asking whether the file was already sitting
    there -- so a player with all seven maps installed still could not start a
    mission on a plane, behind a captive portal, or during a CDN blip. The
    preflight that exists to prevent a crash would have become a new way to fail.

    The pool records each map's archive filename, so the common case needs no
    network at all.
    """
    maps_dir = bar_root / "maps"

    known = archive_for(workspace, map_name)
    if known and (maps_dir / known).exists() and not verify:
        if progress:
            progress.done()
        return {"map": map_name, "status": "present", "path": str(maps_dir / known)}

    if progress:
        progress.start()
    try:
        entry = resolve(map_name)
    except MapProvisionError as exc:
        # The service is down, blocked or changed: BAR's own downloader may still get it.
        got = None if dry_run else _engine_fetch(map_name, bar_root, known, quiet)
        if got is not None:
            if progress:
                progress.done()
            return {"map": map_name, "status": "downloaded", "path": str(got), "via": "pr-downloader"}
        if progress:
            progress.failed(str(exc))
        raise
    filename = str(entry["filename"])
    dest = maps_dir / filename
    size = int(entry.get("size") or 0)
    md5 = str(entry.get("md5") or "")

    if dest.exists():
        # Size match is enough for a file BAR itself installed -- re-hashing
        # ~673 MB of maps on every launch would cost more than it protects.
        # Anything WE wrote was md5-verified before it got this name, so the
        # only unverified files here are BAR's own. --verify forces the check.
        local = dest.stat().st_size
        if local == size and not verify:
            if progress:
                progress.done(size)
            return {"map": map_name, "status": "present", "path": str(dest)}
        if verify and md5 and _md5(dest) == md5:
            if progress:
                progress.done(size)
            return {"map": map_name, "status": "verified", "path": str(dest)}
        if local == size and verify:
            if progress:
                progress.failed("right size, wrong checksum")
            return {"map": map_name, "status": "corrupt", "path": str(dest)}
        if not quiet:
            print(f"    {filename} is the wrong size ({local} vs {size}); refetching.")

    if dry_run:
        if progress:
            progress.done()
        return {"map": map_name, "status": "would-download",
                "path": str(dest), "sizeMB": round(size / 1048576, 1)}

    maps_dir.mkdir(parents=True, exist_ok=True)
    if not quiet:
        print(f"  Downloading {map_name} ({size / 1048576:.0f} MB) from BAR's map service...")
    if progress:
        progress.start(size)
    errors: List[str] = []
    for url in entry["mirrors"]:
        try:
            _download(url, dest, md5, size,
                      _chain_progress(None if quiet else _default_progress(filename),
                                      progress.progress if progress else None))
            break
        except MapProvisionError as exc:
            errors.append(str(exc))
    else:
        got = _engine_fetch(map_name, bar_root, filename, quiet)
        if got is not None:
            if progress:
                progress.done(size)
            return {"map": map_name, "status": "downloaded", "path": str(got), "via": "pr-downloader"}
        msg = "; ".join(errors) or "download failed"
        if progress:
            progress.failed(msg)
        raise MapProvisionError(msg)
    if progress:
        progress.done(size)
    return {"map": map_name, "status": "downloaded", "path": str(dest)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default="")
    ap.add_argument("--bar-data-root", default="")
    ap.add_argument("--map", default="", help='BAR map name, e.g. "Koom Valley 3 3.1"')
    ap.add_argument("--map-id", default="", help="campaign map id, e.g. koom_valley")
    ap.add_argument("--check-all", action="store_true", help="every campaign map")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true", help="md5 files already present")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--progress-json", default="",
                    help="write {map, bytes, total, percent, state, error} here at least every 2 s "
                         "(the kernel passes outbox/provision.latest.json so the hub can poll it)")
    args = ap.parse_args()

    ws = workspace_root(args.workspace)
    try:
        bar_root = bar_data_root(ws, args.bar_data_root)
    except MapProvisionError as exc:
        print(f"FAIL {exc}")
        return 2

    wanted: List[str] = []
    if args.check_all:
        wanted = [m["mapName"] for m in campaign_maps(ws)]
    elif args.map:
        wanted = [args.map]
    elif args.map_id:
        hit = [m for m in campaign_maps(ws) if m["id"] == args.map_id]
        if not hit:
            print(f"FAIL no map with id {args.map_id!r} in the seven-map pool.")
            return 2
        wanted = [hit[0]["mapName"]]
    else:
        print("FAIL pass one of --map, --map-id or --check-all.")
        return 2

    rc = 0
    for name in wanted:
        progress = ProgressFile(Path(args.progress_json), name) if args.progress_json else None
        try:
            res = ensure(name, bar_root, workspace=ws, dry_run=args.dry_run,
                         verify=args.verify, quiet=args.quiet, progress=progress)
            if not args.quiet or res["status"] not in ("present", "verified"):
                print(f"  {res['status']:<16} {name}")
            if res["status"] == "corrupt":
                print(f"    ^ right size, wrong checksum: {res['path']}")
                rc = 1
        except MapProvisionError as exc:
            if progress:
                progress.failed(str(exc))
            print(f"  FAILED           {name}: {exc}")
            rc = 1
        except Exception as exc:  # noqa: BLE001 - the status file must still say failed
            if progress:
                progress.failed(f"{type(exc).__name__}: {exc}")
            raise
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
