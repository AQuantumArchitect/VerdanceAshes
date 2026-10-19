"""Read-only UI preview with in-memory campaign fixtures. Never launches BAR.

python tools/preview_command_console.py --port 8774 --fixture established
"""
import argparse
import copy
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import narrative_v1 as narrative

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ('fresh', 'established', 'partial', 'wounded', 'threatened', 'incomplete', 'late')


def make_fixture(name):
    state = json.loads((ROOT/'state/campaign_state.json').read_text(encoding='utf-8-sig'))
    hub = json.loads((ROOT/'app/showoff/hub_state.json').read_text(encoding='utf-8-sig'))
    state.pop('narrative', None)
    state['history'] = []
    state['homeCamp']['level'] = 0 if name == 'fresh' else 1
    state['company'].update(sealed=name != 'fresh', band=['vane', 'hearth', 'brakhov'])
    hub['company'].update(sealed=name != 'fresh', band=['vane', 'hearth', 'brakhov'])
    if name != 'fresh':
        owned={h.get('id') if isinstance(h,dict) else h for h in hub['company'].get('core',[])+hub['company']['band']}
        for ace in hub.get('aces',[]):
            if ace['id'] in owned: ace['status']='active'
        for hid in owned:
            if hid in state.get('characters',{}): state['characters'][hid]['status']='active'
    hub['flags']['companySealed'] = name != 'fresh'
    hub['homeCamp'].update(level=state['homeCamp']['level'])
    if name != 'fresh':
        narrative.choose(state, 'bring_back:extract', narrative.revision(state), 'fixture-commit')
        verdict = 'partial' if name in ('partial','wounded') else 'victory'
        if name == 'wounded':
            state['characters']['ketha']['wounds'] = 1
        for i in range(3 if name == 'late' else 1):
            state['history'].append({'mapId':'greenest_fields'})
            narrative.accept_result(state, {'resultKey':f'fixture-{i}', 'mapId':'greenest_fields',
                'deployAces':['vane','ketha','hearth','brakhov'], 'observedZoneIds':['GF_NE_PLATEAU'],
                'tenebriumBank':4,'tenebriumSpent':1,'tenebriumLost':0},
                {'advanceMission':True,'verdict':verdict,'credits':{'cleanExtract':verdict=='victory'}})
    if name == 'threatened':
        state.setdefault('zoneMemory',{}).setdefault('greenest_fields',{})['GF_NE_PLATEAU']={'controllingFaction':'ashwalkers'}
        narrative.choose(state,'shelter:claim',narrative.revision(state),'fixture-hold')
    if name == 'incomplete':
        hub['lastResult']={'verdict':'incomplete','headline':'Result pending','reasonHint':'The battle result has not reached the campaign.'}
    if name == 'late':
        state['missionNumber']=hub['missionNumber']=12
    hub['narrative']=narrative.project(state,hub['node']['choices'])
    return state,hub


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8774)
    parser.add_argument('--fixture',choices=FIXTURES,default='fresh')
    args=parser.parse_args()
    state,hub=make_fixture(args.fixture)
    active_fixture=args.fixture
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT/'app/showoff'),**kw)
        def log_message(self,*a): pass
        def send_data(self,data,code=200,ctype='application/json'):
            payload=(json.dumps(data) if ctype=='application/json' else data).encode()
            self.send_response(code);self.send_header('Content-Type',ctype);self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            nonlocal state, hub, active_fixture
            path=self.path.split('?')[0]
            fixture=parse_qs(urlparse(self.path).query).get('fixture',[None])[0]
            fixture=fixture or parse_qs(urlparse(self.headers.get('Referer','')).query).get('fixture',[None])[0]
            if fixture in FIXTURES and (path=='/' or fixture!=active_fixture):
                state,hub=make_fixture(fixture)
                active_fixture=fixture
            if path=='/hub_state.embed.js': return self.send_data('window.HUB_STATE = '+json.dumps(hub)+';',ctype='application/javascript')
            if path=='/api/status': return self.send_data({'schemaVersion':'verdance-hub-host/preview','capabilities':{'stamp':True}})
            if path=='/api/narrative': return self.send_data({'ok':True,'narrative':narrative.project(state,hub['node']['choices'])})
            if path=='/api/hub-state': return self.send_data({'ok':True,'hub':hub})
            if path.startswith('/api/'): return self.send_data({'present':False,'preview':True})
            super().do_GET()
        def do_POST(self):
            # UI interactions in this server cannot mutate the real campaign.
            if self.path=='/api/narrative-choice':
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                receipt=narrative.choose(state,body.get('choiceId'),body.get('expectedRevision'),body.get('requestId'))
                receipt['narrative']=narrative.project(state,hub['node']['choices'])
                return self.send_data(receipt,200 if receipt['ok'] else 409)
            return self.send_data({'ok':False,'error':'Read-only preview: this action is disabled.'},409)
    print(f'Preview: http://127.0.0.1:{args.port}/ ({args.fixture}; no campaign writes)',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__': main()
