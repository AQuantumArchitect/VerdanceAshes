import copy
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verdance_story_engine_v1 as engine


def make_workspace() -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    zone_dir = root / "data" / "zone_maps" / "authored"
    zone_dir.mkdir(parents=True, exist_ok=True)
    (zone_dir / "ancient_bastion.authored.zone_map.json").write_text(
        """{
          "schemaVersion": "verdance-zone-map/0.2",
          "mapId": "ancient_bastion",
          "zones": [
            {"zoneId":"AB_WESTERN_MUSTER_GROUNDS","label":"Western Muster Grounds","role":"legion_start","tags":["start","west"]},
            {"zoneId":"AB_EASTERN_BASTION_WALL","label":"Eastern Bastion Wall","role":"fortress","tags":["bastion","fortress","defense"]}
          ]
        }""",
        encoding="utf-8",
    )
    (zone_dir / "the_rock_jungle.authored.zone_map.json").write_text(
        """{
          "schemaVersion": "verdance-zone-map/0.2",
          "mapId": "the_rock_jungle",
          "zones": [
            {"zoneId":"RJ_NW_JUNGLE_SHELF","label":"Northwest Jungle Shelf","role":"legion_start","tags":["start"]},
            {"zoneId":"RJ_CENTRAL_LAGOON_MAZE","label":"Central Lagoon Maze","role":"raptor_wilds","tags":["wilds","raptors"]}
          ]
        }""",
        encoding="utf-8",
    )
    (zone_dir / "greenest_fields.authored.zone_map.json").write_text(
        """{
          "schemaVersion": "verdance-zone-map/0.2",
          "mapId": "greenest_fields",
          "zones": [
            {"zoneId":"GF_NW_GREEN_START","label":"Northwest Green Start","role":"legion_start","tags":["start"]},
            {"zoneId":"GF_SE_SYNTH_START","label":"Southeast Synth Start","role":"cortex_start","tags":["start","economy"]}
          ]
        }""",
        encoding="utf-8",
    )
    return tmp


def sample_state():
    state = engine.default_v1_state()
    state["missionNumber"] = 1
    state["currentMissionId"] = "va_001"
    return state


def sample_result(**overrides):
    result = {
        "schemaVersion": engine.RESULT_SCHEMA,
        "campaignId": "verdance_ashes",
        "missionId": "va_001",
        "missionNumber": 1,
        "status": "victory",
        "mapId": "ancient_bastion",
        "deploymentMapId": "ancient_bastion",
        "deploymentZoneId": "AB_WESTERN_MUSTER_GROUNDS",
        "extractionStatus": "clean",
        "extractionZoneId": "AB_WESTERN_MUSTER_GROUNDS",
        "elapsedMinutes": 12,
        "pathSignal": "B",
        "destroyedObjectiveIds": ["AB_LRPC_EAST_WING"],
        "resultKey": "verdance_ashes|va_001|1|victory",
    }
    result.update(overrides)
    return result


def sample_telemetry():
    return {
        "schemaVersion": engine.TELEMETRY_SCHEMA,
        "exportId": "test-export",
        "matchId": "test-match",
        "map": {"name": "Ancient Bastion", "mapId": "ancient_bastion", "size": {"x": 16384, "z": 8192}},
        "frame": 21600,
        "seconds": 720,
        "terminal": {"isTerminal": True, "status": "victory", "winnerAllyTeamId": 0},
        "teams": [],
        "zones": {
            "AB_WESTERN_MUSTER_GROUNDS": {
                "zoneId": "AB_WESTERN_MUSTER_GROUNDS",
                "label": "Western Muster Grounds",
                "teams": {
                    "0": {
                        "teamId": 0,
                        "allyTeamId": 0,
                        "side": "legion",
                        "metrics": {
                            "armyValue": 3200,
                            "buildPower": 600,
                            "defensiveValue": 900,
                            "totalUnitValue": 5300,
                            "unitCount": 32,
                            "builderUnitCount": 3,
                            "structureCount": 10,
                        },
                        "unitCountsByDef": {"legcom": 1, "legwin": 8, "legllt": 2, "legcv": 2},
                    }
                },
            },
            "AB_EASTERN_BASTION_WALL": {
                "zoneId": "AB_EASTERN_BASTION_WALL",
                "label": "Eastern Bastion Wall",
                "teams": {
                    "1": {
                        "teamId": 1,
                        "allyTeamId": 1,
                        "side": "armada",
                        "metrics": {
                            "armyValue": 6000,
                            "buildPower": 800,
                            "defensiveValue": 9000,
                            "totalUnitValue": 16000,
                            "unitCount": 64,
                            "builderUnitCount": 4,
                            "structureCount": 30,
                        },
                        "unitCountsByDef": {"armllt": 8, "armbrtha": 1, "armwin": 12, "armcom": 1},
                    }
                },
            },
        },
    }


class StoryEngineV1Tests(unittest.TestCase):
    def test_measured_telemetry_updates_zone_memory_and_intent(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state, report, intent, events = engine.process_result(sample_state(), sample_result(), sample_telemetry(), root)
            self.assertTrue(report["processed"])
            self.assertEqual(state["schemaVersion"], engine.STATE_SCHEMA)
            wall = state["zoneMemory"]["ancient_bastion"]["AB_EASTERN_BASTION_WALL"]
            self.assertEqual(wall["confidence"], "measured")
            self.assertGreater(wall["abstract"]["fortification"], 0.5)
            self.assertIn("AB_LRPC_EAST_WING", state["destroyedObjectives"]["ancient_bastion"])
            self.assertEqual(intent["schemaVersion"], engine.INTENT_SCHEMA)
            self.assertEqual(events["schemaVersion"], engine.EVENTS_SCHEMA)

    def test_duplicate_result_does_not_mutate_state(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state, report, _intent, _events = engine.process_result(sample_state(), sample_result(), sample_telemetry(), root)
            before = copy.deepcopy(state)
            state2, report2, _intent2, _events2 = engine.process_result(state, sample_result(), sample_telemetry(), root)
            self.assertFalse(report2["processed"])
            self.assertEqual(before, state2)

    def test_five_elsewhere_missions_advance_ancient_bastion_about_sixty_minutes(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            wall = state["zoneMemory"]["ancient_bastion"]["AB_EASTERN_BASTION_WALL"]
            start_fort = wall["abstract"]["fortification"]
            for i in range(5):
                result = sample_result(
                    missionId="va_{:03d}".format(i + 1),
                    missionNumber=i + 1,
                    mapId="greenest_fields",
                    deploymentMapId="greenest_fields",
                    deploymentZoneId="GF_NW_GREEN_START",
                    destroyedObjectiveIds=[],
                    resultKey="verdance_ashes|va_{:03d}|{}|victory".format(i + 1, i + 1),
                )
                telemetry = {
                    "schemaVersion": engine.TELEMETRY_SCHEMA,
                    "exportId": "gf-{}".format(i),
                    "matchId": "gf-{}".format(i),
                    "map": {"name": "Greenest Fields", "mapId": "greenest_fields", "size": {"x": 8192, "z": 8192}},
                    "frame": 21600,
                    "seconds": 720,
                    "terminal": {"isTerminal": True, "status": "victory", "winnerAllyTeamId": 0},
                    "teams": [],
                    "zones": {},
                }
                state, _report, _intent, _events = engine.process_result(state, result, telemetry, root)
            wall_after = state["zoneMemory"]["ancient_bastion"]["AB_EASTERN_BASTION_WALL"]
            self.assertAlmostEqual(state["campaignClockMinutes"], 60.0, places=3)
            self.assertGreater(wall_after["abstract"]["fortification"], start_fort + 0.35)
            self.assertEqual(wall_after["offscreenEstimate"]["actor"], "SimpleDefenderAI")

    def test_wild_extraction_resets_live_raptors_but_escalates_pressure(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            state["missionNumber"] = 5
            state["currentMissionId"] = "va_005"
            engine.ensure_zone_memory(state, root)
            result = sample_result(
                missionId="va_005",
                missionNumber=5,
                mapId="the_rock_jungle",
                deploymentMapId="the_rock_jungle",
                deploymentZoneId="RJ_NW_JUNGLE_SHELF",
                extractionStatus="clean",
                elapsedMinutes=20,
                destroyedObjectiveIds=[],
                resultKey="verdance_ashes|va_005|5|victory",
            )
            state, report, intent, _events = engine.process_result(state, result, None, root)
            hazard = state["hazardState"]["the_rock_jungle"]["RJ_CENTRAL_LAGOON_MAZE"]
            self.assertTrue(report["processed"])
            self.assertTrue(hazard["liveUnitsReset"])
            self.assertGreater(hazard["pressure"], 0.0)
            self.assertEqual(intent["hazardPolicy"], "escalating_reset")


class StoryVoiceTests(unittest.TestCase):
    def test_pick_line_is_deterministic_and_within_pool(self):
        voice = engine.load_ketha_voice(ROOT)
        first = engine.pick_line(voice, "debrief.victory", "verdance_ashes", "va_007", "victory")
        second = engine.pick_line(voice, "debrief.victory", "verdance_ashes", "va_007", "victory")
        self.assertEqual(first, second)
        self.assertIn(first, voice["pools"]["debrief.victory"])
        other = engine.pick_line(voice, "debrief.victory", "verdance_ashes", "va_008", "victory")
        self.assertIn(other, voice["pools"]["debrief.victory"])

    def test_intent_carries_briefing_title_and_debrief_candidates(self):
        state = sample_state()
        state["graph"]["q7_resource_scarcity"] = 0.95
        intent = engine.materialize_next_intent(state, ROOT)
        self.assertTrue(intent["title"])
        tags = [line["tag"] for line in intent["briefing"]["lines"]]
        self.assertIn("situation", tags)
        self.assertIn("objective", tags)
        self.assertIn("pressure", tags)
        self.assertIn("path", tags)
        for key in ("victory", "defeat", "partial"):
            self.assertIn(key, intent["debriefCandidates"])

    def test_missing_voice_file_falls_back_without_error(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            intent = engine.materialize_next_intent(sample_state(), root)
            self.assertIsNone(intent["title"])
            self.assertEqual(intent["briefing"]["lines"], [])
            self.assertIn("victory", intent["debriefCandidates"])

    def test_story_events_use_commander_loss_and_streak_pools(self):
        state = sample_state()
        state["history"] = [
            {"missionId": "va_001", "status": "defeat"},
            {"missionId": "va_002", "status": "defeat"},
        ]
        result = sample_result(status="defeat", terminalReason="commander_lost", destroyedObjectiveIds=[])
        events = engine.generate_story_events(state, result, {"storyTags": ["defeat"]}, True, ROOT)
        texts = [e["text"] for e in events["events"] if e["kind"] == "dialogue"]
        voice = engine.load_ketha_voice(ROOT)
        self.assertIn(texts[0], voice["pools"]["debrief.defeat_commander"])
        self.assertTrue(any(t in voice["pools"]["debrief.streak.losses"] for t in texts[1:]))


if __name__ == "__main__":
    unittest.main()
