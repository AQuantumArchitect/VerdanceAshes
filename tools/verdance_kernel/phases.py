"""Ship-phase registry — what is live vs stub."""
from __future__ import annotations

from typing import Any

PHASES: dict[str, dict[str, Any]] = {
    "0": {
        "id": 0,
        "name": "Forge loop",
        "status": "live",
        "summary": "Operator tools under app/bin/forge. Not player path.",
    },
    "1": {
        "id": 1,
        "name": "Single launcher + kernel API",
        "status": "live",
        "summary": "Root PLAY.bat / SETUP.bat → python -m verdance_kernel launch.",
    },
    "2": {
        "id": 2,
        "name": "BAR bridge",
        "status": "live",
        "summary": "Launch watch + auto extract/apply; bridge.latest.json log.",
    },
    "3": {
        "id": 3,
        "name": "Steam freeze",
        "status": "stub",
        "summary": "Cloud save mirror + achievement log; real Steamworks deferred.",
    },
    "4": {
        "id": 4,
        "name": "In-BAR surface",
        "status": "stub",
        "summary": "campaign_surface.latest.json + mutator hooks; more UI can migrate later.",
    },
    "5": {
        "id": 5,
        "name": "Consolidated ship",
        "status": "live",
        "summary": "scripts/ship.ps1 → export/dist self-contained; SHIP.bat.",
    },
}


def phase_status() -> dict[str, Any]:
    return {
        "schemaVersion": "verdance-ship-phases/1.1",
        "phases": PHASES,
        "playerEntry": "SETUP.bat then PLAY.bat  OR  python -m verdance_kernel launch",
        "shipEntry": "SHIP.bat  OR  powershell -File scripts/ship.ps1",
        "kernelModule": "verdance_kernel",
    }
