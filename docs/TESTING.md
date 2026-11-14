# Testing Verdance's Ashes

How the game is tested, what each rig is for, and what was open when testing moved off wargen (2026-11-08). Everything here runs from a clone of this repo. Nothing depends on the old machine.

## Local CI, before every push

GitHub Actions minutes are scarce, so the CI workflow is manual only (`workflow_dispatch`) and GitHub is the save file. Before pushing to master, run `scripts\test\ci.bat`. It runs the hub tests with Umwelt at the pin, then the ship dry run and the staged-build check, which is what `.github/workflows/ci.yml` does, but with the real Umwelt instead of a stub. About a minute. `-TestsOnly` skips the build.

## The rigs, fastest first

| Rig | Needs | What it answers | How |
|---|---|---|---|
| Unit suite | Python 3, `UMWELT_SRC` for the belief tests | Does the code still do what it says? 680 tests, about 10 minutes. | `UMWELT_SRC=<umwelt>/src python3 tests/run_tests.py [name filters]` |
| Lua harness | Lua 5.4: `apt install liblua5.4-0`, or on Windows `winget install DEVCOM.Lua` (`VA_LIBLUA` points at another build) | Do the gadgets behave (autopilot, kings, exfil, heat ray…)? | `python3 tools/test_rig/run_lua.py tools/hud_harness/autopilot_test.lua` |
| No-BAR campaign | Python | Does a whole campaign walk with fake results (jobs, roads, pull home)? | `python3 tests/playthrough_campaign.py --sorties 20` |
| Hub snapshot + flow walk | Python, Playwright + Chromium | What does the player see at sortie N? Screens and word counts for a playtester. | `tools/test_rig/hub_snapshot.py N OUT`, then `tools/test_rig/flow_walk.py OUT SHOTS` |
| Screen tour | Windows, BAR | Every hub tab and BAR screen per sortie, plus each sortie's build inputs (the builder parity corpus). | `scripts\test\tour.bat` |
| Stock-BAR rehearsal | Windows, BAR installed and launched once | Does a sortie still load, fight and come home on a stock BAR? | `scripts\test\rehearsal.bat` (2 sorties) |
| Hard-AI campaign | Windows, BAR | Can a hard AI (BARb hard_aggressive) play the whole campaign, and where does it lose? | `scripts\test\campaign_hard.bat`; `finale.bat A`; `resume.bat autopilot_runs\<stamp>` |
| Release build | Windows, git tag on HEAD | The player zip. | bump `VERSION`, `git tag vX.Y.Z`, `tools\release.ps1 -Channel windows -DryRun` (see RELEASE.md) |

### The Windows bats (`scripts\test\`)

Double-click them. `autopilot.bat` prepares the environment the first time:
- `export\venv` with numpy and scipy. It uses `VA_PYTHON`, else `py -3`, else `python`.
- `export\cache\umwelt` at the commit pinned in `tools\umwelt_pin.json`. The Umwelt repo is private, so the machine needs GitHub access to clone it once.

It then runs `tools\autopilot_campaign_v1.py --stock` with the preset's arguments.
- `--stock` copies only the engine and the rapid game into `autopilot_runs\<stamp>\bar_data`, so your own BAR install and campaign are untouched.
- The log goes to `export\<preset>.log`. Each sortie is one line of JSON in `autopilot_runs\<stamp>\log.jsonl`, with the infologs and startscripts beside it.

Reading a run:
- `log.jsonl` gives map, choice, verdict, `wallSeconds` and `extraction` per sortie.
- In the infologs, `VA_TERMINAL kind=` says how a match ended: extracted, wiped, or a timeout.
- In the startscripts, `va_raptor_grace_seconds` and `va_raptor_clock_seconds` show the Rock Jungle raptor pace for that visit.

Useful autopilot flags:
- `--rival-ai SHORTNAME`: swap a rival's AI.
- `--allow-no-belief`: a diagnostic run without numpy or Umwelt. This is what a bare git clone on a new machine gets.
- `--prefer`: steer the job choice.

## The mission builder

Missions are built in Python: `python -m verdance.mission_builder`, called by the kernel's `build_mission()`.
- `scripts\build_next_mission_v1.ps1` stays as the reference. `VERDANCE_BUILDER=ps1` switches back to it.
- `tests/test_mission_builder_parity.py` holds the Python builder to the PowerShell one on three committed tours (`tests/fixtures/mission_builder/`). With `VA_BUILDER_CORPUS=<dir with tour/NN/build/>` it checks all 11 tours of the 2026-11-04 PC run.
- `build_scenario(..., ps1_faults=True)` reproduces the four PowerShell faults the game no longer has: war seats without colour, the lone warden that never took the field, BARb seats written `Version=<not-versioned>` (the engine never started them), and commanders on the map's random start points.
- To make a new corpus after a builder change, run `scripts\test\tour.bat`, then zip `autopilot_runs\<stamp>\tour\*\build`.

## What was open on 2026-11-08, and where it stands

The day-by-day record from 2026-11-09 on is `docs/DEVLOG.md`. The design state before that is in the project docs: VERDANCE_SMOOTH_PULL_AND_PY_BUILDER_2026-11-04 and VERDANCE_SORTIE_FLOW_BUILT_2026-11-04.

1. ~~The lift limit counts only victories and extractions.~~ **Done 2026-11-09** (owner call): the drop limit grows 1k with every sortie played, any verdict, no ceiling (`verdance.company.reserve`).
2. ~~Rock Jungle field recruits die at frame 120 with no wreck.~~ **Fixed 2026-11-09:** both are aircraft (seeds `armca`, `armstil`), and a quietly killed aircraft leaves no corpse. Air seeds now use a ground constructor that the rez promotes to the real chassis (`tests/test_field_recruit_seeds.py`). Not yet seen working in a live run: watch for `VA_FIELD_RECRUIT_AIR_PROXY`.
3. **The hard AI still loses at home.** The 11-09 baseline wiped six times in seven Rock Jungle visits. Being worked on: a five-minute grace floor, and a proxy player that plays BARb "hard" at home, leaves when the raptors are due and pulls hurt heroes back (DEVLOG).
4. ~~Playtester notes~~ **Done 2026-11-09:** compact hero cards with XP progress and Ketha's lock; blurbs without prices; a shorter jobs screen; recruits say where they are; hostile rescues always listed.
5. **The hot drop window fix is confirmed.** 0.15.0 played on the new laptop, so BAR is no longer minimized while it loads. Watch for the hub not getting the screen back: Windows' foreground lock can refuse. That is harmless, and BAR simply stays in front.
6. ~~`v0.15.0` is tagged only on wargen.~~ **Done 2026-11-09:** tagged on `cfb8f27` and released on GitHub.

## Moving the workspace to another machine

- **What git carries:** everything above. The local-only things are all in `.gitignore`.
- **Copy these if you want them:**
  - `state\` and `outbox\`: your own campaign save.
  - `export\cache\umwelt`: saves a clone.
  - `autopilot_runs\`: old runs for comparison. They are large; the 11-04 runs are summarised in the project docs.
- **Don't copy these; the bats rebuild them:**
  - `export\venv`: a venv is tied to its Python path.
  - `build\` and `export\dist\`.
  - `verdance_config.json`: it holds this machine's BAR path. SETUP writes it.
- **On the new machine:**
  1. Install BAR and launch it once.
  2. `SETUP.bat`.
  3. Run `scripts\test\rehearsal.bat` before anything long. It is the five-minute "does it come home" check.
- **The memory note from the old machine:** it had 4–5 GB of free commit with Chrome, ChatGPT and the Grok bot open. The autopilot tolerates a MemoryError while reading the infolog, but long hard-AI runs did better with less open.
