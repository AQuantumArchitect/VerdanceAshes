# Outbound 19 — quantum-BAR-AI (umwelt player proxy)

**Date:** 2026-07-25  
**Status:** MVP shipped (sim seat + mood graph + Grok brain + early-arc suite)

## What this is

A **player proxy** that plays Verdance strike missions using:

1. An **umwelt belief field** (`tools/quantum_bar_ai/world.py`) — mood axes adapted from yurt-mood.
2. A **rule policy** (always on) + optional **Grok/xAI brain** (`brain.py`).
3. A **headless abstract combat sim** for the first several **no-base-building** missions.
4. A **BAR seat plan** mapper that picks `simple` vs `barbarian_aggressive` for real headless A/B.

## Why sim first

spring-headless + BARbarIAn already probes balance, but it cannot express
mood-conditioned micro-decisions (probe vs flank vs extract). The abstract sim
lets us iterate the **decision graph** in seconds, keep comprehension across
missions (field save/load), then promote a controller plan into BAR.

## Early arc cards

| ID | Map | Kind | Notes |
|----|-----|------|-------|
| va_sim_001 | greenest_fields | eco_raid | tutorial soft raid |
| va_sim_002 | all_that_simmers | seize_lane | fortified hold |
| va_sim_003 | koom_valley | strike_relay | harder strike |
| va_sim_004 | koom_valley | eco_raid | same-map continue carry |
| va_sim_005 | koom_valley | seize_lane | stress test |

Hero HP / force **carry** across missions when not wiped (seamless continue fiction).

## How to run

```bat
RUN_QUANTUM_BAR_AI_SUITE.bat
REM or policy only:
powershell -File scripts\run_quantum_bar_ai_suite.ps1 -NoLlm -Missions 3
```

Artifacts: `headless_runs/quantum_bar_ai_<stamp>/`, `outbox/quantum_bar_ai_suite.latest.json`.

## Iteration targets (quantum-BAR-AI loop)

1. **Policy weights** — if suite hints say over-push / over-hold, tweak `policy.py`.
2. **Sim rates** — if easy missions always die, retune `sim.py` enemy_scale effects.
3. **LLM cadence** — `--llm-every 4` keeps cost low; drop to 1 for deep playtests.
4. **BAR A/B** — take `bar_seat_plan.player_controller` into `run_headless_balance_test.ps1`.
5. **Next ring** — Lua debugcommands / custom AI that consumes seat actions live.

## Hive contract (from umwelt scars)

- Policy/LLM outputs are **claims** (η=0.25), not ground truth.
- Sim telemetry is **wall** (η=0.40).
- Mission verdict is **referee** (η=0.92).
- Never let fluent LLM confabulation write high-η state.

## Shippability

| Audience | Path |
|----------|------|
| Dev team | Run suite, paste `suite_summary.json` + iteration_hints |
| Community (soon) | Package policy-only demo + story of the five cards; BAR play needs existing mutator zip |
| Reddit/Discord | "AI proxy plays the early Verdance raid arc — mood graph + Grok" + summary verdicts |

## Open follow-ups

- [ ] Feed real `bar_zone_telemetry.latest.json` into `pack_wall_sensors`
- [ ] umweltd world registration under yurt (`worlds/verdance_proxy`) for multi-agent hive
- [ ] Live Lua seat: action → `Spring.GiveOrder` / debugcommands
- [ ] Wound/scar carry matching campaign_state heroes
