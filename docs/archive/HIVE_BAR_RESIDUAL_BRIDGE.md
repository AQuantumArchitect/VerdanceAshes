# Hive ↔ Quantum-BAR Residual Bridge (player-proxy muscle)

Thin bidirectional residual so **quantum-BAR-AI / player proxy** is informed by **swarm / umwelt learning** without a god-brain merge.

**Luke:** read faces / story. **Bots:** train, hose, overnight farm, organic muscle. No Luke CLI required for testing.

---

## Laws

| Do | Don't |
|----|-------|
| File vitals residual both ways | Merge hive η rooms into fair_sim |
| Fair-room only for the agent | Leak SimTruth / enemy mass tables |
| UniversalLearner on params | Invent a second learning zoo |
| Real proxy outcomes as evidence | Fake densify / raise BAR n_obs |
| Tag **`ran_on`** muscle node | Assume work always runs on wargen |
| Soft hive doctrine as one-shot prior | Command the fair agent every tick |
| Keep human seals freeable=false | Bot-clear playtest seals |

**BAR densify remains BANNED.** `honesty.nObsWall = 15`.  
**Human seal** `pkt-bar-playtest-s6-retune` stays human-only.

---

## Architecture

```
player_proxy_mesh (auction: free capable muscles)
    │
    ├─► wargen muscle (when free)
    └─► roc muscle (when free + live face)
              │
              ▼
proxy_campaign (story engine + fair_sim player seat)   ← bots run
    ├─► bar_brain histogram scars
    ├─► UniversalLearner (width_action + eco_action)
    └─► hive-bar-residual/1.1 JSON  (+ kind=player_proxy, ran_on, swarmDigest)
              ├─ outbox/hive_bar_residual.latest.json
              └─ yurt-sync/commons/vitals/bar_proxy_residual.latest.json
                        │
                        ▼
              hive_gym_arena (ladder honesty, no densify fraud)
```

Organic free-CPU fill: [`BAR_SWARM_ORGANIC.md`](BAR_SWARM_ORGANIC.md).  
Proxy campaign: [`PROXY_CAMPAIGN.md`](PROXY_CAMPAIGN.md).

---

## For Luke (read-only)

| Face | What it means |
|------|----------------|
| `outbox/proxy_campaign.latest.json` | simple vs barb win/fun |
| `outbox/hive_bar_residual.latest.json` | residual + honesty + **ran_on** |
| `outbox/hive_gym_arena.latest.json` | ladder honesty pass/fail |
| `outbox/overnight_hive_bar.latest.json` | overnight phase scorecard |
| `app/brain/bar_brain_weights.json` | scar tables |
| `app/brain/bar_brain_ul_state.json` | UL sigma / update counts |
| hive `bar_proxy_residual.latest.json` | same residual on swarm vitals |
| hive `player_proxy_mesh.json` | which muscles are free |
| hive `muscle/*_player_proxy.json` | per-node capability |

**You do not start farms.** Bots do. Play BAR with `PLAY.bat` when you want to play the game.

---

## Dialect

Schema: `hive-bar-residual/1.1` — `tools/hive_bar_residual_v1.py` (legacy 1.0 readers OK).

Key fields: `kind` (`player_proxy`), `ran_on` / `muscleNode`, `byStyle`, `headToHead`, `brain` (samples + dual UL), `missionCountThisUnit`, optional `swarmDigest`, `doctrineHints`, `honesty` (includes `humanSealBotClearForbidden`).

## UL family (v0.8.6+)

**`width_action+eco_action`** — front geometry *and* economy feel × ACTIONS.

- State: `app/brain/bar_brain_ul_state.json`
- Weights: `app/brain/bar_brain_weights.json` (width + eco tables)
- Pathway: [`SWARM_BAR_TRAINING_PATHWAY.md`](SWARM_BAR_TRAINING_PATHWAY.md)
- Pre snapshot: `app/brain/bar_brain_weights.pre_0_8_5.json`

---

## Bot entrypoints (seats / pulse only — not Luke)

| Bot | Entry |
|-----|--------|
| Muscle faces | `player_proxy_muscle.publish` / bridge publish-muscle |
| Overnight farm | `overnight_hive_bar.ps1` / Task or detached launch by seat |
| Organic idle | `bar_swarm_bridge` via pulse free FLOPs + `Wargen-BarSwarmOrganic` |
| Residual hose | end of `proxy_campaign_v1 --write` / unit run (bot-invoked) |
| Arena score | `hive_gym_arena` after residual write |

CLI copies exist under `tools/` and `scripts/player/` for **bot automation and unit tests**, not for Luke to type.

---

## Explicit non-goals

Live umweltd dependency · full ObservationTrust on every HUD wall · spring headless as required path · god-brain · densify · auto-clearing human playtest-s6 seal · orchestration seats executing BAR.
