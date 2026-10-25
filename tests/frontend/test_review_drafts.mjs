import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(storage=new Map()){
  const nodes=new Map();
  const document={querySelector:key=>{if(!nodes.has(key))nodes.set(key,{innerHTML:'',showModal(){this.open=true;}});return nodes.get(key);}};
  const context={...model,document,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},crypto,structuredClone,window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\nthis.app={state,showWorkoutEditor,persistDraft,storedDrafts,removeStoredDraft};`,context);
  context.app.state.data={sets:[],workouts:[]};
  const submitStart=source.indexOf("document.addEventListener('submit'");
  const submitEnd=source.indexOf("$('#editor-dialog').addEventListener('click'",submitStart);
  document.addEventListener=(_name,callback)=>context.submit=callback;
  vm.runInContext(source.slice(submitStart,submitEnd),context);
  async function rejectSave(status) {
    context.rejectSave=async()=>{const error=new Error('Save rejected');error.status=status;throw error;};
    vm.runInContext('saveAction=rejectSave;',context);
    const controls=new Map();
    const form={id:'workout-form',querySelector:key=>{
      if(!controls.has(key))controls.set(key,{disabled:false,textContent:''});
      return controls.get(key);
    }};
    await context.submit({target:form,preventDefault(){}});
    return controls;
  }
  return {...context.app,nodes,rejectSave};
}
test('draft restores metadata, precise loads, and sets after a new app instance',()=>{
  const storage=new Map(),a=app(storage);a.showWorkoutEditor();
  Object.assign(a.state.draft,{name:'Upper 1',date:'2026-10-20',durationMinutes:'42.5'});
  a.state.draft.sets[0].weight=42.3;a.state.draft.sets[0].reps=8;a.persistDraft();
  const b=app(storage);b.showWorkoutEditor();
  assert.equal(b.state.draft.name,'Upper 1');assert.equal(b.state.draft.sets[0].weight,42.3);
  assert.equal(b.state.draft.requestId,a.state.draft.requestId);
  assert.match(b.nodes.get('#editor-content').innerHTML,/Restored your unsaved draft/);
  assert.equal(b.state.draft.durationMinutes,'42.5');
});
test('pending save is immutable across reload and different workouts retain separate drafts',()=>{
  const storage=new Map(),a=app(storage);a.showWorkoutEditor();
  a.state.draft.pending={action:'workout_save',requestId:a.state.draft.requestId,sets:[{reps:8,weight:42.3}]};a.persistDraft();
  const b=app(storage);b.showWorkoutEditor('another');b.state.draft.name='Other';b.persistDraft();
  b.showWorkoutEditor();assert.equal(b.state.draft.pending.requestId,a.state.draft.requestId);
  assert.match(b.nodes.get('#editor-content').innerHTML,/fieldset class="workout-inputs" disabled/);
  assert.match(b.nodes.get('#editor-content').innerHTML,/Retry save/);
  b.removeStoredDraft(null);assert.equal(Object.keys(b.storedDrafts()).length,1);
  assert.equal(b.storedDrafts().another.name,'Other');
});
test('editor includes Unknown sets in original order and captures metadata for conflict checks',()=>{
  const a=app();a.state.data={workouts:[{id:'a',date:'2026-10-20',name:'Upper 1',duration:2700,revision:'rev'}],
    sets:[{id:'a:2',sessionId:'a',exercise:'Bench',order:2,weight:40,reps:8}],
    hiddenSets:[{id:'a:1',sessionId:'a',exercise:'Unknown',order:1,weight:null,reps:10}]};
  a.showWorkoutEditor('a');
  assert.deepEqual(Array.from(a.state.draft.sets,s=>s.id),['a:1','a:2']);
  assert.equal(a.state.draft.durationMinutes,45);
  assert.equal(a.state.draft.expectedMetadata.name,'Upper 1');
  assert.doesNotMatch(a.nodes.get('#editor-content').innerHTML,/readonly/);
});

test('authorization rejection leaves the retained workout editable and discardable',async()=>{
  for(const status of [401,403]){
    const a=app();a.showWorkoutEditor();
    a.state.draft.sets[0].weight=40;a.state.draft.sets[0].reps=8;
    const previousId=a.state.draft.requestId;
    a.state.draft.pending={requestId:previousId,sets:structuredClone(a.state.draft.sets)};
    const controls=await a.rejectSave(status);
    assert.equal(a.state.draft.pending,undefined);
    assert.notEqual(a.state.draft.requestId,previousId);
    assert.equal(a.state.draft.sets[0].weight,40);
    assert.equal(controls.get('fieldset').disabled,false);
    assert.equal(controls.get('[data-action="discard-draft"]').disabled,false);
    assert.equal(controls.get('[type="submit"]').textContent,'Save workout');
  }
});

test('uncertain server failures retain the exact save identity and locked payload',async()=>{
  const a=app();a.showWorkoutEditor();
  const pending={requestId:a.state.draft.requestId,sets:structuredClone(a.state.draft.sets)};
  a.state.draft.pending=pending;
  const controls=await a.rejectSave(503);
  assert.equal(a.state.draft.pending,pending);
  assert.equal(a.state.draft.requestId,pending.requestId);
  assert.equal(controls.get('fieldset').disabled,true);
  assert.equal(controls.get('[type="submit"]').textContent,'Retry save');
  assert.equal(controls.get('[type="submit"]').disabled,false);
});
