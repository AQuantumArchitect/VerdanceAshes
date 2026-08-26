# Swarm × BAR Training Pathway (v0.8.7)

**Dual track:** BAR trains **swarm intelligence** *and* the **campaign itself** — on free CPU, without Luke typing CLI.

**Primary mission (v0.9.0):** umwelt + cognifolds are the center; BAR is a **gym**. See [`UMWELT_GYM_PATHWAY.md`](UMWELT_GYM_PATHWAY.md) and yurt-sync `docs/UMWELT_PRIMARY_DUAL_GYM.md`. Dual-farm exclusive lease coordinates BAR units vs SpaceWheat legs.

**Luke:** play with `PLAY.bat` when you want; optionally read faces below.  
**Bots:** organic free-CPU units, overnight farm, fruit harvest, curriculum.

Human seal `pkt-bar-playtest-s6-retune` stays freeable=false forever.  
BAR densify banned (`n_obs=15`). No god-brain merge.

---

## Loop

```
free muscle CPU
    → claim (player_proxy_muscle)
    → curriculum slot (C0–C4)
    → proxy missions (story engine + fair_sim)
    → scars + dual UL (width_action + eco_action) every mission
    → residual hose (ran_on, swarmDigest)
    → fruit (campaign ideas + soft doctrine + safe craft band)
    → better units + better campaign
```

| Track | Improves | Faces |
|-------|----------|--------|
| Swarm intelligence | residual, soft doctrine, cognifold viz | `hive_bar_residual`, `bar_swarm_doctrine_soft` |
| BAR campaign | craft knobs, flow proposals, A/B balance | `campaign_fruit`, `craft_recipe`, proxy scorecards |

---

## Cadences

| Cadence | When | What |
|---------|------|------|
| **Organic** | free CPU (muscle claim) | curriculum unit + train + hose + fruit |
| **Overnight** | scheduled A–G | deep UL, manifold, arena, fruit Phase G |
| **Fruit** | every unit end + overnight G | ideas + optional craft ±10% |

### Curriculum slots

| Slot | Role |
|------|------|
| C0_smoke | first after arm — health |
| C1_ladder | default A/B |
| C2_eco | every 3rd — longer ticks (eco UL) |
| C3_width | every 4th — harder width pressure |
| C4_manifold_snack | gym stale ≥12h — short manifold gens |

Difficulty lives in `app/brain/organic_difficulty.json` (auto bump when simple saturated).

---

## Learn-on-every-mission

Organic/overnight units use `proxy_campaign --write` ⇒ train scars + UL dual family.  
Mission rows append to:

- `app/brain/mission_learn_tape.jsonl`
- hive `commons/vitals/bar_mission_learn_tape.jsonl`

UL family: **`width_action+eco_action`** (not width-only).

---

## Fruit layer

`tools/campaign_fruit_v1.py` reads residual / proxy / UL / craft and writes:

- `outbox/campaign_fruit.latest.json`
- hive `bar_campaign_fruit.latest.json`
- soft doctrine `bar_swarm_doctrine_soft.json`
- optional craft update (`source: campaign_fruit`) inside safety band

Non-auto ideas stay proposals (`auto_apply_ok: false`) — bots may mint freeable packets later; never human seals.

---

## Faces Luke may read

| Face | Meaning |
|------|---------|
| `outbox/hive_bar_residual.latest.json` | learning scoreboard + ran_on |
| `outbox/campaign_fruit.latest.json` | campaign + swarm ideas |
| `outbox/training_pathway_morning.json` | morning digest |
| `app/brain/bar_brain_ul_state.json` | dual UL |
| `app/brain/organic_difficulty.json` | live organic difficulty |
| `app/brain/craft_recipe.json` | campaign craft knobs |
| hive `player_proxy_mesh.json` | free muscles |
| hive `organic_supervisor.json` | loop alive / re-arms |
| hive `bar_swarm_organ.json` | last tick |

Cognifold viz (optional): `verdance_cognifold_bridge.py` → `:8098/cognifold`.

---

## Bot entrypoints

| Bot | Role |
|-----|------|
| `player_proxy_muscle` | capability + claim |
| `bar_swarm_bridge` tick/loop | organic curriculum units |
| `run_organic_loop.py` | multi-hour AFK loop |
| `bar_swarm_unit_v1` | one unit (train+hose+fruit) |
| `campaign_fruit_v1` | harvest ideas |
| `organic_pathway_v1` | difficulty / curriculum / morning |
| `overnight_hive_bar.ps1` | phases A–G |

---

## Law

| Do | Don't |
|----|-------|
| Train every written unit | Skip train on organic |
| Dual-family UL | God-brain merge |
| Tag ran_on | Densify / raise n_obs |
| Fruit proposes; craft band-limited | Auto-clear human seals |
| Free-CPU muscle claim only | Orchestration seats execute BAR |
