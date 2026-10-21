import './campaign.js';

import {session, readNarrative, commitChoice} from './state.js';

import {escape, pretty, field, operation, thread, chronicle, reactions, scene, fieldLine} from './render.js';

import {installOverlays, updateIntelligence, zoneInspector} from './map.js';



const adapter=window.Verdance;

const $=id=>document.getElementById(id);

if(adapter) {

  document.body.classList.add('command-console');

  const main=$('main');

  const operations=document.createElement('section'); operations.id='workspace-operations'; operations.className='cc-workspace';

  while(main.firstChild) operations.append(main.firstChild);

  main.append(operations);

  const pending=document.createElement('section');pending.id='cc-pending';pending.className='cc-error';pending.setAttribute('role','status');pending.hidden=true;

  pending.innerHTML='<h2>Result pending</h2><p>Bring the previous battle result home before deploying again. No narrative deadline advances while synchronization is incomplete.</p><button id="cc-recover-result" type="button">Recover battle result</button>';

  operations.prepend(pending);

  pending.querySelector('button').onclick=()=>$('btn-pull-result').click();

  document.addEventListener('click',e=>{if(e.target.closest('#btn-deploy,#drop-confirm-go') && adapter.snapshot().hub.lastResult?.verdict==='incomplete'){e.preventDefault();e.stopImmediatePropagation();adapter.notify('Recover the pending battle result before deploying again.');}},true);

  const company=$('col-aces'); company.classList.remove('col'); company.classList.add('cc-workspace'); company.hidden=true;

  main.append(company);

  const deployment=document.createElement('details');deployment.id='cc-deployment';deployment.hidden=true;deployment.innerHTML='<summary>Choose who deploys</summary>';company.insertBefore(deployment,$('aces'));deployment.append($('company-sub'),$('company-cap'),$('aces'),$('company-foot'));
  const rail=document.createElement('aside');rail.id='operations-rail';rail.className='col cc-rail';rail.setAttribute('aria-label','Company operations');

  $('app').insertBefore(rail,main);

  const home=document.createElement('section');home.id='workspace-home';home.className='cc-workspace';home.hidden=true;

  home.innerHTML='<p class="cc-eyebrow">The Rock Jungle</p><h1>Something worth returning to</h1><div id="cc-home-status"></div><section id="cc-camp-upgrades"><h2>Camp improvements</h2><p>Invest in the place the company comes back to.</p></section>';

  company.append($('panel-shop'));$('panel-shop').prepend($('btn-bro-tzar'));$('panel-shop').querySelector('h2').textContent='Reinforcements and equipment';home.prepend($('camp-chip'));document.body.append($('camp-sheet'));main.append(home);$('cc-camp-upgrades').append($('camp-sheet-stats'),$('btn-camp-raise'),$('btn-camp-founding'));company.append($('hearth-block'));$('btn-camp-close').hidden=true;

  const archive=document.createElement('section');archive.id='workspace-chronicle';archive.className='cc-workspace';archive.hidden=true;

  archive.innerHTML='<p class="cc-eyebrow">Actions become history</p><h1>Company chronicle</h1><div id="cc-chronicle"></div>';main.append(archive);

  const system=document.createElement('details');system.id='cc-system';

  system.innerHTML='<summary>System</summary><div class="cc-system-body"><h2>Campaign controls</h2><div id="cc-system-actions"></div>'+
    '<section id="cc-ready" aria-label="Ready to drop"><h2>Ready to drop</h2><ul id="cc-ready-list" class="cc-ready-list"><li class="cc-ready-row"><span class="cc-dot"></span><span>Checking…</span></li></ul><p id="cc-ready-progress" class="cc-ready-progress" hidden></p></section>'+
    '<section id="cc-feedback" aria-label="Feedback"><h2>Feedback</h2><p class="cc-feedback-note">Zips the campaign save, the kernel faces, the hub state and the newest BAR log for a bug report. Never the truth frame or another faction\'s mind.</p><textarea id="cc-feedback-notes" rows="2" placeholder="What happened? (optional)"></textarea><button type="button" id="cc-feedback-export">Export feedback bundle</button><p id="cc-feedback-result" class="cc-feedback-result" hidden></p></section>'+
    '<h3>Diagnostics</h3></div>';

  $('app').querySelector('.top').append(system);

  const sysbody=system.querySelector('.cc-system-body');

  sysbody.append($('panel-manifold'));$('panel-manifold').hidden=false;

  sysbody.append($('panel-theaters'));$('panel-theaters').hidden=false;

  $('col-right').innerHTML='<section id="cc-matters" aria-label="Company matters"></section><div id="cc-inspector" aria-label="Company matter details"></div>';const mapDetails=document.createElement('details');mapDetails.id='cc-map-details';operations.append(mapDetails);

  const nav=document.createElement('nav');nav.className='cc-nav';nav.setAttribute('aria-label','Campaign workspaces');

  nav.innerHTML=['operations','company','home','chronicle'].map(name=>`<button type="button" data-workspace="${name}" aria-pressed="${name==='operations'}">${pretty(name)}</button>`).join('');

  $('app').querySelector('.top').append(nav,system);

  for(const id of ['btn-save-campaign','btn-load-campaign','btn-reset-campaign','btn-sync-hub','btn-abandon']) $('cc-system-actions').append($(id));

  const controls=operations.querySelector('.theater-actions');$('app').querySelector('.foot').prepend(controls);

  $('choices').classList.add('cc-source-choices');$('choices-head').hidden=true;

  $('recommend-company').onclick=()=>adapter.recommendCompany();

  $('btn-camp-founding').addEventListener('click',()=>showWorkspace('operations'));

  $('btn-camp-broker').addEventListener('click',()=>showWorkspace('company'));

  $('camp-chip').hidden=true;

  installOverlays($('theater'));



  function showWorkspace(name) {

    session.workspace=name;

    for(const [key,element] of Object.entries({operations,company,home,chronicle:archive})) element.hidden=key!==name;

    nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.workspace===name)));

    controls.hidden=name!=='operations';

    renderInspector();

  }

  nav.onclick=e=>{const b=e.target.closest('[data-workspace]');if(b)showWorkspace(b.dataset.workspace);};



  function renderInspector() {

    const n=session.narrative;

    const snap=adapter.snapshot();

    const t=n?.threads?.find(t=>t.id===session.selectedThread);

    if($('cc-operation-details')) $('cc-operation-details').innerHTML=operation(n?.operations?.find(o=>o.id===snap.plan?.choiceId));

    $('cc-map-details').hidden=!session.selectedZone;

    if(session.selectedZone) $('cc-map-details').innerHTML='<summary>Selected map location</summary>'+zoneInspector(session.selectedZone,snap.focusMap,n);

    if(t && session.workspace==='operations') $('cc-inspector').innerHTML=thread(t,snap.live);

    else if(session.workspace==='home') $('cc-inspector').innerHTML=field('A practical home','Camp level and home clearance reflect the existing simulation. Improvements cost 1 Tenebrium and 1,000 campaign metal.')+field('Resources','Tenebrium supports construction capacity. Check each broker listing for its price and delivery conditions.');

    else if(session.workspace==='company' && session.selectedHero) {

      const ace=(snap.hub.aces || []).find(a=>a.id===session.selectedHero);

      const pack=window.CREW_PACKS?.heroes?.[session.selectedHero] || {};

      const related=(n?.threads || []).filter(t=>t.perspectives.some(p=>p.speaker===session.selectedHero));

      $('cc-inspector').innerHTML=ace?`<p class="cc-eyebrow">Company member</p><h2>${escape(ace.name || pretty(ace.id))}</h2>`+

        field('Role',pack.blurb || ace.role || 'Company specialist')+field('Condition',ace.status || 'Status unavailable')+

        reactions((n?.reactions || []).filter(r=>r.speaker===ace.id))+field('Experience',`${ace.xp ?? 'Not recorded'} campaign XP`)+

        field('Current commitments',related.filter(t=>t.stage==='Committed').map(t=>t.title).join(', ') || 'No current narrative commitment involving this member.')+

        `<details><summary>Pack and progression</summary><pre>${escape(JSON.stringify({unit:pack.unitDef,count:pack.packTotal,fieldEffect:pack.fieldEffect,wounds:ace.wounds,bonds:ace.bonds},null,2))}</pre></details>`:

        field('Member unavailable','This member is no longer in the current company.');

    }

    else if(session.workspace==='company') $('cc-inspector').innerHTML=field('Bring people with a purpose','Core members travel with the company. Your initial three packs establish its strengths; later recruits expand your options.')+field('Readiness','Inspect wounds and roles before deployment. Recovery, construction, and fighting power each serve a different need.')+field('Relationships','Company scenes unlock from recorded shared deployments. Reading them never spends resources or advances a deadline.');

    else $('cc-inspector').innerHTML=field('What kind of company are we?','Select a company matter above to hear the disagreement and choose your response. These promises shape your history; operations on the left determine where you deploy.');

  }



  function paint() {

    const n=session.narrative;const snap=adapter.snapshot();

    pending.hidden=snap.hub.lastResult?.verdict!=='incomplete';

    const choices=(snap.hub.node?.choices || []).filter(c=>c.kind==='deploy' && (c.effect?.mapId===snap.focusMap));

    const ranking=n?.operations || [];

    choices.sort((a,b)=>ranking.findIndex(o=>o.id===a.id)-ranking.findIndex(o=>o.id===b.id));

    const signature=JSON.stringify([n,snap.live,snap.focusMap,snap.plan?.choiceId,snap.hub.homeCamp,snap.hub.aces,snap.hub.lastResult,snap.hub.camp,session.allThreads,session.selectedThread,session.error]);

    updateIntelligence(n,snap.focusMap);

    if(signature===session.signature)return;

    session.signature=signature;

    const actionable=n?.threads?.filter(t=>['Available','Committed','Changed'].includes(t.stage)) || [];

    const shown=session.allThreads?actionable:actionable.filter(t=>n.recommended.includes(t.id));

    rail.innerHTML='<p class="cc-eyebrow">Company operations</p><h2>Where do we go next?</h2>'+fieldLine(adapter.fieldPeople ? adapter.fieldPeople() : [])+choices.slice(0,3).map(c=>`<button class="cc-operation" type="button" data-operation="${escape(c.id)}" ${c.disabled?'disabled':''} aria-pressed="${c.id===snap.plan?.choiceId}"><strong>${escape(c.label)}</strong><span>${escape(ranking.find(o=>o.id===c.id)?.recommendation || 'Plan the route and inspect the requirements.')}</span></button>`).join('')+

      (choices.length>3?`<details><summary>All ${choices.length} operations</summary>${choices.slice(3).map(c=>`<button type="button" data-operation="${escape(c.id)}" ${c.disabled?'disabled':''}>${escape(c.label)}</button>`).join('')}</details>`:'')+

      (!choices.length?'<p>No operation on this theater. Select another map or refresh after your return.</p>':'')+

      '<section id="cc-operation-details" aria-label="Selected operation"></section>';

    $('cc-matters').innerHTML='<p class="cc-eyebrow">Around the company table</p><h2>Company matters</h2><p class="cc-matters-intro">People, principles, and promises.</p>'+shown.map(t=>`<button class="cc-thread" type="button" data-thread="${escape(t.id)}" aria-pressed="${t.id===session.selectedThread}"><small>${escape(t.stage)}${t.remaining!==null?` · ${t.remaining} sorties left`:''}</small><strong>${escape(t.title)}</strong><span>${escape(t.reason)}</span></button>`).join('')+

      (actionable.length>3?`<button type="button" id="cc-more">${session.allThreads?'Show recommended':'Show all matters'}</button>`:'')+

      (session.error?`<p role="status" class="cc-error">${escape(session.error)}</p>`:'');

    $('cc-chronicle').innerHTML=chronicle(n?.chronicle || []);

    adapter.renderCamp();
    const camp=snap.hub.homeCamp || {};

    $('cc-home-status').innerHTML=field('Established',camp.cleared?'Home ground secured':`Camp level ${camp.level || 0}`)+

      field('Next milestone',camp.cleared?'Hold what the company has built.':camp.clearReady?'The home-clear operation is ready. Review its route and requirements.':'Raise the camp to prepare for clearing the surrounding wilds.')+

      field('Next improvement',camp.cleared?'Home clear achieved.':`1 Tenebrium + 1,000 campaign metal. ${camp.canRaise?'Available now.':'Gather the required resources before raising camp.'}`);

    let scenes=$('cc-company-scenes');if(!scenes){scenes=document.createElement('section');scenes.id='cc-company-scenes';company.insertBefore(scenes,$('panel-shop'));}

    let members=$('cc-company-members');if(!members){members=document.createElement('section');members.id='cc-company-members';company.insertBefore(members,deployment);}

    members.innerHTML='<h2>Know your company</h2><div class="cc-members">'+(snap.hub.aces || []).filter(a=>adapter.companyMemberIds().includes(a.id)).map(a=>{

      const p=window.CREW_PACKS?.heroes?.[a.id] || {};

      return `<button type="button" data-hero="${escape(a.id)}"><strong>${escape(a.name || pretty(a.id))}</strong><span>${escape(a.status || 'Condition unknown')}</span><p>${escape(p.blurb || a.role || 'Company specialist')}</p></button>`;

    }).join('')+'</div>';

    const openScenes=new Set([...scenes.querySelectorAll('details[open][data-scene]')].map(el=>el.dataset.scene));
    scenes.innerHTML='<h2>The promises we live by</h2>'+(n?.leadership?.length ? n.leadership.slice(-6).reverse().map(c=>`<blockquote><strong>${escape(c.stance)}</strong><p>${escape(c.words)}</p><small>Chosen after sortie ${escape(c.turn)}</small></blockquote>`).join('') : '<p>Your responses to company matters will be remembered here. A promise shows what you value; your returns show how you lived up to it.</p>')+'<h2>Between sorties</h2>'+(n?.scenes || []).map(s=>scene(s,snap.live)).join('')+'<h2>How they see your command</h2>'+reactions(n?.reactions);

    scenes.querySelectorAll('[data-scene]').forEach(el=>el.open=openScenes.has(el.dataset.scene));
    let returnCard=$('cc-return');if(!returnCard){returnCard=document.createElement('details');returnCard.id='cc-return';operations.insertBefore(returnCard,$('theater'));}

    const last=n?.chronicle?.[0];returnCard.hidden=!last;

    if(last)returnCard.innerHTML=`<summary>Last return · ${escape(last.title)} · ${escape(pretty(last.mapId))}</summary>${chronicle([last])}`;

    renderInspector();

  }



  $('board-zones').addEventListener('click',e=>{const z=e.target.closest('[data-zone]');if(z){session.selectedZone=z.dataset.zone;renderInspector();}});

  document.addEventListener('click',async e=>{

    const op=e.target.closest('[data-operation]');

    const matter=e.target.closest('[data-thread]');

    const commit=e.target.closest('[data-commit]');

    const hero=e.target.closest('[data-hero]');

    if(hero){session.selectedHero=hero.dataset.hero;session.selectedThread=null;session.selectedZone=null;showWorkspace('company');renderInspector();}

    if(op){session.selectedZone=null;showWorkspace('operations');adapter.selectOperation(op.dataset.operation);paint();renderInspector();}

    if(matter){showWorkspace('operations');session.selectedThread=matter.dataset.thread;session.selectedZone=null;const t=session.narrative.threads.find(t=>t.id===session.selectedThread);if(t?.maps.length && !t.maps.includes(adapter.snapshot().focusMap)){const legalMaps=(adapter.snapshot().hub.regions || []).filter(r=>r.selectable!==false).map(r=>r.mapId);const mid=t.maps.find(m=>legalMaps.includes(m));if(mid)adapter.focusMap(mid);}paint();renderInspector();}

    if(e.target.id==='cc-more'){session.allThreads=!session.allThreads;paint();}

    if(commit){commit.disabled=true;try{await commitChoice(adapter,commit.dataset.commit);session.error='';paint();}catch(err){session.error=err.message;paint();}finally{commit.disabled=false;}}

  });

  let polling=false;

  async function refresh() {

    if(polling)return;polling=true;

    try{if(adapter.snapshot().live){session.narrative=await readNarrative(adapter);session.error='';}else session.narrative=adapter.snapshot().hub.narrative || null;paint();}

    catch(err){session.error=err.message;paint();}finally{polling=false;}

  }

  showWorkspace('operations');refresh();setInterval(refresh,3000);

  // READY TO DROP: one honest checklist from /api/health, polled every 5 s while the drawer is open.
  const FIXES={
    python:'Install Python 3.10+ from python.org',
    numpy:'Run SETUP.bat again (numpy is missing)',
    scipy:'Run SETUP.bat again (scipy is missing)',
    umwelt:'Belief engine not found — the map will show no belief; see INSTALL.md',
    bar:'Install Beyond All Reason and launch it once',
    engine:'Launch Beyond All Reason once so it installs an engine',
    mod:'Press Drop once — the kernel installs the campaign into BAR',
    map:'The next map downloads on Drop (keep the window open)',
    kernel:'Start PLAY.bat and keep its window open',
  };
  function readyRows(h){
    if(!h) return [{ok:false,label:'Campaign kernel',fix:FIXES.kernel}];
    const rows=[
      {ok:!!h.pythonOk,label:'Python '+(h.python||'?'),fix:FIXES.python},
      {ok:!!h.numpy,label:'numpy',fix:FIXES.numpy},
      {ok:!!h.scipy,label:'scipy',fix:FIXES.scipy},
      {ok:!!h.umwelt,label:'Belief engine',fix:FIXES.umwelt},
      {ok:!!h.barDataRoot,label:'Beyond All Reason found',fix:FIXES.bar},
      {ok:!!h.engine,label:'BAR engine',fix:FIXES.engine},
      {ok:!!h.modInstalled,label:'Campaign installed in BAR',fix:FIXES.mod},
    ];
    if(h.nextMap) rows.push({ok:h.mapCached===true,label:'Map for the next drop · '+pretty(h.nextMap),fix:FIXES.map,soft:h.mapCached==null});
    rows.push({ok:h.stateMission!=null,label:h.stateMission!=null?('Campaign save · mission '+h.stateMission):'Campaign save',fix:'Press Reset to start a campaign'});
    return rows;
  }
  function paintReady(h){
    const list=$('cc-ready-list');if(!list)return;
    list.innerHTML=readyRows(h).map(r=>`<li class="cc-ready-row ${r.ok?'ok':(r.soft?'soft':'bad')}"><span class="cc-dot" aria-hidden="true"></span><span>${escape(r.label)}${r.ok?'':`<small>${escape(r.fix)}</small>`}</span></li>`).join('');
    const prog=$('cc-ready-progress');const p=h&&h.provision;
    if(prog){const dl=p&&p.state==='downloading';prog.hidden=!dl;if(dl){const pct=Math.max(0,Math.min(100,Number(p.percent)||0));const mb=x=>(Number(x||0)/1048576).toFixed(0);prog.textContent=`Downloading ${p.map||'map'} · ${pct}% (${mb(p.bytes)}/${mb(p.total)} MB)`;}}
  }
  let readyTimer=null;
  async function pollReady(){
    if(!system.open){return;}
    try{const r=await fetch(adapter.api('/api/health'),{cache:'no-store'});paintReady(r.ok?await r.json():null);}
    catch(_){paintReady(null);}
  }
  system.addEventListener('toggle',()=>{if(system.open){pollReady();readyTimer=setInterval(pollReady,5000);}else if(readyTimer){clearInterval(readyTimer);readyTimer=null;}});

  $('cc-feedback-export').onclick=async()=>{
    const btn=$('cc-feedback-export');const out=$('cc-feedback-result');btn.disabled=true;out.hidden=false;out.textContent='Packing…';
    try{
      const r=await fetch(adapter.api('/api/feedback-bundle'),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({notes:$('cc-feedback-notes').value||''})});
      const j=await r.json();
      if(!j.ok) throw new Error(j.error||'bundle failed');
      out.textContent='Saved: '+j.path+(j.skipped&&j.skipped.length?' · left out: '+j.skipped.join(', '):'');
      adapter.notify('Feedback bundle saved — '+j.path,'ok');
    }catch(err){out.textContent='Could not export: '+err.message;adapter.notify('Feedback bundle: '+err.message,'err');}
    finally{btn.disabled=false;}
  };

  // Render selection changes without rebuilding the underlying map or losing its position.

  setInterval(paint,500);

}

