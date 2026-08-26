# Proxy Campaign — player proxy (quantum-BAR-AI) vs Simple / Barbarian

**Goal:** develop and score the **player proxy** without a human at the keyboard.

**Luke:** you do not drive this harness. Bots / organic swarm / overnight farm do.  
**You:** optional read of scorecards; play real BAR with `PLAY.bat` when you want to play.

**Muscle law:** units run on any **free capable** node (wargen, roc, …). Residual tags `ran_on`. Human seal stays human-only. See [`BAR_SWARM_ORGANIC.md`](BAR_SWARM_ORGANIC.md).

---

## What it is

A closed loop that sits **quantum-BAR-AI** (`LocalToolAgent` + umwelt mood graph) in the **player seat** (**player proxy**) and resolves each sortie against an abstract enemy style that maps to BAR controllers:

| Enemy style | Sim pressure | BAR controller (for later headless A/B) |
|-------------|--------------|------------------------------------------|
| `simple` | Lower scale, softer counters | `simple` |
| `barbarian` | Higher scale, pushier | `barbarian_aggressive` |
| `both` | A/B multi-seed | both |

Each sortie:

1. `materialize_next_intent` (real Mode A / theater contracts)
2. `run_fair_mission` (quantum proxy, fair HUD only)
3. Map verdict → `verdance-match-result/1.0`
4. `process_result` (rep, Tnb, claims, BP access, offscreen multirate)
5. `world_tick` (far-band regrow + offscreen clash)

No `spring.exe`. No IconsAtlas. Artifacts under `headless_runs/proxy_campaign_*` and `outbox/proxy_campaign.latest.json`.

---

## Who runs it (bots)

| Bot path | Role |
|----------|------|
| Overnight hive-bar farm | Multi-phase long A/B + UL train |
| Organic `bar_swarm_bridge` | Units when **this muscle** free+capable |
| `player_proxy_muscle` | Mesh free/capability auction |
| Pulse free FLOPs / cascade | Seed + tick organic packet |
| Task `Wargen-BarSwarmOrganic` | Periodic tick on wargen muscle |

Needs `ws-win\umwelt\src` on PYTHONPATH and preferably umwelt venv — **bots set this**, not Luke.

---

## Scorecard faces (Luke may read)

`outbox/proxy_campaign.latest.json`:

- `byStyle.simple.meanWinRate` / `byStyle.barbarian.meanWinRate`
- `headToHead.winRateDelta_barb_minus_simple` — negative means BARb is harder (good)
- `meanFun`, `meanTnb`, `meanClashEvents`
- `train` / residual after bot `--write` path

Full per-sortie tapes: `headless_runs/proxy_campaign_<stamp>/report.json`.

If both styles show `meanWinRate=1.0`, bots should raise difficulty (organic/overnight auto-bump). Fun / Tnb / clash often move before win-rate does.

---

## Relation to other harnesses

| Harness | Player outcome | World | Who |
|---------|----------------|-------|-----|
| `kernel_campaign_sim_v1` | RNG profiles | Real story engine | bots |
| `quantum_bar_ai.beat_campaign` | Fair proxy on fixed arc cards | Not story engine | bots |
| **`proxy_campaign_v1`** | Fair proxy | **Real story engine** | bots |
| headless BAR | BAR controller | Real spring | optional / rare |
| Human PLAY | You | Live BAR | **Luke when playing** |

---

## Hive residual + UL train (v0.8.7 pathway)

When bots invoke proxy with write/train (overnight / organic unit):

1. Trains `bar_brain` histogram scars from fair tapes  
2. UniversalLearner on **`width_action+eco_action`** → `app/brain/bar_brain_ul_state.json`  
3. Appends mission learn tape rows  
4. Hoses residual → outbox + yurt-sync vitals  
5. Fruit harvest + adaptive difficulty (unit end)  
6. Organic free-CPU path: [`BAR_SWARM_ORGANIC.md`](BAR_SWARM_ORGANIC.md) · full pathway: [`SWARM_BAR_TRAINING_PATHWAY.md`](SWARM_BAR_TRAINING_PATHWAY.md)

---

## Iteration (bots)

1. Farm runs (overnight / organic).  
2. If proxy stomps both: bots raise difficulty.  
3. If proxy dies to simple: bots retune via train path / policy scars.  
4. Human scorecards later unlock `pkt-bar-playtest-s6-retune` (seal — not freeable).

## Explicit non-goals

- Live Lua seat issuing Spring orders as required path  
- Cloud multi-map BARb dumps as dependency  
- Billing / ant LLM on proxy path (`QBAI_NO_LLM=1`)  
- BAR densify / raising n_obs past honesty wall  
- Luke typing CLI to “start the test”
