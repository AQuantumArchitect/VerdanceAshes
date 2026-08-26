# Installing Verdance's Ashes (Alpha)

## Requirements

- Windows 10/11
- Beyond All Reason installed (the standard installer from beyondallreason.info),
  launched at least once so it has downloaded a game engine
- ~50 MB free disk space

Python is **not** required — a portable Python runtime is bundled in `runtime\`.

## Steps

1. Unzip the package anywhere you like (e.g. `Documents\VerdanceAshes`).
   Avoid folders that need admin rights (like `Program Files`).
2. Double-click `SETUP.bat`.
   - It auto-detects your BAR install (default: `%LOCALAPPDATA%\Programs\Beyond-All-Reason\data`).
     If it can't find it, it will ask you for the path.
   - It copies `VerdanceAshes.sdd` into BAR's `data\games\` folder.
   - It creates a fresh campaign state.
3. Double-click `PLAY.bat` to play.

## The play loop

`PLAY.bat` starts the campaign kernel (a war map on `http://127.0.0.1:8770`,
opened in your browser) and leaves it running -- leave the window open:

```
war map -> choose a sortie -> Drop into battle -> BAR launches -> play
   |-- the kernel's BAR bridge brings the result home automatically
   +-- back on the war map: hire mercs, rest, talk, or take the next drop
```

You do not need to re-run PLAY.bat between sorties. Close the window to stop.

### Same-map seamless continue

On victory/partial, if the next contracts are on the **same map**, the match does
**not** GameOver. Debrief: press **1 / 2 / 3** to continue. Heroes, wrecks, and
field units carry forward; a new enemy camp reseeds at the new target.

## Troubleshooting

- **"Could not locate a Beyond All Reason data directory"** -- pass the path manually:
  re-run SETUP.bat and enter the `data` folder that contains `engine\` and `games\`.
- **BAR launches vanilla skirmish instead of the mission** -- the mutator isn't installed;
  re-run SETUP.bat and check that `data\games\VerdanceAshes.sdd\modinfo.lua` exists.
- **Mission ends but nothing advances** -- check the kernel's status page
  (`http://127.0.0.1:8770/api/status`) and BAR's `data\infolog.txt` for
  `VA_RESULT_JSON` lines. Include both in a bug report.
- **Reset everything** -- run `RESET.bat` (campaign restarts at mission 1;
  your BAR install is untouched).
- **Uninstall** -- delete `data\games\VerdanceAshes.sdd` from your BAR install and delete
  the unzipped package folder.
