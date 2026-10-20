"""BAR bridge (pass five): the kernel's one watcher over a launched sortie.

Thin adapter kept under the old name so server/launcher construct it the same way. The work is in
verdance_kernel.sortie.SortieWatch: tail the infolog from the launch baseline, reassemble each
VA_RESULT_JSON block in Python, apply it once by resultKey through kernel.bring_home, and notice the
engine closing (no result → incomplete debrief). There is no inbox polling, no session-status file
and no powershell between the gadget and the campaign state any more.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from verdance_kernel.paths import hub_result_path
from verdance_kernel.sortie import SortieWatch

if TYPE_CHECKING:
    from verdance_kernel.api import CampaignKernel


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BarBridge:
    def __init__(self, kernel: "CampaignKernel", *, poll_seconds: float = 2.0,
                 on_auto_apply: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.kernel = kernel
        self.on_auto_apply = on_auto_apply
        self._started_at = _now()
        self.watch = SortieWatch(kernel.ws, kernel.bring_home, kernel._incomplete_home, poll_seconds=poll_seconds, on_event=self._on_event)
        kernel.attach_bridge(self)

    # the server/launcher call start(); the watch itself only runs after a launch
    def start(self) -> None:
        return None

    def stop(self) -> None:
        self.watch.stop()

    def watch_after_launch(self, launch_report: dict[str, Any]) -> None:
        self.watch.watch(launch_report)

    def status(self) -> dict[str, Any]:
        w = self.watch.status()
        w.update({"running": True, "watching": w.get("phase") not in ("idle", "home", "closed-without-result"), "startedAt": self._started_at})
        return w

    def _on_event(self, ev: dict[str, Any]) -> None:
        # one log line per event for operators, and the hub's "autoApplied" mark on the debrief
        try:
            out = self.kernel.ws / "outbox" / "bridge.latest.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(dict(ev, writtenAt=_now()), indent=2) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        if ev.get("event") in ("applied", "incomplete"):
            hr = hub_result_path(self.kernel.ws)
            if hr.is_file():
                try:
                    data = json.loads(hr.read_text(encoding="utf-8-sig"))
                    data["autoApplied"] = True
                    data["autoReason"] = ev.get("event")
                    data["autoAt"] = _now()
                    hr.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            if self.on_auto_apply:
                try:
                    self.on_auto_apply(ev)
                except Exception:  # noqa: BLE001
                    pass
