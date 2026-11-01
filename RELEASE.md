# Verdance's Ashes - release facts (source of truth)

| Field | Value |
|---|---|
| Display name | Verdance's Ashes (itch page title: Verdance's Ashwalkers) |
| Repo / canonical folder | github.com/AQuantumArchitect/VerdanceAshes - `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace` |
| itch page | https://aquantumarchitect.itch.io/verdances-ashwalkers (download) |
| itch channels | `windows` |
| Engine | Beyond All Reason (Recoil) mutator + embedded Python 3.12 hub. Needs BAR installed. |
| Build | `scripts/ship.ps1` (version from `VERSION`) |
| Open issues | Umwelt copy in `ws-win\umwelt` is stale vs WSL `~/ws/umwelt`; `release_manifest.json` contains a personal path; Umwelt license not checked. |
| Play copy | an itch download, run SETUP.bat once then PLAY.bat |
| Release command | bump `VERSION`, `git tag vX.Y.Z; .\tools\release.ps1 -Channel windows` |
| Last verified build | `0.14.0`: itch download byte-identical to the pushed folder. Not launched this pass (needs BAR + SETUP). |
