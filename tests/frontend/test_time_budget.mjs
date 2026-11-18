import test from 'node:test';
import assert from 'node:assert/strict';
import {renderTimeBudget, renderTimeBudgetResult, installTimeBudget} from '../../src/reptrace/web/static/time-budget.mjs';

test('time-budget result preserves unknown targets and warns when priorities exceed budget', () => {
  const html = renderTimeBudgetResult({name:'<img src=x onerror=alert(1)>', exercises:[{name:'Curl', priority:true, proposed:[{weight:null,reps:0}], reason:'Review'}], adaptation:{budgetExceeded:true, estimatedMinutes:12, timeBudget:10, limitations:'Estimate', changes:['Keep priorities'], timing:{Curl:{source:'assumed 3 minutes per set'}}, setImpact:[{exercise:'Curl',recordedThisWeek:3,originalPlannedSets:3,adaptedPlannedSets:3}]}});
  assert.match(html, /Needs more time: 12 min/);
  assert.match(html, /— × 0/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /alternatives, not completed sets/);
});

test('empty training history explains how to start; arbitrary workout names are selectable', () => {
  assert.match(renderTimeBudget({workouts:[], sets:[]}), /Log or sync/);
  const html = renderTimeBudget({workouts:[{id:'new',name:'Hotel circuit',date:'2026-10-20'}],sets:[{sessionId:'new',exercise:'Custom exercise'}]}, 'new');
  assert.match(html, /Hotel circuit/);
  assert.match(html, /Custom exercise/);
  assert.match(html, /Keep all sets/);
});

test('submit reads current input even when a change event has not fired', async () => {
  const originalDocument = globalThis.document, originalFetch = globalThis.fetch;
  const listeners = {};
  const button = {disabled:false}, error = {textContent:''};
  const form = {id:'time-budget-form', isConnected:false, elements:{session_id:{value:'new'}, time_minutes:{value:'10'}}, querySelector:s=>s==='[type="submit"]'?button:error, querySelectorAll:()=>[]};
  let sent;
  try {
    globalThis.document = {addEventListener:(name,handler)=>{listeners[name]=handler;}};
    globalThis.fetch = async (url, options) => {sent=JSON.parse(options.body); return {ok:true,json:async()=>({})};};
    installTimeBudget(()=>({}));
    await listeners.submit({target:form,preventDefault(){}});
    assert.equal(sent.time_minutes,10);
    assert.equal(sent.session_id,'new');
    assert.equal(button.disabled,false);
  } finally {
    globalThis.document = originalDocument;
    globalThis.fetch = originalFetch;
  }
});
