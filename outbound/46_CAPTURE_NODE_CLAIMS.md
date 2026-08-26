# Outbound 46 — Capture = claim living shell node under regrow pressure

**Date:** 2026-07-28  
**Status:** SHIPPED (kernel + gadget + hub contracts; live BAR play residual)  
**Packet:** `pkt-bar-capture-node-claims`  
**Extends:** [36](36_OCCUPIED_MAP_RAID.md), [37](37_LIVING_SHELL_TEMPLATES.md), [39](39_SEVEN_MAP_GROW_RATES.md) Phase D, [44](44_KERNEL_GRAPH_AND_OCCUPATION_LOCK.md)

---

## Fantasy

Capture is **not** standing on empty grass.

1. Map is a **living shell** (frozen eco + teeth).
2. **Clear** the primary pocket — wreck ~60% of shell eco **and** static teeth.
3. **Hold** the cleared node while **regrow pressure** tries to retake it (live waves).
4. **Claim** flips zone control to patron.
5. **No free Tnb mint** — claim never invents Tenebrium; liquid Tnb is reclaim / rare victory scavenge only.

---

## Match (gadget)

| Piece | Behavior |
|-------|----------|
| Kinds | `seize_lane`, `gate_control`, `hold_plateau` |
| Mode stamp | `objective.captureMode = "clear_hold_shell"` |
| Clear | ≥ `CLEAR_FRACTION` (0.6) of primary shell eco+teeth tagged as objectives |
| Hold | Presence + no enemy combat for `requiredHoldFrames` (default 900 = 30s) |
| Regrow | During hold: `spawnWave` pulses labeled `regrow_pressure` |
| Complete how | `node_claimed` (not empty `zone_held` when shell armed) |
| Result fields | `nodeClaimed`, `pocketCleared`, `capturePhase`, `regrowWaves`, `freeTnbMint:false` |

HUD: `CLEAR POCKET` → `HOLD UNDER REGROW` → `NODE CLAIMED`.

Infolog: `VA_CAPTURE_ARMED` · `VA_POCKET_CLEARED` · `VA_REGROW_PRESSURE` · `VA_NODE_CLAIMED`

---

## Campaign / hub

| Piece | Path |
|-------|------|
| Pure rules + contracts | `tools/capture_node_claims.py` |
| Abstract scar regrow | `apply_abstract_regrow` (story engine + module) |
| Quest stamp | `captureMode` / `freeTnbMint:false` on seize/gate/plateau |
| Hub surface | `hub_state.captureContracts[]` + `flags.captureNodeClaims` |
| Commerce | `tenebriumOnZoneFlip` chance **0** |
| Contract v2 | `captureMode=clear_hold_shell`, `freeTnbMint=false` |

---

## Compiler

`build_next_mission_v1.ps1` stamps:

- `objective.captureMode = clear_hold_shell` for presence kinds  
- `missionBase.capture = { mode, clearFraction, holdFrames, regrowPressure, freeTnbMint:false }`  
- Mission card text describes clear + hold (not empty grass)

---

## Tests

```powershell
cd C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace
$env:PYTHONPATH = "$pwd\tools"
python -m unittest tests.test_capture_node_claims tests.test_kernel_phases tests.test_sortie_contract -v
python tools\capture_node_claims.py --workspace . --map koom_valley --write
```

---

## Residual (honest)

- **Live BAR play** of clear→hold→claim not exercised this drop (needs headed/headless mission).
- Shell unit subtract-on-spawn from scar ledger still soft (ledger + abstract regrow; full template filter later).
- Hub HTML deploy UI is player-rig seat (contracts are data-ready).

---

*End outbound 46.*
