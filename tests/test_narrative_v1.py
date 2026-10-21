import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verdance.readings import narrative as narrative


# A workspace with the story data but no belief frame in outbox/: the company has looked at
# nothing yet, so "do we hold ground" falls back to its own claim ledger (claimedNodes).
WS = Path(tempfile.mkdtemp(prefix="va_narrative_"))
(WS / "data").mkdir()
import shutil as _shutil
_shutil.copytree(ROOT / "data" / "story", WS / "data" / "story")


def fresh():
    return {"campaignId": "fixture", "missionNumber": 1, "graph": {}, "history": [],
            "company": {"sealed": True, "core": ["ketha"], "band": ["vane", "hearth", "brakhov"]},
            "characters": {i: {"player": True, "status": "active", "wounds": 0} for i in ("ketha", "vane", "hearth", "brakhov")},
            "homeCamp": {"level": 0}, "commerce": {"tenebrium": 3}, "reputation": {"nullmercs": 48, "cortex": 70}}


def result(state, key="r1", verdict="victory", workspace=None, **extra):
    r = {"resultKey": key, "mapId": "greenest_fields", **extra}
    c = {"verdict": verdict, "advanceMission": verdict in ("victory", "partial", "defeat"),
         "credits": {"cleanExtract": verdict == "victory", "nodeClaimed": verdict == "victory"}}
    return narrative.accept_result(state, r, c, workspace=workspace)


class NarrativeTests(unittest.TestCase):
    def test_reactive_scene_needs_a_matching_observed_return(self):
        s = fresh()
        result(s, deployAces=['vane', 'ketha'])
        target = 'ketha__vane:unfinished_return'
        self.assertNotIn(target, [x['id'] for x in narrative.project(s)['scenes']])
        result(s, key='partial-return', verdict='partial', deployAces=['vane', 'ketha'])
        scene = next(x for x in narrative.project(s)['scenes'] if x['id'] == target)
        self.assertEqual(scene['sourceEventId'], 'partial-return')

    def test_continuation_memory_requires_explicit_chapter_evidence(self):
        scene = {'pair':['vane','ketha'], 'when':{'continued':True}}
        event = {'id':'return', 'participants':['vane','ketha'], 'verdict':'victory'}
        self.assertIsNone(narrative.scene_evidence(scene, [event]))
        event['chapterIndex'] = 2
        self.assertEqual(narrative.scene_evidence(scene, [event]), 'return')

    def test_conversation_response_remembers_without_time_or_cost(self):
        s=fresh(); result(s,deployAces=['vane','ketha'])
        c=next(c for scene in narrative.project(s)['scenes'] for c in scene['choices'])
        before=copy.deepcopy(s); rev=narrative.revision(s)
        receipt=narrative.choose(s,c['id'],rev,'scene-request')
        self.assertTrue(receipt['ok'])
        self.assertEqual(narrative.choose(s,c['id'],rev,'scene-request'),receipt)
        self.assertEqual(s['narrative']['turn'],before['narrative']['turn'])
        self.assertEqual(s['commerce'],before['commerce'])
        self.assertEqual(len(s['narrative']['leadership']),1)
        self.assertTrue(narrative.project(s)['reactions'])
        self.assertFalse(narrative.choose(s,c['id'],narrative.revision(s),'different-request')['ok'])

    def test_projection_is_pure_and_deterministic(self):
        s = fresh(); before = copy.deepcopy(s)
        self.assertEqual(narrative.project(s), narrative.project(s))
        self.assertEqual(s, before)

    def test_commitment_is_idempotent_and_no_resource_cost(self):
        s = fresh(); commerce = copy.deepcopy(s["commerce"]); rep = copy.deepcopy(s["reputation"])
        token = narrative.revision(s)
        a = narrative.choose(s, "bring_back:extract", token, "request")
        b = narrative.choose(s, "bring_back:extract", token, "request")
        self.assertEqual(a, b); self.assertTrue(a["ok"])
        self.assertEqual(s["commerce"], commerce); self.assertEqual(s["reputation"], rep)
        self.assertEqual(s["narrative"]["turn"], 0)

    def test_stale_choice_does_not_mutate(self):
        s = fresh(); token = narrative.revision(s); s["commerce"]["tenebrium"] = 2; before = copy.deepcopy(s)
        self.assertTrue(narrative.choose(s, "place:raid", token, "request")["stale"])
        self.assertEqual(before, s)

    def test_invalid_and_reused_request(self):
        s = fresh(); before = copy.deepcopy(s)
        self.assertFalse(narrative.choose(s, "unknown", narrative.revision(s), "request")["ok"])
        self.assertEqual(s, before)
        narrative.choose(s, "place:raid", narrative.revision(s), "request")
        self.assertFalse(narrative.choose(s, "place:home", narrative.revision(s), "request")["ok"])

    def test_deadline_only_advances_on_accepted_results(self):
        s = fresh(); narrative.choose(s, "bring_back:extract", narrative.revision(s), "request")
        for verdict in ("abandon", "incomplete"):
            self.assertIsNone(result(s, verdict, verdict))
        self.assertEqual(s["narrative"]["turn"], 0)
        for i in range(3):
            result(s, str(i), "defeat")
            self.assertIsNone(result(s, str(i), "defeat"))
        t = s["narrative"]["threads"]["bring_back"]
        self.assertEqual(s["narrative"]["turn"], 3); self.assertEqual(t["stage"], "Changed")
        self.assertEqual(next(t for t in narrative.project(s)["threads"] if t["id"] == "bring_back")["remaining"], 0)

    def test_clean_return_resolves_with_evidence(self):
        s=fresh(); narrative.choose(s,"bring_back:extract",narrative.revision(s),"request")
        e=result(s)
        self.assertEqual(s["narrative"]["threads"]["bring_back"]["stage"],"Resolved")
        self.assertEqual(e["consequences"][0]["sourceEventId"],"r1")

    def test_no_invented_intelligence_or_participants(self):
        s=fresh(); s["zoneMemory"]={"greenest_fields":{"secret":{"controllingFaction":"armada"}}}
        e=result(s)
        self.assertEqual(e["participants"],[])
        self.assertEqual(s["narrative"]["intelligence"],{})
        result(s,"r2",observedZoneIds=["seen"])
        self.assertEqual(set(s["narrative"]["intelligence"]),{"greenest_fields:seen"})

    def test_scene_requires_shared_observation_and_available_characters(self):
        s=fresh(); result(s,deployAces=["vane","ketha"])
        scenes=narrative.project(s)["scenes"]
        self.assertIn("vane__ketha:return_1", [x["id"] for x in scenes])
        self.assertTrue(all(set(x["pair"]) == {"vane", "ketha"} for x in scenes))
        s["characters"]["ketha"]["wounds"]=1
        self.assertEqual(narrative.project(s)["scenes"],[])

    def test_lost_foothold_changes_opportunity(self):
        # belief, not truth: the company's own claim ledger says it holds the pad ...
        s=fresh(); s["claimedNodes"]={"greenest_fields":{"pad":{}}}
        narrative.choose(s,"shelter:claim",narrative.revision(s),"request",workspace=WS)
        # ... and losing that claim is what changes the opportunity.
        s["claimedNodes"]={}
        t=next(t for t in narrative.project(s,workspace=WS)["threads"] if t["id"]=="shelter")
        self.assertEqual(t["stage"],"Changed"); self.assertTrue(t["choices"])

    def test_quantum_authority_does_not_change_world_twice(self):
        for authoritative in (False,True):
            s=fresh(); graph=copy.deepcopy(s["graph"]); commerce=copy.deepcopy(s["commerce"])
            result(s,quantum_authoritative=authoritative)
            self.assertEqual(s["graph"],graph); self.assertEqual(s["commerce"],commerce)

    def test_disabled_feature_preserves_state(self):
        s=fresh(); s["features"]={"narrative":False}; before=copy.deepcopy(s)
        self.assertIsNone(result(s)); self.assertFalse(narrative.project(s)["enabled"])
        self.assertEqual(s,before)

    def test_roundtrip_and_unknown_fields(self):
        s=fresh(); s["custom"]={"future":42}; result(s)
        self.assertEqual(narrative.project(s),narrative.project(json.loads(json.dumps(s))))
        self.assertEqual(s["custom"],{"future":42})

    def test_backup_on_first_migration_write(self):
        from verdance.campaign import save_json
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"campaign_state.json"; s=fresh(); save_json(p,s); old=p.read_bytes()
            result(s); save_json(p,s)
            backups=list((p.parent/"backups/pre_narrative").glob('*.json'))
            self.assertEqual(len(backups),1); self.assertEqual(backups[0].read_bytes(),old)

    def test_authored_content_complete_and_pairs_exist(self):
        data=narrative.catalog(); self.assertEqual(len(data["threads"]),6);self.assertGreaterEqual(len(data["scenes"]),26)
        web=json.loads((ROOT/'data/story/support_web.json').read_text())
        pairs={frozenset((e['a'],e['b'])) for e in web['edges']}
        # Narrative-only core conversations do not create combat bond edges.
        pairs.add(frozenset(('pavise','ketha')))
        for scene in data['scenes']: self.assertIn(frozenset(scene['pair']),pairs)
        for t in data['threads']:
            for key in ('opening','escalation','success','failure','changed','callback'):
                self.assertTrue(t[key])
            self.assertGreaterEqual(len(t['perspectives']),2)

    def test_only_eligible_missions_linked(self):
        choices=[{'id':'raid','kind':'deploy','effect':{'mapId':'greenest_fields'}},
                 {'id':'locked','kind':'deploy','disabled':True,'effect':{'mapId':'greenest_fields'}}]
        for t in narrative.project(fresh(), choices)['threads']:
            self.assertNotIn('locked',t['operations'])

    def test_kernel_commands_and_save_slot_preserve_narrative(self):
        from verdance_kernel.api import CampaignKernel
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'state').mkdir()
            path=root/'state/campaign_state.json';path.write_text(json.dumps(fresh()))
            kernel=CampaignKernel(root)
            before=path.read_bytes(); view=kernel.narrative_surface()['narrative']
            self.assertEqual(path.read_bytes(),before)
            body={'choiceId':'bring_back:extract','expectedRevision':view['revision'],'requestId':'api-test'}
            self.assertTrue(kernel.narrative_choice(body)['ok'])
            saved=path.read_bytes()
            self.assertTrue(kernel.narrative_choice(body)['ok'])
            self.assertEqual(saved,path.read_bytes())
            self.assertTrue(kernel.save_campaign(slot='narrative-test')['ok'])
            self.assertEqual(json.loads((root/'state/saves/narrative-test/campaign_state.json').read_text())['narrative'],json.loads(saved)['narrative'])

    def test_full_engine_result_integration_and_duplicate(self):
        import shutil
        from verdance import campaign as engine
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);shutil.copytree(ROOT/'data',root/'data')
            state=engine.default_v1_state()
            raw={'campaignId':state['campaignId'],'missionId':'va_001','missionNumber':1,
                 'status':'victory','mapId':'greenest_fields','deploymentZoneId':'GF_NE_PLATEAU',
                 'extractionZoneId':'GF_NE_PLATEAU','extractionStatus':'clean','elapsedMinutes':4,
                 'destroyedObjectiveIds':['fixture-target'],'resultKey':'integrated-result',
                 'deployAces':['ketha','pavise'],'observedZoneIds':['GF_NE_PLATEAU']}
            updated,report,intent,events=engine.process_result(state,raw,None,root)
            self.assertEqual(updated['narrative']['turn'],1)
            self.assertEqual(report['narrativeEvent']['id'],report['resultKey'])
            self.assertIn('operationSummary',intent)
            self.assertIn('greenest_fields:GF_NE_PLATEAU',updated['narrative']['intelligence'])
            before=copy.deepcopy(updated['narrative'])
            repeated,report,_,_=engine.process_result(updated,raw,None,root)
            self.assertFalse(report['processed'])
            self.assertEqual(before,repeated['narrative'])

    def test_home_commitment_resolves_after_build_and_return(self):
        state=fresh();narrative.choose(state,'place:home',narrative.revision(state),'home-promise')
        state['homeCamp']['level']=1
        self.assertEqual(next(t for t in narrative.project(state)['threads'] if t['id']=='place')['stage'],'Committed')
        result(state)
        self.assertEqual(state['narrative']['threads']['place']['stage'],'Resolved')
        self.assertEqual(state['narrative']['threads']['place']['supportingEvents'],['r1'])

    def test_no_recovery_claim_without_hero_evidence(self):
        state=fresh();state['history']=[{'mapId':'greenest_fields'}]
        narrative.choose(state,'company:recover',narrative.revision(state),'recover')
        result(state)
        self.assertEqual(state['narrative']['threads']['company']['stage'],'Committed')
        result(state,'r2',heroResults={'ketha':{'status':'survived'}})
        self.assertEqual(state['narrative']['threads']['company']['stage'],'Resolved')

    def test_wounded_survivor_does_not_fulfill_recovery(self):
        state=fresh();state['history']=[{'mapId':'greenest_fields'}]
        narrative.choose(state,'company:recover',narrative.revision(state),'recover')
        result(state,heroResults={'ketha':{'alive':True,'status':'wounded','wounds':1}})
        self.assertEqual(state['narrative']['threads']['company']['stage'],'Committed')

    def test_callback_occurs_once_after_resolution(self):
        state=fresh()
        narrative.choose(state,'bring_back:extract',narrative.revision(state),'extract')
        result(state)
        second=result(state,'r2')
        third=result(state,'r3')
        self.assertTrue(any(c['origin']=='memory' for c in second['consequences']))
        self.assertFalse(any(c['origin']=='memory' for c in third['consequences']))

    def test_all_families_have_success_and_deadline_or_fallback_paths(self):
        for spec in narrative.catalog()['threads']:
            s=fresh();s['history']=[{'mapId':'eye_of_horus'}]
            s['claimedNodes']={'greenest_fields':{'pad':{}}}
            choice=spec['choices'][0]
            self.assertTrue(narrative.choose(s,spec['id']+':'+choice['id'],narrative.revision(s),'choose',workspace=WS)['ok'])
            result(s,mapId='eye_of_horus' if spec['id']=='dealer' else 'greenest_fields',heroResults={'ketha':{'status':'survived'}},workspace=WS)
            self.assertEqual(s['narrative']['threads'][spec['id']]['stage'],'Resolved',spec['id'])


if __name__=='__main__': unittest.main()
