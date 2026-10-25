import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(){
  const nodes={'#exercise-list':{innerHTML:'',scrollTop:0},'.exercise-detail':{innerHTML:'',querySelectorAll:()=>[]}};
  const context={...model,document:{querySelector:selector=>nodes[selector]||{},querySelectorAll:()=>[]},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`
    today=()=> '2026-10-24';
    this.app={state,current,libraryRows,progressPanel,setsTable,insightsPage,volumeHistoryPanel,selectExerciseMuscle};`,context);
  const a=context.app;a.nodes=nodes;
  a.state.data={timezone:'Europe/Kyiv',workouts:[
    {id:'a',date:'2026-10-20',time:'2026-10-20T10:00:00Z',name:'Session A',source:'garmin'},
    {id:'b',date:'2026-10-23',time:'2026-10-23T10:00:00Z',name:'Session B',source:'manual'}],
    sets:[['a','2026-10-20','Barbell Bench Press',100,500,'garmin'],
          ['a','2026-10-20','Cable Biceps Curl',10,50,'garmin'],
          ['b','2026-10-23','Barbell Bench Press',110,550,'manual'],
          ['b','2026-10-23','Cable Biceps Curl',12,60,'manual'],
          ['b','2026-10-23','Pull Up',0,0,'manual']].map(([sessionId,date,exercise,weight,volume,source],i)=>({id:String(i),sessionId,date,time:date+'T10:00:00Z',number:i+1,exercise,weight,reps:5,volume,source})),
    recovery:[{date:'2026-10-20',sleepHours:6,hrv:40},{date:'2026-10-23',sleepHours:8,hrv:60}]};
  return a;
}

test('All exercises combines history without combining strength records and respects library filters',()=>{
  const a=app();a.state.selected='all';
  let view=a.current();
  assert.equal(a.state.selected,'all');assert.equal(view.selected.count,5);
  const html=a.progressPanel(view.selected);
  assert.match(html,/3 exercises · 2 workouts · 5 sets/);
  assert.match(html,/1,160/);
  assert.doesNotMatch(html,/First → latest load|data-volume-week=|volume-history-svg|calendar weeks|Weekly recorded volume/);
  assert.match(html,/one bar per workout/);
  assert.equal((html.match(/class="chart-point workout-bar"/g)||[]).length,2);
  assert.match(html,/data-session="a"[^>]*data-point-value="550"/);
  assert.match(html,/data-session="b"[^>]*data-point-value="610"/);
  assert.equal((html.match(/class="workout-segment"/g)||[]).length,4);
  assert.match(html,/fill="color-mix\(in srgb,var\(--series-0,[^"]+" data-exercise-color="Barbell Bench Press"[^>]*data-point-value="500"/);
  assert.match(html,/fill="color-mix\(in srgb,var\(--series-3,[^"]+" data-exercise-color="Cable Biceps Curl"[^>]*data-point-value="50"/);
  a.state.selected='Cable Biceps Curl';
  for(const metric of ['weight','volume','estimatedMax']){
    a.state.metric=metric;
    const single=a.progressPanel(a.current().selected);
    if(metric!=='estimatedMax')assert.match(single,/class="chart-point workout-bar"[^>]*fill="color-mix\(in srgb,var\(--series-3,[^"]+"/);
  }
  a.state.selected='all';
  assert.match(a.setsTable(view.selected),/<th>Exercise<\/th>/);
  assert.match(a.libraryRows(view.exercises),/data-exercise="all" aria-pressed="true"/);
  a.state.muscleGroup='Biceps';view=a.current();
  assert.equal(view.selected.count,2);
  assert.match(a.progressPanel(view.selected),/110/);
  assert.doesNotMatch(a.setsTable(view.selected),/Barbell Bench Press|Pull Up/);
  a.state.search='no match';assert.equal(a.current().selected.count,0);
  assert.match(a.progressPanel(a.current().selected),/No matching exercises/);
});

test('All exercises keeps source/date filters and survives an empty filtered range',()=>{
  const a=app();a.state.selected='all';a.state.source='manual';
  assert.equal(a.current().selected.count,3);
  a.state.range='custom';a.state.from='2026-10-20';a.state.to='2026-10-20';
  assert.equal(a.current().selected.count,0);assert.equal(a.state.selected,'all');
  assert.doesNotMatch(a.progressPanel(a.current().selected),/NaN|undefined/);
});

for(const mode of ['muscle','exercise'])for(const metric of ['volume','sets','reps']){
  test(`All weekly ${mode}/${metric} sums each set once and includes every contributing workout`,()=>{
    const a=app(),before=JSON.stringify(a.state.data);
    a.state.volumeMode=mode;a.state.volumeMetric=metric;a.state.volumeGroup[mode]='all';
    const html=a.volumeHistoryPanel(a.current());
    assert.equal(a.state.volumeGroup[mode],'all');
    assert.match(html,/data-volume-group="all" class="active" aria-pressed="true"/);
    assert.match(html,/5 recorded sets · 25 recorded reps · 1,160 kg·reps/);
    assert.match(html,/Session A/);assert.match(html,/Session B/);
    assert.doesNotMatch(html,/NaN|undefined/);assert.equal(JSON.stringify(a.state.data),before);
    a.state.source='garmin';
    assert.match(a.volumeHistoryPanel(a.current()),/2 recorded sets · 10 recorded reps · 550 kg·reps/);
  });
}

test('All recovery comparisons preserve per-lift loads, sample counts and thresholds',()=>{
  const a=app();a.state.insightExercise='all';
  const html=a.insightsPage(a.current());
  assert.equal(a.state.insightExercise,'all');
  assert.match(html,/<option value="all" selected>All exercises/);
  assert.match(html,/Loads from different exercises are never averaged together/);
  assert.match(html,/100 <span class="unit">kg/);assert.match(html,/110 <span class="unit">kg/);
  assert.match(html,/10 <span class="unit">kg/);assert.match(html,/12 <span class="unit">kg/);
  assert.doesNotMatch(html,/NaN|undefined/);
  a.state.recoveryMetric='hrv';
  assert.match(a.insightsPage(a.current()),/Each lift uses its own paired-sample median/);
  a.state.data.recovery=[];
  assert.match(a.insightsPage(a.current()),/No paired readings/);
});

for(const page of ['exercises'])test(`${page}: switching a single lift to All muscles updates chart, totals and set history`,()=>{
  const a=app();a.state.page=page;a.state.selected='Barbell Bench Press';
  assert.equal(a.current().selected.name,'Barbell Bench Press');
  a.selectExerciseMuscle('Biceps');
  assert.equal(a.state.selected,'all');
  assert.match(a.nodes['.exercise-detail'].innerHTML,/<h2>Biceps exercises<\/h2>/);
  assert.match(a.nodes['.exercise-detail'].innerHTML,/1 exercises · 2 workouts · 2 sets/);
  assert.doesNotMatch(a.nodes['.exercise-detail'].innerHTML,/Barbell Bench Press|Pull Up/);
  // A single lift may be picked after filtering; All muscles must still clear it.
  a.state.selected='Cable Biceps Curl';
  a.selectExerciseMuscle('all');
  assert.equal(a.state.selected,'all');
  const html=a.nodes['.exercise-detail'].innerHTML;
  assert.match(html,/<h2>All exercises<\/h2>/);
  assert.match(html,/3 exercises · 2 workouts · 5 sets/);
  assert.match(html,/1,160/);
  assert.match(html,/<th>Exercise<\/th>/);
  assert.match(html,/Barbell Bench Press/);assert.match(html,/Cable Biceps Curl/);assert.match(html,/Pull Up/);
  assert.match(a.nodes['#exercise-list'].innerHTML,/data-exercise="all" aria-pressed="true"/);
  assert.match(html,page==='overview'?/Latest sets/:/Set history/);
});

 test('fresh load and browser reload default to the complete All exercises view',()=>{
  for(const a of [app(),app()]){
    a.state.page='exercises';
    assert.equal(a.state.muscleGroup,'all');
    assert.equal(a.state.selected,'all');
    const view=a.current();
    assert.equal(view.selected.all,true);
    assert.equal(view.selected.count,5);
    assert.match(a.progressPanel(view.selected),/3 exercises · 2 workouts · 5 sets/);
    assert.match(a.progressPanel(view.selected),/1,160/);
    assert.match(a.libraryRows(view.exercises),/data-exercise="all" aria-pressed="true"/);
  }
 });
 test('a filtered-out selected lift falls back to all matching records',()=>{
   const a=app();a.state.selected='No longer available';
   const view=a.current();
   assert.equal(a.state.selected,'all');
   assert.equal(view.selected.count,5);
   a.state.source='manual';assert.equal(a.current().selected.count,3);
 });

test('bar-chart date selection follows workout positions rather than elapsed days',()=>{
  const dates=['2026-01-01','2026-01-02','2026-10-23'];
  const selected=model.chartDateRange(Date.parse(dates[0]),Date.parse(dates[2]),0,300,110,190,dates);
  assert.deepEqual(selected,{from:'2026-01-02',to:'2026-01-02'});
  assert.deepEqual(model.chartDateRange(Date.parse(dates[0]),Date.parse(dates[2]),0,300,300,0,dates),{from:dates[0],to:dates[2]});
});
test('workout bars retain zero and missing readings as separate sessions',()=>{
  const a=app();a.state.data.volumeSettings={bodyWeightKg:80};
  a.state.data.sets.forEach(s=>{s.exercise='Assisted Pull Up';s.weight=s.sessionId==='a'?80:null;});
  const html=a.progressPanel(a.current().selected);
  assert.match(html,/class="chart-point workout-bar"[^>]*data-session="a"[^>]*data-point-value="0"/);
  assert.match(html,/class="workout-missing" data-session="b"/);
  assert.doesNotMatch(html,/<circle|<path|NaN/);
});

test('Back exercise totals, charts and set history include bodyweight and added pull-up load',()=>{
 const a=app();a.state.page='exercises';a.state.muscleGroup='Back';
 a.state.data.volumeSettings={bodyWeightKg:80};
 const bw=a.state.data.sets.find(s=>s.exercise==='Pull Up');
 a.state.data.sets.push({...bw,id:'weighted',sessionId:'a',date:'2026-10-20',time:'2026-10-20T10:00:00Z',source:'garmin',weight:20,volume:100});
 a.state.data.sets.push({...bw,id:'row',exercise:'Seated Cable Row',sessionId:'a',date:'2026-10-20',time:'2026-10-20T10:00:00Z',source:'garmin',weight:50,volume:250});
 const before=JSON.stringify(a.state.data);
 const view=a.current(),pull=view.exercises.find(e=>e.name==='Pull Up');
 assert.equal(pull.volume,1012.5);
 assert.equal(model.sumKnown(view.selected.rows.map(s=>s.volume)),1325);
 const html=a.progressPanel(view.selected);
 assert.match(html,/Back exercises/);assert.match(html,/1,325/);
 assert.match(html,/data-exercise-color="Pull Up"[^>]*data-point-value="450"/);
 assert.match(html,/data-exercise-color="Pull Up"[^>]*data-point-value="562.5"/);
 assert.match(a.setsTable(view.selected),/450/);
 assert.equal(JSON.stringify(a.state.data),before);
 a.state.selected='Pull Up';a.state.metric='volume';
 const single=a.progressPanel(a.current().selected);
 assert.match(single,/Adjusted volume/);assert.match(single,/data-point-value="450"/);
 assert.match(single,/data-point-value="562.5"/);
 a.state.source='manual';
 assert.equal(a.current().selected.volume,450);
 a.state.data.volumeSettings.exercises={'Pull Up':{multiplier:2,bodyweight:1}};
 assert.equal(a.current().selected.volume,800);
 a.state.page='volume';
 assert.equal(a.current().exercises.find(e=>e.name==='Pull Up').volume,800);
});

test('exercise volume uses earlier weigh-ins outside the selected date range',()=>{
 const a=app();a.state.selected='Pull Up';a.state.range='custom';
 a.state.from='2026-10-23';a.state.to='2026-10-23';
 a.state.data.recovery.push({date:'2026-10-19',bodyWeightKg:84},{date:'2026-10-24',bodyWeightKg:100});
 assert.equal(a.current().selected.volume,472.5);
 assert.equal(a.current().selected.bestWeight,0);
});
