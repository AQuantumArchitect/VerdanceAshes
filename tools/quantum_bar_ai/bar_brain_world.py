"""Umwelt DomainSpec for a full-BAR quantum brain (eco + combat).

Extends the strike-proxy mood graph with eco organs so campaign tapes
and normal BAR games share one comprehension substrate.

Hive η tiers unchanged: claim 0.25 / wall 0.40 / referee 0.92.
"""
from __future__ import annotations

from umwelt.spec.schema import BindingSpec, DomainSpec, DriverSpec, NodeSpec

from .world import (
    AXES,
    ETA_CLAIM,
    ETA_REF,
    ETA_WALL,
    FORCE_ROLES,
    GAMMA_FAST,
    GAMMA_MOOD,
    HERO_ROLES,
    HEROES,
    MISSION_ROLES,
    TICK_S,
    WARM_NORM,
)

ECO_ROLES = ("metal", "energy", "buildpower", "eco_level", "tech", "stall")


def bar_brain_spec(*, name: str = "verdance-bar-brain") -> DomainSpec:
    """Full BAR seat: proxy mood + mission + force + heroes + eco."""
    nodes: list[NodeSpec] = [
        NodeSpec(
            "proxy",
            parent=None,
            kind="root",
            roles=AXES,
            role_modes={a: "dissipative" for a in AXES},
            params={"gamma_diss": (GAMMA_MOOD, 0.0001, 0.0, 1.0)},
        ),
        NodeSpec(
            "mission",
            parent="proxy",
            roles=MISSION_ROLES,
            role_modes={r: "dissipative" for r in MISSION_ROLES},
            params={"gamma_diss": (GAMMA_FAST, 0.0001, 0.0, 1.0)},
        ),
        NodeSpec(
            "force",
            parent="proxy",
            roles=FORCE_ROLES,
            role_modes={r: "dissipative" for r in FORCE_ROLES},
            params={"gamma_diss": (GAMMA_FAST, 0.0001, 0.0, 1.0)},
        ),
        NodeSpec(
            "eco",
            parent="proxy",
            roles=ECO_ROLES,
            role_modes={r: "dissipative" for r in ECO_ROLES},
            params={"gamma_diss": (GAMMA_FAST, 0.0001, 0.0, 1.0)},
        ),
    ]
    for hero in HEROES:
        nodes.append(
            NodeSpec(
                hero,
                parent="proxy",
                roles=HERO_ROLES,
                role_modes={r: "dissipative" for r in HERO_ROLES},
                params={"gamma_diss": (GAMMA_FAST, 0.0001, 0.0, 1.0)},
            )
        )

    bindings: list[BindingSpec] = []
    for axis in AXES:
        for tier, eta in (("claim", ETA_CLAIM), ("wall", ETA_WALL), ("referee", ETA_REF)):
            bindings.append(
                BindingSpec(
                    f"proxy_{axis}_{tier}",
                    zone="proxy",
                    role=axis,
                    normalizer=WARM_NORM,
                    force_observe=True,
                    collapse_alpha=eta,
                    description=f"{tier} on proxy {axis}",
                )
            )

    for role in MISSION_ROLES:
        for tier, eta in (("wall", ETA_WALL), ("referee", ETA_REF)):
            bindings.append(
                BindingSpec(
                    f"mission_{role}_{tier}",
                    zone="mission",
                    role=role,
                    normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                    force_observe=True,
                    collapse_alpha=eta,
                    description=f"mission {role} {tier}",
                )
            )

    for role in FORCE_ROLES:
        bindings.append(
            BindingSpec(
                f"force_{role}_wall",
                zone="force",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_WALL,
                description=f"force {role}",
            )
        )

    for role in ECO_ROLES:
        bindings.append(
            BindingSpec(
                f"eco_{role}_wall",
                zone="eco",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_WALL,
                description=f"eco {role} wall",
            )
        )
        bindings.append(
            BindingSpec(
                f"eco_{role}_referee",
                zone="eco",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_REF,
                description=f"eco {role} referee",
            )
        )

    for hero in HEROES:
        for role in HERO_ROLES:
            bindings.append(
                BindingSpec(
                    f"{hero}_{role}_wall",
                    zone=hero,
                    role=role,
                    normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                    force_observe=True,
                    collapse_alpha=ETA_WALL,
                    description=f"{hero} {role}",
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


BAR_BRAIN_SPEC = bar_brain_spec()
