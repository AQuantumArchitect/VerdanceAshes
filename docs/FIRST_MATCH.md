# The first match, minute by minute

What a new player meets from PLAY.bat to the first objective of mission 1 (the opening raid on
Greenest Fields), and where they stall. Written 2026-11-02 for issue #4, from two sources:

- **The hub:** a fresh campaign (`init-state` + the reset's hub rebuild) served locally and clicked
  through in a browser.
- **The match:** the stock-BAR rehearsal on Luke's PC (`autopilot_campaign_v1.py --stock
  --sorties 1`, run `20261102_154330`): a BAR data folder with only the engine, packages, pool and
  rapid game, as beyondallreason.info installs it. The company was played by BARb (hard_aggressive),
  so its choices are a bot's, but every number the HUD showed is in the log.

Times in the match are game time from frame 0. **Stall** marks a place a player waits, guesses or
gives up. **Fixed** names the change on branch `claude/issue-4`.

## Before the match (wall clock)

| When | What the player sees | What they learn or feel | Stall |
|---|---|---|---|
| 0:00 | PLAY.bat opens the war map at 127.0.0.1:8770 with "Who are you?" over it: pick yourself and two more; Ketha always comes. | The company is people. Choosing feels good; **Recommend a team** works for anyone who doesn't want to read five cards. | — |
| ~0:30 | **Confirm company**. The seal takes a few seconds and the modal stays up meanwhile. | — | Small: no busy state on the button, so a second click is tempting. Not fixed here. |
| ~0:40 | Operations. The bottom rail shows five steps; four are already ticked (job, pad, target picked for mission 1). One button: **Ready the drop**. | Clear next action. | — |
| ~0:40 | The job card: "break the Armada's decoy's farms **on the southeast plateau** ... Hold the plateau too and the road to Koom Valley opens." The map and the rail say **Take Northwest Bastion**. "To win: Destroy the required raid targets." | Three different goals on one screen. | **Stall 2.** The card was written before the target moved next door (2026-10-25), and "To win" named the contract (eco raid) instead of what the game checks (clear and hold). **Fixed:** the card names the Northwest Bastion; "To win" says what taking a zone means, with the numbers. |
| ~1:00 | **Into the field**: party, reserve, mercenaries (recommended), then **Lock drop**. BAR starts loading behind the hub. | — | If the copy into BAR fails, the hub said only "mod sync failed". **Fixed:** it now says why (the installer's first error line). |
| ~1:30 | BAR loads. On a fresh BAR data folder the first load scans every archive: game frame 0 came **about 4½ minutes** after launch on Luke's PC. | Nothing moves; it looks hung. | Expectation only: BAR's own first-run scan. The docs now say the first drop on a new install loads for several minutes. |

## The match (game time)

| When | What happens | What the player learns or feels | Stall |
|---|---|---|---|
| 0:00 | The briefing card; Space dismisses it. The rail: `APPROACH 7:30 · presence 0 / 3871 · EXTRACT (nobody on our ground)`. | The clock, the job's gauge, the way out. | — |
| 0:00 | Two field-recruit heroes lie as wrecks on the map (Pavise and Cauter in this run). They log as "down" at frame 2. | — | The generic hero-down bark can fire here about strangers. Passed to the opening's author (#7), who owns the beats. |
| 0:02 | Yeva: "Nobody had looked at Northwest Muster. There is a column in it." The pad itself is dark ground with an enemy column on it. | Tension in the first seconds; the map is alive. | — |
| 0:48 | The same line for Northwest Bastion: the target is revealed by walking into it. | Discovery by doing. | — |
| 0:50 | Ketha's opening bark (beat `b1_move_out`). | — | — |
| 1:41 | 65 of 108 shell structures down: "Pocket clear. Hold the node — they will try to regrow it." The rail switches to `hold 0s / 30s · presence … / …`. Regrow pressure, wave 1, at 1:49. | The goal changes from breaking to holding. Good beat. | — |
| 1:41 – 15:00 | **The hold never starts.** The presence the hold needs climbs from 3,871 to 27,751 while the company's own is 0 – 1,040. The Null Mercs, the company's allies in the match, walk into the Bastion behind it (7,731 of presence by the end), and the claim counted them as "everyone else". Overtime from 8:00. The bot leaves on the clock at 15:00 with a partial. | Thirteen dead minutes. A human player does everything right and the bar never moves. | **Stall 1, the big one.** **Fixed:** the company's allies count neither for it nor against it, in the objective's hold, in the live extraction points and at home (`va_claim.lua`, `verdance.world.claim`). The hold now needs more than 1,500 of the company's own presence, and three times the enemy's. |
| any | When the hold clock sits at 0 the rail gave no reason unless an enemy was fighting on the zone. | "Is it broken?" | **Stall 3.** **Fixed:** the hold gauge reads `hold 0s / 30s · waiting for presence` (and turns the warning colour) while the company is short; the presence gauge beside it says how short. |
| 2:09 | Vane goes down (a hero wreck; Ketha can raise her). | A hero is at stake. | — |
| ~14:00 | (Headless rig, the capture seed with Halbard's heat ray.) `game_verdance_heatray.lua:83` raised in GameFrame every 10 frames, about 900 times: a Halberd that veterancy never touched has no `va_vet_range_mult` at all, and `tonumber()` of no value is an error. The burn ticks after it stopped too. | — | **Fixed**, with a harness case that fails without the fix. |

## Minutes 5 – 10, once the hold works

With the allies fix, a player who stands in the Bastion with more than 1,500 metal of army, and
three times whatever the Armada has left there, holds for 30 s and the objective completes around
the 3 – 5 minute mark. Then `MARKS` (bonus marks: the fusion vaults at the gates, Pavise's or
Cauter's wreck to raise) and `EXTRACT`: get onto the pad, press EXTRACT, confirm the manifest.
The 7:30 clock only ends in overtime, which wakes the map; nothing ends the sortie but the player.

## Not fixed here

- The seal button's missing busy state (above).
- Overtime pacing after a completed objective: not reached in this run, so not judged.
- A hands-on two-minute play on a stock install. The rehearsal is a bot. A human pass on the
  0.14.2 build is still wanted: does the player find the Bastion without reading, and does the
  hold feel fair?
