# Installing Verdance's Ashes (Alpha)

## Requirements

- Windows 10/11
- Beyond All Reason installed (the standard installer from beyondallreason.info),
  launched at least once so it has downloaded a game engine
- ~50 MB free disk space

Python is **not** required — a portable Python runtime is bundled in `workspace\runtime\`.

## Steps

1. Unzip the package anywhere you like (e.g. `Documents\VerdanceAshes`).
   Avoid folders that need admin rights (like `Program Files`).
2. Double-click `workspace\SETUP.bat`.
   - It auto-detects your BAR install (default: `%LOCALAPPDATA%\Programs\Beyond-All-Reason\data`).
     If it can't find it, it will ask you for the path.
   - It copies `VerdanceAshes.sdd` into BAR's `data\games\` folder.
   - It creates a fresh campaign state.
3. Double-click `workspace\PLAY_SESSION.bat` to play.

## The play loop

`PLAY_SESSION.bat` runs the whole cycle for one mission:

```
build mission -> launch BAR -> you play -> result auto-detected
   -> campaign advances -> next mission built -> "next-ready"
```

Just close BAR after the victory/defeat banner, and run PLAY_SESSION again for
the next mission. If you prefer buttons, `LAUNCH_CONSOLE.bat` opens a browser
control panel with the same loop plus file inspectors.

## Troubleshooting

- **"Could not locate a Beyond All Reason data directory"** — pass the path manually:
  re-run SETUP.bat and enter the `data` folder that contains `engine\` and `games\`.
- **BAR launches vanilla skirmish instead of the mission** — the mutator isn't installed;
  re-run SETUP.bat and check that `data\games\VerdanceAshes.sdd\modinfo.lua` exists.
- **Mission ends but nothing advances** — check `workspace\outbox\play_session.status.json`
  and BAR's `data\infolog.txt` for `VA_RESULT_JSON` lines. Include both in a bug report.
- **Reset everything** — run `workspace\RESET_CAMPAIGN.bat` (campaign restarts at mission 1;
  your BAR install is untouched).
- **Uninstall** — delete `data\games\VerdanceAshes.sdd` from your BAR install and delete
  the unzipped package folder.
