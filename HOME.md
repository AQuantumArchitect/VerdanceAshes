# BAR Verdance Workspace — HOME

**Verdance's Ashes** — BAR campaign shell.

## Recalibration (read this first)

**One Drop = one observation.** The hub holds the company's belief between fights; BAR is where it looks; `bring_home` folds what it saw back into belief (`docs/UMWELT_IN_VERDANCE.md`).  
Law + inventory: [`docs/archive/GRAPH_COLLAPSE_SSOT.md`](docs/archive/GRAPH_COLLAPSE_SSOT.md)

World SSOT: `state/campaign_state.json` → `graph`  
Character graph: `data/story/hero_umwelt.json` + `support_web.json`  
Combat lens (optional): molecule soft policy — not world truth; rollback `va_molecule_policy=off`

## Docs

- **The rules / the engine:** [`docs/THE_GAME.md`](docs/THE_GAME.md) · [`docs/UMWELT_IN_VERDANCE.md`](docs/UMWELT_IN_VERDANCE.md) (older graph-collapse framing: `docs/archive/GRAPH_COLLAPSE_SSOT.md`)
- **Narrative readings (ρ_N over readings, attractors, voices, the roll):** [`docs/NARRATIVE_READINGS_SSOT.md`](docs/NARRATIVE_READINGS_SSOT.md) — faces: `outbox/readings.latest.json`, `outbox/occasions.latest.md`
- Deploy truth: [`docs/DEPLOY_TRUTH.md`](docs/DEPLOY_TRUTH.md)
- Ship architecture: [`docs/SHIP_ARCHITECTURE.md`](docs/SHIP_ARCHITECTURE.md)
- **Campaign ↔ BAR protocol:** [`docs/CAMPAIGN_BAR_PROTOCOL.md`](docs/CAMPAIGN_BAR_PROTOCOL.md) — after a fight the kernel brings the result home; if not: Pull result / Abandon.
- **Ash Console UI:** [`docs/UI_ASH_CONSOLE.md`](docs/UI_ASH_CONSOLE.md) — shared feel for BAR HUD + HTML hub.
- **Theater map + home jungle:** [`docs/archive/THEATER_MAP_AND_HOME.md`](docs/archive/THEATER_MAP_AND_HOME.md) — map-first sorties, quiet-rim or Ashwalker-base infil/exfil, Rock Jungle home, rep curve.
- Hero / FE graph foundation: [`docs/HERO_GRAPH_UMWELT_FOUNDATION.md`](docs/HERO_GRAPH_UMWELT_FOUNDATION.md)
- Quantum design law (aspiration): [`BAR_verdant_ashes_campaign/quantum_graph_framework.md`](BAR_verdant_ashes_campaign/quantum_graph_framework.md)

---

## Player (when you want to play the game)

**Play path you use (this workspace):** `SETUP.bat` once, then **`PLAY.bat`** every session (leave it open). `RESET.bat` wipes the campaign (confirms).

**Other machines:** `SHIP.bat` → `export\dist\VerdanceAshes_vX.Y.Z` (+ zip). Recipients run SETUP then PLAY from the unzipped folder. Optional: `python -m verdance_kernel ship --my-games`.

Feedback after a session: hub → System → **Export feedback bundle** (writes `export\feedback_<stamp>.zip`).

```
SETUP.bat          # once: BAR + mutator + hub
PLAY.bat           # every session: kernel + war map + bridge
RESET.bat          # optional: wipe campaign (confirms)
SHIP.bat           # build export\dist\VerdanceAshes_vX.Y.Z (+ zip)
```

Leave `PLAY.bat` open → green sortie → **Drop into battle** → homecoming folds the sortie into belief.

### Faces worth your eyes (player)

- `state/campaign_state.json` → `graph` (world between fights)
- `outbox/hub_result.latest.json` (debrief after bring_home)
- `outbox/war_map.json` / `campaign_surface.latest.json`
- `outbox/human_playthrough.latest.json` (and yurt-sync vitals copies, if present)

Everything else in `outbox/` is derived or bot output — see `docs/hub_state_v1.md` (files beside it).

---

## Bots own testing (not the player path)

Luke does **not** need to run proxy / overnight / residual / dual-gym scripts. Those exist for swarm seats and unit tests.

Doc shelf (bots only): [`docs/archive/PROXY_CAMPAIGN.md`](docs/archive/PROXY_CAMPAIGN.md) · [`docs/HIVE_BAR_RESIDUAL_BRIDGE.md`](docs/HIVE_BAR_RESIDUAL_BRIDGE.md) · [`docs/OVERNIGHT_HIVE_BAR_0_8_5.md`](docs/OVERNIGHT_HIVE_BAR_0_8_5.md) · [`docs/BAR_SWARM_ORGANIC.md`](docs/BAR_SWARM_ORGANIC.md) · [`docs/SWARM_BAR_TRAINING_PATHWAY.md`](docs/SWARM_BAR_TRAINING_PATHWAY.md) · [`docs/UMWELT_GYM_PATHWAY.md`](docs/UMWELT_GYM_PATHWAY.md)

**Bot faces (ignore unless debugging farms):** `proxy_campaign`, `hive_bar_residual`, `overnight_hive_bar`, `training_pathway_morning`, `campaign_fruit`, `bar_swarm_*`, hive `cognifold_faces` / muscle portfolio.

---

## Version

Root `VERSION` (kernel reads it). Consolidation line starts at **0.8.0**. Current line: **0.14.0** (second test line; see CHANGELOG.md). 0.13.0 was the first test export.

## Dev tools

Content and test scripts (not the player path), run with PowerShell from the workspace:

```
scripts\bake_living_shell.ps1            # bake an enemy base template (local headless)
scripts\forge\cloud\Invoke-CloudShellBake.ps1   # the same bake on a cloud host
scripts\run_headless_smoke.ps1           # headless BAR smoke of the mission seed
scripts\run_headless_balance_test.ps1    # headless balance telemetry
scripts\verify_hero_lifecycle.ps1        # hero down / wreck / rez in real BAR
scripts\run_zone_cartography_survey.ps1  # zone map surveys
scripts\run_ai_duel_suite.ps1            # AI vs AI zone-flow duels
```

The old launchers, the proxy-AI and the overnight tooling live on the git branch
`archive/tooling-2026-10-22`.

## Kernel CLI (seats / automation)

```
python -m verdance_kernel launch
python -m verdance_kernel status
python -m verdance_kernel sync-mod
python -m verdance_kernel ship
```

## In BAR

Space briefing · 1/2/3 continue · `/vazones` · `/vastory`

## Archive

Pre-pass snapshots and numbered LLM handoffs were removed from the tree. Git history still has `_attic/` and `outbound/` — see [`docs/ARCHIVE.md`](docs/ARCHIVE.md).
