# Playtesting Verdance's Ashes

Thanks for testing. The most useful thing you can do is **play 2–3 sorties in a row**
and tell us where the loop broke or felt wrong.

## The player path (use this)

```
app\bin\PLAY.bat
→ war map (kernel on http://127.0.0.1:8770/)
```

1. **First light** — read the welcome card (**How this works** reopens it anytime).
2. **Choose a sortie** — green cards in the center. Stay on home ground first.
3. **Briefing table** — green = objective, blue = landing. Defaults are usually fine.
4. **Drop into battle** — Beyond All Reason should open into the mission.
5. **Play** — briefing (Space to dismiss), clear the objective, extract if prompted.
   After a win, **1 / 2 / 3** can take the next pocket on the same map.
6. **Bring it home** — bridge usually auto-applies. Fallback: **After the fight — bring it home**.
7. Hire mercs, talk to Ketha, rest, or take the next drop.

Optional seat-only path (no war map): run `scripts\play_session_v1.ps1`.
(An older note here pointed at `app\bin\PLAY_AS_PLAYER.bat`; that file lives
under `app\bin\forge\`, which is a workspace-only tool and is never shipped.)

## What we're testing

1. **Clarity** — do you always know the next button to click?
2. **Seat loop** — multi-sortie without re-running bats?
3. **Carry-forward** — heroes and warband across same-map chapters?
4. **Objectives** — panel sense, victory/defeat correct?
5. **Pacing** — trivial, fair, or hopeless? Sortie length?
6. **Campaign feel** — does the world react across a few missions?
7. **Vibe** — does it feel like a game, or a tool?

## Feedback template

```
Build / date:
Missions played:
Same-map continues? (Y/N, how many):
What felt good:
What was confusing:
Where the vibe broke:
```
