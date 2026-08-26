# Experiment Registry

Log of headless balance tests, map probes, scenario simulations, and verification runs performed by the Boots-on-the-Ground Agent.

| Exp ID | Timestamp | Command / Scenario | Target Map | AI Seat / Variant | Outcome / Observations | Log Artifact |
|---|---|---|---|---|---|---|
| EXP-000 | 2026-07-24 | `python -m unittest discover tests` | N/A | Unit Test Suite | PASS (52/52 tests green) | Terminal Output |
| BUILD-004 | 2026-07-24 | build_next_mission_v1 (front-band + pack knobs) | koom_valley | alpha_player human | Seed installed; escalation 8×60s packs; requiredFrames 19800 | outbound/WO-004_REPORT.md |
| BUILD-010 | 2026-07-24 | extraction_zone_for rewrite | koom_valley | intent materialize | Extract SE shelf ~10691 elmos from NW deploy | outbound/WO-010_REPORT.md |
| PROBE-101 | 2026-07-24 | Engine infolog + RmlUi files | recoil_2025.06.24 | N/A | RmlUi initializes; array/io/Reload not greenlit | outbound/WO-101_REPORT.md |
| B0-CONTRACT | 2026-07-24 | validate_sortie_contract + materialize | koom central scar | nullmercs patron | Legal contract accepted; fromZones filled | outbox/next_sortie_order.json |

## Experiment Template

When running a new experiment, log:
1. **Experiment ID**: e.g., `EXP-001`
2. **Hypothesis / Objective**: What question does this experiment answer?
3. **Execution Command**: e.g., `powershell -ExecutionPolicy Bypass -File scripts/run_headless_balance_test.ps1 -ScenarioPath ...`
4. **Metrics Collected**: Victory/Defeat, Elapsed Time, Hero Wounds, Telemetry Packet, Infolog Markers.
5. **Synthesis**: Direct implications for campaign balance, story engine, or map layout.
