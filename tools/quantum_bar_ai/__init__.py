"""quantum_bar_ai — umwelt-mood player proxy for Verdance campaign playtests.

MVP stack
---------
1. ``world``     — DomainSpec: player mood axes + mission field (belief graph)
2. ``mood``      — read calibrated mood; post claim/wall/referee sensors
3. ``policy``    — rule-based action picker from mood (offline brain)
4. ``brain``     — optional Grok/xAI override (subscription brain)
5. ``sim``       — headless abstract combat for no-base strike missions
6. ``seat``      — observe → mood → decide → act loop
7. ``bar_map``   — map proxy decisions → BAR PlayerController profiles
8. ``suite``     — multi-mission iteration / tape for quantum-BAR-AI

Design breadcrumb: yurt ``worlds/yurt_mood`` axes + umwelt hive η tiers
(claim 0.25 / wall 0.40 / referee 0.92). Game shape follows
``examples/fledgeling_fog`` (tick driver, dissipative roles, GameHost-friendly).
"""

# Keep imports light so `python -m quantum_bar_ai.suite` does not re-enter suite.
from .world import PROXY_SPEC, player_proxy_spec

__all__ = [
    "PROXY_SPEC",
    "player_proxy_spec",
    "PlayerProxySeat",
    "run_early_arc_suite",
]

__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "PlayerProxySeat":
        from .seat import PlayerProxySeat

        return PlayerProxySeat
    if name == "run_early_arc_suite":
        from .suite import run_early_arc_suite

        return run_early_arc_suite
    raise AttributeError(name)
