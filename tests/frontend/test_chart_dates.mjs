import test from 'node:test';
import assert from 'node:assert/strict';
import {timeAxisDates} from '../../src/reptrace/web/static/model.mjs';
test('ticks span time evenly rather than clustered workout indices',()=>{
 const dates=timeAxisDates('2026-08-07','2026-10-20');
 assert.equal(dates[0],'2026-08-07');assert.equal(dates.at(-1),'2026-10-20');
 for(let i=1;i<dates.length;i++)assert.ok((Date.parse(dates[i])-Date.parse(dates[i-1]))/86400000>=24);
});
test('single-day and short ranges never duplicate date labels',()=>{
 assert.deepEqual(timeAxisDates('2026-08-07','2026-08-07'),['2026-08-07']);
 assert.deepEqual(timeAxisDates('2026-08-07','2026-08-08'),['2026-08-07','2026-08-08']);
 assert.deepEqual(timeAxisDates('invalid','2026-08-08'),[]);
});
