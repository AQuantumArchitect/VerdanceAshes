export const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const pretty = value => String(value || 'Unknown').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
export const field = (label, text) => `<div class="cc-field"><h3>${escape(label)}</h3><p>${escape(text)}</p></div>`;

export function operation(op) {
  if (!op) return field('Choose an operation','Select a sortie in the operations rail to see its requirements, risks, and route.');
  return `<p class="cc-eyebrow">Operation / ${escape(pretty(op.mapId))}</p><h2>${escape(op.title)}</h2>`+
    field('Purpose',op.purpose)+field('Required',op.required)+field('Bring home',op.bringHome)+
    field('Known risks',op.risks)+field('Consequences',op.consequences);
}

// One line for the operations rail: people of ours who are not at camp.
// rows: [{name, where: posted|transit|field, label, wounded}]
export function fieldLine(rows) {
  const list=(rows || []).filter(Boolean);
  if(!list.length) return '';
  const word=r=>r.where==='transit' ? 'on the road' : (r.label || 'somewhere');
  return `<p class="cc-field-people" role="status">Left in the field: ${list.map(r=>`<b class="${r.wounded?'bad':''}">${escape(r.name)}</b> (${escape(word(r))}${r.wounded?' · wounded':''})`).join(', ')}</p>`;
}

export function thread(t, live) {
  return `<p class="cc-eyebrow">Company matter / ${escape(t.stage)}</p><h2>${escape(t.title)}</h2>
    <p>${escape(t.opening)}</p>${field('Why now',t.reason)}
    ${t.history.length ? field('Commitment record',t.trust>0?'A kept promise strengthens this thread.':t.trust<0?'An unfinished promise remains part of this relationship.':'This situation is still unfolding.') : ''}
    ${t.remaining !== null ? field('Commitment window',`${t.remaining} completed sorties remain. Planning and reading do not consume turns.`):''}
    ${t.perspectives.map(p=>`<blockquote><strong>${escape(pretty(p.speaker))}</strong><p>${escape(p.text)}</p></blockquote>`).join('')}
    ${reactions(t.reactions)}
    ${t.promise?field('Your words',t.promise):''}${t.response?field('Around the table',t.response):''}
    ${t.choices.map(c=>`<div class="cc-choice"><button type="button" data-commit="${escape(c.id)}" ${live?'':'disabled'}>${escape(c.label)}</button><p class="cc-stance">${escape(c.stance || "Commitment")}</p><p>${escape(c.obligation)}</p><small>No resource cost. Records a narrative commitment; does not launch a battle.</small></div>`).join('')}
    ${t.stage==='Resolved'?field('Remembered',t.remembered || t.callback):''}
    <h3>Available operations</h3>${t.operations.length ? t.operations.map(id=>`<button type="button" data-operation="${escape(id)}">Plan: ${escape(t.operationLabels?.[id] || pretty(id))}</button>`).join(''): '<p>No compatible operation is currently available. Review the map after your next result.</p>'}
    <details><summary>Evidence and history</summary>${t.history.map(e=>`<p>Turn ${escape(e.turn)} · ${escape(e.text)}</p>`).join('') || '<p>Based on the current campaign situation. No previous commitment is assumed.</p>'}</details>`;
}

export function chronicle(events) {
  return events.map(e=>`<article class="cc-record"><p class="cc-eyebrow">Return ${escape(e.turn)} / ${escape(pretty(e.mapId))}</p>
    <h2>${escape(e.title)}</h2>${field('Company',e.participants.length?e.participants.map(pretty).join(', '):'Deployment record unavailable.')}
    ${e.wounded.length?field('Wounded',e.wounded.map(pretty).join(', ')):''}
    ${field('Resources',Object.entries(e.resources).map(([k,v])=>`${pretty(k.replace('tenebrium','Tenebrium '))}: ${v}`).join(' · ') || 'No detailed resource ledger was supplied with this result.')}
    ${e.consequences.map(c=>field(c.origin==='memory'?'Remembered':c.origin==='elsewhere'?'While you were elsewhere':c.origin==='campaign_update'?'War assessment after your return':'Because of this return',c.text)).join('')}
    <details><summary>Result evidence</summary><p>${escape(e.id)}</p><pre>${escape(JSON.stringify(e.credits,null,2))}</pre></details></article>`).join('') || '<p class="cc-empty">Your first recorded return begins the chronicle. Older saves are not given invented history.</p>';
}

export function reactions(rows) {
  return (rows || []).map(r=>`<article class="cc-reaction"><strong>${escape(pretty(r.speaker))}</strong><p>${escape(r.text)}</p><small>${r.basis==='kept'?'After a kept promise':r.basis==='unfinished'?'After an unfinished promise':'Remembering your words'}: “${escape(r.memory)}”</small></article>`).join('');
}
export function scene(s,live) {
  return `<details data-scene="${escape(s.id)}"><summary>${escape(s.title)} · ${s.pair.map(pretty).map(escape).join(' / ')}${s.decision?' · Answered':''}</summary>${s.setup?`<p>${escape(s.setup)}</p>`:''}${s.beats.map(b=>`<blockquote><strong>${escape(pretty(b.speaker))}</strong><p>${escape(b.text)}</p></blockquote>`).join('')}${s.decision?field('Your answer',s.decision.words)+field('The response',s.decision.response): (s.choices || []).map(c=>`<div class="cc-choice"><button data-commit="${escape(c.id)}" ${live?'':'disabled'}>${escape(c.label)}</button><p class="cc-stance">${escape(c.stance)}</p><small>Records your position. No cost, deadline, or battle effect.</small></div>`).join('')}</details>`;
}
