# Outbound Briefing 06: Scenario Compilation & Force Design

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Compiler Script:** [`scripts/build_next_mission_v1.ps1`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/scripts/build_next_mission_v1.ps1) (45 KB)

---

## 1. Scenario Compilation Workflow

When the story engine updates [`outbox/next_mission_intent.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/next_mission_intent.json), the compiler script `build_next_mission_v1.ps1` executes to produce a fully playable BAR mission:

```
[outbox/next_mission_intent.json]
                 │
                 ▼
[scripts/build_next_mission_v1.ps1]
                 │
   ┌─────────────┴─────────────┐
   ▼                           ▼
[mod/VerdanceAshes.sdd/     [data/scenarios/generated/
 singleplayer/missions/      next_mission_intent.playable.json]
 va_seed_current.lua]                  │
   │                                   ▼
   │                        [BAR Startscript Execution]
   └───────────────────────────────────┘
```

---

## 2. Force Architecture: Camp Rings & Objectives

Missions are compiled using a **Focal Camp Architecture**. Enemy forces do not spawn as generic spread-out armies; they are structured around an **objective centerpiece**:

```
           +---------------------------------------------+
           |           OUTER PATROL PERIMETER            |
           |   Armada Garrison Patrols (Defend/Screen)   |
           |                                             |
           |      +-------------------------------+      |
           |      |      INNER CAMP DEFENSES      |      |
           |      |  Turrets, Shields, Energy     |      |
           |      |                               |      |
           |      |    +---------------------+    |      |
           |      |    | OBJECTIVE CENTERPIECE|    |      |
           |      |    | (Cortex Relay / LRPC|    |      |
           |      |    |  / Synth Works)     |    |      |
           |      |    +---------------------+    |      |
           |      +-------------------------------+      |
           +---------------------------------------------+
```

### Centerpiece Objective Mapping

| Objective Type | Objective Centerpiece Target | Surrounding Camp Garrison |
|---|---|---|
| **`economy_disrupt`** | Cortex Fusion + Adv Solars + Converter Farm | Armada Garrison protecting Cortex synth works |
| **`strike_relay`** | Targeting Facility + Adv Radar + Fusion Plant | Cortex dealer relay garrison |
| **`destroy_key_structure`** | LRPC (Intimidator) + Fortification Walls | Heavy Armada Bastion Wing |
| **`seize_lane` / `gate_control`** | None (Zone presence capture) | Pure Armada Garrison (no eco centerpiece) |
| **`hive_clear_or_bypass`** | Raptor Hives + Spore Turrets | Swarm pressure (Raptors AI) |

> **Critical Design Principle:** Only the centerpiece structure is objective-tagged! Destruction missions are surgical strikes into a defended camp, NOT tedious full-base wipes.

---

## 3. World War Mechanics: Standing Factions & Merc Footholds

The standing conflict model in Verdance's Ashes features three active factions:

1. **Armada (Garrison Power):** Default holding force on all standard sector maps. Holds perimeter fortifications and key terrain.
2. **Null Mercs (Foothold Outsiders):** Outsider Legion-chassis mercenary crews in ash-grey null colors. Every non-PVE mission spawns a **Null Merc Foothold** on a flank perpendicular to the primary deploy-to-target axis.
   - **Alliance Threshold (`nullmercs >= 40.0`):** If player reputation with Null Mercs is \(\ge 40.0\), the merc foothold spawns as an **Allied Team** (`Ally` tag in startscript), fighting alongside the player!
   - **Compensation Scaling:** When mercs are allied, Armada defender forces scale \(\times 1.1\) to maintain tactical parity.
3. **Cortex (Contractor Pockets):** Cortex appears primarily as specialized contractor pockets (e.g., the dealer relay on `eye_of_horus`) and high-tech centerpiece targets protected by an Armada garrison.

---

## 4. Difficulty & Scale Coefficients

Enemy force size is dynamically computed during compilation:

\[
\text{Total Enemy Force Scale} = \text{expectedEnemyScale} \times \text{DifficultyCoefficient}(q6\_contested) \times \text{RampFactor}
\]

- **Ramp Factor:** Missions 1 & 2 apply an onboarding ramp (\(0.7\times\) on M1, \(0.85\times\) on M2).
- **Tier-2 Defense Upgrade:** At \(q6\_contested \ge 1.4\), the compiler automatically upgrades camp turrets from Tier-1 (Gauss/Plasma) to Tier-2 (Pop-up Heavy Turrets, Flak, and Shields).
