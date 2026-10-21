# Campaign ↔ BAR Resolution Protocol

**One outbound contract. One inbound contract. One ingest owner. One credit table.**

> **Pass five (2026-10-20).** The sortie ends on the player's **manifest** (what goes, what stays, where
> to); the gadget writes facts only and `tools/manifest_v1.py` reads the verdict off them. The kernel
> launches Spring itself and tails the infolog (`tools/verdance_kernel/sortie.py`); there is no
> play_session host, no extract script, no receipts file and no live-command channel on the player path.
> Sections below that mention those describe the operator/headless tooling or history.
> See `docs/NARRATIVE_READINGS_SSOT.md` → "Pass five".

After a fight, the kernel brings the result home. If not: **Pull result** or **Abandon**.

**Collapse law:** one Drop / MatchResult is the **observation** that updates world graph `G` inside `process_result` (`apply_graph_deltas` + `measure_graph_from_world`). See [`GRAPH_COLLAPSE_SSOT.md`](GRAPH_COLLAPSE_SSOT.md).

**Objective ledger law (one primary):** the stamped `objectiveArchetype` owns the board. On `eco_raid`, Tnb/eco is primary; wild field recruits seed as **optional** bonuses (`optionalJoin=true`) unless explicitly contracted. Destroying an optional recruit must not set `objectiveFailed`. Dedicated rescue contracts hard-link only when authored that way.

See also: `docs/DEPLOY_TRUTH.md` (play path), `tools/contract_v2.py`, `tools/match_credit_v1.py`, `docs/UI_ASH_CONSOLE.md` (shared debrief language on BAR + hub).

---

## Mental model

```
SORTIE  ──(Sortie v2)──►  BAR MATCH  ──(MatchResult v2)──►  CAMPAIGN (+ collapse G)
  hub/stamp                 gadget terminal                  kernel.bring_home
  one seed                  one terminal per chapter         one credit table + M(G,result)
```

| Direction | Contract | Writer | Consumer |
|---|---|---|---|
| Out | `verdance-sortie-contract/2.0` | stamp / materialize | mission seed + gadget |
| In | `verdance-match-result/2.0` | gadget → infolog → extract | `process_result` only via normalize |

**Hard rules**

1. MatchResult v2 is law after normalize. Raw gadget JSON is source, not API.
2. Only `CampaignKernel.bring_home()` advances campaign state from a match.
3. Credit decisions come only from `match_credit_v1.credit_from_result`.
4. Never free-mint Tnb on capture claim (`freeTnbMint` always false).
5. Every homecoming (including failure) produces a presentable hub debrief.

---

## File map

| Artifact | Who writes | Who reads |
|---|---|---|
| `outbox/hub_deploy_plan.latest.json` | stamp | build, apply debrief context |
| `outbox/next_sortie_order.json` | stamp | materialize / build |
| `mod/.../generated/va_current.lua` | build | BAR |
| BAR `infolog.txt` `VA_RESULT_JSON_*` | gadget | extract |
| `inbox/latest_va_result.json` | extract only | bring_home / process_result |
| `inbox/archive/{resultKey}.json` | extract | audit |
| `state/campaign_state.json` | process_result | hub, next sortie |
| `outbox/hub_result.latest.json` | apply / bring_home | hub UI |
| `outbox/bridge.latest.json` | BarBridge | operators |
| `outbox/result_harvest_fail.latest.json` | extract fail path | diagnostics |
| `outbox/play_session.status.json` | play_session host | bridge / status |

---

## MatchResult: the gadget writes facts, Python interprets

The gadget (`game_verdance_campaign.lua` `resultJson`, one blob per sortie as `VA_RESULT_JSON_*`
in the infolog) carries **no verdict, no credits, no zone flip and no extraction judgement**.
Its `status` is the terminal **kind** only. Everything a reader needs to judge the sortie is a
fact in the blob; `tools/manifest_v1.py` turns the manifest into the verdict and
`tools/match_credit_v1.py` turns the facts into credits. `tools/contract_v2.normalize_result`
is the only door: it strips any judgement field an older result still carries
(`verdict`, `credits`, `zoneFlipped`, `zoneFlipEligible`, `cleanExtract`, `freeTnbMint`,
`mapSpent`, `theaterExhausted`) before the credit table sees it.

**How a sortie ends** (and only these ways):

| `status` (terminal kind) | What happened | Python verdict |
|---|---|---|
| `extracted` | the player confirmed the manifest (`VA_CMD:extract:<dest>`) | `victory` if `manifest.objectiveComplete` and `manifest.staying.heroes` is empty, else `partial` |
| `wiped` | nobody left to confirm one; the exfil gadget stamps an empty manifest | `defeat` |
| `closed` | the engine ended the game without a manifest (resign / external GameOver) | `abandon` |

The clock never ends a sortie: when `requiredFrames` runs out the HUD phase becomes `OVERTIME`
and play continues until the player lifts. `extractionStatus` is Python's reading of
`manifest.enemyOnPad` (`clean` when 0, else `contested`); it is not written by Lua.

**Fields** (all facts; `*` = new in pass nine):

| Group | Fields |
|---|---|
| identity | `schemaVersion` `campaignId` `missionId` `missionNumber` `chapterIndex` `resultKey` `sortieId` `playerTeamId` `pathSignal` `patron` |
| ending | `status` (kind) `terminalReason` `manifest` (`verdance-manifest/1`: `kind` `destination` `pad` `going` `staying` `enemyOnPad` `objectiveComplete` `seen` `tenebrium`) `frame` `elapsedMinutes` `holdFrames` `requiredFrames` |
| where | `deploymentMapId` `mapId` `deploymentZoneId` `targetZoneId` `extractionZoneId` `map` `zoneMap` |
| primary objective | `objectiveComplete` `objectiveCompleteHow`* `objectiveCompleteFrame`* `objectiveKind`* `objectiveMode`* (capture · presence · fortify · targets_choice · targets_raid · targets_all) `objectiveTargetsTotal`* `objectiveTargetsDestroyed`* `objectiveBypassed` `chosenTargetForceId` `destroyedObjectiveIds` `objectiveResults[]` (`objectiveId` `kind` `mode`* `status`: incomplete · destroyed · complete · claimed, `how`* `targetsTotal`* `targetsDestroyed`* `damage`) |
| capture state machine | `captureMode` `capturePhase` (idle · clear · hold · claimed) `pocketCleared` `nodeClaimed` `nodeClaimedFrame`* `zoneHoldFrames`* `regrowWaves` |
| marks | `secondaryResults[]` `requiredMarksLeft`* `allObjectivesDone`* (primary + every required mark + purge: the HUD's EXTRACT phase) `purge{armed,done}` |
| rescue contract | `objectiveFailed` `objectiveFailReason` `objectiveFailHero` `rescueContractFailed` |
| company | `heroResults{}` `namedOutcomes[]` `recruitedHeroIds[]` `playerSurvivors{}` `playerSurvivorXp{}` `loanUnitHp{}` `armyValue` / `metrics.armyValue` (metal of living mobile combat units, a measurement) `companionsAlive` `companionsTotal` `primaryCompanion` |
| field | `playerFootprint[]` `survivingInstalls[]` `shellScars[]` `observedZones{}` `beliefExport{}` |
| economy | `metalStored` `metalStorage` `metalKExtracted` `metalKBrought` `metalKFieldStart` `metalExportMode` `economy` `tenebrium*` (`Bank` `Looted` `Spent` `Lost` `Invested` `LivingStakes` `LivingStakeUnits` `LootEvents` `WrecksCreated` `WrecksClaimed` `WrecksLost` `UnclaimedOnExtraction` `ClaimEvents` `TeamBanks` `FactionBanks`) `armadaTenebriumCrisis` |
| world | `graph` `reputation` `quantumTransitionJournal` `finalQuantumState` `sessionMode` `occupationModel` `farmSortie` `debugAutoProgress` |

After normalize, MatchResult v2 adds what Python decided: `verdict`/`status` (verdict enum),
`terminalKind`, `extractionStatus`, `cleanExtract`, `zoneFlipped`, `credits{}`, `success`,
`freeTnbMint:false`.

```json
{
  "schemaVersion": "verdance-match-result/2.0",
  "resultKey": "campaign|missionId|missionNumber|chN|<kind>|<reason>|fFRAME",
  "verdict": "victory|partial|defeat|abandon|incomplete",
  "terminalKind": "extracted|wiped|closed",
  "terminalReason": "extracted|wiped|closed|gameover_external|…",
  "credits": {
    "objectiveComplete": true,
    "nodeClaimed": true,
    "pocketCleared": true,
    "zoneFlipEligible": true,
    "cleanExtract": true,
    "raidCredit": false
  },
  "chapterIndex": 1,
  "freeTnbMint": false
}
```

---

## Credit table

| Verdict | Zone flip | XP / rep | Mission # advances | Hub tone |
|---|---|---|---|---|
| **victory** | Capture: only if `nodeClaimed`. Non-capture: yes if objective credited | full | yes | Secured. |
| **partial** | **only if** `nodeClaimed` | partial | yes | Hinge. Not a win. |
| **defeat** | never | loss / wounds | yes | Field costs. |
| **abandon** | never | optional scar only | **no** | Left the field. |
| **incomplete** | never | none | **no** | Result not home — Retry / Abandon. |

**Laws**

- `partial ≠ victory` for full XP and empty-grass flips.
- Capture path never flips without `nodeClaimed`.
- Duplicates (`resultKey` already in `processedResults`) → no-op, hub shows “already applied”.
- One sortie, one result: there is no same-map continue and no second chapter (`chapterIndex` is always 1).
- The gadget never decides any row of this table; it only reports the facts the table reads.

---

## Crazy-path playbook

| Event | Action |
|---|---|
| Clock runs out | nothing ends: HUD phase `OVERTIME`; the player still lifts via the manifest |
| BAR exit, 0 results | `incomplete` debrief; Retry extract or Abandon |
| Extract parse fail | `incomplete` + `outbox/result_harvest_fail.latest.json` |
| External GameOver (resign / crash-to-lobby) | gadget writes the facts with `status: closed`, `terminalReason: gameover_external`, no manifest → `abandon` (bead only, mission number held) |
| Company wiped | exfil gadget stamps an empty manifest (`kind: wiped`) → `defeat` |
| Re-Pull same result | duplicate no-op |
| Stale inbox | refuse if already processed; ask re-extract or new Drop |

---

## Ingest (sole owner)

```
kernel.bring_home()
  1. extract → inbox (no hub side effects)
  2. normalize → MatchResult v2
  3. abandon/incomplete → hub_result only (no process_result credit)
  4. process_result via credit table
  5. rebuild hub + bridge log + debrief card
```

- Hub PLAY auto path: **BarBridge**
- Multi-mission host: **play_session** (same bring_home / same keys; no invent credit-bearing fake keys)
- Manual: hub **Pull BAR result** → `/api/advance`

---

## Abandon

Records a history bead, does **not** flip zones, does **not** fake victory, does **not** bump mission number. Unlocks the next Drop so a rage-quit never soft-locks the campaign.
