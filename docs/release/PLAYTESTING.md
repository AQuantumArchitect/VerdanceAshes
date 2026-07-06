# Playtesting Verdance's Ashes

Thanks for testing! The most useful thing you can do is **play 2–3 missions in a row**
and tell us where the loop broke or felt wrong.

## What we're testing

1. **The loop** — does build → play → auto-result → next mission actually flow without
   manual intervention?
2. **Objectives** — did the objective panel make sense? Did victory/defeat trigger when
   it should have? (Destroy-objectives complete when the target structures die; then you
   return to the extraction zone to finish.)
   A briefing card with Ketha's read on the situation shows at mission start (Space
   dismisses it); a debrief screen shows at mission end. Tell us if the lines fit what
   actually happened — that's generated, not scripted.
3. **Difficulty and pacing** — was the generated opposition trivial, fair, or hopeless?
   How long did the sortie take?
4. **Campaign feel** — after a few missions, does the world state (graph values, mission
   framing, Ketha's line) seem to respond to what you did?

## Reporting feedback

Post in the Discord thread (or open a GitHub issue) with:

```
Mission(s) played:      e.g. va_001 (greenest_fields), va_002 (eye_of_horus)
What happened:          short description
Expected:               what you thought should happen
```

For bugs, please attach:

1. `infolog.txt` from your BAR `data\` folder (grab it right after the broken match)
2. `workspace\outbox\play_session.status.json`
3. `workspace\state\campaign_state.json`
4. `workspace\inbox\latest_va_result.json` (if it exists)

## Debug commands (in-game chat)

Objectives are automatic, but these still exist for emergencies:

- `/vastatus` — current mission status
- `/vawin`, `/vafail`, `/vapartial` — force an outcome (use only if detection failed —
  and report that it failed!)
- `/vazones` — print the zone map the mission is using
- `/vahelp` — list commands
