# Tracked playtest

How to play the campaign so the session records itself, and what comes out.

## Play

```
PLAY_TRACKED.bat
```

Leave the console window open while you play. It builds the next mission from
`state/campaign_state.json`, launches BAR with tracking armed, waits for you to
finish, files the record, advances the campaign, and writes the analysis.

You should see a small `REC Verdance playtest` readout at the top-left in game.
If it is not there, the session is **not** being recorded -- see Troubleshooting.

### Ending a mission

Finishing the objective (or losing) ends it normally. To stop early and still
have the mission count, type in BAR's chat:

| Command | Effect |
| --- | --- |
| `/luarules vawin` | count it as a victory |
| `/luarules vafail` | count it as a defeat |
| `/luarules vapartial` | count it as partial |

Alt-F4 also works. You keep the full movement record; the mission just has no
outcome, and the campaign will not advance on it.

### Replaying the same mission

```
PLAY_TRACKED.bat -NoAdvance
```

Campaign state is backed up to `state/backups/campaign_state_<stamp>.json`
before every advance, so a bad result is always undoable.

## What gets recorded

Recorded by `luaui/Widgets/gui_verdance_playtest_recorder.lua`, from packets the
campaign gadget already computes:

| | |
| --- | --- |
| **Zone occupancy** | what every zone is worth, per team, sampled through the mission |
| **Border crossings** | which corridors your units actually use, and which sit unused |
| **Your orders** | move / fight / attack / patrol / build / reclaim / guard, counted over time |
| **Economy** | metal and energy, stock and income |
| **Army centroid** | where your force's centre of mass is, mission by mission |
| **Outcome** | verdict, frame, and the full result packet |

Written to `<BAR data>/LuaUI/Config/verdance/session_<stamp>.json` while you
play -- so a crash costs you nothing but the last few seconds.

## What comes out

| Path | What |
| --- | --- |
| `reports/human_zone_flow.latest.md` | readable summary: live vs inert corridors, zone peaks, verdict |
| `reports/human_zone_flow.latest.json` | the same, structured |
| `human_runs/session_<stamp>/session.json` | the raw session record |
| `human_runs/session_<stamp>/*.sdfz` | BAR's own replay of the match |

The analysis comes from `tools/ai_duel_zone_flow_v1.py` -- the same tool that
produced the 42-run AI matrix -- so a human session and an AI run are directly
comparable. The zone-flow sampler is deliberately pinned to the same 150-frame
observation rate the AI runs used; crossing counts depend on how often you look,
so they are only comparable at a shared rate.

## Collecting sessions without the launcher

If you played through some other path, or want to re-analyse:

```bash
python tools/collect_client_sessions_v1.py
```

Scans the client's session files, copies them into `human_runs/`, and runs the
analysis. `--list` shows what is there without collecting.

## Troubleshooting

**No `REC` readout in game.** The recorder removes itself when the session was
not launched with tracking armed. Check the startscript in `playable_runs/` for
`va_play_track=1`. `PLAY_TRACKED.bat` asserts this before you play and refuses to
launch without it, so this only happens on a hand-rolled launch.

**Unit icons missing at range / stale profiling settings.** A past headless run
left `UnitIconDist = 99999` in BAR's `springsettings.cfg`. `Spring.SetConfigInt`
writes through to that file unless its third argument (`useOverlay`) is true, and
the probe gadgets were missing it, so the setting outlived the process. Fixed at
source, but an already-written value stays written. Run
`PLAY_TRACKED.bat -RepairConfig` to restore it (a backup is written first).

The same runs may also have left `LuaUI = 0` in that file. That one is harmless:
the engine does not enumerate `LuaUI` as a config variable at all -- it is an
unrecognised key nothing reads. `-RepairConfig` removes it for tidiness.

**"No in-client record found".** The widget did not load. Most likely the mod is
installed as a full copy rather than a junction (a prior hub "Drop into battle"
does this), so it is running an older build. Re-run `PLAY_TRACKED.bat`, which
reinstalls first. The launcher falls back to reading the infolog, which produces
the same record a step later.

**Campaign jumped to a strange mission number.** The overnight AI probes leave
results in `inbox/`. `PLAY_TRACKED.bat` moves those to `inbox/quarantine/` before
every run; if you advanced by hand, restore from `state/backups/`.

## Notes

- Tracking does not change gameplay. It deliberately stays out of the profiling
  predicate that headless runs use, because that one disables the HUD, forces the
  sim to 20x, turns off waves and beats, and skips `Spring.GameOver`.
- `va_no_ui=1` is a separate modoption for headless probes that need no UI. Never
  set it for a real session.
