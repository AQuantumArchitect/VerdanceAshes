# WO-101 — Engine Capability Probe (RmlUi / IO)

**Date:** 2026-07-24  
**Engine path:** `C:\Users\Luke Spooner\AppData\Local\Programs\Beyond-All-Reason\data\engine\recoil_2025.06.24`  
**Source:** live infolog + `LuaUI/rml_setup.lua` (no new in-game gadget run)

---

## Five answers (DCO-02 §1)

| # | Question | Result |
|---|---|---|
| 1 | **Engine version** | **Spring Engine Version: 2025.06.24** (folder `recoil_2025.06.24`, spring.exe dated 2026-05-24) |
| 2 | **RmlUi present** | **YES.** Infolog: `[RmlUi::Initialize]`, `[RmlGui::InitializeLua]`, fonts load. `LuaUI/rml_setup.lua` guards on `RmlUi` global. |
| 3 | **io / os in unsynced LuaRules** | **UNVERIFIED in LuaRules this probe.** `LuaUI/savetable.lua` uses `io.open` successfully in UI. DCO-02 claims unsynced LuaRules has `io`/`os` by default — **needs a one-line gadget Echo** next session if we start the port. |
| 4 | **os.execute not stripped** | **UNKNOWN** — no evidence in engine tree scan; treat as **assume blocked / do not design around shell out** until probed in-game. |
| 5 | **Spring.Reload(startscript)** | **NOT probed this session.** BAR campaign harness already restarts matches via external scripts; in-engine Reload is still a Phase C milestone. |

---

## Array-model risk (the real DCO-02 gate)

DCO-02 says RmlUi **array indexing fixes** landed in the **2026.06** cycle. This engine is **2025.06.24**.

| Capability | Status |
|---|---|
| RmlUi boots and draws | Likely OK |
| Data model arrays for 45 zones / contracts | **RISK — may still be broken or partial** |
| Full deck port | **Do not start full port** until a tiny array-binding smoke widget is green |

---

## Head Hancho verdict

- **RmlUi is real on this install** — not vaporware.
- **Full DCO-02 port is still gated** on (a) array model smoke test, (b) LuaRules `io` write of `campaign_state.json`, (c) Reload loop.
- **Play-critical path stays:** external compile → BAR launch → extract result → Python advance. Clipboard / console deck remains valid forever.
- **Next RmlUi step (optional):** 20-line widget that binds a Lua array of 45 strings and renders `data-for` — if it fails, stay external.

---

## Navigation

| Item | Path | Len |
|---|---|---|
| Engine | `C:\Users\Luke Spooner\AppData\Local\Programs\Beyond-All-Reason\data\engine\recoil_2025.06.24` | 92 |
| Infolog (BAR data) | `C:\Users\Luke Spooner\AppData\Local\Programs\Beyond-All-Reason\data\infolog.txt` | 80 |
| This report | `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbound\WO-101_REPORT.md` | 88 |
