"""Phase 4 — campaign surface for in-BAR (and future RML) consumers.

Writes a small, stable JSON the mutator can poll without talking HTTP.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from verdance.common import utc_now

from verdance_kernel.paths import campaign_surface_path, hub_state_path, state_path


def build_surface(ws: Path, hub: dict[str, Any] | None = None) -> dict[str, Any]:
    if hub is None:
        p = hub_state_path(ws)
        if p.is_file():
            try:
                hub = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:  # noqa: BLE001
                hub = {}
        else:
            hub = {}
    node = (hub or {}).get("node") or {}
    companion = (hub or {}).get("companion") or {}
    aces = (hub or {}).get("aces") or []
    return {
        "schemaVersion": "verdance-campaign-surface/1.0",
        "at": utc_now(),
        "missionNumber": (hub or {}).get("missionNumber"),
        "arc": (hub or {}).get("arc"),
        "tagline": (hub or {}).get("tagline"),
        "sessionHomeMap": (hub or {}).get("sessionHomeMap"),
        "sessionMode": (hub or {}).get("sessionMode"),
        "ketha": {
            "text": node.get("text"),
            "morale": companion.get("morale"),
            "stress": companion.get("stress"),
        },
        "choices": [
            {
                "id": c.get("id"),
                "kind": c.get("kind"),
                "label": c.get("label"),
                "blurb": c.get("blurb"),
            }
            for c in (node.get("choices") or [])
            if isinstance(c, dict)
        ],
        "aces": [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "level": a.get("level"),
                "wounds": a.get("wounds"),
                "status": a.get("status"),
            }
            for a in aces
            if isinstance(a, dict)
        ],
        "tenebrium": (hub or {}).get("tenebrium"),
        "pathSignal": (hub or {}).get("pathSignal"),
        "statePresent": state_path(ws).is_file(),
        "note": "BAR widgets may show this between sorties; full CYOA stays in shell for now.",
    }


def write_surface(ws: Path, hub: dict[str, Any] | None = None) -> dict[str, Any]:
    surface = build_surface(ws, hub)
    path = campaign_surface_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(surface, indent=2) + "\n", encoding="utf-8")
    surface["path"] = str(path)
    return surface
