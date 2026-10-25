import test from 'node:test';
import assert from 'node:assert/strict';
import {exerciseMuscles,muscleMapWeeks,muscleWeekSummary,muscleWeekComparison,filterData} from '../../src/reptrace/web/static/model.mjs';
import {renderMuscleMap,muscleChange,flexMusclePath} from '../../src/reptrace/web/static/muscle-map.mjs';
const set=(exercise,extra={})=>({exercise,date:'2026-10-23',sessionId:'a',weight:80,reps:10,volume:800,source:'garmin',...extra});
const group=(summary,name)=>summary.groups.find(g=>g.name===name);

test('fixed group borders match the artwork clipping regions while hit targets stay fixed',()=>{
 const html=renderMuscleMap({summary:muscleWeekSummary([set('Squat')],'2026-10-19'),weeks:['2026-10-19'],selected:'Core',includeSecondary:true,asOf:'2026-10-24'});
 for(const [side,name] of [['front','Core'],['front','Quads'],['back','Back']]){
  const svg=html.match(new RegExp(`<svg[^>]*data-body-key="body-work-${side}"[\\s\\S]*?<\\/svg>`))[0];
  const region=svg.match(new RegExp(`<clipPath id="body-work-${side}-${name}-region"[^>]*><path class="muscle-region-shape" d="([^"]+)"`))[1];
  const control=svg.match(new RegExp(`<g id="map-${side}-${name}"[\\s\\S]*?<\\/g>`))[0];
  const outlines=[...control.matchAll(/<path d="([^"]+)"[^>]*class="muscle-group-area"/g)].map(match=>match[1]);
  assert.deepEqual(outlines,[region,region],`${side} ${name} border exactly matches its clip region`);
  assert.equal((control.match(/class="muscle-group-hit"/g)||[]).length,2,'seams still belong to the same hit region');
 }
});

test('front shins use broad curved shading without the long rod-like tendon strokes',()=>{
 const html=renderMuscleMap({summary:muscleWeekSummary([],'2026-10-19'),weeks:['2026-10-19'],selected:'all',includeSecondary:true,asOf:'2026-10-24'});
 const front=html.match(/<svg[^>]*data-body-key="body-work-front"[\s\S]*?<\/svg>/)[0];
 const back=html.match(/<svg[^>]*data-body-key="body-work-back"[\s\S]*?<\/svg>/)[0];
 assert.equal((front.match(/class="front-shin-shading"/g)||[]).length,2);
 assert.doesNotMatch(front,/M83 351 L83 418|M87\.83 347 L88\.07 424|L86 413 L83 431/);
 assert.match(back,/L86 413 L83 431/,'posterior tendon artwork remains intact');
});

test('compound sets credit every involved muscle once while weekly totals stay unique',()=>{
 const data=muscleWeekSummary([set('Squat'),set('Barbell Deadlift')],'2026-10-19');
 assert.equal(data.sets,2);assert.equal(data.workouts,1);assert.equal(data.volume,1600);
 assert.equal(group(data,'Glutes').primary,2);assert.equal(group(data,'Glutes').secondary,0);
 assert.equal(group(data,'Glutes').volume,1600);assert.equal(group(data,'Quads').sets,2);
 assert.equal(group(data,'Core').secondary,2);assert.equal(group(data,'Core').primary,0);
 assert.deepEqual(group(data,'Glutes').exercises.map(e=>e.name),['Barbell Deadlift','Squat']);
});
test('supported movement variants count toward their muscles without renaming records',()=>{
 const exercises=['Barbell Squat','Romanian Deadlift','Cable Lateral Raise','Assisted Pull Up','Chin Up','Dip','Assisted Dip','Rear Delt Fly','Overhead Cable Triceps Extension','Single Arm Cable Triceps Extension'];
 const data=muscleWeekSummary(exercises.map(name=>set(name)),'2026-10-19');
 assert.equal(data.sets,10);
 assert.equal(data.exercises.length,10);
 assert.equal(group(data,'Unassigned').sets,0);
 assert.equal(group(data,'Quads').primary,1);
 assert.equal(group(data,'Hamstrings').primary,1);
 assert.equal(group(data,'Glutes').primary,2);
 assert.equal(group(data,'Back').primary,2);
 assert.equal(group(data,'Chest').primary,2);
 assert.equal(group(data,'Triceps').primary,4);
 assert.equal(group(data,'Shoulders').primary,2);
 assert.equal(group(data,'Biceps').secondary,2);
 assert.deepEqual(exerciseMuscles('Assisted Pull Up',{'Assisted Pull Up':'Unassigned'}),{primary:['Unassigned'],secondary:[]});
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

test('muscle flex rounds the belly while preserving tips and curve topology',()=>{
 const rest='M0 0 C0 5 0 10 0 20 L10 20 C10 10 10 5 10 0 Z';
 const flexed=flexMusclePath(rest);
 assert.deepEqual(flexed.match(/[MLCQZ]/g),rest.match(/[MLCQZ]/g));
 assert.match(flexed,/^M0 0/);assert.match(flexed,/L10 20/);
 const values=flexed.match(/-?\d+(?:\.\d+)?/g).map(Number);
 assert.ok(values[4]<0,'left belly expands beyond its resting edge');
 assert.ok(values[10]>10,'right belly expands beyond its resting edge');
 const render=selected=>renderMuscleMap({summary:muscleWeekSummary([],'2026-10-19'),weeks:['2026-10-19'],selected,includeSecondary:true,asOf:'2026-10-24'});
 const normal=render('all'),selected=render('Chest');
 const hitPaths=html=>[...html.matchAll(/<path d="([^"]+)"[^>]*class="muscle-group-hit"/g)].map(match=>match[1]);
 assert.deepEqual(hitPaths(normal),hitPaths(selected),'selection does not move click targets');
 const chest=html=>html.split('data-body-muscle="Chest"')[1].split('data-body-muscle=')[0].match(/class="muscle-surface"[^>]* d="([^"]+)"/)[1];
 assert.notEqual(chest(normal),chest(selected),'selection changes the actual muscle outline');
});

test('full-sized muscles expand inside their own fixed group border and the body silhouette',()=>{
 const render=selected=>renderMuscleMap({summary:muscleWeekSummary([],'2026-10-19'),weeks:['2026-10-19'],selected,includeSecondary:true,asOf:'2026-10-24'});
 const normal=render('all'),selected=render('Chest');
 const shell=html=>html.match(/class="body-outline"[^>]* d="([^"]+)"/)[1];
 assert.equal(shell(normal),shell(selected),'the body never expands');
 for(const html of [normal,selected]){
  const body=html.match(/<clipPath id="body-work-front-body-boundary" clipPathUnits="userSpaceOnUse"><path d="([^"]+)"/)[1];
  assert.equal(body,shell(html),'containment uses the actual body shape');
  assert.match(html,/class="body-muscle-art [^"]+" clip-path="url\(#body-work-front-Chest-region\)" data-body-muscle="Chest"/);
  assert.match(html,/<g clip-path="url\(#body-work-front-body-boundary\)">[\s\S]*class="muscle-group-area"[\s\S]*<\/g><path class="body-containment-outline"/,'muscles and their highlights share body containment; fixed body edge is above both');
  const region=html.match(/<path class="muscle-region-shape" d="([^"]+)"/)[1];
  assert.ok(region.length>20);
  assert.doesNotMatch(html,/class="muscle-group-area"[^>]*data-muscle-rest=/,'the border never morphs');
 }
 const regionPaths=html=>[...html.matchAll(/class="muscle-region-shape" d="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(regionPaths(normal),regionPaths(selected),'all group boundaries remain fixed');
 const shape=selected.split('data-body-muscle="Chest"')[1].match(/data-muscle-rest="([^"]+)" data-muscle-flexed="([^"]+)"/);
 assert.equal(shape[1],'M75 84 C83 80 101 83 107 91 L107 119 C105 135 78 138 66 121 C61 112 64 96 75 84 Z','resting chest keeps its exact original size');
 const width=path=>{const xs=path.match(/-?\d+(?:\.\d+)?/g).map(Number).filter((_,i)=>i%2===0);return Math.max(...xs)-Math.min(...xs);};
 assert.ok(width(shape[2])>width(shape[1])*1.25,'selection expands from the original full size');
});

function sample(path){
 const tokens=path.match(/[MLCQZ]|-?\d+(?:\.\d+)?/g);let i=0,p=[0,0],start=p,result=[];
 const pair=()=>[Number(tokens[i++]),Number(tokens[i++])];
 while(i<tokens.length){const cmd=tokens[i++],a=p;
  if(cmd==='M'){p=pair();start=p;result.push(p);}
  else if(cmd==='L'){p=pair();result.push(p);}
  else if(cmd==='Z'){p=start;result.push(p);}
  else if(cmd==='Q'||cmd==='C'){
   const b=pair(),c=pair(),d=cmd==='C'?pair():null;
   for(let j=1;j<=80;j++){const t=j/80,u=1-t;result.push([0,1].map(k=>d?u*u*u*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t*t*t*d[k]:u*u*a[k]+2*u*t*b[k]+t*t*c[k]));}
   p=d||c;
  }else throw new Error(cmd);
 }
 return result;
}
function outside(point,poly){let inside=false,distance=Infinity;const [x,y]=point;
 for(let i=0,j=poly.length-1;i<poly.length;j=i++){
  const [ax,ay]=poly[j],[bx,by]=poly[i];
  if((ay>y)!==(by>y)&&x<(bx-ax)*(y-ay)/(by-ay)+ax)inside=!inside;
  const dx=bx-ax,dy=by-ay,t=Math.max(0,Math.min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy||1)));
  distance=Math.min(distance,Math.hypot(x-ax-t*dx,y-ay-t*dy));
 }
 return inside?0:distance;
}

test('every original resting muscle fits inside its anatomical compartment',()=>{
 const html=renderMuscleMap({summary:muscleWeekSummary([],'2026-10-19'),weeks:['2026-10-19'],selected:'all',includeSecondary:true,asOf:'2026-10-24'});
 let checked=0;
 for(const side of ['front','back']){
  const svg=html.match(new RegExp(`<svg[^>]*data-body-key="body-work-${side}"[\\s\\S]*?<\\/svg>`))[0];
  for(const match of svg.matchAll(/<clipPath id="body-work-[^"]+-([A-Za-z]+)-region"[^>]*><path class="muscle-region-shape" d="([^"]+)"/g)){
   const [,name,border]=match,region=sample(border);
   const art=svg.split(`data-body-muscle="${name}"`)[1].split('data-body-muscle=')[0];
   const paths=[...art.matchAll(/class="muscle-surface"[^>]*data-muscle-rest="([^"]+)"/g)].map(m=>m[1]);
   assert.ok(paths.length,`${side} ${name} has resting artwork`);
   for(const path of paths)assert.ok(sample(path).every(point=>outside(point,region)<=.3),`${side} ${name} original size must not be clipped smaller`);
   checked++;
  }
 }
 assert.equal(checked,14,'all front and back muscle groups have explicit compartments');
});
