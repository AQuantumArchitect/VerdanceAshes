"""compat shim — remove after the first public playtest.

The module lives at ``verdance.hub.apply_result_to_hub`` now; this file keeps ``python tools/apply_result_to_hub_v1.py`` and
``import apply_result_to_hub_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.hub import apply_result_to_hub as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
