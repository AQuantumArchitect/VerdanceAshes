import {escape, pretty, field} from './render.js';

export function installOverlays(theater) {
  const bar=document.createElement('fieldset'); bar.className='cc-overlays';
  bar.innerHTML='<legend>Map layers</legend>'+['Ownership','Intelligence','Route'].map(label=>`<label><input type="checkbox" data-overlay="${label.toLowerCase()}" checked> ${label}</label>`).join('');
  theater.insertBefore(bar,document.getElementById('board'));
  const key=document.createElement('div');key.className='cc-faction-key';key.setAttribute('aria-label','Faction ownership legend');key.innerHTML='<span class="ally">● Company / Null Mercs</span><span class="armada">◆ Armada</span><span class="cortex">■ Cortex</span><span class="raptors">▲ Raptors</span><span class="scavengers">✦ Scavengers</span>';bar.after(key);
  bar.addEventListener('change',e=>theater.classList.toggle(`hide-${e.target.dataset.overlay}`,!e.target.checked));
}

export function updateIntelligence(narrative, mapId) {
  document.querySelectorAll('#board-zones .zone').forEach(zone=>{
    const record=narrative?.intelligence?.[`${mapId}:${zone.dataset.zone}`];
    // Unknown hostile ownership must not leak through colors or hover text.
    if(!record && !zone.classList.contains('ctrl-ashwalkers')) {
      [...zone.classList].filter(c=>c.startsWith('ctrl-')).forEach(c=>zone.classList.remove(c));
      zone.title=zone.querySelector('.zone-label')?.textContent || zone.dataset.zone;
    }
    const faction=[...zone.classList].find(c=>c.startsWith('ctrl-'))?.slice(5);
    let owner=zone.querySelector('.cc-owner');if(!owner){owner=document.createElement('span');owner.className='cc-owner';zone.append(owner);}
    owner.textContent=({ashwalkers:'● Company',nullmercs:'● Null Mercs',armada:'◆ Armada',cortex:'■ Cortex',raptors:'▲ Raptors',raptor:'▲ Raptors',wild:'▲ Raptors',scavengers:'✦ Scavengers'})[faction] || '';
    let label=zone.querySelector('.cc-intel');
    if(!label){label=document.createElement('span');label.className='cc-intel';zone.append(label);}
    label.textContent=record ? `${record.status==='Confirmed'?'●':'◐'} ${record.status}` : '○ Unknown';
    zone.setAttribute('aria-label',`${zone.querySelector('.zone-label')?.textContent || zone.dataset.zone}. ${record?record.status:'Intelligence unknown'}.`);
  });
}

export function zoneInspector(zoneId,mapId,narrative) {
  const record=narrative?.intelligence?.[`${mapId}:${zoneId}`];
  return `<p class="cc-eyebrow">Map intelligence</p><h2>${escape(pretty(zoneId))}</h2>`+
    field('Knowledge',record?.status || 'Unknown')+
    field('Source',record?.source || 'No explicit battlefield observation is recorded.')+
    (record?.lastObservedTurn!=null?field('Last observed',`Completed sortie ${record.lastObservedTurn}. Conditions may have changed since then.`):field('Last observed','No direct observation has been recorded.'))+
    field('Landing rules','Use a legal quiet perimeter or an established Ashwalker foothold. Establish an Ashwalker foothold to unlock an inland landing area.')+
    field('Forecast','Unobserved enemy strength remains uncertain. A route suggestion is not a promise of safety.');
}
