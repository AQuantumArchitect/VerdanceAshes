# Verdance's Ashes — playtest today (for Luke)

**Build:** 0.9.0 · **Home map:** The Rock Jungle · **Your seat:** wargen (play box)

**One-click:** double-click Desktop **`Verdance Playtest.bat`**  
or workspace root **`START_PLAYTEST.bat`**

When you're done: double-click **`END_PLAYTEST.bat`** (harvests your session so bots/Grok can read it).

---

## Broad campaign status (bot-honest, Aug 2026)

### What the game *is* right now

You're not playing a finished Steam product. You're playing a **live campaign shell** on BAR:

| Layer | State |
|-------|--------|
| **Story / theater** | Mode A same-map loop: hub → theater board → rim infil/target/exfil → Drop into battle → bring-home |
| **Home** | Rock Jungle camp; raid for **Tenebrium (Tnb)**; scale build power at home with Tnb |
| **World between fights** | Multi-rate offscreen clock, rival clashes, Cortex crater grudge, attachments (Vane / Ketha / Null) |
| **AI proxy farm** | Bots sit in the *player seat* when you're not playing (~150k brain samples, UL ~2.2k updates) |
| **Hive** | Routine testing / learning moved to oa2it77 hearth; this box stays **your play machine** |

### What bots already learned (not the same as you)

Latest residual (wargen organic units):

| Signal | Proxy number | What it means for *you* |
|--------|--------------|-------------------------|
| Simple enemy win rate | **1.0** | Easy lane is soft for AI — may still feel easy or dull for a human who micro/plans |
| Barbarian win rate | **0.5** | BARb is the real pressure lane |
| Fun (simple / barb) | 0.37 / 0.47 | Proxy "fun" is a sim score — **your feel score is the truth** |
| Brain samples | ~150k | Lots of scar memory; still push-monoculture (~92% PUSH_OBJECTIVE) |
| Densify | **banned** | Fair-room only; no god-brain cheat |

**Campaign fruit (bots' ideas — do not treat as law):** raise late multipath + enemy aggro on easy clears; inject mid-mission pressure; diversify mission geometry away from pure push.

### What's deliberately waiting on *you*

| Item | Why |
|------|-----|
| **Human seal** `pkt-bar-playtest-s6-retune` | Bots must not retune power/attachments until **your** scorecards exist |
| Feel gates (coherent world, want one more sortie, care about cast) | Only a human can bank these |
| Difficulty for *players* not proxies | Proxy stomps simple; you may not |

---

## Playtest hitlist (do this, in order)

### 0. Preflight (2–5 min)

- [ ] Close heavy bot loops if the machine is lagging (optional; PLAY should still work)
- [ ] Optional clean run: `RESET.bat` only if you want a fresh campaign (confirms wipe)
- [ ] If mutator/hub feels stale: `SETUP.bat` once
- [ ] Optional abstract preflight: `NIGHT_TEST.bat` (no Spring required) — PASS is nice, not blocking

### 1. Launch (player path only)

1. **`START_PLAYTEST.bat`** (or Desktop shortcut) — opens this brief + starts `PLAY.bat`
2. Leave the hub/kernel window open
3. Green sortie → set **rim** infil + target + **rim** exfil on the theater map
4. **Drop into battle**

### 2. Session goals (P0–P5) — aim for 3 sorties if energy allows

| # | Do this | Pass looks like |
|---|---------|-----------------|
| **P0** | Launch; briefing names war + map + objective | You know why you're fighting |
| **P1** | Full sortie → debrief | Tnb / scars / claim show up; result returns to hub |
| **P2** | Mode A continue (no full restart) | Second sortie without reinstalling life |
| **P3** | One deliberate **fail** or bloody win | Story still advances; world doesn't soft-lock |
| **P4** | Shop / loan / home build if reachable | Or note "UI owns it / blocked" |
| **P5** | Stop → **`END_PLAYTEST.bat`** + quick scorecard notes | Telemetry + notes banked |

### 3. Systems to poke (while you play)

- [ ] Theater map visible; route arrows infil → target → exfil  
- [ ] Midfield infil/exfil **rejected** (rim only)  
- [ ] Tnb bank **0** → can't fab/con freely; after scavenge, BP unlocks  
- [ ] BP chip used/max makes sense  
- [ ] Bring-home advances the war clock / offscreen note  
- [ ] Optional: crater / Horus if you want Cortex grudge  
- [ ] Debug if stuck: `/vastatus` `/vahelp` `/vawin` (emergency)

### 4. Feel gates (circle what was true)

- Coherent world (same war, scars persist)
- Next contract feels dynamic (not a fixed checklist)
- Simulation weight (world moved / pushback while you were gone)
- Care about Vane / Ketha / Null foothold
- **Want one more sortie**

### 5. After play (mandatory for telemetry)

1. Run **`END_PLAYTEST.bat`**
2. Fill the short form it opens (`docs/HUMAN_PLAY_SCORECARD.md`) — even 5 bullets is enough
3. Optional: leave me a note in that file under **Notes for retune (S6)**

---

## How your telemetry gets to me (different from AI proxies)

| Source | What it is | Path |
|--------|------------|------|
| **Human session face** | One JSON per harvest: `kind=human_player`, your notes hook | `outbox/human_playthrough.latest.json` |
| **Hive vitals copy** | Same face for mesh / Grok / hive | `yurt-sync/commons/vitals/human_playthrough.latest.json` |
| **Tape** | Append-only history of sessions | `…/human_playthrough_tape.jsonl` |
| **BAR result** | `VA_RESULT` from infolog | existing extract → inbox + archive |
| **Zone telemetry** | If gadget emitted it | `outbox/bar_zone_telemetry.latest.json` |
| **Scorecard** | Your words | `docs/HUMAN_PLAY_SCORECARD.md` |

Proxies write `kind=player_proxy` residuals. **Never merge human sessions into proxy UL without an explicit human-seal open.** Your tape stays labeled `human_player`.

---

## What *not* to run

These are bot farms, not the fun path:

- `PROXY_CAMPAIGN.bat`
- `OVERNIGHT_HIVE_BAR.bat`
- organic / swarm PowerShell one-liners

---

## If something's broken

| Symptom | Try |
|---------|-----|
| Hub won't start | `SETUP.bat` then `PLAY.bat` |
| Dirty / weird save | Snapshot restore or `RESET.bat` (careful — wipes campaign) |
| Fight ends but campaign doesn't advance | Hub **Pull result** / Abandon; then `END_PLAYTEST.bat` |
| No telemetry after END | Play to a real terminal (win/lose) once; check `outbox/result_harvest_fail.latest.json` |

---

*Excited for you to play. Proxies map the room; you decide if the war is worth fighting.*
