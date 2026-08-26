# Overnight scorecard — FINAL

| Metric | Value |
|--------|-------|
| Gens | **51** |
| Elapsed | **4.56 h** (16411 s) |
| Mean craft_score | **0.912** |
| **Champion craft_score** | **0.960** |
| Champion arcs | **0.9 / 0.6 / 0.8** |
| Champion overall | **0.767** |
| Path entropy | **0.817** |
| Diversity | **0.399** |

## Champion knobs
difficulty 1.31 · width 0.18→0.74 · decoy 2.2 · aggro 1.35  
arc scales 0.94 / 0.95 / 1.67

## Artifacts
- `app/brain/craft_recipe.json`
- `app/brain/craft_width_override.json`
- `headless_runs/manifold_gym_20260726_131147/gym_report.json`
- `outbound/34_OVERNIGHT_FINAL.md`

## Morning
```powershell
python -m quantum_bar_ai.gym_digest
python -m quantum_bar_ai.beat_campaign --once --train
```
