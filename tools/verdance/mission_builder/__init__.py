"""The mission builder: intent + campaign state -> the playable scenario BAR is installed from.

A port of scripts/build_next_mission_v1.ps1 (kept in the repo as the reference). It writes the same
scenario to data/scenarios/generated/next_mission_intent.playable.json, then hands the install step
(Lua seeds, startscript) to scripts/install_playable_slice.ps1 when a PowerShell host exists.

    python -m verdance.mission_builder --workspace W [--intent P] [--state P] [--launch]
                                       [--save-game] [--save-name N] [--extra-mod-options S]

Modules:
    _ps       Windows PowerShell 5.1 rules the output depends on (truthiness, casts, rounding)
    kits      unit specs, the company's kits, enemy camp rings
    shell     the living shell: templates, scars, the company's footprint
    field     teams, allyteams, forces, AIs and pacts: the camps put on the field
    builder   the build itself, the scenario, the install step, the manifest, the CLI
"""
from __future__ import annotations

__all__ = ["build_scenario", "main"]


def build_scenario(*args, **kwargs):
    from verdance.mission_builder.builder import build_scenario as _build

    return _build(*args, **kwargs)


def main(argv=None):
    from verdance.mission_builder.builder import main as _main

    return _main(argv)
