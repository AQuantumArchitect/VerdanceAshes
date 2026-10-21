"""compat shim — remove after the first public playtest.

The module lives at ``verdance.company.hero_observe`` now; this file keeps ``python tools/hero_observe_v1.py`` and
``import hero_observe_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.company import hero_observe as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
