# Verdance's Ashes

A single-player **campaign shell** for [Beyond All Reason](https://www.beyondallreason.info).

You plan the war from a map. You fight short sorties in BAR. Between missions the planet digs in — aces gain XP and wounds, and the next fight is grown from that living world.

**Public alpha.** BAR must already be installed and launched once. This repository does not ship BAR, Recoil, or campaign maps (the kernel fetches each map from BAR's own content service the first time a mission needs it).

## Play

There is one path. Windows 10/11.

```
SETUP.bat     once   — finds BAR (asks for the path if it cannot), installs the mutator, writes mission 1
PLAY.bat      every session — leave the window open while you play
RESET.bat     start the campaign over (your old save lands in state\backups\)
```

`PLAY.bat` opens the war map at `http://127.0.0.1:8770`. Choose a green sortie, confirm the objective, **Drop into battle**. After the fight the kernel brings the result home; if the map does not move, click **After the fight — bring it home**.

- From a **git clone**: Python 3.10+ must be installed (python.org, tick "Add python.exe to PATH"). `SETUP.bat` tells you if it cannot find one.
- From the **zip** (`SHIP.bat` output): nothing to install; Python is embedded under `runtime\`.

Thirty-second path: [`docs/release/START_HERE.txt`](docs/release/START_HERE.txt). Install details and troubleshooting: [`docs/release/INSTALL.md`](docs/release/INSTALL.md).

## Sending feedback

In the hub: **System menu → Export feedback bundle**. It writes `export/feedback_<stamp>.zip` (your campaign state plus the logs the kernel needs to reproduce the problem). Attach it to a GitHub issue at <https://github.com/AQuantumArchitect/verdanceashes/issues>, with the three lines from [`docs/release/PLAYTESTING.md`](docs/release/PLAYTESTING.md): what you did, what you expected, what happened.

## Ship (other machines)

```
SHIP.bat
```

Writes `export/dist/VerdanceAshes_vX.Y.Z` and a zip. It downloads the embeddable Python, installs numpy + scipy into it (the belief world's substrate; `-SkipScience` opts out) and vendors the Umwelt package when a clone is found (`UMWELT_SRC`, a sibling `..\umwelt`, or `~\umwelt`). Recipients unzip anywhere, run `SETUP.bat`, then `PLAY.bat`.

Steam, GitHub Releases, and a Steam AppID are not wired yet. The dist zip is the publishing path.

## What this is

| Piece | Role |
|---|---|
| Campaign kernel (`tools/verdance_kernel`) | Control plane: launch, stamp, ingest |
| War map (`app/showoff`, port 8770) | CYOA hub; the minimap paints the company's **belief**, not the truth |
| `mod/VerdanceAshes.sdd` | BAR mutator |
| `state/campaign_state.json` | World graph *G* between Drops (runtime; not tracked) |

One BAR Drop is one observation that collapses the world graph. Law: [`docs/GRAPH_COLLAPSE_SSOT.md`](docs/GRAPH_COLLAPSE_SSOT.md). Protocol: [`docs/CAMPAIGN_BAR_PROTOCOL.md`](docs/CAMPAIGN_BAR_PROTOCOL.md). Architecture: [`docs/SHIP_ARCHITECTURE.md`](docs/SHIP_ARCHITECTURE.md). Deploy truth: [`docs/DEPLOY_TRUTH.md`](docs/DEPLOY_TRUTH.md).

```
python -m verdance_kernel launch
python -m verdance_kernel status
python -m verdance_kernel ship
```

Operator notes live in [`HOME.md`](HOME.md); forge launchers (overnight, proxy, tracked play) live under `app/bin/forge/`.

## License

Split on purpose. Read [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

- `mod/`, `data/`, `scripts/`, `docs/` — GPL-2.0-or-later (Recoil requires game code it loads to be GPL-compatible)
- `tools/`, `app/` — all rights reserved
- BAR content and maps stay with their authors; this project never redistributes them

## Status

Public alpha. Version is the root `VERSION` file. Consolidation line starts at 0.8.0 (one play path). Current line: **0.12.7**.
