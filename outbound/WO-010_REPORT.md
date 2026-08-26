# WO-010 — Forward Extraction Distance

**Date:** 2026-07-24  
**Status:** BUILT

---

## Change

`extraction_zone_for` in `tools/verdance_story_engine_v1.py` no longer picks the **nearest** non-deploy zone (which collapsed extract into deploy neighborhood).

New policy:

1. Never deploy zone, never objective zone.
2. Prefer forward along deploy→target axis with distance ≥ ~0.14 normalized (~1500+ elmos on typical maps).
3. Fall back to farthest legal zone if none clear the floor.

## va_003 result (Koom Valley)

| Field | Zone |
|---|---|
| Deploy | `KOOM_NW_GREEN_SHELF` |
| Target | `KOOM_CENTRAL_FLUID_SCAR` |
| Extract | `KOOM_SE_GREEN_SHELF` |
| Distance | **~10,691 elmos** (far diagonal — clear of the 1500 floor) |

History beads already store `deploymentZoneId` from result JSON when the gadget emits it (engine path). Live play should confirm result markers include deploy id.

---

## Paths

| Item | Path | Len |
|---|---|---|
| Engine | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\tools\verdance_story_engine_v1.py` | 85 |
| Intent | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbox\next_mission_intent.json` | 85 |
| Report | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbound\WO-010_REPORT.md` | 87 |
