"""compat shim — remove after the first public playtest.

The module lives at ``verdance.hub.contract`` now; this file keeps ``python tools/contract_v2.py`` and
``import contract_v2`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.hub import contract as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
