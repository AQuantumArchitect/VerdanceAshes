# Umwelt in Verdance's Ashes — the engine under the game

*For the reader who wants to know why the map lies, and how. Rules of play: `docs/THE_GAME.md`. Running it: `docs/DEPLOY_TRUTH.md`.*

## The claim

Most strategy games keep one world state and hide parts of it from the player with a fog mask. Verdance's Ashes keeps **one belief state per mind** and never shows the player anything else. The company, Armada, Cortex and the mercenaries each hold their own picture of the same zone graph; each picture is updated only by what that mind observed, decays where it has not looked, absorbs rumours, and drives that mind's decisions. The hidden truth frame exists only to resolve what each mind sees. The game is played in the gap between a belief and the ground.

The engine that holds these pictures is **Umwelt** ([AQuantumArchitect/umwelt](https://github.com/AQuantumArchitect/umwelt)): a belief-field engine where a world is a graph and a mind's belief is a density-matrix-style field over it rather than a table of facts. Verdance's Ashes is its first public demonstration.

## The words

| Word | Meaning here |
|---|---|
| **Mind** | A holder of belief: the company, each faction. |
| **Belief** | A mind's field over the zone graph: per zone, per role (`ours`, `held`, `strength`, `threat`), a value, a confidence, an age, a source. |
| **Observation** | A mind saw a zone with quality **η** (0..1): a full line-of-sight sweep is η≈1, a glimpse 0.2, a rumour less. Observations move belief in proportion to η. |
| **Decay** | Unseen belief loses confidence over time; stale belief is marked, not hidden. |
| **Surprise** | Distance between what a mind believed and what it then observed. Carried home from every sortie; shown as `✗`/`○` on the board. |
| **Divergence** | Distance between two minds' beliefs about the same zones. The player sees only the company's side: how much of *us* another mind has seen (**exposure**). |
| **Frame** | A snapshot of a belief field at a minute of campaign time. The truth frame is a frame nobody plays from. |

## The law

**Lua reports facts; Python interprets. The player side shows the company's belief and nothing else.**

- The BAR gadgets export facts: per-zone line-of-sight share and enemy counts seen, who stood on the pad, what was wrecked, the manifest. They compute no verdicts.
- Python folds those facts into the company's belief, computes verdicts from the manifest, composes the next mission from belief, and writes the in-game belief file the HUD paints from.
- The hub and the in-game HUD read belief surfaces only. Routes that expose the truth frame or another mind are dev-only and refused otherwise.

## How the pieces fit

```
                 hub (app/showoff)                     Beyond All Reason
   belief board · company · chronicle · Drop      infil card · minimap board · sidebar · manifest
                 ▲            │                             ▲                │
      hub_state  │            │ plan                 va_intel_current.lua   │ facts (LOS, pad, manifest)
                 │            ▼                      va_pad_current.lua     ▼
            ┌────┴─────────────────────────┐    ┌──────────────────────────────┐
            │  kernel (tools/verdance_kernel) │    │  gadgets (luarules/gadgets)   │
            │  stamp · launch · ingest        │◄──►│  observe · exfil · campaign   │
            └────┬─────────────────────────┘    └──────────────────────────────┘
                 │ result (facts)
                 ▼
            ┌──────────────────────────────────────────────────────────────┐
            │ belief lane (tools/verdance/belief, tools/verdance/readings)   │
            │ belief.world ── adapter over Umwelt (observe, decay, frame)    │
            │ belief.homecoming ── fold a sortie's facts into belief         │
            │ belief.perspectives ── the other minds, by observation policy  │
            │ belief.camp_clock ── camp time: scouts, patrols, rumours       │
            │ belief.hub_belief / intel_lua ── belief surfaces for hub / HUD │
            │ belief.manifest / match_credit ── verdicts from the manifest   │
            │ readings.readings / occasions ── what the story thinks happened│
            └──────────────────────────────────────────────────────────────┘
```

## A sortie, as belief

1. **Stamp.** The company's current frame becomes `va_intel_current.lua` (per zone: ours/held/threat with value, confidence, state, age, and the faction last seen holding). The pad and its links become `va_pad_current.lua`.
2. **Infil.** The HUD paints that frame. Yeva reads it aloud in plain words.
3. **Fight.** `game_verdance_belief_observe.lua` measures, every two seconds, how much of each zone the company's units can see and how many enemies they see there, with an eight-minute half-life. The minimap fades the briefed belief as η rises. When η passes 0.5 and the ground contradicts the brief, the HUD marks it and remembers.
4. **Extract.** The manifest is a headcount, not a judgement: who is inside the pad ring, who is not and where, what structures stand where, who else is on the pad.
5. **Homecoming.** Python folds the observed zones into the company's belief at their η; the surprise per zone is recorded; people left become obligations; structures become holdings; the other minds are folded by their own observation policy (what *they* could see of us) on a background worker; verdicts are derived from the manifest.
6. **Camp.** Minutes pass. Posted heroes scout (an observation at modest η), patrols take losses, rumours flip zones — all as belief updates. The next stamp starts from the result.

## Why this is interesting

- Fog of war becomes **epistemic**: "nobody looked" is a state with consequences, not a grey overlay.
- Enemy behaviour is **explainable**: a faction acts on what it believes, which is what it saw, which is what the player gave away. Exposure is a number the player can read and manage.
- Story is **keyed to interpretation**: readings are a weighted mixture over competing accounts of the same events, with explicit ambiguity; voice lines, briefings and debriefs draw from that mixture rather than from the raw event log.
- A third-party RTS is used as the **resolver** for a simulation it knows nothing about. BAR sees a normal match; the campaign sees an observation.

## Where to read next

- `tools/verdance/belief/world.py` — the whole adapter; start here.
- `tools/verdance/belief/homecoming.py` — one sortie folded into belief.
- `tests/test_belief_lane.py` — the lane's contracts as unit tests; `tests/e2e_campaign.py` — a whole sortie without BAR.
- `luaui/Include/va_board.lua` — the one painter for belief in BAR.
- `docs/NARRATIVE_READINGS_SSOT.md` — readings, and the pass-by-pass log of how the game got here.
