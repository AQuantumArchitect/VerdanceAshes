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
| Open issues | no match yet on a stock BAR install (0.14.2 below). Fixed 2026-10-31: the stale `ws-win` Umwelt (pin above); the personal path in `release_manifest.json` (now `sourceCommit` + `umweltCommit`, and `UMWELT_SNAPSHOT.txt` names the repo and commit, not a folder); the Umwelt license (below). |
| Play copy | an itch download, run SETUP.bat once then PLAY.bat |
| Release command | bump `VERSION`, `git tag vX.Y.Z; .\tools\release.ps1 -Channel windows` (`-DryRun` builds without pushing) |
| Last verified build | `0.14.1` (commit ce26b4c, tag v0.14.1): pushed to verdances-ashwalkers:windows, butler build #2275151, 2026-11-01; pushed folder byte-identical to build\release\windows\VerdanceAshes_v0.14.1 + VERSION.txt. First stock-BAR playtest (a friend's PC) did not get into a match: SETUP refused a data folder without games\ (fixed 250c3b2) and the first map would not download (fixed 651e22f, 146d88a). |
| Pushing to itch | the Grok bot pushes with butler; `.\tools\release.ps1 -Channel windows` where butler and a login are set up. |
| Stock-BAR check | 0.14.0 could not start on a BAR from beyondallreason.info (`Dependent archive "Beyond All Reason $VERSION" not found`); 0.14.1 stamps the installed mutator with the rapid BAR. 0.14.1 on a friend's stock install: SETUP needed a hand-made games\ folder, and Greenest Fields 1.3 never downloaded (the map service answered with a single object; BAR's own download gave 1.3.1, which the pinned campaign cannot use). Both fixed on master for 0.14.2. |

## Umwelt license check (2026-10-31)

- **What ships:** `scripts/ship.ps1` copies Umwelt's `src/umwelt` package, unmodified, into `tools/_vendor/umwelt/` of every Windows build.
- **The license:** Umwelt (github.com/AQuantumArchitect/umwelt) is licensed **Apache-2.0**, both in its `LICENSE` file and in `pyproject.toml` (`license = { text = "Apache-2.0" }`, classifier "OSI Approved :: Apache Software License"). The package's source files carry no other license or copyright headers. Its README records it as extracted from Luke's own private meerkat project and released as Apache-2.0.
- **Verdict:** redistribution is allowed, including inside a closed, all-rights-reserved product. Section 4 of the license asks for three things:
  - a copy of the license with the redistributed code. `ship.ps1` now stages `tools/_vendor/umwelt/LICENSE` and fails the build if it is missing; before 2026-10-31 it was not shipped.
  - notice of any modifications. There are none; the copy is verbatim at the pinned commit.
  - Umwelt's NOTICE file, if it had one. It does not.
- **Where it is recorded:** `NOTICE` lists Umwelt, and `LICENSE` part 2 carves `tools/_vendor/umwelt/` out of the kernel's all-rights-reserved terms.
- **Builds already published:** the 0.13.0 and 0.14.0 builds shipped the code without its LICENSE file. 0.13.0 also used the stale clone. Both gaps close with the next build.
