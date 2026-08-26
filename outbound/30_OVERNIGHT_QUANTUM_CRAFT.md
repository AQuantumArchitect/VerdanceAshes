# 30 — Overnight dual-manifold craft + novel quantum brains

**Date:** 2026-07-26 (overnight)  
**Status:** Mechanisms shipped + co-evolution gym running

## Intent

While Luke sleeps: iterate **proxy-player belief** against **campaign-shape density** until the Verdance campaign is diverse, compelling, clear early, wider late, and beatable.

## Novel quantum-brain mechanisms

| Mechanism | Module | What it does |
|-----------|--------|--------------|
| **PathKet** | `quantum_membrane.py` | Complex amplitudes over paths A/B/C (Armada / Free-ashes / Void-exit). Soft measure + rotate + phase kick. |
| **CampaignDensity** | same | 3×3 Hermitian path membrane: diag = path weight, off = coherence. Dephase on loss, rephase on multipath win. |
| **ProxyBelief** | same | Partial-trace stand-in. HUD weakly collapses belief; **never** loads campaign ρ. DecoyPOVM injects confusion. |
| **LaneDensity** | same + `lane_war.py` | n×n line-war membrane. HOLD rephases; BREAKTHROUGH collapses adjacent coherence. |
| **PredicateInterference** | same + `fair_sim.py` | Multipath win predicates as amplitudes; constructive clear on wide cards; thrash penalty. |
| **SolutionEntropy** | same | Shannon width of viable vector mix (craft diagnostic). |
| **Disposition⊗Density** | `campaign_manifold.py` | Enemy AI disposition modulated by path coherence/entropy Kraus-ish channel. |
| **Craft controller** | `manifold_gym.py` | Retunes difficulty / width curve / decoy / lane bias toward arc win-rate bands. Aggressive steamroll response when win≈100%. |
| **InterferenceTuner** | `interference_tuner.py` | Phase layouts per mission kind; multipath reward vs thrash punish → craft nudges. |
| **Path anti-collapse** | `PathKet.soft_measure` | Soft mix + amplitude floor so A/B/C cannot die overnight. |
| **EnemyLineAI** | `enemy_line_ai.py` + `fair_sim` | Disposition⊗density enemy that WEIGHT/BREAKTHROUGH/STAGGER against player front. |
| **craft_apply** | `craft_apply.py` | Pin gym widths into `craft_width_override.json` for campaign curve. |
| **PathAnneal** | `anneal_paths.py` | Reheat collapsed A/B/C multipath between gens. |
| **PerArcScale** | `CraftKnobs.arc*_scale` | Keep arc1 clear while arc3 grows teeth. |
| **SchismEntangle** | `schism_entangle.py` | High schism widens late solutions + B–C path coherence. |

## Dual manifold fair rule (unchanged)

- Proxy sees: briefing, FairHUD, width_band, primary_hint, lane feel bands, belief state.
- Proxy never sees: campaign diag, win_predicates list, enemy exact mass, ρ purity raw as numbers used for cheat.

## Co-evolution gym

```powershell
$ws = "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
$env:PYTHONPATH = "$ws\tools;C:\Users\Luke Spooner\ws-win\umwelt\src"
$py = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"

# Overnight (time budget)
& $py -m quantum_bar_ai.manifold_gym --gens 40 --seeds 2 --hours 6

# Quick craft pass
& $py -m quantum_bar_ai.manifold_gym --gens 8 --seeds 2
```

Each generation:
1. Craft campaign under knobs (width early→late, decoys, enemy aggro, lane bias).
2. LocalToolAgent + bar_brain plays full 15-mission fair campaign (N seeds).
3. CampaignDensity + PathKet + CampaignRho evolve from outcomes.
4. bar_brain trains (now with **width_band** + **lane_band** tables).
5. Craft controller retunes knobs toward targets:
   - Arc1 win 80–98% (clear vectors)
   - Arc2 55–85%
   - Arc3 40–75% (wide multipath)
   - Overall 55–85%, diversity ≥ 0.32

Artifacts:
- `headless_runs/manifold_gym_<stamp>/gym_report.json`
- `outbox/manifold_gym.latest.json`
- `app/brain/craft_recipe.json` (champion knobs)
- `app/brain/bar_brain_weights.json` (updated)

## bar_brain v0.3

New tables:
- `width_action`: narrow | open | wide
- `lane_action`: solid | ragged | broken

Narrow priors push **PUSH_OBJECTIVE**; wide priors open multipath eco/flank/defend.

## Lane AI (Koom 3–5)

`LineFront.density: LaneDensity` now co-evolves with classical lane state:
- solid front (high purity/coherence) fights better
- breakthrough is a **measurement** on that column

## Tests

```powershell
& $py -m unittest quantum_bar_ai.test_quantum_membrane quantum_bar_ai.test_manifolds_lane -v
```

47 tests green (quantum + prior manifold/lane suite).

## Morning checklist

1. Read `outbox/manifold_gym.latest.json` → `best.arc_rates` + `craft_score`
2. Inspect `app/brain/craft_recipe.json`
3. Optional: pin champion knobs into `campaign_manifold.mission_width_curve` defaults
4. Still pending human: Lua Koom strips, umweltd register, BAR play verify
5. Human dams Luke-only (never auto-clear)

## Early overnight signals

| gen | overall | arc rates (1/2/3) | craft_score | note |
|-----|---------|-------------------|-------------|------|
| 0 | 100% | 1 / 1 / 1 | 0.43 | too easy — steamroll response |
| 1 | 97% | 1.0 / 0.9 / 1.0 | 0.57 | teeth on arc2 |
| 2 | **67%** | **0.6 / 0.4 / 1.0** | **0.66** | teeth overshot arc1/2; arc3 still free |
| restart+arc scales | **87%** | **1.0 / 0.6 / 1.0** | **0.76** | arc1 clear, arc2 in band, pathH=0.91 |
| rebalance v2 gen1 | **80%** | **0.8 / 0.6 / 1.0** | **0.800** | arc1+2 in band; arc3 free |
| arc3 teeth gen0 | **83%** | **1.0 / 0.6 / 0.9** | **0.844** | climax finally bites |
| **arc3 teeth gen1** | **77%** | **0.9 / 0.6 / 0.8** | **0.960** | **OVERNIGHT CHAMPION** (best diversity) |
| arc3 teeth gen4 | **70%** | **0.8 / 0.6 / 0.7** | **0.955** | perfect band fit; diversity low |

**Champion feel:** early clear (arc1 90%), mid tense (arc2 60%), late wide multipath with real losses (arc3 80%), overall 77% beatable. Path entropy 0.82.

**Gen4 alternate:** all three arcs *inside* target bands (0.8/0.6/0.7) — slightly lower score only because action diversity dipped.

Co-evolution is alive. Gym continues refining; pin already written to `app/brain/craft_recipe.json`.

Champion knobs mid-run (evolving) — see `headless_runs/manifold_gym_*/champion_knobs.json`.

Also landed **path annealing** (`anneal_paths.py`) for next gym restarts — reheats collapsed A/B/C multipath.

## Acceptance (this night)

- [x] Dual manifolds co-evolve offline
- [x] Novel quantum mechanisms implemented + tested
- [x] Lane density membrane on line war
- [x] bar_brain width/lane bands
- [x] Long gym runnable (`--hours`)
- [x] Enemy line AI disposition channel
- [x] InterferenceTuner craft nudges
- [ ] Champion recipe reviewed by human after sleep
- [ ] In-BAR Lua lane strips
- [ ] Live umweltd registration
