# Deploy truth (v0.8 consolidated)

**One play path. One setup. One ship.**

## Canonical commands

| Job | Command |
|-----|---------|
| **Play** | `PLAY.bat` → `python -m verdance_kernel launch` |
| **First run** | `SETUP.bat` |
| **Reset** | `RESET.bat` |
| **Smoke** | `powershell -File scripts\player\smoke_play_path.ps1` |
| **Ship** | `SHIP.bat` or `python -m verdance_kernel ship` → `export\dist\` |

## Layout

```
PLAY.bat SETUP.bat RESET.bat SHIP.bat   ← player root
app\bin\                                ← PLAY, HUB_HOST, SHIP, _env
app\bin\forge\                          ← operator only
scripts\player\                         ← setup / smoke / aliases kernel calls
scripts\ship.ps1                        ← only ship pipeline
tools\verdance_kernel\                  ← product API
mod\VerdanceAshes.sdd\                  ← mutator source; sync on every Drop
export\dist\                            ← only ship output
```

## Rules

1. Kernel is the only player control plane.
2. `commit_deploy` always `sync_mod -Copy` (workspace SDD → BAR `data\games`) **before** the build, then launches `spring.exe` itself and tails the infolog (pass five). SHIP is for other people's machines; your own Drop always runs the workspace Lua.
3. My Games is **not** a second product unless you run `ship -InstallToMyGames` (full dist).
4. Do not add `export\customer\VerdanceAshes_v0.*` trees.

## Work packages

| WP | Status |
|----|--------|
| WP0 VERSION + this doc | done |
| WP1 honest forge path | done |
| WP2 launcher collapse | done |
| WP3 ship.ps1 | done |
| WP4 kernel mod sync + player script resolve | done |
| WP5 attic | done (folder removed from tree; see `docs/ARCHIVE.md`) |
