"""compat shim — remove after the first public playtest.

The module lives at ``verdance.belief.world`` now; this file keeps ``python tools/umwelt_world_v1.py`` and
``import umwelt_world_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.belief import world as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
