# Overnight Hive↔BAR 0.8.5 — bot runbook

**Luke does not run this.** Seats / detached bots / Task Scheduler arm the farm.  
Luke may later **read** the morning scorecard faces.

---

## Who starts it

| Actor | Action |
|-------|--------|
| Grok / seat bots | Launch detached overnight when work is owed |
| Organic swarm | `bar_swarm_bridge` fills more units when CPU free |
| Luke | Sleep / live; optional morning glance at faces |

No spring.exe. No IconsAtlas. Policy-only (`QBAI_NO_LLM=1`). Umwelt on PYTHONPATH (bots set this).

---

## Phases (bot-internal)

| Phase | What | Fail behavior |
|-------|------|----------------|
| A | Unit tests (proxy, UL, residual, arena) | **Stop** if red |
| B | Smoke proxy 2×1 both | Stop if crash |
| C | UL train loops | Continue with note |
| D | Long A/B difficulty sweep | Continue with note |
| E | Manifold gym if time remains | Optional skip |
| F | Residual hose + arena + morning scorecard | Always try |

Auto difficulty bump: if Phase B both styles meanWin ≥ 0.95, base difficulty += 0.25 for C/D.

---

## Morning faces (Luke may read)

```
outbox/overnight_hive_bar.latest.json
outbox/proxy_campaign.latest.json
outbox/hive_bar_residual.latest.json
outbox/hive_gym_arena.latest.json
app/brain/bar_brain_weights.json
app/brain/bar_brain_ul_state.json
docs/HIVE_BAR_RESIDUAL_BRIDGE.md
```

Also hive: `commons/vitals/bar_proxy_residual.latest.json`

---

## Pass criteria (bots assert; Luke can skim)

- Unit gate PASS  
- Residual honesty densifyBanned=true  
- At least one difficulty with barb harder than simple (or saturation noted)  
- ulUpdateCount > 0 after train phases  
- No spring hang  

---

## Seat-only launch note (not for Luke)

Scripts live at `OVERNIGHT_HIVE_BAR.bat` / `scripts/player/overnight_hive_bar.ps1` for **bot process spawn**. Do not paste them into human chat as “please run.”
