# Outbound Briefing 10: Current Pain Points & Initial Experiment Backlog

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Context:** Synthesis of User Playtest (Missions 1 & 2) and System Limitations

---

## 1. Executive Summary of User Feedback & Friction

Following the user's initial playtest of Mission 1 (Greenest Fields - Victory) and Mission 2 (Eye of Horus - Defeat via Ketha loss), five key pain points have been identified in the current game flow:

---

## 2. Friction Point Analysis

### 1. Hero Loss Hard Restart (`hero_lost_restart`)
- **Observation:** In Mission 2, Ketha was destroyed during the assault on the Cortex relay, causing an immediate hard match defeat and halting campaign progression (`processed: false`).
- **Friction:** A single hero death invalidates the entire sortie, forcing an immediate replay without permanent consequences, injury mechanics, or alternative story paths.
- **Narrative Opportunity:** Instead of instant failure, hero loss could trigger an emergency extraction objective, temporary field hospitalization, or scar penalties while allowing the campaign to move forward.

### 2. Deployment vs. Extraction Zone Overlap
- **Observation:** On several map intents (including Mission 1), the starting deployment zone and the final extraction zone are identical or adjacent.
- **Friction:** On destruction objectives, destroying the target structure immediately satisfies extraction if player units are still sitting in their starting base, rendering the extraction phase trivial.
- **UX Recommendation:** Force extraction zones to spawn across the map at a designated forward choke point or flank line to create a meaningful tactical retreat phase.

### 3. AI Commander Combat Suicide in Balance Probes
- **Observation:** During headless balance tests (`run_headless_balance_test.ps1`), `BARbarIAn aggressive` AI frequently walks its Commander unit directly into enemy turrets, triggering false-positive commander death defeats.
- **Friction:** Balance probe logs report defeat even when the AI destroyed all objective targets.
- **Tooling Fix:** Filter out commander death metrics when validating objective destruction in automated balance runs.

### 4. Presence Objective Feedback
- **Observation:** Objectives like `seize_lane` or `gate_control` rely on holding majority zone density for 30 consecutive seconds.
- **Friction:** The HUD widget does not clearly indicate zone boundary contours or progress percentage, leading to user confusion about why the timer reset.

### 5. High Resource Scarcity Penalty (`q7 = 0.9846`)
- **Observation:** Scarcity is currently near maximum (`q7 = 0.9846`), heavily reducing starting metal income.
- **Friction:** Players starting Mission 2 feel starved of build power from frame 1, compounding early game frustration.

---

## 3. Initial Candidate Experiment Backlog for Web GUI Adviser

The ground agent stands ready to execute the following experiments upon approval from the Web GUI Adviser:

```
+-----------------------------------------------------------------------------------+
| EXP-001: HERO INJURY & REFIT DYNAMICS                                            |
| Test replacing hard mission abort on hero loss with a "Hero Wounded" state,       |
| applying a temporary stress penalty and roster recovery timer instead of restart.|
+-----------------------------------------------------------------------------------+

+-----------------------------------------------------------------------------------+
| EXP-002: FORWARD EXTRACTION ZONE DISTANCE EXPERIMENT                              |
| Modify compiler (build_next_mission_v1.ps1) to force extractionZoneId to be at   |
| least 1500 world units away from deploymentZoneId.                               |
+-----------------------------------------------------------------------------------+

+-----------------------------------------------------------------------------------+
| EXP-003: BARB AI COMMANDER SAFETIES FOR HEADLESS PROBES                            |
| Add gadget override option in headless test mode to set player AI commander to   |
| defensive behavior, preventing suicide pushes in automated balance suites.        |
+-----------------------------------------------------------------------------------+

+-----------------------------------------------------------------------------------+
| EXP-004: ZONE PRESENCE HUD CAPTURE PROGRESS OVERLAY                              |
| Prototype visual zone border indicator and capture progress bar in                |
| gui_verdance_objectives.lua for presence objectives.                             |
+-----------------------------------------------------------------------------------+
```
