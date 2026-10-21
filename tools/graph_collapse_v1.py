"""compat shim — remove after the first public playtest.

The module lives at ``verdance.world.graph_collapse`` now; this file keeps ``python tools/graph_collapse_v1.py`` and
``import graph_collapse_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.world import graph_collapse as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
