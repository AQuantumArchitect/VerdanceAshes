# 31 — Sleep handoff (overnight craft)

**When you wake:** dual manifolds have been co-evolving; novel quantum brains landed.

## What was invented tonight

1. **`quantum_membrane.py`** — PathKet, CampaignDensity, ProxyBelief, LaneDensity, PredicateInterference, DecoyPOVM, solution entropy
2. **`manifold_gym.py`** — proxy vs campaign-shape co-evolution with craft controller
3. **`interference_tuner.py`** — multipath phase layouts + thrash punish
4. **`enemy_line_ai.py`** — disposition⊗density enemy line planner (wired into fair_sim)
5. **`lane_stress.py`** — Koom 3–5 line-war bench
6. **`craft_apply.py`** — pin champion widths into campaign curve
7. **bar_brain v0.3** — width_band + lane_band action tables
8. **policy width_band** — narrow→clear push; wide→multipath eco

## Overnight job (current)

```
python -m quantum_bar_ai.manifold_gym --gens 100 --seeds 2 --hours 5.5 --base-seed 71
# out: headless_runs/manifold_gym_20260726_122122
```

**OVERNIGHT COMPLETE:** score **0.960**, arcs **0.9 / 0.6 / 0.8**, overall **77%**  
51 gens · 4.56h · mean score 0.912 · run `manifold_gym_20260726_131147`.  
See `outbound/34_OVERNIGHT_FINAL.md`.

Artifacts:

| Path | What |
|------|------|
| `headless_runs/manifold_gym_*/gym_report.json` | full history |
| `headless_runs/manifold_gym_*/champion_knobs.json` | best craft |
| `outbox/manifold_gym.latest.json` | latest report |
| `app/brain/craft_recipe.json` | recipe for pin |
| `app/brain/craft_width_override.json` | pinned widths (if pin ran) |
| `app/brain/bar_brain_weights.json` | trained scars |

## Morning 5-minute ritual

```powershell
$ws = "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
$env:PYTHONPATH = "$ws\tools;C:\Users\Luke Spooner\ws-win\umwelt\src"
$py = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"

# 1) morning digest
& $py -m quantum_bar_ai.gym_digest

# 2) pin widths if score looks good
& $py -m quantum_bar_ai.craft_apply --show
& $py -m quantum_bar_ai.craft_apply --pin

# 3) smoke campaign at champion difficulty
& $py -m quantum_bar_ai.beat_campaign --once --train
```


## Fair rule (still)

Proxy never reads campaign ρ or enemy exact mass. Luke/Dave human dams never auto-clear.

## Still human / later

- Lua Koom zone strips (Phase D)
- umweltd register verdance_proxy + verdance_campaign
- BAR play verify free
- Review craft_score ≥ 0.75 before pinning as default curve
