import test from 'node:test';
import assert from 'node:assert/strict';
import {exerciseSummaries,filterData,weeklyWorkouts,chartPoints,csvForSets} from '../../src/reptrace/web/static/model.mjs';
const set = (overrides={}) => ({sessionId:'1',exercise:'Barbell Bench Press',date:'2025-05-01',time:'2025-05-01T09:00:00Z',weight:75,reps:5,volume:375,estimatedMax:87.5,source:'manual',...overrides});
test('exercise ordering uses set counts; load progress ignores missing values and preserves zero',()=>{
 const data=[set({weight:null,volume:null}),set({sessionId:'2',date:'2025-06-01',weight:0,volume:0}),set({sessionId:'3',date:'2026-10-20',weight:80,volume:400}),set({exercise:'Curl'})];
 const rows=exerciseSummaries(data);
 assert.equal(rows[0].name,'Barbell Bench Press');assert.equal(rows[0].count,3);
 assert.equal(rows[0].firstWeight,0);assert.equal(rows[0].latestWeight,80);assert.equal(rows[0].change,80);
 assert.equal(rows[0].volume,400);
 assert.equal(chartPoints(rows[0].history,'weight')[0].value,null);
});
test('missing reps never produce invented rep totals or zero volumes',()=>{
 const row=exerciseSummaries([set({reps:null,weight:16,volume:null,estimatedMax:null})])[0];
 assert.equal(row.reps,null);assert.equal(row.volume,null);assert.equal(row.bestMax,null);
});
test('date filters are inclusive and manual overlays count one session',()=>{
 const data={sets:[set(),set({source:'garmin'}),set({sessionId:'2',date:'2026-10-20'})],workouts:[{id:'1',date:'2025-05-01'},{id:'2',date:'2026-10-20'}]};
 const result=filterData(data,{from:'2025-05-01',to:'2025-05-01'},'manual');
 assert.equal(result.sets.length,1);assert.equal(result.workouts.length,1);
 assert.equal(filterData(data,{from:'2026-01-01',to:'2026-12-31'}).sets.length,1);
});
test('weekly buckets start Monday and distinguish Sunday from the next Monday',()=>{
 const weeks=weeklyWorkouts([{date:'2026-10-18'},{date:'2026-10-19'},{date:'2026-10-20'}],'2026-10-21',2);
 assert.deepEqual(weeks,[{date:'2026-10-12',count:1},{date:'2026-10-19',count:2}]);
});
test('CSV export preserves missing data and quotes source text',()=>{
 const csv=csvForSets([set({weight:null,reps:null,note:'Check "original", please'})]);
 assert.match(csv,/Check ""original"", please/);assert.match(csv,/,"","",/);
 assert.equal(csv.split('\r\n').length,2);
});
test('recovery export keeps sleep units and missing HRV unambiguous',async()=>{
 const {csvForRecovery}=await import('../../src/reptrace/web/static/model.mjs');
 const csv=csvForRecovery([{date:'2026-10-21',sleepHours:7.8,hrv:null,restingHR:49}]);
 assert.match(csv,/Sleep \(hours\)/);assert.match(csv,/"7.8"/);assert.match(csv,/,"","49",/);
});

test('bot-added captain chair sets count toward Core without inventing weighted volume',async()=>{
 const {volumeByWeek,weeklyVolumeHistory}=await import('../../src/reptrace/web/static/model.mjs');
 const rows=[set({exercise:"Captain's Chair Leg Raises",date:'2026-10-23',weight:null,reps:15,volume:null,estimatedMax:null})];
 const [week]=volumeByWeek(rows,'muscle');
 assert.equal(week.group,'Core');assert.equal(week.week,'2026-10-19');
 assert.equal(week.sets,1);assert.equal(week.reps,15);assert.equal(week.volume,null);
 const [series]=weeklyVolumeHistory(rows,'muscle',{}, {from:'2026-10-19',to:'2026-10-25'});
 assert.equal(series.group,'Core');assert.equal(series.history[0].sets,1);
 assert.equal(volumeByWeek(rows,'muscle',{[rows[0].exercise]:'Unassigned'})[0].group,'Unassigned');
});

test('CSV neutralizes spreadsheet formulas without changing numeric measurements',()=>{
  const csv=csvForSets([{date:'2026-10-20',exercise:'=1+1',sessionId:'safe',number:1,weight:42.3,reps:8,volume:338.4,note:'\t=HYPERLINK("https://example.invalid")',originalExercise:' +command'}]);
  assert.ok(csv.includes('"\'=1+1"'));
  assert.ok(csv.includes('"\'\t=HYPERLINK('));
  assert.ok(csv.includes('"\' +command"'));
  assert.ok(csv.includes('"42.3","8","338.4"'));
});
