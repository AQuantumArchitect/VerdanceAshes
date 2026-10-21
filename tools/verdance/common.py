"""Shared helpers for the Verdance campaign package.

One definition each. Every module under ``verdance`` imports these instead of
carrying its own copy (there were nine ``load_json`` and ten ``_clamp`` before
pass ten).
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_MISSING = object()

# tools/verdance/common.py -> tools/verdance -> tools -> workspace root
TOOLS_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = TOOLS_DIR.parent

# Map ids the engine and the zone graph both accept; the canonical spelling wins.
MAP_ALIASES = {
    "rock_jungle": "the_rock_jungle",
}


def tools_env(workspace: Optional[Path] = None, base: Optional[dict] = None) -> dict:
    """Environment for a child ``python -m verdance...`` process: tools/ first on PYTHONPATH.

    ``workspace/tools`` wins when it holds the package (a copied workspace runs its own copy).
    """
    tools = TOOLS_DIR
    if workspace is not None and (Path(workspace) / "tools" / "verdance" / "__init__.py").is_file():
        tools = Path(workspace).resolve() / "tools"
    env = dict(os.environ if base is None else base)
    prev = env.get("PYTHONPATH") or ""
    parts = [str(tools)] + [p for p in prev.split(os.pathsep) if p and p != str(tools)]
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def utc_now() -> str:
    """ISO-8601 UTC to the second, ``Z`` suffixed (``2026-10-21T15:21:09Z``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clamp(x: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp ``x`` into ``[lo, hi]``; None, junk and NaN clamp to ``lo``."""
    try:
        v = float(x if x is not None else lo)
    except (TypeError, ValueError):
        return lo
    if math.isnan(v):
        return lo
    return max(lo, min(hi, v))


def load_json(path: Path, default: Any = _MISSING) -> Any:
    """Read JSON. ``utf-8-sig`` tolerates the BOM PowerShell 5.1 prepends.

    Without ``default`` a missing file raises (the caller meant it to exist).
    With ``default`` a missing or unreadable file returns ``default`` instead.
    """
    path = Path(path)
    if default is not _MISSING:
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, obj: Any, indent: int = 2, sort_keys: bool = False) -> None:
    """Atomic JSON write: temp file beside the target, then ``os.replace``.

    A crash mid-write leaves the previous file intact rather than a truncated
    save. The first write of a narrative save keeps a pre-narrative backup so
    projection alone never destroys the older shape of ``campaign_state.json``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.name == "campaign_state.json" and path.exists() and isinstance(obj, dict) and obj.get("narrative"):
        try:
            previous = path.read_bytes()
            if not json.loads(previous.decode("utf-8-sig")).get("narrative"):
                import hashlib

                backup = path.parent / "backups" / "pre_narrative"
                backup.mkdir(parents=True, exist_ok=True)
                (backup / (hashlib.sha256(previous).hexdigest()[:16] + ".json")).write_bytes(previous)
        except Exception:
            pass
    # ASCII-escaped on purpose: PowerShell 5.1 reads a BOM-less file as ANSI.
    text = json.dumps(obj, indent=indent, sort_keys=sort_keys)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def canonical_map_id(map_id: Optional[str]) -> str:
    """Lower-cased, alias-resolved map id; ``"unknown"`` when empty."""
    if not map_id:
        return "unknown"
    lower = str(map_id).strip().lower()
    return MAP_ALIASES.get(lower, lower)


def edge_score(bounds: Any) -> float:
    """Distance from the map rim in normalized coords (0 = on the edge, 0.5 = dead centre)."""
    if not isinstance(bounds, dict):
        return 0.5
    try:
        xmin = float(bounds.get("xMin", 0) or 0)
        xmax = float(bounds.get("xMax", 1) or 1)
        zmin = float(bounds.get("zMin", 0) or 0)
        zmax = float(bounds.get("zMax", 1) or 1)
    except (TypeError, ValueError):
        return 0.5
    cx = (xmin + xmax) * 0.5
    cz = (zmin + zmax) * 0.5
    return min(cx, 1.0 - cx, cz, 1.0 - cz)


__all__ = [
    "MAP_ALIASES",
    "TOOLS_DIR",
    "WORKSPACE_ROOT",
    "canonical_map_id",
    "clamp",
    "edge_score",
    "load_json",
    "save_json",
    "tools_env",
    "utc_now",
]
