"""compat shim — remove after the first public playtest.

The module lives at ``verdance.belief.hub_belief`` now; this file keeps ``python tools/hub_belief_v1.py`` and
``import hub_belief_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.belief import hub_belief as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
