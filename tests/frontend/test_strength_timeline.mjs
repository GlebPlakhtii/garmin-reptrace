import test from 'node:test';
import assert from 'node:assert/strict';
import {estimatedStrengthHistory,filterData} from '../../src/reptrace/web/static/model.mjs';

const set=(id,date,weight,reps,estimatedMax,extra={})=>({sessionId:id,date,time:date+'T12:00:00Z',exercise:'Bench Press',weight,reps,estimatedMax,source:'manual',...extra});

test('weekly 1RM takes the best eligible estimate of one lift, preserving missing weeks',()=>{
  const rows=[set('a','2026-10-05',60,5,70),set('a','2026-10-05',50,6,60),
    set('b','2026-10-07',75,2,80),set('c','2026-10-20',60,12,null),
    set('other','2026-10-07',200,3,220,{exercise:'Deadlift'})];
  const before=JSON.stringify(rows);
  const result=estimatedStrengthHistory(rows,'Bench Press',true,{from:'2026-10-05',to:'2026-10-25'});
  assert.deepEqual(result.map(p=>p.value),[80,null,null]);
  assert.deepEqual(result.map(p=>p.sets),[3,0,1]);
  assert.equal(result[0].eligibleSets,3);
  assert.equal(result[0].sessionId,'b');
  assert.equal(JSON.stringify(rows),before);
  assert.deepEqual(estimatedStrengthHistory(rows,'Bench Press').map(p=>p.value),[70,80,null]);
});

test('timeline obeys source/date filters and does not invent zero estimates',()=>{
  const rows=[set('a','2026-10-05',60,5,70,{source:'garmin'}),set('b','2026-10-07',75,2,80),set('c','2026-10-20',80,3,88)];
  const range={from:'2026-10-06',to:'2026-10-22'};
  const filtered=filterData({sets:rows,workouts:[]},range,'manual');
  const result=estimatedStrengthHistory(filtered.sets,'Bench Press',true,range);
  assert.deepEqual(result.map(p=>p.value),[80,null,88]);
  assert.equal(result[0].partial,true);
  assert.equal(result.at(-1).partial,true);
  assert.deepEqual(estimatedStrengthHistory(rows,'Missing lift'),[]);
});

test('invalid, timed, bodyweight-only and assisted sets cannot produce a strength estimate',()=>{
  const rows=[set('a','2026-10-05',0,5,50),set('b','2026-10-06',60,null,70),
    set('c','2026-10-07',60,12,84),set('d','2026-10-08',null,5,70),
    set('e','2026-10-09',60,5,70,{assistance:true}),set('f','2026-10-10',60,5,NaN)];
  assert.deepEqual(estimatedStrengthHistory(rows,'Bench Press').map(p=>p.value),Array(6).fill(null));
});
