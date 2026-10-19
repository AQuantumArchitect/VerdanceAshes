export const session = { workspace: 'operations', narrative: null, selectedThread: null, selectedHero: null, selectedZone: null, allThreads: false, signature: '', error: '' };

export async function readNarrative(adapter) {
  const response = await fetch(adapter.api('/api/narrative'), {cache:'no-store'});
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.error || 'Campaign information is unavailable.');
  return body.narrative;
}

export async function commitChoice(adapter, choiceId) {
  const requestId = crypto.randomUUID();
  const response = await fetch(adapter.api('/api/narrative-choice'), {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({choiceId, expectedRevision:session.narrative.revision, requestId})
  });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.error || 'The commitment could not be recorded.');
  session.narrative = body.narrative;
  return body;
}
