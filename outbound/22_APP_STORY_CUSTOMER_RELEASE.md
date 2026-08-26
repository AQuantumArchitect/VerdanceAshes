# Outbound 22 — App layout, proxy story, customer release

**Date:** 2026-07-25  
**Status:** shipped

## What changed

1. **Yurt-style app shell** under `app/`
   - `app/HOME.md` — places + verbs
   - `app/bin/` — launchers (fair arc, ant, story HTTP, customer export)
   - `app/bin/operator/` — former root bat spam
   - `app/story/latest/` — published proxy story
   - Root `HOME.md` + thin stubs only

2. **Story pipeline** (quantum graph → human tell)
   - `tools/quantum_bar_ai/story_teller.py` — chapters, beats, ant steam thoughts, markdown/html/lua
   - `tools/quantum_bar_ai/story_http.py` — hearth on `:8765`
   - `beat_first_arc --once` always publishes story + operator report

3. **Lua GUI**
   - `mod/.../gui_verdance_proxy_story.lua`
   - seed: `proxy_story_current.lua`
   - commands: `/vastory` `/vastorynext` `/vastoryprev` `/vastoryhide`

4. **Customer export**
   - `scripts/export_customer_release.ps1`
   - `app/bin/EXPORT_CUSTOMER.bat`
   - lands at `Documents\My Games\VerdanceAshes` (play room)
   - also mirrors zip under `export/customer/`

## Operator loop

```
app\bin\RUN_FAIR_ARC_ANT.bat
app\bin\SERVE_STORY.bat
app\bin\EXPORT_CUSTOMER.bat
```

Customer opens My Games pack → `PLAY.bat` → BAR; story via `WATCH_STORY.bat` or `/vastory`.
