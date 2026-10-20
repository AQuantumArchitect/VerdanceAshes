import {escape, pretty, field} from './render.js';

export function installOverlays(theater) {
  const bar=document.createElement('fieldset'); bar.className='cc-overlays';
  bar.innerHTML='<legend>Map layers</legend>'+['Ownership','Intelligence','Route'].map(label=>`<label><input type="checkbox" data-overlay="${label.toLowerCase()}" checked> ${label}</label>`).join('');
  theater.insertBefore(bar,document.getElementById('board'));
  // Belief key: what the COMPANY believes holds each zone. Faction colour = "we believe they hold it".
  const key=document.createElement('div');key.className='cc-faction-key';key.setAttribute('aria-label','Belief legend');
  key.innerHTML='<span class="ally">● Ours</span><span class="held">◆ Held · unseen</span><span class="armada">◆ Armada</span><span class="cortex">◆ Cortex</span><span class="nullmercs">◆ Null Mercs</span><span class="raptors">◆ Wild</span><span class="scavengers">◆ Scavengers</span><span class="empty">○ Empty</span><span class="dark">? Dark · nobody looked</span>';
  bar.after(key);
  bar.addEventListener('change',e=>theater.classList.toggle(`hide-${e.target.dataset.overlay}`,!e.target.checked));
}

const FACTION_WORD={armada:'Armada',cortex:'Cortex',nullmercs:'Null Mercs',wild:'Wild',raptors:'Raptors',raptor:'Raptors',scavengers:'Scavengers',legion:'Legion'};

// Owner glyph + label from the zone's BELIEF data attributes (set by renderBoard).
// Never re-adds a truth class; never rewrites the belief tooltip.
export function ownerFromBelief(zone) {
  const believed=zone.dataset.believed || 'dark';
  const control=zone.dataset.control || 'unknown';
  if(believed==='ours') return '● Ours';
  if(believed==='held') return FACTION_WORD[control] ? `◆ ${FACTION_WORD[control]}` : '◆ Held';
  if(believed==='empty') return '○ Empty';
  if(believed==='unsure') return '◌ Unsure';
  return '? Dark';
}

export function updateIntelligence(narrative, mapId) {
  document.querySelectorAll('#board-zones .zone').forEach(zone=>{
    const record=narrative?.intelligence?.[`${mapId}:${zone.dataset.zone}`];
    const ownerText=ownerFromBelief(zone);
    let owner=zone.querySelector('.cc-owner');if(!owner){owner=document.createElement('span');owner.className='cc-owner';zone.append(owner);}
    if(owner.textContent!==ownerText) owner.textContent=ownerText;
    let label=zone.querySelector('.cc-intel');
    if(!label){label=document.createElement('span');label.className='cc-intel';zone.append(label);}
    const conf=Math.round(Number(zone.dataset.conf || 0)*100);
    const st=zone.dataset.state || 'dark';
    const intelText=record ? `${record.status==='Confirmed'?'●':'◐'} ${record.status}` : (st==='dark' ? '○ Dark' : `${st==='current'?'●':'◐'} ${conf}% · ${st}`);
    if(label.textContent!==intelText) label.textContent=intelText;
    const name=zone.querySelector('.zone-label')?.textContent || zone.dataset.zone;
    const aria=`${name}. Believed ${ownerText.slice(2)}, ${conf}% sure, ${st}.${record?' '+record.status+'.':''}`;
    if(zone.getAttribute('aria-label')!==aria) zone.setAttribute('aria-label',aria);
  });
}

export function zoneInspector(zoneId,mapId,narrative) {
  const record=narrative?.intelligence?.[`${mapId}:${zoneId}`];
  const el=document.querySelector(`#board-zones .zone[data-zone="${CSS.escape(String(zoneId))}"]`);
  const believed=el ? ownerFromBelief(el).slice(2) : 'Unknown';
  const conf=el ? Math.round(Number(el.dataset.conf || 0)*100) : 0;
  const st=el ? (el.dataset.state || 'dark') : 'dark';
  return `<p class="cc-eyebrow">Map intelligence</p><h2>${escape(pretty(zoneId))}</h2>`+
    field('We believe',st==='dark' ? 'Nobody has looked.' : `${believed} · ${conf}% sure · ${st}`)+
    field('Knowledge',record?.status || (st==='dark' ? 'Unknown' : 'From the company\'s own looking'))+
    field('Source',record?.source || 'No explicit battlefield observation is recorded.')+
    (record?.lastObservedTurn!=null?field('Last observed',`Completed sortie ${record.lastObservedTurn}. Conditions may have changed since then.`):field('Last observed','See the zone tooltip for how long ago the company looked.'))+
    field('Pad rules','A pad is legal when we believe the zone is ours, when it is a quiet rim we believe empty or have not looked at, or when it is the camp\'s next pad. You leave from where you landed.')+
    field('Forecast','Belief is not the ground. A route suggestion is not a promise of safety.');
}
