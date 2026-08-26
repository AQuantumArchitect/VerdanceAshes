"""Player-proxy umwelt world — mood graph for a Verdance strike commander.

Axes (signed feelings, same idiom as yurt-mood / quantum_lichen):

    aggression   -1 hold/defensive   .. +1 push/charge
    caution      -1 reckless         .. +1 careful
    focus        -1 distracted       .. +1 objective-locked
    pressure     -1 calm/time        .. +1 clock-panic
    cohesion     -1 scattered        .. +1 group-kept
    momentum     -1 stalled          .. +1 steamrolling

Nodes:
    proxy (root) — overall commander mood
    mission      — objective / threat / clock field
    force        — relative combat strength
    hero_vane / hero_ketha — optional per-hero organs

Hive η tiers on every organ×axis:
    *_claim    0.25  (proxy / LLM self-report)
    *_wall     0.40  (sim / telemetry hose)
    *_referee  0.92  (objective/result ground truth)

WIRE SIGN LAW (from yurt_mood live probe): warm evidence posts as +v with
inverted regime so d drives Bloch-z toward the warm pole (z=-1).
"""
from __future__ import annotations

from umwelt.spec.schema import BindingSpec, DomainSpec, DriverSpec, NodeSpec

ETA_CLAIM = 0.25
ETA_WALL = 0.40
ETA_REF = 0.92

# Warm pole = negative d under inverted regime (see yurt_mood world.py).
WARM_NORM = {"type": "regime", "center": 0.0, "width": 0.5, "invert": True}

AXES = (
    "aggression",
    "caution",
    "focus",
    "pressure",
    "cohesion",
    "momentum",
)

# Mission-side continuous sensors (not full mood axes).
MISSION_ROLES = ("objective", "threat", "clock", "progress")
FORCE_ROLES = ("player_strength", "enemy_strength", "advantage")
HERO_ROLES = ("alive", "wounded", "near_objective")

HEROES = ("hero_vane", "hero_ketha")

TICK_S = 5.0  # one proxy decision tick ≈ 5 sim seconds
GAMMA_MOOD = 0.002  # tau ~ 8 min — mood outlives a few ticks
GAMMA_FAST = 0.01   # mission sensors ease faster


def player_proxy_spec(*, name: str = "verdance-player-proxy") -> DomainSpec:
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

    # Mood organs: claim / wall / referee per axis on proxy root.
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

    # Mission continuous [0,1] sensors via wall tier.
    for role in MISSION_ROLES:
        bindings.append(
            BindingSpec(
                f"mission_{role}_wall",
                zone="mission",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_WALL,
                description=f"mission {role} telemetry",
            )
        )
        bindings.append(
            BindingSpec(
                f"mission_{role}_referee",
                zone="mission",
                role=role,
                normalizer={"type": "range", "lo": 0.0, "hi": 1.0},
                force_observe=True,
                collapse_alpha=ETA_REF,
                description=f"mission {role} ground truth",
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


# Concrete instance for `python -m umwelt.spec.validate`
PROXY_SPEC = player_proxy_spec()
