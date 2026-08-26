# Outbound 45 — Overnight kernel phases (shipped + river queue)

**Date:** 2026-07-28  
**Seat:** wargen-grok (kernel / game rules)  
**Status:** Phases 1–5 **SHIPPED + tested**; Phase 6 **deferred with plan**; remainder **queued** in yurt work river

---

## What you asked

> build all phases in order and queue the rest into the yurt work river system. i'm going to sleep.

## Phases built (in order)

| # | Phase | Status | Artifacts |
|---|-------|--------|-----------|
| 1 | world_zone_graph + **quest gen** | SHIPPED | `tools/world_zone_graph.py`, `tools/quest_generator_v1.py`, `outbox/quest_batch.latest.json` |
| 2 | Sortie + Result **contract v2** | SHIPPED | `tools/contract_v2.py`, `data/contracts/*.v2.json`, engine adapters |
| 3 | Occupation shell-only + **scar memory** | SHIPPED | `apply_shell_scars`, gadget `shellScars` + `recordShellScar`, compiler lock |
| 4 | Tnb edge cases | SHIPPED | loan **HP quality** settle, `factionBanks`, result `loanUnitHp` |
| 5 | Mode A same-map session | SHIPPED | quest fallback, `sessionMode=same_map` on intent/order |
| 6 | Split campaign.lua | DEFERRED | method-table already modular; `include/va_tenebrium_README.md` for physical split |

## Tests

```text
76 tests OK  (kernel phases + world graph + sortie + full story engine suite)
```

```powershell
cd C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace
$env:PYTHONPATH = "$pwd\tools"
python -m unittest tests.test_kernel_phases tests.test_world_zone_graph tests.test_sortie_contract tests.test_verdance_story_engine_v1 -v
```

### Smoke

```powershell
python tools\quest_generator_v1.py --workspace . --map koom_valley --write --pick 1
python tools\contract_v2.py --workspace .
python tools\verdance_story_engine_v1.py intent --workspace .
# → mapId koom_valley, objective seize_lane
```

## Game / gadget deltas

- Result JSON adds: `loanUnitHp`, `shellScars`, `sessionMode`, `occupationModel`
- Shell unit deaths append scar events for campaign ledger
- Loan settle uses avg HP frac vs loaned smoking baseline

## Yurt work river (queued open packets)

| packet_id | Who |
|-----------|-----|
| `pkt-bar-player-rig-hub-shop-deploy` | **player-rig bot** |
| `pkt-bar-mode-b-reload-travel` | worker (after capability GO) |
| `pkt-bar-lua-tenebrium-file-split` | worker |
| `pkt-bar-cloud-shell-bake-real-dumps` | worker / AWS |
| `pkt-bar-capture-node-claims` | worker (after shells) |
| `pkt-bar-seven-map-shell-recipes` | worker |

Face: `yurt-sync/commons/vitals/work_packets/`  
Workbench claim (done kernel): `yurt-sync/workbench/wargen-grok-bar-kernel-overnight.toml`  
Mail: `yurt-sync/mail/for-bar-claude/0001-player-rig-work-queued.md`  
Mint helper: `scripts/mint_overnight_packets.py`

## Explicit non-work (this night)

- Hub HTML / shop UI / Deploy button (player-rig)
- Live BAR playtest (needs you)
- IconsAtlas / cloud real shell dumps
- Mode B map travel
- Capture/claim gameplay

## Operator wake checklist

1. Read this file + outbound 44  
2. `PLAY_SESSION` / `DEV_LAUNCH` on Koom seize_lane (intent already graph-picked)  
3. Infolog grep: `VA_TENEBRIUM_`, `VA_RESULT`, loan HP  
4. Leave player-rig packet for the other bot  
5. Cloud bake when you want real shells  

---

*Sleep well. Kernel river is flowing.*
