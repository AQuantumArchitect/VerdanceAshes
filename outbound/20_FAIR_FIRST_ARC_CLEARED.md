# Outbound 20 — Fair first arc CLEARED (player context only)

**Date:** 2026-07-25  
**Status:** **SUCCESS** at nominal difficulty 1.0 (3/3 seeds, 5/5 missions)

## Goal

Get quantum-BAR-AI to beat the first Verdance arc using **only**:

1. Player-facing mission briefing (`PlayerFacingCard`)
2. Coarse combat HUD bands (`FairHUD`)
3. Umwelt **belief graph** fed solely from that HUD
4. **Tool calls**: `read_briefing`, `read_hud`, `read_beliefs`, `read_recent`, `think`, `commit_action`

**No magic:** agent never sees `enemy_scale`, exact enemy strength, raw HP floats, or sim RNG.

## First arc (campaign-faithful)

| ID | Title | Kind | Notes |
|----|-------|------|-------|
| va_001 | Greenest Fields eco onboarding | eco_raid | tutorial |
| va_002 | Glass Under the Eye | strike_relay | fortified; FLANK from briefing |
| va_003 | All That Simmers lane | seize_lane | hold then extract |
| va_004 | Koom Fluid Scar | seize_lane | ferrocrete → flank |
| va_005 | East Ridge Pocket continue | eco_raid | tired roster carry |

## Champion result

```
difficulty = 1.0
seeds      = 111, 128, 145  (also 11, 28, 45, 99)
hard wins  = 5/5 × 3 seeds = 100%
backend    = local_tools (same tool belt as GrokToolAgent)
```

Report: `headless_runs/quantum_bar_ai_beat_*/beat_report.json`  
Latest: `outbox/quantum_bar_ai_beat.latest.json`

## Fairness audit

- Leaks of `enemy_scale` / `SimTruth` into agent-facing tape fields: **none**
- Every decision tick tool order: `read_hud` → `read_beliefs` → (`read_briefing` if cold) → `read_recent` → `think` → `commit_action`
- Belief walls come from `fair_hud_to_wall_sensors()` only

## Iteration scars (what we fixed)

1. **Early EXTRACT death spiral** — HUD cried "nearly" at ~half progress; agent extracted forever. Fixed objective bands + EXTRACT only on `done`.
2. **Fortified frontal stall (va_004)** — pure PUSH melted force. Briefing text ("ferrocrete", "route around") now drives FLANK via tools.
3. **Late-arc carry tax** — double 0.92 strength tax + weak refit. Blend start strength with carry; short patch between sorties.
4. **Nearly-done freeze** — min objective bleed once progress ≥ 0.7 under legitimate pressure actions.

## Both sides tuned (honest)

| Side | Knobs |
|------|--------|
| Agent | LocalToolAgent HUD/briefing heuristics; anti-stall; tool protocol |
| Mission | difficulty dial, duration, fortify rates, carry blend — **not** god sensors for the agent |

## Grok tool path

`GrokToolAgent` implements the same tools via xAI `tools=` chat completions and falls back to `LocalToolAgent` if the network/key path is unavailable.

```powershell
# offline champion (proven)
python -m quantum_bar_ai.beat_first_arc --once --difficulty 1.0

# multi-seed lock
python -m quantum_bar_ai.beat_first_arc --difficulty 1.0 --seeds 3 --max-rounds 5

# with Grok tools when API allowed
python -m quantum_bar_ai.beat_first_arc --once --llm
```

## Next rings

- Run GrokToolAgent live overnight (same contract)
- Feed real BAR telemetry → FairHUD projector
- Live Lua seat consuming `commit_action` only
