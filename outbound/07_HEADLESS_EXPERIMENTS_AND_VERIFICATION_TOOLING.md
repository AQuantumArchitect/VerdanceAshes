# Outbound Briefing 07: Headless Experiments & Verification Tooling

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Primary Test Scripts:** [`scripts/run_headless_balance_test.ps1`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/scripts/run_headless_balance_test.ps1), [`scripts/verify_campaign_arc.ps1`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/scripts/verify_campaign_arc.ps1)

---

## 1. Overview of Headless Verification Suite

The workspace features a comprehensive suite of headless testing tools. These allow the Boots-on-the-Ground Agent to execute fast, automated experiments, probe AI behavior, verify objective automation, and simulate multi-mission campaign arcs **without opening the BAR GUI window**.

---

## 2. Key Headless Test Entrypoints

### A. Mission Balance Probe (`run_headless_balance_test.ps1`)
Runs a generated mission headlessly with an AI taking the player seat (Team 0) to evaluate mission solvability and difficulty tuning.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_headless_balance_test.ps1 `
  -ScenarioPath data\scenarios\generated\next_mission_intent.playable.json `
  -Variant alpha_player `
  -PlayerControllers simple,barbarian_aggressive `
  -SimFrames 21600 `
  -TimeoutSeconds 2400
```

- **Player AI Seats Tested:**
  - `simple`: Passive baseline AI.
  - `barbarian_aggressive`: High-pressure offensive AI.
- **Target Balance Horizon:** `barbarian_aggressive` should gain clear map advantage or complete objectives within the simulation horizon (~15-20 min / 21600 frames), whereas `simple` should stall out.

### B. Campaign Arc Verification (`verify_campaign_arc.ps1`)
Chains \(N\) missions together in-memory, running headless matches, parsing telemetry, and advancing state to verify multi-mission progression and graph stability.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_campaign_arc.ps1 -Missions 8
```

- Produces: [`reports/arc_verify.latest.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/reports/arc_verify.latest.json)

### C. Objective Automation Verification (`verify_objective_automation.ps1`)
Launches a fast headless match into `mod/VerdanceAshes.sdd`, executes the cheat command `/luarules vatest_killobjective`, and verifies that the gadget correctly detects objective destruction, triggers extraction, and emits clean `VA_RESULT_JSON_*` markers.

### D. Python Unit Test Suite (`python -m unittest discover tests`)
Runs 52 unit tests covering Jacobi spectral decomposition, idempotency ledgers, story event generation, roster level progression, and intent compilation. **(Current status: 52/52 PASS)**.

---

## 3. Interpreting Headless Balance Logs

Headless runs write detailed logs under [`headless_runs/`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/headless_runs/).

When inspecting balance probe logs:
1. **Infolog Marker Extraction:** Look for `VA_RESULT_JSON_*` to determine if victory or defeat was achieved.
2. **Objective Target Down Count:** Check `VA_OBJECTIVE_TARGET_DOWN` lines in `infolog.txt`.
3. **AI Caveat Warning:** BARb AI (`barbarian_aggressive`) frequently walks its Commander unit into the frontline, causing a `hero_lost` or Commander death defeat. Commander deaths in AI balance probes are often an AI pathfinding artifact — always cross-reference `VA_OBJECTIVE_TARGET_DOWN` counts to verify actual tactical progress!
