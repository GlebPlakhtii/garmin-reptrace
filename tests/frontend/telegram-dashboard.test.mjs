import test from 'node:test';
import assert from 'node:assert/strict';
import {dashboard} from '../../src/reptrace/coaching/dashboard.mjs';
import {adjustedVolumeSets, weeklyVolumeHistory} from '../../src/reptrace/web/static/model.mjs';

const sets=[
  {id:'1',sessionId:'a',date:'2026-10-01',exercise:'Custom lift',weight:50,reps:10,estimatedMax:66.67,source:'manual'},
  {id:'2',sessionId:'b',date:'2026-10-20',exercise:'Custom lift',weight:60,reps:null,estimatedMax:null,source:'garmin'},
  {id:'3',sessionId:'a',date:'2026-10-01',exercise:'Assisted Pull-up',weight:30,reps:10,estimatedMax:999,source:'manual'},
  {id:'4',sessionId:'b',date:'2026-10-20',exercise:'Assisted Pull-up',weight:20,reps:10,estimatedMax:999,source:'garmin'},
];
const data={sets,workouts:[{id:'a',name:'Upper 1',date:'2026-10-01'},{id:'b',name:'Upper 2',date:'2026-10-20'}],recovery:[{date:'2026-10-01',bodyWeightKg:80,sleepHours:7,deepSeconds:1234}],volumeSettings:{exercises:{'Custom lift':{multiplier:2,bodyweight:0,loadCopies:1,reviewed:true}}},goals:[{id:'g',exercise:'Assisted Pull-up',mode:'load_reps',weight:25,reps:10}]};
const read=(view,opts={})=>dashboard(data,{view,source:'all',offset:0,limit:200,...opts},'2026-10-25');

test('Telegram uses exact web volume model, with independent numeric coverage',()=>{
  const result=read('weekly_volume',{exercise:'Custom lift',options:{grouping:'exercise'}});
  assert.equal(result.rows.find(r=>r.week==='2026-09-28').volume,1000);
  assert.equal(result.rows.find(r=>r.week==='2026-10-19').volume,null);
  assert.equal(result.rows.find(r=>r.week==='2026-10-05').volume,0);
  const expected=weeklyVolumeHistory(adjustedVolumeSets(sets.filter(s=>s.exercise==='Custom lift'),data.recovery,data.volumeSettings),'exercise',{},{}).flatMap(r=>r.history).sort((a,b)=>b.week.localeCompare(a.week));
  assert.deepEqual(result.rows,expected);
  assert.equal(read('exercises',{exercise:'Custom lift'}).rows[0].volume,500);
});

test('Assistance records, estimates and goals retain direction and full-history scope',()=>{
  const record=read('records',{exercise:'Assisted Pull-up'}).rows[0];
  assert.equal(record.bestWeight,20);
  assert.equal(record.bestMax,null);
  assert.ok(read('strength',{exercise:'Assisted Pull-up'}).rows.every(p=>p.value===null));
  const goal=read('goals',{from_date:'2026-10-01',to_date:'2026-10-01',source:'manual'}).rows[0];
  assert.equal(goal.progress.achieved,true);
  assert.equal(goal.progress.sessionId,'b');
});

test('Comparison suppresses incomplete volume differences and pagination is explicit',()=>{
  const row=read('compare',{options:{left_id:'a',right_id:'b'}}).rows.find(r=>r.name==='Custom lift');
  assert.equal(row.volumeComplete,false);
  assert.equal(row.volumeChange,null);
  const page=read('sets',{source:'manual',limit:1});
  assert.equal(page.matchingRows,2);assert.equal(page.truncated,true);
  assert.equal(read('sets',{source:'manual',limit:1,offset:1}).rows[0].id,'3');
  assert.equal(read('recovery').rows[0].deepSeconds,1234);
  assert.equal(read('sets',{from_date:'2027-01-01'}).matchingRows,0);
});

test('Every dashboard view handles empty data and CSV preserves formula protections',()=>{
  for(const view of ['overview','exercises','sets','workouts','weekly_volume','muscle_map','strength','recovery','insights','records','goals','sync','preferences']){
    const result=dashboard({sets:[],workouts:[],recovery:[]},{view,exercise:view==='strength'?'Bench':null,source:'all',offset:0,limit:10},'2026-10-25');
    assert.ok(Array.isArray(result.rows),view);
  }
  const csv=dashboard({...data,sets:[{...sets[0],note:'=HYPERLINK("bad")'}]},{view:'csv_sets',source:'all',offset:0,limit:10,options:{search:'Upper 1'}},'2026-10-25');
  assert.match(csv.text,/'=HYPERLINK/);
  assert.equal(csv.count,1);
});
