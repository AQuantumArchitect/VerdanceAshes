# Outbound 23 — Three-arc campaign + super quantum BAR brain

**Date:** 2026-07-26  
**Status:** **SHIPPED** — full campaign playable by player-proxy-bot; BAR brain training live

## What shipped

### 1. Three fair arcs (15 missions)

| Arc | IDs | Theme | Base building |
|-----|-----|-------|---------------|
| 1 — First Scar | va_001–005 | strike team raids | NO |
| 2 — Expand & Tempo | va_006–010 | Tabula / converter eco / tempo / deeper glass | YES (except hold_plateau pure hold) |
| 3 — Siege & Climax | va_011–015 | Bastion siege, Rock Jungle wilds, Simmers multipressure | YES |

Kinds: `eco_raid`, `strike_relay`, `seize_lane`, `hold_plateau`, `eco_expand`, `siege`, `survive_wilds`, `multipressure`.

Maps cover the full seven-map pool: greenest_fields, eye_of_horus, all_that_simmers, koom_valley, tabula, ancient_bastion, the_rock_jungle.

### 2. Eco manifold priors

`tools/quantum_bar_ai/eco_manifold.py` — compact ROI model distilled from  
https://bar-eco-manifold-five.vercel.app/  
(T1 mex/wind/solar/con/nano/moho costs + incomes).

Used for:
- fair_sim eco state + FairHUD eco bands (dry/thin/steady/fat)
- `BUILD_*` action vocabulary
- BAR brain bootstrap priors

### 3. Super quantum BAR brain (umwelt)

| Piece | Path |
|-------|------|
| DomainSpec (eco organ) | `bar_brain_world.py` |
| Weights + train/ingest | `bar_brain.py` |
| CLI | `train_bar_brain.py` |
| Weights file | `app/brain/bar_brain_weights.json` |

Trains from campaign tapes (action histograms × HUD/eco context × kind family).  
Outputs BAR seat hints (`simple` vs `barbarian_aggressive`, eco_first vs pressure) for normal BAR games.

Hive η unchanged: claim 0.25 / wall 0.40 / referee 0.92.

### 4. Runners

```bat
RUN_CAMPAIGN.bat              REM local tools, arcs 1-3, train brain
RUN_CAMPAIGN_ANT.bat          REM ant subscription steam
app\bin\TRAIN_BAR_BRAIN.bat   REM inspect / retrain from latest report
```

```powershell
python -m quantum_bar_ai.beat_campaign --once --arcs 1,2,3 --train
python -m quantum_bar_ai.beat_campaign --once --arcs 2 --ant --ant-every 6
python -m quantum_bar_ai.train_bar_brain --show
```

Story still publishes to `app/story/latest` + HTTP `:8765` + Lua `/vastory`.

## Champion result (local tools)

```
difficulty = 1.0
seed       = 11 (also 28)
hard wins  = 15/15
by_arc     = 5/5 · 5/5 · 5/5
backend    = local_tools
train      = 342+ samples · win_rate 1.0
elapsed    ≈ 2.5 min
```

## Fairness contract (unchanged)

Agent sees: PlayerFacingCard, FairHUD (incl. eco bands when building allowed), umwelt beliefs from HUD walls, tools.  
Agent never sees: enemy_scale, raw HP, SimTruth.

## Dual-room posture

| Room | Path | Role |
|------|------|------|
| Design forge | `BAR_Verdance_Workspace` | campaign authoring, beat runners, brain train |
| Customer | `Documents\My Games\VerdanceAshes` | play release + story GUI |

## Next rings

- [ ] Ant subscription full 15-mission overnight lock (multi-seed)
- [ ] Feed live BAR zone telemetry → FairHUD + eco walls
- [ ] Lua seat: commit_action → GiveOrder / build queues
- [ ] Mode B public zip with three-arc story baked in
- [ ] denser bar_brain: couple weights into LocalToolAgent each tick
