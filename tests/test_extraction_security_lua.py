"""Execute production extraction functions with a small Spring boundary stub.

Optional runner: install lupa, then python -m unittest discover -s tests
-p test_extraction_security_lua.py. No BAR installation or campaign save required.
"""
from pathlib import Path
import unittest

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime = None

ROOT = Path(__file__).resolve().parents[1]
GADGET = ROOT / 'mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_campaign.lua'


@unittest.skipUnless(LuaRuntime, 'Lua 5.1 runtime (lupa) unavailable')
class ExtractionSecurityTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.source = GADGET.read_text(encoding='utf-8')
        self.lua.execute('''
          rules = {}; frameNow = 0; done = true; present = true; enemy = false
          secure = true; terminal = false; status = 'active'; playerTeamID = 0
          mission={extractionZoneId='Z',objective={requiredFrames=1}}
          extractionZoneRect = {0,0,100,100}; extractionHoldFrames = 0
          objectiveTargetCount = 1; objectiveTargetsDestroyed = 0
          CHECK_PERIOD = 30; EXTRACTION_HOLD_FRAMES = 90; BAIL_HOLD_FRAMES = 90
          AUTO_EVAC_FRAMES = 100; RAID_CREDIT_FRACTION = 1; headless = {}
          Spring = {SetGameRulesParam=function(k,v) rules[k]=v end,
            GetGameFrame=function() return frameNow end, Echo=function() end}
          objectiveKind=function() return 'seize_lane' end
          vaAllObjectivesDone=function() return done end
          vaSideWorkCredit=function() return false end
          scanZoneArmyValue=function() return 100 end
          teamArmyValue=function() return 100 end
          extractHoldRateFromAv=function() return 1,1 end
          setTerminal=function(s,r) terminal=true; outcome=s; reason=r end
          extractLoop={scan=function() return present,enemy end,
            security=function() return secure, secure and 'secured' or 'hostiles_in_zone' end}
          openExtractLoop=function() extractLoop.opened=true end
        ''')
        self.load_between('function extractLoop.publish()', 'function checkPlayerWipe(frame)')


    def load_between(self, start, end):
        a = self.source.index(start)
        self.lua.execute(self.source[a:self.source.index(end, a)])

    def run_hold(self, ticks=20):
        self.lua.execute(f'for i=1,{ticks} do frameNow=i*30; if not terminal then checkExtraction(frameNow) end end')

    def test_completion_waits_for_sidebar_confirmation(self):
        self.run_hold()
        self.assertFalse(self.lua.globals().terminal)

    def test_confirmed_secure_hold_succeeds(self):
        self.lua.execute('requestPlayerExfil()')
        self.run_hold()
        self.assertEqual(self.lua.globals().outcome, 'victory')

    def test_contested_zone_never_auto_evacuates(self):
        self.lua.execute('requestPlayerExfil(); secure=false; enemy=true')
        self.run_hold(100)
        self.assertFalse(self.lua.globals().terminal)
        self.assertEqual(self.lua.globals().extractionHoldFrames, 0)

    def test_clear_pad_without_zone_ownership_is_not_enough(self):
        self.lua.execute('requestPlayerExfil(); secure=false')
        self.run_hold()
        self.assertFalse(self.lua.globals().terminal)

    def test_interruption_requires_new_uncontested_hold(self):
        self.lua.execute('requestPlayerExfil(); checkExtraction(30); secure=false; checkExtraction(60)')
        self.assertEqual(self.lua.globals().extractionHoldFrames, 0)
        self.lua.execute('secure=true')
        self.run_hold()
        self.assertEqual(self.lua.globals().outcome, 'victory')

    def test_early_secure_extraction_stays_partial(self):
        self.lua.execute('done=false; requestPlayerExfil()')
        self.run_hold()
        self.assertEqual(self.lua.globals().outcome, 'partial')

    def test_repeated_confirmation_does_not_reset_hold(self):
        self.lua.execute('requestPlayerExfil(); checkExtraction(30); requestPlayerExfil()')
        self.assertEqual(self.lua.globals().extractionHoldFrames, 30)

    def test_blocked_confirmation_is_rejected_without_arming(self):
        self.lua.execute('secure=false')
        self.assertFalse(self.lua.eval('requestPlayerExfil()'))
        self.assertFalse(self.lua.globals().extractLoop.playerRequest)

    def test_cancel_stops_hold_without_result(self):
        self.lua.execute('requestPlayerExfil(); checkExtraction(30); cancelPlayerExfil()')
        self.run_hold()
        self.assertFalse(self.lua.globals().terminal)
        self.assertEqual(self.lua.globals().extractionHoldFrames, 0)

    def test_timeout_cannot_claim_extraction_even_after_rescue_failure(self):
        self.load_between('function checkSoftClock(frame)', 'function isCommanderUnitDef')
        self.lua.execute('done=false; rescueContractFailed=true; secure=false; checkSoftClock(300)')
        self.assertEqual(self.lua.globals().reason, 'soft_clock_rescue_failed')
        self.assertFalse(self.lua.globals().extractLoop.completed)

    def test_same_hold_duration_for_partial_and_complete(self):
        for complete in (True, False):
            self.setUp()
            self.lua.globals().done = complete
            self.lua.execute('requestPlayerExfil(); checkExtraction(30); checkExtraction(60)')
            self.assertFalse(self.lua.globals().terminal)
            self.lua.execute('checkExtraction(90)')
            self.assertTrue(self.lua.globals().terminal)

    def test_home_waits_for_matching_saved_receipt(self):
        ui = (ROOT / 'mod/VerdanceAshes.sdd/luaui/Widgets/gui_verdance_objectives.lua').read_text(encoding='utf-8')
        self.lua.execute("""
          widget={}; departureClock=0; savePollAt=0; resultReady=true
          state={terminal=true,terminalReason='extracted'}; reviewFieldAfterExtract=false
          returnAfterReport=false; quitDialogRequested=false; rules.va_exfil_requested=1
          rules.va_result_key='current-chapter'; savedBlob='["previous-chapter"]'; quits=0
          numParam=function(k,d) return rules[k] or d end
          collapseEnemyTeams=function() end
          Spring.GetGameRulesParam=function(k) return rules[k] end
          Spring.SendLuaRulesMsg=function(msg)
            if msg=='VA_CMD:varesultack:current-chapter' then rules.va_campaign_saved=1 end
          end
          Spring.SendCommands=function(cmd) if cmd=='quitforce' then quits=quits+1 end end
          io={open=function() return {read=function() return savedBlob end,close=function() end} end}
        """)
        a = ui.index('function widget:Update(dt)')
        b = ui.index('  -- The synced kernel', a)
        self.lua.execute(ui[a:b] + '\nend')
        self.lua.execute('widget:Update(1)')
        self.assertFalse(self.lua.globals().returnAfterReport)
        self.lua.execute("""savedBlob='["current-chapter"]'; widget:Update(1); widget:Update(1); widget:Update(1)""")
        self.assertEqual(self.lua.globals().quits, 1)

    def test_stay_does_not_close_after_save_and_timeout_does_not_auto_extract(self):
        # Reuse the actual update prefix and receipt boundary from the Home test.
        self.test_home_waits_for_matching_saved_receipt()
        self.lua.execute("quits=0; quitDialogRequested=false; returnAfterReport=false; reviewFieldAfterExtract=true; widget:Update(1); widget:Update(1)")
        self.assertEqual(self.lua.globals().quits, 0)
        self.lua.execute("reviewFieldAfterExtract=false; state.terminalReason='soft_clock_no_extract'; widget:Update(1); widget:Update(1)")
        self.assertEqual(self.lua.globals().quits, 0)

    def test_both_full_files_compile_on_engine_lua_version(self):
        self.lua.execute('assert(loadstring(...))', self.source)
        ui = ROOT / 'mod/VerdanceAshes.sdd/luaui/Widgets/gui_verdance_objectives.lua'
        self.lua.execute('assert(loadstring(...))', ui.read_text(encoding='utf-8'))

    def test_security_uses_live_friendly_control_and_all_hostile_units(self):
        self.lua.execute('''
          mission={extractionZoneId='Z'}; gaiaTeamID=99
          teamFaction={[0]='ashwalkers',[1]='armada',[2]='nullmercs'}
          zoneRectFor=function() return {0,0,100,100} end
          units={}; owner='armada'
          Spring.GetAllUnits=function() return units end
          Spring.GetUnitPosition=function() return 5,0,5 end
          zoneForPosition=function() return {zoneId=unitZone or 'Z'} end
          Spring.GetUnitTeam=function() return 1 end
          Spring.ValidUnitID=function() return true end
          Spring.GetUnitIsDead=function() return false end
          Spring.AreTeamsAllied=function(a,b) return b==0 or b==2 end
          VAQ={zoneSamples=function() return {{zoneId='Z',control=owner}} end}
        ''')
        self.load_between('function extractLoop.security(zoneId)', 'function extractLoop.publish()')
        self.assertFalse(self.lua.eval('extractLoop.security()')[0])
        self.lua.execute("owner='nullmercs'")
        self.assertTrue(self.lua.eval('extractLoop.security()')[0])
        self.lua.execute('units={5}')
        self.assertEqual(self.lua.eval('extractLoop.security()')[:2], (False, 'hostiles_in_zone'))
        self.lua.execute("unitZone='NEIGHBOUR'")
        self.assertTrue(self.lua.eval('extractLoop.security()')[0])

    def test_pressure_producers_share_one_authored_pack_per_chapter(self):
        self.lua.execute('''
          VAQ={}; sortieChapter=1; teamFaction={[1]='armada'}
          mission={objective={targetZoneId='Z'}}; created={}
          Spring.GetGroundHeight=function() return 0 end
          Spring.CreateUnit=function(name) created[#created+1]=name; return #created end
          Spring.GiveOrderToUnit=function() end
        ''')
        a = self.source.index('function VAQ.responseDefs(')
        b = self.source.index('function VAQ.teamForFaction', a)
        self.lua.execute(self.source[a:b].replace('local function spawnWave', 'function spawnWave'))
        self.lua.execute('''
          VAQ.entryFor=function() return 3000,3000 end
          VAQ.hiddenFromPlayer=function() return true end
          VAQ.playerDistanceOk=function() return true end
          spawnWave(1,5,0,0,'regrow'); spawnWave(1,5,0,0,'hot_extraction')
        ''')
        created = list(self.lua.globals().created.values())
        self.assertEqual(len(created), 11)
        self.assertEqual(created.count('armdecom'), 1)
        self.assertEqual(created.count('armflea'), 4)
        self.assertEqual(created.count('armpw'), 4)
        self.assertEqual(created.count('corthud'), 2)


if __name__ == '__main__':
    unittest.main()
