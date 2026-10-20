# Verdance's Ashes

A single-player **campaign shell** for [Beyond All Reason](https://www.beyondallreason.info).

The green is dying. Ashwalkers hold the line.

You plan the war from a map. You fight short sorties in BAR. Between missions the planet digs in — aces gain XP and wounds, and the next fight is grown from that living world.

**Alpha playtest.** BAR must already be installed. This repository does not ship BAR, Recoil, or campaign maps.

## Play (this workspace)

```
SETUP.bat     once
PLAY.bat      every session — leave the window open
```

War map at `http://127.0.0.1:8770` → green sortie → **Drop into battle**. After the fight the kernel brings the result home. If the map does not move: **After the fight — bring it home**.

Reset: `RESET.bat`. Thirty-second path: [`docs/release/START_HERE.txt`](docs/release/START_HERE.txt). Feedback: [`docs/release/PLAYTESTING.md`](docs/release/PLAYTESTING.md).

## Ship (other machines)

```
SHIP.bat
```

Writes `export/dist/VerdanceAshes_vX.Y.Z` (and a zip). Recipients unzip, run `SETUP.bat`, then `PLAY.bat`. Optional My Games copy: `python -m verdance_kernel ship --my-games`.

Steam, GitHub Releases, and a Steam AppID are not wired yet. The dist zip is the publishing path.

## What this is

| Piece | Role |
|---|---|
| Campaign kernel (`tools/verdance_kernel`) | Control plane: launch, stamp, ingest |
| War map (`app/showoff`, port 8770) | CYOA hub |
| `mod/VerdanceAshes.sdd` | BAR mutator |
| `state/campaign_state.json` | World graph *G* between Drops |

One BAR Drop is one observation that collapses the world graph. Law: [`docs/GRAPH_COLLAPSE_SSOT.md`](docs/GRAPH_COLLAPSE_SSOT.md). Protocol: [`docs/CAMPAIGN_BAR_PROTOCOL.md`](docs/CAMPAIGN_BAR_PROTOCOL.md). Architecture: [`docs/SHIP_ARCHITECTURE.md`](docs/SHIP_ARCHITECTURE.md). Deploy truth: [`docs/DEPLOY_TRUTH.md`](docs/DEPLOY_TRUTH.md).

```
python -m verdance_kernel launch
python -m verdance_kernel status
python -m verdance_kernel ship
```

Operator notes live in [`HOME.md`](HOME.md).

## License

Split on purpose. Read [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

- `mod/`, `data/`, `scripts/`, `docs/` — GPL-2.0-or-later (Recoil requires game code it loads to be GPL-compatible)
- `tools/`, `app/` — all rights reserved
- BAR content and maps stay with their authors; this project never redistributes them

## Status

Private repo. Version is the root `VERSION` file. Consolidation line starts at 0.8.0 (one play path). Current line: **0.12.7**.
