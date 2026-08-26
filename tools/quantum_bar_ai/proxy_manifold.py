"""Proxy-player umwelt manifold facade — information-limited campaign agent.

This is Manifold A: what the proxy *believes* from briefing + FairHUD + wall
telemetry. It never loads campaign ρ or lane referee ground truth into the
agent view.

Canonical DomainSpec lives in ``world.PROXY_SPEC`` / ``bar_brain_world``.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .mood import MoodSnapshot, pack_claim_sensors, pack_wall_sensors, read_mood
from .world import (
    AXES,
    ETA_CLAIM,
    ETA_REF,
    ETA_WALL,
    PROXY_SPEC,
    player_proxy_spec,
)

try:
    from .bar_brain_world import bar_brain_spec, ECO_ROLES
except Exception:  # pragma: no cover
    bar_brain_spec = None  # type: ignore
    ECO_ROLES = ()


FAIR_VIEW_KEYS = (
    "phase",
    "contact",
    "objective_bar",
    "eco_feel",
    "clock_band",
    "hero_tags",
    "last_outcome",
)


@dataclass
class FairProxyView:
    """Everything the proxy is allowed to condition on (no ρ, no exact enemy)."""

    mission_id: str
    kind: str
    briefing: str
    hud: dict[str, Any]
    mood: dict[str, Any]
    recent_actions: list[str]
    # fair-only solution hints (width as band, not full predicates)
    width_band: str = "narrow"  # narrow | open | wide
    primary_hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def width_to_band(width: float) -> str:
    if width < 0.4:
        return "narrow"
    if width < 0.7:
        return "open"
    return "wide"


def proxy_spec(*, with_eco: bool = False, name: str | None = None):
    """Return DomainSpec for the proxy seat."""
    if with_eco and bar_brain_spec is not None:
        return bar_brain_spec(name=name or "verdance-bar-brain")
    return player_proxy_spec(name=name or "verdance-player-proxy")


def load_proxy_spec(*, with_eco: bool = False):
    return proxy_spec(with_eco=with_eco)


def fair_view_from_tick(
    *,
    mission_id: str,
    kind: str,
    briefing: str,
    hud: dict[str, Any] | None,
    mood: MoodSnapshot,
    recent: list[str] | None = None,
    width: float | None = None,
    primary_vectors: list[str] | None = None,
) -> FairProxyView:
    """Build a fair agent view. Strips any forbidden keys from hud if present."""
    hud = dict(hud or {})
    for bad in ("enemy_scale", "enemy_strength_exact", "rho", "win_predicates", "_truth"):
        hud.pop(bad, None)
    wb = width_to_band(float(width)) if width is not None else "narrow"
    hint = ""
    if primary_vectors:
        hint = primary_vectors[0]
    return FairProxyView(
        mission_id=mission_id,
        kind=kind,
        briefing=briefing,
        hud={k: hud[k] for k in hud if not str(k).startswith("_")},
        mood=mood.as_dict(),
        recent_actions=list(recent or [])[-8:],
        width_band=wb,
        primary_hint=hint,
    )


def claim_from_action(action: str, mood: MoodSnapshot) -> dict[str, float]:
    return pack_claim_sensors(action, mood)


def walls_from_fair_sensors(sensors: dict[str, float]) -> dict[str, float]:
    """Pass-through helper: only wall-tier keys should be posted to proxy."""
    return {k: v for k, v in sensors.items() if k.endswith("_wall") or "wall" in k}


def proxy_manifest() -> dict[str, Any]:
    return {
        "name": PROXY_SPEC.name,
        "axes": list(AXES),
        "eta": {"claim": ETA_CLAIM, "wall": ETA_WALL, "referee": ETA_REF},
        "nodes": [n.name if hasattr(n, "name") else str(n) for n in PROXY_SPEC.nodes],
        "bindings": len(PROXY_SPEC.bindings),
        "fair_rule": "proxy never reads campaign rho or lane referee ground truth",
        "eco_roles": list(ECO_ROLES) if ECO_ROLES else [],
    }


def snapshot_engine(engine, turn: int = 0) -> MoodSnapshot:
    return read_mood(engine, turn=turn)
