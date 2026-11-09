# Dev log: toward 0.16

One entry per working day: what changed, what was measured, what's next. The newest entry comes first. Run folders live under `autopilot_runs\` on the dev PC (fenrir); they're not in git.

## Morning summary for Luke (2026-11-09)

**Decisions waiting on you**
1. **The Overthrow's medium soak is hard but beatable.** First attempts broke 52 and 50 of the Keep's 65 guns and factories in 45 game minutes (partial). Then campaign v3 **won it on its second attempt, 65/65** (the campaign offers the finale again after a partial). The easy soak (15 min) was won outright. My read: keep medium at 20 minutes; it's a two-try finale for the proxy. Your call if it should be one try (bake at 17–18).
2. **The hard soak's tors spend the soak on economy.** 515 metal makers at one tor; 3,309 units in all. Swapping the tors' SimpleConstructorAI for SimpleDefenderAI would give fortifications instead.
3. **The pull home never lets go on the hard-AI runs.** The bag's Tenebrium isn't spent at home, so the proxy keeps choosing Rock Jungle jobs. v2 did seven door jobs in a row. Is that the intended pull, or should a few visits without spending ease it?

**What changed overnight** (all on master, local CI green each time)
- The drop limit grows 1k per sortie played, with no cap. A wipe loses its stockpile. The field's free 1k is no longer banked as hauled metal (a contract bug).
- Rock Jungle grace has a 5-minute floor.
- The Overthrow is a soak: eight Armada works, a strip after, one commander left in the Keep.
- Proxy player:
  - Hero caution, which steps away from enemies before heading home; Ketha is held back sooner.
  - The home profile is BARb `hard`, and it leaves on the raptor clock.
  - It buys mercs.
  - It holds the door on Rock Jungle jobs.
- Air heroes (Rookery, Stiletto) can be rescued; they used to vanish at frame 120.
- Hero temper, the first slice of mood-driven hero AI: camp bonds, wounds and grief become nerve and drive. They tilt the hero's doctrine in the field and show on the hub as steady, shaken, eager or grieving.
- UI:
  - Compact hero cards with XP bars.
  - The flow's tabs say where they stand.
  - The debrief says what was brought home.
  - A shorter jobs screen; the legend folded into a Key.
  - Talk answers lead with what they stand for.
  - The store sorts by what you can buy and shows that it scrolls.
  - **No more `VA_` debug lines in the in-game console.**
  - The mission rail clears BAR's raptor panel.
- Tooling:
  - Local CI (`scripts\test\ci.bat`).
  - `--soak`, `--shots` (windowed screenshots for HUD review), `--modopt` and `--prefer` on the autopilot.
  - A camp-talk word audit (`docs/writing/talk_audit.md`: talks are short, but 43% of their words are narration).

**Measured** (details below)
- Rock Jungle wipes: baseline 6, v2 0.
- Caution A/B over four arms: hero-sorties lost per run fell from 5.0 with no caution to 2.7 with the current one (Ketha leashed and let go only when whole).
- The door-hold fix won Rock Jungle doors and broke the home loop in v3.
- **Campaign v3** (everything up to the soak, the door hold, temper and the bleed rule): **completed in 12 sorties.**
  - The finale on the medium soak: partial (50/65), then won (65/65).
  - Vane and Halbard fell early (sorties 1 and 3), and the hollowed company lost three Rock Jungle drops to roaming raptors. Since then the retreat steps away from the enemy first and Ketha is held back sooner (9a5f6a4), now in A/B trials.

**Not done or not verified**
- The HUD reviewer's density cuts to the mission rail (smaller rows, fewer lines). Some of what it would cut is yours by design ("Left if you lift"), so it waits for you.
- The writing pass itself: only the audit is done, not rewrites.

## 2026-11-09 (night): owner notes worked through

Owner notes after the baseline (Luke asleep; "err on the side of doing too much"):
- Rock Jungle grace of 5 minutes.
- A safer proxy that plays non-aggressive at home and leaves when the raptors come.
- Mercenaries.
- The finale as a soak.
- When in doubt, the UI.

**Changes (all on master, local CI green each time)**
- Raptor grace eases from 600 toward a 300 s floor (d3aa1fa).
- Proxy player, 4f05519:
  - **Hero caution:** every second, a hero below 55% health, or below 85% with five enemies near, walks to the pad and is held until whole.
  - **No nudging heroes** into the wound.
  - **Raptor ground:** plays BARb `hard` ("Hard | Balanced"; BARb has no defensive profile) and departs 60 s after the grace ends.
  - **Mercs:** 80% of the metal bag spent on them before each drop.
- The Overthrow is a soak (c91f183):
  - Three BARb hard and five Simple defender/constructor AIs raise the castle unopposed.
  - Easy 15 / medium 20 (shipped) / hard 35 min.
  - The strip keeps factories, 15% of builders and one commander, the Keep's.
  - In the mission, every start commander but the Keep's is swept.
  - Medium: 957 units. Easy: 699. Hard: 3,309, of which the two tor constructor AIs built 1,800 structures, mostly economy (515 metal makers at one tor). Medium is the playable one; the hard soak's tors probably want SimpleDefenderAI instead.
- Air heroes can be rescued (bb8f519). The frame-120 deaths of Rookery and Stiletto were air seeds: a quietly killed aircraft leaves no corpse.
- Hero temper (50d0d69), the first slice of mood-driven hero AI:
  - Camp bonds, wounds and griefs become each hero's nerve and drive on a drop.
  - The behaviour gadget scales the hero's doctrine by them (bail, kite, push).
- UI, from the playtester notes and a blind Sonnet review:
  - Compact hero cards with XP progress and Ketha's "always comes" lock.
  - Blurbs without prices.
  - Hostile rescues always listed.
  - Recruits say where they wait.
  - A shorter jobs screen.
  - "Choose this job" alone on the right.
  - The store shows it scrolls.
  - Talks say what unlocks Next.

**Measured so far**
- Trial `20261109_005443` (3 sorties, before tightening the caution thresholds):
  - Caution and rescue worked.
  - Vane and Ketha still fell at the first thresholds.
  - Mercs were bought every drop.
- `campaign_hard_v2` (`20261109_011314`), in progress:
  - Sortie 1 (Greenest) came home with all four heroes; the baseline lost Vane and Ketha there.
  - Sortie 2, the Rock Jungle founding (baseline: wiped), extracted clean with all four plus Veil. It departed on the raptor clock at frame 19,811 (600 s grace plus 60 s).
  - Sortie 3 (Greenest): everyone home.
  - Sortie 4 (Rock Jungle): extracted clean; Ketha fell.
- Finale A, the Overthrow, as a soak, in 45 game minutes against the hard AI with mercenaries (it rents Bro and his Tzar):

  | Soak | Targets | Result | Heroes |
  |---|---|---|---|
  | Medium, shipped (`20261109_012053`) | 65 | 52 broken, then left on the clock: partial | Vane and Halbard fell; Ketha and Verse came home wounded |
  | Easy (`--soak easy`) | 34 | all broken: won | Bro, Lunkhead and Verse came home |

  - The sweep left one commander of eight.
  - Under the old siege bake, Verse alone took the Overthrow in 154 s.
  - The soak time works as a difficulty dial. Medium may be a little past what the proxy can finish: the next lever is soak minutes (17–18) or the strip.
  - The heroes lost hp with "enemies=0" within 700: the Keep's long guns. Since then, a hero losing 12% hp in a second pulls back too (18214ea).
- **`campaign_hard_v2`** (`20261109_011314`, done): 11 sorties to the finale, **0 wipes** (baseline 6).
  - Vane lived to sortie 10 (baseline: died in sortie 1). Halbard lived throughout (baseline: died in sortie 3). Ketha fell from sortie 4 on.
  - Eight Rock Jungle visits all extracted, but sorties 4–10 were the same door job, partial every time: the hold never started (fixed after v2 began, f2793fd). The pull home kept choosing home, because the bag's Tenebrium is never spent there.
  - Its finale used the old siege bake (it started before the soak landed), so its finale win says nothing about the soak.
- **`campaign_hard_v3`** (all fixes) started badly: Vane died in sortie 1, Halbard in sortie 3, and sortie 4 wiped. The wipe was by roaming raptors inside the grace, with only Verse left. Hence the A/B test below rather than a judgement from one run.
- **Caution A/B**, 3 trials each, 3 sorties (the caution toggle `va_autopilot_caution=0`):

  | | Caution on | Caution off |
  |---|---|---|
  | Heroes dead after sortie 1 | 1 | 4 |
  | Heroes dead by sortie 3 | 6 | 7 |
  | Hero-sorties lost | 11 | 15 |
  | Victories in 9 sorties | 5 | 2 |
  | Wipes | 1 | 1 |

  Caution helps clearly early on and comes with more victories. Heroes still die from sortie 2. Next for hero survival: rescue faster after a hero falls (Ketha herself falls most), and retreat paths that avoid the enemy.
- **Caution, second version** (9a5f6a4: step away from the enemies first; Ketha pulled back hurt with two near): **worse at first.**
  - After sortie 1, heroes lost: 1, 1, 1, 2, 2 (old caution-on 0, 1, 0).
  - Ketha fell in sortie 1 in three of five runs.
  - The traces showed why: her pull-back threshold (0.95) sat above the release threshold (0.90), so she flapped, pulled back and let go every other second, and BARb sent her straight back to the front each time. One trace has her pulled back at 0.90 and down 3.5 s later, thirteen minutes in, at the front.
  - Fixed in d248b0e: a critical hero is let go only whole (0.98), with nobody near and close to the pad, and is leashed within 1,500 of the pad outside a rescue.
- **Caution, all arms** (3 sorties a run, the same start):

  | Arm | Runs | Hero-sorties lost per run | Dead after sortie 1 | Victories | Wipes |
  |---|---|---|---|---|---|
  | Off | 3 | 5.0 | 1.33 | 2/9 | 1 |
  | v1 | 3 | 3.7 | 0.33 | 5/9 | 1 |
  | v2 (Ketha flapping) | 5 | 4.8 | 1.4 | 6/15 | 0 |
  | **v3 (Ketha fixed)** | 3 | **2.7** | 0.33 | 3/9 | 1 |

  - v3 keeps heroes alive best. Ketha survived sorties 1 and 2 in every run.
  - Victories vary with the route: sortie 3 went to Koom Valley in two v3 runs. Samples are small.
- **Console clean-up** (6d5fc43): `VA_` debug lines no longer reach the player's chat. Found with the windowed screenshot rig (`--windowed --shots N`) and a log probe. BAR's chat drops priority L_DEPRECATED, and the infolog keeps it.
- Also tonight:
  - The Rock Jungle door jobs sat in "clear" all sortie with nothing booked. A capture with nothing to wreck clears by standing in the zone in strength. The proxy now masses there in that phase too (f2793fd).
  - Temper reads the mean bond with drop-mates; the sum saturated.
  - Hero cards and the Company tab say steady, shaken, eager or grieving when it's notable.

## 2026-11-09: the hard-AI baseline

**Run:** `scripts\test\campaign_hard.bat` (BARb hard_aggressive, stock BAR, speed 10, beats on), `autopilot_runs\20261109_001446`. It ran on 0cfc556, so it predates the drop-limit rule of 1be6f78. It's a baseline for the proxy player, not for the drop limit.

**Outcome:** the campaign completed in 11 sorties and 2 h 20 min wall time, finishing with the Overthrow (finale A) won. That reads like a pass, but it isn't one.

| # | Map | Job | Verdict | Wall | Heroes home |
|---|---|---|---|---|---|
| 1 | Greenest Fields | seize lane (raid) | victory | 155 s | Verse, Halbard |
| 2 | Greenest Fields | take the Koom door | victory | 107 s | Verse, Halbard |
| 3 | Rock Jungle | fortify (founding) | **wiped** | 138 s | — |
| 4 | Koom Valley | road | partial | 178 s | — |
| 5 | Rock Jungle | door SE outer muster | **wiped** | 80 s | — |
| 6 | Rock Jungle | door NE rim | **wiped** | 62 s | — |
| 7 | Rock Jungle | door NE rim | victory (contested) | 209 s | Verse |
| 8 | Rock Jungle | door SE outer muster | **wiped** | 83 s | — |
| 9 | Rock Jungle | door SE outer muster | **wiped** | 65 s | — |
| 10 | Rock Jungle | door SE outer muster | **wiped** | 95 s | — |
| 11 | Ancient Bastion | the Overthrow | victory | 154 s | Verse |

**What it shows**

1. **The proxy throws heroes away.** By the end, 20 named heroes were dead. That includes Vane (sortie 1), Halbard (sortie 3), Ketha (almost every sortie; she keeps coming back) and every field recruit the company raised. Verse alone carried the finale, which went to the finale kit. BARb treats heroes as units. This is the first job for the proxy player: keep named heroes alive (pull back early, resurrect the fallen).
2. **The Rock Jungle is a death spiral.** Six wipes in seven visits, all on the same two door jobs. Two things feed it:
   - **The raptor pace climbs with every visit, won or lost.** Grace went from 600 s to 430, 308, 158, 113 and 81, and the raptors' head start from 0 to 950 s. A company that keeps failing at home keeps making home harder.
   - **The pull home never lets go.** The bag held 11 Tenebrium through the whole spiral, and a wipe doesn't spend it, so the pull curve sent the company home again and again. The "defeat raises the stock a visit wants" rule (f51e375) didn't break the loop.
   Both need an owner call: is home supposed to get harder per visit, or per time the raptors have had to grow?
3. **The finale is easy for a hollow company.** The Overthrow fell in 154 s to Verse and the finale kit.
4. **The reserve did fill:** 27 units at the end (6 Legion constructors, 7 Rezbots, 5 Javelins and others). The wallet ended at 24k metal and 11 Tenebrium.

**Next**
- Proxy player, hero caution: named heroes retreat toward the pad at low health or under a heavy threat, and a Rezbot or Ketha goes for a fallen hero's wreck. Measure it as hero deaths per sortie against this run (20 dead in 11 sorties).
- Proxy player, extraction: get the built army onto the pad before extracting.
- Owner call on the Rock Jungle spiral (visit-based escalation, a pull that ignores wipes).
