"""compat shim — remove after the first public playtest.

The module lives at ``verdance.readings.validate_story`` now; this file keeps ``python tools/validate_story_v1.py`` and
``import validate_story_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.readings import validate_story as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
