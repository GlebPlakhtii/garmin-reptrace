import test from 'node:test';
import assert from 'node:assert/strict';
import {matchingRepHistory,volumeByWeek,plateauSignals,compareWorkouts,recoveryComparison,goalProgress,presetRange} from '../../src/reptrace/web/static/model.mjs';
const row=(id,date,weight=80,reps=5,extra={})=>({sessionId:String(id),exercise:'Barbell Bench Press',date,time:date+'T09:00:00Z',weight,reps,volume:weight===null||reps===null?null:weight*reps,...extra});
test('matching rep progress excludes other rep bands and missing loads, grouping each workout once',()=>{
 const history=matchingRepHistory([row(1,'2026-10-01'),row(1,'2026-10-01',85),row(2,'2026-10-02',100,1),row(3,'2026-10-03',null),row(4,'2026-10-04',0)],5);
 assert.deepEqual(history.map(h=>h.weight),[85,0]);assert.equal(history[0].sets,2);
});
test('weekly muscle involvement totals overlap and retain incomplete coverage',()=>{
 const sets=[row(1,'2026-10-18'),row(2,'2026-10-19'),row(2,'2026-10-19',null,null),row(2,'2026-10-19',null,8,{exercise:'Unknown'})];
 const groups=volumeByWeek(sets,'muscle',{'Unknown':'Chest'});
 assert.equal(groups.reduce((n,r)=>n+r.sets,0),10);assert.equal(groups.length,6);
 assert.equal(volumeByWeek(sets).reduce((n,r)=>n+r.sets,0),4);
 assert.equal(groups[0].week,'2026-10-19');assert.equal(groups[0].sets,3);assert.equal(groups[0].volumeKnown,1);assert.equal(groups[0].reps,13);assert.equal(groups[0].volume,400);
 assert.equal(volumeByWeek([sets[2]])[0].volume,null);
});
test('plateau flags require enough comparable sessions and a meaningful date span',()=>{
 const sets=['01','05','10','15','20'].map((d,i)=>row(i,'2026-10-'+d));
 assert.equal(plateauSignals(sets,'2026-10-21')[0].status,'watch');
 assert.equal(plateauSignals([...sets,row(6,'2026-10-27',85)],'2026-10-28')[0].status,'progressing');
 assert.equal(plateauSignals(sets,'2027-01-01')[0].status,'inactive');
 assert.equal(plateauSignals(sets.slice(1),'2026-10-21')[0].status,'insufficient');
 assert.equal(plateauSignals(sets.map(s=>({...s,date:'2026-10-20'})),'2026-10-21')[0].status,'insufficient');
});
test('workout comparison only pairs equal reps and keeps absent exercises unknown',()=>{
 const sets=[row(1,'2026-10-01'),row(2,'2026-10-02',85),row(2,'2026-10-02',100,1),row(1,'2026-10-01',15,10,{exercise:'Curl'})];
 const [bench,curl]=compareWorkouts({sets},'1','2');
 assert.deepEqual(bench.matched,[{reps:5,left:80,right:85}]);assert.equal(curl.loadChange,null);assert.equal(curl.right,undefined);
});
test('recovery comparisons join exact dates and reps, without borrowing nearby readings',()=>{
 const sets=[row(1,'2026-10-01'),row(2,'2026-10-02',90),row(3,'2026-10-03',95),row(4,'2026-10-04',100,1)];
 const recovery=[{date:'2026-10-01',sleepHours:6},{date:'2026-10-02',sleepHours:8},{date:'2026-10-04',sleepHours:8}];
 const result=recoveryComparison(sets,recovery,'Barbell Bench Press',5,'sleepHours');
 assert.equal(result.pairs.length,2);assert.equal(result.threshold,7);assert.equal(result.low.mean,80);assert.equal(result.high.mean,90);assert.equal(result.enough,false);
});
test('goals require load and reps in one actual set and use all qualifying history',()=>{
 const goal={exercise:'Barbell Bench Press',mode:'load_reps',weight:100,reps:5};
 const sets=[row(1,'2026-10-01',100,1),row(2,'2026-10-02',80,10)];
 assert.equal(goalProgress(goal,sets).achieved,false);assert.equal(goalProgress(goal,sets).percent,80);
 const result=goalProgress(goal,[...sets,row(3,'2026-10-03',100,5)]);assert.equal(result.date,'2026-10-03');assert.equal(result.percent,100);
 assert.equal(goalProgress({...goal,mode:'reps',reps:12},[row(1,'2026-10-01',null,12)]).achieved,true);
 assert.equal(goalProgress(goal,[]).best,null);
});
test('date presets include both endpoints and clamp calendar months and leap years',()=>{
 assert.deepEqual(presetRange('30','2026-10-21'),{from:'2026-09-22',to:'2026-10-21'});
 assert.equal(presetRange('6m','2026-08-31').from,'2026-02-28');
 assert.equal(presetRange('1y','2024-02-29').from,'2023-02-28');
 assert.equal(presetRange('all','2026-10-21').from,'');
});
test('historical volume fills calendar gaps, preserves missing metrics and marks partial weeks',async()=>{
 const {weeklyVolumeHistory}=await import('../../src/reptrace/web/static/model.mjs');
 const sets=[row(1,'2026-10-01',80,5),row(2,'2026-10-13',null,null),row(3,'2026-10-21',0,10)];
 const [chest]=weeklyVolumeHistory(sets,'muscle',{}, {from:'2026-10-01',to:'2026-10-22'});
 assert.equal(chest.history.length,4);assert.equal(chest.history[0].partial,true);assert.equal(chest.history[0].volume,400);
 assert.equal(chest.history[1].sets,0);assert.equal(chest.history[1].volume,0);assert.equal(chest.history[1].noRecords,true);
 assert.equal(chest.history[2].sets,1);assert.equal(chest.history[2].volume,null);assert.equal(chest.history[2].noRecords,false);
 assert.equal(chest.history[3].volume,0);assert.equal(chest.history[3].volumeKnown,1);assert.equal(chest.history[3].partial,true);
 assert.equal(chest.history.reduce((n,w)=>n+w.sets,0),3);
});
test('historical volume respects filters and primary muscle overrides without duplication',async()=>{
 const {weeklyVolumeHistory}=await import('../../src/reptrace/web/static/model.mjs');
 const sets=[row(1,'2026-10-01'),row(2,'2026-10-14',20,10,{exercise:'Custom'})];
 const series=weeklyVolumeHistory(sets,'muscle',{'Custom':'Back'},{from:'2026-10-10',to:'2026-10-18'});
 assert.equal(series.length,1);assert.equal(series[0].group,'Back');assert.equal(series[0].count,1);
 assert.equal(series[0].history[0].week,'2026-10-05');assert.equal(series[0].history.at(-1).week,'2026-10-12');
 assert.deepEqual(weeklyVolumeHistory([], 'exercise'),[]);
});

test('assisted progress means less assistance at matching reps, including zero assistance',()=>{
 const rows=[40,35,30,25,20].map((weight,i)=>({exercise:'Assisted Pull Up',sessionId:String(i),date:`2026-10-${String(1+i*5).padStart(2,'0')}`,time:'09:00',weight,reps:8,volume:weight*8}));
 const history=matchingRepHistory([...rows,{...rows.at(-1),weight:30}],8);
 assert.equal(history.at(-1).weight,20);
 const signal=plateauSignals(rows,'2026-10-25',4)[0];
 assert.equal(signal.status,'progressing');assert.equal(signal.baseline,40);
 const goal={exercise:'Assisted Pull Up',mode:'load_reps',weight:25,reps:8};
 assert.equal(goalProgress(goal,rows.slice(0,2)).achieved,false);
 assert.equal(goalProgress(goal,rows).date,'2026-10-16');
 assert.equal(goalProgress({...goal,weight:0},[{...rows[0],weight:0}]).achieved,true);
 assert.equal(goalProgress({...goal,weight:0},rows).achieved,false);
 const compared=compareWorkouts({sets:[{...rows[0],sessionId:'a'},{...rows[0],sessionId:'a',weight:35},{...rows.at(-1),sessionId:'b'}]},'a','b')[0];
 assert.equal(compared.matched[0].left,35);assert.equal(compared.matched[0].right,20);
});

test('incomplete sets cannot imply a comparable volume decrease',()=>{
 const sets=[row(1,'2026-10-01'),row(1,'2026-10-01',null,5),row(2,'2026-10-02',80,5)];
 const result=compareWorkouts({sets},'1','2')[0];
 assert.equal(result.left.count,2);assert.equal(result.right.count,1);
 assert.equal(result.volumeChange,null);assert.equal(result.volumeComplete,false);
});

test('deadlift history credits glutes and secondary muscles with missing-aware totals',async()=>{
 const {weeklyVolumeHistory}=await import('../../src/reptrace/web/static/model.mjs');
 const sets=[row(1,'2026-10-20',100,5,{exercise:'Barbell Deadlift'}),row(1,'2026-10-20',null,3,{exercise:'Barbell Deadlift'})];
 const range={from:'2026-10-19',to:'2026-11-01'};
 const history=weeklyVolumeHistory(sets,'muscle',{},range);
 assert.deepEqual(history.map(s=>s.group).sort(),['Back','Core','Glutes','Hamstrings','Quads']);
 for(const series of history){
  const [week,empty]=series.history;
  assert.equal(week.sets,2);assert.equal(week.reps,8);assert.equal(week.volume,500);
  assert.equal(week.volumeKnown,1);assert.equal(week.repsKnown,2);
  assert.equal(empty.sets,0);assert.equal(empty.volume,0);assert.equal(empty.noRecords,true);
 }
 const overridden=weeklyVolumeHistory(sets,'muscle',{'Barbell Deadlift':'Back'},range);
 assert.deepEqual(overridden.map(s=>s.group).sort(),['Back','Core']);
 assert.equal(overridden.find(s=>s.group==='Back').history[0].sets,2);
 const unassigned=weeklyVolumeHistory(sets,'muscle',{'Barbell Deadlift':'Unassigned'},range);
 assert.deepEqual(unassigned.map(s=>s.group),['Unassigned']);
 const [exercise]=weeklyVolumeHistory(sets,'exercise',{},range);
 assert.equal(exercise.history[0].sets,2);assert.equal(exercise.history[0].volume,500);
});
