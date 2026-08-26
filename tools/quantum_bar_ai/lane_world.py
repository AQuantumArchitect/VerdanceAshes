"""Umwelt DomainSpec for line-war lane membrane (verdance-lane-war).

Each lane is an organ under line_war root. Classical sim posts wall sensors;
lane AI posts claims; objective ownership posts referees.
"""
from __future__ import annotations

from umwelt.spec.schema import BindingSpec, DomainSpec, DriverSpec, NodeSpec

ETA_CLAIM = 0.25
ETA_WALL = 0.40
ETA_REF = 0.92
WARM_NORM = {"type": "regime", "center": 0.0, "width": 0.5, "invert": True}
GAMMA_FRONT = 0.004
GAMMA_LANE = 0.01
TICK_S = 5.0

FRONT_ROLES = ("front_coherence", "tempo", "panic", "commit")
LANE_ROLES = (
    "pressure",
    "hold",
    "push",
    "bleed",
    "friendly_mass",
    "enemy_mass",
    "contested",
)


def lane_war_spec(*, lane_count: int = 4, name: str = "verdance-lane-war") -> DomainSpec:
    n = max(1, min(8, int(lane_count)))
    nodes: list[NodeSpec] = [
        NodeSpec(
            "line_war",
            parent=None,
            kind="root",
            roles=FRONT_ROLES,
            role_modes={r: "dissipative" for r in FRONT_ROLES},
            params={"gamma_diss": (GAMMA_FRONT, 0.0001, 0.0, 1.0)},
        ),
    ]
    for i in range(n):
        nodes.append(
            NodeSpec(
                f"lane_{i}",
                parent="line_war",
                roles=LANE_ROLES,
                role_modes={r: "dissipative" for r in LANE_ROLES},
                params={"gamma_diss": (GAMMA_LANE, 0.0001, 0.0, 1.0)},
            )
        )

    bindings: list[BindingSpec] = []
    for role in FRONT_ROLES:
        for tier, eta in (("claim", ETA_CLAIM), ("wall", ETA_WALL), ("referee", ETA_REF)):
            bindings.append(
                BindingSpec(
                    f"front_{role}_{tier}",
                    zone="line_war",
                    role=role,
                    normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                    force_observe=True,
                    collapse_alpha=eta,
                    description=f"front {role} {tier}",
                )
            )
    for i in range(n):
        zone = f"lane_{i}"
        for role in LANE_ROLES:
            for tier, eta in (("claim", ETA_CLAIM), ("wall", ETA_WALL), ("referee", ETA_REF)):
                # enemy_mass referee only — proxy must not get exact enemy via claim path
                if role == "enemy_mass" and tier == "claim":
                    continue
                bindings.append(
                    BindingSpec(
                        f"{zone}_{role}_{tier}",
                        zone=zone,
                        role=role,
                        normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                        force_observe=True,
                        collapse_alpha=eta,
                        description=f"{zone} {role} {tier}",
                    )
                )

    return DomainSpec(
        name=name if n == 4 else f"{name}-{n}",
        nodes=tuple(nodes),
        bridges=(),
        bindings=tuple(bindings),
        outputs=(),
        drivers=(DriverSpec("tick", node="_clock", role="phase", period_s=TICK_S),),
        anchors={},
        ingest_hold_s=TICK_S,
    )


# Default Koom 4-lane membrane
LANE_SPEC = lane_war_spec(lane_count=4)
LANE_SPEC_3 = lane_war_spec(lane_count=3)
LANE_SPEC_5 = lane_war_spec(lane_count=5)


def walls_from_front(front) -> dict[str, float]:
    """Pack LineFront into wall-tier sensor dict for engine.ingest."""
    out: dict[str, float] = {
        "front_front_coherence_wall": float(front.coherence),
        "front_tempo_wall": float(front.tempo),
        "front_panic_wall": float(front.panic),
        "front_commit_wall": float(front.commit),
    }
    for i, L in enumerate(front.lanes):
        z = f"lane_{i}"
        out[f"{z}_pressure_wall"] = L.pressure
        out[f"{z}_hold_wall"] = L.hold
        out[f"{z}_push_wall"] = L.push
        out[f"{z}_bleed_wall"] = L.bleed
        out[f"{z}_friendly_mass_wall"] = L.friendly_mass
        out[f"{z}_enemy_mass_wall"] = L.enemy_mass
        out[f"{z}_contested_wall"] = L.contested
    return out
