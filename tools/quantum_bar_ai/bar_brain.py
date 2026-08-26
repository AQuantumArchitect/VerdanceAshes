"""Super quantum BAR brain — umwelt field + manifold priors + campaign scars.

Trains from fair-campaign tapes (action histograms conditioned on HUD/eco bands)
and manifold ROI priors so the same seat can play:
  - Verdance proxy campaign (via LocalToolAgent / ant)
  - Normal BAR games (eco + build + army) via bar_map seat plan + future Lua

Weights live in app/brain/bar_brain_weights.json (operator room).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .eco_manifold import MANIFOLD_NOTES, EcoState, recommend_build
from .mood import MoodSnapshot
from .policy import ACTIONS, Decision, decide
from .suite import _workspace_root


DEFAULT_WEIGHTS_PATH = Path("app") / "brain" / "bar_brain_weights.json"

# Context keys used for conditional action weights
CONTEXT_KEYS = (
    "phase",
    "contact",
    "obj",
    "eco",
    "kind_family",
    "width_band",
    "lane_band",
)


def _kind_family(kind: str) -> str:
    if kind in ("eco_raid", "strike_relay"):
        return "strike"
    if kind in ("eco_expand",):
        return "eco"
    if kind in ("siege",):
        return "siege"
    if kind in ("survive_wilds",):
        return "wilds"
    if kind in ("seize_lane", "hold_plateau", "multipressure"):
        return "hold"
    return "general"


def _band_bucket(hud: dict[str, Any] | None, eco_level: float | None = None) -> str:
    hud = hud or {}
    eco = hud.get("eco_feel") or "n/a"
    if eco == "n/a" and eco_level is not None:
        if eco_level < 0.25:
            eco = "dry"
        elif eco_level < 0.45:
            eco = "thin"
        elif eco_level < 0.7:
            eco = "steady"
        else:
            eco = "fat"
    return "|".join(
        [
            str(hud.get("phase") or "APPROACH"),
            str(hud.get("contact") or "none"),
            str(hud.get("objective_bar") or "empty"),
            str(eco),
        ]
    )


@dataclass
class BarBrainWeights:
    """Action preference tables learned from campaign + manifold priors."""

    version: str = "0.3"
    samples: int = 0
    wins: int = 0
    losses: int = 0
    # global action prior
    action_counts: dict[str, float] = field(default_factory=dict)
    # context → action counts
    context_action: dict[str, dict[str, float]] = field(default_factory=dict)
    # kind_family → action counts
    kind_action: dict[str, dict[str, float]] = field(default_factory=dict)
    # eco band → preferred build
    eco_action: dict[str, dict[str, float]] = field(default_factory=dict)
    # width_band (narrow|open|wide) → action counts  [quantum solution geometry]
    width_action: dict[str, dict[str, float]] = field(default_factory=dict)
    # lane_band (none|solid|ragged|broken) → action counts
    lane_action: dict[str, dict[str, float]] = field(default_factory=dict)
    manifold_notes: str = MANIFOLD_NOTES
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BarBrainWeights":
        return cls(
            version=str(d.get("version") or "0.3"),
            samples=int(d.get("samples") or 0),
            wins=int(d.get("wins") or 0),
            losses=int(d.get("losses") or 0),
            action_counts=dict(d.get("action_counts") or {}),
            context_action={k: dict(v) for k, v in (d.get("context_action") or {}).items()},
            kind_action={k: dict(v) for k, v in (d.get("kind_action") or {}).items()},
            eco_action={k: dict(v) for k, v in (d.get("eco_action") or {}).items()},
            width_action={k: dict(v) for k, v in (d.get("width_action") or {}).items()},
            lane_action={k: dict(v) for k, v in (d.get("lane_action") or {}).items()},
            manifold_notes=str(d.get("manifold_notes") or MANIFOLD_NOTES),
            updated_at=str(d.get("updated_at") or ""),
        )


def weights_path(workspace: Path | None = None) -> Path:
    ws = workspace or _workspace_root()
    return ws / DEFAULT_WEIGHTS_PATH


def load_weights(path: Path | None = None) -> BarBrainWeights:
    p = path or weights_path()
    if not p.is_file():
        return seed_manifold_priors()
    try:
        return BarBrainWeights.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return seed_manifold_priors()


def save_weights(w: BarBrainWeights, path: Path | None = None) -> Path:
    p = path or weights_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    w.updated_at = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(w.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def seed_manifold_priors() -> BarBrainWeights:
    """Bootstrap from eco manifold ROI logic before any campaign tapes."""
    w = BarBrainWeights(samples=0)
    # mild global combat defaults
    for a, c in (
        ("PUSH_OBJECTIVE", 3.0),
        ("FLANK", 2.0),
        ("PROBE", 1.5),
        ("HOLD_AND_HEAL", 1.5),
        ("BUILD_ENERGY", 2.0),
        ("BUILD_MEX", 2.0),
        ("BUILD_CON", 1.2),
        ("EXPAND_FRONT", 1.5),
        ("EXTRACT", 1.0),
    ):
        w.action_counts[a] = c
    # eco band priors (manifold)
    w.eco_action["dry"] = {"BUILD_ENERGY": 4.0, "BUILD_MEX": 3.0, "BUILD_CON": 1.0}
    w.eco_action["thin"] = {"BUILD_ENERGY": 2.5, "BUILD_MEX": 2.5, "EXPAND_FRONT": 1.5}
    w.eco_action["steady"] = {"EXPAND_FRONT": 2.0, "PUSH_OBJECTIVE": 2.0, "BUILD_CON": 1.0}
    w.eco_action["fat"] = {"PUSH_OBJECTIVE": 3.0, "TECH_UP": 1.5, "FLANK": 1.5}
    w.kind_action["eco"] = {"BUILD_ENERGY": 3.0, "BUILD_MEX": 3.0, "EXPAND_FRONT": 2.0}
    w.kind_action["siege"] = {"BUILD_ENERGY": 2.0, "PUSH_OBJECTIVE": 2.5, "FLANK": 2.0}
    w.kind_action["wilds"] = {"RALLY": 3.0, "HOLD_AND_HEAL": 2.0, "PROBE": 2.0}
    w.kind_action["strike"] = {"PUSH_OBJECTIVE": 3.0, "FLANK": 2.5, "PROBE": 1.5}
    w.kind_action["hold"] = {"HOLD_AND_HEAL": 2.0, "PUSH_OBJECTIVE": 2.5, "FLANK": 1.5}
    # width_band priors — early narrow: clear push; late wide: multipath
    w.width_action["narrow"] = {
        "PUSH_OBJECTIVE": 4.0,
        "FLANK": 2.0,
        "PROBE": 1.5,
        "HOLD_AND_HEAL": 1.2,
    }
    w.width_action["open"] = {
        "PUSH_OBJECTIVE": 2.5,
        "FLANK": 2.5,
        "EXPAND_FRONT": 2.0,
        "HOLD_AND_HEAL": 1.5,
        "BUILD_ENERGY": 1.2,
    }
    w.width_action["wide"] = {
        "PUSH_OBJECTIVE": 2.0,
        "FLANK": 2.0,
        "EXPAND_FRONT": 2.2,
        "BUILD_MEX": 1.5,
        "BUILD_ENERGY": 1.5,
        "DEFEND_BASE": 1.5,
        "RALLY": 1.2,
        "TECH_UP": 1.0,
    }
    # lane front feel
    w.lane_action["solid"] = {"PUSH_OBJECTIVE": 3.0, "EXPAND_FRONT": 2.0, "FLANK": 1.5}
    w.lane_action["ragged"] = {"HOLD_AND_HEAL": 3.0, "RALLY": 2.5, "DEFEND_BASE": 2.0}
    w.lane_action["broken"] = {"RALLY": 3.0, "FALLBACK": 2.0, "HOLD_AND_HEAL": 2.5}
    w.lane_action["none"] = {}
    return w


def _width_band_from_card(card: dict[str, Any] | None) -> str:
    card = card or {}
    wb = card.get("width_band")
    if wb in ("narrow", "open", "wide"):
        return str(wb)
    return "open"


def _lane_band_from_tape_row(row: dict[str, Any]) -> str:
    truth = row.get("_truth") or {}
    bands = truth.get("lane_bands") or {}
    front = bands.get("front") if isinstance(bands, dict) else None
    if front in ("solid", "ragged", "broken"):
        return str(front)
    return "none"


def ingest_campaign_report(report: dict[str, Any], weights: BarBrainWeights | None = None) -> BarBrainWeights:
    """Train weights from a fair campaign / arc report (results[].tape)."""
    w = weights or load_weights()
    results = report.get("results") or []
    for res in results:
        won = bool(res.get("won"))
        if won:
            w.wins += 1
        else:
            w.losses += 1
        card = res.get("player_card") or {}
        kind = card.get("kind") or "eco_raid"
        fam = _kind_family(kind)
        width_band = _width_band_from_card(card)
        scale = 1.35 if won else 0.55
        tape = res.get("tape") or []
        for row in tape:
            action = row.get("action") or "WAIT"
            if action not in ACTIONS:
                continue
            w.samples += 1
            w.action_counts[action] = w.action_counts.get(action, 0.0) + scale
            ka = w.kind_action.setdefault(fam, {})
            ka[action] = ka.get(action, 0.0) + scale
            ctx = _band_bucket(row.get("hud"), (row.get("_truth") or {}).get("eco"))
            ca = w.context_action.setdefault(ctx, {})
            ca[action] = ca.get(action, 0.0) + scale
            eco = (row.get("hud") or {}).get("eco_feel") or "n/a"
            if eco != "n/a":
                ea = w.eco_action.setdefault(eco, {})
                ea[action] = ea.get(action, 0.0) + scale
            wa = w.width_action.setdefault(width_band, {})
            wa[action] = wa.get(action, 0.0) + scale
            lb = _lane_band_from_tape_row(row)
            if lb != "none":
                la = w.lane_action.setdefault(lb, {})
                la[action] = la.get(action, 0.0) + scale
    return w


def bias_from_weights(
    weights: BarBrainWeights,
    *,
    kind: str,
    hud: dict[str, Any] | None = None,
    width_band: str | None = None,
    lane_band: str | None = None,
) -> dict[str, float]:
    """Normalized action scores for this context (higher = preferred)."""
    scores: dict[str, float] = {a: 0.1 for a in ACTIONS}
    for a, c in weights.action_counts.items():
        scores[a] = scores.get(a, 0.0) + float(c) * 0.3
    fam = _kind_family(kind)
    for a, c in (weights.kind_action.get(fam) or {}).items():
        scores[a] = scores.get(a, 0.0) + float(c) * 0.8
    if hud:
        ctx = _band_bucket(hud)
        for a, c in (weights.context_action.get(ctx) or {}).items():
            scores[a] = scores.get(a, 0.0) + float(c) * 1.2
        eco = hud.get("eco_feel") or "n/a"
        for a, c in (weights.eco_action.get(eco) or {}).items():
            scores[a] = scores.get(a, 0.0) + float(c) * 1.0
        # fair width band may ride on hud extras from player_view
        if width_band is None:
            width_band = hud.get("width_band")  # type: ignore[assignment]
        if lane_band is None:
            lane_band = hud.get("lane_band")  # type: ignore[assignment]
    wb = width_band if width_band in ("narrow", "open", "wide") else None
    if wb:
        for a, c in (weights.width_action.get(wb) or {}).items():
            scores[a] = scores.get(a, 0.0) + float(c) * 0.9
    lb = lane_band if lane_band in ("solid", "ragged", "broken") else None
    if lb:
        for a, c in (weights.lane_action.get(lb) or {}).items():
            scores[a] = scores.get(a, 0.0) + float(c) * 0.85
    # normalize
    total = sum(scores.values()) or 1.0
    return {a: v / total for a, v in scores.items()}


class BarBrain:
    """Trained brain that can overlay LocalToolAgent decisions or run standalone."""

    name = "bar_brain"

    def __init__(self, weights: BarBrainWeights | None = None):
        self.weights = weights or load_weights()

    def decide_overlay(
        self,
        base: Decision,
        *,
        mood: MoodSnapshot,
        kind: str,
        hud: dict[str, Any] | None = None,
        allow_eco: bool = False,
        recent: list[str] | None = None,
    ) -> Decision:
        """Blend policy decision with learned biases (never overrides survival)."""
        if base.action in ("FALLBACK", "EXTRACT") and base.confidence >= 0.8:
            return base
        if mood.hero_vane_alive < 0.35 or mood.hero_ketha_alive < 0.35:
            return base

        scores = bias_from_weights(self.weights, kind=kind, hud=hud)
        # boost base action
        scores[base.action] = scores.get(base.action, 0.0) + 0.35 * base.confidence

        # manifold eco inject when dry
        if allow_eco and hud:
            eco_feel = hud.get("eco_feel") or "n/a"
            if eco_feel in ("dry", "thin") and (hud.get("contact") or "none") in (
                "none",
                "light",
                "moderate",
            ):
                eco = EcoState(
                    metal_income=0.2 if hud.get("metal_feel") == "thin" else 0.1,
                    energy_income=0.2 if hud.get("energy_feel") == "thin" else 0.1,
                    buildpower=0.2,
                )
                rec = recommend_build(eco, no_metal_map="converter" in str(hud).lower())
                scores[rec] = scores.get(rec, 0.0) + 0.25

        best = max(scores.items(), key=lambda kv: kv[1])
        if best[0] == base.action or best[1] < scores.get(base.action, 0) + 0.05:
            return base
        return Decision(
            best[0],
            f"bar_brain overlay: {base.action}→{best[0]} ({best[1]:.2f})",
            source="bar_brain",
            confidence=min(0.85, 0.5 + best[1]),
        )

    def bar_seat_hint(self, *, kind: str = "eco_raid", hud: dict[str, Any] | None = None) -> dict[str, Any]:
        """Hints for normal BAR games / headless controller selection."""
        scores = bias_from_weights(self.weights, kind=kind, hud=hud)
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:5]
        pushy = sum(scores.get(a, 0) for a in ("PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT"))
        ecoey = sum(scores.get(a, 0) for a in ("BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "TECH_UP"))
        if (ecoey > pushy and kind in ("eco_expand", "siege")) or ecoey > 0.35:
            controller = "simple"  # grow first
            style = "eco_first"
        elif pushy > 0.4:
            controller = "barbarian_aggressive"
            style = "pressure"
        else:
            controller = "simple"
            style = "balanced"
        return {
            "player_controller": controller,
            "style": style,
            "top_actions": top,
            "pushy": round(pushy, 3),
            "ecoey": round(ecoey, 3),
            "samples": self.weights.samples,
            "win_rate": round(
                self.weights.wins / max(1, self.weights.wins + self.weights.losses), 3
            ),
            "manifold": MANIFOLD_NOTES[:120],
        }


def train_from_report_file(report_path: Path, *, save: bool = True) -> BarBrainWeights:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # unwrap beat reports
    if "results" not in report and report.get("champion"):
        runs = (report.get("champion") or {}).get("runs") or report.get("history_tail", [{}])[-1].get("runs") or []
        if runs:
            report = runs[0]
    w = ingest_campaign_report(report, load_weights())
    if save:
        save_weights(w)
    return w
