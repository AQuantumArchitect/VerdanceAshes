#!/usr/bin/env python3
"""Champion craft recipe → live campaign (fair sim + BAR seed path).

Usage:
  python -m quantum_bar_ai.craft_apply --show
  python -m quantum_bar_ai.craft_apply --pin          # width curve pin
  python -m quantum_bar_ai.craft_apply --roll-in      # pin + stamp campaign state
  python -m quantum_bar_ai.craft_apply --verify       # smoke: craft stamps 15 missions
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .suite import _workspace_root


def recipe_path(ws: Path | None = None) -> Path:
    return (ws or _workspace_root()) / "app" / "brain" / "craft_recipe.json"


def override_path(ws: Path | None = None) -> Path:
    return (ws or _workspace_root()) / "app" / "brain" / "craft_width_override.json"


def campaign_craft_path(ws: Path | None = None) -> Path:
    """Live stamp consumed by BAR mission compiler + dev launch."""
    return (ws or _workspace_root()) / "app" / "brain" / "campaign_craft.json"


def load_recipe(ws: Path | None = None) -> dict:
    p = recipe_path(ws)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def has_recipe(ws: Path | None = None) -> bool:
    r = load_recipe(ws)
    return bool(r.get("knobs"))


# ---------------------------------------------------------------------------
# Craft knobs (shared with manifold_gym)
# ---------------------------------------------------------------------------

@dataclass
class CraftKnobs:
    """What the campaign-shape side is allowed to retune between gens."""

    difficulty: float = 1.0
    width_early: float = 0.15
    width_late: float = 0.95
    width_ease: float = 0.85
    decoy_pressure: float = 1.0
    enemy_aggro: float = 1.0
    lane_bias: float = 1.0
    path_purity_target: float = 0.7
    arc1_scale: float = 0.92
    arc2_scale: float = 1.0
    arc3_scale: float = 1.08

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CraftKnobs":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        base = cls()
        out: dict[str, Any] = {}
        for k in known:
            if k in d:
                out[k] = type(getattr(base, k))(d[k])
        return cls(**out)


def knobs_from_recipe(ws: Path | None = None, recipe: dict | None = None) -> CraftKnobs | None:
    recipe = recipe if recipe is not None else load_recipe(ws)
    knobs = recipe.get("knobs") or {}
    if not knobs:
        return None
    return CraftKnobs.from_dict(knobs)


def recipe_difficulty(default: float = 1.0, ws: Path | None = None) -> float:
    k = knobs_from_recipe(ws)
    if k is None:
        return float(default)
    return float(k.difficulty)


def knobs_width(mission_index: int, knobs: CraftKnobs, *, n: int = 15) -> float:
    if n <= 1:
        return 0.5
    t = max(0.0, min(1.0, mission_index / float(n - 1)))
    w = knobs.width_early + (knobs.width_late - knobs.width_early) * (t ** knobs.width_ease)
    return round(max(0.08, min(0.98, w)), 4)


def knobs_width_from_recipe(mission_index: int, recipe: dict | None = None, *, n: int = 15) -> float | None:
    """Return crafted width or None if no recipe knobs."""
    recipe = recipe if recipe is not None else load_recipe()
    knobs = knobs_from_recipe(recipe=recipe)
    if knobs is None:
        return None
    return knobs_width(mission_index, knobs, n=n)


def arc_scale_for_index(index: int, knobs: CraftKnobs) -> float:
    if index < 5:
        return float(knobs.arc1_scale)
    if index < 10:
        return float(knobs.arc2_scale)
    return float(knobs.arc3_scale)


def arc_scale_for_mission_number(mission_number: int, knobs: CraftKnobs) -> float:
    """1-based mission numbers (va_001 → 1)."""
    return arc_scale_for_index(max(0, int(mission_number) - 1), knobs)


def pin_override(ws: Path | None = None) -> Path:
    ws = ws or _workspace_root()
    recipe = load_recipe(ws)
    widths = [knobs_width_from_recipe(i, recipe) for i in range(15)]
    out = {
        "schemaVersion": "craft-width-override/0.1",
        "source_recipe": recipe.get("stamp"),
        "knobs": recipe.get("knobs"),
        "widths": widths,
        "notes": "Consumed by campaign_manifold if present (optional pin after gym).",
    }
    p = override_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return p


def write_campaign_craft(ws: Path | None = None) -> Path:
    """Write app/brain/campaign_craft.json — BAR compiler + fair sim share this."""
    ws = ws or _workspace_root()
    recipe = load_recipe(ws)
    knobs = knobs_from_recipe(ws, recipe) or CraftKnobs()
    widths = [knobs_width(i, knobs) for i in range(15)]
    out = {
        "schemaVersion": "verdance-campaign-craft/0.1",
        "active": bool(recipe.get("knobs")),
        "source": recipe.get("source") or "craft_recipe",
        "stamp": recipe.get("stamp"),
        "craft_score": recipe.get("craft_score"),
        "arc_rates": recipe.get("arc_rates"),
        "overall_win_rate": recipe.get("overall_win_rate"),
        "knobs": knobs.as_dict(),
        "widths": widths,
        "notes": (
            "Champion craft rolled into live campaign. Fair sim stamps solution_space + "
            "truth via craft_mission; BAR mission compiler multiplies enemyScale by "
            "enemy_aggro × per-arc scale."
        ),
    }
    p = campaign_craft_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return p


def sync_campaign_state_dial(ws: Path | None = None) -> dict[str, Any]:
    """Push recipe difficulty into state/campaign_state.json progression dial."""
    ws = ws or _workspace_root()
    knobs = knobs_from_recipe(ws)
    state_path = ws / "state" / "campaign_state.json"
    if not state_path.is_file() or knobs is None:
        return {"ok": False, "reason": "no_state_or_recipe"}
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    prog = state.setdefault("progression", {})
    if not isinstance(prog, dict):
        prog = {}
        state["progression"] = prog
    # Clamp matches story engine ensure_progression (0.7–1.35)
    dial = max(0.7, min(1.35, float(knobs.difficulty)))
    old = prog.get("difficultyDial")
    prog["difficultyDial"] = round(dial, 3)
    prog["craftStamp"] = load_recipe(ws).get("stamp")
    prog["craftSource"] = "overnight_champion"
    state["craft"] = {
        "stamp": load_recipe(ws).get("stamp"),
        "knobs": knobs.as_dict(),
        "rolledIn": True,
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "path": str(state_path), "old_dial": old, "difficultyDial": dial}


def craft_mission(
    m: Any,
    index: int,
    knobs: CraftKnobs,
    rho: Any,
    density: Any,
    *,
    n_missions: int = 15,
) -> Any:
    """Re-stamp solution_space + lane geometry + truth scale from knobs."""
    from .campaign_manifold import (
        _decoys,
        _expand_viable,
        _kind_predicates,
        _kind_primary_vectors,
        solution_space_for,
        vector_clarity_from_width,
    )
    from .lane_war import geometry_for_map
    from .quantum_membrane import solution_entropy_width
    from .schism_entangle import widen_solution_for_schism

    kind = m.kind
    width = knobs_width(index, knobs, n=n_missions)
    # density entropy pulls width slightly
    try:
        ent_pull = density.width_from_entropy()
    except Exception:
        ent_pull = 0.5
    width = max(0.1, min(0.98, width + 0.06 * (float(ent_pull) - 0.5)))
    width = round(width, 4)

    ss = solution_space_for(mission_index=index, kind=kind, n_missions=n_missions, rho=rho)
    ss.width = width
    ss.vector_clarity = vector_clarity_from_width(width)
    primary = _kind_primary_vectors(kind)
    ss.primary_vectors = primary
    ss.viable_vectors = _expand_viable(primary, kind, width)
    ss.win_predicates = _kind_predicates(kind, width)
    decoys = _decoys(kind, width, ss.viable_vectors)
    if knobs.decoy_pressure < 0.5:
        decoys = []
    elif knobs.decoy_pressure > 1.2 and width >= 0.55:
        extra = ["TECH_UP", "RECLAIM"]
        for e in extra:
            if e not in ss.viable_vectors and e not in decoys:
                decoys.append(e)
    ss.decoy_vectors = decoys[:3]
    ss = widen_solution_for_schism(ss, rho, kind=kind)
    ent_w = solution_entropy_width(ss.viable_vectors, ss.primary_vectors)
    ss.notes = (
        f"craft idx={index} kind={kind} width={ss.width:.2f} ent_w={ent_w:.2f} "
        f"preds={ss.win_predicates} decoys={ss.decoy_vectors}"
    )
    m.solution_space = ss

    arc_s = arc_scale_for_index(index, knobs)
    arc_ramp = 1.0 + 0.03 * max(0, index - 4)
    m.truth.enemy_scale = max(
        0.5,
        min(1.85, float(m.truth.enemy_scale) * knobs.enemy_aggro * arc_s * arc_ramp),
    )
    if index >= 10:
        if knobs.arc3_scale >= 1.1 or (knobs.decoy_pressure >= 1.3 and knobs.enemy_aggro >= 1.15):
            m.truth.fortified = True
        if knobs.arc3_scale >= 1.15:
            tax = min(1.0, knobs.arc3_scale - 1.0)
            m.truth.player_start_strength = max(
                0.48, float(m.truth.player_start_strength) * (1.0 - 0.14 * tax)
            )
            m.truth.enemy_start_strength = min(
                0.9, float(m.truth.enemy_start_strength) * (1.0 + 0.12 * tax)
            )
            m.truth.duration_ticks = max(
                90, int(float(m.truth.duration_ticks) * (1.0 - 0.12 * tax))
            )
            m.truth.enemy_scale = min(1.95, float(m.truth.enemy_scale) * (1.0 + 0.1 * tax))
    if kind in ("siege", "hold_plateau", "multipressure") and knobs.enemy_aggro >= 1.25:
        m.truth.fortified = True
    if index < 2:
        m.truth.fortified = False

    lane_w = width * knobs.lane_bias
    geo = geometry_for_map(m.map_id, width=lane_w)
    if geo is not None and kind in ("seize_lane", "hold_plateau", "multipressure"):
        m.lane_geometry = geo
    return m


def stamp_recipe_on_missions(
    missions: list[Any],
    *,
    knobs: CraftKnobs | None = None,
    rho: Any | None = None,
    density: Any | None = None,
    ws: Path | None = None,
) -> list[Any]:
    """Apply champion (or given) knobs onto an already-enriched mission list."""
    from .campaign_manifold import CampaignRho
    from .quantum_membrane import CampaignDensity

    knobs = knobs or knobs_from_recipe(ws)
    if knobs is None or not missions:
        return missions
    rho = rho or CampaignRho()
    density = density or CampaignDensity()
    n = max(len(missions), 15)
    for i, m in enumerate(missions):
        craft_mission(m, i, knobs, rho, density, n_missions=n)
    return missions


def build_crafted_campaign(
    knobs: CraftKnobs | None = None,
    rho: Any | None = None,
    density: Any | None = None,
    *,
    arcs: tuple[int, ...] = (1, 2, 3),
    difficulty: float | None = None,
) -> list[Any]:
    """Build full campaign already stamped with craft (gym + live share this)."""
    from .campaign import build_full_campaign
    from .campaign_manifold import CampaignRho
    from .quantum_membrane import CampaignDensity

    knobs = knobs or knobs_from_recipe() or CraftKnobs()
    rho = rho or CampaignRho()
    density = density or CampaignDensity()
    d = float(difficulty if difficulty is not None else knobs.difficulty)
    # use_craft=False: we stamp ourselves with the knobs passed in (gym retunes)
    missions = build_full_campaign(difficulty=d, arcs=arcs, use_craft=False)
    return stamp_recipe_on_missions(missions, knobs=knobs, rho=rho, density=density)


def roll_into_campaign(ws: Path | None = None) -> dict[str, Any]:
    """Pin widths, write campaign_craft.json, sync campaign state dial."""
    ws = ws or _workspace_root()
    recipe = load_recipe(ws)
    if not recipe.get("knobs"):
        return {"ok": False, "reason": "no craft_recipe.json knobs"}
    pin = pin_override(ws)
    craft = write_campaign_craft(ws)
    state = sync_campaign_state_dial(ws)
    return {
        "ok": True,
        "recipe_stamp": recipe.get("stamp"),
        "craft_score": recipe.get("craft_score"),
        "knobs": recipe.get("knobs"),
        "width_override": str(pin),
        "campaign_craft": str(craft),
        "state_sync": state,
    }


def verify_craft_stamp(ws: Path | None = None) -> dict[str, Any]:
    """Smoke: build 15 missions with craft and report scales/widths."""
    from .campaign import build_full_campaign

    knobs = knobs_from_recipe(ws)
    if knobs is None:
        return {"ok": False, "reason": "no recipe"}
    missions = build_full_campaign(difficulty=knobs.difficulty, use_craft=True)
    rows = []
    for i, m in enumerate(missions):
        ss = getattr(m, "solution_space", None)
        rows.append(
            {
                "id": m.id,
                "kind": m.kind,
                "width": getattr(ss, "width", None),
                "enemy_scale": round(float(m.truth.enemy_scale), 4),
                "fortified": bool(m.truth.fortified),
                "player_str": round(float(m.truth.player_start_strength), 3),
            }
        )
    return {
        "ok": True,
        "count": len(rows),
        "difficulty": knobs.difficulty,
        "missions": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Champion craft → live campaign")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--pin", action="store_true", help="Write craft_width_override.json")
    ap.add_argument("--roll-in", action="store_true", help="Pin + campaign_craft + state dial")
    ap.add_argument("--verify", action="store_true", help="Smoke stamp 15 missions")
    args = ap.parse_args()
    recipe = load_recipe()
    if args.show or not (args.pin or args.roll_in or args.verify):
        print(json.dumps(recipe, indent=2)[:2000])
        print("widths:", [knobs_width_from_recipe(i, recipe) for i in range(15)])
    if args.pin:
        p = pin_override()
        print("pinned", p)
    if args.roll_in:
        report = roll_into_campaign()
        print(json.dumps(report, indent=2))
        if not report.get("ok"):
            return 1
    if args.verify:
        v = verify_craft_stamp()
        print(json.dumps(v, indent=2)[:4000])
        if not v.get("ok"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
