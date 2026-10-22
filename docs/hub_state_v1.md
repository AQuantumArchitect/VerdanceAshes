# hub_state — the hub's JSON

`tools/build_hub_state_v1.py` builds it from `state/campaign_state.json`, the belief frame (`outbox/intel.latest.json`), the zone graph and the commerce catalog, and writes `app/showoff/hub_state.json` (+ `hub_state.embed.js` for file:// opens). The kernel serves it at `GET /api/hub-state` and rebuilds it after every stamp and every homecoming.

**Law.** Everything in it is the company's belief or the company's own books. No field is derived from the truth frame or another faction's mind. Enemy economies, true controllers and the other minds' pictures are not in this file; the dev-only routes that expose them refuse unless `devMode` is on.

## Top level

| Key | What |
|---|---|
| `schemaVersion`, `generatedAt`, `campaignId`, `missionNumber`, `arc`, `seed` | Identity. |
| `theater` | The map the next Drop is on: `mapId`, `zones[]` (below), `openTargets`, `intelByZone`. |
| `belief` | The company's belief over every zone it knows (`zones{zoneId→row}`, `counts{current,stale,dark}`, `surprise[]` from the last homecoming, `asOfMinute`). Theater zones are the same rows filtered to one map. |
| `camp` | Camp time and people: `clockMinutes`, `people{heroId→{where: camp\|posted\|transit\|field, zoneId, wounded, eta}}`, `nextPadZoneId/MapId` (a destination chosen at the last manifest), `homeZoneId/MapId`, `lastManifest`. |
| `exposure` | Our side of the mirror only: per faction, which of our holdings they `known`/`suspected`/`blind` on, and `ofOurs` (a fraction). Never their beliefs about the world. |
| `aces[]` | Heroes: `id, name, rank, level, status, wounds, scars, bonds, loadout, unitDef, campaignXp, deployable, where`. `deployable` is false for anyone posted, in transit or left in the field. |
| `company`, `companion`, `reputation`, `supportWeb`, `commerce`, `tenebrium`, `bay` | The company's books: people, standing, shelves, bag, Tenebrium bank. |
| `captureContracts[]`, `claimedNodes`, `nodeClaims`, `captureMode`, `homeCamp`, `homeEval` | Open contracts and holdings. `against` on a contract is the *believed* holder. |
| `history[]` | Beads: one per sortie, with `manifest`, verdict, map. |
| `lastResult` | The homecoming card: `verdict` (victory\|partial\|defeat\|abandon\|incomplete), `headline`, `reasonHint`, `tokens`, `manifest`. |
| `narrative`, `tagline`, `node`, `pathSignal`, `graph`, `graphPressure`, `spectral`, `campaignRho`, `occupationModel` | Readings face, story node, and the company's own belief-derived pressure summaries. |
| `features`, `flags`, `sessionMode`, `sessionHomeMap` | Hub switches. |

## A zone row (`theater.zones[]` and `belief.zones{}`)

| Field | Meaning | Paints |
|---|---|---|
| `zoneId`, `label`, `mapId` | Identity | — |
| `believed` | `ours` \| `held` \| `empty` \| `dark` \| `unsure` | fill kind |
| `control` | `ashwalkers`, a faction name (who we last **saw** holding it), `held`, `empty`, `unknown` | fill colour (`--f-*`) |
| `confidence` | 0..1 | fill alpha |
| `state` | `current` \| `stale` \| `dark` | outline: solid / dashed / hairline + `?` |
| `ageMin`, `source` | How old the word is, where it came from | tooltip |
| `threat` | Believed threat 0..1 | threat bar |
| `surprise` | Last homecoming's contradiction here, if any (`believed`, `found`, `surprise`, `eta`) | ✗ / ○ |
| `people[]` | Heroes posted here or left here (`heroId, name, where, wounded`) | ⚑ |
| `holding` | Structures we left here (count) | ■ |
| `openTarget`, `preferred`, `claimed`, `hazard` | Contract / legality hints | rings |

## The deploy plan (`POST /api/deploy`)

```json
{ "schemaVersion": "verdance-deploy-plan/1.0",
  "mapId": "the_rock_jungle",
  "deployAces": ["vane", "ketha"],
  "marks": { "deployZoneId": "TRJ_SW_LANE", "captureZoneIds": ["TRJ_C_GATE"], "secondaryCaptureZoneIds": [] } }
```

One pad: `extract = deploy` always (the stamp normalises it; there is no separate extraction zone). Legality is judged from belief in `tools/stamp_deploy_plan_v1.py`: ours, or a rim zone believed empty/dark/unsure with threat ≤ 0.4, or `camp.nextPadZoneId`. An illegal zone is refused with the belief sentence ("believed held by Armada (88%)").

Stamp → `outbox/next_sortie_order.json` → story intent (`outbox/next_mission_intent.json`, with `intel` = the company's belief) → `generated/va_intel_current.lua`, `va_pad_current.lua`, `va_current.lua` → BAR. The kernel owns launch and ingest (`tools/verdance_kernel/sortie.py`).

## Files beside it

| File | Written by | Read by |
|---|---|---|
| `outbox/intel.latest.json` | belief fold (homecoming, camp clock) | `hub_belief_v1`, `intel_lua_v1` |
| `outbox/divergence.latest.json` | perspectives worker | `/api/exposure` (company side only) |
| `outbox/readings.latest.json`, `occasions.latest.json`, `chronicle.latest.json` | readings | hub narrative / chronicle |
| `outbox/provision.latest.json` | map download | `/api/health` |
| `outbox/camp.latest.json` | camp clock | hub Home |

## The live board (`GET /api/live`)

While a dropped sortie is being fought, the minimap widget (`gui_verdance_minimap.lua`) writes `LuaUI/Config/verdance/live.json` in BAR's data folder every observation tick: per zone our sight (`eta`), enemies seen, exposure and any contradiction (`found`); our heroes' positions; pad and objective counts. The kernel serves it only for the mission in `outbox/next_mission_intent.json` and only while it is under 20 s old; otherwise `{"live": false}`. The hub (`console/live.js`) paints it over the belief board on the fight's map and drops it when the match ends. It is the company's sight, not the ground, and it never writes belief; belief still moves at homecoming.
