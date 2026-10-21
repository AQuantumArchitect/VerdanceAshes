"""compat shim — remove after the first public playtest.

The module lives at ``verdance.company.commerce_delivery`` now; this file keeps ``python tools/commerce_delivery_v1.py`` and
``import commerce_delivery_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.company import commerce_delivery as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
