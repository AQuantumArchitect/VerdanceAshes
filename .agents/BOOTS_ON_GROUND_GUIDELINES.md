# Boots on the Ground Operating Guidelines

**Partner:** Grok Build (BAR Harness)  
**Workspace:** `C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace`  
**Adviser:** Web GUI Command Deck (clipboard packets only)

## Core responsibilities

1. **Information gathering & docs** — keep `outbound/` current for the web brain (assume it knows nothing about BAR).
2. **Headless / build execution** — compile seeds, install mod, run balance/smoke when asked.
3. **Campaign state truth** — all world changes land in `state/campaign_state.json`.
4. **Contract integrity** — illegal contracts get named rejects; never silent rewrite.
5. **Operator navigation** — every closing note includes **full absolute paths + character lengths** for places the user should open.

## Packet lifecycle

| Packet | Action |
|---|---|
| `VA-SORTIE/1` | `validate_sortie_contract.py` → `outbox/next_sortie_order.json` → story engine intent → `build_next_mission_v1.ps1` → install seed → short reply |
| `VA-WORK/1` | Queue in `WORK_ORDER_QUEUE.md` → implement → `outbound/WO-xxx_REPORT.md` → update `STATUS.md` |

## Build-first mode

When the operator says **no tests, just build**: implement and install; do not thrash the unittest suite. Keep code testable; run tests only when asked or before a risky release.

## Yurt (optional)

`C:\Users\Luke Spooner\ws-win\yurt` is Semantica/fleet ops. BAR does not depend on it. Do not block campaign work on hearth health.

## Safety

- Backup `campaign_state.json` before advances that write state.
- Do not force-push or print API keys / OAuth secrets.
- Prefer reversible local edits; confirm before destructive wipe of campaign state.

## Session close checklist

1. Update `STATUS.md` and `WORK_ORDER_QUEUE.md`.  
2. Write or refresh outbound handoff if the web brain needs new context.  
3. List full paths + lengths for operator navigation.  
