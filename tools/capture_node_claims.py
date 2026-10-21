"""compat shim — remove after the first public playtest.

The module lives at ``verdance.company.capture_node_claims`` now; this file keeps ``python tools/capture_node_claims.py`` and
``import capture_node_claims`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.company import capture_node_claims as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
