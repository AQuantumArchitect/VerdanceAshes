# Outbound 47 — Multi-stage playtest infra (built while you walked)

**Date:** 2026-07-28/29  
**Seat:** wargen-grok  
**Plan:** Multi-stage playtest + density wrap + strategic seat  

---

## What you asked

> work and test until it feels good… simulation as much as RTS… density matrix wraps a coherent world… rig so you can play strategically and develop attachments… multi-stage playtest and infrastructure building plan

## Stages shipped this session

| Stage | Status | Notes |
|-------|--------|-------|
| **S0** Warm calibration | DONE | 76 kernel tests + 10 playtest-infra tests OK; Mode A intent = `koom_valley` seize_lane; snapshot taken |
| **S1** Kernel campaign sim | DONE | `tools/kernel_campaign_sim_v1.py` — real `process_result` settle, multi-seed |
| **S2** Strategic seat + attachments | DONE | `tools/attachments_v1.py`, `tools/quantum_bar_ai/strategic_seat.py` |
| **S3** World tick + power response | DONE | `tools/world_tick_v1.py`; hooked into `process_result` |
| **S4** Hybrid BAR ladder | DOCUMENTED | Abstract (default) / headless / human — shared contract v2 |
| **S5** Afternoon pack | DONE | snapshot, restore script, scorecard template, this brief |
| **S6** Emergent retune | WAITING | After your human P0–P5 scorecards |

---

## Fresh numbers (just ran)

### Kernel sim — 5 seeds × 8 sorties (maps rotated)

```
meanFun: 0.796
diverse: true (4 clusters)
tnbSpread: 6.0  | claimSpread: 5.0
homes: koom, greenest, eye_of_horus, all_that_simmers, ancient_bastion
kinds: seize_lane, eco_raid, destroy_key_structure
pushback: armada watches bank, tnb crisis, regrow pressure, multipressure,
          garrison scale, deep-strike paths, soft work
```

Artifacts:

- `headless_runs/kernel_sim_*/report.json`
- `outbox/kernel_sim.latest.json`

### Strategic seat — 3 seeds × 8 deploys

```
meanFun: 0.703
drama: mixed on all three
```

- `outbox/strategic_seat.latest.json`

### Fun scorecard

```powershell
python tools\fun_scorecard.py --workspace .
# → outbox/fun_scorecard.latest.json
```

---

## New tools (kernel / sim only — no hub UI)

| Path | Role |
|------|------|
| `tools/attachments_v1.py` | Vane / Ketha / Null foothold ledger + fair dossier |
| `tools/world_tick_v1.py` | Offscreen tick + power-response curve |
| `tools/kernel_campaign_sim_v1.py` | Multi-sortie real settle without BAR |
| `tools/quantum_bar_ai/strategic_seat.py` | Fair strategic loop (local policy) |
| `tools/fun_scorecard.py` | Aggregate fun / divergence |
| `tests/test_playtest_infra.py` | Unit coverage |
| `scripts/restore_afternoon_snapshot.ps1` | Restore pre-playtest state |
| `docs/AFTERNOON_PLAYTEST_SCORECARD.md` | Your P0–P5 sheet |

`process_result` now also stamps **attachments** + **worldResponse** on every real advance.

---

## Density / power-response (feel)

Player strength (Tnb, claims, bond, Null favor, wounds) → world pushback:

| Signal | Response |
|--------|----------|
| High Tnb | `loanScrutiny`, `denseTeeth`, crisis tightens |
| Many claims | regrow boost, multipressure contracts |
| High Null favor | Armada garrison scale |
| Bond high, wounds low | path width / deep-strike offer |
| Bloody / weak | soft contracts + scarcity floor |

Between sorties: abstract regrow, pressure drift, q7 creep, optional REST heal.

---

## Afternoon playtest (you)

1. **Scorecard:** `docs/AFTERNOON_PLAYTEST_SCORECARD.md`
2. **Restore if messy:**
   ```powershell
   powershell -File scripts\restore_afternoon_snapshot.ps1
   ```
3. Snapshot lives at: `state/backups/pre_afternoon_playtest/`
4. Launch via existing `PLAY_SESSION` / console path (Mode A home = current intent: **Koom seize_lane** unless you override).
5. Grep infolog: `VA_RESULT` `VA_TENEBRIUM_` `VA_CAPTURE_` `VA_NODE_CLAIMED`
6. Success ≠ zero bugs — **want one more sortie** + coherent war.

Shop/Deploy pretty UI still **player-rig bot**. Kernel can settle Tnb/claims without it.

---

## Commands to re-play the sim yourself

```powershell
cd "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
$env:PYTHONPATH = "$pwd\tools"

python -m unittest tests.test_playtest_infra tests.test_kernel_phases -v

python tools\kernel_campaign_sim_v1.py --workspace . --sorties 8 --seeds 5 --seed 31 --write
python tools\quantum_bar_ai\strategic_seat.py --workspace . --sorties 8 --seeds 3 --seed 21 --write
python tools\fun_scorecard.py --workspace .
python tools\world_tick_v1.py --self-test
```

---

## Still queued (yurt river)

| Packet | Who |
|--------|-----|
| `pkt-bar-player-rig-hub-shop-deploy` | player-rig bot |
| `pkt-bar-mode-b-reload-travel` | **cleared** — session host Reload path + strategic_link atlas (2026-07-29) |
| `pkt-bar-cloud-shell-bake-real-dumps` | AWS / idle machine |
| `pkt-bar-lua-tenebrium-file-split` | maintainability |
| NEW: kernel-sim / strategic-seat / density-tick | **shipped this seat** — close or leave as “iterate fun” |

---

## Honest gaps before “LLM campaign is fun forever”

1. Strategic seat uses **local heuristic**, not Ant/Grok live (umwelt import optional; Ant path still works via package when env set).
2. fair_sim three-arc champion ≠ this kernel sim — two fidelity lanes; converging via shared result contract.
3. Human BAR is ground truth — sim can be “fun” while in-match still needs your feel.
4. Quest kinds still lean seize_lane; eco_raid appears via sim profile override + some maps.

---

*Walk done. Machine played the war a few dozen times. Your turn with BAR this afternoon.*
