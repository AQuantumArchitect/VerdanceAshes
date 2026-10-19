# Installing Verdance's Ashes (Alpha)

## Requirements

- Windows 10/11
- Beyond All Reason installed (the standard installer from beyondallreason.info),
  launched at least once so it has downloaded a game engine
- ~50 MB free disk space for the package itself
- Up to ~700 MB more in your **BAR install** for campaign maps, if you don't
  already have them. The campaign uses seven community maps and fetches each one
  the first time a mission needs it, from Beyond All Reason's own content
  service. The first mission needs about 100 MB; the rest arrive as you go.
- An internet connection the first time each new map comes up

Python is **not** required — a portable Python runtime is bundled in `runtime\`.
The maps are not bundled: they belong to their authors and your BAR client
downloads them from the same place it always does.

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
- **BAR closes instantly, or `Dependent archive "<map name>" not found`** -- the
  mission's map isn't installed and couldn't be downloaded. This is fatal inside
  BAR itself, before the campaign loads, so it looks like a crash. Check your
  connection and try again; to fetch every map up front, run:
  `runtime\python\python.exe tools\map_provisioner_v1.py --check-all`
  As a last resort, join any BAR lobby on that map once and let the client pull it.
- **Mission ends but nothing advances** -- check the kernel's status page
  (`http://127.0.0.1:8770/api/status`) and BAR's `data\infolog.txt` for
  `VA_RESULT_JSON` lines. Include both in a bug report.
- **Reset everything** -- run `RESET.bat` (campaign restarts at mission 1;
  your BAR install is untouched).
- **Uninstall** -- delete `data\games\VerdanceAshes.sdd` from your BAR install and delete
  the unzipped package folder.
