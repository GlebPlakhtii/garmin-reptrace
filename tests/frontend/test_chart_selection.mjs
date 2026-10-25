import test from 'node:test';
import assert from 'node:assert/strict';
import {chartDateRange,presetRange} from '../../src/reptrace/web/static/model.mjs';
const start=Date.parse('2026-10-01'),end=Date.parse('2026-10-11');
test('date selection supports reverse drags and clamps to plot bounds',()=>{
 assert.deepEqual(chartDateRange(start,end,40,840,200,680),{from:'2026-10-03',to:'2026-10-09'});
 assert.deepEqual(chartDateRange(start,end,40,840,680,200),{from:'2026-10-03',to:'2026-10-09'});
 assert.deepEqual(chartDateRange(start,end,40,840,-100,1000),{from:'2026-10-01',to:'2026-10-11'});
});
test('date selection preserves same-day ranges and rejects malformed geometry',()=>{
 assert.deepEqual(chartDateRange(start,start,40,840,100,200),{from:'2026-10-01',to:'2026-10-01'});
 assert.equal(chartDateRange(start,end,40,40,100,200),null);
 assert.equal(chartDateRange(start,end,40,840,NaN,200),null);
});
test('weekly plot right edge includes Sunday without adding the next Monday',()=>{
 assert.deepEqual(chartDateRange(Date.parse('2026-10-05'),Date.parse('2026-10-19')-1,0,100,0,100),{from:'2026-10-05',to:'2026-10-18'});
});

test('one and two week shortcuts include today',()=>{
 assert.deepEqual(presetRange('7','2026-10-22'),{from:'2026-10-16',to:'2026-10-22'});
 assert.deepEqual(presetRange('14','2026-10-22'),{from:'2026-10-09',to:'2026-10-22'});
});
