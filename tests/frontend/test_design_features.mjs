import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function setup(document={querySelector:()=>({})}){
 const context={...model,document,window:{},setTimeout,clearTimeout};
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\nthis.api={state,pages,nav,muscleTag,recoveryChart,loadingSkeleton,bindChart,volumeExerciseImpact,volumeHistoryChart};bindTimeSelection=()=>{};`,context);
 return context.api;
}
test('grouped navigation includes every page exactly once and preserves active state',()=>{
 const elements={};const a=setup({querySelector:key=>elements[key]??={}});a.state.page='recovery';a.nav();
 const html=elements['#navigation'].innerHTML;
 for(const key of Object.keys(a.pages))assert.equal(html.split(`href="#${key}"`).length-1,1,key);
 for(const group of ['Training','Management'])assert.ok(html.includes(`aria-label="${group}"`));
 assert.match(html,/href="#recovery"[^>]*aria-current="page"/);
 const primary=html.slice(0,html.indexOf('<details'));
 for(const key of ['overview','exercises','workouts','volume','recovery','nutrition','garmin','insights'])assert.ok(primary.includes(`href="#${key}"`));
 for(const key of ['next','records','compare','goals','logging','sync','preferences'])assert.ok(!primary.includes(`href="#${key}"`));
});
test('muscle tags honor corrections, escape names, and leave unknown exercises unassigned',()=>{
 const a=setup();assert.match(a.muscleTag('Barbell Bench Press'),/>Chest</);
 a.state.data={muscleOverrides:{'Barbell Bench Press':'Triceps','Custom':'<custom>'}};
 assert.match(a.muscleTag('Barbell Bench Press'),/>Triceps</);
 assert.match(a.muscleTag('Custom'),/&lt;custom&gt;/);
 assert.equal(a.muscleTag('Mystery movement'),'');
});
test('recovery tooltip comparisons use previous recorded values across missing days including zero',()=>{
 const a=setup();const html=a.recoveryChart([{date:'2026-10-20',hrv:0},{date:'2026-10-21',hrv:null},{date:'2026-10-22',hrv:50}],{key:'hrv',label:'HRV',color:'#59dcc5',unit:'ms'});
 assert.match(html,/data-point-previous="0" data-point-value="50" data-point-unit="ms"/);
 assert.equal((html.match(/data-point-value=/g)||[]).length,2);
});
test('tooltips expose change, fit narrow charts, and dismiss with Escape',()=>{
 const classes=new Set();const tooltip={textContent:'',style:{},classList:{add:v=>classes.add(v),remove:v=>classes.delete(v)},get offsetWidth(){return classes.has('visible')?180:0},get offsetHeight(){return classes.has('visible')?70:0}};
 const handlers={};const point={dataset:{pointLabel:'22 Oct · 50 ms',pointPrevious:'0',pointValue:'50',pointUnit:'ms'},addEventListener:(k,v)=>handlers[k]=v,getBoundingClientRect:()=>({left:295,top:90,width:6})};
 const container={querySelector:()=>tooltip,querySelectorAll:()=>[point],getBoundingClientRect:()=>({left:0,top:0,width:300})};
 const a=setup({querySelectorAll:selector=>selector==='.chart-wrap'?[container]:[]});a.bindChart();handlers.focus();
 assert.match(tooltip.textContent,/\+50 ms vs previous reading/);
 assert.equal(tooltip.style.left,'210px');assert.equal(tooltip.style.top,'8px');
 handlers.keydown({key:'Escape'});assert.equal(classes.has('visible'),false);
});
test('loading placeholder identifies itself without inventing metric values',()=>{
 const html=setup().loadingSkeleton();assert.match(html,/aria-busy="true"/);assert.match(html,/role="status"/);assert.match(html,/aria-hidden="true"/);
 assert.doesNotMatch(html,/Training sessions|kg|bpm/);
});

test('recovery line does not interpolate across entirely absent calendar days',()=>{
 const a=setup();
 const html=a.recoveryChart([{date:'2026-10-20',hrv:40},{date:'2026-10-23',hrv:50}],{key:'hrv',label:'HRV',color:'#59dcc5',unit:'ms'});
 // Each isolated reading gets its own line run, rather than suggesting daily measurements.
 assert.equal((html.match(/fill="none" stroke="#59dcc5"/g)||[]).length,2);
 assert.equal((html.match(/class="chart-point daily-point"/g)||[]).length,2);
});

test('weekly exercise impact uses known contributions and preserves missing and zero values',()=>{
 const a=setup();a.state.data={};
 const sets=[{date:'2026-10-19',exercise:'A',volume:300,reps:10},{date:'2026-10-19',exercise:'B',volume:100,reps:5},{date:'2026-10-19',exercise:'Missing',volume:null,reps:null},{date:'2026-10-19',exercise:'Zero',volume:0,reps:0}];
 const html=a.volumeExerciseImpact(sets,'volume');
 assert.match(html,/75%/);assert.match(html,/25%/);assert.match(html,/0%/);
 assert.match(html,/data-view-exercise="Missing"/);assert.match(html,/0\/1 sets have inputs/);
 assert.doesNotMatch(html,/NaN|Infinity/);
 assert.match(a.volumeExerciseImpact([],'sets'),/No exercises recorded/);
 assert.equal((a.volumeExerciseImpact(sets,'sets').match(/25%/g)||[]).length,8);
});
test('exercise identities share their muscle palette and respect corrected assignments',()=>{
 assert.match(model.exerciseColor('Barbell Bench Press'),/--series-0,/);
 assert.match(model.exerciseColor('Incline Bench Press'),/--series-0,/);
 assert.notEqual(model.exerciseColor('Barbell Bench Press'),model.exerciseColor('Incline Bench Press'));
 assert.match(model.exerciseColor('Cable Biceps Curl'),/--series-3,/);
 assert.match(model.exerciseColor('Custom',{'Custom':'Triceps'}),/--series-4,/);
 assert.match(model.exerciseColor('Unknown'),/--series-11,/);
 assert.equal(new Set(model.MUSCLE_GROUPS.map(model.muscleColor)).size,12);
});

test('weekly all-muscle bars stack exact exercise contributions with shared colors',()=>{
 const a=setup();a.state.data={};
 const week={week:'2026-10-19',sets:3,reps:15,volume:400,volumeKnown:2,exercises:[
 {group:'Barbell Bench Press',volume:300,sets:1,reps:10},
 {group:'Pull Up',volume:100,sets:1,reps:5},
 {group:'Missing',volume:null,sets:1,reps:null}]};
 const html=a.volumeHistoryChart({group:'All muscles',history:[week]},'volume');
 assert.equal((html.match(/class="volume-exercise-segment"/g)||[]).length,2);
 assert.match(html,/Barbell Bench Press: 300 adjusted kg·reps · 75% of week/);
 assert.match(html,/Pull Up: 100 adjusted kg·reps · 25% of week/);
 const heights=Object.fromEntries([...html.matchAll(/class="volume-exercise-segment" data-exercise-color="([^"]+)"[^>]*height="([^"]+)"/g)].map(m=>[m[1],Number(m[2])]));
 assert.ok(Math.abs(heights['Barbell Bench Press']/heights['Pull Up']-3)<1e-9);
 assert.equal((a.volumeHistoryChart({group:'All muscles',history:[week]},'sets').match(/class="volume-exercise-segment"/g)||[]).length,3);
 assert.doesNotMatch(html,/NaN|Infinity/);
});
test('stack order groups exercises bottom-to-top and honors muscle overrides',()=>{
 const names=['Lateral Raise','Barbell Bench Press','Leg Press','Calf Raise Machine','Squat','Pull Up','Mystery','Cable Crunch'];
 assert.deepEqual([...names].sort((a,b)=>model.compareExerciseStack(a,b)),['Calf Raise Machine','Leg Press','Squat','Cable Crunch','Pull Up','Barbell Bench Press','Lateral Raise','Mystery']);
 assert.deepEqual(['Squat','Custom','Calf Raise Machine'].sort((a,b)=>model.compareExerciseStack(a,b,{Custom:'Calves'})),['Calf Raise Machine','Custom','Squat']);
 const a=setup();a.state.data={};
 const exercises=names.map(group=>({group,volume:10,sets:1,reps:1}));
 const html=a.volumeHistoryChart({group:'All muscles',history:[{week:'2026-10-19',volume:80,sets:8,volumeKnown:8,exercises}]},'volume');
 assert.deepEqual([...html.matchAll(/class="volume-exercise-segment" data-exercise-color="([^"]+)"/g)].map(m=>m[1]),['Calf Raise Machine','Leg Press','Squat','Cable Crunch','Pull Up','Barbell Bench Press','Lateral Raise','Mystery']);
 assert.equal(exercises[0].group,'Lateral Raise');
});
test('all muscle and exercise filters start with all selections',()=>{
 const {state}=setup();
 assert.equal(state.selected,'all');assert.equal(state.muscleGroup,'all');
 assert.equal(state.volumeGroup.muscle,'all');assert.equal(state.volumeGroup.exercise,'all');
 assert.equal(state.mapMuscle,'all');assert.equal(state.insightExercise,'all');
});
