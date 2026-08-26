"""Verdance's Ashes — campaign kernel (Steam ship spine).

Phases (see docs/SHIP_ARCHITECTURE.md):
  0  Forge loop (hub_host + bats) — still works
  1  Single launcher + frozen API surface
  2  BAR bridge owns launch + auto-apply
  3  Steam cloud / achievements stubs + freeze
  4  In-BAR campaign surface hooks

Public surface:
  CampaignKernel  — get_hub_surface, commit_deploy, apply_result, purchase, ...
  serve / launch  — product entrypoints
"""
from __future__ import annotations

from pathlib import Path

from verdance_kernel.api import CampaignKernel, KERNEL_SCHEMA
from verdance_kernel.phases import PHASES, phase_status

__all__ = [
    "CampaignKernel",
    "KERNEL_SCHEMA",
    "PHASES",
    "phase_status",
    "__version__",
]


def _read_version() -> str:
    """Prefer workspace VERSION file; fall back to package default."""
    try:
        ver_path = Path(__file__).resolve().parents[2] / "VERSION"
        if ver_path.is_file():
            text = ver_path.read_text(encoding="utf-8").strip().splitlines()
            if text and text[0].strip():
                return text[0].strip()
    except Exception:  # noqa: BLE001
        pass
    return "0.8.0"


__version__ = _read_version()
