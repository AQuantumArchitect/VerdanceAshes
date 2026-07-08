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
            {"zoneId":"GF_SE_SYNTH_START","label":"Southeast Synth Start","role":"defender_start","tags":["start","economy"]},
            {"zoneId":"GF_NORTH_DESERT_EDGE","label":"North Desert Edge","role":"energy_edge","tags":["north","wind"]},
            {"zoneId":"GF_SOUTH_DESERT_EDGE","label":"South Desert Edge","role":"energy_edge","tags":["south","wind"]}
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


class WorldConflictTests(unittest.TestCase):
    def test_zone_control_reflects_mercs_vs_armada_world(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            gf = state["zoneMemory"]["greenest_fields"]
            # Synth economy reads as Cortex (accent power, never mixed with Armada).
            self.assertEqual(gf["GF_SE_SYNTH_START"]["controllingFaction"], "cortex")
            # First flank zone becomes the Null Merc foothold; only one per map.
            self.assertEqual(gf["GF_NORTH_DESERT_EDGE"]["controllingFaction"], "nullmercs")
            self.assertEqual(gf["GF_SOUTH_DESERT_EDGE"]["controllingFaction"], "neutral")
            self.assertEqual(state["offscreenActors"]["greenest_fields"]["GF_NORTH_DESERT_EDGE"], "NullMercsAI")
            # Re-running never grants a second foothold.
            engine.ensure_zone_memory(state, root)
            mercs = [z for z, m in gf.items() if m["controllingFaction"] == "nullmercs"]
            self.assertEqual(mercs, ["GF_NORTH_DESERT_EDGE"])

    def test_intent_world_conflict_block_tracks_merc_reputation(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            intent = engine.materialize_next_intent(state, root)
            conflict = intent["worldConflict"]
            self.assertEqual(conflict["primaryEnemy"], "armada")
            self.assertEqual(conflict["accentFaction"], "cortex")
            self.assertTrue(conflict["nullMercs"]["alliedWithPlayer"])
            self.assertIn("GF_NORTH_DESERT_EDGE", conflict["nullMercs"]["footholdZoneIds"])
            state["reputation"]["nullmercs"] = 25
            intent2 = engine.materialize_next_intent(state, root)
            self.assertFalse(intent2["worldConflict"]["nullMercs"]["alliedWithPlayer"])

    def test_merc_foothold_pressure_grows_offscreen(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            zone = state["zoneMemory"]["greenest_fields"]["GF_NORTH_DESERT_EDGE"]
            engine.tick_zone(zone, "NullMercsAI", "greenest_fields", 30.0, state)
            self.assertGreater(zone["abstract"]["militaryPressure"], 0.1)
            self.assertEqual(zone["controllingFaction"], "nullmercs")

    def test_faction_from_team_honors_explicit_tag(self):
        team = {"faction": "nullmercs", "side": "legion", "unitCountsByDef": {"legmg": 2}}
        self.assertEqual(engine.faction_from_team(team, "GF_NORTH_DESERT_EDGE"), "nullmercs")
        contractor = {"faction": "cortex", "side": "armada", "unitCountsByDef": {}}
        self.assertEqual(engine.faction_from_team(contractor, "GF_SE_SYNTH_START"), "cortex")

    def test_briefing_war_line_switches_on_merc_reputation(self):
        voice = engine.load_ketha_voice(ROOT)
        state = sample_state()
        objective = engine.objective_for_map("greenest_fields", state)
        briefing = engine.generate_briefing(state, voice, "greenest_fields", "economy", objective, {})
        war = [l for l in briefing["lines"] if l["tag"] == "war"]
        self.assertEqual(len(war), 1)
        self.assertIn(war[0]["text"], voice["pools"]["briefing.war.mercs_allied"])
        state["reputation"]["nullmercs"] = 20
        briefing2 = engine.generate_briefing(state, voice, "greenest_fields", "economy", objective, {})
        war2 = [l for l in briefing2["lines"] if l["tag"] == "war"]
        self.assertIn(war2[0]["text"], voice["pools"]["briefing.war.mercs_wary"])


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


class WarMapTests(unittest.TestCase):
    def test_enumerate_front_targets_offers_spine_plus_alternatives(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            candidates = engine.enumerate_front_targets(state)
            self.assertGreaterEqual(len(candidates), 2)
            self.assertLessEqual(len(candidates), 4)
            spine_map = engine.ALPHA_SPINE[0][0]  # mission 1 -> greenest_fields
            recommended = [c for c in candidates if c["recommended"]]
            self.assertEqual(len(recommended), 1)
            self.assertEqual(recommended[0]["mapId"], spine_map)
            valid_maps = {m for m, _ in engine.ALPHA_SPINE}
            for c in candidates:
                self.assertIn(c["mapId"], valid_maps)
                self.assertIn(c["objective"]["kind"], (
                    "economy_disrupt", "strike_relay", "seize_lane", "gate_control",
                    "destroy_key_structure", "hive_clear_or_bypass", "choose_target_then_extract"))
                self.assertTrue(c["consequenceIfIgnored"])

    def test_next_map_override_is_honored_then_cleared(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            state["nextMapOverride"] = {"mapId": "the_rock_jungle", "deploymentZoneId": "RJ_NW_JUNGLE_SHELF"}
            self.assertEqual(engine.choose_next_map_zone(state), ("the_rock_jungle", "RJ_NW_JUNGLE_SHELF"))
            state, report, _intent, _events = engine.process_result(
                state,
                sample_result(mapId="the_rock_jungle", deploymentMapId="the_rock_jungle",
                              deploymentZoneId="RJ_NW_JUNGLE_SHELF", destroyedObjectiveIds=[],
                              resultKey="verdance_ashes|va_001|1|victory"),
                None, root)
            self.assertTrue(report["processed"])
            self.assertNotIn("nextMapOverride", state)

    def test_front_decay_flips_neglected_ashwalker_zone(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            ab = state["zoneMemory"]["ancient_bastion"]
            ab["AB_EASTERN_BASTION_WALL"]["controllingFaction"] = "armada"
            ab["AB_EASTERN_BASTION_WALL"]["abstract"]["control"] = "armada"
            ab["AB_EASTERN_BASTION_WALL"]["abstract"]["militaryPressure"] = 0.6
            west = ab["AB_WESTERN_MUSTER_GROUNDS"]
            self.assertEqual(west["controllingFaction"], "ashwalkers")
            flips = []
            for _ in range(4):
                # Active map is elsewhere, so ancient_bastion keeps eroding.
                flips += engine.apply_front_decay(state, "greenest_fields", [], 20.0)
            self.assertEqual(west["controllingFaction"], "armada")
            self.assertTrue(any(f["zoneId"] == "AB_WESTERN_MUSTER_GROUNDS" for f in flips))
            self.assertTrue(any(ev["type"] == "zone_lost" for ev in state["frontEvents"]))

    def test_front_decay_does_not_fire_without_enemy_pressure(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            flips = engine.apply_front_decay(state, "greenest_fields", [], 30.0)
            self.assertEqual(flips, [])

    def test_build_war_map_snapshot_shape(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            war = engine.build_war_map(state)
            self.assertEqual(len(war["regions"]), len(engine.ALPHA_SPINE))
            for region in war["regions"]:
                self.assertIn("control", region)
                self.assertIn("threatBand", region)
            self.assertTrue(war["candidates"])


class RosterTests(unittest.TestCase):
    def _win(self, n, survivors):
        return sample_result(
            missionId="va_{:03d}".format(n), missionNumber=n,
            mapId="greenest_fields", deploymentMapId="greenest_fields",
            deploymentZoneId="GF_NW_GREEN_START", destroyedObjectiveIds=[],
            playerSurvivors=survivors,
            resultKey="verdance_ashes|va_{:03d}|{}|victory".format(n, n))

    def test_roster_grows_from_survivors_and_levels_commander(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            for n in range(1, 6):
                state, _r, intent, _e = engine.process_result(state, self._win(n, {"legcen": 6, "leggat": 8}), None, root)
            commander = state["roster"]["commander"]
            self.assertGreater(commander["level"], 1)
            self.assertTrue(commander["perks"])
            self.assertTrue(state["roster"]["cadre"])
            # Cadre never exceeds the (possibly perk-boosted) cap.
            self.assertLessEqual(sum(state["roster"]["cadre"].values()), state["roster"]["cadreCap"])
            self.assertEqual(intent["roster"]["cadreCap"], state["roster"]["cadreCap"])

    def test_cadre_trims_to_cap(self):
        trimmed = engine.trim_cadre({"legcen": 20, "leggat": 20}, 12)
        self.assertLessEqual(sum(trimmed.values()), 12)

    def test_defeat_scars_commander_and_suppresses_perks(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            # Earn a perk first.
            for n in range(1, 4):
                state, _r, _i, _e = engine.process_result(state, self._win(n, {"legcen": 6}), None, root)
            self.assertTrue(state["roster"]["commander"]["perks"])
            state, _r, intent, _e = engine.process_result(
                state,
                sample_result(missionId="va_004", missionNumber=4, status="defeat", extractionStatus="",
                              mapId="greenest_fields", deploymentMapId="greenest_fields",
                              deploymentZoneId="GF_NW_GREEN_START", destroyedObjectiveIds=[],
                              playerSurvivors={"legcen": 1},
                              resultKey="verdance_ashes|va_004|4|defeat"),
                None, root)
            self.assertTrue(state["roster"]["commander"]["scars"])
            # Perks are retained but suppressed for the wounded mission.
            self.assertTrue(state["roster"]["commander"]["perks"])
            self.assertEqual(intent["roster"]["commander"]["activePerks"], [])
            self.assertTrue(intent["roster"]["commander"]["scarred"])

    def test_intent_exposes_roster_and_merc_foothold_scale(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            intent = engine.materialize_next_intent(state, root)
            self.assertIn("roster", intent)
            self.assertIn("commander", intent["roster"])
            self.assertIn("cadre", intent["roster"])
            scale = intent["worldConflict"]["nullMercs"]["footholdScale"]
            self.assertGreaterEqual(scale, 0.85)  # allied at default rep 43
            state["reputation"]["nullmercs"] = 20
            intent2 = engine.materialize_next_intent(state, root)
            self.assertLess(intent2["worldConflict"]["nullMercs"]["footholdScale"], 0.85)


def _zone(control, mil=0.0, base=0.0, eco=0.0, hazard=0.0, instab=0.5, fort=0.0):
    return {
        "controllingFaction": control,
        "abstract": {"control": control, "militaryPressure": mil, "baseStrength": base,
                     "economyMomentum": eco, "hazardPressure": hazard, "instability": instab,
                     "fortification": fort, "objectiveDamage": 0.0},
    }


class GraphEmergenceTests(unittest.TestCase):
    def test_q0_tracks_measured_faction_density(self):
        state = engine.default_v1_state()
        state["zoneMemory"] = {"m": {"a": _zone("cortex", base=0.9), "b": _zone("armada", base=0.1)}}
        before = state["graph"]["q0_armada_cortex"]
        engine.measure_graph_from_world(state, {})
        self.assertGreater(state["graph"]["q0_armada_cortex"], before)  # eased toward cortex-heavy
        # Armada-heavy world pulls it back down.
        state["zoneMemory"] = {"m": {"a": _zone("armada", base=0.9), "b": _zone("cortex", base=0.1)}}
        mid = state["graph"]["q0_armada_cortex"]
        engine.measure_graph_from_world(state, {})
        self.assertLess(state["graph"]["q0_armada_cortex"], mid)

    def test_q7_falls_as_economy_develops(self):
        state = engine.default_v1_state()  # q7 default 0.98
        state["zoneMemory"] = {"m": {"a": _zone("ashwalkers", eco=0.8), "b": _zone("cortex", eco=0.7)}}
        engine.measure_graph_from_world(state, {})
        self.assertLess(state["graph"]["q7_resource_scarcity"], 0.98)

    def test_q2_rises_with_disorder(self):
        state = engine.default_v1_state()  # q2 default 0.15
        state["zoneMemory"] = {"m": {
            "a": _zone("armada", base=0.3, hazard=0.6),
            "b": _zone("cortex", base=0.3, hazard=0.6),
            "c": _zone("wild", base=0.3, hazard=0.6),
        }}
        engine.measure_graph_from_world(state, {})
        self.assertGreater(state["graph"]["q2_void_structure"], 0.15)

    def test_warband_props_up_q6_independent_without_dragging_down(self):
        state = engine.default_v1_state()
        engine.ensure_roster(state)
        state["roster"]["cadre"] = {"legcen": 12}
        state["roster"]["commander"]["level"] = 3
        state["graph"]["q6_independent"] = 0.05  # clans reading marginal
        engine.measure_graph_from_world(state, {})
        self.assertGreaterEqual(state["graph"]["q6_independent"], 0.14)  # floored up by the warband
        # A strong existing sovereignty is never dragged DOWN by the floor.
        state["graph"]["q6_independent"] = 0.6
        engine.measure_graph_from_world(state, {})
        self.assertGreaterEqual(state["graph"]["q6_independent"], 0.6)

    def test_front_decay_direction_follows_q0(self):
        def run(q0):
            state = engine.default_v1_state()
            state["graph"]["q0_armada_cortex"] = q0
            state["graph"]["q6_contested"] = 0.85
            state["zoneMemory"] = {"m": {
                "ash": _zone("ashwalkers"),
                "arm": _zone("armada", mil=0.6),
                "cor": _zone("cortex", mil=0.6),
            }}
            flips = []
            for _ in range(8):
                flips += engine.apply_front_decay(state, "other", [], 20.0)
                if flips:
                    break
            return flips[0]["toFaction"] if flips else None
        self.assertEqual(run(0.85), "cortex")   # Cortex ascendant claims the ground
        self.assertEqual(run(0.15), "armada")

    def test_front_decay_rate_scales_with_contested(self):
        def enc_after_one(q6c):
            state = engine.default_v1_state()
            state["graph"]["q6_contested"] = q6c
            state["graph"]["q0_armada_cortex"] = 0.15
            state["zoneMemory"] = {"m": {"ash": _zone("ashwalkers"), "arm": _zone("armada", mil=0.6)}}
            engine.apply_front_decay(state, "other", [], 20.0)
            return state["zoneMemory"]["m"]["ash"]["encroachment"]
        self.assertGreater(enc_after_one(0.9), enc_after_one(0.2))

    def test_intent_exposes_resource_modifier_and_allies(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            state["graph"]["q7_resource_scarcity"] = 0.98
            state["graph"]["q0_armada_cortex"] = 0.8
            intent = engine.materialize_next_intent(state, root)
            self.assertLess(intent["economy"]["resourceModifier"], 1.0)   # scarcity thins economy
            self.assertIn("cortex_defectors", intent["roster"]["availableAllies"])  # Cortex ascendant
            self.assertIn("ashwalkers", intent["roster"]["availableAllies"])

    def test_war_map_carries_world_reading_and_graph(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            war = engine.build_war_map(state)
            self.assertIn("worldReading", war)
            self.assertTrue(war["worldReading"])
            self.assertIn("q6_contested", war["graph"])


class SpectralMeasurementTests(unittest.TestCase):
    def test_jacobi_eigen_matches_known_spectra(self):
        vals, _ = engine.jacobi_eigen([[2.0, 1.0], [1.0, 2.0]])
        self.assertEqual(sorted(round(v, 6) for v in vals), [1.0, 3.0])
        vals3, _ = engine.jacobi_eigen([[5.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 1.0]])
        self.assertEqual(sorted(round(v, 6) for v in vals3), [1.0, 3.0, 5.0])

    def _packet(self):
        return {
            "global": {"hydrology": {"saturation": 0.2}},
            "nodes": [
                {"zoneId": "A", "density": 0.9, "hydroCoupling": 0.05},
                {"zoneId": "B", "density": 0.4, "hydroCoupling": 0.05},
                {"zoneId": "C", "density": 0.35, "hydroCoupling": 0.05},
            ],
            "entanglements": [
                {"zoneIds": ["A", "B"], "coupling": 0.28},
                {"zoneIds": ["B", "C"], "coupling": 0.25},
            ],
        }

    def _state_with_control(self):
        state = engine.default_v1_state()
        state["zoneMemory"] = {"m": {
            "A": {"controllingFaction": "cortex", "abstract": {"control": "cortex"}},
            "B": {"controllingFaction": "armada", "abstract": {"control": "armada"}},
            "C": {"controllingFaction": "armada", "abstract": {"control": "armada"}},
        }}
        return state

    def test_spectral_summary_reads_dominant_faction(self):
        state = self._state_with_control()
        s = engine.spectral_summary(self._packet(), state)
        self.assertIsNotNone(s)
        self.assertEqual(s["zones"], 3)
        # Zone A (Cortex) is densest + entangled, so it dominates the principal mode.
        fw = s["factionWeights"]
        self.assertGreater(fw.get("cortex", 0), fw.get("armada", 0))

    def test_spectral_blends_into_q0(self):
        # Same world, but a Cortex-dominant battlefield observable pushes q0 higher.
        base = engine.default_v1_state()
        base["zoneMemory"] = {"m": {"a": _zone("cortex", base=0.5), "b": _zone("armada", base=0.5)}}
        no_spec = copy.deepcopy(base)
        engine.measure_graph_from_world(no_spec, {}, None)
        with_spec = copy.deepcopy(base)
        spectral = {"factionWeights": {"cortex": 0.9, "armada": 0.1}, "spread": 0.3}
        engine.measure_graph_from_world(with_spec, {}, spectral)
        self.assertGreater(with_spec["graph"]["q0_armada_cortex"], no_spec["graph"]["q0_armada_cortex"])

    def test_process_result_accepts_translation_and_records_spectral(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            packet = self._packet()
            # Point packet zoneIds at real greenest_fields zones so control resolves.
            packet["nodes"][0]["zoneId"] = "GF_SE_SYNTH_START"
            packet["nodes"][1]["zoneId"] = "GF_NW_GREEN_START"
            packet["nodes"][2]["zoneId"] = "GF_NORTH_DESERT_EDGE"
            packet["entanglements"] = [{"zoneIds": ["GF_SE_SYNTH_START", "GF_NW_GREEN_START"], "coupling": 0.28}]
            state2, report, _i, _e = engine.process_result(
                state,
                sample_result(mapId="greenest_fields", deploymentMapId="greenest_fields",
                              deploymentZoneId="GF_NW_GREEN_START", destroyedObjectiveIds=[],
                              resultKey="verdance_ashes|va_001|1|victory"),
                None, root, packet)
            self.assertIsNotNone(report["spectral"])
            self.assertIn("lastSpectral", state2)

    def test_no_translation_is_backward_compatible(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            state2, report, _i, _e = engine.process_result(
                state, sample_result(destroyedObjectiveIds=[], resultKey="verdance_ashes|va_001|1|victory"),
                None, root)  # no translation arg
            self.assertIsNone(report["spectral"])
            self.assertTrue(report["processed"])


class KethaReactiveTests(unittest.TestCase):
    def _briefing(self, state):
        voice = engine.load_ketha_voice(ROOT)
        objective = engine.objective_for_map("greenest_fields", state)
        return engine.generate_briefing(state, voice, "greenest_fields", "economy", objective, {})

    def test_scarred_commander_earns_a_briefing_line(self):
        state = sample_state()
        engine.ensure_roster(state)
        state["roster"]["commander"]["scars"] = [{"kind": "wounded", "untilMission": 99}]
        tags = [l["tag"] for l in self._briefing(state)["lines"]]
        self.assertIn("warband", tags)

    def test_world_ascendancy_line_switches_on_q0(self):
        state = sample_state()
        state["graph"]["q0_armada_cortex"] = 0.8
        voice = engine.load_ketha_voice(ROOT)
        cortex_line = [l for l in self._briefing(state)["lines"] if l["tag"] == "world"]
        self.assertTrue(cortex_line)
        self.assertIn(cortex_line[0]["text"], voice["pools"]["briefing.world.cortex_ascendant"])
        state["graph"]["q0_armada_cortex"] = 0.2
        armada_line = [l for l in self._briefing(state)["lines"] if l["tag"] == "world"]
        self.assertIn(armada_line[0]["text"], voice["pools"]["briefing.world.armada_ascendant"])

    def test_territory_lost_debrief_names_the_zone(self):
        state = sample_state()
        state["frontEvents"] = [{"type": "zone_lost", "zoneId": "GF_NW_GREEN_START",
                                 "label": "Northwest Green Start", "toFaction": "armada"}]
        result = sample_result(status="victory", destroyedObjectiveIds=[])
        bead = {"storyTags": ["victory", "territory-lost"]}
        events = engine.generate_story_events(state, result, bead, True, ROOT)
        texts = [e["text"] for e in events["events"] if e["kind"] == "dialogue"]
        self.assertTrue(any("Northwest Green Start" in t for t in texts))
        # The {zone} token must be fully interpolated (no literal placeholder left).
        self.assertFalse(any("{zone}" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
