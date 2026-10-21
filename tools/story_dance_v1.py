"""compat shim — remove after the first public playtest.

The module lives at ``verdance.readings.story_dance`` now; this file keeps ``python tools/story_dance_v1.py`` and
``import story_dance_v1`` working for the PowerShell scripts and anything not yet repointed.
"""
from verdance.readings import story_dance as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_m.main())
