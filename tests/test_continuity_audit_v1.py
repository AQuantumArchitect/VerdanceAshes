"""Phase 0 continuity membrane inspector — Fatboy miss + fusion regen fixtures."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TOOLS = WS / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import continuity_audit_v1 as audit  # noqa: E402


def _fatboy_state() -> dict:
    return {
        "sessionHomeMap": "greenest_fields",
        "fieldPool": {
            "fatboy": {
                "heroId": "fatboy",
                "name": "Fatboy Contract",
                "unitDef": "armfboy",
                "status": "wild",
                "home": ["greenest_fields", "GF_NE_PLATEAU"],
                "recruit": {
                    "type": "wreck_rez",
                    "mapId": "greenest_fields",
                    "zoneId": "GF_NE_PLATEAU",
                },
            },
            "cauter": {
                "heroId": "cauter",
                "name": "Cauter",
                "unitDef": "legshot",
                "status": "wild",
                "home": ["greenest_fields", "GF_NW_BASTION"],
                "recruit": {
                    "type": "wreck_rez",
                    "mapId": "greenest_fields",
                    "zoneId": "GF_NW_BASTION",
                },
            },
            "spoke": {
                "heroId": "spoke",
                "status": "wild",
                "home": ["greenest_fields", "GF_C_INNER_GATE"],
                "recruit": {
                    "type": "wreck_rez",
                    "mapId": "greenest_fields",
                    "zoneId": "GF_C_INNER_GATE",
                },
            },
        },
        "shellScars": {
            "greenest_fields": {
                "byZone": {
                    "GF_NW_BASTION": {"destroyedCount": 3, "damageSum": 3.0},
                },
                "units": [
                    {
                        "zoneId": "GF_NW_BASTION",
                        "pocketId": "gf_central_s",
                        "unitDefName": "armsolar",
                        "destroyed": True,
                    }
                ],
            }
        },
        "zoneMemory": {
            "greenest_fields": {
                "GF_NW_BASTION": {"abstract": {"shellScar": 0.4}},
            }
        },
        "graph": {"q2_cohesion": 0.5},
        "company": {"sealed": False, "band": [], "core": []},
    }


def _mission_with_fusion(*, include_fatboy: bool, spawn_wreck: bool = True) -> dict:
    recruits = []
    if include_fatboy:
        recruits.append(
            {
                "heroId": "fatboy",
                "zoneId": "GF_NE_PLATEAU",
                "recruitMode": "wreck_rez",
                "beliefScore": 10.0,
                "spawnAsWreck": spawn_wreck,
            }
        )
    else:
        recruits.append(
            {
                "heroId": "cauter",
                "zoneId": "GF_NW_BASTION",
                "recruitMode": "wreck_rez",
                "beliefScore": 10.0,
                "spawnAsWreck": True,
            }
        )
        recruits.append(
            {
                "heroId": "spoke",
                "zoneId": "GF_C_INNER_GATE",
                "recruitMode": "wreck_rez",
                "beliefScore": 0.5,
                "spawnAsWreck": True,
            }
        )
    return {
        "missionBase": {
            "mapId": "greenest_fields",
            "targetZoneId": "GF_NE_PLATEAU",
            "fieldRecruits": recruits,
            "livingShell": {
                "requestedZoneId": "GF_NE_PLATEAU",
                "primaryZoneId": "GF_NW_BASTION",
                "pockets": [
                    {
                        "pocketId": "gf_c_gate_fus",
                        "zoneId": "GF_C_GATE",
                        "kind": "fusion_fort",
                        "optionalTarget": True,
                        "highValue": True,
                        "scarred": False,
                    }
                ],
                "units": [
                    {
                        "pocketId": "gf_c_gate_fus",
                        "zoneId": "GF_C_GATE",
                        "unitDef": "armfus",
                    },
                    {
                        "pocketId": "gf_c_gate_fus",
                        "zoneId": "GF_C_GATE",
                        "unitDef": "armbeamer",
                    },
                ],
            },
        }
    }


class ContinuityAuditTests(unittest.TestCase):
    def test_fatboy_mark_miss_is_high(self):
        state = _fatboy_state()
        mission = _mission_with_fusion(include_fatboy=False)
        result = {"mapId": "greenest_fields", "targetZoneId": "GF_NE_PLATEAU", "shellScars": []}
        report = audit.run_audit(
            WS,
            state=state,
            result=result,
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("recruit_mark_miss", codes)
        self.assertEqual(report["verdict"], "broken")
        self.assertEqual(report["exitHint"], 2)

    def test_fatboy_present_wreck_ok(self):
        state = _fatboy_state()
        mission = _mission_with_fusion(include_fatboy=True, spawn_wreck=True)
        # Avoid remap high finding dominating — align zones for this case.
        mission["missionBase"]["livingShell"]["primaryZoneId"] = "GF_NE_PLATEAU"
        result = {"mapId": "greenest_fields", "targetZoneId": "GF_NE_PLATEAU"}
        report = audit.run_audit(
            WS,
            state=state,
            result=result,
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertNotIn("recruit_mark_miss", codes)
        self.assertNotIn("recruit_live_poof", codes)

    def test_live_poof_flagged(self):
        state = _fatboy_state()
        mission = _mission_with_fusion(include_fatboy=True, spawn_wreck=False)
        mission["missionBase"]["livingShell"]["primaryZoneId"] = "GF_NE_PLATEAU"
        report = audit.run_audit(
            WS,
            state=state,
            result={"mapId": "greenest_fields", "targetZoneId": "GF_NE_PLATEAU"},
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("recruit_live_poof", codes)

    def test_fusion_regen_when_fusion_scarred(self):
        state = _fatboy_state()
        state["shellScars"]["greenest_fields"]["units"].append(
            {
                "zoneId": "GF_C_GATE",
                "pocketId": "gf_c_gate_fus",
                "unitDefName": "armfus",
                "destroyed": True,
            }
        )
        mission = _mission_with_fusion(include_fatboy=True)
        mission["missionBase"]["livingShell"]["primaryZoneId"] = "GF_NE_PLATEAU"
        report = audit.run_audit(
            WS,
            state=state,
            result={"mapId": "greenest_fields"},
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("fusion_regen_despite_hv_scar", codes)

    def test_beamer_scar_ignored_by_bake_rule(self):
        state = _fatboy_state()
        state["shellScars"]["greenest_fields"]["units"].append(
            {
                "zoneId": "GF_C_GATE",
                "pocketId": "gf_c_gate_fus",
                "unitDefName": "armbeamer",
                "destroyed": True,
            }
        )
        mission = _mission_with_fusion(include_fatboy=True)
        mission["missionBase"]["livingShell"]["primaryZoneId"] = "GF_NE_PLATEAU"
        report = audit.run_audit(
            WS,
            state=state,
            result={"mapId": "greenest_fields"},
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("fusion_regen_beamer_scar_ignored", codes)

    def test_fusion_witness_gap(self):
        state = _fatboy_state()
        mission = _mission_with_fusion(include_fatboy=True)
        mission["missionBase"]["livingShell"]["primaryZoneId"] = "GF_NE_PLATEAU"
        report = audit.run_audit(
            WS,
            state=state,
            result={"mapId": "greenest_fields"},
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("fusion_witness_gap", codes)

    def test_zone_remap_and_attention_abandoned(self):
        state = _fatboy_state()
        mission = _mission_with_fusion(include_fatboy=True)
        report = audit.run_audit(
            WS,
            state=state,
            result={"mapId": "greenest_fields", "targetZoneId": "GF_NE_PLATEAU"},
            mission=mission,
            marked=["GF_NE_PLATEAU"],
        )
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("objective_zone_remap", codes)
        self.assertIn("attention_zone_abandoned", codes)
        abandoned = next(f for f in report["findings"] if f["code"] == "attention_zone_abandoned")
        self.assertEqual(abandoned["zoneId"], "GF_NE_PLATEAU")
        self.assertEqual(abandoned["severity"], "high")

    def test_resolve_map_prefers_mission_map_over_session_home(self):
        """Playable packets put the sortie map on mission.map.id / deploymentMapId.

        sessionHomeMap is the camp (often the_rock_jungle). Auditing home scars
        against a GF livingShell produced false fusion_witness_gap toasts.
        """
        state = {
            "sessionHomeMap": "the_rock_jungle",
            "zoneMemory": {
                "the_rock_jungle": {
                    "TRJ_NE_SHALLOWS": {
                        "controllingFaction": "nullmercs",
                        "abstract": {"control": "nullmercs", "shellScar": 0.0},
                    }
                }
            },
            "shellScars": {},
            "fieldPool": {},
            "company": {"sealed": False, "band": [], "core": []},
        }
        mission = {
            "map": {"id": "greenest_fields", "name": "Greenest Fields 1.3"},
            "missionBase": {
                # Intentionally no mapId — real opener packets look like this.
                "deploymentMapId": "greenest_fields",
                "deploymentZoneId": "GF_NW_MUSTER",
                "fieldRecruits": [],
                "livingShell": {
                    "primaryZoneId": "GF_NW_BASTION",
                    "pockets": [
                        {
                            "pocketId": "gf_c_gate_fus",
                            "zoneId": "GF_C_GATE",
                            "kind": "fusion_fort",
                            "highValue": True,
                            "optionalTarget": True,
                            "scarred": False,
                        }
                    ],
                    "units": [
                        {
                            "pocketId": "gf_c_gate_fus",
                            "zoneId": "GF_C_GATE",
                            "unitDef": "armfus",
                        }
                    ],
                },
            },
        }
        mid = audit.resolve_map_id(state, {}, mission)
        self.assertEqual(mid, "greenest_fields")
        report = audit.run_audit(WS, state=state, result={}, mission=mission)
        self.assertEqual(report["sections"]["mapId"], "greenest_fields")
        codes = {f["code"] for f in report["findings"]}
        self.assertNotIn("fusion_witness_gap", codes)

    def test_live_workspace_smoke(self):
        """Runs against real campaign artifacts if present; never fails the suite hard."""
        state_path = WS / "state" / "campaign_state.json"
        if not state_path.exists():
            self.skipTest("no campaign_state")
        report = audit.run_audit(WS)
        self.assertIn(report["verdict"], {"continuous", "smelly", "broken"})
        self.assertIn("findings", report)
        # Must be JSON-serializable for outbox.
        json.dumps(report)


if __name__ == "__main__":
    unittest.main()
