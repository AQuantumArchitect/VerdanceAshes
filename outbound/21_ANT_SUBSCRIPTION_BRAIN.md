# Outbound 21 — quantum-BAR-AI on yurt **ant** subscription brains

**Date:** 2026-07-25  
**Status:** LIVE — first arc cleared with `ant_subscription` billing

## Law

From `yurt-sync/work/_wargen/plans/GROK_SUBSCRIPTION_BRAINS.md`:

| Priority | Path | Billing |
|----------|------|---------|
| 1 | `ant_brain.spawn_grok` + `~/.grok/auth.json` | **subscription** (`real_spend=0`) |
| Forbidden default | `XAI_API_KEY` / console.x.ai | metered API $ |

## Architecture

```
FairHUD + PlayerFacingCard  ──walls──►  umwelt belief graph
         │                                    │
         ▼                                    ▼
   free ToolBelt (read_*/think)     free LocalToolAgent chassis
         │
         │ every N ticks
         ▼
   ant_client.ant_decide
         │
         ▼
   ant_brain.spawn_grok(caste=verdance-proxy-ant)
         │
         ▼
   grok CLI (subscription session) → ACTION line → commit_action
```

- **Free chassis:** tools + beliefs + local policy between ant beats  
- **Steam:** Grok subscription via yurt ant (not HTTP xAI SDK)

## Proven run

```
python -m quantum_bar_ai.beat_first_arc --once --ant --ant-every 5 --difficulty 1.0
```

| Metric | Value |
|--------|-------|
| cleared | **true** 5/5 |
| agent | `ant_subscription` |
| ant calls | 21 |
| billing | **subscription** |
| wall | ~4.5 min total |
| backends | mix of `ant_subscription` + `local_tools_chassis` |

Example ant decision (smoke):
```
ACTION PUSH_OBJECTIVE | Edge felt, light quiet contact, team fresh — commit on converters before soft clock bites.
```
wall_s ≈ 8.9s · caste `verdance-proxy-ant`

## CLI

```bat
RUN_BEAT_FIRST_ARC_ANT.bat

REM or
set PYTHONPATH=tools;...\umwelt\src;...\yurt-sync\work\_wargen\coral
python -m quantum_bar_ai.beat_first_arc --once --ant --ant-every 5
```

## Code

| File | Role |
|------|------|
| `tools/quantum_bar_ai/ant_client.py` | wraps `ant_brain.check_auth_guard` + `spawn_grok` |
| `tools/quantum_bar_ai/ant_agent.py` | free tool chassis + subscription steam |
| `tools/quantum_bar_ai/beat_first_arc.py` | `--ant` / `--ant-every` |

## Tape

Ant brain turns also append to yurt:
`yurt-sync/commons/vitals/ant_brain_tape.jsonl` (caste `verdance-proxy-ant`).
