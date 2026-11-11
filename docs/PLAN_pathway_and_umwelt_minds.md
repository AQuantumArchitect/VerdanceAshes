# Plan: the pathway through Koom Valley, and Umwelt-driven hero minds

Written 2026-11-10, while the raptor-forecast trial ran. Two pieces of work, independent of each other:

1. **The pathway.** The Rock Jungle is where the company builds its army; from there it invades. The hub's recommendation guides the player along that path, through Koom Valley.
2. **Umwelt hero minds as a first-class product.** Umwelt drives hero behaviour in the field, and Verdance's work becomes a contribution back to the engine.

Both follow the standing rules: no magic numbers (scales come from unit defs, the bakes and the campaign's own numbers), every change trialled against master on identical campaigns, local CI green, push to master.

---

## Part 1 — The pathway: muster at home, invade through Koom

### Where it stands (facts)

- **The recommendation is a seeded random draw.** `roads.road_sorties` draws a "lean" card by softmax (temperature 0.75) over the legal door jobs (`tools/verdance/world/roads.py:363-376`, `:473-491`). The hub marks it "the world leans here", and the autopilot follows it.
- **Nothing in the scoring knows the company or the campaign.** It sees which maps are shut, leakage, rescues, faction bias and the home pull (`roads.py:279-335`). It doesn't see mission number or act, company strength, reserve, hero health, enemy strength, or past verdicts.
- **The Rock Jungle has no build-up job after its founding.** Road cards replace the home cards, including Journey A's "Hold the jungle shelf" (`build_hub_state.py:746-751`). After the founding, home offers only door takes (`door_TRJ_SE_OUTER_MUSTER`, `door_TRJ_NE_RIM`).
- **The army already persists.** What lifts goes into `roster.reserve` (`company/reserve.py:104-127`), and the drop limit grows by 1k per sortie played anywhere (`:73-77`). So a home sortie that builds and lifts does grow the army. The game just never says so, and never recommends it.
- **The only home lever is the Tenebrium pull.** `home_pull` (`campaign/home.py:89-96`) is ±1.2 on every Rock Jungle job. That's decision 3: the pull never lets go, and it drove the company into home wipe spirals (six wipes in seven visits on the baseline; four in a row in v4).
- **Koom Valley is mission 3 at the earliest:** take `GF_SE_PLATEAU`, cross to `KV_NW_MUSTER`, then take `KV_SE_MUSTER` (an Armada seat). Its opposition is the standing war, baked per tier (`data/base_templates/koom_valley/war_recipe.json`, t2/t3 snapshots).
- **The geographic road to the Overthrow pad** is Greenest Fields → Koom (NW→SE) → Tabula (NW→SE) → Bastion `AB_NE_HEIGHTS`. But the finale fires at mission 11 whatever is held, and its letter comes from path signals, not geography (`campaign/acts.py:110-145`, `measure.py:677-713`).

### The design

**1. A muster job at home.** It's the Rock Jungle's standing offer after the founding.
- It's a home sortie whose purpose is the army: build, hold the camp, lift what was built. The contract is the existing `fortify_zone` at `TRJ_NW_GATE`, plus a fortify-at-camp variant if the owner wants one.
- The raptor forecast already decides when it's time to leave (this week's work).
- What it pays is shown plainly: "the reserve grew by N units (X metal)".
- Plumbing: road cards merge with the home cards instead of replacing them (`build_open_node`, `:746-751`).

**2. A recommendation that weighs the company against the job.** It's continuous and has no thresholds. For each legal job (muster, take, cross, found, fetch):
- **Opposition** `F_job` is the known strength at the job's target, as sum of sqrt(dps × hp), from the belief board's zone strength, or from the bake snapshot for maps not yet walked. The bakes are known data: Koom's war at its visit tier, the Overthrow soak.
- **The company** `F_us` is the reserve the drop can bring (up to the drop limit), plus the heroes, from the same profiles.
- **Win share** is Lanchester's, as in the safety field: `keep = sqrt(1 − r²)` with `r = F_job / F_us`.
- **Worth:**
  - An invasion job is worth what it opens (a door, a map, progress toward the finale pad) times `keep`, against the company's expected losses.
  - The muster job is worth the army it adds, valued by how much that raises `keep` on the next invasion. That way muster is worth most exactly when the company is too weak to invade, and fades as it grows.
- **The recommendation is the argmax.** The existing "the world leans here" draw stays as story flavour, but becomes a second, separate mark. So **Recommended** means the company's best move, and **The world leans** means the story's pull. The autopilot follows Recommended.
- **This replaces the Tenebrium home pull** (decision 3). Home pulls because the army is thin, not because Tenebrium sits in the bag. A wiped company sees a big strength deficit and musters, instead of spiralling into raids.

**3. The path to the finale follows the road.** Optional; owner call below.
- Path signals take a geographic term: doors held on the Koom → Tabula → Bastion road push Path A.
- The hub's Koom card names what it's for: "the road to the Bastion runs through Koom Valley".

**4. The hub says why.**
- The recommended card's subtitle gives the reckoning in words: "The company fields 6k; Koom's war fields about 11k. Muster first."
- The rail sorts by recommendation, not just the narrative ranking (`narrative.py:299-307`, `shell.js:131-134`).

### Steps

1. Strength from data:
   - `F_job` per job from the belief board and the bake snapshots;
   - `F_us` from the reserve and the drop limit;
   - shared profile code with the safety field (one profile, Python and Lua parity-tested).
2. The muster job, plus the home/road card merge.
3. Recommendation by argmax, with the lean kept as a separate mark. Tests are rewritten where they pin today's draw (`tests/test_roads.py`, `test_home_pull_roads.py`, `test_theater_home_v083.py`, `test_autopilot_campaign.py`).
4. Retire the Tenebrium home pull (decision 3). Document it in the dev log and changelog.
5. Hub text and rail order; then walk the hub in the browser.
6. Trials: campaigns with **no `--prefer`** (the rig follows Recommended), paired against master.
   - What's measured: doors held by mission N, reaching Koom and then Tabula, hero deaths, home wipes, reserve size over time.
   - Success means Koom is invaded with a bigger army, there are fewer wipes, and the company reaches the Bastion road by act 3.

### What the trials showed (2026-11-11): nobody spends the Tenebrium

Across the 12 Rock Jungle sorties of the wave-forecast trial (two campaigns), Tenebrium stayed at 3 from start to finish, with `tenebriumSpent 0` and metal income 0. Nothing in the field could spend it:
- The player's commander is swept at game start (`VA_SWEEP_PLAYER_COMMANDERS keep=0`).
- The rig's band (verse, vane, halbard) has no builder, and the Rock Jungle's kit family ("wild") brings none. Only the "economy" family adds a `legck`.
- The rig's mercenary buyer spends metal only, by design ("Tenebrium is for builders").
- So BARb only ever had guns and one rez bot. The single spend in 12 sorties was a rez bot raising a wrecked constructor.

Tenebrium is a **stake**, not a cost (`va_tenebrium_handlers.lua`). Building a constructor, lab or nano puts its stake in (`ceil(buildSpeed / 150)`, so 1 for T1). Every living stake comes back to the bank at exfil, structures left behind included. Only shards left on the field when their unit died are lost. So "spend it all at home" costs nothing as long as the builders live, and what they build is real. Everything that lifts goes into the reserve (no ceiling), and the camp's buildings stay standing in the Rock Jungle for the next visit.

### Owner calls (2026-11-11)

- **The rhythm.** "They should go to the jungle, do a sortie while the builders spend all their Tnb, and then the next sortie should be out on the fields of battle again." Muster at home, then battle, then muster.
- **Muster and fortify are one mission type.** The home "Hold the jungle shelf" fortify at `TRJ_NW_GATE` *is* the muster. There's no separate camp contract.
- Still open: the finale path by geography (step 3 of the design), and whether to keep the lean mark visible.

### First slice (this week), from those calls

1. **The muster card is always on offer at home after the founding.** It's merged into the road cards instead of being replaced by them. Fortify at `TRJ_NW_GATE`, journey `muster`.
2. **Recommended = muster** when the bank can pay a builder's stake (at least the cheapest stake in the shop's constructors) *and* the last sortie wasn't a muster. Otherwise, a battle job. Among battle jobs, today's lean draw stands until the Lanchester weighing lands (design step 2). The card says why: "3 Tenebrium sits unstaked. Go home and build with it."
3. **The muster drop brings a builder.** The kit adds the camp's constructor (`legck`, a pre-spawned kit unit, so its stake is stamped and not charged). BARb stakes the rest of the bank in the field: a lab, more constructors, nanos. The lab prints the army from the jungle's metal.
4. **A muster isn't over when the gate is secured.** On a muster the autopilot doesn't leave on objective completion. It leaves on the wave forecast (now, or before a wave that would tip it) or the clock, so the builders have the whole safe window.
5. **The battle goes out (built 11-11).** Once home is founded, the recommended battle is the strongest job off the home map, when one is open. The lean keeps its mark.
6. **The strength reckoning, parked.** Reach from presence measured at the target misreads the jungle, where waves come and go (27,738 then 1,010 at one door), and hero packs make the company's landing weight nearly constant (about 10.7k). Next time, weigh the jungle's doors by the spawner's wave forecast and other maps by their bakes, with the harvested fight profiles (`data/story/unit_fight.json`) on both sides.
7. **Measure:** paired Rock Jungle → battle campaigns with no `--prefer`. Tenebrium staked per muster, reserve value after each muster, battle sorties' army size, and hero deaths.

---

## Part 2 — Umwelt hero minds as a first-class product

### Where it stands (facts)

- **In-game hero behaviour is already "a Lua port of the Umwelt host contract"**, written by hand (`game_verdance_unit_behavior.lua:19-34`):
  - scalar beliefs with confidence (`include/va_belief_field.lua`);
  - a world → team → squad → unit graph with roles `orders`, `hold`, `threat`, `pain`, `pressure` and `craft`;
  - an intent cascade with hysteresis (`include/va_intent_resolver.lua`), every 0.6 s, for named heroes.
- **Real Umwelt touches heroes only between sorties.** Temper (nerve, drive) runs on a throwaway Umwelt graph per drop and is shipped in `va_current.lua`. The belief world moves at homecoming.
- **Umwelt v0.2.0 has no built-in way to choose among actions.** Each `OutputSpec` is one tendril (one belief → a sticky binary or a linear scalar, shadow by default). Choosing among N actions is host logic: `AgencyLoop` routines, which are internal, or the app's own argmax. No reward-to-action learner exists; `BrainRunner` is an offline replayer.
- **Live Umwelt in the game loop is too slow at six roles per hero.** Measured on fenrir:
  - 5 heroes × 6 roles is about 575 ms per step (dense) and about 175 ms (cumulant);
  - 5 × 2 is about 29 ms.
- **There's no game-client path.** umweltd is HTTP on localhost, and synced BAR Lua has no I/O. Going through LuaUI sockets would add latency and break determinism for replays and multiplayer.
- **The per-role physics is a single-qubit Bloch vector, and it ports exactly:**
  - observe: `r ← (1−α) r + α·target`;
  - dissipative relaxation: `dz/dt = −γ(z − v)`, `dx, dy` decaying at γ/2, which has an exact exponential solution, so no RK4;
  - unitary kick: a rotation about x;
  - bridges: a mean-field nudge toward the pair's average, with the partner conjugated by σx for a negative coupling;
  - projection: a parent nudged toward its child;
  - read-out: value (z+1)/2, confidence |r|;
  - tendrils: pump, sticky collapse and egress gates, plain Python, also portable.
  - What doesn't port is the learned joint state (ZZ/XY couplings, calibration, forecasts). CLAIMS row 183 notes that local observations keep within-node correlation near 0 anyway.
- **There's precedent for doing it this way.** SpaceWheat's "Witness" is an in-engine port (`examples/manifold_game`). Umwelt's own open slots include a game bot built on OutputSpec tendrils (`examples/gridworld`) and FL-core's exit gate: "one playable loop where turning FL-core off makes the SI dumber in a measured way" (`FLEDGELING_CORE.md:345`).

### The design: one mind, two runtimes

**Specified once, in Umwelt.** Each hero's mind is an Umwelt `DomainSpec` in Python:
- a node per hero, with roles `threat`, `pain`, `orders`, `nerve`, `drive`, plus a few more;
- bridges to bonded heroes on the same drop, with coupling = bond points / 100 and negative for rivals, as temper uses now;
- dissipative γ from the spec's priors.

This one declarative spec is the single source of truth.

**Run live in Lua as a faithful port.** `include/va_umwelt_lite.lua` is a Bloch vector per role with the exact dissipative step, unitary kicks, bridges, projection and tendrils.
- It's generated from the spec: the hub writes the node, role, bridge and γ tables into `va_current.lua`, so the in-game mind *is* the spec.
- It's allocation-free, after this week's out-of-memory crash.

**Parity-tested against Umwelt.** A conformance suite feeds the same recorded observation streams to Python Umwelt (uncoupled roles) and to the Lua port through the existing liblua harness, and asserts that the beliefs match to tolerance. This turns "a Lua port of the Umwelt host contract" from a claim into a test.

**Choosing actions:**
- Each candidate intent (bail, kite, push, hold, raise, refuge) is scored by the safety field's `U = S × (V + G)`.
- The mind's Bloch state shapes S and G: nerve scales seen danger, drive scales gain (as now), and confidence scales commitment.
- Tendrils give each intent its hysteresis, which replaces the hand-tuned enter/leave cascade in `va_intent_resolver.lua`.

**Live bonds.** A friend going down in the field is an observation on that hero's node, and the bridge carries it to the living heroes in real time, not just at the next camp. This is the "sub-clustering expression" asked for on 11-09, live.

**Offline learning.** Between sorties, Python Umwelt replays the sortie's event log (`BrainRunner` on the hero minds' observation streams) and updates each hero's parameters (γ, coupling strengths, tendril pump rates) from outcomes. They ship in the next `va_current.lua`. The game acts; Umwelt learns at camp.

### Steps

1. **The hero-mind `DomainSpec`** in `tools/verdance/company/hero_mind.py`, plus the generator that writes the spec's tables into `va_current.lua`. Temper becomes this spec's initial state instead of its own throwaway graph.
2. **`va_umwelt_lite.lua`**, the runtime: Bloch roles, bridges, projection, tendrils. Allocation-free.
3. **Parity suite** (`tests/test_umwelt_lite_parity.py`): recorded streams, Python Umwelt against Lua, tolerance asserts. Plus a timing check against the 0.6 s think budget.
4. **Wire it in, shadow first.** The hero doctrine and autopilot caution read beliefs from the lite mind. Intents are decided by U × tendrils and logged in shadow beside the current resolver (`va_shadow_intent` exists for this). Only then do they go live.
5. **Live bonds:** down and death events become observations; check that grief and steadiness propagate within a sortie.
6. **Measure:** paired trials, Umwelt mind vs current resolver, on identical campaigns. Hero deaths, time alive, kills against losses, objectives. Umwelt's own law: it must beat the dumb baseline, or it isn't claimed.
7. **Offline learning:** replay plus parameter updates between sorties. Trials over a full campaign, to see whether heroes get better at staying alive as they gain experience.
8. **Contribute to Umwelt:**
   - (a) A worked example, `examples/bar_hero_minds` (or a name the Umwelt owner prefers): the spec, recorded streams and a CLAIMS row with the trial evidence. That fills the open "playable loop" gate.
   - (b) The conformance vectors, as a reference for any in-engine port: SpaceWheat's Witness, this, the next one.
   - (c) Ask to promote what Verdance depends on into the facade, through the STABILITY process: `foresight.encounter`, the agency loop, or a stable surface for the coupling access temper uses today.

### Owner direction (2026-11-11)

- **Sparse clusters, run in parallel.** "Umwelt should be able to run pretty efficiently in clusters of bits with only a few bridges across. If they all connect then it becomes a giant matrix and it's a mess, so keep it sparse and then run the clusters in parallel."
  - In the spec: a cluster is a hero plus the heroes it's bonded to on this drop. Bridges only cross between clusters where a bond does. The connected components of the bond graph are the units of work.
  - In the runtime: each cluster steps on its own, with no global matrix. The parity suite runs one cluster at a time.
- **Coarse and event-driven, not fast.** "It can update in coarse chunks as the battlefield updates. You can run the frames as things happen (like orders are given or the state of the known field changes)."
  - A cluster steps when one of its heroes gets an order, when the known field around it changes (the safety field's refresh, a sighting, a hit, a friend down), or on a slow heartbeat.
  - The step's dt is the real game time since that cluster's last step, which the exact dissipative solution handles at any size. So there's no per-frame cost, and quiet clusters cost nothing.
- **The resolver lives in the engine, and the HUD reads it through the same interface.** The Lua port is the runtime, not a mirror. Its beliefs and intents are published on the same rules params and `GG` surface the HUD and voice already read (`va_shadow_intent` and the hero cards), so the player sees the mind the units act on.
- **Learning happens between runs, while the player is in the menu.** The hub replays the sortie's observation log through Python Umwelt while the debrief and camp screens are up, and the next `va_current.lua` carries the update.
- **Camp decisions shape what a hero learns from the mission.** It's the owner's idea and fits the shape. What the player does at camp (who sits with whom, who's praised or blamed, who gets the rest) sets the learning step for that hero's replay: which observations weigh more, and which couplings are allowed to move. The same sortie teaches a praised hero confidence and a blamed one caution. It needs a spec for which camp choices map to which learning weights; draft that with the owner before building it.

### Progress (2026-11-11, overnight)

- **Steps 1–3 are done:**
  - **The spec:** `tools/verdance/company/hero_mind.py`. `mind_tables` splits the drop into clusters by its bonds, and `domain_spec` and `reference_run` are the Umwelt side.
  - **The runtime:** `include/va_umwelt_lite.lua`. It's allocation-free and frame-based.
  - **The parity suite:** `tests/test_umwelt_lite_parity.py`. Umwelt runs in a fresh fp64 process with learning frozen, against the Lua under Lua 5.4. Four clusters (a pair, rivals, a chain of three, one alone), 60 ingests each, with gaps past the catch-up cap and overwritten readings. The worst difference is 4.4e-16.
- **The math, from the source** (a00a0e7, GameHost path):
  - Each role is a Bloch vector. Every ingest is one fixed RK4 step, h = 0.01, and z relaxes toward the centre by P(−γh), with γ = 5.
  - Bridges nudge both ends toward their mean, scaled by 0.5·|c|, with the far end mirrored for a negative c.
  - A forced observation blends the vector toward (0, 0, 0.95·(2v−1)) by η.
  - Real time enters only through `ingest_hold_s`: min(⌊gap/hold⌋ − 1, 32) catch-up steps.
  - The default host also learns online (a Hamiltonian drawn from an unseeded RNG), so it isn't reproducible. The engine copy runs the frozen dynamics and learns between sorties instead (step 7).
- **One timing catch.** Umwelt's clock is whole microseconds, so 2.4 s / 0.6 s comes out at 3.9999999999999996: three holds, not four. The runtime takes game frames, and frames/30 is the same correctly-rounded double.
- **Step 4 is in shadow:**
  - The builder ships `mission.heroMind`.
  - `include/va_hero_mind.lua` sees, steps and publishes from the hero doctrine's think loop. The think period (0.6 s) is the hold, so each think is one step.
  - **Pain** is the share of health lost. **Threat** is 1 − exp(−incoming/hp × horizon), the safety field's own reading of staying.
  - A hero going down makes its node despair (nerve 0), and its cluster steps at once.
  - It publishes `va_mind_<role>` and `va_mind_<role>_c` on each hero unit, the same interface as `va_doctrine`. Nothing reads it yet.
- **A design call made here:** bridges carry mood (nerve, drive) only, as temper does. Threat and pain are a hero's own.
- **Done since:**
  - The sidebar draws nerve under each hero's health.
  - Mood holds for a sortie (γ = 0.1, from the 10-minute targetDuration).
  - A live mode, `va_hero_mind_live=1`, writes nerve and drive into the temper rows that caution and the doctrine read.
  - Trial 17's pair (live against shadow, identical code) both had 0 deaths in 8 sorties, so live isn't claimed yet.
- **Next:**
  - More pairs on harder ground before going live.
  - Read them in the safety field instead of the camp-fixed temper (S × (V + G) with live nerve and drive).
  - Then intents with tendril hysteresis, paired trials, and learning between runs.

### Owner calls needed

- **Where the contribution lives:** in the Umwelt repo (`examples/`, with the Lua as reference code), or in Verdance with only the spec and vectors upstream? Umwelt's layering law keeps applications out of `src/`, and examples are where foreign worlds go.
- **Scope of the first slice:** heroes only (named), or every unit the company fields? The cost budget says heroes first.
- **Learning:** offline only, as planned, or also a slow in-game adaptation?

---

## Order of work

1. Land the raptor forecast once its trial is in (this week's work).
2. **Part 1, the pathway.** It's the owner's next ask and touches the hub and Python side.
3. **Part 2, hero minds.** It's independent of Part 1 and touches the in-game Lua and the Umwelt spec, so it can run in its own session in parallel. Steps 1–3 (spec, Lua runtime, parity suite) need no trials and can start straight away.
