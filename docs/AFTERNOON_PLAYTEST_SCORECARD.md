# Afternoon Playtest Scorecard

**Date:** _______________  
**Home map / session:** _______________  
**Build:** kernel graph + shells + capture + attachments + world_tick  

## Pre-flight

- [ ] Snapshot exists: `state/backups/pre_afternoon_playtest/`
- [ ] Restore if needed: `powershell -File scripts/restore_afternoon_snapshot.ps1`
- [ ] Intent map matches compile (Mode A same-map)
- [ ] Debug: `/vastatus` `/vahelp` `/vawin` (emergency)

## Protocol (P0–P5)

| Step | Focus | Done? |
|------|--------|-------|
| P0 | Launch; briefing names war + map + objective | |
| P1 | Full sortie → debrief; Tnb number + scar/claim | |
| P2 | Mode A continue without full restart | |
| P3 | One deliberate fail or bloody win — story advances? | |
| P4 | Shop/loan if reachable (else note rig owns UI) | |
| P5 | Stop; dump scorecards + infolog slice | |

## Per-sortie log

### Sortie 1

| Field | Value |
|-------|-------|
| Win / partial / fail | |
| Extraction quality | |
| Tnb delta + bank | |
| Heroes alive / wounds | |
| Node claimed? | |
| Felt fair? (1–5) | |
| Wanted next? (Y/N) | |
| Surprise? | |

### Sortie 2

| Field | Value |
|-------|-------|
| Win / partial / fail | |
| Extraction quality | |
| Tnb delta + bank | |
| Heroes alive / wounds | |
| Node claimed? | |
| Felt fair? (1–5) | |
| Wanted next? (Y/N) | |
| Surprise? | |

### Sortie 3

| Field | Value |
|-------|-------|
| Win / partial / fail | |
| Extraction quality | |
| Tnb delta + bank | |
| Heroes alive / wounds | |
| Node claimed? | |
| Felt fair? (1–5) | |
| Wanted next? (Y/N) | |
| Surprise? | |

## Infolog greps

```
VA_RESULT
VA_TENEBRIUM_
VA_CAPTURE_
VA_NODE_CLAIMED
VA_POCKET_CLEARED
shellScars / VA_ shell
```

## Feel gates (circle)

- Coherent world (same war, scars persist)
- Dynamic next contract (not fixed list feel)
- Simulation weight (world moved / pushback)
- Care about Vane / Ketha / Null foothold
- Want one more sortie

## Bugs (severity: blocker / polish)

1. 
2. 
3. 

## Notes for retune (S6)

-
