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

## MatchResult essentials

```json
{
  "schemaVersion": "verdance-match-result/2.0",
  "resultKey": "campaign|missionId|missionNumber|chN|verdict|reason|fFRAME",
  "verdict": "victory|partial|defeat|abandon|incomplete",
  "terminalReason": "extracted|soft_clock_no_extract|player_wiped|…",
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

Gadget still emits a flat JSON blob; `contract_v2.normalize_result` fills v2 + credits.

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
- Mode A chapters are full MatchResults each; soft-continue does not skip credit.

---

## Crazy-path playbook

| Event | Action |
|---|---|
| Mode A soft continue | Process each new `resultKey`; keep watching until BAR exits |
| Travel / extract_leave | Process last result; relaunch is host concern |
| BAR exit, 0 results | `incomplete` debrief; Retry extract or Abandon |
| Extract parse fail | `incomplete` + `outbox/result_harvest_fail.latest.json` |
| External GameOver | Gadget safety net logs; normalize as victory/partial/defeat + `gameover_external` |
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
