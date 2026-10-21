"""Zone id canonicalisation: legacy ids migrate onto the current zone maps.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, load_json

_ZONE_MIGRATION_CACHE: Dict[str, Dict[str, str]] = {}
_ZONE_VALID_CACHE: Dict[str, set] = {}


def load_zone_migration(workspace: Optional[Path] = None) -> Dict[str, str]:
    """old zone id -> the zone that inherited it, from the last re-cut."""
    key = str(workspace or "")
    if key in _ZONE_MIGRATION_CACHE:
        return _ZONE_MIGRATION_CACHE[key]
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "zone_maps" / "authored")
    roots.append(WORKSPACE_ROOT / "data" / "zone_maps" / "authored")
    mapping: Dict[str, str] = {}
    for root in roots:
        path = root / "zone_id_migration.json"
        if not path.exists():
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        table = (data or {}).get("zones") if isinstance(data, dict) else None
        if isinstance(table, dict):
            mapping.update({str(k): str(v) for k, v in table.items() if v})
        if mapping:
            break
    _ZONE_MIGRATION_CACHE[key] = mapping
    return mapping


def valid_zone_ids(workspace: Optional[Path] = None) -> set:
    """Every zone id that currently exists, across all maps."""
    key = str(workspace or "")
    if key in _ZONE_VALID_CACHE:
        return _ZONE_VALID_CACHE[key]
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "zone_maps" / "authored")
    roots.append(WORKSPACE_ROOT / "data" / "zone_maps" / "authored")
    ids: set = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.zone_map.json")):
            try:
                data = load_json(path)
            except Exception:
                continue
            for zone in (data or {}).get("zones") or []:
                ids.add(str(zone.get("zoneId")))
        if ids:
            break
    _ZONE_VALID_CACHE[key] = ids
    return ids


def canonical_zone_id(zone_id: Any, workspace: Optional[Path] = None) -> Any:
    """Translate a retired zone id forward.

    Authored content -- default deploy zones, world character homes, the act-3
    finale objectives -- names zones directly, and a re-cut retires those names.
    Rather than hand-editing every constant on every re-cut, stale ids are
    translated through the migration map at the point of use."""
    if not isinstance(zone_id, str) or not zone_id:
        return zone_id
    valid = valid_zone_ids(workspace)
    if not valid or zone_id in valid:
        return zone_id
    mapping = load_zone_migration(workspace)
    direct = mapping.get(zone_id)
    if direct:
        return direct
    # Prose carries zone ids too ("Deploy RJ_CENTRAL_LAGOON_MAZE"), and a
    # briefing naming a zone that no longer exists reads as a bug to the player.
    if len(zone_id) > 12 and "_" in zone_id:
        replaced = zone_id
        for old_id, new_id in mapping.items():
            if old_id in replaced:
                replaced = replaced.replace(old_id, new_id)
        if replaced != zone_id:
            return replaced
    return zone_id


def canonicalize_zone_ids(node: Any, workspace: Optional[Path] = None) -> Any:
    """Translate every retired zone id anywhere in a structure."""
    if isinstance(node, str):
        return canonical_zone_id(node, workspace)
    if isinstance(node, list):
        return [canonicalize_zone_ids(item, workspace) for item in node]
    if isinstance(node, dict):
        return {key: canonicalize_zone_ids(value, workspace) for key, value in node.items()}
    return node


__all__ = [
    "_ZONE_MIGRATION_CACHE",
    "_ZONE_VALID_CACHE",
    "canonical_zone_id",
    "canonicalize_zone_ids",
    "load_zone_migration",
    "valid_zone_ids",
]
