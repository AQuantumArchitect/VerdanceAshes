# Outbound Briefing 04: Story Engine & Graph Scalars

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Primary Engine File:** [`tools/verdance_story_engine_v1.py`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/tools/verdance_story_engine_v1.py) (105 KB)

---

## 1. Overview of Python Story Engine

The Python story engine (`verdance_story_engine_v1.py`) is the campaign brain. It operates statelessly and idempotently:

1. **Ingest Result:** Accepts match results (`inbox/latest_va_result.json`) and telemetry packets.
2. **Idempotency Ledger Check:** Checks `campaignId|missionId|missionNumber|status` against [`ledger/processed_results.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/ledger/processed_results.json). If already processed, it aborts state mutation.
3. **Graph Evolution:** Mutates campaign graph scalars based on match outcomes and telemetry spectra.
4. **World Reading & Front Line Decay:** Moves map front lines across the 7-map pool.
5. **Roster & Companion Management:** Updates Commander level, perk selection, cadre unit survival, and companion morale/stress.
6. **Intent Generation:** Generates [`outbox/next_mission_intent.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/next_mission_intent.json) and [`outbox/story_events.latest.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/story_events.latest.json).

---

## 2. Mathematical Graph Scalars (`q0` to `q7`)

The campaign world state is represented by six core scalar values normalized between `0.0` and `1.0`:

| Scalar | Name | Range Interpretation | Campaign Effect |
|---|---|---|---|
| **`q0_armada_cortex`** | Faction Dominance Ratio | `0.0` = Full Armada ascendant<br>`1.0` = Full Cortex ascendant | Determines which faction occupies territory offscreen, enemy base defense tech levels, and defector availability. |
| **`q2_void_structure`** | Frontier Disorder & Volatility | `0.0` = Ordered/stable line<br>`1.0` = High disorder/wild space | Controls Raptor hazard spawns and secondary objective chaos. |
| **`q6_contested`** | Line-World Instability | `0.0` = Pacified sector<br>`1.0` = Maximum contest | Acts as enemy force scale multiplier (`expectedEnemyScale`). At `q6 >= 1.4`, enemy bases gain Tier-2 heavy defenses. |
| **`q6_independent`** | Clan Sovereignty | `0.0` = Dependent / no reserve<br>`1.0` = Sovereign Ashwalker warband | Floored by player roster cadre size. High values unlock Ashwalker reinforcement drops. |
| **`q7_resource_scarcity`** | Economic Scarcity | `0.0` = Abundant resources<br>`1.0` = Severe metal/energy drought | Modifies player economic floor (`resourceModifier = 1.0 - (q7 * 0.2)`). Thins starting metal income under scarcity. |
| **`pathSignalA/B/C`** | Campaign Orientation | `A` = Armada alignment<br>`B` = Ashwalker autonomy<br>`C` = Void / Rogue alignment | Tracks cumulative choices, opening specific narrative pathways and companion reactions. |

---

## 3. Companion System & Ketha's Voice

- **Companion (Ketha):** Ashwalker scout captain and primary tactical adviser.
- **Companion State Attributes:**
  - **Morale (0-100):** Rises on clean extractions (+5) and objective destruction (+3); drops on hero injuries (-15) or heavy unit losses.
  - **Stress (0-100):** Rises during prolonged combat, contested extractions (+10), or hero damage. High stress triggers grim dialogue.
  - **Loyalty (0-100):** Influenced by alignment choice (Path B boosts Ketha's loyalty).

### Voice Engine Engine (`data/story/ketha_voice.json`)
Briefing lines and debrief responses are compiled deterministically per campaign moment using `ketha_voice.json`.

Sample Briefing Generation Logic:
- `situation`: Map condition summary ("Fast ground. Whoever hesitates here feeds the other side's map.")
- `objective`: Primary mission goal ("Cut the relay and the chain forgets a link. Then leave.")
- `war`: Faction context ("Null flags on our flank today. Paid guns, pointed the right way. Use them.")
- `world`: Macro conflict state ("The Cortex ascendancy is real. We fight uphill until that changes.")
- `pressure`: Scarcity / hazard warning ("Metal is short everywhere. Waste nothing, not even wrecks.")
- `path`: Clan reaction ("The clans are listening. That matters more than the map says.")

---

## 4. Debrief Candidate Matrix

The engine generates outcome-keyed debrief lines based on match results:
- **`victory`**: "Done is done. Mark the map and move."
- **`victoryClean`**: "No one chased us out. We simply finished."
- **`partial`**: "Not a win. Not a loss. A hinge."
- **`defeat`**: "The map will remember this. So will I. Differently."
- **`defeatCommander`**: "The command walker is scrap. The command is not. Rebuild."
- **`defeatHero`**: "The line does not bury its own on a maybe. Refit. Go back."
- **`objectiveDestroyed`**: "That target stays gone. The rest of the front will learn around the hole."
