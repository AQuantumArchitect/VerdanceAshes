# Umwelt gym pathway (BAR is downstream)

**Primary objective:** skill with **umwelt + cognifolds**.  
BAR player-proxy, residual, fruit, and organic free-CPU are a **gym** that feeds the field — not the center of gravity.

Canonical design (N-gym):  
`ws-win/yurt-sync/docs/N_GYM_PORTFOLIO.md`  

n=2 dual-gym notes:  
`ws-win/yurt-sync/docs/UMWELT_PRIMARY_DUAL_GYM.md`

## What Luke glances at

| Face | Where |
|------|--------|
| N-gym portfolio | hive `commons/vitals/muscle_portfolio.json` |
| Workstream registry | hive `commons/vitals/workstream_registry.json` |
| Dual farm slot (n=2 mirror) | hive `commons/vitals/dual_farm_supervisor.json` |
| Umwelt skill OKR | hive `commons/vitals/umwelt_skill_morning.json` |
| Cognifold live? | hive `commons/vitals/cognifold_faces.json` · BAR bridge `:8098/cognifold` |
| BAR residual | `outbox/hive_bar_residual.latest.json` (may include `umweltPost`) |
| Training morning | `outbox/training_pathway_morning.json` |

## Law (short)

- No densify · no god-brain · human seal sacred  
- Exclusive heavy slot: BAR unit **or** SpaceWheat leg, not both  
- umweltd dark → still farm; record dark; do not fail the unit solely for that  
- Cognifold dark is visible (flag), not silent  

## Bots

Dual-farm supervisor (coral) leases; organic loop is a **client**.  
SpaceWheat legs lease the same slot. AWS later: same acts, different muscle.

---

## Dev wishlist — full cognifold implementation

**Status:** post-playtest / spine skill work. Not G0.  
**Law:** no densify · no god-brain · dark banner > silent still field · human seal sacred.

### Already shipped (thin face — keep)

| Piece | Where | Note |
|-------|--------|------|
| Hero umwelt molecules | `data/story/hero_umwelt.json`, `tools/support_web_v1.py molecules` | Compact polarity icon per hero (carriers of significance) |
| Cultivated couples | support web edges + `umwelt` block | Energy supply↔hunger etc. — not authored force |
| Glyph chart | `docs/HERO_UMWELT.md` | Human-readable molecule table |
| Hub embed stub | `app/showoff/hero_umwelt.embed.js` | Offline face only |
| BAR cognifold bridge slot | `:8098/cognifold` · `cognifold_faces.json` | Often dark — flag, don't fake live |

### Wishlist — full cognifold (do in order)

1. **Shared cognifold schema (BAR × SpaceWheat × heroes)**  
   One `cognifold-face/2.x` dialect: axes, marks, η, dark flag, `ran_on`, timestamp.  
   Heroes reuse the same face shape as gym residuals (molecule ⊂ cognifold).  
   Refuse a second densified brain — extend the face, don't fork.

2. **Live BAR cognifold bridge**  
   Keep `:8098/cognifold` honest: stamp after sortie / residual observe.  
   Dark → visible banner on hub + morning OKR; never invent green.  
   Optional: fold hero-company aggregate molecule into the stamp (company umwelt).

3. **SpaceWheat icon-molecule parity**  
   Port SW cognifold / icon-molecule read path so Verdance molecules and SW glyphs share axis names + render contract.  
   Exclusive dual-farm lease still applies (BAR unit **or** SW leg).

4. **Hub cognifold panel**  
   Company column / hearth: per-ace molecule glyph, top marks, couple highlights (e.g. Hearth↔Kiln supply↔hunger).  
   Click mark → eligible support talks filtered by umwelt couple.  
   Offline embed OK; live prefers bridge face.

5. **Sortie → observe loop**  
   After Drop settle: update pair bonds (done) **and** refresh company cognifold from deployed aces' molecules + outcome tags (wound, extract, kiln_plod telemetry).  
   Residual `umweltPost` may carry the stamp; umweltd down → `umweltd_dark=true`, farm still OK.

6. **In-Drop marks (light)**  
   Optional HUD / bark when a high-η couple shares the field (support bark keyed off cognifold couple, not a second AI).  
   Soft doctrine shadow only — no densify.

7. **Morning / skill face**  
   Wire `umwelt_skill_morning.json` + `cognifold_faces.json` so Luke can glance: live/dark, last stamp, top cultivated couples, wishlist progress.  
   AWS promotion still gated on dual-gym acceptance checklist above.

8. **Authoring tools**  
   `support_web_v1.py molecules --couple` stays. Add: diff two stamps, export SVG/CSS glyph sheet, hand-pin mark overrides without killing cultivation.

### Explicitly out of wishlist scope

- God-brain merge of BAR + SW + heroes into one planner  
- Silent fake-live cognifold when bridge is dark  
- Replacing BeliefField / IntentResolver with a cognifold LLM  
- Shipping umweltd / SW engine inside the Steam depot for G0  

### Pointers

- Dual gym law: `ws-win/yurt-sync/docs/UMWELT_PRIMARY_DUAL_GYM.md`  
- N-gym: `ws-win/yurt-sync/docs/N_GYM_PORTFOLIO.md`  
- Support web / hearth: `docs/SUPPORT_WEB.md`  
- Hero graph umwelt foundation (co-evolve → observe → tensor): `docs/HERO_GRAPH_UMWELT_FOUNDATION.md`  
- Molecule policy brain (D(u) shadow → soft merge gates): `docs/MOLECULE_POLICY_BRAIN.md`  
- G0 freeze (this is post-playtest): `docs/G0_SCOPE_FREEZE.md`
