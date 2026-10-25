import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(){
 const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout,structuredClone};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+'\nopenEditor=html=>{this.output=html};this.app={state,garminPage,showGarminEditor,showGarminPreview,showFullEditor,splitRepeat};',context);
 return context;
}
test('Garmin page matches plans automatically without source selector',()=>{
 const c=app();c.app.state.data={nextSessions:[{type:'upper1',name:'Upper 1'}]};c.app.state.garminWorkouts=[{id:123,name:'Upper 1',planType:'upper1'}];
 const html=c.app.garminPage();assert.match(html,/Quick weights &amp; reps|Quick weights & reps/);assert.match(html,/Full edit/);assert.doesNotMatch(html,/Use suggestions from|<select/);
});
test('full Garmin editor exposes workout structure and review',()=>{
 const c=app();c.app.state.garminFull={workoutId:123,name:'Leg Day 1',description:'Tempo',segments:[{workoutSteps:[
  {stepType:{stepTypeKey:'repeat'},numberOfIterations:3,skipLastRestStep:true,workoutSteps:[
   {stepType:{stepTypeKey:'interval'},endCondition:{conditionTypeKey:'reps'},endConditionValue:8,category:'SQUAT',exerciseName:'BARBELL_SQUAT',weightValue:80},
   {stepType:{stepTypeKey:'rest'},endCondition:{conditionTypeKey:'time'},endConditionValue:90}
  ]}
 ]}]};
 c.app.showFullEditor();
 assert.match(c.output,/Workout name/);assert.match(c.output,/Iterations/);assert.match(c.output,/Skip last rest/);
 assert.match(c.output,/Garmin exercise code/);assert.match(c.output,/Review full workout/);
 assert.match(c.output,/Advanced workout structure/);
});
test('splitting a repeat keeps the played sequence and omitted final rest',()=>{
 const c=app();const steps=c.app.splitRepeat({numberOfIterations:3,skipLastRestStep:true,workoutSteps:[
  {stepType:{stepTypeKey:'interval'},exerciseName:'SQUAT',stepId:5},
  {stepType:{stepTypeKey:'rest'},endConditionValue:90,stepId:6},
 ]});
 assert.equal(steps.length,5);
 assert.equal(JSON.stringify(steps.map(s=>s.stepType.stepTypeKey)),JSON.stringify(['interval','rest','interval','rest','interval']));
 assert.ok(steps.every(s=>s.stepId===undefined));
});
test('manual editor shows original targets and optional suggestion fill',()=>{
 const c=app();c.app.showGarminEditor({previewId:'id',name:'Upper 1',editable:[{index:0,exercise:'Bench',stepOrder:2,sets:3,weightEditable:true,weight:80,reps:8,suggestedWeight:85,suggestedReps:10}]});
 assert.match(c.output,/Fill next-session targets/);assert.match(c.output,/value="80"/);assert.match(c.output,/value="8"/);assert.match(c.output,/Review changes/);
});
test('Garmin editor separates exercises and numbers repeated sets within each group',()=>{
 const c=app();c.app.showGarminEditor({previewId:'id',name:'Upper 1',editable:[
  {index:0,exercise:'Bench',stepOrder:2,sets:3,weightEditable:true,weight:80,reps:8},
  {index:1,exercise:'Curl',stepOrder:3,sets:1,weightEditable:true,weight:20,reps:10},
  {index:2,exercise:'Bench',stepOrder:7,sets:1,weightEditable:true,weight:75,reps:10},
 ]});
 assert.equal((c.output.match(/class="garmin-group"/g)||[]).length,2);
 assert.match(c.output,/Sets 1–3/);assert.match(c.output,/Set 4/);
 assert.match(c.output,/Shared target/);
 assert.equal((c.output.match(/data-garmin-row=/g)||[]).length,3);
 assert.ok(c.output.indexOf('data-garmin-row="2"')<c.output.indexOf('data-garmin-row="1"'));
});
test('Garmin confirmation groups changes for the same exercise',()=>{
 const c=app();c.app.showGarminPreview({previewId:'id',name:'Upper 1',changes:[
  {exercise:'Bench',stepOrder:2,sets:1,field:'weight',before:80,after:82.5},
  {exercise:'Curl',stepOrder:3,sets:1,field:'reps',before:8,after:9},
  {exercise:'Bench',stepOrder:2,sets:1,field:'reps',before:8,after:10},
 ],skipped:[]});
 assert.equal((c.output.match(/class="garmin-group"/g)||[]).length,2);
 assert.ok(c.output.indexOf('82.5 kg')<c.output.indexOf('10 reps'));
 assert.ok(c.output.indexOf('10 reps')<c.output.indexOf('Curl</span></h3>'));
});
test('Garmin confirmation allows a structure-only loop regrouping',()=>{
 const c=app();c.app.showGarminPreview({previewId:'id',name:'Upper 1',changes:[],structureChanged:true,skipped:[{exercise:'Bench',reason:'Identical sets stay in one repeat block.'}]});
 assert.match(c.output,/Target values stay the same/);
 assert.match(c.output,/Update Garmin workout/);
 assert.doesNotMatch(c.output,/data-apply-garmin="id" disabled/);
});
