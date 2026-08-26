# In-client game loop + ship path — execution note (2026-07-25)

Head Hancho executed the **first iteration** of the approved plan:
*In-BAR Full Game Loop + Ship Path*.

---

## Shipped this pass

### Mode A — same-map seamless continue (WO-050..053)

| Piece | Behavior |
|---|---|
| Soft terminal | Victory/partial **skips `Spring.GameOver`** when same-map candidates exist |
| Debrief 1/2/3 | Same-map pick → `VA_CMD:vacontinue:N` → reseed in-place |
| Carry | Heroes + player units stay; enemy camp cleared/reseeds at new target |
| UX | Debrief labels `[same map]` / `[travel]`; continue reopens mission card |
| Telemetry | `VA_SOFT_TERMINAL`, `VA_CONTINUE`, result JSON still emitted per chapter |

### Mode B — strategic_link map travel (session host Reload path) — SHIPPED

**Capability gate:** `VA_CAPABILITY reload=true` (engine 2025.06.24) — see `outbound/18_CAPABILITY_MATRIX.md` + `outbox/va_capability.latest.json`.

| Piece | Behavior |
|---|---|
| Atlas edges | `world_zone_graph` `strategic_link` (7 authored corridors) |
| Resolve tool | `tools/mode_b_reload_travel.py` validates hop + stamps choice |
| Session host | `play_session_v1.ps1` phase `mode-b-travel` on every extract (key + fallback) before rebuild/relaunch |
| In-mod table | `mod/.../include/va_strategic_links.lua` (auto-emitted) |
| Debrief UI | injects Mode B travel candidates; tags `sessionMode=reload_travel` |
| Infolog | `VA_MODE_B_TRAVEL`, `VA_MODE_B_CANDIDATE`, `VA_UI_MAP_CHANGE_PICK` |
| Stamp | `outbox/mode_b_travel.latest.json` + `next_sortie_choice.json` |

**Still deferred:** in-engine `Spring.Reload(startscript)` — probe showed `io/write=false`; external relaunch is the Reload path until write works.

### Session host (WO-057)

`scripts/play_session_v1.ps1` (schema `verdance-play-session/1.2`):

- Default **auto-relaunch** after BAR exit (multi-mission, `MaxMissions=12`)
- Re-arms extract on **every unique `resultKey`** (Mode A multi-chapter in one launch)
- Mode B: after extract, resolve `strategic_link` pick → stamp `next_sortie_choice` → build → relaunch
- `-NoAutoRelaunch` restores old one-shot “next-ready” behavior
- Leave `PLAY_SESSION_V1.bat` open for a full sit-down session

### Capability probe v2 (WO-054)

`game_verdance_capability_probe.lua` logs:

```
VA_CAPABILITY {io=...,write=...,read_back=...,reload=...,os=...,engine=...,path=...}
```

Fill `outbound/18_CAPABILITY_MATRIX.md` from first live infolog after play.

### Seed + package

- `continueRules` baked into mission seeds by `build_next_mission_v1.ps1`
- Release docs: README / INSTALL / PLAYTESTING updated for session host + Mode A
- `docs/release/START_HERE.txt` (10-line cold start)
- `package_release.ps1` copies START_HERE + zone graph when present

---

## How to play-test now

```
C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\PLAY_SESSION_V1.bat
```

1. Start paused → mission card → unpause  
2. Win / extract → soft debrief (if same-map candidates)  
3. Press **1 / 2 / 3** → next chapter on **same map** (no BAR exit)  
4. Travel pick or exit BAR → session host builds + relaunches  

Debug: `/vacontinue N`, `/vanext N`, `/vastatus`

Infolog grep: `VA_SOFT_TERMINAL`, `VA_CONTINUE`, `VA_CAPABILITY`, `VA_PROBE_`

---

## Still deferred (plan L2–L4)

- In-engine `Spring.Reload(startscript)` once write/read-back GO  
- Prebaked mission packs without Python mid-session (community zip core)  
- Public Discord/Reddit cut + Package A zip build  
- Full RmlUi hub  

---

## Absolute paths (operator)

| Artifact | Path |
|---|---|
| Campaign gadget | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\mod\VerdanceAshes.sdd\luarules\gadgets\game_verdance_campaign.lua` |
| Objectives widget | `...\luaui\Widgets\gui_verdance_objectives.lua` |
| Session host | `...\scripts\play_session_v1.ps1` |
| START_HERE | `...\docs\release\START_HERE.txt` |
| This note | `...\outbound\18_IN_CLIENT_LOOP_AND_SHIP.md` |

---

*Play Koom, try 2–3 same-map continues; on a strategic corridor zone pick Mode B travel and let PLAY_SESSION relaunch. Capability matrix filled from headless evidence 2026-07-27; re-confirm on next live infolog.*
