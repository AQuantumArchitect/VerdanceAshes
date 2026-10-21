"""compat shim — remove after the first public playtest.

The module lives at ``verdance.world.zone_graph`` now; this file keeps ``python tools/world_zone_graph.py`` and
``import world_zone_graph`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.world import zone_graph as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
