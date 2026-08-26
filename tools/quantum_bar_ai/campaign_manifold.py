"""Campaign-shape umwelt manifold — density membrane over the war, not the player.

Phase 1: expectation vector on design axes (Q0–Q7 style) + path_space width.
Full complex ρ packing is Phase 2.

The campaign membrane owns:
  - world-state axes (faction, schism, zone control, tenebrium, …)
  - mission *solution geometry* (width, viable vectors, win predicates)
  - evolution after mission measurements

Fair rule: the proxy-player manifold never reads this object raw.
Only derived fair fields (briefing text, HUD bands, how_to_win hints) leak out.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from umwelt.spec.schema import BindingSpec, DomainSpec, DriverSpec, NodeSpec

# ---------------------------------------------------------------------------
# η tiers (same house law as yurt_mood / player proxy)
# ---------------------------------------------------------------------------
ETA_CLAIM = 0.25
ETA_WALL = 0.40
ETA_REF = 0.92
WARM_NORM = {"type": "regime", "center": 0.0, "width": 0.5, "invert": True}
GAMMA_SLOW = 0.0005  # campaign mood outlives many missions
GAMMA_MED = 0.002
TICK_S = 60.0  # one "campaign tick" ≈ mission-scale, not combat tick

# Design axes (expectation form of design-doc qubits Q0–Q7)
CAMPAIGN_AXES = (
    "arm_cor",       # Q0 Armada ↔ Cortex  (+1 = Armada weight)
    "schism",        # Q1 internal schism
    "void_struct",   # Q2 Void ↔ Structure
    "bio_cold",      # Q3 Biogenesis ↔ Cold
    "ai_human",      # Q4 AI synthesis ↔ Human sovereignty
    "phi",           # Q5 process-time 0..1 through campaign
    "zone_control",  # Q6 contested ↔ held
    "tenebrium",     # Q7 scarce ↔ abundant (we store "abundance" polarity)
)

PATH_ROLES = (
    "width",             # 0 rail .. 1 open multipath
    "vector_clarity",    # inverse of width feel
    "path_a",            # Armada alignment weight
    "path_b",            # Free-space / ashes-hold weight
    "path_c",            # Void / exit weight
    "multipath_entropy", # diversity of live win paths
)

BIOME_ROLES = ("spot", "wind", "e_penalty", "bp", "atmosphere", "thermal", "stability")
THEATER_ROLES = ("mission_index", "difficulty", "kind_mix", "map_hash")

# Action vectors the solution space may declare viable
VECTOR_POOL = (
    "PUSH_OBJECTIVE",
    "PROBE",
    "FLANK",
    "HOLD_AND_HEAL",
    "RALLY",
    "FALLBACK",
    "EXTRACT",
    "BUILD_MEX",
    "BUILD_ENERGY",
    "BUILD_CON",
    "EXPAND_FRONT",
    "DEFEND_BASE",
    "TECH_UP",
    "RECLAIM",
)

# Win predicates fair_sim may satisfy (any-of when width high)
PREDICATE_POOL = (
    "objective_hold",   # progress + extract classic
    "eco_wreck",        # eco raid complete / eco fat enough
    "lane_hold",        # multi-lane control
    "strike_cut",       # deep strike / relay kill
    "survive_clock",    # live until clock with progress floor
    "siege_break",      # fortified objective cracked
)


@dataclass
class MissionSolutionSpace:
    """Diverging (or narrow) winning geometry for one mission."""

    width: float
    vector_clarity: float
    primary_vectors: list[str] = field(default_factory=list)
    viable_vectors: list[str] = field(default_factory=list)
    win_predicates: list[str] = field(default_factory=list)
    decoy_vectors: list[str] = field(default_factory=list)
    mission_index: int = 0  # 0..14 across full campaign
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_narrow(self) -> bool:
        return self.width < 0.4

    @property
    def is_wide(self) -> bool:
        return self.width >= 0.7


@dataclass
class CampaignRho:
    """Phase-1 density membrane: expectation vector on campaign axes.

    Values in [-1, +1] signed poles (warmth-like). ``phi`` is special: only
    advances forward on mission complete.
    """

    arm_cor: float = 0.54       # mild Armada lean (0.77|ARM| classical → signed)
    schism: float = 0.8         # Taelith-dominant
    void_struct: float = -0.7   # Structure
    bio_cold: float = 0.0
    ai_human: float = 0.1
    phi: float = 0.0            # campaign progress 0..1
    zone_control: float = 0.0   # contested
    tenebrium: float = -0.96    # scarce
    path_a: float = 0.33
    path_b: float = 0.34
    path_c: float = 0.33
    # biome defaults (resolved when theater opens)
    spot: float = 0.0
    wind: float = 0.0
    e_penalty: float = 0.0
    bp: float = 0.0
    atmosphere: float = 0.2
    thermal: float = 0.0
    stability: float = 0.3

    def expectation(self) -> dict[str, float]:
        return {a: float(getattr(self, a)) for a in CAMPAIGN_AXES}

    def path_weights(self) -> dict[str, float]:
        raw = {"a": max(0.0, self.path_a), "b": max(0.0, self.path_b), "c": max(0.0, self.path_c)}
        s = sum(raw.values()) or 1.0
        return {k: v / s for k, v in raw.items()}

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CampaignRho":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: float(v) for k, v in d.items() if k in known})

    def packed_diag(self) -> list[float]:
        """Sparse stand-in for density_matrix_packed: diagonal of classical ρ."""
        # Map signed axes to probabilities on |0⟩/|1⟩ then diag entries.
        out: list[float] = []
        for a in CAMPAIGN_AXES:
            v = max(-1.0, min(1.0, float(getattr(self, a))))
            p1 = (v + 1.0) / 2.0
            out.extend([1.0 - p1, p1])
        return out


def mission_width_curve(mission_index: int, *, n_missions: int = 15) -> float:
    """Early = narrow/clear; late = wide. mission_index 0-based.

    If ``app/brain/craft_width_override.json`` exists (pinned by craft_apply
    after a gym run), use those widths instead of the static curve.
    """
    try:
        from pathlib import Path
        from .suite import _workspace_root
        import json

        p = _workspace_root() / "app" / "brain" / "craft_width_override.json"
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            widths = data.get("widths") or []
            if 0 <= mission_index < len(widths) and widths[mission_index] is not None:
                return float(widths[mission_index])
    except Exception:
        pass
    if n_missions <= 1:
        return 0.5
    t = max(0.0, min(1.0, mission_index / float(n_missions - 1)))
    # Arc-shaped: 0.15 → 0.95 with slight ease-in
    return round(0.15 + 0.80 * (t ** 0.85), 4)


def vector_clarity_from_width(width: float) -> float:
    return round(max(0.05, min(1.0, 1.0 - 0.85 * width)), 4)


def _kind_primary_vectors(kind: str) -> list[str]:
    if kind in ("eco_raid", "strike_relay"):
        return ["PUSH_OBJECTIVE", "FLANK"]
    if kind in ("seize_lane", "hold_plateau"):
        return ["PUSH_OBJECTIVE", "HOLD_AND_HEAL"]
    if kind == "eco_expand":
        return ["BUILD_MEX", "BUILD_ENERGY", "EXPAND_FRONT"]
    if kind == "siege":
        return ["PUSH_OBJECTIVE", "FLANK", "EXPAND_FRONT"]
    if kind == "survive_wilds":
        return ["HOLD_AND_HEAL", "RALLY", "PROBE"]
    if kind == "multipressure":
        return ["PUSH_OBJECTIVE", "EXPAND_FRONT", "DEFEND_BASE"]
    return ["PUSH_OBJECTIVE", "PROBE"]


def _kind_predicates(kind: str, width: float) -> list[str]:
    base: list[str]
    if kind in ("eco_raid",):
        # Combat wreck on converters — not "build your own eco"
        base = ["objective_hold", "eco_wreck"]
    elif kind in ("strike_relay",):
        base = ["strike_cut", "objective_hold"]
    elif kind in ("seize_lane", "hold_plateau"):
        base = ["lane_hold", "objective_hold"]
    elif kind == "eco_expand":
        base = ["eco_wreck", "objective_hold"]
    elif kind == "siege":
        base = ["siege_break", "objective_hold"]
    elif kind == "survive_wilds":
        base = ["survive_clock", "objective_hold"]
    elif kind == "multipressure":
        base = ["eco_wreck", "lane_hold", "strike_cut", "objective_hold"]
    else:
        base = ["objective_hold"]

    if width < 0.35:
        # Early: single bright predicate (first in list)
        return [base[0]] if base else ["objective_hold"]
    if width < 0.55:
        return base[:2] if len(base) >= 2 else base
    if width < 0.75:
        return base[:3] if len(base) >= 3 else base
    return list(base)


def _expand_viable(primary: list[str], kind: str, width: float) -> list[str]:
    viable = list(primary)
    extras_by_width: list[str] = []
    if width >= 0.3:
        extras_by_width += ["PROBE", "RALLY"]
    if width >= 0.45:
        extras_by_width += ["FLANK", "HOLD_AND_HEAL"]
    if width >= 0.55 and kind in ("eco_expand", "siege", "multipressure"):
        extras_by_width += ["BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "EXPAND_FRONT"]
    if width >= 0.7:
        extras_by_width += ["DEFEND_BASE", "FALLBACK", "TECH_UP"]
    if width >= 0.85:
        extras_by_width += ["RECLAIM", "EXTRACT"]
    for a in extras_by_width:
        if a not in viable and a in VECTOR_POOL:
            viable.append(a)
    return viable


def _decoys(kind: str, width: float, viable: list[str]) -> list[str]:
    if width < 0.55:
        return []
    # Look-good-but-wrong late: pure eco on strike, pure extract early, etc.
    candidates = {
        "eco_raid": ["BUILD_MEX", "BUILD_ENERGY", "TECH_UP"],
        "strike_relay": ["BUILD_MEX", "DEFEND_BASE"],
        "seize_lane": ["TECH_UP", "BUILD_MEX"],
        "hold_plateau": ["TECH_UP", "BUILD_ENERGY"],
        "survive_wilds": ["PUSH_OBJECTIVE", "EXPAND_FRONT"],
        "multipressure": [],  # all major lines legit
    }.get(kind, ["TECH_UP"])
    return [c for c in candidates if c not in viable][:2]


def solution_space_for(
    *,
    mission_index: int,
    kind: str,
    n_missions: int = 15,
    rho: CampaignRho | None = None,
) -> MissionSolutionSpace:
    """Build MissionSolutionSpace from index + kind (+ optional ρ bias)."""
    width = mission_width_curve(mission_index, n_missions=n_missions)
    if rho is not None:
        # Contested zones slightly widen; scarce tenebrium narrows eco options.
        width = max(0.1, min(0.98, width + 0.05 * abs(rho.zone_control) - 0.03 * max(0.0, -rho.tenebrium)))
        width = round(width, 4)
    clarity = vector_clarity_from_width(width)
    primary = _kind_primary_vectors(kind)
    viable = _expand_viable(primary, kind, width)
    preds = _kind_predicates(kind, width)
    decoys = _decoys(kind, width, viable)
    notes = (
        f"idx={mission_index} kind={kind} width={width:.2f} clarity={clarity:.2f} "
        f"preds={preds} primary={primary}"
    )
    return MissionSolutionSpace(
        width=width,
        vector_clarity=clarity,
        primary_vectors=primary,
        viable_vectors=viable,
        win_predicates=preds,
        decoy_vectors=decoys,
        mission_index=mission_index,
        notes=notes,
    )


def evolve_rho(
    rho: CampaignRho,
    *,
    won: bool,
    mission_index: int,
    kind: str,
    path_nudge: str | None = None,
    n_missions: int = 15,
) -> CampaignRho:
    """Unitary-ish classical update after a mission measurement."""
    r = CampaignRho(**rho.as_dict())
    # φ only forward
    r.phi = max(r.phi, (mission_index + (1.0 if won else 0.4)) / float(max(1, n_missions)))
    if won:
        r.zone_control = max(-1.0, min(1.0, r.zone_control + 0.08))
        r.tenebrium = max(-1.0, min(1.0, r.tenebrium + 0.04))
        if kind in ("eco_raid", "eco_expand"):
            r.tenebrium = max(-1.0, min(1.0, r.tenebrium + 0.05))
        if kind in ("siege", "multipressure"):
            r.arm_cor = max(-1.0, min(1.0, r.arm_cor + 0.04))
    else:
        r.zone_control = max(-1.0, min(1.0, r.zone_control - 0.06))
        r.arm_cor = max(-1.0, min(1.0, r.arm_cor - 0.03))

    nudge = (path_nudge or "").lower()
    if nudge in ("a", "path_a", "armada"):
        r.path_a += 0.08
        r.path_b -= 0.03
        r.path_c -= 0.03
    elif nudge in ("b", "path_b", "free", "ashes"):
        r.path_b += 0.08
        r.path_a -= 0.03
        r.path_c -= 0.03
    elif nudge in ("c", "path_c", "void"):
        r.path_c += 0.08
        r.path_a -= 0.03
        r.path_b -= 0.03
        r.void_struct = max(-1.0, min(1.0, r.void_struct + 0.05))
    # renormalize soft path weights
    pw = r.path_weights()
    r.path_a, r.path_b, r.path_c = pw["a"], pw["b"], pw["c"]
    return r


def deembed_disposition(rho: CampaignRho) -> dict[str, float]:
    """AI disposition from partial trace of ρ (design §5)."""
    return {
        "eco_aggression": max(0.0, min(1.0, 0.5 + 0.25 * rho.arm_cor + 0.2 * rho.tenebrium)),
        "military_aggression": max(0.0, min(1.0, 0.45 + 0.3 * rho.arm_cor - 0.15 * rho.zone_control)),
        "expansion_target": max(0.0, min(1.0, 0.4 + 0.3 * (1.0 - abs(rho.zone_control)))),
        "fortify_bias": max(0.0, min(1.0, 0.35 - 0.25 * rho.arm_cor + 0.2 * rho.schism)),
        "swarm_bias": max(0.0, min(1.0, 0.4 + 0.35 * rho.schism)),
    }


def disposition_from_density(rho: CampaignRho, density: Any | None = None) -> dict[str, float]:
    """Disposition = classical deembed ⊗ path-coherence Kraus channel.

    High path coherence → more coordinated (less swarm chaos).
    High path entropy → multipath pressure (more expansion targets).
    """
    d = deembed_disposition(rho)
    if density is None:
        return d
    try:
        coh = float(density.coherence())
        ent = float(density.width_from_entropy())
        pur = float(density.purity)
    except Exception:
        return d
    d["military_aggression"] = max(0.0, min(1.0, d["military_aggression"] * (0.85 + 0.3 * coh)))
    d["swarm_bias"] = max(0.0, min(1.0, d["swarm_bias"] * (1.15 - 0.4 * pur)))
    d["expansion_target"] = max(0.0, min(1.0, d["expansion_target"] * (0.8 + 0.4 * ent)))
    d["fortify_bias"] = max(0.0, min(1.0, d["fortify_bias"] * (0.9 + 0.25 * (1.0 - coh))))
    d["path_coherence"] = coh
    d["path_entropy"] = ent
    return d


# ---------------------------------------------------------------------------
# Umwelt DomainSpec — campaign shape membrane
# ---------------------------------------------------------------------------

def campaign_shape_spec(*, name: str = "verdance-campaign-shape") -> DomainSpec:
    nodes: list[NodeSpec] = [
        NodeSpec(
            "campaign",
            parent=None,
            kind="root",
            roles=CAMPAIGN_AXES,
            role_modes={a: "dissipative" for a in CAMPAIGN_AXES},
            params={"gamma_diss": (GAMMA_SLOW, 0.0001, 0.0, 1.0)},
        ),
        NodeSpec(
            "path_space",
            parent="campaign",
            roles=PATH_ROLES,
            role_modes={r: "dissipative" for r in PATH_ROLES},
            params={"gamma_diss": (GAMMA_MED, 0.0001, 0.0, 1.0)},
        ),
        NodeSpec(
            "biome",
            parent="campaign",
            roles=BIOME_ROLES,
            role_modes={r: "dissipative" for r in BIOME_ROLES},
            params={"gamma_diss": (GAMMA_MED, 0.0001, 0.0, 1.0)},
        ),
        NodeSpec(
            "theater",
            parent="campaign",
            roles=THEATER_ROLES,
            role_modes={r: "dissipative" for r in THEATER_ROLES},
            params={"gamma_diss": (GAMMA_MED, 0.0001, 0.0, 1.0)},
        ),
    ]
    bindings: list[BindingSpec] = []
    for axis in CAMPAIGN_AXES:
        for tier, eta in (("claim", ETA_CLAIM), ("wall", ETA_WALL), ("referee", ETA_REF)):
            bindings.append(
                BindingSpec(
                    f"campaign_{axis}_{tier}",
                    zone="campaign",
                    role=axis,
                    normalizer=WARM_NORM,
                    force_observe=True,
                    collapse_alpha=eta,
                    description=f"{tier} on campaign {axis}",
                )
            )
    for role in PATH_ROLES:
        for tier, eta in (("wall", ETA_WALL), ("referee", ETA_REF)):
            bindings.append(
                BindingSpec(
                    f"path_{role}_{tier}",
                    zone="path_space",
                    role=role,
                    normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                    force_observe=True,
                    collapse_alpha=eta,
                    description=f"path_space {role} {tier}",
                )
            )
    for role in BIOME_ROLES:
        bindings.append(
            BindingSpec(
                f"biome_{role}_wall",
                zone="biome",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_WALL,
                description=f"biome {role}",
            )
        )
    for role in THEATER_ROLES:
        bindings.append(
            BindingSpec(
                f"theater_{role}_wall",
                zone="theater",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_WALL,
                description=f"theater {role}",
            )
        )
    return DomainSpec(
        name=name,
        nodes=tuple(nodes),
        bridges=(),
        bindings=tuple(bindings),
        outputs=(),
        drivers=(DriverSpec("tick", node="_clock", role="phase", period_s=TICK_S),),
        anchors={},
        ingest_hold_s=TICK_S,
    )


CAMPAIGN_SPEC = campaign_shape_spec()


def attach_solution_spaces(
    missions: list[Any],
    *,
    rho: CampaignRho | None = None,
    n_missions: int | None = None,
) -> list[Any]:
    """Mutate/return ArcMissions with solution_space filled (by list order)."""
    n = n_missions if n_missions is not None else len(missions)
    rho = rho or CampaignRho()
    for i, m in enumerate(missions):
        kind = getattr(m, "kind", None) or getattr(getattr(m, "card", None), "kind", "eco_raid")
        ss = solution_space_for(mission_index=i, kind=str(kind), n_missions=n, rho=rho)
        if hasattr(m, "solution_space"):
            m.solution_space = ss
        else:
            try:
                object.__setattr__(m, "solution_space", ss)
            except Exception:
                pass
    return missions
