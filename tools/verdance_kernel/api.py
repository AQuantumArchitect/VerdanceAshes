"""CampaignKernel — frozen product API (Phase 1+).

Callers (HTTP shell, launcher, tests, future Tauri) should use this class
rather than invoking scattered .ps1 / .py scripts.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# tools/ on path for stamp / apply / story engine
_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from apply_result_to_hub_v1 import apply as apply_result_to_hub  # noqa: E402
from stamp_deploy_plan_v1 import stamp as stamp_plan  # noqa: E402

from verdance_kernel import steam as steam_mod
from verdance_kernel import surface as surface_mod
from verdance_kernel.paths import (
    hub_result_path,
    hub_state_path,
    latest_result_path,
    resolve_workspace,
    session_status_path,
    showoff_dir,
    state_path,
)
from verdance_kernel.runtime import run_cmd, run_ps1

KERNEL_SCHEMA = "verdance-campaign-kernel/1.0"

# Preferred player-path scripts first, then legacy scripts/ names.
_PS1_ALIASES: dict[str, tuple[str, ...]] = {
    "build": ("scripts/player/build_mission.ps1", "scripts/build_next_mission_v1.ps1"),
    "session": ("scripts/player/play_session.ps1", "scripts/play_session_v1.ps1"),
    "extract": ("scripts/player/extract_result.ps1", "scripts/extract_latest_result.ps1"),
    "install_mod": ("scripts/player/install_mod.ps1", "scripts/install_mod_archive.ps1"),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CampaignKernel:
    """Authoritative campaign ops for one workspace."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.ws = resolve_workspace(workspace)
        self._lock = threading.RLock()
        self._busy = False
        self._last_deploy: dict[str, Any] | None = None
        self._last_launch: dict[str, Any] | None = None
        self._last_advance: dict[str, Any] | None = None
        self._last_mod_sync: dict[str, Any] | None = None
        self._error: str | None = None
        self._bridge = None  # set by bar_bridge if attached
        self.started_at = _now()

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

    def session_status(self) -> dict[str, Any]:
        p = session_status_path(self.ws)
        if not p.is_file():
            return {"present": False}
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            return {"present": True, "status": data}
        except Exception as e:  # noqa: BLE001
            return {"present": True, "error": str(e)}

    # ── ops ──────────────────────────────────────────────────

    def rebuild_hub(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        py = sys.executable
        for name in ("build_hub_state_v1.py", "build_zone_boards_v1.py"):
            script = self.ws / "tools" / name
            if script.is_file():
                out[name] = run_cmd([py, str(script)], self.ws, timeout=60)
        apply_info = apply_result_to_hub(self.ws, skip_advance=True)
        hub = self.get_hub_surface()
        surface = surface_mod.write_surface(
            self.ws, hub.get("hub") if hub.get("ok") else None
        )
        steam_mod.cloud_mirror(self.ws)
        return {
            "ok": True,
            "rebuild": out,
            "apply": apply_info,
            "surface": {"path": surface.get("path")},
            "at": _now(),
        }

    def materialize_intent(self) -> dict[str, Any]:
        engine = self.ws / "tools" / "verdance_story_engine_v1.py"
        return run_cmd(
            [sys.executable, str(engine), "intent", "--workspace", str(self.ws)],
            self.ws,
            timeout=120,
        )

    def sync_mod(self, *, copy: bool = True) -> dict[str, Any]:
        """Copy (or junction) workspace mutator into BAR data/games before play."""
        script = self._resolve_ps1("install_mod")
        if script is None:
            report = {"ok": False, "reason": "install_mod script missing", "at": _now()}
            self._last_mod_sync = report
            return report
        extra: list[str] = []
        # install_mod.ps1 defaults to Copy; legacy install_mod_archive needs -Copy
        if copy and script.name == "install_mod_archive.ps1":
            extra.append("-Copy")
        report = run_ps1(script, self.ws, extra_args=extra or None, timeout=120)
        report = dict(report)
        report["at"] = _now()
        report["script"] = str(script)
        self._last_mod_sync = report
        return report

    def build_mission(self) -> dict[str, Any]:
        script = self._resolve_ps1("build")
        if script is None:
            return {"ok": False, "reason": "build mission script missing"}
        return run_ps1(script, self.ws, timeout=240)

    def launch_bar(self, *, max_missions: int = 1, auto_relaunch: bool = False) -> dict[str, Any]:
        script = self._resolve_ps1("session")
        if script is None:
            return {"ok": False, "reason": "play_session script missing"}
        args = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Workspace",
            str(self.ws),
            "-MaxMissions",
            str(max_missions),
        ]
        if not auto_relaunch:
            args.append("-NoAutoRelaunch")
        try:
            proc = subprocess.Popen(
                args,
                cwd=str(self.ws),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            report = {
                "ok": True,
                "pid": proc.pid,
                "script": str(script),
                "note": f"play_session started (MaxMissions={max_missions}, auto_relaunch={auto_relaunch})",
                "at": _now(),
            }
            self._last_launch = report
            if self._bridge is not None:
                try:
                    self._bridge.watch_after_launch(report)
                except Exception:  # noqa: BLE001
                    pass
            return report
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "reason": f"{type(e).__name__}: {e}"}

    def commit_deploy(self, plan: dict[str, Any], *, launch: bool = True) -> dict[str, Any]:
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "kernel busy with another deploy"}
            self._busy = True
            self._error = None
            try:
                # Always refresh BAR mutator so Drop does not load a stale SDD
                mod_report = self.sync_mod(copy=True)
                stamp_report = stamp_plan(plan, self.ws)
                intent_report = self.materialize_intent()
                build_report = (
                    self.build_mission() if intent_report.get("ok") else {"ok": False, "skipped": True}
                )
                launch_report: dict[str, Any] = {"skipped": True}
                if launch and build_report.get("ok"):
                    launch_report = self.launch_bar()
                elif launch and not build_report.get("ok"):
                    launch_report = {"ok": False, "reason": "build failed — not launching"}

                result = {
                    "ok": bool(
                        stamp_report.get("ok")
                        and intent_report.get("ok")
                        and build_report.get("ok")
                    ),
                    "at": _now(),
                    "modSync": mod_report,
                    "stamp": stamp_report,
                    "intent": intent_report,
                    "build": build_report,
                    "launch": launch_report,
                    "seedHint": {
                        "targetZoneId": stamp_report.get("targetZoneId"),
                        "deploymentZoneId": stamp_report.get("deploymentZoneId"),
                        "extractionZoneId": stamp_report.get("extractionZoneId"),
                        "secondaryCaptureZoneIds": stamp_report.get("secondaryCaptureZoneIds"),
                    },
                }
                self._last_deploy = result
                if launch:
                    self._last_launch = launch_report
                if not result["ok"]:
                    self._error = "deploy pipeline failed — see stamp/intent/build"
                return result
            finally:
                self._busy = False

    def extract_result(self) -> dict[str, Any]:
        script = self._resolve_ps1("extract")
        if script is None:
            return {"ok": False, "reason": "extract script missing"}
        return run_ps1(script, self.ws, timeout=60)

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
                extract_info: dict[str, Any] = {"skipped": True}
                if extract and not skip_advance:
                    extract_info = self.extract_result()
                    if not extract_info.get("ok", True) and extract_info.get("returncode", 0) not in (
                        0,
                        None,
                    ):
                        # Extract failed — present incomplete debrief, do not fake advance
                        incomplete = self._incomplete_home(
                            reason="extract_failed",
                            extract_info=extract_info,
                            mode=mode,
                        )
                        self._last_advance = incomplete
                        self._error = "extract failed — incomplete"
                        return incomplete

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
                hub = self.get_hub_surface()
                surface = surface_mod.write_surface(
                    self.ws, hub.get("hub") if hub.get("ok") else None
                )
                debrief = (hub_apply or {}).get("debrief") or (
                    (hub_apply or {}).get("lastResult") or {}
                ).get("debrief")
                result = {
                    "ok": bool(hub_apply.get("ok")),
                    "at": _now(),
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
        try:
            from match_credit_v1 import presentable_debrief, credit_from_result

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
            "at": _now(),
            "ok": False,
            "incomplete": True,
            "reason": reason,
            "debrief": debrief,
            "lastResult": {
                "at": _now(),
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
            "at": _now(),
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
        with self._lock:
            if self._busy:
                return {"ok": False, "error": "kernel busy"}
            self._busy = True
            self._error = None
            try:
                tools = Path(__file__).resolve().parent.parent
                if str(tools) not in sys.path:
                    sys.path.insert(0, str(tools))
                from verdance_story_engine_v1 import (  # noqa: E402
                    load_json,
                    migrate_state,
                    process_result,
                    save_json,
                )

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
                        "at": _now(),
                        "verdict": "abandon",
                        "debrief": debrief,
                        "source": "abandon_sortie",
                    }
                    data["ok"] = True
                    data["at"] = _now()
                    hr.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
                hub = self.get_hub_surface()
                surface_mod.write_surface(
                    self.ws, hub.get("hub") if hub.get("ok") else None
                )
                result = {
                    "ok": bool(report.get("processed") or report.get("reason") == "duplicate"),
                    "at": _now(),
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

    def purchase(self, listing_id: str) -> dict[str, Any]:
        if not listing_id:
            return {"ok": False, "error": "listingId required"}
        if not state_path(self.ws).is_file():
            return {"ok": False, "error": "missing campaign_state.json"}
        try:
            from verdance_story_engine_v1 import (  # noqa: E402
                load_json,
                migrate_state,
                purchase_listing,
                save_json,
            )

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
                "at": _now(),
                "receipt": receipt,
                "missionNumber": hub.get("missionNumber") or hub_info.get("missionNumber"),
                "tenebrium": hub.get("tenebrium"),
                "commerce": hub.get("commerce"),
                "aces": hub.get("aces"),
                "hubResultPath": hub_info.get("hubResultPath"),
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def home_build(self) -> dict[str, Any]:
        """Raise the Rock Jungle camp (Tnb + scrap). Hub-only scale lever."""
        if not state_path(self.ws).is_file():
            return {"ok": False, "error": "missing campaign_state.json"}
        try:
            from verdance_story_engine_v1 import (  # noqa: E402
                apply_home_build,
                load_json,
                migrate_state,
                save_json,
            )

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
                "at": _now(),
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
