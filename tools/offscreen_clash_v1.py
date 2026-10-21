"""compat shim — remove after the first public playtest.

The module lives at ``verdance.world.offscreen_clash`` now; this file keeps ``python tools/offscreen_clash_v1.py`` and
``import offscreen_clash_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.world import offscreen_clash as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
