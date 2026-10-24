"""CampaignKernel — frozen product API (Phase 1+).

Callers (HTTP shell, launcher, tests, future Tauri) should use this class
rather than invoking scattered .ps1 / .py scripts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verdance.common import load_json, save_json, utc_now
from verdance.belief import camp_clock as camp, hub_belief, perspectives as P, world as W
from verdance.belief.match_credit import credit_from_result, presentable_debrief
from verdance.campaign import (
    apply_home_build,
    build_war_map,
    ensure_commerce,
    migrate_state,
    opening_sortie_order,
    process_result,
    purchase_listing,
)
from verdance.company import continuity_audit as audit
from verdance.company.company import (
    company_deploy_aces,
    company_deploy_band,
    consume_mission_call_ins,
    ensure_company,
    hub_company_surface,
    peek_mission_call_ins,
    seal_company as _seal,
    sortie_roster,
)
from verdance.hub.apply_result_to_hub import apply as apply_result_to_hub
from verdance.hub.stamp_deploy_plan import stamp as stamp_plan
from verdance.readings.narrative import choose, project

from verdance_kernel import steam as steam_mod
from verdance_kernel import surface as surface_mod
from verdance_kernel.paths import (
    backups_dir,
    hub_result_path,
    hub_state_path,
    latest_result_path,
    resolve_workspace,
    saves_dir,
    showoff_dir,
    state_path,
)
from verdance_kernel.runtime import run_cmd, run_module, run_ps1

KERNEL_SCHEMA = "verdance-campaign-kernel/1.0"

# Preferred player-path scripts first, then legacy scripts/ names.
_PS1_ALIASES: dict[str, tuple[str, ...]] = {
    "build": ("scripts/player/build_mission.ps1", "scripts/build_next_mission_v1.ps1"),
    "install_mod": ("scripts/player/install_mod.ps1", "scripts/install_mod_archive.ps1"),
}


def _first_error_line(*reports: dict[str, Any]) -> str:
    """The most useful single line from a failed pipeline stage.

    The hub shows one short string. PowerShell puts the part that identifies the
    fault -- script, line, and reason -- at the TOP of stderr, then follows it
    with several lines of CategoryInfo/FullyQualifiedErrorId noise, so the first
    non-empty line is the one worth surfacing.
    """
    for rep in reports:
        if not isinstance(rep, dict) or rep.get("ok"):
            continue
        for key in ("error", "reason", "stderr_tail", "stderr"):
            raw = rep.get(key)
            if not raw:
                continue
            for line in str(raw).splitlines():
                line = line.strip()
                if line:
                    return line[:400]
        for raw in (rep.get("errors") or rep.get("warnings") or []):
            line = str(raw).strip()
            if line:
                return line[:400]
    return "deploy pipeline failed -- see build.stderr_tail"


def _plan_key(plan: dict[str, Any] | None) -> str:
    """What fixes the loaded field: the map, the pad, the targets and the job. Not the company."""
    p = plan or {}
    m = p.get("marks") or {}
    return json.dumps([p.get("mapId"), p.get("contractKind"), m.get("deployZoneId"),
                       sorted(m.get("captureZoneIds") or [])], sort_keys=True)


def _spring_already_open() -> str | None:
    """Name of a running spring.exe, or None.

    play_session refuses to start when one is already up, but it does that
    inside a detached process. The hub would otherwise hear "started" and
    then nothing would open.
    """
    if sys.platform != "win32":
        return None
    try:
        r = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        return None
    for line in (r.stdout or "").splitlines():
        name = line.split(",", 1)[0].strip().strip('"').lower()
        if name in ("spring.exe", "spring-headless.exe"):
            return name
    return None


def dev_mode(ws: Path) -> bool:
    """Truth faces are dev-only. On when verdance_config.json has "devMode": true or VA_DEV=1."""
    if str(os.environ.get("VA_DEV") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    p = Path(ws) / "verdance_config.json"
    if p.is_file():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8-sig")) or {}
            return bool(cfg.get("devMode"))
        except Exception:  # noqa: BLE001
            return False
    return False


DEV_ONLY = {"ok": False, "error": "dev only"}


def _campaign_lock(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


class CampaignKernel:
    """Authoritative campaign ops for one workspace."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.ws = resolve_workspace(workspace)
        self._lock = threading.RLock()
        self._busy = False
        self._deploy_phase = "idle"
        self._pending_roster: dict[str, Any] | None = None
        self._roster_gen = 0
        self._roster_client_gen = 0
        self._roster_token = ""
        self._last_deploy: dict[str, Any] | None = None
        self._last_launch: dict[str, Any] | None = None
        self._last_advance: dict[str, Any] | None = None
        self._last_mod_sync: dict[str, Any] | None = None
        self._error: str | None = None
        self._bridge = None  # set by bar_bridge if attached
        self._hot: dict[str, Any] | None = None   # the hot-drop launch: token, pid, dropped (verdance_kernel.hot_drop)
        self._hot_behind: threading.Event | None = None
        self.started_at = utc_now()

    def _resolve_ps1(self, key: str) -> Path | None:
        for rel in _PS1_ALIASES.get(key, ()):
            p = self.ws / rel.replace("/", "\\")
            if p.is_file():
                return p
        return None

    # ── surface ──────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        from verdance_kernel.phases import phase_status

        bridge_info = None
        if self._bridge is not None:
            bridge_info = getattr(self._bridge, "status", lambda: None)()
        return {
            "schemaVersion": KERNEL_SCHEMA,
            "kernelVersion": __import__("verdance_kernel").__version__,
            "startedAt": self.started_at,
            "workspace": str(self.ws),
            "showoff": str(showoff_dir(self.ws)),
            "busy": self._busy,
            "deployPhase": self._deploy_phase,
            "hotDrop": self.hot_drop_status(),
            "error": self._error,
            "lastDeploy": self._last_deploy,
            "lastLaunch": self._last_launch,
            "lastAdvance": self._last_advance,
            "deployStub": False,
            "phases": phase_status(),
            "steam": steam_mod.status(self.ws),
            "bridge": bridge_info,
            "capabilities": {
                "stamp": True,
                "materialize": True,
                "build": True,
                "launch": True,
                "advance": True,
                "hubState": True,
                "result": True,
                "purchase": True,
                "autoApply": True,
                "campaignSurface": True,
                "field": True,
                "continueField": True,
                "steamStub": True,
                "modSync": True,
            },
            "lastModSync": self._last_mod_sync,
        }

    def get_hub_surface(self) -> dict[str, Any]:
        p = hub_state_path(self.ws)
        if not p.is_file():
            return {"ok": False, "error": "hub_state.json missing — call rebuild_hub()"}
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            return {"ok": True, "hub": data}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def get_result(self) -> dict[str, Any]:
        p = hub_result_path(self.ws)
        if not p.is_file():
            return {"present": False}
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            return {"present": True, "result": data}
        except Exception as e:  # noqa: BLE001
            return {"present": True, "error": str(e)}

    def narrative_surface(self) -> dict[str, Any]:
        p = state_path(self.ws)
        if not p.is_file():
            return {"ok": False, "error": "Campaign save is missing."}
        with self._lock:
            state = json.loads(p.read_text(encoding="utf-8-sig"))
            hub = self.get_hub_surface().get("hub") or {}
            return {"ok": True, "narrative": project(state, (hub.get("node") or {}).get("choices") or [], self.ws)}

    def narrative_choice(self, body: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "A campaign operation is in progress. Try again after it completes."}
            p = state_path(self.ws)
            if not p.is_file():
                return {"ok": False, "error": "Campaign save is missing."}
            state = json.loads(p.read_text(encoding="utf-8-sig"))
            receipt = choose(state, body.get("choiceId"), body.get("expectedRevision"), body.get("requestId"), self.ws)
            if receipt.get("ok"):
                save_json(p, state)
                receipt["narrative"] = self.narrative_surface()["narrative"]
            return receipt

    # ── camp clock (interstitial time, weak measurements, surprise pauses) ──────
    def camp_surface(self) -> dict[str, Any]:
        """What the company knows and where its people are. Reads state; writes only
        outbox/camp.latest.json and outbox/intel.latest.json (DERIVE faces)."""
        p = state_path(self.ws)
        if not p.is_file():
            return {"ok": False, "error": "Campaign save is missing."}
        with self._lock:
            state = json.loads(p.read_text(encoding="utf-8-sig"))
            try:
                return {"ok": True, "camp": camp.surface(state, self.ws)}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": str(e)}

    def camp_act(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run the clock: rest / wait / scout / post / recall. Mutates the campaign
        save (clock, camp, intel, zone truth via the engine's own offscreen tick) and
        the persisted belief world; time stops at the first pause."""
        action = str((body or {}).get("action") or "")
        if action not in ("rest", "wait", "scout", "post", "recall"):
            return {"ok": False, "error": "Unknown camp action."}
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "A campaign operation is in progress. Try again after it completes."}
            p = state_path(self.ws)
            if not p.is_file():
                return {"ok": False, "error": "Campaign save is missing."}
            state = json.loads(p.read_text(encoding="utf-8-sig"))
            try:
                out = camp.act(state, self.ws, action,
                               hours=float((body or {}).get("hours") or 8.0),
                               zoneId=(body or {}).get("zoneId"), heroId=(body or {}).get("heroId"))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": str(e)}
            if out.get("ok"):
                save_json(p, state)
            return out

    # ── pass three faces: belief frames, truth (dev), divergence, chronicle ─────
    def _outbox_face(self, name: str, hidden: bool = False) -> dict[str, Any]:
        p = self.ws / "outbox" / name
        if not p.is_file():
            return {"ok": False, "error": f"{name} not written yet (no fold has run)."}
        try:
            face = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        out = {"ok": True, "face": face}
        if hidden:
            out["hidden"] = True  # dev-only: never show the player truth in the hub
        return out

    def dev_mode(self) -> bool:
        return dev_mode(self.ws)

    def intel_surface(self, perspective: str = "company") -> dict[str, Any]:
        """A belief frame (verdance-intel/1). company = the player's own. armada/nullmercs/cortex are
        other minds: THE LAW says the player side never sees them, so they are dev-only (403)."""
        if perspective not in ("", "company"):
            if not self.dev_mode():
                return dict(DEV_ONLY)
            return self._outbox_face(f"intel.{perspective}.latest.json", hidden=True)
        return self._outbox_face("intel.latest.json")

    def truth_surface(self) -> dict[str, Any]:
        if not self.dev_mode():
            return dict(DEV_ONLY)
        return self._outbox_face("truth.latest.json", hidden=True)

    def divergence_surface(self) -> dict[str, Any]:
        """Belief vs truth (`actually` fields) — dev-only. Players get /api/exposure."""
        if not self.dev_mode():
            return dict(DEV_ONLY)
        out = self._outbox_face("divergence.latest.json", hidden=True)
        # faction minds fold in a detached worker; say whether the face is still catching up
        try:
            out["pending"] = P.pending(self.ws)
        except Exception:  # noqa: BLE001
            pass
        return out

    def exposure_surface(self) -> dict[str, Any]:
        """Player-safe projection of divergence: our side of the mirror only. Per faction, which of
        the zones WE BELIEVE are ours they have eyes on (known / suspected / blind). No `actually`,
        no other faction's picture of the world, nothing about ground we do not know we hold."""
        exp = hub_belief.exposure_surface(self.ws)
        if not exp.get("present"):
            return {"ok": True, "present": False, "factions": {}}
        ours: set[str] | None = None
        p = state_path(self.ws)
        if p.is_file():
            try:
                state = json.loads(p.read_text(encoding="utf-8-sig"))
                ours = set(hub_belief.believed_ours(self.ws, state))
            except Exception:  # noqa: BLE001
                ours = None
        factions: dict[str, Any] = {}
        for fac, a in (exp.get("factions") or {}).items():
            def keep(xs: Any) -> list[str]:
                xs = [str(x) for x in (xs or [])]
                return [x for x in xs if ours is None or x in ours]
            known, susp, blind = keep(a.get("known")), keep(a.get("suspected")), keep(a.get("blind"))
            factions[fac] = {"known": known, "suspected": susp, "blind": blind,
                             "ofOurs": (len(ours) if ours is not None else a.get("ofOurs"))}
        out: dict[str, Any] = {"ok": True, "present": True, "asOfMinute": exp.get("asOfMinute"), "factions": factions}
        try:
            out["pending"] = P.pending(self.ws)
        except Exception:  # noqa: BLE001
            pass
        return out

    def chronicle_surface(self) -> dict[str, Any]:
        return self._outbox_face("chronicle.latest.json")

    def continuity_audit(self, marks: list[str] | None = None) -> dict[str, Any]:
        """Phase 0 continuity membrane inspector (witness vs belief vs reinduce)."""
        try:
            report = audit.run_audit(self.ws, marked=marks or [])
            audit.write_outbox(self.ws, report)
            report["outbox"] = str(self.ws / "outbox" / "continuity_audit.latest.json")
            return report
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ── ready to drop (pass 8B): one honest checklist for the System drawer ───────
    def health(self) -> dict[str, Any]:
        """Each check is a bool or a path|None; the hub paints a dot and a one-line fix per red."""
        import importlib.util
        import platform

        from verdance_kernel import sortie as _sortie

        out: dict[str, Any] = {
            "ok": True,
            "at": utc_now(),
            "python": platform.python_version(),
            "pythonOk": sys.version_info >= (3, 10),
            "numpy": importlib.util.find_spec("numpy") is not None,
            "scipy": importlib.util.find_spec("scipy") is not None,
            "umwelt": False,
            "barDataRoot": None,
            "engine": None,
            "modInstalled": False,
            "mapCached": None,
            "nextMap": None,
            "provision": None,
            "stateMission": None,
            "devMode": self.dev_mode(),
        }
        # Belief engine. _umwelt() may raise SystemExit (old) or return None (new); both mean "not found".
        try:
            out["umwelt"] = W._umwelt() is not None
        except BaseException:  # noqa: BLE001  (SystemExit included)
            out["umwelt"] = False
        # Where BAR lives. bar_config raises when it cannot find a data directory.
        cfg: dict[str, Any] | None = None
        try:
            cfg = _sortie.bar_config(self.ws)
            out["barDataRoot"] = cfg.get("barDataRoot")
        except Exception:  # noqa: BLE001
            cfg = None
        if cfg:
            try:
                out["engine"] = str(_sortie.engine_exe(cfg))
            except Exception:  # noqa: BLE001
                out["engine"] = None
            try:
                out["modInstalled"] = (Path(cfg["barDataRoot"]) / "games" / "VerdanceAshes.sdd").is_dir()
            except Exception:  # noqa: BLE001
                out["modInstalled"] = False
        # Next mission + its map, from the campaign save and the hub face (no network).
        try:
            sp = state_path(self.ws)
            if sp.is_file():
                st = json.loads(sp.read_text(encoding="utf-8-sig"))
                out["stateMission"] = int(st.get("missionNumber") or 1)
        except Exception:  # noqa: BLE001
            pass
        next_map = None
        try:
            hub = (self.get_hub_surface().get("hub") or {})
            node = hub.get("node") or {}
            next_map = node.get("sortieMapId") or node.get("regionHint") or hub.get("sessionHomeMap")
        except Exception:  # noqa: BLE001
            next_map = None
        out["nextMap"] = next_map
        if next_map and cfg:
            try:
                pool = json.loads((self.ws / "data" / "map_pool" / "seven_maps.json").read_text(encoding="utf-8-sig"))
                arch = next((str(m.get("archivePattern") or "") for m in pool.get("maps") or [] if str(m.get("id")) == str(next_map)), "")
                if arch:
                    out["mapCached"] = (Path(cfg["barDataRoot"]) / "maps" / arch).is_file()
            except Exception:  # noqa: BLE001
                out["mapCached"] = None
        prov_fn = getattr(_sortie, "provision_status", None)
        if callable(prov_fn):
            try:
                out["provision"] = prov_fn(self.ws)
            except Exception:  # noqa: BLE001
                out["provision"] = None
        return out

    # ── feedback bundle (pass 8B): what a tester sends back, nothing the player may not see ──
    def feedback_bundle(self, body: dict[str, Any] | None) -> dict[str, Any]:
        import zipfile

        body = body or {}
        notes = str(body.get("notes") or "").strip()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = self.ws / "export"
        out_dir.mkdir(parents=True, exist_ok=True)
        zpath = out_dir / f"feedback_{stamp}.zip"
        included: list[str] = []
        skipped: list[str] = []

        def _banned(name: str) -> bool:
            n = name.lower()
            # THE LAW: truth and other minds never leave the kernel, not even in a bug report.
            if n.startswith("truth") or n.startswith("divergence"):
                return True
            # intel.<faction>.latest.json is another mind; the company's own intel.latest.json is fine
            return n.startswith("intel.") and n != "intel.latest.json"

        def _redact_config(raw: str) -> str:
            try:
                cfg = json.loads(raw)
            except Exception:  # noqa: BLE001
                return "{}"
            def red(v: Any) -> Any:
                if isinstance(v, str):
                    # any absolute path (C:\..., /home/..., \\server\...) names the tester's machine
                    looks_path = (len(v) > 2 and v[1] == ":" and v[2] in "\\/") or v.startswith("/") or v.startswith("\\\\")
                    return "<redacted path>" if looks_path else v
                if isinstance(v, dict):
                    return {k: red(x) for k, x in v.items()}
                if isinstance(v, list):
                    return [red(x) for x in v]
                return v
            return json.dumps(red(cfg), indent=2)

        try:
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("notes.txt", (notes or "(no notes)") + "\n")
                for rel in ("state/campaign_state.json", "app/showoff/hub_state.json", "VERSION"):
                    p = self.ws / rel
                    if p.is_file():
                        z.write(p, rel)
                        included.append(rel)
                cfgp = self.ws / "verdance_config.json"
                if cfgp.is_file():
                    z.writestr("verdance_config.json", _redact_config(cfgp.read_text(encoding="utf-8-sig")))
                    included.append("verdance_config.json (paths redacted)")
                ob = self.ws / "outbox"
                if ob.is_dir():
                    for p in sorted(ob.glob("*.latest.json")):
                        if _banned(p.name):
                            skipped.append(p.name)
                            continue
                        z.write(p, f"outbox/{p.name}")
                        included.append(f"outbox/{p.name}")
                # newest BAR infolog (the engine keeps infolog.txt at the data root; older ones roll to infolog_*.txt)
                try:
                    from verdance_kernel import sortie as _sortie
                    cfg = _sortie.bar_config(self.ws)
                    root = Path(cfg["barDataRoot"])
                    cands = [Path(cfg.get("infolog") or (root / "infolog.txt"))] + sorted(root.glob("infolog*.txt"))
                    cands = [c for c in cands if c.is_file()]
                    if cands:
                        newest = max(cands, key=lambda c: c.stat().st_mtime)
                        z.write(newest, f"bar/{newest.name}")
                        included.append(f"bar/{newest.name}")
                except Exception as e:  # noqa: BLE001
                    skipped.append(f"infolog ({type(e).__name__})")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "at": utc_now()}
        return {"ok": True, "at": utc_now(), "path": str(zpath), "included": included, "skipped": skipped}

    def session_status(self) -> dict[str, Any]:
        """The sortie watch is the session: launching → in-game → bringing-home → home | closed-without-result."""
        w = getattr(self._bridge, "status", lambda: None)() if self._bridge is not None else None
        if not w or w.get("phase") in (None, "idle"):
            return {"present": False}
        # same keys the hub already reads: phase / springPid / updatedAt
        last = w.get("last") or {}
        return {"present": True, "status": {"phase": w.get("phase"), "springPid": w.get("pid"), "pid": w.get("pid"),
                                             "updatedAt": last.get("at") or w.get("startedAt"), "startedAt": w.get("startedAt"),
                                             "applied": w.get("applied"), "last": last}}

    def live(self) -> dict[str, Any]:
        """The match as the company sees it right now: the minimap widget's live report
        (LuaUI/Config/verdance/live.json). Only for the mission the hub dropped, and only while
        fresh; it never touches belief, which moves at homecoming."""
        from verdance_kernel.sortie import find_bar_data_root
        root = find_bar_data_root(self.ws)
        path = Path(root) / "LuaUI" / "Config" / "verdance" / "live.json" if root else None
        if not path or not path.is_file():
            return {"live": False}
        age = datetime.now().timestamp() - path.stat().st_mtime
        if age > 20:
            return {"live": False, "ageSec": round(age)}
        data = None
        for _ in range(3):  # BAR writes in place; a torn read just tries again
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except (ValueError, OSError):
                threading.Event().wait(0.05)
        if not isinstance(data, dict) or data.get("schema") != "verdance-live/1":
            return {"live": False}
        intent = load_json(self.ws / "outbox" / "next_mission_intent.json", {}) or {}
        if intent.get("missionId") and data.get("missionId") and str(data["missionId"]) != str(intent["missionId"]):
            return {"live": False, "reason": "another mission"}
        return dict(data, live=True, ageSec=round(age, 1))

    # ── ops ──────────────────────────────────────────────────

    def rebuild_hub(self, *, skip_apply: bool = False, keep_result: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {}
        # war_map is required input for hub paint — regenerate from live state.
        war_path = self.ws / "outbox" / "war_map.json"
        state_file = self.ws / "state" / "campaign_state.json"
        if state_file.is_file():
            try:

                save_json(war_path, build_war_map(load_json(state_file)))
                out["war_map"] = {"ok": True, "path": str(war_path)}
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"war_map regenerate failed: {e}") from e
        elif not war_path.is_file():
            raise RuntimeError("missing campaign_state.json and outbox/war_map.json")
        for name in ("build_hub_state", "build_zone_boards"):
            out[name] = run_module(self.ws, f"verdance.hub.{name}", [], workspace_flag=False, timeout=60)
        hub_build = out.get("build_hub_state") or {}
        if hub_build and not hub_build.get("ok"):
            detail = (
                hub_build.get("stderr_tail")
                or hub_build.get("stdout_tail")
                or hub_build.get("reason")
                or "build_hub_state failed"
            )
            raise RuntimeError(f"hub rebuild failed: {str(detail).strip()[:400]}")
        # Campaign reset / wipe must NOT re-ingest results. Calling
        # apply_result_to_hub(skip_advance=True) still painted lastResult and
        # could leave the shell on "sortie 2" after a wipe (Sortie 2 ghost).
        apply_info: dict[str, Any]
        if skip_apply:
            apply_info = {"skipped": True, "reason": "skip_apply_no_result_ingest"}
            # Drop stale debrief paint so the board shows the live missionNumber. Not after a
            # homecoming (keep_result): that file is how the open hub learns the sortie is home.
            stale = self.ws / "outbox" / "hub_result.latest.json"
            if stale.is_file() and not keep_result:
                try:
                    stale.unlink()
                    apply_info["clearedHubResult"] = True
                except OSError:
                    apply_info["clearedHubResult"] = False
        else:
            apply_info = apply_result_to_hub(self.ws, skip_advance=True)
        hub = self.get_hub_surface()
        if not hub.get("ok"):
            raise RuntimeError(
                f"hub surface unreadable after rebuild: {hub.get('error') or 'missing hub_state.json'}"
            )
        # Hard assert: surface mission must match campaign_state (never a ghost).
        state_path = self.ws / "state" / "campaign_state.json"
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
            want = int(state.get("missionNumber") or 1)
            got = int((hub.get("hub") or {}).get("missionNumber") or 0)
            if got != want:
                raise RuntimeError(
                    f"hub mission ghost after rebuild: surface={got} state={want}. "
                    "Refusing to paint over campaign_state with stale hub_state."
                )
        surface = surface_mod.write_surface(
            self.ws, hub.get("hub") if hub.get("ok") else None
        )
        steam_mod.cloud_mirror(self.ws)
        return {
            "ok": True,
            "rebuild": out,
            "apply": apply_info,
            "surface": {"path": surface.get("path")},
            "missionNumber": (hub.get("hub") or {}).get("missionNumber"),
            "at": utc_now(),
        }

    @_campaign_lock
    def reset_campaign(self, *, confirm: str = "") -> dict[str, Any]:
        """Full wipe via scripts/player/reset_campaign.ps1. Requires confirm=YES."""
        if str(confirm).strip().upper() != "YES":
            return {
                "ok": False,
                "error": "type YES to confirm full campaign reset",
                "at": utc_now(),
            }
        script = self.ws / "scripts" / "player" / "reset_campaign.ps1"
        if not script.is_file():
            return {"ok": False, "error": "reset_campaign.ps1 missing", "at": utc_now()}
        report = run_ps1(script, self.ws, timeout=180)
        hub = self.get_hub_surface()
        return {
            "ok": bool(report.get("ok", report.get("exitCode", 1) == 0)),
            "at": utc_now(),
            "reset": report,
            "hub": hub.get("hub") if hub.get("ok") else None,
            "missionNumber": (hub.get("hub") or {}).get("missionNumber"),
        }

    @staticmethod
    def _sanitize_slot(name: str) -> str | None:
        raw = str(name or "").strip()
        if not raw:
            return None
        # Keep portal prompts simple: letters, digits, dash, underscore, space → underscore
        cleaned = []
        for ch in raw:
            if ch.isalnum() or ch in "-_":
                cleaned.append(ch)
            elif ch.isspace():
                cleaned.append("_")
        slot = "".join(cleaned).strip("_-")[:48]
        return slot or None

    def list_saves(self) -> dict[str, Any]:
        """Named campaign slots under state/saves/."""
        root = saves_dir(self.ws)
        root.mkdir(parents=True, exist_ok=True)
        slots: list[dict[str, Any]] = []
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            state_file = child / "campaign_state.json"
            if not state_file.is_file():
                continue
            meta: dict[str, Any] = {}
            meta_path = child / "meta.json"
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
                except Exception:  # noqa: BLE001
                    meta = {}
            mission = meta.get("missionNumber")
            if mission is None:
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8-sig"))
                    mission = data.get("missionNumber")
                except Exception:  # noqa: BLE001
                    mission = None
            slots.append(
                {
                    "id": child.name,
                    "label": meta.get("label") or child.name,
                    "savedAt": meta.get("savedAt"),
                    "missionNumber": mission,
                    "note": meta.get("note"),
                }
            )
        return {"ok": True, "at": utc_now(), "saves": slots, "dir": str(root)}

    @_campaign_lock
    def seal_company(self, *, band: list[str] | None = None) -> dict[str, Any]:
        """Hub preamble: lock core + exactly seatCap band packs for this run."""

        sp = state_path(self.ws)
        if not sp.is_file():
            return {"ok": False, "error": "campaign_state.json missing", "at": utc_now()}
        try:
            state = migrate_state(load_json(sp))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"load state failed: {e}", "at": utc_now()}
        ok, err, company = _seal(state, list(band or []), workspace=self.ws)
        if not ok:
            return {"ok": False, "error": err, "company": company, "at": utc_now()}
        try:
            save_json(sp, state)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"save state failed: {e}", "at": utc_now()}
        hub_report = self.rebuild_hub()
        surface = hub_company_surface(state, self.ws)

        # Post-seal: for mission 1, bake the *canonical opening* with sealed
        # crew + fieldRecruits. Do NOT call generic materialize_intent here —
        # that can pick Mode A / extract ghosts and desync the hub theater.
        seed_report: dict[str, Any] = {"skipped": True}
        try:
            _save_json = save_json

            mission_n = int(state.get("missionNumber") or 1)
            order = opening_sortie_order(state, self.ws) if mission_n == 1 else None
            if isinstance(order, dict) and order.get("mapId"):
                outbox = self.ws / "outbox"
                outbox.mkdir(parents=True, exist_ok=True)
                # Stamp sealed muster onto the opening packet.
                order = dict(order)
                order["deployAces"] = company_deploy_aces(state)
                order["crewBand"] = company_deploy_band(state)
                order["seedStaleUntilCompanySeal"] = False
                _save_json(outbox / "next_sortie_order.json", order)
                rim = str(order.get("deploymentZoneId") or "")
                target = str(order.get("targetZoneId") or "")
                intent = {
                    "schemaVersion": "verdance-mission-intent/1.0",
                    "campaignId": order.get("campaignId") or "verdance_ashes",
                    "missionId": "va_001",
                    "missionNumber": 1,
                    "act": 1,
                    "mapId": order.get("mapId"),
                    "deploymentZoneId": rim,
                    "extractionZoneId": str(order.get("extractionZoneId") or rim),
                    "targetZoneId": target,
                    "objective": order.get("objectiveArchetype") or "eco_raid",
                    "objectiveTarget": {
                        "id": target,
                        "kind": order.get("objectiveArchetype") or "eco_raid",
                        "label": f"{order.get('objectiveArchetype') or 'eco_raid'}: {target}",
                        "targetZoneId": target,
                        "mapId": order.get("mapId"),
                        "enemyFaction": order.get("against") or "armada",
                        "patron": order.get("patron") or "nullmercs",
                    },
                    "captureZoneIds": list(order.get("captureZoneIds") or [target]),
                    "secondaryCaptureZoneIds": list(
                        order.get("secondaryCaptureZoneIds") or []
                    ),
                    "fromZoneIds": list(order.get("fromZoneIds") or [rim]),
                    "deployAces": list(order.get("deployAces") or []),
                    "crewBand": list(order.get("crewBand") or []),
                    "openingMission": True,
                    "openingDoctrine": order.get("openingDoctrine"),
                    "patron": order.get("patron") or "nullmercs",
                    "against": order.get("against") or "armada",
                    "sessionMode": order.get("sessionMode") or "reload_travel",
                    "occupationModel": order.get("occupationModel") or "living_shell",
                    "seededAt": utc_now(),
                    "seedReason": "company_seal_opening_bake",
                }
                _save_json(outbox / "next_mission_intent.json", intent)
                # Align hub deploy plan marks with the opening so Drop doesn't
                # revive a stale NW-bastion / Mode A plan.
                plan = {
                    "schemaVersion": "verdance-deploy-plan/1.0",
                    "mapId": order.get("mapId"),
                    "contractKind": order.get("objectiveArchetype") or "eco_raid",
                    "deployAces": list(order.get("deployAces") or []),
                    "crewBand": list(order.get("crewBand") or []),
                    "marks": {
                        "deployZoneId": rim,
                        "extractZoneId": str(order.get("extractionZoneId") or rim),
                        "captureZoneIds": list(order.get("captureZoneIds") or [target]),
                    },
                    "patron": order.get("patron") or "nullmercs",
                    "against": order.get("against") or "armada",
                    "occupationModel": order.get("occupationModel") or "living_shell",
                    "sessionMode": order.get("sessionMode") or "reload_travel",
                }
                _save_json(outbox / "hub_deploy_plan.latest.json", plan)
                build_report = self.build_mission()
                seed_report = {
                    "ok": bool(build_report.get("ok")),
                    "source": "opening_sortie_order",
                    "deploymentZoneId": rim,
                    "targetZoneId": target,
                    "build": build_report,
                }
                (outbox / "seed_status.json").write_text(
                    json.dumps(
                        {
                            "schemaVersion": "verdance-seed-status/1.0",
                            "stale": not bool(build_report.get("ok")),
                            "reason": "company_sealed_opening",
                            "at": utc_now(),
                            "deployAces": company_deploy_aces(state),
                            "crewBand": company_deploy_band(state),
                            "deploymentZoneId": rim,
                            "targetZoneId": target,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            else:
                # Mid-run seal (rare) — Drop will bake from the player's marks.
                seed_report = {
                    "ok": True,
                    "skipped": True,
                    "reason": "non_opening_seal_await_drop",
                }
                (self.ws / "outbox" / "seed_status.json").write_text(
                    json.dumps(
                        {
                            "schemaVersion": "verdance-seed-status/1.0",
                            "stale": True,
                            "reason": "await_drop_bake",
                            "at": utc_now(),
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
        except Exception as e:  # noqa: BLE001
            seed_report = {"ok": False, "error": str(e)}

        return {
            "ok": True,
            "at": utc_now(),
            "company": company,
            "surface": surface,
            "deployAces": company_deploy_aces(state),
            "deployBand": company_deploy_band(state),
            "hub": hub_report.get("hub") if hub_report.get("ok") else None,
            "rebuild": hub_report,
            "seed": seed_report,
        }

    @_campaign_lock
    def save_campaign(self, *, slot: str = "", label: str = "", note: str = "") -> dict[str, Any]:
        """Snapshot campaign_state.json into state/saves/<slot>/."""
        import shutil

        name = self._sanitize_slot(slot) or self._sanitize_slot(label)
        if not name:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            name = f"slot_{stamp}"
        src = state_path(self.ws)
        if not src.is_file():
            return {"ok": False, "error": "campaign_state.json missing", "at": utc_now()}
        dest_dir = saves_dir(self.ws) / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "campaign_state.json"
        shutil.copy2(src, dest)
        mission = None
        try:
            data = json.loads(src.read_text(encoding="utf-8-sig"))
            mission = data.get("missionNumber")
        except Exception:  # noqa: BLE001
            data = {}
        meta = {
            "schemaVersion": "verdance-save-slot/1.0",
            "id": name,
            "label": str(label or name).strip() or name,
            "note": str(note or "").strip() or None,
            "savedAt": utc_now(),
            "missionNumber": mission,
        }
        (dest_dir / "meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
        # Keep Steam cloud mirror in sync with "I saved"
        try:
            steam_mod.cloud_mirror(self.ws)
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "at": utc_now(),
            "slot": name,
            "path": str(dest),
            "meta": meta,
            "saves": self.list_saves().get("saves"),
        }

    @_campaign_lock
    def load_campaign(self, *, slot: str = "", confirm: str = "") -> dict[str, Any]:
        """Restore a named save over live campaign_state, then rebuild hub."""
        import shutil

        if str(confirm).strip().upper() != "YES":
            return {
                "ok": False,
                "error": "type YES to confirm load (overwrites live campaign_state)",
                "at": utc_now(),
            }
        name = self._sanitize_slot(slot)
        if not name:
            return {"ok": False, "error": "slot name required", "at": utc_now()}
        src = saves_dir(self.ws) / name / "campaign_state.json"
        if not src.is_file():
            return {"ok": False, "error": f"save slot not found: {name}", "at": utc_now()}
        live = state_path(self.ws)
        backups_dir(self.ws).mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = backups_dir(self.ws) / f"campaign_state.pre_load_{stamp}.json"
        if live.is_file():
            shutil.copy2(live, backup)
        live.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, live)
        hub_report = self.rebuild_hub()
        try:
            steam_mod.cloud_mirror(self.ws)
        except Exception:  # noqa: BLE001
            pass
        hub = self.get_hub_surface()
        return {
            "ok": bool(hub_report.get("ok", True)),
            "at": utc_now(),
            "slot": name,
            "backup": str(backup) if live.is_file() else None,
            "hubRebuild": hub_report,
            "hub": hub.get("hub") if hub.get("ok") else None,
            "missionNumber": (hub.get("hub") or {}).get("missionNumber"),
        }

    def materialize_intent(self) -> dict[str, Any]:
        return run_module(self.ws, "verdance.campaign.engine", ["intent"], timeout=120)

    def sync_mod(self, *, copy: bool = True) -> dict[str, Any]:
        """Copy (or junction) workspace mutator into BAR data/games before play."""
        script = self._resolve_ps1("install_mod")
        if script is None:
            report = {"ok": False, "reason": "install_mod script missing", "at": utc_now()}
            self._last_mod_sync = report
            return report
        extra: list[str] = []
        # One spine (pass five): every Drop copies the WORKSPACE mod into BAR's data\games. The
        # workspace is the truth; the My Games install is only what SHIP produces for other people.
        # (install_mod.ps1 without -Copy would junction data\games to My Games instead.)
        if copy:
            extra.append("-Copy")
        report = run_ps1(script, self.ws, extra_args=extra or None, timeout=120)
        report = dict(report)
        report["at"] = utc_now()
        report["script"] = str(script)
        self._last_mod_sync = report
        return report

    def _seed_hint_from_outbox(self) -> dict[str, Any]:
        """Read the sealed sortie/intent zones after materialize (truth for Drop)."""
        out: dict[str, Any] = {}
        for rel in (
            "outbox/next_mission_intent.json",
            "outbox/next_sortie_order.json",
            "outbox/next_sortie_choice.json",
        ):
            path = self.ws / rel
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for key in (
                "targetZoneId",
                "deploymentZoneId",
                "extractionZoneId",
                "secondaryCaptureZoneIds",
                "openingMission",
                "source",
                "mapId",
            ):
                if key in data and data[key] is not None and key not in out:
                    out[key] = data[key]
            if out.get("targetZoneId") and out.get("deploymentZoneId"):
                break
        return out

    def build_mission(self) -> dict[str, Any]:
        script = self._resolve_ps1("build")
        if script is None:
            return {"ok": False, "reason": "build mission script missing"}
        return run_ps1(script, self.ws, timeout=240)

    def launch_bar(self, *, max_missions: int = 1, auto_relaunch: bool = False) -> dict[str, Any]:
        """Start spring.exe on the startscript the build wrote, and watch the infolog for the result.
        The kernel is the only launcher and the only ingest (pass five): no play_session host."""
        del max_missions, auto_relaunch
        from verdance_kernel import sortie as _sortie

        if _sortie.spring_running():
            return {"ok": False, "skipped": True,
                    "reason": "Beyond All Reason is already open. Finish or close that match, then drop again."}
        report = _sortie.launch(self.ws)
        if report.get("ok"):
            self._last_launch = report
            if self._bridge is not None:
                try:
                    self._bridge.watch_after_launch(report)
                except Exception as e:  # noqa: BLE001
                    report["watch"] = {"ok": False, "error": str(e)}
        return report

    # ── hot drop: load while the player chooses, drop into the running game ──

    def hot_drop_status(self) -> dict[str, Any]:
        from verdance_kernel import hot_drop as _hot
        phase = None
        if self._bridge is not None:
            phase = (getattr(self._bridge, "status", lambda: {})() or {}).get("phase")
        return _hot.status_of(self._hot, phase)

    def _arm_hot(self, token: str, launch_report: dict[str, Any], plan: dict[str, Any]) -> None:
        from verdance_kernel import hot_drop as _hot
        self._clear_hot()
        self._hot = {"token": token, "pid": launch_report.get("pid"), "mapId": plan.get("mapId"),
                     "plan": _plan_key(plan), "at": utc_now(), "dropped": False}
        if launch_report.get("pid"):
            self._hot_behind = threading.Event()
            _hot.keep_behind(int(launch_report["pid"]), self._hot_behind)

    def _clear_hot(self) -> None:
        if self._hot_behind is not None:
            self._hot_behind.set()
        self._hot_behind = None
        self._hot = None

    def preload(self, plan: dict[str, Any]) -> dict[str, Any]:
        """The sortie is chosen: build and launch now, every candidate pack compiled in, nobody on
        the field. The player picks who goes while the level loads; drop() sends them in."""
        from verdance_kernel.sortie import pid_alive
        hot = self._hot
        if hot and not hot.get("dropped"):
            if pid_alive(hot.get("pid")) and hot.get("mapId") == (plan or {}).get("mapId") \
                    and hot.get("plan") == _plan_key(plan):
                return {"ok": True, "accepted": True, "already": True, "phase": self.hot_drop_status().get("phase")}
            self.cancel_preload()
            for _ in range(40):                  # let the old field close before the new one starts
                if not pid_alive(hot.get("pid")):
                    break
                time.sleep(0.25)
            self._clear_hot()
        plan = dict(plan or {}, hotDrop=True)
        return self.commit_deploy(plan, launch=True)

    def cancel_preload(self) -> dict[str, Any]:
        """The player backed out before dropping: close the loaded field. Nothing went."""
        from verdance_kernel import hot_drop as _hot
        hot = self._hot
        if not hot or hot.get("dropped"):
            return {"ok": True, "cancelled": False}
        stopped = _hot.stop_engine(int(hot["pid"])) if hot.get("pid") else False
        _hot.disarm(self.ws)
        return {"ok": True, "cancelled": True, "stopped": stopped}

    def drop(self, body: dict[str, Any]) -> dict[str, Any]:
        """Send the chosen packs (and reserve) into the loaded field."""
        from verdance_kernel import hot_drop as _hot
        from verdance_kernel.sortie import find_bar_data_root, pid_alive
        from verdance.company import reserve as _reserve
        hot = self._hot
        if not hot:
            return {"ok": False, "error": "No field is loaded. Choose a sortie first."}
        if hot.get("dropped"):
            return {"ok": True, "already": True}
        if not pid_alive(hot.get("pid")):
            self._clear_hot()
            return {"ok": False, "error": "Beyond All Reason closed before the drop. Choose the sortie again."}
        if self.hot_drop_status().get("phase") != "ready":
            return {"ok": False, "error": "The field is still loading. Drop wakes when it is ready."}
        root = find_bar_data_root(self.ws)
        if not root:
            return {"ok": False, "error": "BAR's data folder was not found."}
        with self._lock:
            sp = state_path(self.ws)
            st = migrate_state(load_json(sp))
            ensure_company(st, self.ws)
            requested = (body or {}).get("crewBand")
            band, aces = sortie_roster(st, [str(x) for x in requested] if isinstance(requested, list) else None)
            roster = st.setdefault("roster", {})
            held = _reserve.ensure_reserve(roster)
            cap = _reserve.lift_cap(st)
            asked = (body or {}).get("reserveBring")
            roster["cadre"] = (_reserve.clamp_bring(asked, held, cap, self.ws) if isinstance(asked, dict)
                               else _reserve.default_bring(held, cap, self.ws))
            save_json(sp, st)
            _hot.record_roster(self.ws, band, aces)
            path = _hot.write_drop(root, _hot.drop_line(hot["token"], band, roster["cadre"]))
            hot["dropped"] = True
            hot["droppedAt"] = utc_now()
            if self._hot_behind is not None:
                self._hot_behind.set()
        forward = _hot.bring_forward(int(hot["pid"])) if hot.get("pid") else False
        return {"ok": True, "at": utc_now(), "crewBand": band, "deployAces": aces,
                "reserveBring": dict(roster["cadre"]), "dropFile": str(path), "broughtForward": forward}

    def _deploy_async(self, plan: dict[str, Any]) -> None:
        try:
            result = self._deploy_body(plan, launch=True)
            with self._lock:
                if result.get("ok"):
                    if self._deploy_phase not in ("launching", "sealing"):
                        self._deploy_phase = "launching"
                else:
                    self._deploy_phase = "failed"
                    self._error = result.get("error") or self._error
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._deploy_phase = "failed"
                self._error = f"{type(e).__name__}: {e}"
                self._last_deploy = {
                    "ok": False,
                    "accepted": False,
                    "phase": "failed",
                    "error": self._error,
                    "at": utc_now(),
                }
        finally:
            with self._lock:
                self._busy = False

    def commit_deploy(self, plan: dict[str, Any], *, launch: bool = True) -> dict[str, Any]:
        """Launch returns as soon as the build is accepted. The posted roster is locked."""
        plan = dict(plan or {})
        # Hub-only. Must not ride into the stamped intent.
        token = str(plan.pop("rosterToken", "") or "")
        try:
            done = (load_json(self.ws / "state" / "campaign_state.json") or {}).get("campaignComplete")
        except Exception:  # noqa: BLE001
            done = None
        if done:
            return {"ok": False, "accepted": False, "error": "The war is over. The campaign is complete."}
        if launch:
            with self._lock:
                if self._busy:
                    return {"ok": False, "error": "kernel busy with another deploy"}
                if _spring_already_open():
                    err = "Beyond All Reason is already open. Finish or close that match, then drop again."
                    refused = {
                        "ok": False,
                        "error": err,
                        "at": utc_now(),
                        "launch": {"ok": False, "skipped": True, "reason": err},
                    }
                    self._last_deploy = refused
                    self._error = err
                    self._deploy_phase = "failed"
                    return refused
                self._busy = True
                self._error = None
                self._deploy_phase = "building"
                self._pending_roster = None
                self._roster_gen = 0
                self._roster_client_gen = 0
                self._roster_token = token
            threading.Thread(
                target=self._deploy_async,
                args=(plan,),
                name="va-deploy",
                daemon=True,
            ).start()
            return {"ok": True, "accepted": True, "phase": "building", "at": utc_now()}

        with self._lock:
            if self._busy:
                return {"ok": False, "error": "kernel busy with another deploy"}
            self._busy = True
            self._error = None
        try:
            return self._deploy_body(plan, launch=False)
        finally:
            with self._lock:
                self._busy = False

    def _deploy_body(self, plan: dict[str, Any], *, launch: bool = True) -> dict[str, Any]:
        # The build used to run under _lock on the request thread, which froze
        # every other hub call. This block stays indented; the lock is gone.
        plan = dict(plan or {})
        hot = bool(plan.pop("hotDrop", False))
        if True:
            try:
                if launch and _spring_already_open():
                    err = "Beyond All Reason is already open. Finish or close that match, then drop again."
                    refused = {
                        "ok": False,
                        "error": err,
                        "at": utc_now(),
                        "launch": {"ok": False, "skipped": True, "reason": err},
                    }
                    self._last_deploy = refused
                    self._error = err
                    return refused

                # Company preamble gate — drop only after hub seals the run company.
                try:

                    sp = state_path(self.ws)
                    if sp.is_file():
                        st = migrate_state(load_json(sp))
                        ensure_company(st, self.ws)
                        company = st.get("company") or {}
                        if not company.get("sealed"):
                            return {
                                "ok": False,
                                "error": "Form the company first — pick 3 packs on the hub preamble",
                                "at": utc_now(),
                                "companyPreambleNeeded": True,
                            }
                        # Core always ships. The hub Dropping list is who else comes.
                        # Missing crewBand means the whole living company (old callers).
                        # Ids outside the sealed company are dropped.
                        plan = dict(plan or {})
                        requested = plan.get("crewBand")
                        if requested is None:
                            requested = plan.get("deployAces")
                        if hot:
                            # Hot drop: every pack the company could send is compiled in; the
                            # Drop names who actually goes (CampaignKernel.drop).
                            requested = None
                        band, aces = sortie_roster(st, requested)
                        plan["crewBand"] = band
                        plan["deployAces"] = aces
                        plan["rosterNote"] = (
                            f"{len(band)} packs + {len(aces) - len(band)} core"
                        )
                        # The reserve: what boards this drop (roster.cadre), clamped to what the
                        # reserve holds and the lift limit; no choice sent = the suggestion.
                        from verdance.company import reserve as _reserve
                        roster = st.setdefault("roster", {})
                        held = _reserve.ensure_reserve(roster)
                        cap = _reserve.lift_cap(st)
                        asked = plan.get("reserveBring")
                        if hot:
                            roster["cadre"] = {d: int(n) for d, n in held.items() if int(n or 0) > 0}
                        else:
                            roster["cadre"] = (_reserve.clamp_bring(asked, held, cap, self.ws) if isinstance(asked, dict)
                                               else _reserve.default_bring(held, cap, self.ws))
                        plan["reserveBring"] = dict(roster["cadre"])
                        save_json(sp, st)
                        # Bro Tzar (and future call-ins): stamp then consume so one order = one Drop.
                        calls = peek_mission_call_ins(st)
                        if calls:
                            plan["missionCallIns"] = calls
                            consume_mission_call_ins(st)
                            try:
                                save_json(sp, st)
                            except Exception:  # noqa: BLE001
                                pass
                except Exception as e:  # noqa: BLE001
                    return {
                        "ok": False,
                        "error": f"company gate failed: {e}",
                        "at": utc_now(),
                    }

                # Arm (or clear) the hot drop before the build reads it.
                from verdance_kernel import hot_drop as _hot
                from verdance_kernel.sortie import find_bar_data_root
                hot_token = _hot.arm(self.ws, find_bar_data_root(self.ws)) if hot else None
                if not hot:
                    _hot.disarm(self.ws)
                # Stamp → intent → build FIRST, then sync the built seed into BAR.
                # Syncing before build used to freeze a stale SDD under data/games
                # while the workspace seed moved on — hub marks never reached BAR.
                stamp_report = stamp_plan(plan, self.ws)
                if not stamp_report.get("ok"):
                    err = stamp_report.get("error") or _first_error_line(stamp_report)
                    refused = {
                        "ok": False,
                        "error": err,
                        "at": utc_now(),
                        "stamp": stamp_report,
                        "launch": {"ok": False, "skipped": True, "reason": err},
                    }
                    self._last_deploy = refused
                    self._error = err
                    return refused
                intent_report = self.materialize_intent()
                # Order (pass five): sync the mod FIRST, then build. The installer writes the seed into
                # BAR's data\games copy; building before the copy left a seedless archive, which the
                # retired play_session host used to paper over with a second build.
                mod_report: dict[str, Any] = {"skipped": True}
                if intent_report.get("ok"):
                    mod_report = self.sync_mod(copy=True)
                build_report = (
                    self.build_mission() if intent_report.get("ok") and mod_report.get("ok") is not False else {"ok": False, "skipped": True, "reason": "mod sync failed" if mod_report.get("ok") is False else "intent failed"}
                )
                launch_report: dict[str, Any] = {"skipped": True}
                if launch and build_report.get("ok"):
                    # The build already installed the seed and wrote the startscript; the kernel starts the engine.
                    with self._lock:
                        self._deploy_phase = "launching"
                    launch_report = self.launch_bar()
                    if hot_token and launch_report.get("ok") and not launch_report.get("skipped"):
                        self._arm_hot(hot_token, launch_report, plan)
                elif launch and not build_report.get("ok"):
                    launch_report = {"ok": False, "reason": "build failed — not launching"}

                # Prefer what intent/materialize actually sealed (hub stamp wins),
                # not the pre-override stamp report alone.
                intent_zones = self._seed_hint_from_outbox()
                # The seal asks one question: did the engine start?
                # A stamp warning must not turn a live launch into "drop failed".
                engine_started = bool(
                    launch_report.get("ok") and not launch_report.get("skipped")
                )
                if launch:
                    drop_ok = engine_started
                else:
                    drop_ok = bool(
                        stamp_report.get("ok")
                        and intent_report.get("ok")
                        and build_report.get("ok")
                    )
                result = {
                    "ok": drop_ok,
                    "at": utc_now(),
                    "modSync": mod_report,
                    "stamp": stamp_report,
                    "intent": intent_report,
                    "build": build_report,
                    "launch": launch_report,
                    "seedHint": {
                        "targetZoneId": intent_zones.get("targetZoneId")
                        or stamp_report.get("targetZoneId"),
                        "deploymentZoneId": intent_zones.get("deploymentZoneId")
                        or stamp_report.get("deploymentZoneId"),
                        "extractionZoneId": intent_zones.get("extractionZoneId")
                        or stamp_report.get("extractionZoneId"),
                        "secondaryCaptureZoneIds": intent_zones.get("secondaryCaptureZoneIds")
                        or stamp_report.get("secondaryCaptureZoneIds"),
                        "openingMission": intent_zones.get("openingMission"),
                        "source": intent_zones.get("source") or stamp_report.get("source"),
                    },
                }
                self._last_deploy = result
                if launch:
                    self._last_launch = launch_report
                if not result["ok"]:
                    err = _first_error_line(build_report, intent_report, stamp_report)
                    if err.startswith("deploy pipeline failed") and launch_report.get("reason"):
                        err = str(launch_report["reason"])[:400]
                    self._error = err
                    result["error"] = err
                return result
            finally:
                pass

    def bring_home(
        self,
        *,
        extract: bool = True,
        skip_advance: bool = False,
        mode: str = "manual",
    ) -> dict[str, Any]:
        """Sole campaign ingest path: extract → normalize/advance → hub debrief.

        See docs/CAMPAIGN_BAR_PROTOCOL.md. apply_result is an alias.
        """
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "kernel busy"}
            self._busy = True
            self._error = None
            try:
                # The watcher (verdance_kernel.sortie) already wrote inbox/latest_va_result.json from the
                # infolog; `extract` is kept for callers but there is no second extractor any more.
                extract_info: dict[str, Any] = {"skipped": True, "source": "sortie_watch_inbox"}
                del extract

                has_inbox = latest_result_path(self.ws).is_file()
                if not has_inbox and not skip_advance:
                    incomplete = self._incomplete_home(
                        reason="no_inbox_result",
                        extract_info=extract_info,
                        mode=mode,
                    )
                    self._last_advance = incomplete
                    self._error = "no result in inbox"
                    return incomplete

                hub_apply = apply_result_to_hub(
                    self.ws,
                    skip_advance=skip_advance or not has_inbox,
                )
                steam_bits = steam_mod.maybe_achievements_from_result(self.ws, hub_apply)
                cloud = steam_mod.cloud_mirror(self.ws)
                # apply_result_to_hub builds the hub from the state it loaded before the advance
                # ran; rebuild once more so the homecoming card carries the bead's manifest and
                # the board paints the belief the fold just wrote.
                if hub_apply.get("ok"):
                    try:
                        self.rebuild_hub(skip_apply=True, keep_result=True)
                    except Exception as exc:  # noqa: BLE001
                        hub_apply["postRebuildError"] = str(exc)
                hub = self.get_hub_surface()
                surface = surface_mod.write_surface(
                    self.ws, hub.get("hub") if hub.get("ok") else None
                )
                debrief = (hub_apply or {}).get("debrief") or (
                    (hub_apply or {}).get("lastResult") or {}
                ).get("debrief")
                result = {
                    "ok": bool(hub_apply.get("ok")),
                    "at": utc_now(),
                    "mode": mode,
                    "extract": extract_info,
                    "apply": hub_apply,
                    "debrief": debrief,
                    "steam": {"achievements": steam_bits, "cloud": cloud},
                    "surface": {"path": surface.get("path")},
                    "auto": mode == "auto",
                }
                # Promote top-level debrief fields for hub poll
                if isinstance(debrief, dict):
                    result["verdict"] = debrief.get("verdict")
                    result["headline"] = debrief.get("headline")
                    result["resultKey"] = debrief.get("resultKey")
                    result["duplicate"] = debrief.get("duplicate")
                # Promote wallets so clients that merge the advance response
                # (without waiting on hub_result) still see post-settle Tnb/km$.
                for key in (
                    "tenebrium",
                    "commerce",
                    "company",
                    "factionBanks",
                    "missionNumber",
                ):
                    if hub_apply.get(key) is not None:
                        result[key] = hub_apply.get(key)
                    elif isinstance(hub.get("hub"), dict) and hub["hub"].get(key) is not None:
                        result[key] = hub["hub"].get(key)
                self._last_advance = result
                if not result["ok"]:
                    self._error = "advance/hub apply failed"
                return result
            finally:
                self._busy = False

    def apply_result(self, *, extract: bool = True, skip_advance: bool = False) -> dict[str, Any]:
        """Alias for bring_home (backward compatible)."""
        return self.bring_home(extract=extract, skip_advance=skip_advance, mode="manual")

    def _incomplete_home(
        self,
        *,
        reason: str,
        extract_info: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """Write presentable incomplete debrief without mutating campaign credit."""
        hot = self._hot
        if hot and not hot.get("dropped"):
            # The field was loaded for a drop that never happened: nothing went, nothing to report.
            self._clear_hot()
            return {"ok": True, "at": utc_now(), "mode": mode, "cancelled": True,
                    "headline": "The field closed before the drop. Nothing went."}
        try:

            credit = credit_from_result({"status": "incomplete", "terminalReason": reason})
            debrief = presentable_debrief(credit)
        except Exception:  # noqa: BLE001
            debrief = {
                "ok": False,
                "verdict": "incomplete",
                "headline": "Result not home — Retry extract or Abandon.",
                "terminalReason": reason,
                "changed": ["no campaign credit"],
                "nextAction": "retry_or_abandon",
                "resultKey": None,
                "duplicate": False,
            }
        patch = {
            "schemaVersion": "verdance-hub-result/1.0",
            "at": utc_now(),
            "ok": False,
            "incomplete": True,
            "reason": reason,
            "debrief": debrief,
            "lastResult": {
                "at": utc_now(),
                "verdict": "incomplete",
                "debrief": debrief,
                "source": "bring_home_incomplete",
            },
        }
        try:
            out = hub_result_path(self.ws)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(patch, indent=2) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "at": utc_now(),
            "mode": mode,
            "incomplete": True,
            "reason": reason,
            "extract": extract_info,
            "debrief": debrief,
            "apply": patch,
            "auto": mode == "auto",
            "verdict": "incomplete",
            "headline": debrief.get("headline"),
        }

    def abandon_sortie(self, *, reason: str = "player_abandon") -> dict[str, Any]:
        """Record abandon bead without zone flip or mission bump; unlock next Drop."""
        from verdance_kernel import sortie as _sortie

        if _sortie.spring_running():
            return {"ok": False, "error": "Beyond All Reason is still open. Extract or close it first; abandon is for a sortie that never came home."}
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "kernel busy"}
            self._busy = True
            self._error = None
            try:
                tools = Path(__file__).resolve().parent.parent
                if str(tools) not in sys.path:
                    sys.path.insert(0, str(tools))

                sp = state_path(self.ws)
                if not sp.is_file():
                    return {"ok": False, "error": "missing campaign_state.json"}
                state = migrate_state(load_json(sp))
                fake = {
                    "status": "abandon",
                    "verdict": "abandon",
                    "terminalReason": reason,
                    "campaignId": state.get("campaignId") or "verdance_ashes",
                    "missionId": state.get("currentMissionId") or "va_unknown",
                    "missionNumber": state.get("missionNumber") or 0,
                    "chapterIndex": 1,
                    "mapId": state.get("sessionHomeMap") or "",
                    "resultKey": (
                        f"{state.get('campaignId') or 'verdance_ashes'}|"
                        f"{state.get('currentMissionId') or 'va_unknown'}|"
                        f"{state.get('missionNumber') or 0}|ch1|abandon|{reason}|f0"
                    ),
                    "freeTnbMint": False,
                }
                state, report, _intent, _events = process_result(
                    state, fake, None, self.ws, None
                )
                save_json(sp, state)
                hub_apply = apply_result_to_hub(self.ws, skip_advance=True)
                # Stamp debrief onto hub_result
                debrief = report.get("debrief") or {
                    "verdict": "abandon",
                    "headline": "Left the field.",
                    "resultKey": report.get("resultKey"),
                }
                try:
                    hr = hub_result_path(self.ws)
                    data = {}
                    if hr.is_file():
                        data = json.loads(hr.read_text(encoding="utf-8-sig"))
                    data["debrief"] = debrief
                    data["lastResult"] = {
                        "at": utc_now(),
                        "verdict": "abandon",
                        "debrief": debrief,
                        "source": "abandon_sortie",
                    }
                    data["ok"] = True
                    data["at"] = utc_now()
                    hr.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
                hub = self.get_hub_surface()
                surface_mod.write_surface(
                    self.ws, hub.get("hub") if hub.get("ok") else None
                )
                result = {
                    "ok": bool(report.get("processed") or report.get("reason") == "duplicate"),
                    "at": utc_now(),
                    "abandon": True,
                    "report": {
                        k: v
                        for k, v in report.items()
                        if k not in ("bead",)
                    },
                    "debrief": debrief,
                    "verdict": "abandon",
                    "headline": debrief.get("headline") if isinstance(debrief, dict) else "Left the field.",
                    "hubRebuild": hub_apply.get("hubRebuild") if isinstance(hub_apply, dict) else None,
                }
                self._last_advance = result
                return result
            except Exception as e:  # noqa: BLE001
                self._error = str(e)
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
            finally:
                self._busy = False

    @_campaign_lock
    def purchase(self, listing_id: str) -> dict[str, Any]:
        if not listing_id:
            return {"ok": False, "error": "listingId required"}
        if not state_path(self.ws).is_file():
            return {"ok": False, "error": "missing campaign_state.json"}
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "kernel busy — try the buy again in a moment"}
            self._busy = True
            try:

                raw = load_json(state_path(self.ws))
                state = migrate_state(raw)
                receipt = purchase_listing(state, listing_id, self.ws)
                if not receipt.get("ok"):
                    return {"ok": False, **receipt}
                save_json(state_path(self.ws), state)
                hub_info = apply_result_to_hub(self.ws, skip_advance=True)
                hub_payload = self.get_hub_surface()
                hub = hub_payload.get("hub") if hub_payload.get("ok") else {}
                steam_mod.unlock_achievement(self.ws, "BROKER_DEAL", detail=listing_id)
                steam_mod.cloud_mirror(self.ws)
                surface_mod.write_surface(self.ws, hub)
                return {
                    "ok": True,
                    "at": utc_now(),
                    "receipt": receipt,
                    "missionNumber": hub.get("missionNumber") or hub_info.get("missionNumber"),
                    "tenebrium": hub.get("tenebrium"),
                    "commerce": hub.get("commerce"),
                    "aces": hub.get("aces"),
                    "hubResultPath": hub_info.get("hubResultPath"),
                }
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
            finally:
                self._busy = False

    @_campaign_lock
    def home_build(self) -> dict[str, Any]:
        """Raise the Rock Jungle camp (Tnb + 1km$ metal). Hub-only scale lever."""
        if not state_path(self.ws).is_file():
            return {"ok": False, "error": "missing campaign_state.json"}
        try:

            raw = load_json(state_path(self.ws))
            state = migrate_state(raw)
            receipt = apply_home_build(state, self.ws)
            if not receipt.get("ok"):
                return receipt
            save_json(state_path(self.ws), state)
            hub_info = apply_result_to_hub(self.ws, skip_advance=True)
            hub_payload = self.get_hub_surface()
            hub = hub_payload.get("hub") if hub_payload.get("ok") else {}
            surface_mod.write_surface(self.ws, hub)
            return {
                "ok": True,
                "at": utc_now(),
                "receipt": receipt,
                "homeCamp": hub.get("homeCamp") or receipt.get("homeCamp"),
                "flags": hub.get("flags") or receipt.get("flags"),
                "tenebrium": hub.get("tenebrium"),
                "commerce": hub.get("commerce"),
                "hubResultPath": hub_info.get("hubResultPath") if isinstance(hub_info, dict) else None,
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def write_campaign_surface(self) -> dict[str, Any]:
        hub = self.get_hub_surface()
        return surface_mod.write_surface(self.ws, hub.get("hub") if hub.get("ok") else None)

    def attach_bridge(self, bridge: Any) -> None:
        self._bridge = bridge
