import test from 'node:test';
import assert from 'node:assert/strict';
import {exerciseMuscles,muscleMapWeeks,muscleWeekSummary,muscleWeekComparison,filterData} from '../../src/reptrace/web/static/model.mjs';
import {renderMuscleMap,muscleChange} from '../../src/reptrace/web/static/muscle-map.mjs';
const set=(exercise,extra={})=>({exercise,date:'2026-10-23',sessionId:'a',weight:80,reps:10,volume:800,source:'garmin',...extra});
const group=(summary,name)=>summary.groups.find(g=>g.name===name);

test('compound sets credit every involved muscle once while weekly totals stay unique',()=>{
 const data=muscleWeekSummary([set('Squat'),set('Barbell Deadlift')],'2026-10-19');
 assert.equal(data.sets,2);assert.equal(data.workouts,1);assert.equal(data.volume,1600);
 assert.equal(group(data,'Glutes').primary,2);assert.equal(group(data,'Glutes').secondary,0);
 assert.equal(group(data,'Glutes').volume,1600);assert.equal(group(data,'Quads').sets,2);
 assert.equal(group(data,'Core').secondary,2);assert.equal(group(data,'Core').primary,0);
 assert.deepEqual(group(data,'Glutes').exercises.map(e=>e.name),['Barbell Deadlift','Squat']);
});
test('primary-only excludes assistance but keeps compound primary work and recorded totals',()=>{
 const data=muscleWeekSummary([set('Barbell Bench Press'),set('Barbell Deadlift')],'2026-10-19',{},false);
 assert.equal(group(data,'Triceps').sets,0);assert.equal(group(data,'Core').sets,0);
 assert.equal(group(data,'Glutes').primary,1);assert.equal(data.sets,2);
});
test('custom assignments win, do not duplicate secondary credits, and unassigned stays explicit',()=>{
 assert.deepEqual(exerciseMuscles('Squat',{Squat:'Quads'}).primary,['Quads','Glutes']);
 assert.deepEqual(exerciseMuscles('Squat',{Squat:'Glutes'}).primary,['Glutes']);
 const data=muscleWeekSummary([set('Squat'),set('Barbell Bench Press'),set('Mystery')],'2026-10-19',{Squat:'Glutes','Barbell Bench Press':'Triceps'});
 assert.equal(group(data,'Quads').sets,0);assert.equal(group(data,'Triceps').sets,1);assert.equal(group(data,'Triceps').secondary,0);
 assert.equal(group(data,'Unassigned').sets,1);
 assert.deepEqual(exerciseMuscles('Squat',{Squat:'Unassigned'}),{primary:['Unassigned'],secondary:[]});
});
test('bodyweight reps and recorded zero remain distinct from missing volume',()=>{
 const rows=[set("Captain's Chair Leg Raises",{weight:null,volume:null,reps:15,source:'manual'}),set('Cable Crunch',{weight:0,volume:0,reps:null})];
 const core=group(muscleWeekSummary(rows,'2026-10-19'),'Core');
 assert.equal(core.sets,2);assert.equal(core.reps,15);assert.equal(core.repsKnown,1);
 assert.equal(core.volume,0);assert.equal(core.volumeKnown,1);
 assert.equal(group(muscleWeekSummary(rows.slice(0,1),'2026-10-19'),'Core').volume,null);
});
test('calendar includes empty weeks and applies Monday boundaries and date/source filters',()=>{
 const sets=[set('Squat',{date:'2026-10-18'}),set('Squat',{date:'2026-10-19'}),set('Squat',{date:'2026-10-25',source:'manual'}),set('Squat',{date:'2026-10-26'})];
 assert.equal(muscleWeekSummary(sets,'2026-10-19').sets,2);
 const filtered=filterData({sets,workouts:[]},{from:'2026-10-20',to:'2026-10-25'},'manual');
 assert.equal(muscleWeekSummary(filtered.sets,'2026-10-19').sets,1);
 assert.deepEqual(muscleMapWeeks([], {from:'2026-10-18',to:'2026-11-01'},'2026-11-01'),['2026-10-12','2026-10-19','2026-10-26']);
 assert.deepEqual(muscleMapWeeks([],{},'2026-10-24'),['2026-10-19']);
 assert.deepEqual(muscleMapWeeks(sets,{from:'2026-11-02',to:'2026-11-01'},'2026-11-01'),[]);
 assert.equal(muscleWeekSummary(sets,'2026-11-02').sets,0);
});
test('map exposes keyboard controls, roles, empty states, and escapes exercise names',()=>{
 const name='<img src=x onerror=alert(1)>';
 const summary=muscleWeekSummary([set(name)],'2026-10-19',{[name]:'Glutes'});
 const html=renderMuscleMap({summary,weeks:['2026-10-19'],selected:'Glutes',includeSecondary:true,asOf:'2026-10-24'});
 assert.match(html,/id="map-back-Glutes"[^>]*role="button" tabindex="0" aria-pressed="true"/);
 assert.match(html,/data-map-week="2026-10-19" aria-pressed="true"/);
 assert.match(html,/&lt;img src=x onerror=alert\(1\)&gt;/);assert.doesNotMatch(html,/<img src=x/);
 assert.match(html,/in progress/);assert.match(html,/primary work takes priority/);
 const empty=renderMuscleMap({summary:muscleWeekSummary([],'2026-10-19'),weeks:['2026-10-19'],selected:'Glutes',includeSecondary:true,asOf:'2026-10-25'});
 assert.match(empty,/No training recorded this week/);assert.doesNotMatch(empty,/NaN|undefined/);
});

test('week-to-date compares matching weekdays and ignores later days of the previous week',()=>{
 const rows=[set('Squat',{date:'2026-10-12'}),set('Squat',{date:'2026-10-17'}),set('Squat',{date:'2026-10-18'}),set('Squat',{date:'2026-10-19'})];
 const comparison=muscleWeekComparison(rows,'2026-10-19',{asOf:'2026-10-24',historyStart:'2026-01-01'});
 assert.equal(comparison.available,true);assert.deepEqual(comparison.periods,[{from:'2026-10-12',to:'2026-10-17'}]);
 assert.equal(comparison.sets,2);assert.equal(group(comparison,'Glutes').sets,2);
});
test('four-week average includes empty weeks and excludes selected-week records',()=>{
 const rows=[set('Squat',{date:'2026-10-05'}),set('Squat',{date:'2026-10-06'}),set('Squat',{date:'2026-10-19'})];
 const comparison=muscleWeekComparison(rows,'2026-10-19',{count:4,asOf:'2026-10-24',historyStart:'2026-01-01'});
 assert.equal(comparison.sets,.5);assert.equal(group(comparison,'Glutes').sets,.5);
 assert.equal(group(comparison,'Glutes').volume,400);assert.equal(group(comparison,'Calves').volume,0);
 assert.equal(comparison.periods.length,4);
});
test('comparison keeps missing volume unknown and rejects insufficient history',()=>{
 const rows=[set('Squat',{date:'2026-10-12',volume:null})];
 const comparison=muscleWeekComparison(rows,'2026-10-19',{asOf:'2026-10-24',historyStart:'2026-01-01'});
 assert.equal(group(comparison,'Glutes').volume,null);assert.equal(group(comparison,'Glutes').reps,10);
 assert.equal(muscleWeekComparison(rows,'2026-10-19',{count:4,asOf:'2026-10-24'}).available,false);
 assert.equal(muscleWeekComparison(rows,'2026-10-19',{count:0,asOf:'2026-10-24'}),null);
});
test('comparison reads history outside current date range, applies source and partial-date scope',()=>{
 const data={sets:[set('Squat',{date:'2026-10-13',source:'manual'}),set('Squat',{date:'2026-10-14',source:'manual'}),set('Squat',{date:'2026-10-15',source:'garmin'})],workouts:[]};
 const sets=filterData(data,{},'manual').sets;
 const comparison=muscleWeekComparison(sets,'2026-10-19',{range:{from:'2026-10-21',to:'2026-10-23'},asOf:'2026-10-24',historyStart:'2026-01-01'});
 assert.deepEqual(comparison.periods,[{from:'2026-10-14',to:'2026-10-16'}]);
 assert.equal(comparison.sets,1);assert.equal(group(comparison,'Glutes').sets,1);
});
test('comparison renderer shows absolute change without zero-baseline percentages or an inner scrollbar',()=>{
 const rows=[set('Squat',{date:'2026-10-23'})];
 const comparison=muscleWeekComparison(rows,'2026-10-19',{asOf:'2026-10-24',historyStart:'2026-01-01'});
 const html=renderMuscleMap({summary:muscleWeekSummary(rows,'2026-10-19'),weeks:['2026-10-12','2026-10-19'],selected:'Glutes',includeSecondary:true,asOf:'2026-10-24',comparison});
 assert.match(html,/<b>\+1 more<\/b>/);assert.match(html,/<span>Previous week<\/span><strong>0<\/strong>/);
 assert.match(html,/Compared with previous week · Mon–Sat/);
 assert.match(html,/id="map-compare-1"/);assert.match(html,/data-map-week="2026-10-19"/);assert.doesNotMatch(html,/<select|data-map-shift|data-map-today|Infinity|NaN/);
});
test('long exercise breakdowns expand instead of scrolling inside the map',()=>{
 const names=['A','B','C','D','E'];const overrides=Object.fromEntries(names.map(name=>[name,'Core']));
 const html=renderMuscleMap({summary:muscleWeekSummary(names.map(name=>set(name)),'2026-10-19',overrides),weeks:['2026-10-19'],selected:'Core',includeSecondary:true,asOf:'2026-10-24'});
 assert.match(html,/<details class="map-more-exercises"><summary>Show 1 more exercise/);
});

test('comparison body distinguishes increases, decreases, equal work, inactivity and missing history',()=>{
 for(const [current,prior,available,status] of [[8,3,true,'more'],[2,4,true,'less'],[3,3,true,'same'],[0,0,true,'no-work'],[3,0,true,'more'],[0,3,true,'less'],[8,3,false,'unknown']]){
  assert.equal(muscleChange({sets:current},{sets:prior},available).status,status);
 }
 const rows=[set('Squat')],summary=muscleWeekSummary(rows,'2026-10-19');
 const comparison=muscleWeekComparison(rows,'2026-10-19',{asOf:'2026-10-24',historyStart:'2026-01-01'});
 const html=renderMuscleMap({summary,weeks:['2026-10-19'],selected:'Glutes',includeSecondary:true,asOf:'2026-10-24',comparison});
 assert.match(html,/id="map-change-back-Glutes" class="body-muscle change-more selected" role="button" tabindex="0"/);
 assert.match(html,/Glutes: 1 more sets: 1 vs 0/);
 assert.match(html,/id="map-change-front-Chest" class="body-muscle change-no-work/);
 const ids=[...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(ids).size,ids.length);
 const off=renderMuscleMap({summary,weeks:['2026-10-19'],selected:'Glutes',includeSecondary:true,asOf:'2026-10-24'});
 assert.doesNotMatch(off,/id="map-change-/);
});
test('all-muscle map counts compound exercises once and compares unique totals',()=>{
 const rows=[set('Squat'),set('Barbell Bench Press'),set('Squat',{date:'2026-10-16'})];
 const summary=muscleWeekSummary(rows,'2026-10-19');
 assert.equal(summary.exercises.reduce((n,e)=>n+e.sets,0),2);
 assert.equal(summary.exercises.reduce((n,e)=>n+e.volume,0),1600);
 const comparison=muscleWeekComparison(rows,'2026-10-19',{asOf:'2026-10-25',historyStart:'2026-10-01'});
 assert.equal(comparison.sets,1);assert.equal(comparison.reps,10);assert.equal(comparison.volume,800);
 const html=renderMuscleMap({summary,weeks:['2026-10-19'],selected:'all',includeSecondary:true,asOf:'2026-10-25',comparison});
 assert.match(html,/data-map-muscle="all" aria-pressed="true"/);
 assert.match(html,/2 recorded sets · each set counted once/);
 assert.equal((html.match(/data-view-exercise=/g)||[]).length,2);
 const empty=renderMuscleMap({summary:muscleWeekSummary([],'2026-10-19'),weeks:['2026-10-19'],selected:'all',includeSecondary:true,asOf:'2026-10-25'});
 assert.match(empty,/No training recorded this week/);
});
