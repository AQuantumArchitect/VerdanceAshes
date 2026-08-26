# Capability matrix (WO-054) — fill from live play

**Status:** filled from headless infolog evidence (2026-07-27 shell bake).  
**Mode B gate:** `reload=true` → **GO** for session-host Reload path.

## How to fill

1. Run `PLAY_SESSION_V1.bat`, play until frame 45+ (probe fires).
2. Open BAR `data\infolog.txt`.
3. Search for `VA_CAPABILITY` and `VA_PROBE_`.
4. Paste results below.

## Results (operator / playtest)

| Probe | Result | Notes |
|---|---|---|
| `io` available | **false** | headless probe sandbox |
| write ok | **false** | no mid-match startscript write |
| read-back ok | **false** | depends on write |
| `Spring.Reload` present | **true** | do not call until startscript path exists |
| `os` available | **false** | headless probe |
| Engine version | **2025.06.24** | recoil |

```
VA_CAPABILITY {io=false,write=false,read_back=false,reload=true,os=false,engine=2025.06.24,path=}
```

**Evidence path:**  
`headless_runs/shell_bake_the_rock_jungle_20260727_232018/infolog.txt`  
Stamped: `outbox/va_capability.latest.json` (via `tools/mode_b_reload_travel.py --action stamp-capability`).

## Gates

| Feature | Requires | Decision |
|---|---|---|
| Mode A same-map continue | none (shipped) | **GO** |
| Persist runtime across Reload | write + read-back | **NO_GO** (io/write false) |
| Mode B in-engine `Spring.Reload` call | Reload + writable startscript | **DEFERRED** |
| Mode B session-host Reload path | Reload present + strategic_link atlas | **GO** (shipped pkt-bar-mode-b) |
| Session host Mode C | external only | **GO** (shipped) |

## Mode B wiring (2026-07-29)

| Piece | Path |
|---|---|
| strategic_link helpers | `tools/world_zone_graph.py` → `mode_b_travel_candidates` |
| session host resolve | `tools/mode_b_reload_travel.py` |
| session host loop | `scripts/play_session_v1.ps1` (schema 1.2, phase `mode-b-travel`) |
| in-mod edge table | `mod/.../include/va_strategic_links.lua` |
| debrief travel picks | `gui_verdance_objectives.lua` injects Mode B candidates |
| result stamp | `outbox/mode_b_travel.latest.json` + `next_sortie_choice.json` |

**Rule:** Mode A remains kernel default (`same_map`). Mode B only on `strategic_link` hops; session host rebuilds + relaunches (external Reload path). In-engine `Spring.Reload(startscript)` waits on write capability.

## Date filled

- Operator: worker-ant / wargen-grok (from headless evidence)
- Date: 2026-07-29
