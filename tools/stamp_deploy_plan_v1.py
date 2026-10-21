"""compat shim — remove after the first public playtest.

The module lives at ``verdance.hub.stamp_deploy_plan`` now; this file keeps ``python tools/stamp_deploy_plan_v1.py`` and
``import stamp_deploy_plan_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.hub import stamp_deploy_plan as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
