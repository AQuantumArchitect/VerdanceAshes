# Forge tools (not the player path)

These launchers are for design / overnight / ant / legacy export.

**Players:** use workspace root `SETUP.bat` + `PLAY.bat` only.

`operator\` holds older PowerShell wrappers. Prefer:

```
python -m verdance_kernel launch
powershell -File scripts\ship.ps1
powershell -File scripts\player\smoke_play_path.ps1
```

Each bat here calls `..\_env.bat` (one level up from forge).
