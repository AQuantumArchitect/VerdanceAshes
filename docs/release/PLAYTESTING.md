# Playtesting Verdance's Ashes

Thanks for testing. The most useful thing you can do is **play 2–3 sorties in a row**
and tell us where the loop broke or felt wrong.

## The player path (use this)

```
SETUP.bat   once
PLAY.bat    every session → war map (kernel on http://127.0.0.1:8770/)
RESET.bat   start over
```

1. **First light** — read the welcome card (**How this works** reopens it anytime).
2. **Choose a sortie** — green cards in the center. Stay on home ground first.
3. **Briefing table** — green = objective, blue = landing. Defaults are usually fine.
   The minimap paints what the company **believes** about each zone, not the truth.
4. **Launch, then Drop** — Launch loads the field in Beyond All Reason behind the hub
   while you pick who goes; Drop sends them in and brings BAR to the front. The first
   Launch on a new map downloads it first; the hub shows the progress.
5. **Play** — briefing (Space to dismiss), clear the objective, extract if prompted.
   After a win, **1 / 2 / 3** can take the next pocket on the same map.
6. **Bring it home** — bridge usually auto-applies. Fallback: **After the fight — bring it home**.
7. Hire mercs, talk to Ketha, rest, or take the next drop.

There is no other player path. Everything under `app\bin\forge\` is workspace
tooling and is not shipped.

## What we're testing

1. **Clarity** — do you always know the next button to click?
2. **Seat loop** — multi-sortie without re-running bats?
3. **Carry-forward** — heroes and warband across same-map chapters?
4. **Objectives** — panel sense, victory/defeat correct?
5. **Pacing** — trivial, fair, or hopeless? Sortie length?
6. **Campaign feel** — does the world react across a few missions?
7. **Vibe** — does it feel like a game, or a tool?

## A test machine (the dev kit)

`SHIP_DEV.bat` (in the workspace) builds `export\dist\VerdanceAshes_v<version>_dev_win64.zip`: the
player build plus the headless rig. On the test machine:

1. Install Beyond All Reason and launch it once.
2. Unzip anywhere, run `SETUP.bat` once.
3. `PLAY.bat` to play; `AUTOPILOT_TEST.bat` for two headless sorties with a hard BARbarian in the
   company seat; `WAR_BAKE.bat --map <map>` to re-bake a standing war.
4. `runtime\python\python.exe tests\run_tests.py` runs the suite (a fresh tree gets its SETUP save
   first).

`release_manifest.json` says what the build carries. `beliefWorks: false` means the vendored Umwelt
did not import (a stale clone on the building machine): the belief world is off and AUTOPILOT will not
run. Update the Umwelt clone and ship again.

## Sending feedback

1. In the hub: **System menu → Export feedback bundle**. It writes
   `export\feedback_<stamp>.zip` (your campaign state plus the logs the kernel
   needs to reproduce the problem).
2. Open an issue at <https://github.com/AQuantumArchitect/verdanceashes/issues>,
   attach the zip, and paste the template below.

```
Build / date:            (VERSION file, or the zip name)
Missions played:
Same-map continues? (Y/N, how many):
What I did:
What I expected:
What happened:
What felt good:
What was confusing:
Where the vibe broke:
```
