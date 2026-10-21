# quantum-BAR-AI

**Umwelt-mood player proxy** for Verdance Ashes campaign playtests.

Goal: sit a belief-field + Grok brain in the player seat so we can iterate the
early no-base strike arc headlessly, then map those decisions onto real BAR
AI controllers for spring-headless A/B.

## Breadcrumbs (yurt / umwelt)

| Source | What we took |
|--------|----------------|
| `ws-win/umwelt` | DomainSpec, η-weighted observe, dissipative mood roles, blank boot |
| `yurt/worlds/yurt_mood` | 5-axis mood idiom, claim/wall/referee tiers, warm-regime sign law |
| `examples/fledgeling_fog` | tick driver, game-shaped field, comprehension inheritance |
| `examples/hive_relay` | LLM claims at η&lt;1, referees at η≈1, confabulation scars |
| `spacewheat/.../ollama_seat.py` | one-command-per-turn seat pattern |

## MVP loop

```
mission sensors (sim or BAR telemetry)
        │ wall η=0.40
        ▼
  umwelt mood graph  (aggression, caution, focus, pressure, cohesion, momentum)
        │
        ├─ policy.py   (always-on offline brain)
        └─ brain.py    (Grok/xAI override every N ticks)
                │
                ▼
        ACTION  →  abstract combat sim  (or BAR PlayerController plan)
                │
                ▼
        referee sensors η=0.92  →  field holds comprehension across missions
```

## Fair play contract (required)

The agent may only use:

| Allowed | Forbidden |
|---------|-----------|
| `PlayerFacingCard` briefing text | `enemy_scale`, exact enemy HP |
| `FairHUD` coarse bands | raw sim RNG / unit tables |
| umwelt beliefs (HUD→walls only) | omniscient advantage floats |
| tools: read_*/think/commit_action | writing high-η truth without referee |

First arc champion: **5/5 missions × 3 seeds @ difficulty 1.0**.  
Full campaign champion: **15/15 @ difficulty 1.0** (seeds 11, 28). Scorecards lived in `outbound/` (git history; `docs/ARCHIVE.md`).

## Quick start

```powershell
cd "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"

$py = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"
$env:PYTHONPATH = "tools;C:\Users\Luke Spooner\ws-win\umwelt\src"

# validate the domain
& $py -m umwelt.spec.validate quantum_bar_ai.world:PROXY_SPEC

# BEAT the fair first arc (local tool agent — free chassis)
& $py -m quantum_bar_ai.beat_first_arc --once --difficulty 1.0

# FULL three-arc campaign + train BAR brain (eco manifold + tapes)
& $py -m quantum_bar_ai.beat_campaign --once --arcs 1,2,3 --train

# multi-seed lock + auto-tune (arc 1)
& $py -m quantum_bar_ai.beat_first_arc --difficulty 1.0 --seeds 3 --max-rounds 5

# yurt ANT subscription brain (preferred — grok.com session, $0 real_spend)
# requires: grok login, no XAI_API_KEY; coral on PYTHONPATH
$env:PYTHONPATH = "tools;C:\Users\Luke Spooner\ws-win\umwelt\src;C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral"
Remove-Item Env:XAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:GROK_API_KEY -ErrorAction SilentlyContinue
& $py -m quantum_bar_ai.beat_first_arc --once --ant --ant-every 5
& $py -m quantum_bar_ai.beat_campaign --once --arcs 1,2,3 --ant --ant-every 6 --train

# inspect trained super quantum BAR brain
& $py -m quantum_bar_ai.train_bar_brain --show

# Dual umwelt manifolds + co-evolution gym (proxy belief ⊥ campaign density)
& $py -m quantum_bar_ai.manifold_gym --gens 12 --seeds 2
& $py -m quantum_bar_ai.manifold_gym --gens 80 --seeds 2 --hours 6   # overnight
& $py -m quantum_bar_ai.craft_apply --show
& $py -m quantum_bar_ai.craft_apply --pin   # pin widths into campaign curve

# Novel quantum mechanisms: PathKet, CampaignDensity, ProxyBelief, LaneDensity,
# PredicateInterference, DecoyPOVM, InterferenceTuner, EnemyLineAI
# Dual-manifold / overnight craft notes: git history under outbound/ (docs/ARCHIVE.md)


# or bat
.\RUN_CAMPAIGN.bat
.\RUN_CAMPAIGN_ANT.bat
```

**Do not** use metered `GROK_API_KEY` / xAI console for ant brains.

Outputs:
- campaign: `headless_runs/quantum_bar_ai_campaign_*/`, `outbox/quantum_bar_ai_campaign.latest.json`
- story: `app/story/latest`
- brain: `app/brain/bar_brain_weights.json`

## Action vocabulary

Combat: `PUSH_OBJECTIVE` `PROBE` `FLANK` `HOLD_AND_HEAL` `RALLY` `FALLBACK` `EXTRACT` `WAIT`  
Eco (arcs 2–3 / normal BAR): `BUILD_MEX` `BUILD_ENERGY` `BUILD_CON` `EXPAND_FRONT` `RECLAIM` `TECH_UP` `DEFEND_BASE`

Eco ROI priors from [bar-eco-manifold-five](https://bar-eco-manifold-five.vercel.app/).

## BAR bridge (current)

`bar_map.py` maps mood/action histograms → existing headless controllers:

- pushy mood → `barbarian_aggressive`
- cautious mood → `simple`

Feed that into:

```powershell
.\scripts\run_headless_balance_test.ps1 `
  -ScenarioPath data\scenarios\generated\next_mission_intent.playable.json `
  -Variant alpha_player `
  -PlayerControllers barbarian_aggressive `
  -SimFrames 12000
```

True in-engine quantum AI (Lua command issuance from the seat) is the next
ring — sim iteration is intentionally first so the mood graph earns its keep.

## Env

| Var | Meaning |
|-----|---------|
| `GROK_API_KEY` | xAI key (also loaded from `ws-win/yurt/config/yurt.env`) |
| `GROK_MODEL` | default `grok-code-fast` |
| `GROK_API_URL` | default `https://api.x.ai/v1/chat/completions` |
| `QBAI_NO_LLM=1` | force policy-only |

## Shippability

- **Dev team:** suite summary JSON + per-mission tapes; no BAR GUI required for mood iteration.
- **Community later:** package sim demo + a prebaked headless controller plan; full BAR seat needs the existing playable mutator install path (`PACKAGE_RELEASE` / playable slice).
