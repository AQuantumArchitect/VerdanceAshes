"""Workspace path helpers for the campaign kernel."""
from __future__ import annotations

from pathlib import Path


def resolve_workspace(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # tools/verdance_kernel/paths.py → tools → workspace root
    return Path(__file__).resolve().parents[2]


def showoff_dir(ws: Path) -> Path:
    return ws / "app" / "showoff"


def state_path(ws: Path) -> Path:
    return ws / "state" / "campaign_state.json"


def saves_dir(ws: Path) -> Path:
    """Named campaign save slots (portal Save / Load)."""
    return ws / "state" / "saves"


def backups_dir(ws: Path) -> Path:
    return ws / "state" / "backups"


def outbox(ws: Path) -> Path:
    return ws / "outbox"


def inbox(ws: Path) -> Path:
    return ws / "inbox"


def hub_state_path(ws: Path) -> Path:
    return showoff_dir(ws) / "hub_state.json"


def hub_result_path(ws: Path) -> Path:
    return outbox(ws) / "hub_result.latest.json"


def latest_result_path(ws: Path) -> Path:
    return inbox(ws) / "latest_va_result.json"


def steam_dir(ws: Path) -> Path:
    return ws / "state" / "steam"


def campaign_surface_path(ws: Path) -> Path:
    """Phase 4: flat surface the BAR mutator / future RML can read."""
    return outbox(ws) / "campaign_surface.latest.json"


