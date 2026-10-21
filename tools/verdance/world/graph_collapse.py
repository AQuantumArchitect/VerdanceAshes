#!/usr/bin/env python3
"""Drop-as-collapse helpers — format M(G, result) for hub / stamp / debrief.

Law: docs/archive/GRAPH_COLLAPSE_SSOT.md
Live mutators: verdance.campaign.apply_graph_deltas + measure_graph_from_world
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

# Short labels for hub chips / standing orders
AXIS_LABEL = {
    "q0_armada_cortex": "Armada↔Cortex",
    "q2_void_structure": "void scars",
    "q6_contested": "contested",
    "q6_independent": "independents",
    "q7_resource_scarcity": "scarcity",
    "pathSignalA": "path A",
    "pathSignalB": "path B",
    "pathSignalC": "path C",
}

CANON_AXES = (
    "q0_armada_cortex",
    "q2_void_structure",
    "q6_contested",
    "q6_independent",
    "q7_resource_scarcity",
    "pathSignalA",
    "pathSignalB",
    "pathSignalC",
)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def snapshot_graph(graph: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Full G snapshot for sortie stamp / debrief (not a second SSOT)."""
    g = graph or {}
    out: Dict[str, float] = {}
    for key in CANON_AXES:
        if key in g or key.startswith("pathSignal") or key.startswith("q"):
            out[key] = round(_f(g.get(key)), 4)
    # Include any extra q* keys already present
    for key, val in g.items():
        if key in out:
            continue
        if str(key).startswith("q") or str(key).startswith("pathSignal"):
            out[str(key)] = round(_f(val), 4)
    return out


def format_delta_chip(key: str, delta: float) -> str:
    label = AXIS_LABEL.get(key, key)
    sign = "+" if delta >= 0 else ""
    return f"collapse {label} {sign}{delta:.3f}"


def format_measure_chip(key: str, entry: Any) -> str:
    label = AXIS_LABEL.get(key, key)
    if isinstance(entry, dict):
        if "value" in entry and "target" in entry:
            return f"collapse {label} → {_f(entry['value']):.3f}"
        if "floor" in entry:
            return f"collapse {label} floor {_f(entry['floor']):.3f}"
        if "value" in entry:
            return f"collapse {label} → {_f(entry['value']):.3f}"
    return f"collapse {label} measured"


def collapse_chips(
    graph_delta: Optional[Dict[str, Any]] = None,
    graph_measured: Optional[Dict[str, Any]] = None,
    *,
    max_chips: int = 6,
) -> List[str]:
    """Human-readable chips for debrief.changed / homecoming."""
    chips: List[str] = []
    delta = graph_delta or {}
    # Largest absolute additive deltas first
    ranked: List[Tuple[float, str, float]] = []
    for key, raw in delta.items():
        d = _f(raw)
        if abs(d) < 1e-6:
            continue
        ranked.append((abs(d), str(key), d))
    ranked.sort(reverse=True)
    for _, key, d in ranked:
        chips.append(format_delta_chip(key, d))
        if len(chips) >= max_chips:
            return chips

    measured = graph_measured or {}
    for key, entry in measured.items():
        if key in delta and abs(_f(delta.get(key))) >= 1e-6:
            continue  # already showed additive move
        # Prefer axes that actually eased (target present)
        if isinstance(entry, dict) and ("target" in entry or "floor" in entry or "value" in entry):
            chips.append(format_measure_chip(str(key), entry))
        if len(chips) >= max_chips:
            break
    return chips


def collapse_payload(
    *,
    graph_after: Optional[Dict[str, Any]] = None,
    graph_delta: Optional[Dict[str, Any]] = None,
    graph_measured: Optional[Dict[str, Any]] = None,
    quantum_authoritative: bool = False,
) -> Dict[str, Any]:
    """Structured collapse record for hub_result / advance report."""
    chips = collapse_chips(graph_delta, graph_measured)
    return {
        "schemaVersion": "verdance-graph-collapse/1.0",
        "quantumAuthoritative": bool(quantum_authoritative),
        "delta": {k: round(_f(v), 4) for k, v in (graph_delta or {}).items()},
        "measured": graph_measured or {},
        "graph": snapshot_graph(graph_after),
        "chips": chips,
        "summary": "; ".join(chips[:4]) if chips else "graph steady",
    }


def pressure_brief(graph: Optional[Dict[str, Any]]) -> str:
    """One-line briefing pressure from G for hub / stamp."""
    g = graph or {}
    q6 = _f(g.get("q6_contested"), 0.5)
    q7 = _f(g.get("q7_resource_scarcity"), 0.5)
    q0 = _f(g.get("q0_armada_cortex"), 0.5)
    q2 = _f(g.get("q2_void_structure"), 0.15)
    bits: List[str] = []
    if q6 >= 0.75:
        bits.append("high contest")
    elif q6 <= 0.35:
        bits.append("quiet lanes")
    else:
        bits.append("mixed contest")
    if q7 >= 0.75:
        bits.append("Tnb scarce")
    elif q7 <= 0.4:
        bits.append("stocked")
    if q0 >= 0.65:
        bits.append("Cortex lean")
    elif q0 <= 0.35:
        bits.append("Armada lean")
    if q2 >= 0.35:
        bits.append("void scars")
    return " · ".join(bits) if bits else "world steady"


def character_collapse_chips(state: Optional[Dict[str, Any]], report: Optional[Dict[str, Any]] = None) -> List[str]:
    """H-layer chips for joins. XP/wounds/bonds already ride debrief tokens."""
    chips: List[str] = []
    ar = report or {}
    for j in ar.get("heroJoins") or []:
        if isinstance(j, dict) and j.get("name"):
            chips.append(f"H: {j['name']} joined")
    return chips[:4]
