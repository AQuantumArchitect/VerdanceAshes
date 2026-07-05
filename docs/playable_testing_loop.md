# Playable Testing Loop

This layer now treats All That Simmers as a scenario recipe plus named simulation variants.

## Main Files

- `data/scenarios/all_that_simmers.playable.json`
  - map identity and dimensions
  - reusable base recipes
  - team colors and start boxes
  - AI variant definitions
- `scripts/install_playable_slice.ps1`
  - generates `outbox/va_current.lua`
  - installs the generated mission seed into BAR
  - writes a matching startscript under `playable_runs/`
  - optionally launches BAR or creates a savegame
- `scripts/run_playable_variant_matrix.ps1`
  - runs several variants and writes a matrix manifest

## Variants

- `pressure_mix`: default playable slice, with authored proxy bases and conservative AIs.
- `simple_defenders`: low-volatility baseline for checking whether the base layout itself feels good.
- `barbarian_hard`: active BARbarIAn players using profile `hard`.
- `barbarian_aggressive`: active BARbarIAn players using profile `hard_aggressive`.

BARb identity was verified against the local BAR install:

- `ShortName=BARb`
- `Version=stable`
- profile config folders include `hard`, `medium`, `easy`, and `hard_aggressive`

## Commands

List variants:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_playable_slice.ps1 -ListVariants
```

Install the default playable seed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_playable_slice.ps1 -Variant pressure_mix
```

Create a loadable save for one variant:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_playable_slice.ps1 -Variant barbarian_aggressive -SaveGame -SaveName verdance_ats_barb_aggressive_001
```

Create comparable saves for the default matrix:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_playable_variant_matrix.ps1 -SaveGame
```

Run a fully headless AI balance probe:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_headless_balance_test.ps1
```

Short probe for harness validation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_headless_balance_test.ps1 -PlayerControllers simple,barbarian_aggressive -SimFrames 600 -TimeoutSeconds 240
```

The balance runner:

- installs the BAR Lua telemetry patch unless `-SkipPatchInstall` is passed
- gives Team 3 to the requested player-controller AI
- runs `spring-headless.exe`
- exports `VA_TELEMETRY_JSON_*` at the requested frame
- writes the latest telemetry to `outbox/bar_zone_telemetry.latest.json`
- writes per-run telemetry, match analysis, and a suite manifest under `headless_runs/balance_*`

Classification values:

- `target_band`: aggressive BARb gains/clears while SimpleAI stalls
- `too_hard_for_aggressive`: aggressive BARb cannot gain advantage by the tested horizon
- `too_easy_for_simple`: SimpleAI also gains/clears
- `needs_longer`: short probe ended while the aggressive controller was still active
- `inconclusive`: comparison did not include enough controller coverage

## Current Abstraction

The useful authoring unit is:

```text
zone intent -> force anchor -> base recipe -> AI personality -> savegame
```

The base recipe remains explicit and inspectable. Metal extractors use BAR's runtime metal spot finder through the existing Lua spawn hook, so recipes can say `atMetalSpots=true` instead of hardcoding every extractor coordinate.

The next layout step is to split recipes into rings:

- economy ring: mexes, wind/solar, storage
- defensive ring: LLTs, missile towers, radar
- production ring: labs, nanos, rally direction
- patrol ring: mobile defenders and pressure units

That gives the tactical layer knobs like `frontier_defensive`, `eco_greedy`, or `attacker_forward` without losing unit-level control.
