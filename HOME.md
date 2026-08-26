# BAR Verdance Workspace — HOME

**Verdance's Ashes** — BAR campaign shell.

## Docs

- Deploy truth: [`docs/DEPLOY_TRUTH.md`](docs/DEPLOY_TRUTH.md)
- Ship architecture: [`docs/SHIP_ARCHITECTURE.md`](docs/SHIP_ARCHITECTURE.md)
- **Campaign ↔ BAR protocol:** [`docs/CAMPAIGN_BAR_PROTOCOL.md`](docs/CAMPAIGN_BAR_PROTOCOL.md) — after a fight the kernel brings the result home; if not: Pull result / Abandon.
- **Ash Console UI:** [`docs/UI_ASH_CONSOLE.md`](docs/UI_ASH_CONSOLE.md) — shared feel for BAR HUD + HTML hub.
- **Theater map + home jungle:** [`docs/THEATER_MAP_AND_HOME.md`](docs/THEATER_MAP_AND_HOME.md) — map-first sorties, rim infil/exfil, Rock Jungle home, rep curve.
- **Night play (v0.8.4 feel):** [`docs/NIGHT_TEST_0_8_4.md`](docs/NIGHT_TEST_0_8_4.md) — multi-rate offscreen, clash, Tnb BP; scorecard [`docs/NIGHT_PLAYTEST_SCORECARD.md`](docs/NIGHT_PLAYTEST_SCORECARD.md).

### Bot testing (Luke does not run these)

- **Player proxy campaign:** [`docs/PROXY_CAMPAIGN.md`](docs/PROXY_CAMPAIGN.md) — AI in player seat vs Simple/BARb (bots).
- **Hive residual bridge:** [`docs/HIVE_BAR_RESIDUAL_BRIDGE.md`](docs/HIVE_BAR_RESIDUAL_BRIDGE.md) — UL + residual hose + `ran_on` (bots).
- **Overnight farm:** [`docs/OVERNIGHT_HIVE_BAR_0_8_5.md`](docs/OVERNIGHT_HIVE_BAR_0_8_5.md) — multi-hour bot farm.
- **Node-agnostic organic muscle:** [`docs/BAR_SWARM_ORGANIC.md`](docs/BAR_SWARM_ORGANIC.md) — free wargen/roc when capable (bots).
- **Swarm × BAR training pathway (v0.8.7):** [`docs/SWARM_BAR_TRAINING_PATHWAY.md`](docs/SWARM_BAR_TRAINING_PATHWAY.md) — free-CPU learn every mission + campaign fruit.
- **Umwelt-primary dual gym:** [`docs/UMWELT_GYM_PATHWAY.md`](docs/UMWELT_GYM_PATHWAY.md) — umwelt+cognifold are the mission; BAR/SW are gyms (canonical N-gym: yurt-sync `docs/N_GYM_PORTFOLIO.md`).

---

## Player (when you want to play the game)

**Easiest today:** Desktop **`Verdance Playtest.bat`** (or `START_PLAYTEST.bat` here).  
When done: Desktop **`Verdance End Playtest.bat`** (or `END_PLAYTEST.bat`) — harvests **human** telemetry (not AI proxy).

Player brief + hitlist: [`docs/LUKE_PLAYTEST_TODAY.md`](docs/LUKE_PLAYTEST_TODAY.md)  
Scorecard: [`docs/HUMAN_PLAY_SCORECARD.md`](docs/HUMAN_PLAY_SCORECARD.md)

```
SETUP.bat          # once: BAR + mutator + hub
START_PLAYTEST.bat  # brief + PLAY.bat
PLAY.bat           # every session: kernel + war map + bridge
END_PLAYTEST.bat    # harvest human_playthrough faces + open scorecard
RESET.bat          # optional: wipe campaign (confirms)
SHIP.bat           # build export\dist\VerdanceAshes_vX.Y.Z (+ zip)
```

Leave `PLAY.bat` open → green sortie → **Drop into battle**.

Optional preflight before a **human** play night: `NIGHT_TEST.bat` (abstract; no spring required).

Human session faces (read by Grok/hive; **not** auto-merged into proxy UL):

- `outbox/human_playthrough.latest.json`
- `yurt-sync/commons/vitals/human_playthrough.latest.json`
- `yurt-sync/commons/vitals/human_playthrough_tape.jsonl`

---

## Bots own testing (not the player path)

Player-proxy farm, overnight UL train, residual hose, and organic free-CPU units are started by **swarm bots** (pulse, cascade, Task Scheduler, detached seats) on **any free capable muscle** (wargen, roc, …). Human seal stays human-only.

Luke does **not** need to run:

- `PROXY_CAMPAIGN.bat`
- `OVERNIGHT_HIVE_BAR.bat`
- powershell one-liners for proxy / residual / arena

Those scripts exist for **bot spawn and unit tests** only.

**Morning / curiosity faces (read-only):**

- `outbox/proxy_campaign.latest.json`
- `outbox/hive_bar_residual.latest.json` (includes `ran_on`, dual UL)
- `outbox/campaign_fruit.latest.json` (campaign + swarm ideas)
- `outbox/training_pathway_morning.json`
- `outbox/overnight_hive_bar.latest.json`
- `app/brain/bar_brain_ul_state.json` (`width_action+eco_action`)
- `app/brain/craft_recipe.json`
- hive: `commons/vitals/bar_proxy_residual.latest.json`
- hive: `commons/vitals/player_proxy_mesh.json`
- hive: `commons/vitals/organic_supervisor.json`
- hive: `commons/vitals/muscle_portfolio.json` (N-gym leases + rank)
- hive: `commons/vitals/workstream_registry.json` (workstreams as data)
- hive: `commons/vitals/dual_farm_supervisor.json` (n=2 mirror)
- hive: `commons/vitals/umwelt_skill_morning.json` (primary OKR)
- hive: `commons/vitals/cognifold_faces.json`
- hive: `commons/vitals/muscle/*_player_proxy.json`

---

## Version

Root `VERSION` (kernel reads it). Consolidation line starts at **0.8.0**. Current line: **0.9.0** (umwelt-primary dual gym + residual umweltPost + dual_farm lease).

## Forge tools

Operator / ant / overnight live under **`app\bin\forge\`** (bot/seat path, not “type this to play”).

```
app\bin\forge\RUN_CAMPAIGN.bat
app\bin\forge\DEV_LAUNCH.bat
app\bin\forge\operator\          # legacy PS1 wrappers
```

## Kernel CLI (seats / automation)

```
python -m verdance_kernel launch
python -m verdance_kernel status
python -m verdance_kernel sync-mod
python -m verdance_kernel ship
```

## In BAR

Space briefing · 1/2/3 continue · `/vazones` · `/vastory`

## Attic

`_attic\` holds pre-consolidation bats and old brochure exports. Safe to delete after you trust `export\dist`.
