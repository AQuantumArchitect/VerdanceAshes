# 34 — Overnight final: dual-manifold craft complete

**Status:** DONE · 51 gens · 4.56 hours · champion craft_score **0.960**

## Champion campaign shape

| Arc | Win rate | Intent |
|-----|----------|--------|
| 1 | **0.90** | Early clear, bright action vectors |
| 2 | **0.60** | Mid tense, multipath opening |
| 3 | **0.80** | Late bites, still beatable |
| Overall | **0.77** | Clear + beatable |

Path entropy **0.82** · diversity **0.40** at champion gen.

### Champion knobs

```json
{
  "difficulty": 1.31,
  "width_early": 0.18,
  "width_late": 0.74,
  "width_ease": 0.66,
  "decoy_pressure": 2.2,
  "enemy_aggro": 1.35,
  "lane_bias": 1.02,
  "path_purity_target": 0.37,
  "arc1_scale": 0.94,
  "arc2_scale": 0.95,
  "arc3_scale": 1.67
}
```

Pinned:

- `app/brain/craft_recipe.json`
- `app/brain/craft_width_override.json`
- `app/brain/bar_brain_weights.json` (trained through gym)
- Full report: `headless_runs/manifold_gym_20260726_131147/gym_report.json`

## Novel quantum-brain mechanisms invented

1. **PathKet** — complex path A/B/C superposition  
2. **CampaignDensity** — Hermitian path membrane  
3. **ProxyBelief** — partial-trace fair belief (no ρ leak)  
4. **LaneDensity** — n×n Koom line-war coherence  
5. **PredicateInterference** — multipath win amplitudes  
6. **DecoyPOVM** — decoy dephasing on belief  
7. **InterferenceTuner** — thrash vs multipath craft nudges  
8. **PathAnneal** — reheat collapsed multipath  
9. **PerArcScale** — keep early clear, late teeth  
10. **SchismEntangle** — schism widens late solutions  
11. **EnemyLineAI** — disposition⊗density line adversary  
12. **Arc3Teeth** — clock/strength tax on climax  
13. **Craft controller** — dual-manifold retune loop  

## What the night proved

- Campaign density and proxy belief can co-evolve offline  
- Early missions stay clear while late multipath gains real losses  
- Lane AI membrane fights shoulder-to-shoulder (Koom 3–5)  
- Mean craft_score across 51 gens stayed ~**0.91** — stable region, not a fluke  

## Morning commands

```powershell
$ws = "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
$env:PYTHONPATH = "$ws\tools;C:\Users\Luke Spooner\ws-win\umwelt\src"
$py = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"

& $py -m quantum_bar_ai.gym_digest
& $py -m quantum_bar_ai.craft_apply --show
& $py -m quantum_bar_ai.beat_campaign --once --train
& $py -m unittest quantum_bar_ai.test_quantum_membrane quantum_bar_ai.test_manifolds_lane -v
```

## Still later (human)

- Lua Koom zone strips  
- umweltd register proxy + campaign worlds  
- BAR play verify  
- Luke/Dave dams never auto-clear  
