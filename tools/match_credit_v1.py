"""compat shim — remove after the first public playtest.

The module lives at ``verdance.belief.match_credit`` now; this file keeps ``python tools/match_credit_v1.py`` and
``import match_credit_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.belief import match_credit as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
