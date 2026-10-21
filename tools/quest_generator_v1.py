"""compat shim — remove after the first public playtest.

The module lives at ``verdance.company.quest_generator`` now; this file keeps ``python tools/quest_generator_v1.py`` and
``import quest_generator_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.company import quest_generator as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
