"""compat shim — remove after the first public playtest.

The module lives at ``verdance.hub.build_hub_state`` now; this file keeps ``python tools/build_hub_state_v1.py`` and
``import build_hub_state_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.hub import build_hub_state as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
