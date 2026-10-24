import copy
import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance import campaign as engine


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
            {"zoneId":"GF_NW_MUSTER","label":"Northwest Muster","role":"start","tags":["start","northwest","low"],"campEligible":true,"deployEligible":true,"extractEligible":true,"bounds":{"xMin":0.0,"xMax":0.25,"zMin":0.0,"zMax":0.25}},
            {"zoneId":"GF_SW_MUSTER","label":"Southwest Muster","role":"start","tags":["start","southwest","low"],"campEligible":true,"deployEligible":true,"extractEligible":true,"bounds":{"xMin":0.0,"xMax":0.25,"zMin":0.75,"zMax":1.0}},
            {"zoneId":"GF_NE_PLATEAU","label":"Northeast Plateau / North Desert","role":"plateau","tags":["high","start","northeast"],"campEligible":true,"deployEligible":true,"extractEligible":true,"bounds":{"xMin":0.55,"xMax":1.0,"zMin":0.0,"zMax":0.5}},
            {"zoneId":"GF_NW_GREEN_START","label":"Northwest Green Start","role":"legion_start","tags":["start"]},
            {"zoneId":"GF_SE_SYNTH_START","label":"Southeast Synth Start","role":"defender_start","tags":["start","economy"]},
            {"zoneId":"GF_NORTH_DESERT_EDGE","label":"North Desert Edge","role":"energy_edge","tags":["north","wind"]},
            {"zoneId":"GF_SOUTH_DESERT_EDGE","label":"South Desert Edge","role":"energy_edge","tags":["south","wind"]},
            {"zoneId":"GF_N_PLATEAU","label":"North Plateau","role":"plateau","tags":["north","high"],"campEligible":true,"deployEligible":true,"extractEligible":true,"bounds":{"xMin":0.3,"xMax":0.7,"zMin":0.0,"zMax":0.22}},
            {"zoneId":"GF_C_GATE","label":"Central Gate","role":"gate","campEligible":true,"deployEligible":false,"extractEligible":false,"bounds":{"xMin":0.4,"xMax":0.6,"zMin":0.4,"zMax":0.5}},
            {"zoneId":"GF_C_INNER_GATE","label":"Central Inner Gate","role":"gate","campEligible":true,"deployEligible":false,"extractEligible":false,"bounds":{"xMin":0.4,"xMax":0.6,"zMin":0.5,"zMax":0.6}},
            {"zoneId":"GF_SE_PLATEAU","label":"Southeast Plateau","role":"plateau","tags":["southeast","start"],"campEligible":true,"deployEligible":true,"extractEligible":true,"bounds":{"xMin":0.55,"xMax":1.0,"zMin":0.55,"zMax":1.0}}
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
    def test_hub_stamp_beats_opening_on_fresh_campaign(self):
        """Theater-board Drop must not be stomped by the authored opening."""
        with make_workspace() as tmp:
            root = Path(tmp)
            outbox = root / "outbox"
            outbox.mkdir(parents=True, exist_ok=True)
            hub = {
                "schemaVersion": "verdance-sortie-order/1.0",
                "mapId": "greenest_fields",
                "targetZoneId": "GF_N_PLATEAU",
                "deploymentZoneId": "GF_NW_MUSTER",
                "extractionZoneId": "GF_NW_MUSTER",
                "fromZoneIds": ["GF_NW_MUSTER"],
                "captureZoneIds": ["GF_N_PLATEAU"],
                "patron": "nullmercs",
                "against": "armada",
                "objectiveArchetype": "seize_lane",
                "hubChoiceId": "c_theater",
                "source": "hub_deploy_plan",
                "derived": {"source": "hub_deploy_plan"},
            }
            (outbox / "next_sortie_choice.json").write_text(
                json.dumps(hub), encoding="utf-8"
            )
            (outbox / "next_sortie_order.json").write_text(
                json.dumps(hub), encoding="utf-8"
            )

            intent = engine.materialize_next_intent(sample_state(), root)

            self.assertEqual(intent["mapId"], "greenest_fields")
            self.assertEqual(intent["targetZoneId"], "GF_N_PLATEAU")
            self.assertEqual(intent["deploymentZoneId"], "GF_NW_MUSTER")
            self.assertFalse(bool(intent.get("openingMission")))
            order = json.loads(
                (outbox / "next_sortie_order.json").read_text(encoding="utf-8")
            )
            self.assertEqual(order["targetZoneId"], "GF_N_PLATEAU")
            self.assertEqual(order["source"], "hub_deploy_plan")

    def test_opening_hub_choice_is_a_projection_of_the_story_order(self):
        state = engine.default_v1_state()
        order = engine.opening_sortie_order(state)
        choice = engine.opening_hub_choice(state)
        self.assertIsNotNone(choice)
        self.assertEqual(choice["effect"]["deploymentZoneId"], order["deploymentZoneId"])
        self.assertEqual(choice["effect"]["targetZoneId"], order["targetZoneId"])
        self.assertEqual(choice["effect"]["extractionZoneId"], order["extractionZoneId"])
        self.assertEqual(choice["effect"]["openingForce"], order["openingForce"])

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
            # v0.8.4 multi-rate clock: ancient_bastion is a FAR theater (0.25x),
            # so 60 wall minutes are ~15 effective minutes of defender growth.
            self.assertEqual(wall_after["offscreenEstimate"]["timeBand"], "far")
            self.assertGreater(wall_after["abstract"]["fortification"], start_fort + 0.10)
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
    def test_next_map_override_is_honored_then_cleared(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            state["nextMapOverride"] = {"mapId": "the_rock_jungle", "deploymentZoneId": "RJ_NW_JUNGLE_SHELF"}
            # Pass root: choose_next_map_zone now translates retired zone ids
            # forward, and without a workspace it would resolve against the real
            # repo's authored maps (where RJ_NW_JUNGLE_SHELF has migrated to
            # TRJ_NW_MUSTER) rather than this fixture's, which still defines it.
            self.assertEqual(engine.choose_next_map_zone(state, root),
                             ("the_rock_jungle", "RJ_NW_JUNGLE_SHELF"))
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
            for _ in range(6):
                # Active map is elsewhere, so ancient_bastion keeps eroding —
                # at the FAR-band rate (0.25x, v0.8.4 multi-rate clock), which
                # needs ~5 twenty-minute beats before the zone actually falls.
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
            self.assertEqual(len(war["regions"]), len(engine.WORLD_MAPS))
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


class CommerceTests(unittest.TestCase):
    def test_fresh_bag_has_starter_metal_and_tnb(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = engine.default_v1_state()
            commerce = engine.ensure_commerce(state, root)
            self.assertEqual(commerce["tenebrium"], 3)
            self.assertEqual(commerce.get("metalK"), 7)
            self.assertNotIn("credits", commerce)
            # Buy-everything: fresh bag is wallets only — no free Punch.
            self.assertNotIn("punch_of_thugs", commerce.get("owned") or {})
            intent = engine.build_commerce_intent(state, root)
            punch = next(
                (d for d in intent.get("deploy") or [] if d.get("listingId") == "punch_of_thugs"),
                None,
            )
            self.assertIsNone(punch)
            bought = engine.purchase_listing(state, "punch_of_thugs", root)
            self.assertTrue(bought.get("ok"), bought)
            intent2 = engine.build_commerce_intent(state, root)
            punch2 = next(
                (d for d in intent2.get("deploy") or [] if d.get("listingId") == "punch_of_thugs"),
                None,
            )
            self.assertIsNotNone(punch2)
            self.assertEqual(int(punch2.get("count") or 0), 7)

    def test_intent_exposes_metal_bag(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            state.setdefault("commerce", {})["metalK"] = 3
            engine.ensure_zone_memory(state, root)
            intent = engine.materialize_next_intent(state, root)
            self.assertIn("commerce", intent)
            self.assertEqual(intent["commerce"]["tenebrium"], intent["commerce"].get("tenebrium", 0))
            self.assertIn("metalK", intent["commerce"])
            self.assertGreaterEqual(int(intent["commerce"]["metalK"]), 0)


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


class CraftedWorldTests(unittest.TestCase):
    """Get-back-on-track: the generator reads the crafted seven_maps world."""

    def test_parse_campaign_forces_grammar(self):
        self.assertEqual(engine.parse_campaign_forces("So6 Wi4 D2"),
                         {"mex": 0, "solar": 6, "wind": 4, "defense": 2})
        self.assertEqual(engine.parse_campaign_forces("M9 So4 Wi3 D8"),
                         {"mex": 9, "solar": 4, "wind": 3, "defense": 8})
        self.assertEqual(engine.parse_campaign_forces(""),
                         {"mex": 0, "solar": 0, "wind": 0, "defense": 0})
        self.assertEqual(engine.parse_campaign_forces(None)["solar"], 0)

    def test_greenest_fields_objective_is_armada_eco_raid(self):
        obj = engine.objective_for_map("greenest_fields", {})
        self.assertEqual(obj["kind"], "eco_raid")
        self.assertEqual(obj["enemyFaction"], "armada")
        # The target zone id must NOT trip the compiler's Cortex name heuristic.
        self.assertNotIn("SYNTH", obj["targetZoneId"].upper())

    def test_zone_infrastructure_reads_crafted_pool(self):
        # Uses the real data/map_pool/seven_maps.json via the repo root.
        infra = engine.zone_infrastructure_for("greenest_fields", ROOT)
        self.assertEqual(infra["primaryFaction"], "armada")
        self.assertEqual(infra["parsed"]["armada"], {"mex": 0, "solar": 6, "wind": 4, "defense": 2})
        self.assertEqual(infra["parsed"]["nullmercs"]["wind"], 2)
        # Greenest Fields is authored with NO Cortex presence.
        self.assertFalse(any(infra["parsed"]["cortex"].values()))
        # Eye of Horus is the Cortex accent map.
        eoh = engine.zone_infrastructure_for("eye_of_horus", ROOT)
        self.assertEqual(eoh["primaryFaction"], "cortex")



class HeroRosterTests(unittest.TestCase):
    """Mission-feel pass: the named Fire-Emblem hero roster."""

    def test_default_state_seeds_critical_heroes(self):
        # WO-008: missionCritical is UI emphasis only (no longer auto-abort).
        state = sample_state()
        roster = engine.ensure_roster(state)
        ids = {h["heroId"] for h in roster["heroes"]}
        self.assertIn("vane", ids)
        self.assertIn("ketha", ids)
        for hero in roster["heroes"]:
            self.assertIn("missionCritical", hero)
            self.assertNotEqual(hero["unitDef"], "legcom")
            self.assertIn("campaignXp", hero)
            self.assertGreaterEqual(hero["xp"], 0.0)

    def test_intent_deploys_active_heroes_and_skips_dead(self):
        state = sample_state()
        roster = engine.ensure_roster(state)
        roster["heroes"].append({
            "heroId": "brakka", "name": "Brakka", "unitDef": "leggat",
            "missionCritical": False, "status": "dead", "xp": 1.0, "timesWounded": 2,
        })
        intent = engine.build_roster_intent(state)
        ids = [h["heroId"] for h in intent["heroes"]]
        self.assertIn("vane", ids)
        self.assertNotIn("brakka", ids)

    def test_wounded_hero_deploys_thinner(self):
        state = sample_state()
        roster = engine.ensure_roster(state)
        for hero in roster["heroes"]:
            if hero["heroId"] == "ketha":
                hero["status"] = "wounded"
        intent = engine.build_roster_intent(state)
        ketha = next(h for h in intent["heroes"] if h["heroId"] == "ketha")
        vane = next(h for h in intent["heroes"] if h["heroId"] == "vane")
        self.assertTrue(ketha["wounded"])
        self.assertLess(ketha["hpMult"], vane["hpMult"])

    def test_cracked_farm_mode_levels_heroes_fast(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            state["progression"] = {
                "mode": "cracked_farm",
                "difficultyDial": 1.0,
                "xpMultiplier": 1.0,
                "farmSortiesEnabled": True,
                "xpPersistOnDeath": True,
            }
            roster = engine.ensure_roster(state)
            for h in roster["heroes"]:
                h["campaignXp"] = 0.0
                h["xp"] = 0.1
                h["peakBarXp"] = 0.1
            # Several clean victories should put heroes well up the ladder.
            for n in range(1, 9):
                mid = f"va_{n:03d}"
                result = sample_result(
                    missionNumber=n,
                    missionId=mid,
                    resultKey=f"verdance_ashes|{mid}|{n}|victory",
                    heroResults={
                        "vane": {"status": "survived", "wasDown": False, "xp": 0.2 + n * 0.05},
                        "ketha": {"status": "survived", "wasDown": False, "xp": 0.1 + n * 0.04},
                    },
                )
                state, report, intent, _ = engine.process_result(state, result, None, root)
                self.assertTrue(report["processed"])
            heroes = {h["heroId"]: h for h in state["roster"]["heroes"]}
            self.assertGreaterEqual(heroes["vane"]["level"], 5)
            self.assertGreaterEqual(heroes["vane"]["campaignXp"], 400)
            # Intent deploys thicker cracked heroes.
            vane = next(h for h in intent["roster"]["heroes"] if h["heroId"] == "vane")
            self.assertGreaterEqual(vane["level"], 5)
            self.assertGreaterEqual(vane["hpMult"], 1.5)
            self.assertIn(intent["roster"]["progression"]["mode"], ("cracked_farm", "standard"))
            self.assertTrue(intent["roster"]["progression"]["xpPersistOnDeath"])

    def test_cadre_xp_banks_majority_between_rounds(self):
        """Packs / escorts keep ~85% of field XP across drops via cadreXp."""
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_roster(state)
            result = sample_result(
                playerSurvivors={"legcen": 4, "legrezbot": 2},
                playerSurvivorXp={
                    "legcen": {
                        "count": 4, "peakXp": 1.0, "avgXp": 0.8,
                        "peakCraftXp": 0.0, "avgCraftXp": 0.0,
                    },
                    "legrezbot": {
                        "count": 2, "peakXp": 0.4, "avgXp": 0.35,
                        "peakCraftXp": 0.6, "avgCraftXp": 0.5,
                    },
                },
            )
            state, report, intent, _ = engine.process_result(state, result, None, root)
            self.assertTrue(report["processed"])
            bank = state["roster"]["cadreXp"]
            self.assertIn("legcen", bank)
            # Majority retain: seed xp should be well above half of avg.
            self.assertGreaterEqual(bank["legcen"]["xp"], 0.8 * 0.85 * 0.9)
            self.assertGreaterEqual(bank["legcen"]["peakXp"], 1.0)
            self.assertGreaterEqual(bank["legrezbot"]["craftXp"], 0.5 * 0.85 * 0.9)
            # Intent carries cadreXp for the next mission bake.
            intent_bank = (intent.get("roster") or {}).get("cadreXp") or {}
            self.assertIn("legcen", intent_bank)
            self.assertGreater(float(intent_bank["legcen"]["xp"]), 0.0)

    def test_wounds_heal_between_missions(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            roster = engine.ensure_roster(state)
            for hero in roster["heroes"]:
                if hero["heroId"] == "ketha":
                    hero["status"] = "wounded"
            result = sample_result(heroResults={
                "ketha": {"status": "survived", "wasDown": False, "xp": 0.2},
            })
            state, report, _, _ = engine.process_result(state, result, None, root)
            heroes = {h["heroId"]: h for h in state["roster"]["heroes"]}
            self.assertEqual(heroes["ketha"]["status"], "active")

    def test_hero_lost_result_advances_campaign(self):
        """WO-008: hero loss is now a wreck decision, not a hard abort.
        The sortie processes as a defeat, the mission advances, and
        the story events carry a hero-lost tag for the wreck narrative."""
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            before = copy.deepcopy(engine.migrate_state(state))
            result = sample_result(status="defeat", terminalReason="hero_lost_ketha",
                                   destroyedObjectiveIds=[], extractionStatus="")
            state, report, intent, events = engine.process_result(state, result, None, root)
            # Campaign DOES advance — no more hard restart.
            self.assertTrue(report["processed"])
            # Mission number incremented.
            self.assertGreater(state["missionNumber"], before["missionNumber"])
            # History now has an extra bead.
            self.assertGreater(len(state["history"]), len(before["history"]))


class BeatsAndExtractionTests(unittest.TestCase):
    """Mission-feel pass: seed-authored beats and distinct extraction zones."""

    def test_intent_carries_beats_with_core_triggers(self):
        state = {"campaignId": "verdance_ashes", "missionNumber": 1,
                 "reputation": {"nullmercs": 43}, "graph": {}, "zoneMemory": {}}
        engine.ensure_roster(state)
        intent = engine.materialize_next_intent(state, ROOT)
        beats = intent["beats"]
        self.assertGreaterEqual(len(beats), 4)
        triggers = {b["trigger"]["type"] for b in beats}
        self.assertIn("time", triggers)
        self.assertIn("objective_complete", triggers)
        self.assertIn("hero_down", triggers)
        for beat in beats:
            for action in beat["actions"]:
                if action["type"] == "bark":
                    self.assertTrue(action["text"])
                    self.assertEqual(action["speaker"], "Ketha")

    def test_beats_are_deterministic_per_campaign_moment(self):
        state = {"campaignId": "verdance_ashes", "missionNumber": 3,
                 "reputation": {"nullmercs": 43}, "graph": {}, "zoneMemory": {}}
        engine.ensure_roster(state)
        a = engine.materialize_next_intent(copy.deepcopy(state), ROOT)["beats"]
        b = engine.materialize_next_intent(copy.deepcopy(state), ROOT)["beats"]
        self.assertEqual(a, b)


class ActStructureTests(unittest.TestCase):
    """Drop 2: acts — ground control, constrained RTS, path-keyed finales."""

    @staticmethod
    def _state(mission_number, path="B", graph=None):
        state = {"campaignId": "verdance_ashes", "missionNumber": mission_number,
                 "pathSignal": path, "reputation": {"nullmercs": 43},
                 "graph": dict(graph or {}), "zoneMemory": {}}
        engine.ensure_roster(state)
        return state

    def test_act_boundaries(self):
        self.assertEqual(engine.act_for_mission(1), 1)
        self.assertEqual(engine.act_for_mission(5), 1)
        self.assertEqual(engine.act_for_mission(6), 2)
        self.assertEqual(engine.act_for_mission(10), 2)
        self.assertEqual(engine.act_for_mission(11), 3)
        self.assertEqual(engine.act_for_mission(19), 3)

    def test_act1_intent_carries_ground_control_policy(self):
        intent = engine.materialize_next_intent(self._state(2), None)
        self.assertEqual(intent["act"]["act"], 1)
        self.assertNotIn("techPolicy", intent)  # no fabrication gate: Tnb and build power only
        self.assertIsNone(intent["finale"])
        self.assertIn("ground_control", intent["storyTags"])

    def test_act2_intent_constrained_rts(self):
        intent = engine.materialize_next_intent(self._state(7), None)
        self.assertEqual(intent["act"]["act"], 2)
        self.assertIsNone(intent["finale"])

    def test_finale_path_leader_beats_stale_letter(self):
        state = self._state(12, path="B",
                            graph={"pathSignalA": 0.8, "pathSignalB": 0.2, "pathSignalC": 0.0})
        self.assertEqual(engine.finale_path_for_state(state), "A")

    def test_finale_current_path_wins_ties(self):
        state = self._state(12, path="C",
                            graph={"pathSignalA": 0.5, "pathSignalB": 0.5, "pathSignalC": 0.5})
        self.assertEqual(engine.finale_path_for_state(state), "C")

    def test_finale_intent_deterministic(self):
        state = self._state(11, path="B", graph={"pathSignalB": 0.7})
        first = engine.materialize_next_intent(copy.deepcopy(state), None)
        second = engine.materialize_next_intent(copy.deepcopy(state), None)
        self.assertEqual(first["mapId"], second["mapId"])
        self.assertEqual(first["objectiveTarget"], second["objectiveTarget"])
        self.assertEqual(first["finale"], second["finale"])


class HeroRosterArcTests(unittest.TestCase):
    """Drop 3 Wave 2: authored hero roster, recruitment beats, act-2 grants."""

    @staticmethod
    def _state(mission_number, rep=None):
        state = {"campaignId": "verdance_ashes", "missionNumber": mission_number,
                 "pathSignal": "B", "reputation": dict(rep or {"nullmercs": 43}),
                 "graph": {}, "zoneMemory": {}}
        engine.ensure_roster(state)
        return state

    def test_mission_victory_recruits(self):
        state = self._state(3)
        joined = engine.apply_recruitment_beats(state, {"missionNumber": 2}, True, 2)
        ids = {j["heroId"] for j in joined}
        self.assertIn("rusk", ids)
        self.assertNotIn("verse", ids)  # verse needs mission 3 won
        by_id = {h["heroId"]: h for h in state["roster"]["heroes"]}
        self.assertEqual(by_id["rusk"]["status"], "active")
        self.assertEqual(by_id["rusk"]["joinedAtMission"], 2)
        self.assertEqual(state["characters"]["rusk"]["player"], True)
        self.assertEqual(state["recentHeroJoins"]["missionNumber"], 3)

    def test_no_victory_no_mission_recruit(self):
        state = self._state(3)
        engine.apply_recruitment_beats(state, {"missionNumber": 2}, False, 2)
        by_id = {h["heroId"]: h for h in state["roster"]["heroes"]}
        self.assertEqual(by_id["rusk"]["status"], "locked")

    def test_rep_recruit_fires_without_victory(self):
        state = self._state(4, rep={"nullmercs": 70, "ashwalkers": 5})
        joined = engine.apply_recruitment_beats(state, {"missionNumber": 4}, False, 4)
        ids = {j["heroId"] for j in joined}
        self.assertIn("grath", ids)
        by_id = {h["heroId"]: h for h in state["roster"]["heroes"]}
        self.assertEqual(by_id["grath"]["status"], "active")
        self.assertTrue(state["characters"]["grath"]["player"])

    def test_act2_reward_grants_into_reserve(self):
        state = self._state(7)
        rec = engine.apply_act_rewards(state, 6, True)
        self.assertIsNotNone(rec)
        roster = state["roster"]
        self.assertGreaterEqual(roster["reserve"].get("legshot", 0), 2)
        self.assertEqual(len(roster["grants"]), 1)
        # Duplicate grant for the same mission is refused.
        self.assertIsNone(engine.apply_act_rewards(state, 6, True))
        # Act-1 missions and non-victories mint nothing.
        self.assertIsNone(engine.apply_act_rewards(state, 3, True))
        self.assertIsNone(engine.apply_act_rewards(state, 7, False))


class Drop3TextureTests(unittest.TestCase):
    """Drop 3 Wave 3: objective matrix, finale voice, campaign completion."""

    def test_act1_rotation_prefers_slot_kind(self):
        from verdance.company import quest_generator as qg
        lane = {"zoneId": "Z1", "role": "lane", "tags": []}
        eco = {"zoneId": "Z2", "role": "energy_edge", "tags": []}
        state2 = {"missionNumber": 2, "graph": {}, "reputation": {}, "zoneMemory": {}}
        self.assertGreater(
            qg.score_candidate(state2, "m", "Z1", lane, "armada"),
            qg.score_candidate(state2, "m", "Z2", eco, "armada"))
        state1 = {"missionNumber": 1, "graph": {}, "reputation": {}, "zoneMemory": {}}
        self.assertGreater(
            qg.score_candidate(state1, "m", "Z2", eco, "armada"),
            qg.score_candidate(state1, "m", "Z1", lane, "armada"))

    def test_finale_briefing_speaks_path_voice(self):
        state = {"campaignId": "verdance_ashes", "missionNumber": 12,
                 "pathSignal": "A", "reputation": {"nullmercs": 43},
                 "graph": {"pathSignalA": 0.9}, "zoneMemory": {}}
        engine.ensure_roster(state)
        voice = engine.load_ketha_voice(ROOT)
        briefing = engine.generate_briefing(
            state, voice, "ancient_bastion", "siege",
            {"kind": "destroy_key_structure"}, {})
        tags = [line["tag"] for line in briefing["lines"]]
        self.assertIn("finale", tags)

    def test_campaign_complete_marks_epilogue_intent(self):
        state = {"campaignId": "verdance_ashes", "missionNumber": 12,
                 "pathSignal": "B", "reputation": {"nullmercs": 43},
                 "graph": {"pathSignalB": 0.7}, "zoneMemory": {},
                 "campaignComplete": {"missionNumber": 11, "finaleKind": "sovereignty"}}
        engine.ensure_roster(state)
        intent = engine.materialize_next_intent(state, None)
        self.assertIn("epilogue", intent["storyTags"])
        self.assertTrue(intent["campaignComplete"])


class Drop4EscalationTests(unittest.TestCase):
    """Escalation ladder, secondary objectives, strong objectives, and the
    stale-sortie fix (Drop 4)."""

    def test_ladder_windows_climb_and_strengths(self):
        from verdance.world import escalation_ladder as ladder
        mids = []
        for n in range(1, 11):
            plan = ladder.plan_for_mission(n, False)
            lo, hi = plan["scaleWindow"]
            self.assertLess(lo, hi)
            mids.append((lo + hi) / 2.0)
        self.assertEqual(mids, sorted(mids))
        self.assertEqual(ladder.plan_for_mission(4, False)["secondaries"], [{"required": False}])
        self.assertEqual(ladder.plan_for_mission(6, False)["secondaries"], [{"required": True}])
        self.assertEqual(ladder.plan_for_mission(9, False)["objectiveStrength"], "raze")
        self.assertEqual(ladder.plan_for_mission(10, False)["objectiveStrength"], "purge")
        finale = ladder.plan_for_mission(11, True)
        self.assertEqual(finale["objectiveStrength"], "finale")
        self.assertGreaterEqual(finale["scaleWindow"][0], 1.6)
        self.assertEqual(finale["secondaries"], [])

    def test_clamp_scale_windows_and_dial(self):
        from verdance.world import escalation_ladder as ladder
        self.assertEqual(ladder.clamp_scale(2.145, [0.85, 1.12]), 1.12)
        self.assertEqual(ladder.clamp_scale(0.3, [0.35, 0.5]), 0.35)
        self.assertEqual(ladder.clamp_scale(0.9, [0.85, 1.12]), 0.9)
        # The owner's dial scales the window walls themselves.
        self.assertEqual(ladder.clamp_scale(2.145, [0.85, 1.12], dial=1.25), 1.4)
        self.assertEqual(ladder.clamp_scale(1.0, None), 1.0)

    def test_escalation_plan_stamps_secondaries_from_real_board(self):
        import escalation_map_v1 as emap
        with emap.make_sandbox(ROOT) as tmp:
            ws = Path(tmp)
            state = engine.default_v1_state()
            state["missionNumber"] = 6
            state["currentMissionId"] = engine.mission_id(6)
            intent = engine.materialize_next_intent(state, ws)
            plan = intent.get("escalationPlan") or {}
            secs = plan.get("secondaries") or []
            self.assertEqual(len(secs), 1)
            self.assertTrue(secs[0]["required"])
            self.assertTrue(secs[0]["zoneId"])
            self.assertNotEqual(secs[0]["zoneId"], intent.get("targetZoneId"))
            state["missionNumber"] = 10
            state["currentMissionId"] = engine.mission_id(10)
            i10 = engine.materialize_next_intent(state, ws)
            self.assertEqual(i10["escalationPlan"]["objectiveStrength"], "purge")
            self.assertEqual(i10["escalationPlan"]["secondaries"], [])

    def test_stale_mode_a_sortie_is_consumed(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            outbox = root / "outbox"
            outbox.mkdir(exist_ok=True)
            order = {"mapId": "ancient_bastion", "targetZoneId": "AB_EASTERN_BASTION_WALL",
                     "objectiveArchetype": "seize_lane", "patron": "nullmercs",
                     "source": "quest_generator_v1"}
            (outbox / "next_sortie_order.json").write_text(
                __import__("json").dumps(order), encoding="utf-8")
            report = engine.consume_played_hub_sorties(
                root, {"mapId": "ancient_bastion"}, "ancient_bastion")
            self.assertIn("next_sortie_order.json", report["cleared"])
            self.assertFalse((outbox / "next_sortie_order.json").exists())

    def test_materialize_discards_order_for_patron_held_zone(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            zm = state["zoneMemory"]["ancient_bastion"]["AB_EASTERN_BASTION_WALL"]
            zm["controllingFaction"] = "nullmercs"
            outbox = root / "outbox"
            outbox.mkdir(exist_ok=True)
            (outbox / "next_sortie_order.json").write_text(
                __import__("json").dumps({
                    "mapId": "ancient_bastion", "targetZoneId": "AB_EASTERN_BASTION_WALL",
                    "objectiveArchetype": "seize_lane", "patron": "nullmercs"}),
                encoding="utf-8")
            intent = engine.materialize_next_intent(state, root)
            self.assertNotEqual(
                (intent.get("objectiveTarget") or {}).get("targetZoneId"),
                "AB_EASTERN_BASTION_WALL")

    def test_anti_repeat_penalizes_last_kind(self):
        from verdance.company import quest_generator as qg
        node = {"role": "lane", "tags": []}
        base_state = {"missionNumber": 7, "graph": {}, "reputation": {}, "zoneMemory": {}}
        fresh = qg.score_candidate(base_state, "greenest_fields", "GF_X", node, "armada")
        repeated = qg.score_candidate(
            {**base_state, "history": [{"objectiveKind": "seize_lane"}]},
            "greenest_fields", "GF_X", node, "armada")
        self.assertAlmostEqual(fresh - repeated, qg.ANTI_REPEAT_PENALTY, places=6)

    def test_zone_vocabulary_maps_to_varied_archetypes(self):
        from verdance.company import quest_generator as qg
        self.assertEqual(qg.archetype_for_node({"role": "causeway"}), "gate_control")
        self.assertEqual(qg.archetype_for_node({"role": "island_chain"}), "hold_plateau")
        self.assertEqual(qg.archetype_for_node({"role": "raptor_wilds"}), "survive_wilds")
        self.assertEqual(qg.archetype_for_node({"role": "fortress"}), "siege")
        self.assertEqual(qg.archetype_for_node({"role": "", "tags": ["raptors"]}), "survive_wilds")

    def test_briefing_gets_escalation_lines(self):
        state = {"campaignId": "verdance_ashes", "missionNumber": 9,
                 "pathSignal": "B", "reputation": {"nullmercs": 43},
                 "graph": {}, "zoneMemory": {}}
        engine.ensure_roster(state)
        voice = engine.load_ketha_voice(ROOT)
        plan = {"objectiveStrength": "raze",
                "secondaries": [{"id": "s", "zoneId": "Z", "required": True}]}
        briefing = engine.generate_briefing(
            state, voice, "greenest_fields", "economy", {"kind": "strike_relay"}, {}, plan)
        tags = [line["tag"] for line in briefing["lines"]]
        self.assertEqual(tags.count("escalation"), 2)
        texts = [line["text"] for line in briefing["lines"]]
        raze_pool = voice.get("pools", {}).get("briefing.raze") or []
        self.assertTrue(any(t in raze_pool for t in texts))

    def test_card_preview_respects_ladder_window(self):
        state = sample_state()
        state["missionNumber"] = 6
        # Inflate zone presence so the raw preview would exceed the m6 window.
        state["zoneMemory"] = {}
        pres = engine._difficulty_presentation(state, "ancient_bastion")
        from verdance.world import escalation_ladder as ladder
        lo, hi = ladder.plan_for_mission(6, False)["scaleWindow"]
        self.assertGreaterEqual(pres["enemyScalePreview"], lo)
        self.assertLessEqual(pres["enemyScalePreview"], hi)


class LivingWorldTests(unittest.TestCase):
    """The mechanics landed from tools/campaign_flow_matrix_v1.py's already-
    validated scouting pass: seasons, temperaments, tides, wind, the raptor
    bloom, and the player's regression arc. Each test pins the mechanism,
    not the tuning -- the knobs remain guesses by design."""

    def test_the_storm_turns_with_the_season(self):
        self.assertAlmostEqual(engine.hydrology_storm_phase(1), 0.0, places=9)
        self.assertAlmostEqual(engine.hydrology_storm_phase(4), 0.9505, places=3)
        self.assertAlmostEqual(engine.hydrology_storm_phase(8), 0.0, places=3)
        for n in range(1, 30):
            self.assertTrue(0.0 <= engine.hydrology_storm_phase(n) <= 1.0)

    def test_koom_valley_never_rises_past_its_cap(self):
        state = sample_state()
        cap = engine.HYDRO_LEVEL_CAP["koom_valley"]
        for n in range(1, 60):
            state["missionNumber"] = n
            level = engine.map_waterline(state, "koom_valley", None)["level"]
            self.assertLessEqual(level, cap + 1e-9)

    def test_a_dry_map_never_swings(self):
        """Greenest Fields' amplitude is 0 -- it cannot swing, and needs no
        special case to read that way."""
        state = sample_state()
        for n in range(1, 20):
            state["missionNumber"] = n
            swing = engine.hydrology_swing(state, None)
            self.assertEqual(swing["greenest_fields"], 0.0)
            self.assertTrue(0.0 <= swing["koom_valley"] <= 1.0)

    def test_temperaments_pull_opposite_ways(self):
        """The owner's judgment call, at the mechanism level: a still map
        wakes the mercs, a swinging map wakes the armada. Swing is forced by
        hand-crafting the hydro record with planetWater already present --
        ensure_planet_hydrology only reseeds levelDelta/peakSwing on a truly
        fresh (no planetWater) record, and only ever overwrites
        amplitude/fill/level/basins otherwise, so a pre-set value survives."""
        state = sample_state()
        state["hydrology"] = {"planetWater": 1.0, "maps": {
            "tabula": {"levelDelta": 0.95, "peakSwing": 1.0},
            "eye_of_horus": {"levelDelta": 0.01, "peakSwing": 1.0},
        }}
        activity = engine.hydrology_activity(state, None)
        self.assertGreater(activity["tabula"]["armada"], activity["tabula"]["nullmercs"])
        self.assertGreater(activity["eye_of_horus"]["nullmercs"], activity["eye_of_horus"]["armada"])

    def test_cortex_never_reads_swing_only_wind(self):
        state = sample_state()
        state["hydrology"] = {"planetWater": 1.0, "maps": {
            "tabula": {"levelDelta": 0.95, "peakSwing": 1.0},
        }}
        activity = engine.hydrology_activity(state, None)
        self.assertAlmostEqual(activity["tabula"]["cortex"], engine.TEMPERAMENT["cortex"]["base"])

    def test_the_wind_is_real_and_paces_the_windier_map_faster(self):
        ranges = engine.hydrology_wind_range(ROOT)
        self.assertIn("tabula", ranges)
        self.assertLess(ranges["all_that_simmers"]["max"], ranges["tabula"]["max"])
        state = sample_state()
        for n in range(1, 10):
            state["missionNumber"] = n
            pace = engine.hydrology_wind_pace(state, ROOT)
            lo, hi = engine.WIND["floor"], engine.WIND["floor"] + engine.WIND["gain"]
            for value in pace.values():
                self.assertTrue(lo - 1e-9 <= value <= hi + 1e-9)
            self.assertGreaterEqual(pace["tabula"], pace["all_that_simmers"])

    def test_wind_pace_is_empty_without_a_map_pool(self):
        state = sample_state()
        self.assertEqual(engine.hydrology_wind_pace(state, None), {})

    def test_tick_zone_scales_armada_and_cortex_independently(self):
        armada = {"zoneId": "z1", "abstract": {"control": "armada"}}
        engine.tick_zone(armada, "SimpleAI", "tabula", 12.0, {},
                         activity={"armada": 2.0, "nullmercs": 0.3, "cortex": 1.0})
        cortex = {"zoneId": "z2", "abstract": {"control": "cortex"}}
        engine.tick_zone(cortex, "SimpleAI", "tabula", 12.0, {},
                         activity={"armada": 2.0, "nullmercs": 0.3, "cortex": 1.0})
        baseline_armada = {"zoneId": "z3", "abstract": {"control": "armada"}}
        engine.tick_zone(baseline_armada, "SimpleAI", "tabula", 12.0, {})
        self.assertGreater(armada["abstract"]["baseStrength"],
                           baseline_armada["abstract"]["baseStrength"])
        self.assertAlmostEqual(cortex["abstract"]["baseStrength"],
                               baseline_armada["abstract"]["baseStrength"])

    def test_tick_zone_is_backward_compatible_without_activity(self):
        zone = {"zoneId": "z1", "abstract": {"control": "armada"}}
        engine.tick_zone(zone, "SimpleAI", "tabula", 12.0, {})
        self.assertGreater(zone["abstract"]["baseStrength"], 0.0)

    def test_bloom_fires_after_recession_and_decays_in_still_water(self):
        state = sample_state()
        state["hydrology"] = {"planetWater": 1.0, "maps": {"the_rock_jungle": {
            "levelDeltaPrevious": -0.9, "levelDelta": 0.0}}}
        first = engine.update_hydrology_bloom(state, "the_rock_jungle", None)
        self.assertGreater(first, 0.0)
        state["hydrology"]["maps"]["the_rock_jungle"] = {
            "levelDeltaPrevious": 0.0, "levelDelta": 0.0}
        series = [first]
        for _ in range(6):
            series.append(engine.update_hydrology_bloom(state, "the_rock_jungle", None))
        for a, b in zip(series, series[1:]):
            self.assertLess(b, a)

    def test_the_bloom_only_lives_on_wild_maps(self):
        state = sample_state()
        state["hydrology"] = {"maps": {"ancient_bastion": {
            "levelDeltaPrevious": -0.9, "levelDelta": 0.0}}}
        self.assertEqual(engine.update_hydrology_bloom(state, "ancient_bastion", None), 0.0)

    def test_tide_feeds_the_bloom_same_mission(self):
        state = sample_state()
        state["hydrology"] = {"planetWater": 1.0, "maps": {"the_rock_jungle": {
            "levelDeltaPrevious": 0.0, "levelDelta": 0.6}}}
        bloom = engine.update_hydrology_bloom(state, "the_rock_jungle", None)
        self.assertGreater(bloom, 0.0)

    def test_hydrology_beats_rising_spreads_pulses_falling_is_one_beat(self):
        rising = engine.hydrology_beats(
            {"amplitude": 0.8, "level": 0.2, "nextLevel": 0.6}, lambda *_a: None)
        self.assertEqual(len(rising), engine.TIDE["pulses"])
        for beat in rising:
            self.assertTrue(600 <= beat["trigger"]["seconds"] <= 1140)
        falling = engine.hydrology_beats(
            {"amplitude": 0.8, "level": 0.6, "nextLevel": 0.2}, lambda *_a: None)
        self.assertEqual(len(falling), 1)
        negligible = engine.hydrology_beats(
            {"amplitude": 0.8, "level": 0.5, "nextLevel": 0.51}, lambda *_a: None)
        self.assertEqual(negligible, [])
        dry_map = engine.hydrology_beats(
            {"amplitude": 0.0, "level": 0.2, "nextLevel": 0.9}, lambda *_a: None)
        self.assertEqual(dry_map, [])

    def test_player_regression_is_inert_outside_the_window(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            for n in (1, 3, 7, 11):
                state["missionNumber"] = n
                flips = engine.apply_player_regression(state, "greenest_fields", [], 20.0, root)
                self.assertEqual(flips, [])

    def test_player_regression_only_touches_other_maps_ashwalker_ground(self):
        with make_workspace() as tmp:
            root = Path(tmp)
            state = sample_state()
            engine.ensure_zone_memory(state, root)
            state["missionNumber"] = 5
            state["hydrology"] = {"planetWater": 1.0, "maps": {
                "ancient_bastion": {"levelDelta": 0.95, "peakSwing": 1.0},
            }}
            flips = []
            for _ in range(6):
                flips += engine.apply_player_regression(state, "greenest_fields", [], 20.0, root)
            self.assertTrue(any(f["mapId"] == "ancient_bastion" for f in flips))
            self.assertTrue(any(f["toFaction"] == "armada" for f in flips))
            # The active map's own ashwalker ground (greenest_fields'
            # GF_NW_GREEN_START) must never regress -- it is the map being
            # played, not "another map."
            gf_start = state["zoneMemory"]["greenest_fields"]["GF_NW_GREEN_START"]
            self.assertEqual(gf_start["controllingFaction"], "ashwalkers")

    def test_scouting_the_living_world_never_writes_campaign_state(self):
        path = ROOT / "state" / "campaign_state.json"
        before = path.read_bytes()
        state = sample_state()
        engine.hydrology_activity(state, ROOT)
        engine.hydrology_wind_pace(state, ROOT)
        engine.update_hydrology_bloom(state, "the_rock_jungle", ROOT)
        self.assertEqual(path.read_bytes(), before)


class AuthoredZoneIdsAreLiveTests(unittest.TestCase):
    """Authored zone-id constants must resolve against the REAL zone maps.

    These run against ROOT, not a fixture, on purpose. The bug they exist to
    catch is a zone re-cut retiring an id that a hardcoded constant still names:
    ALPHA_SPINE and objective_for_map between them named twelve zones that no
    longer existed, and nothing failed, because every test that touched them
    used a synthetic workspace where the old ids were still valid.

    A fixture cannot catch this. Only the shipping data can.
    """

    def test_every_door_is_a_live_zone(self):
        from verdance.world.roads import load_doors
        valid = engine.valid_zone_ids(ROOT)
        self.assertTrue(valid, "no authored zone ids loaded; the check would be vacuous")
        doors = load_doors(ROOT)
        self.assertEqual({d["mapId"] for d in doors.values()}, set(engine.WORLD_MAPS))
        for zone_id, door in doors.items():
            self.assertIn(zone_id, valid, f"door {zone_id} on {door['mapId']} is not a live zone")

    def test_choose_next_map_zone_is_live_for_every_mission(self):
        valid = engine.valid_zone_ids(ROOT)
        for mission in range(1, 13):
            map_id, zone_id = engine.choose_next_map_zone({"missionNumber": mission}, ROOT)
            self.assertIn(zone_id, valid,
                          f"mission {mission} deploys to {zone_id} on {map_id}, "
                          "which is not a live zone")

    def test_objective_fallback_targets_all_exist(self):
        valid = engine.valid_zone_ids(ROOT)
        for map_id in engine.WORLD_MAPS:
            objective = engine.objective_for_map(map_id, {}, ROOT)
            target = objective.get("targetZoneId")
            if target is None:
                continue  # the generic sortie fallback names no zone
            self.assertIn(target, valid,
                          f"objective_for_map({map_id}) targets {target}, "
                          "which is not a live zone")


if __name__ == "__main__":
    unittest.main()
