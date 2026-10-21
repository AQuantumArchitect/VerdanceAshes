"""compat shim — remove after the first public playtest.

The module lives at ``verdance.belief.intel_lua`` now; this file keeps ``python tools/intel_lua_v1.py`` and
``import intel_lua_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.belief import intel_lua as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
