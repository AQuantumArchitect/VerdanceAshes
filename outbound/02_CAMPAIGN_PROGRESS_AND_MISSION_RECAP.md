# Outbound Briefing 02: Campaign Progress & Mission Recap

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Active Campaign:** `verdance_ashes`  
**State File:** [`state/campaign_state.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/state/campaign_state.json)

---

## 1. Current Campaign Status

The player has launched into campaign **`verdance_ashes`** and attempted the first two sorties:

- **Current Mission Number:** 2
- **Active Mission ID:** `va_002` ("Glass Under the Eye")
- **Path Signal:** `B` (Ashwalker pragmatism / balanced expansion)
- **Campaign Clock:** 2.03 total combat minutes
- **Companion Status (Ketha):**
  - XP: `0.04`
  - Morale: `74.0` / 100
  - Loyalty: `75` / 100
  - Stress: `7.0` / 100

---

## 2. Mission 1 Recap: Greenest Fields (`va_001`)

- **Map:** `greenest_fields` (No-metal economy / converter benchmark)
- **Title:** "Greenest Fields: Economy Onboarding"
- **Objective:** `economy_disrupt` (Destroy Armada Energy Works at `GF_ARMADA_ENERGY_WORKS`)
- **Outcome:** **VICTORY**
- **Duration:** 2.03 minutes
- **Extraction:** Clean (`GF_CENTRAL_OPEN_GRASSLAND`)
- **Graph Delta Applied:**
  - `q6_contested`: `-0.025`
  - `q6_independent`: `+0.035`
  - `pathSignalB`: `+0.08`
- **Story Tags Generated:** `["victory", "extract-clean", "objective-destroyed", "path-b", "ashwalker-gain"]`
- **Summary:** The player successfully established early build power, pushed across the central grassland, and destroyed the primary Armada energy converter farm. Extraction was clean and unhindered.

---

## 3. Mission 2 Recap: Eye of Horus (`va_002`)

- **Map:** `eye_of_horus` (MIRV Glassed Crater)
- **Title:** "Glass Under the Eye"
- **Objective:** `strike_relay` (Destroy Cortex Dealer Relay at `EOH_CORTEX_DEALER_RELAY` in zone `EOH_SE_CORTEX_POCKET`)
- **Forces Present:** Player Ashwalkers vs Cortex Dealer Relay (Objective) + Armada Perimeter Garrison + Null Mercs Foothold on Flank.
- **Outcome:** **DEFEAT / HARD RESTART** (`hero_lost_ketha`)
- **Reason Code:** `hero_lost_restart`
- **Story Event Output:** [`outbox/story_events.latest.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/story_events.latest.json)
  - *Warning Tag:* `hero-lost`, `mission-restart`
  - *Warning Text:* "A mission-critical hero was destroyed beyond recovery. The sortie does not stand - refit and go again."
  - *Ketha Dialogue:* **"That name is not going on the wall today. Run it again."**
- **Advancement State:** `processed: false` in [`outbox/advance_report.v1.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/outbox/advance_report.v1.json). The story engine enforces hero survival — losing Ketha triggers a refit request and halts graph mutation until the sortie is successfully re-played or resolved.

---

## 4. Current Campaign Graph & Reputation State

```json
{
  "graph": {
    "q0_armada_cortex": 0.7025,
    "q2_void_structure": 0.2066,
    "q6_contested": 0.825,
    "q6_independent": 0.35,
    "q7_resource_scarcity": 0.9846,
    "pathSignalA": 0.0,
    "pathSignalB": 0.18,
    "pathSignalC": 0.0
  },
  "reputation": {
    "armada": 42,
    "cortex": 21,
    "clans": 52.0,
    "nullmercs": 44.0,
    "sev": 50
  }
}
```

### Key Graph Interpretations:
- **`q0_armada_cortex` (0.7025):** Cortex remains ascendant across the front. The player's strike on the dealer relay is intended to sever Cortex command channels.
- **`q7_resource_scarcity` (0.9846):** Scarcity is extremely high across the sector, thinning metal income and building power floors.
- **`nullmercs` Reputation (44.0):** Above the 40.0 alliance threshold! Null Merc footholds are currently deployed as **allied units** alongside player forces on Mission 2.
- **Player Roster:**
  - Commander: Ash-Captain Vane (Level 1, XP 54.0)
  - Cadre Units: 1 Legion Centurion (`legcen`), 6 Legion Ballistas (`legbal`), 1 Karkinos (`legkark`), 4 Rezbots (`legrezbot`).
  - Active Heroes: Vane (`legbal`, mission-critical) and Ketha (`legcen`, mission-critical).
