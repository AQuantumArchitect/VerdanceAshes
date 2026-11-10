# Dev log: toward 0.16

One entry per working day: what changed, what was measured, what's next. The newest entry comes first. Run folders live under `autopilot_runs\` on the dev PC (fenrir); they're not in git.

## 2026-11-10 (overnight): leaving on the field, Umwelt v0.2.0

**Owner calls**
- Put leaving the field on the safety field ("Yes, do it here").
- Umwelt v0.2.0 is out, a moderately stable release: make it the base.
- Keep iterating overnight.

**Umwelt v0.2.0** (91a2be6, pushed). Pin `a00a0e7`. The belief world now imports through Umwelt's stable surface (`from umwelt import DomainSpec, …, GameHost`) instead of internal paths. Nothing else needed changing: 699 hub tests pass, and the ship dry run vendors the new pin.

**Leaving: what was built** (`va_safety_field.lua`: `companyStays`, `fightOutcome`, `clearUp`, `boarding`)
- **While the objective is open:** Lanchester's square law in fight units, sqrt(dps × hp). Ours is every mobile gun. Theirs is what contests the company: an enemy walker within twice its reach (its reach plus one reach of walking), a turret only where it covers the pad or the objective. The campaign gives no price for an objective (a failed one is another sortie), so it's worth what the company risked: staying is worth sqrt(1 − r²) × 2A, going is A × the walk home. It goes when sqrt(1 − r²) falls below half its chance of getting home (r ≈ 0.87 on a safe walk).
- **After the objective:** stay only while the raising under way (Ketha) brings back worth faster than the field takes it.
- **At the pad:** wait for a walker only while that's worth what the units aboard risk meanwhile. A walker that made no ground over the time it takes to cross a cell isn't waited for.
- **Hero caution runs on the walk home.** During the departure a hero's own plan is the walk to the pad with no wait there, so caution only takes a refuge as a way round.
- Gone: the 40 s settle, "three settles" for stuck units, and "60 s after the raptor grace". The 15-minute clock stays, as the rig's budget only.

**What the trials taught** (each one a fix)
- **Batch 3: every enemy army on the map counted.** Greenest Fields left at frame 0. Fix: only enemies that contest the company count.
- **Batch 3: boarding on the unknown's prior priced every walk home on raptor ground at nothing.** Fifteen units and Vane were left behind. Fix: the company's own calls read the guns it has seen.
- **Batch 4: point-blank enemies barely counted.** The contest kernel ("blur by one reach") gave an enemy right beside the company only a 0.39 chance of being in the fight. Fix: a disc of twice its reach.
- **Batch 5: with the fight read only logged, Rock Jungle wiped once.** The company read r ≈ 0.75 on what it had seen and lost three quarters of its strength in the next minute to raptors it hadn't. Vane sat twelve minutes in a corner refuge (ring points pinned to the map edge) and was stranded. Fixes: off-map refuges are dropped; the walk home during departure.
- **Batch 6: adding the unseen enemy to the company's fight left every Rock Jungle sortie in its first seconds.** The raptors' unfound strength, spread over the jungle, read r ≈ 0.88 at every pad. Taken back out: the prior is for where a hero stands.
- **Batch 7: the departure log named what the company was facing.**
  - At Greenest Fields' pad, 20,307 of 22,932 was one Legion commander's D-Gun read as sustained fire. Fix: manual-fire weapons aren't fire.
  - A raptor queen nest 5,456 from the pad read r = 3.74 because one unit had wandered into its reach. Fix: a turret counts only where it covers the pad or the objective.

- **Batch 8: a paired baseline.** Master's timers and the new rule ran side by side on identical settings: two campaigns preferring Rock Jungle, one preferring Koom, seven sorties each.
- **Batch 9: an enemy counts once it has hurt the company.** The claim fades over the time the enemy takes to walk its reach. This came from batch 8's raptors near the pad reading r ≈ 1 when they weren't attacking. Boarding also averaged each walker's closing speed since the departure order.

**Measured: the paired comparison**

| Same campaigns (3 × 7 sorties) | Master: timers | New rule, batch 8 (proximity) | New rule, batch 9 (hits) |
|---|---|---|---|
| Rock Jungle campaigns: core-hero deaths (14 sorties) | **0** | 1 (Vane, after being stranded) | **7** (Ketha 3, Vane 2, Halbard 2) |
| Rock Jungle defeats | 0 | 0 | 3 |
| Rock Jungle heroes stranded | 0 | 1 | 1 sortie with 3 left behind |
| Everyone on the pad at lift | 14/14 | most; walkers left on Koom (4/6, 9/15) | mostly |
| Koom-leaning campaign | 1 stranded (Halbard); 2 sorties didn't finish | Vane stranded | Ketha, Vane, Halbard dead in one Rock Jungle sortie; Verse stranded |
| Lua errors | 0 | 0 | 0 |

- **Decision: the leave rule doesn't go to master.** It's parked on `wip/field-departure` (0592d14) with its tests. Master keeps "60 s after the raptor grace", the 15-minute clock, and "wait for everyone, or three settles".
- **Why it fails on raptor ground.** No reading of the present sees a wave before it lands. Proximity reads every wandering raptor as a fight; the unknown's prior reads the whole jungle as one; hits taken arrive too late. The timer works because it encodes the spawner's schedule.
- **Next, if it's picked up again:**
  - Forecast the waves from the spawner's own published state (`raptorGracePeriod`, `raptorQueenAnger`/`raptorTechAnger`, its wave cooldowns) as known danger arriving at a known time. That keeps what the timer knows without its fixed 60 s.
  - Boarding should keep the old "wait for everyone" behaviour, priced by what the units aboard risk, rather than drop walkers.
- **Worth testing alone first** (on the branch, not on master): the D-Gun fix; dropping refuges past the map edge; the twice-reach contest. Each changes hero caution as well, so each needs its own trial.

**Also**
- **Flaky `test_sortie_flow`, fixed.** It failed in about half of today's full CI runs and never alone. It waited a flat 2 s, then checked for the formation screen. Under a loaded run the page hadn't drawn it yet, so the test took the sealed-company path and failed on a screen that wasn't there. It now waits for either screen to be visible. The full suite then passed three times out of three (699 passed). Found on the way: `build_hub_state.py` writes `app/showoff/hub_state.embed.js` under the real workspace, so trials and tests overwrite the page's state while they run. That didn't cause this failure, but it's an isolation gap.
- **The raptor forecast, for later.** The spawner's next wave is predictable: `timeOfLastWave + raptorSpawnRate × waveTimeMultiplier`, with the multiplier set when each wave fires. Each wave's contents are rolled at spawn time, so its strength would have to be estimated from the waves already seen (the raptor roster's jump at each wave). Publishing the next wave's time from the mod's spawner copy is a one-line addition, but it touches live gameplay code, so it waits for the owner.

## 2026-11-09 (afternoon): the safety field, temper on Umwelt, the ten-work soak

**Owner calls (after the morning summary)**
- No leashes and no magic numbers anywhere: reason from continuous geometry, as Umwelt proposes. Zones of safety from the balance of allied and enemy power; unknown ground is scary; Ketha, a rez bot, keeps to known-safe ground.
- The loop to aim for: the army smashes the base and loses a couple of units; Ketha runs in once it's safe and raises the wrecks; everyone extracts when safe.
- Mood and personality graphs run on Umwelt graphs.
- The finale: a 20-minute soak with five SimpleDefenderAIs, two SimpleConstructorAIs (three would scale too hard) and balanced BARbs, 8–10 AIs in all, plus a couple of LRPCs on the walls.
- Mission 1 is fine as it is. The pull home (decision 3) may be solved by continuous decisions. The camp talks are still to be read.

**What changed** (all on master, local CI green each time)
- **The safety field** (`include/va_safety_field.lua`; 4ebc469, 9c87172, d49fe8e, 50b34fe). Every quantity comes from unit defs, positions and what the company has seen:
  - **Fire.** A known gun covers its weapon range. Its edge is blurred by how far it could have walked since it was seen, as a 2-D normal that is exact at the centre. A turret seen once stays sharp. Its fire is shared over the company units it can reach.
  - **The unknown.** Enemy firepower not yet located is spread over unseen or long-unseen ground. "Long" means the time the enemy's typical walker takes to cross a cell; a cell is the company's median sight.
  - **Hazard.** Fire reaching the hero ÷ its health now.
  - **A plan's worth.** U = e^(−hazard on the way and while there) × (the hero's worth + what it gains). The hero takes the best plan among its own orders, staying put, the pad, the company's centre of strength, a ring at one enemy reach, and the wrecks it knows of (for a rez hero).
  - **Worth.** A hero's worth is its unit's cost at its level, plus (for a rez hero) its share of the raising still to do. All of that is multiplied by the sorties it would still serve.
  - **Temper** (below) scales seen danger × e^(−nerve) and gain × e^(drive).
- **The proxy (autopilot)** now runs caution and the rescue on the field. The old knobs are gone: 0.55/0.85/0.90 health, "5 enemies in 700", Ketha's 1500 leash, the 700 step, the hot-pad count, the 4-gun squad and the 700 quiet rule.
  - The rescue squad is the nearest guns until they outfight what covers the wreck (Lanchester).
  - While a hero is held, it's weighed on what BARb wanted when it was taken. That ended the flapping (78 swaps a sortie in the first trial).
- **The hero doctrine (human play).** An idle rez hero picks a wreck or a refuge from the same field.
  - **Bug found:** the doctrine aimed reclaim and rez at raw feature IDs, which the engine reads as *unit* IDs. They're now offset by `Game.maxUnits`.
- **Temper on Umwelt** (7a31af5). Each hero on the drop is a node with dissipative nerve and drive.
  - Camp events are observations: each level, each time down, a wound carried, and each bond felt (at a confidence of its points).
  - Bridges bind bonded drop-mates (coupling = points/100, negative for rivals) and each bonded friend who died; the dead are held at despair, so grief reaches the living through the bond.
  - Umwelt's transport runs across the graph's width. The doctrine's temper weights (0.30/0.15/0.30) are now the same exponentials.
  - The old tanh form is kept only for a build without Umwelt.
- **The Overthrow soak** (4ebc469). Ten works: five SimpleDefenderAIs, two SimpleConstructorAIs and three balanced BARbs. Two LRPCs (`armbrtha`) stand on the gatehouse towers, set down after the soak.
  - Re-baked: medium 1,198 units (was 957), easy 792, hard 2,362.
  - **Note:** BAR's SimpleDefenderAI is not turret-only. Its builders put up turrets on their random rolls and around every mex, but its factories still build an army that patrols friendly ground.

**Measured**

Batch 1 is on the field's first version (before the flapping fix, temper in the field, and the campaign worth). Same setup as last night: two 7-sortie campaigns preferring Koom.

| | Old caution (last night) | Field v1 |
|---|---|---|
| Sorties home | 14/14 | 14/14 |
| Core heroes killed | 4 (Vane and Halbard in both, by sortie 3) | 1 (Ketha, Rock Jungle, sortie 3) |
| Koom drops survived by every hero | — (one drop, Ketha down 14 s in) | 4 of 4 |
| Lua errors | 0 | 0 |

- Ketha's Rock Jungle death is why "a named hero is worth every sortie it would still serve" exists: she went to raise a wreck at 38% survival.
- The finale on the new medium soak (one try): partial, 19 of the Keep's 46 targets, all four heroes alive. Harder than last night's eight-work soak (36/65 on a first try).

Batch 2: everything as of 50b34fe (no flapping, temper in the field, campaign worth). Two field campaigns, one campaign with caution off on the same code, and a finale.

| Core-hero deaths | Sorties | Deaths | Per 7 sorties |
|---|---|---|---|
| Caution off (batch 2) | 7 | 4 (Ketha twice, Vane, Halbard) | 4.0 |
| Old caution (last night) | 14 | 4 | 2.0 |
| Field v1 (batch 1) | 14 | 1 | 0.5 |
| Field, current (batch 2) | 14 | 1 | 0.5 |

- Every run came home 7 of 7, with no Lua errors. One campaign drew five Koom drops and lost nobody.
- **The finale on the ten-work medium soak:** 17/46, then **46/46 on the second try. Campaign complete, all four heroes alive.** Still a two-try finale, as last night's eight-work soak was.
- **Both field deaths were Ketha on Rock Jungle.** The second (batch 2, sortie 6) shows why: she was held by the pad all sortie (survival 0.97, falling to 0.51 as the raptors came) and died 17 s after the departure order, while the company boarded. Caution doesn't run during departure, and on raptor ground the pad itself is overrun.
- **Next:** the departure is still a knob (leave 60 s after the grace; the 15-minute clock). Make leaving a field decision: go when staying costs the company more than it still gains.
- **Not done:** the pull home (decision 3) is the hub's job recommendation, which the field doesn't touch. A continuous version would weigh each job by the company's expected survival there (its strength against the job's known opposition on the belief board).

## Morning summary for Luke (2026-11-09)

**Decisions waiting on you** (afternoon: 1, 2 and 5 answered above; 3 hoped for; 4 still yours)
1. **The Overthrow's medium soak is hard but beatable.** First attempts broke 52 and 50 of the Keep's 65 guns and factories in 45 game minutes (partial). Then campaign v3 **won it on its second attempt, 65/65** (the campaign offers the finale again after a partial). The easy soak (15 min) was won outright. My read: keep medium at 20 minutes; it's a two-try finale for the proxy. Your call if it should be one try (bake at 17–18).
2. **The hard soak's tors spend the soak on economy.** 515 metal makers at one tor; 3,309 units in all. Swapping the tors' SimpleConstructorAI for SimpleDefenderAI would give fortifications instead.
3. **The pull home never lets go on the hard-AI runs.** The bag's Tenebrium isn't spent at home, so the proxy keeps choosing Rock Jungle jobs. v2 did seven door jobs in a row. In v4, once the core heroes were dead, it chose home four times in a row and was wiped each time. Two levers, both yours:
   - Should the pull ease after visits that spend nothing, or after wipes?
   - Should a company too thin to hold home (heroes dead, reserve small) feel less pull?

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
  - A shorter jobs screen; the legend folded into a Key (now one small toggle line; a generic box style had drawn it as an empty 56 px panel).
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
- Caution A/B: hero-sorties lost per run fell from 5.0 with no caution to 3.0 with the current one, and Ketha survived every sortie of the last trials. A Lua error had silently broken one version; it was found by a new harness test, fixed, and the runner now flags such errors.
- The door-hold fix won Rock Jungle doors and broke the home loop in v3.
- **Campaigns v3 and v4 both completed in 12 sorties**, winning the medium-soak finale on the second try. v4 lost its four core heroes by sortie 6 and still won.
- **Campaign v3** (everything up to the soak, the door hold, temper and the bleed rule): **completed in 12 sorties.**
  - The finale on the medium soak: partial (50/65), then won (65/65).
  - Vane and Halbard fell early (sorties 1 and 3), and the hollowed company lost three Rock Jungle drops to roaming raptors. The caution work since then is measured above.
- **Campaign v4** (everything as of 03:40), interim at sortie 10:
  - Sorties 1–5 all extracted clean (one victory, four partials), though Vane fell in sortie 1 (mission 1's opening).
  - **Sortie 6, a fortify job on Koom Valley's standing war**, killed Verse and Halbard. The pad was the fight, so the retreat led back into it. Fixed in cb8e5de: on a hot pad, the second leg steps further away. That fix is in the harness but not yet seen in the field: Koom isn't offered in the first three missions.
  - With Vane, Verse and Halbard gone, sorties 7–10 were four Rock Jungle wipes in a row: the pull home keeps choosing home for a company that can't hold it.
  - Sortie 11, the finale with every core hero dead: partial, 36 of 65, and Mask came home.
  - **Sortie 12 won the finale, 65 of 65. Campaign v4 completed in 12 sorties**, the same as v3, with no Lua errors in any row. It needed two finale tries again, which fits decision 1.
- **Two 7-sortie trials preferring Koom** (current code): 14 of 14 sorties came home, with no Lua errors. Three victories, ten partials and one Rock Jungle defeat.
  - Vane died in both: in mission 1 of trial 1, and by sortie 3 of trial 2. Halbard died by sortie 3 in both. That is decision 5's opening problem again, and Rock Jungle's.
  - Only trial 1 reached Koom, on its last sortie: partial, clean, Verse unhurt. **The hot-pad retreat still hasn't fired in the field**, because no hero pulled back on that drop.
  - Ketha went down 14 s in, about 830 from the pad, before caution's once-a-second check saw her hurt. She was walking toward a hostile rescue wreck. Her wreck was a heap (heavy overkill). Nothing from the baked battle stands within 1,500 of the pad. A Legion base (team `w`) begins about 1,700 from where she fell: cluster artillery ×3, light turrets ×10 and drone hives. So she most likely walked into artillery range.
  - This is a level question as much as a proxy one: a rescue wreck sits beyond an artillery base, and the critical hero's 1,500 leash lets her walk toward it. On the proxy side, I could keep a critical rez hero inside the pad's radius until the rescue path is quiet. That's untested.
- **Two 3-sortie trials on the current code** (hot-pad retreat included): 6 of 6 sorties came home, with no wipes and no Lua errors. Three victories and three partials, one of them a Rock Jungle drop. Trial 1 lost no heroes. In trial 2, Halbard fell in mission 1's opening, the same spot as decision 5. Neither trial was offered Koom, so two 7-sortie trials preferring Koom are running (`export\koom_act2_*.log`).

**Writing** (`docs/writing/`)
- 93 camp talks no longer read out internal role ids ("core_skirm seat beside core_rez.").
- **The cluttered feeling is mostly a template.** 60 generated talks share the same four middle lines and the close "Support locks. X and Y leave the hearth different."
- `talk_proposals.md` lists all 60 and drafts three replacements in the pairs' own voices (Ketha/Vane goes from 82 to 46 words). These are proposals; nothing was applied.

**Decision 4:** do the drafts in `talk_proposals.md` sound like your characters? If so, I'll write the rest the same way.

**Decision 5:** in mission 1's opening, Vane's pack meets about ten enemies 40 s in and he usually falls, even with caution working. Tune the opening's forces, or have the proxy pull heroes back pre-emptively when heavily outnumbered?
- New evidence (04:40, trial `koom_hotpad_2`, mission 1): caution did fire early. Ketha pulled back at 0.91 health with 5 enemies near and was down 28 s later. Halbard pulled back at 0.80 with 6 near and was down 69 s later. Neither was released back to work first.
- So pulling back sooner won't help much on its own. The retreat leg isn't safe: the enemy follows, or reaches wherever the hero stops.
- On the proxy side, the next things to try are an escort for a retreating hero, or retreating toward the nearest friendly army rather than a fixed step. I've left this until you choose between tuning the opening and changing the proxy.

**Not done or not verified**
- The HUD reviewer's density cuts to the mission rail (smaller rows, fewer lines). Some of what it would cut is yours by design ("Left if you lift"), so it waits for you.
- The rail's text is about 7 px on a 2560×1600 screen. A UI scale has to scale the EXTRACT button's click area too, so it needs an interactive test (headed BAR).
- The writing pass itself: only the role-id clean-up, the audit and three drafts are done.
- Hero temper is in the field, but nothing yet measures whether a steady hero behaves differently from a shaken one.

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
  - **Correction: the v2 and v3 arms ran with a bug.** From 9a5f6a4, the "step away from the enemies" retreat raised a Lua error on every pull-back with an enemy near. In `local ex, ez = x and threatCentroid(...)`, `and` keeps one value, so `ez` was nil. The error also left the order guard (`issuing`) stuck on, so BARb could override the rig's orders.
    - In those arms, no retreat order was ever given with enemies near.
    - v3's better numbers came from the Ketha leash, whose pull-backs happen with no enemies near.
    - Found by the new caution cases in `tools/hud_harness/autopilot_test.lua`; fixed in c847524 (the retreat now runs in pcall).
  - **Fixed caution** (`ab_caution4_*`, 3 runs): 3.0 hero-sorties lost per run (off 5.0, v1 3.7), 0.67 dead after sortie 1, 4/9 victories, 1 wipe, no Lua errors.
    - **Ketha survived every sortie of every run.**
    - The main casualty is now Vane, nearly always in mission 1's opening: about 40 s in, his pack meets ten enemies. Pulled back at 0.74, he falls about 25 s later. That opening is already flagged in RELEASE.md as wanting tuning from a human play.
  - The runner now records each sortie's Verdance Lua errors (`luaErrors` in the row) and warns.
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
