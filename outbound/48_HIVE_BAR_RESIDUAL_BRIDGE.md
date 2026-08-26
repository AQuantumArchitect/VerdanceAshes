# Outbound 48 — Hive ↔ Quantum-BAR Residual Bridge (v0.8.6 player-proxy muscle)

**Status:** shipped; bots own runtime  
**Date:** 2026-08-02  

## Law for humans

**Luke does not run CLI for BAR testing.**  
Play path = `PLAY.bat` when he wants to play.  
Test / train / residual / organic fill = swarm bots only.  
Human seal `pkt-bar-playtest-s6-retune` stays human-only.

## What shipped

Thin residual bridge so **player proxy** (quantum-BAR-AI in player seat) is informed by swarm/umwelt learning without a god-brain. **Muscle is node-agnostic** (wargen or roc when free+capable).

| Piece | Path | Who runs |
|-------|------|----------|
| UL pilot (`width_action`) | `tools/quantum_bar_ai/bar_brain_ul.py` | bots |
| Residual hose (`ran_on`) | `tools/hive_bar_residual_v1.py` | bots |
| Gym arena | `tools/quantum_bar_ai/hive_gym_arena.py` | bots |
| Proxy train+hose | `tools/proxy_campaign_v1.py` | bots |
| Overnight harness | `overnight_hive_bar.ps1` | bots / seats |
| Muscle auction | `player_proxy_muscle.py` | bots |
| Organic idle | `bar_swarm_bridge` + Task `Wargen-BarSwarmOrganic` | free capable muscle |
| Docs | `docs/HIVE_BAR_*`, `BAR_SWARM_ORGANIC`, `PROXY_CAMPAIGN`, HOME | Luke reads |

## Laws held

- Fair-room only for agent  
- BAR densify **banned** (n_obs wall 15)  
- Bidirectional residual files, not merged brains  
- Free-CPU rest when busy  
- Run where free and capable (host-agnostic)  
- Human seals never bot-cleared  

## Faces (Luke may skim)

- `outbox/overnight_hive_bar.latest.json`  
- `outbox/hive_bar_residual.latest.json` (`ran_on`, `kind=player_proxy`)  
- `outbox/hive_gym_arena.latest.json`  
- `app/brain/bar_brain_ul_state.json`  
- hive `bar_proxy_residual.latest.json`  
- hive `player_proxy_mesh.json`  
- hive `muscle/*_player_proxy.json`  

## Next seals (not freeable by bots alone)

- Human playtest scorecard → `pkt-bar-playtest-s6-retune`  
- Optional live umweltd registration of verdance_proxy  
- Expand UL beyond `width_action` if pilot proves out  
