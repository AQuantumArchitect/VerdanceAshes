# Outbound 36 — Occupied-map raid loop (Arc A harmony)

**Date:** 2026-07-27  
**Status:** Implemented in compiler + campaign gadget (player seed rebuild required)

## Problem

Mission 1 felt right as a raid, but **continues felt fake**: empty grass, mock camps, soft clocks already dead. The map never felt like a living Armada energy landscape.

## Fantasy (player-facing)

1. Drop onto a map **already full of Armada eco** (solars, winds, converters) with static teeth.
2. **Raid the marked works** (~60% wreck), then **extract** before wrath piles on.
3. At debrief, pick **per objective**:
   - Raid another **pre-placed** wind/solar pocket already on the map, or
   - **Extract / leave the field** and bank the scar.
4. Same map continues **promote** living occupation — they do not wipe and rebuild toy camps.

Arc 2 inherits the same occupation idea: the field is a graph of scars, not a sequence of empty boxes.

## Implementation

| Layer | Change |
|-------|--------|
| `build_next_mission_v1.ps1` | Eco raid places **primary** works + **occupation pockets** on other energy zones |
| Seed | `mapOccupation[]`, `continueRules.promoteOccupationOnContinue` |
| Debrief picks | Prefer preplaced occupation nodes + **Extract leave** |
| Gadget | `promoteOccupationInZone` re-tags eco; does not clear next scar; re-arms soft clock |
| Kit (prior) | Phobos + rez + Wheelies; Vane in Karkinos; beefy primary defenses |

## Soft rules

- Soft clock is a **real end** (gadget). Continues set `requiredFrames = now + budget`.
- Hot extract only on Arc A (`escalation = off`).
- No SimpleAI on eco occupation (static world).

## What “quantum” still means here

Occupation layout is **authored zone + campaign forces + craft scale** today. The quantum/proxy story layer remains the fair belief graph for *how hard* a scar feels and which pick the proxy prefers — not a substitute for a dead map. Live occupation is the substrate; quantum is the mood and pick pressure on top.

## Playtest checklist

1. M1 Greenest: see multiple eco clusters, not one lonely farm.
2. Wreck ~60% of **marked** works → extract available.
3. Debrief: “Raid North Desert…” / “Raid South…” / “Extract leave”.
4. Pick a raid: zone already has eco; objective retargets; soft clock resets.
5. Pick extract: session stops soft-continue (leave BAR / host advances).

## Next rings

- **Done / superseded direction:** [37_LIVING_SHELL_TEMPLATES.md](37_LIVING_SHELL_TEMPLATES.md) — SimpleAI-grown frozen shells + contact wrath.
- Tag occupation damage into zone memory so later re-entry sees scars.
- Arc 2: expand nodes (mex + labs) on the same occupation graph.
- Proxy story panel reads `mapOccupation` + live chapter, not archive clears.
- Capture missions reworked only after shells exist (claim living nodes).
