"""Phase 2 — BAR bridge: watch launch, auto extract/apply.

Owns the post-fight half of the loop so the player does not need to
operate the pipeline. Manual apply_result remains a fallback.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from verdance_kernel.paths import hub_result_path, latest_result_path, session_status_path

if TYPE_CHECKING:
    from verdance_kernel.api import CampaignKernel


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BarBridge:
    """Background watcher attached to a CampaignKernel."""

    def __init__(
        self,
        kernel: CampaignKernel,
        *,
        poll_seconds: float = 4.0,
        on_auto_apply: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.kernel = kernel
        self.poll_seconds = poll_seconds
        self.on_auto_apply = on_auto_apply
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._watching = False
        self._last_result_sig: str | None = None
        self._last_auto: dict[str, Any] | None = None
        self._last_session_phase: str | None = None
        self._launch_pid: int | None = None
        self._started_at = _now()
        kernel.attach_bridge(self)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="va-bar-bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def watch_after_launch(self, launch_report: dict[str, Any]) -> None:
        self._watching = True
        self._launch_pid = launch_report.get("pid")
        self._last_session_phase = None
        # Do not clear last_result_sig — we only apply *new* results.

    def status(self) -> dict[str, Any]:
        return {
            "schemaVersion": "verdance-bar-bridge/1.0",
            "running": bool(self._thread and self._thread.is_alive()),
            "watching": self._watching,
            "launchPid": self._launch_pid,
            "lastAuto": self._last_auto,
            "pollSeconds": self.poll_seconds,
            "startedAt": self._started_at,
        }

    def _write_bridge_log(self, payload: dict[str, Any]) -> None:
        """Persist last bridge action for operators (outbox/bridge.latest.json)."""
        try:
            out = self.kernel.ws / "outbox" / "bridge.latest.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            data = dict(payload)
            data["writtenAt"] = _now()
            out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    def _result_sig(self) -> str | None:
        p = latest_result_path(self.kernel.ws)
        if not p.is_file():
            # also accept hub_result as signal of prior apply
            return None
        try:
            st = p.stat()
            # content hash-lite: size + mtime
            return f"{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            return None

    def _session_phase(self) -> str | None:
        p = session_status_path(self.kernel.ws)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            return str(data.get("phase") or data.get("status") or "")
        except Exception:  # noqa: BLE001
            return None

    def _try_auto_apply(self, reason: str) -> None:
        # Prefer inbox result; if extract just ran, apply may still work
        try:
            # Sole ingest path (protocol): bring_home
            if hasattr(self.kernel, "bring_home"):
                report = self.kernel.bring_home(
                    extract=True, skip_advance=False, mode="auto"
                )
            else:
                report = self.kernel.apply_result(extract=True, skip_advance=False)
        except Exception as e:  # noqa: BLE001
            self._last_auto = {"ok": False, "at": _now(), "reason": reason, "error": str(e)}
            self._write_bridge_log(self._last_auto)
            return

        report = dict(report)
        report["auto"] = True
        report["autoReason"] = reason
        self._last_auto = report
        self._write_bridge_log(report)
        new_sig = self._result_sig()
        if new_sig:
            self._last_result_sig = new_sig
        # Mark hub_result for shell poll
        hr = hub_result_path(self.kernel.ws)
        if hr.is_file():
            try:
                data = json.loads(hr.read_text(encoding="utf-8-sig"))
                data["autoApplied"] = bool(report.get("ok") or report.get("incomplete"))
                data["autoReason"] = reason
                data["autoAt"] = _now()
                if report.get("debrief"):
                    data["debrief"] = report["debrief"]
                hr.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        if self.on_auto_apply:
            try:
                self.on_auto_apply(report)
            except Exception:  # noqa: BLE001
                pass
        # Mode A: keep watching after a chapter so later resultKeys still apply.
        # Only stop when session is truly complete / BAR process gone.
        if reason in ("session-complete", "bar-exited"):
            self._watching = False
        # incomplete after bar exit also stops aggressive watch
        if report.get("incomplete") and reason in ("session-complete", "bar-exited"):
            self._watching = False

    def _bar_process_alive(self) -> bool | None:
        """Return True/False if we know launch pid; None if unknown."""
        if not self._launch_pid:
            return None
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            SYNCHRONIZE = 0x00100000
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(self._launch_pid))
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except Exception:  # noqa: BLE001
            try:
                import os

                # Windows: os.kill(pid, 0) is not reliable; try OpenProcess fallback failed
                os.kill(int(self._launch_pid), 0)
                return True
            except OSError:
                return False
            except Exception:  # noqa: BLE001
                return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(self.poll_seconds)

    def _tick(self) -> None:
        # Always notice new result files even if not "watching" (Mode A extracts)
        sig = self._result_sig()
        if sig and sig != self._last_result_sig:
            # New inbox result appeared
            if self._watching or self._last_result_sig is not None:
                self._try_auto_apply("result-file")
            else:
                # First sighting at boot — record without applying
                self._last_result_sig = sig

        phase = self._session_phase()
        if phase and phase != self._last_session_phase:
            prev = self._last_session_phase
            self._last_session_phase = phase
            pl = phase.lower()
            if self._watching and any(
                k in pl for k in ("extract", "session-complete", "complete", "advanced")
            ):
                self._try_auto_apply(f"session-{pl}")
            elif prev and "in-game" in (prev or "").lower() and "complete" in pl:
                self._try_auto_apply("session-complete")

        # BAR process exit while watching → final harvest (incomplete if empty)
        if self._watching:
            alive = self._bar_process_alive()
            if alive is False:
                self._try_auto_apply("bar-exited")
