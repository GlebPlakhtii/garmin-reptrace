import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
const context={...model,document:{},window:{},structuredClone,setTimeout,clearTimeout};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\nthis.api={splitRepeat,validateFullStructure,fullStepHtml};`,context);
const {splitRepeat,validateFullStructure,fullStepHtml}=context.api;
test('full editor retains native pounds and explicitly labels missing units',()=>{
  const step={stepType:{stepTypeKey:'interval'},weightValue:80,weightUnit:{unitKey:'pound'}};
  assert.match(fullStepHtml(step,'0/0'),/Weight \(lb\)/);
  assert.match(fullStepHtml({...step,weightUnit:null},'0/0'),/Weight \(unit unspecified\)/);
});
test('repeat splitting preserves playback and caps expansion before allocating excessive steps',()=>{
  const set={stepType:{stepTypeKey:'interval'},weightValue:80},rest={stepType:{stepTypeKey:'rest'}};
  assert.deepEqual(Array.from(splitRepeat({numberOfIterations:2,skipLastRestStep:true,workoutSteps:[set,rest]}),s=>s.stepType.stepTypeKey),['interval','rest','interval']);
  const group={numberOfIterations:100,workoutSteps:[{numberOfIterations:100,workoutSteps:[set]}]};
  assert.throws(()=>splitRepeat(group),/5,000/);
});
test('advanced JSON is validated before replacing a usable editor draft',()=>{
  for(const segments of [null,[],[null],[{workoutSteps:[null]}],[{workoutSteps:[{numberOfIterations:0,workoutSteps:[]}]}]])assert.throws(()=>validateFullStructure(segments));
  assert.doesNotThrow(()=>validateFullStructure([{workoutSteps:[{stepType:{stepTypeKey:'interval'}}]}]));
});
test('custom exercise work remains excluded until factors are explicitly reviewed',()=>{
  const sets=[{exercise:'Custom machine',date:'2026-10-01',weight:40,reps:10}];
  const rule={multiplier:.5,loadCopies:1,bodyweight:0,assistance:false};
  assert.equal(model.adjustedVolumeSets(sets,[],{exercises:{'Custom machine':rule}})[0].volume,null);
  assert.equal(model.adjustedVolumeSets(sets,[],{exercises:{'Custom machine':{...rule,reviewed:true}}})[0].volume,200);
});
