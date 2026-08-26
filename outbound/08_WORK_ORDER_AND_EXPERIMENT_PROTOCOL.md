# Outbound Briefing 08: Work Order & Experiment Protocol

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Ledger Location:** [`.agents/WORK_ORDER_QUEUE.md`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/.agents/WORK_ORDER_QUEUE.md)

---

## 1. Interaction Model Overview

The user's workflow separates responsibilities into two distinct agents:

```
+-------------------------------------------------------------------------+
|                          BIG BRAIN WEB GUI BOT                          |
|  - Conducts discussions, planning, story design, map layout, & UX.       |
|  - Translates user rants and feedback into structured WORK ORDERS.      |
|  - Reviews experiment reports returned by the ground agent.             |
+-------------------------------------------------------------------------+
                                    │
                                    │ Issues Work Orders & Experiments
                                    ▼
+-------------------------------------------------------------------------+
|                  BOOTS-ON-THE-GROUND EXECUTION AGENT                    |
|  - Explores local BAR workspace, code, Lua gadgets, and scripts.        |
|  - Executes headless BAR experiments, unit tests, and balance runs.     |
|  - Mutates code/data and generates clean outbound documentation.        |
+-------------------------------------------------------------------------+
```

---

## 2. Work Order Format & Schema

When the Web GUI Adviser bot creates a Work Order for the ground agent, it should follow this standardized format:

```markdown
# Work Order: [WO-XXX] [Short Descriptive Title]

## 1. Objective & Rationale
Brief description of the problem, UX issue, or narrative feature to be implemented/tested.

## 2. Target Component & Files
- [ ] Story Engine: `tools/verdance_story_engine_v1.py`
- [ ] Lua Gadget / UI: `mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_campaign.lua`
- [ ] Scenario Compiler: `scripts/build_next_mission_v1.ps1`
- [ ] Authored Zone Maps: `data/zone_maps/authored/*.json`
- [ ] Voice Tables: `data/story/ketha_voice.json`

## 3. Requested Experiment / Code Action
Specific instructions for headless balance runs, script modifications, or map re-configurations.

## 4. Verification & Acceptance Criteria
- [ ] Headless run command to execute.
- [ ] Expected infolog output or telemetry markers.
- [ ] Unit tests that must remain green (`python -m unittest discover tests`).

## 5. Expected Output Document
Path in `outbound/` or `.agents/` where the ground agent should report results.
```

---

## 3. Work Order Execution Lifecycle

1. **Queueing:** Work Order is appended to [`.agents/WORK_ORDER_QUEUE.md`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/.agents/WORK_ORDER_QUEUE.md) with status `PENDING`.
2. **Execution:** The ground agent updates status to `IN_PROGRESS`, executes requested experiments, modifies code/data as required, and runs verification commands.
3. **Log & Telemetry Audit:** The ground agent parses infolog markers and JSON output silently.
4. **Report & Completion:** Results are logged in [`.agents/EXPERIMENT_REGISTRY.md`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/.agents/EXPERIMENT_REGISTRY.md), outbound briefings are updated, and status is set to `COMPLETED`.
