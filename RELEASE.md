# Verdance's Ashes - release facts (source of truth)

| Field | Value |
|---|---|
| Display name | Verdance's Ashes (itch page title: Verdance's Ashwalkers) |
| Repo / canonical folder | github.com/AQuantumArchitect/VerdanceAshes - `%USERPROFILE%\Documents\BAR_Verdance_Workspace` on the build PC |
| itch page | https://aquantumarchitect.itch.io/verdances-ashwalkers (download) |
| itch channels | `windows` |
| Engine | Beyond All Reason (Recoil) mutator + embedded Python 3.12 hub. Needs BAR installed. |
| Build | `scripts/ship.ps1` (version from `VERSION`) |
| Umwelt in the build | exactly the commit in `tools/umwelt_pin.json` (now `8154c13`, Umwelt `main` on 2026-10-31), fetched by `ship.ps1` into `export\cache\umwelt`. Home-folder clones (`~\ws-win\umwelt`, `~\umwelt`) are no longer searched; `UMWELT_SRC` still overrides and must sit on the pin (`-AllowUmweltDrift` for a dev build). A shipped build imports its own snapshot before any clone on the machine. To move to a newer Umwelt: bump the pin, run the tests, ship. |
| Licenses shipped | Lua, data, scripts, docs: GPL-2.0-or-later. Kernel (`tools/`, `app/`): all rights reserved. Vendored Umwelt: Apache-2.0, LICENSE beside it. CPython: PSF. NumPy/SciPy: BSD-3-Clause. Full list: `LICENSE`, `NOTICE`. |
| Open issues | itch push of 0.14.1 (above). Fixed 2026-10-31: the stale `ws-win` Umwelt (pin above); the personal path in `release_manifest.json` (now `sourceCommit` + `umweltCommit`, and `UMWELT_SNAPSHOT.txt` names the repo and commit, not a folder); the Umwelt license (below). |
| Play copy | an itch download, run SETUP.bat once then PLAY.bat |
| Release command | bump `VERSION`, `git tag vX.Y.Z; .\tools\release.ps1 -Channel windows` (`-DryRun` builds without pushing) |
| Last verified build | `0.14.0`: itch download byte-identical to the pushed folder. Not launched this pass (needs BAR + SETUP). |
| Last build | `v0.14.1` (`ce26b4c`, tagged and pushed), built 2026-11-01 on the build PC with `release.ps1 -Channel windows -DryRun`: exit 0, 3718 files, Umwelt `8154c13` with its LICENSE, belief world imports, gates pass. Output `build\release\windows\VerdanceAshes_v0.14.1` and `build\release\VerdanceAshes_v0.14.1_win64.zip` (67 MB). **Not on itch yet:** the build PC has no butler and no itch login (`BUTLER_API_KEY` unset, no `~\.config\itch\butler_creds`, none in WSL). |
| Pushing to itch | Either upload the zip on the itch Edit game page (Uploads, mark it Windows, hide or delete the 0.14.0 file), or install butler (itch.io/docs/butler), run `butler login` once, set `BUTLER_API_KEY` or keep the login, and run `.\tools\release.ps1 -Channel windows`. |
| Stock-BAR check | 0.14.0 and earlier could not start on a BAR installed from beyondallreason.info (`Dependent archive "Beyond All Reason $VERSION" not found`, reproduced headless). 0.14.1 stamps the installed mutator with the rapid BAR the launcher downloaded; a headless sortie played through with it. The build PC uses a developer BAR (`games\BAR.sdd`), so play on a stock install is the thing to watch in the first friend test. |

## Umwelt license check (2026-10-31)

- **What ships:** `scripts/ship.ps1` copies Umwelt's `src/umwelt` package, unmodified, into `tools/_vendor/umwelt/` of every Windows build.
- **The license:** Umwelt (github.com/AQuantumArchitect/umwelt) is licensed **Apache-2.0**, both in its `LICENSE` file and in `pyproject.toml` (`license = { text = "Apache-2.0" }`, classifier "OSI Approved :: Apache Software License"). The package's source files carry no other license or copyright headers. Its README records it as extracted from Luke's own private meerkat project and released as Apache-2.0.
- **Verdict:** redistribution is allowed, including inside a closed, all-rights-reserved product. Section 4 of the license asks for three things:
  - a copy of the license with the redistributed code. `ship.ps1` now stages `tools/_vendor/umwelt/LICENSE` and fails the build if it is missing; before 2026-10-31 it was not shipped.
  - notice of any modifications. There are none; the copy is verbatim at the pinned commit.
  - Umwelt's NOTICE file, if it had one. It does not.
- **Where it is recorded:** `NOTICE` lists Umwelt, and `LICENSE` part 2 carves `tools/_vendor/umwelt/` out of the kernel's all-rights-reserved terms.
- **Builds already published:** the 0.13.0 and 0.14.0 builds shipped the code without its LICENSE file. 0.13.0 also used the stale clone. Both gaps close with the next build.
