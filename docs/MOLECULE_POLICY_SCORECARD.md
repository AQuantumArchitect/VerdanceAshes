# Molecule Policy — Stage 3 Human Seal Scorecard

**Gate:** Stage 4 soft live merge stays locked until this card is sealed.  
**Shadow tools:** `python tools/shadow_intent_v1.py run|smoke` · `python tools/phi_projector_v1.py smoke`  
**Faces:** `outbox/shadow_intent.latest.json` · `outbox/phi_shadow.latest.json`

---

## Latest shadow run (auto)

Fill after `python tools/shadow_intent_v1.py run` (example from first Stage 3 ship):

| Metric | Value |
|--------|------:|
| Overall agreement | **67.1%** (47/70) |
| Kiln / siege_plod | ~86% |
| Pad | 100% |
| Line | **~14%** (largest doctrine gap — molecule wants more push/preferDefenses) |
| Hardest scenarios | `dying` 40% · `kiln_heat_push` 40% |

Disagreement flavor to judge: dying skirmishers shadow-kite while live-bail; line/anvil shadow-push while live-hold; Mira shadow-kite on heat (artyish) vs live-hold.

---

## What to glance

1. Run shadow metrics:
   ```bash
   python tools/phi_projector_v1.py smoke
   python tools/shadow_intent_v1.py run
   ```
2. Check overall **agreement %** (shadow vs live hand IntentResolver on canned scenarios).
3. Skim **disagreements** — do they feel *more like the character* than live, or worse?
4. Pin heroes: **Kiln / Vane / Hearth / Mira** under heat, under-fire, craft, dying.

### Feel questions (2–3 Drops optional later)

| # | Question | Y / N / Notes |
|---|----------|---------------|
| 1 | Does shadow Kiln stay plod (no bail) when dying/heat? | |
| 2 | Does shadow Vane/skirm lean kite when under fire? | |
| 3 | Does shadow Hearth prefer craft/hold on eco surplus? | |
| 4 | Does Mira stay arty-ish (kite room), not kiln? | |
| 5 | Would soft-merging D(u) biases (α≈0.2) feel better than hand-only? | |

---

## Seal

| Field | Value |
|-------|-------|
| Date | 2026-09-10 |
| Agreement % (from face) | 67.1% (47/70) — formal Drop grind **skipped** |
| Seal | **PASS → Stage 4** (vibe seal) |
| Notes | Luke: not in the mood to test; cartoonish umwelt/molecule disagreements feel like they **add character** to heroes — treated as a positive. Soft **default on** for YOLO play; deploy to My Games. Rollback=`off`. |

**Law reminder:** soft bias only; BeliefField + player orders stay sacred. Rollback = leave flag off / set `off`.
