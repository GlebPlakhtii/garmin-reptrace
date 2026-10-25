import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
const code=source.slice(source.indexOf('function recoveryChart('),source.indexOf('function sleepStages('));
const context={present:v=>typeof v==='number'&&Number.isFinite(v),number:(v,n=0)=>Number(v).toFixed(n),date:d=>d,escape:s=>String(s)};
vm.createContext(context);vm.runInContext(code+'\nthis.chart=recoveryChart;',context);
test('weight chart distinguishes small changes in kg without NaN or invented missing values',()=>{
 const output=context.chart([{date:'2026-10-19',bodyWeightKg:73.1},{date:'2026-10-20'},{date:'2026-10-21',bodyWeightKg:72.9}],{key:'bodyWeightKg',label:'Body weight',unit:'kg',color:'#e4ac63'});
 assert.doesNotMatch(output,/NaN|undefined/);assert.match(output,/73\.10 kg/);assert.match(output,/72\.90 kg/);
 assert.equal((output.match(/class="chart-point/g)||[]).length,2);
});
test('sleep charts still render with their existing zero baseline and missing values',()=>{
 const output=context.chart([{date:'2026-10-20',sleepHours:7.2},{date:'2026-10-21',sleepHours:null}],{key:'sleepHours',label:'Sleep',unit:'hours',color:'#aaa'});
 assert.doesNotMatch(output,/NaN|undefined/);assert.match(output,/7\.20 h/);
});
test('empty weight history has an explicit empty state',()=>{
 assert.match(context.chart([{date:'2026-10-21'}],{key:'bodyWeightKg',label:'Body weight',unit:'kg'}),/No readings/);
});
