"""compat shim — remove after the first public playtest.

The module lives at ``verdance.world.world_tick`` now; this file keeps ``python tools/world_tick_v1.py`` and
``import world_tick_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.world import world_tick as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
