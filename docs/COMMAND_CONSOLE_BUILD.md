# A Company in a Living War — implementation and release record

Status: development candidate, October 15, 2026. This is not a live-BAR-validated release.

## Implemented

- Browser-native modules separate the console workspace controller, narrative API state, presentation helpers, and intelligence overlays. The existing deployment/formation/map controller is preserved in `app/showoff/console/campaign.js`; further decomposition of that controller remains possible without changing its contracts.
- Operations, Company, Home, and Chronicle share the persistent theater, inspector, system menu, and contextual action strip. Operations are presented as purpose, required conditions, bring-home conditions, known risks, and consequences. Existing route legality and deployment controls remain authoritative.
- Map layers can be toggled separately. Zones support keyboard activation. Unknown hostile ownership and ambient unrecruited characters are suppressed. Intelligence differentiates mission reports from explicit result observations; missing observations remain unknown.
- First-run formation can suggest three affordable legal packs. The player can edit the suggestion and must explicitly confirm it.
- Company inspection includes role, condition, existing progression information, relevant commitments, and eligible scenes. Home exposes the existing camp milestone and broker.
- Pending results have a prominent recovery action and prevent another console deployment. Homecoming and Chronicle show accepted results, participants, recorded resource fields, and sourced consequences.
- `tools/narrative_v1.py` provides deterministic projections, additive versioned state, persistent threads, narrative trust, recorded commitments, evidence references, stable ranking, and callbacks. It never applies a second quantum world update or awards economy/reputation/bond rewards.
- Narrative time advances once for each newly accepted progression-bearing victory, partial result, or defeat. Reading, refresh, purchases, withdrawal, incomplete results, and duplicate results do not advance it. Authored deadline choices use three subsequent accepted sorties.
- Six authored families include openings, escalations, resolutions, failure responses, changed fallbacks, and callbacks. Twelve scenes use six existing character pairs and require recorded shared deployments plus currently available, healthy participants.
- Narrative choices use stable IDs, a whole-state revision token, and request receipts. The kernel serializes relevant campaign mutations and validates choices server-side. Read projections use a copy.
- The result hook runs after authoritative campaign accounting and before next-intent generation. It adds narrative evidence to the report/debrief and shared briefing context to the next intent. Existing Lua-authoritative folds remain authoritative.
- Initial narrative persistence backs up the existing campaign file under `state/backups/pre_narrative/`. Existing save/load naturally includes the additive section and preserves unknown fields.
- BAR presentation uses the revised verdict wording, shared mission purpose/return instructions, and an ambient bark cooldown with urgent-message priority. `/valog` prints the retained field-dialogue log.
- Shipping includes the narrative Python module, content catalogs, and console modules. `legacy.html` preserves the presentation present at the start of this implementation, including prior workspace changes.

## Development controls

- `?console=0` opens the legacy presentation. Campaign `features.commandConsole=false` also selects it.
- `VERDANCE_NARRATIVE=0` disables narrative processing/projection. Campaign `features.narrative=false` is the save-specific alternative.
- Both features are enabled in this development candidate. Do not publish it as the default release until the remaining release gates below pass.
- `GET /api/narrative` returns the current projection and revision. `POST /api/narrative-choice` accepts `choiceId`, `expectedRevision`, and `requestId`.

## Isolated preview

Run `python tools/preview_command_console.py --port 8774 --fixture established`, then open `http://127.0.0.1:8774/`.

Supported `?fixture=` values: `fresh`, `established`, `partial`, `wounded`, `threatened`, `incomplete`, `late`. This server never launches BAR or writes the actual campaign. Narrative choices affect only its in-memory fixture. Purchases, formation confirmation, recovery, and deployment are intentionally rejected by the preview server. Fixtures are presentation scenarios based on the workspace's current data, not simulated live playthroughs.

## Verification performed

- 22 focused narrative tests pass: deterministic nonmutating reads, stale/repeated requests, duplicate results, deadline exclusions, explicit intelligence, real participants, scene eligibility, invalidated footholds, migration backup, unknown-field round trips, isolated kernel save/load, actual Python result-path integration, callback timing, wounded-survivor handling, and all six family success paths.
- 21 match-credit tests pass.
- Console JavaScript syntax checks and modified Python compilation pass.
- Modified objective HUD and shared verdict-token Lua compile with Lua 5.1 via an isolated validation runtime.
- Browser checks exercised all four workspaces, editable starting recommendation, commitment selection and deadline display, Chronicle, the seven fixture routes, pending-result deployment protection, and keyboard workspace activation.
- DOM layout checks at 1280×720, 1920×1080, and 2560×1440 showed no horizontal document overflow. Focus styling and reduced-motion rules are included; a complete keyboard-only and contrast audit remains outstanding.
- The broader story-engine suite currently reports 6 failures and 25 errors across 110 tests. Re-running with the new result hook removed in memory reproduces the same failing test identities/counts. These baseline failures include missing temporary graph fixtures and outdated roster/content expectations. They have not been hidden or repaired by changing unrelated campaign data.

## Remaining release gates and limits

1. Run the five live BAR scenarios from the approved plan: successful raid/home improvement, partial extraction, wounded return/recovery, same-map continuation then hub return, and interrupted synchronization/recovery. The shared result path is covered automatically; equivalent live same-session behavior is not yet established.
2. Exercise all legal routes, mission archetypes, seven theaters, and authored fallback paths against live campaign histories. Current narrative opportunities link and prioritize supported existing operations; they do not add new mission mechanics or rewrite finale selection.
3. Audit mission-specific quantities and extraction wording against actual generated BAR objectives. Shared summaries currently describe the existing archetype rules; generated mission data remains the authority for exact target counts and timers.
4. Complete keyboard-only, overlay clutter, contrast, and reduced-motion testing at the target resolutions. The retained map renderer still uses the campaign's existing zone geometry.
5. Run the three BAR-familiar newcomer tests and require at least two to meet the plan's comprehension criteria before release.
6. Resolve or formally triage the preexisting broad-suite failures before declaring a clean release build.

No live campaign save was migrated for testing, no BAR installation was replaced, and no release package was published by this implementation pass. Existing dirty workspace changes were preserved.
