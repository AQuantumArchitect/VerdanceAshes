#!/usr/bin/env python3
"""Zip a fresh Verdance campaign through the real hub buttons and the real extract.

The sandbox is a separate workspace. This never resets the live My Games
campaign and never calls reset_campaign.ps1 (that script kills port 8770 and
deletes the live mission seed).

Drop on the sandbox kernel is headless when VERDANCE_ZIP=1. The autoplay
gadget then teleports the company onto the objective, explodes hostiles
(wrecks, not reclaim), and stands on the extract pad until the match logs
a real result.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LIVE = Path(r"C:\Users\Luke Spooner\Documents\My Games\VerdanceAshes")
PY = LIVE / "runtime" / "python" / "python.exe"
MAPS = (
    "greenest_fields",
    "eye_of_horus",
    "koom_valley",
    "tabula",
    "ancient_bastion",
    "the_rock_jungle",
    "all_that_simmers",
)
PREFERRED_BAND = ("solarium", "consul", "mira")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _spring_open() -> str | None:
    try:
        r = subprocess.run(
            [
                "tasklist",
                "/FI",
                "IMAGENAME eq spring.exe",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        text = (r.stdout or "") + (r.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return f"tasklist failed: {exc}"
    low = text.lower()
    if "spring.exe" in low or "spring-headless.exe" in low:
        return text.strip()
    r2 = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq spring-headless.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    text2 = (r2.stdout or "").lower()
    if "spring-headless.exe" in text2:
        return (r2.stdout or "").strip()
    return None


def _http(port: int, method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            code = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        code = exc.code
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:500]}
    if not isinstance(parsed, dict):
        parsed = {"value": parsed}
    parsed["_http"] = code
    return parsed


def _junction(link: Path, target: Path) -> None:
    if link.exists():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(["cmd", "/c", "mklink", "/J", str(link), str(target)])


def _copy_showoff(sandbox: Path) -> None:
    src = LIVE / "app" / "showoff"
    dest = sandbox / "app" / "showoff"
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.name in ("hub_state.json", "hub_state.embed.js"):
            continue
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def ensure_sandbox(sandbox: Path) -> None:
    sandbox.mkdir(parents=True, exist_ok=True)
    for name in ("tools", "scripts", "data", "mod"):
        _junction(sandbox / name, LIVE / name)
    for name in ("state", "outbox", "inbox", "ledger", "playable_runs"):
        (sandbox / name).mkdir(parents=True, exist_ok=True)
    _copy_showoff(sandbox)
    # Generated scenario json lives under the data junction, so a zip build
    # rewrites the live playable intent. The next real Drop rebuilds it.
    (sandbox / "outbox").mkdir(parents=True, exist_ok=True)


def write_fresh_state(sandbox: Path) -> None:
    tools = str(sandbox / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from verdance_story_engine_v1 import default_v1_state, migrate_state, save_json

    state = migrate_state(default_v1_state())
    path = sandbox / "state" / "campaign_state.json"
    save_json(path, state)


def backup_live_seed() -> Path | None:
    local = os.environ.get("LOCALAPPDATA") or ""
    seed = (
        Path(local)
        / "Programs"
        / "Beyond-All-Reason"
        / "data"
        / "games"
        / "VerdanceAshes.sdd"
        / "singleplayer"
        / "verdance_ashes"
        / "generated"
        / "va_current.lua"
    )
    if not seed.is_file():
        return None
    dest = Path(os.environ.get("TEMP") or ".") / "va-zip-live-seed" / "va_current.lua"
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed, dest)
    return dest


def restore_live_seed() -> str:
    local = os.environ.get("LOCALAPPDATA") or ""
    seed = (
        Path(local)
        / "Programs"
        / "Beyond-All-Reason"
        / "data"
        / "games"
        / "VerdanceAshes.sdd"
        / "singleplayer"
        / "verdance_ashes"
        / "generated"
        / "va_current.lua"
    )
    src = Path(os.environ.get("TEMP") or ".") / "va-zip-live-seed" / "va_current.lua"
    if not src.is_file():
        return "no backup"
    if _spring_open():
        return "spring still open; left the seed in place"
    seed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, seed)
    return str(seed)


def start_kernel(sandbox: Path, port: int) -> None:
    env = os.environ.copy()
    env["VERDANCE_ZIP"] = "1"
    env["VERDANCE_PY"] = str(PY)
    env["PYTHONPATH"] = str(sandbox / "tools")
    log = sandbox / "outbox" / "zip_kernel.log"
    handle = log.open("a", encoding="utf-8")
    handle.write(f"\n--- kernel {_now()} port={port} ---\n")
    handle.flush()
    subprocess.Popen(
        [
            str(PY),
            "-m",
            "verdance_kernel",
            "launch",
            "--workspace",
            str(sandbox),
            "--port",
            str(port),
            "--no-ui",
            "--no-browser",
        ],
        cwd=str(sandbox),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


def wait_kernel(port: int, sandbox: Path, timeout: float = 90) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        try:
            last = _http(port, "GET", "/api/status", timeout=5)
        except Exception as exc:  # noqa: BLE001
            last = {"error": str(exc)}
            time.sleep(2)
            continue
        if last.get("_http") == 200 and Path(str(last.get("workspace") or "")).resolve() == sandbox.resolve():
            return last
        if last.get("_http") == 200:
            raise SystemExit(
                f"port {port} is a different workspace: {last.get('workspace')}"
            )
        time.sleep(2)
    raise SystemExit(f"sandbox kernel did not come up: {last}")


def hub_of(port: int) -> dict:
    payload = _http(port, "GET", "/api/hub-state", timeout=20)
    hub = payload.get("hub")
    if not isinstance(hub, dict):
        raise RuntimeError(f"hub missing: {payload.get('error') or payload}")
    return hub


def pick_band(hub: dict) -> list[str]:
    company = hub.get("company") or {}
    cap = int(company.get("seatCap") or 3)
    pool = [c for c in (company.get("pool") or []) if isinstance(c, dict)]
    by_id = {str(c.get("id")): c for c in pool}
    tnb = int(company.get("formationWalletTnb") or 0)
    km = int(company.get("formationWalletKm") or 0)

    def affordable(ids: list[str]) -> bool:
        spend_t = 0
        spend_k = 0
        for hid in ids:
            card = by_id.get(hid) or {}
            spend_t += int(card.get("hireTnb") or 0)
            spend_k += int(card.get("hireKm") or 0)
        return spend_t <= tnb and spend_k <= km and len(ids) == cap

    preferred = [hid for hid in PREFERRED_BAND if hid in by_id]
    if affordable(preferred):
        return preferred
    ranked = sorted(
        pool,
        key=lambda c: (int(c.get("hireTnb") or 0) + int(c.get("hireKm") or 0), str(c.get("id"))),
    )
    picked: list[str] = []
    spend_t = 0
    spend_k = 0
    for card in ranked:
        if str(card.get("role") or "band") != "band":
            continue
        hid = str(card.get("id") or "")
        if not hid or hid in picked:
            continue
        nt = int(card.get("hireTnb") or 0)
        nk = int(card.get("hireKm") or 0)
        if spend_t + nt > tnb or spend_k + nk > km:
            continue
        picked.append(hid)
        spend_t += nt
        spend_k += nk
        if len(picked) == cap:
            return picked
    raise RuntimeError(f"could not afford {cap} packs from wallet tnb={tnb} km={km}")


def choices_of(hub: dict) -> list[dict]:
    node = hub.get("node") or {}
    raw = node.get("choices") or hub.get("choices") or []
    return [c for c in raw if isinstance(c, dict)]


def pick_choice(hub: dict, visited: set[str] | None = None) -> dict:
    """Any of the three cards is a legal drop. Prefer a fight or a road not yet walked."""
    rows = choices_of(hub)
    if not rows:
        raise RuntimeError("hub has no sortie choices")
    seen = visited or set()

    def score(row: dict) -> tuple[int, int, int]:
        effect = row.get("effect") or {}
        fight = str(effect.get("mapId") or "")
        head = str(effect.get("headingMapId") or "")
        return (
            1 if fight and fight not in seen else 0,
            1 if head and head not in seen else 0,
            1 if row.get("recommended") is True else 0,
        )

    return max(rows, key=score)


def plan_from(hub: dict, choice: dict) -> dict:
    effect = choice.get("effect") or {}
    company = hub.get("company") or {}
    infil = effect.get("infilZoneId") or effect.get("preferredDeployZoneId") or effect.get("deploymentZoneId")
    exfil = effect.get("exfilZoneId") or effect.get("preferredExtractionZoneId") or effect.get("extractionZoneId") or infil
    capture = effect.get("preferredCaptureZoneId") or (effect.get("captureZoneIds") or [None])[0] or infil
    band = list(company.get("deployBand") or company.get("band") or [])
    aces = list(company.get("deployAces") or [])
    return {
        "schemaVersion": "verdance-deploy-plan/1.0",
        "mapId": effect.get("mapId") or hub.get("sessionHomeMap"),
        "contractKind": effect.get("contractKind") or "seize_lane",
        "deployAces": aces,
        "crewBand": band,
        "choiceId": choice.get("id"),
        "marks": {
            "deployZoneId": infil,
            "extractZoneId": exfil,
            "captureZoneIds": [capture] if capture else [],
        },
        "sessionMode": effect.get("sessionMode") or hub.get("sessionMode") or "same_map",
        "against": effect.get("against") or "armada",
        "wetReach": bool(effect.get("wetReach") and effect.get("infilZoneId") and effect.get("exfilZoneId")),
        "infilZoneId": effect.get("infilZoneId"),
        "exfilZoneId": effect.get("exfilZoneId"),
        "headingMapId": effect.get("headingMapId"),
        "headingZoneId": effect.get("headingZoneId"),
        "alongTheWay": list(effect.get("alongTheWay") or []),
        "occupationModel": hub.get("occupationModel") or "living_shell",
        "pathSignal": hub.get("pathSignal"),
        "patron": "nullmercs",
        "arcId": ((hub.get("arc") or {}).get("id") or 1),
    }


def _slim(got: dict) -> dict:
    return {
        "ok": got.get("ok"),
        "skipped": got.get("skipped"),
        "error": got.get("error"),
        "http": got.get("_http"),
    }


def press_buttons(port: int, hub: dict, report: dict) -> None:
    """Shop, camp raise, camp talk, and the roster lock. Shop cards use id as listingId."""
    entry: dict = {"mission": hub.get("missionNumber")}
    shop = ((hub.get("commerce") or {}).get("shop") or [])
    listing = next(
        (
            s
            for s in shop
            if isinstance(s, dict)
            and s.get("available")
            and not s.get("owned")
            and (s.get("listingId") or s.get("id"))
        ),
        None,
    )
    if listing:
        lid = str(listing.get("listingId") or listing.get("id"))
        got = _http(port, "POST", "/api/purchase", {"listingId": lid})
        entry["purchase"] = {"id": lid, **_slim(got)}
    else:
        entry["purchase"] = {"skipped": True, "reason": "no available listing"}
    entry["home-build"] = _slim(_http(port, "POST", "/api/home-build", {}))
    talks = ((hub.get("supportWeb") or {}).get("eligibleTalks") or [])
    talk = next((t for t in talks if isinstance(t, dict) and t.get("id")), None)
    if talk:
        got = _http(
            port,
            "POST",
            "/api/camp-talk",
            {"talkId": talk.get("id"), "a": talk.get("a") or "", "b": talk.get("b") or ""},
        )
        entry["camp-talk"] = {"id": talk.get("id"), **_slim(got)}
    else:
        entry["camp-talk"] = {"skipped": True, "reason": "no eligible talk"}
    entry["deploy-roster"] = _slim(_http(port, "POST", "/api/deploy-roster", {"crewBand": []}))
    report.setdefault("presses", []).append(entry)


def wait_sortie(port: int, sandbox: Path, before: int, history_before: int, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_phase = None
    kernel_misses = 0
    while time.time() < deadline:
        phase = None
        detail = None
        status_path = sandbox / "outbox" / "play_session.status.json"
        if status_path.is_file():
            try:
                blob = json.loads(status_path.read_text(encoding="utf-8-sig"))
                phase = blob.get("phase")
                detail = blob.get("message") or blob.get("error")
            except Exception:
                phase = None
        try:
            hub = hub_of(port)
            mission = int(hub.get("missionNumber") or 0)
            kernel_misses = 0
        except Exception as exc:  # noqa: BLE001
            mission = before
            hub = {"error": str(exc)}
            kernel_misses += 1
            if kernel_misses >= 6:
                return {
                    "ok": False,
                    "mission": mission,
                    "phase": phase,
                    "reason": "sandbox kernel stopped answering",
                    "detail": str(exc),
                }
        history = history_before
        state_path = sandbox / "state" / "campaign_state.json"
        if state_path.is_file():
            try:
                history = len(json.loads(state_path.read_text(encoding="utf-8-sig")).get("history") or [])
            except Exception:
                history = history_before
        advanced = mission > before or history > history_before
        spring = _spring_open()
        if phase in ("error", "no-result") and not spring:
            return {
                "ok": False,
                "mission": mission,
                "phase": phase,
                "history": history,
                "detail": detail,
                "hubError": hub.get("error"),
            }
        if phase == "session-complete" and not spring:
            return {
                "ok": advanced,
                "mission": mission,
                "phase": phase,
                "history": history,
                "reason": None if advanced else "session ended without a mission advance",
            }
        last_phase = phase
        time.sleep(5)
    return {"ok": False, "phase": last_phase, "reason": "timeout", "mission": before}


def history_len(sandbox: Path) -> int:
    path = sandbox / "state" / "campaign_state.json"
    if not path.is_file():
        return 0
    try:
        return len(json.loads(path.read_text(encoding="utf-8-sig")).get("history") or [])
    except Exception:
        return 0


def visited_maps(sandbox: Path) -> list[str]:
    path = sandbox / "state" / "campaign_state.json"
    if not path.is_file():
        return []
    try:
        state = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    seen = []
    for bead in state.get("history") or []:
        if not isinstance(bead, dict):
            continue
        mid = str(bead.get("mapId") or bead.get("sortieMapId") or "")
        if mid and mid not in seen:
            seen.append(mid)
    return seen


def run(sandbox: Path, port: int, sorties: int, fresh: bool) -> dict:
    if sandbox.resolve() == LIVE.resolve():
        raise SystemExit("refusing to zip the live My Games campaign")
    open_spring = _spring_open()
    if open_spring:
        raise SystemExit("spring is already open; not starting a second match.\n" + open_spring)
    ensure_sandbox(sandbox)
    seed_backup = backup_live_seed()
    if fresh or not (sandbox / "state" / "campaign_state.json").is_file():
        write_fresh_state(sandbox)
    report: dict = {
        "startedAt": _now(),
        "sandbox": str(sandbox),
        "port": port,
        "liveUntouched": str(LIVE / "state" / "campaign_state.json"),
        "seedBackup": str(seed_backup) if seed_backup else None,
        "sorties": [],
    }
    try:
        try:
            status = _http(port, "GET", "/api/status", timeout=3)
        except Exception:
            status = {}
        if status.get("_http") != 200:
            start_kernel(sandbox, port)
        status = wait_kernel(port, sandbox)
        report["kernel"] = {
            "version": status.get("kernelVersion"),
            "workspace": status.get("workspace"),
        }
        hub = hub_of(port)
        if not (hub.get("company") or {}).get("sealed"):
            band = pick_band(hub)
            sealed = _http(port, "POST", "/api/seal-company", {"band": band})
            report["seal"] = {"band": band, "ok": sealed.get("ok"), "error": sealed.get("error"), "http": sealed.get("_http")}
            if not sealed.get("ok"):
                report["ok"] = False
                return report
            hub = hub_of(port)
        else:
            report["seal"] = {"skipped": True, "reason": "already sealed"}
        stalls = 0
        for n in range(1, sorties + 1):
            if _spring_open():
                report["sorties"].append({"n": n, "ok": False, "error": "spring already open"})
                break
            hub = hub_of(port)
            press_buttons(port, hub, report)
            hub = hub_of(port)
            before = int(hub.get("missionNumber") or 1)
            history_before = history_len(sandbox)
            try:
                choice = pick_choice(hub, set(visited_maps(sandbox)))
                plan = plan_from(hub, choice)
            except Exception as exc:  # noqa: BLE001
                report["sorties"].append({"n": n, "ok": False, "error": str(exc), "mission": before})
                stalls += 1
                if stalls >= 2:
                    break
                continue
            status_path = sandbox / "outbox" / "play_session.status.json"
            try:
                status_path.unlink(missing_ok=True)
            except OSError:
                pass
            dropped = _http(port, "POST", "/api/deploy?launch=1", plan, timeout=20)
            entry = {
                "n": n,
                "before": before,
                "choiceId": choice.get("id"),
                "mapId": plan.get("mapId"),
                "headingMapId": plan.get("headingMapId"),
                "accepted": dropped.get("accepted"),
                "http": dropped.get("_http"),
                "error": dropped.get("error"),
            }
            if not dropped.get("accepted"):
                entry["ok"] = False
                report["sorties"].append(entry)
                stalls += 1
                if stalls >= 2:
                    break
                continue
            outcome = wait_sortie(port, sandbox, before, history_before, timeout=720)
            entry.update(outcome)
            entry["visited"] = visited_maps(sandbox)
            report["sorties"].append(entry)
            if not outcome.get("ok"):
                stalls += 1
                if stalls >= 2:
                    break
            else:
                stalls = 0
            seen = set(entry.get("visited") or [])
            if seen.issuperset(MAPS):
                report["end"] = "every map visited"
                break
        report["visited"] = visited_maps(sandbox)
        report["ok"] = any(s.get("ok") for s in report["sorties"])
        report["finishedAt"] = _now()
        return report
    finally:
        out = sandbox / "outbox" / "zip_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["seedRestored"] = restore_live_seed()


def main() -> int:
    ap = argparse.ArgumentParser(description="Zip a sandbox Verdance campaign")
    ap.add_argument("--sandbox", default=str(Path(os.environ.get("TEMP") or ".") / "va-zip-sandbox"))
    ap.add_argument("--port", type=int, default=8771)
    ap.add_argument("--sorties", type=int, default=8)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    report = run(Path(args.sandbox), args.port, args.sorties, args.fresh)
    print(json.dumps({
        "ok": report.get("ok"),
        "seal": report.get("seal"),
        "presses": report.get("presses"),
        "sorties": [
            {
                "n": s.get("n"),
                "ok": s.get("ok"),
                "mapId": s.get("mapId"),
                "mission": s.get("mission"),
                "phase": s.get("phase"),
                "error": s.get("error") or s.get("reason"),
            }
            for s in report.get("sorties") or []
        ],
        "visited": report.get("visited"),
        "end": report.get("end"),
        "seedRestored": report.get("seedRestored"),
        "report": str(Path(args.sandbox) / "outbox" / "zip_report.json"),
    }, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
