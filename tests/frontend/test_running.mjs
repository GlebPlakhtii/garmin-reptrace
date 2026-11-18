import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
import * as running from '../../src/reptrace/web/static/running.mjs';
import {renderRunningDashboard,runningState} from '../../src/reptrace/web/static/running-view.mjs';

const runs=[
  {id:'1',date:'2026-11-01',time:'2026-11-01T09:00:00Z',name:'<test>',type:'running',distanceKm:5,movingSeconds:1500,elapsedSeconds:1800},
  {id:'2',date:'2026-11-03',time:'2026-11-03T09:00:00Z',name:'Trail',type:'trail_running',distanceKm:10,movingSeconds:3600},
  {id:'3',date:'2026-11-05',time:'2026-11-05T09:00:00Z',name:'Missing',type:'running',distanceKm:2,movingSeconds:null},
];
test('pace uses distance-weighted paired moving records; elapsed time is not substituted',()=>{
  assert.deepEqual(running.runningSummary(runs),{count:3,distance:17,moving:5100,pace:340,distanceCount:3,movingCount:2,paceCount:2});
  assert.equal(running.runPace(runs[0]),300);
  assert.equal(running.runPace(runs[2]),null);
  assert.equal(running.runPace({distanceKm:0,movingSeconds:30}),null);
  assert.equal(running.runPace({distanceKm:5,movingSeconds:0}),null);
});
test('missing measurements stay missing and zero distance is retained',()=>{
  assert.equal(running.runningSummary([{distanceKm:null,movingSeconds:null}]).distance,null);
  assert.equal(running.runningSummary([{distanceKm:0,movingSeconds:0}]).distance,0);
  assert.equal(running.runningSummary([]).pace,null);
  assert.equal(running.paceLabel(null),'—');
  assert.equal(running.paceLabel(359.9),'6:00');
  assert.equal(running.runningTime(3601),'1:00:01');
  assert.equal(running.runningTime(59.9),'1:00');
  assert.equal(running.runningTime(null),'—');
});
test('date filters are inclusive, newest first, and do not mutate input',()=>{
  assert.deepEqual(running.runningHistory(runs,{from:'2026-11-03',to:'2026-11-05'}).map(r=>r.id),['3','2']);
  assert.equal(runs[0].id,'1');
  assert.deepEqual(running.runningWeeks(runs).map(w=>[w.date,w.distance]),[['2026-10-26',5],['2026-11-02',12]]);
});
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function render(records,range='all') {
  runningState.view='runs';runningState.tab='overview';runningState.type='all';runningState.search='';runningState.details.clear();
  const context={...model,...running,renderRunningDashboard,records,selectedRange:range,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+
    '\ntoday=()=>"2026-11-11";state.page="running";state.range=selectedRange;state.data={runs:records,workouts:[],timezone:"UTC"};this.html=runningPage();',context);
  return context.html;
}
test('running page escapes names, labels pace and uses running dates without strength controls',()=>{
  const html=render(runs);
  assert.match(html,/Activity log/);
  assert.match(html,/data-run-view="progress"/);
  assert.doesNotMatch(html,/Weekly distance/);
  assert.match(html,/&lt;test&gt;/);
  assert.match(html,/Running date range/);
  assert.doesNotMatch(html,/<select\b|<option\b/);
  assert.doesNotMatch(html,/id="source-filter"|data-action="export"/);
});
test('empty and filtered states offer relevant next steps',()=>{
  assert.match(render([]),/Check Garmin sync/);
  assert.match(render(runs.slice(0,2),'7'),/Reset running filters/);
});

test('chart gaps, resets and pauses are not joined by invented measurements',()=>{
  const rows=[{seconds:0,pace:300},{seconds:5,pace:null},{seconds:10,pace:310},{seconds:100,pace:320},{seconds:99,pace:330}];
  assert.deepEqual(running.chartSegments(rows,'pace').map(s=>s.length),[1,1,1,1]);
});
test('CSV preserves raw units, quotes names and prevents spreadsheet formulas',()=>{
  const csv=running.runningCSV([{date:'2026-11-01',name:'=1+1',type:'running',movingSeconds:1500}], [{key:'movingSeconds',label:'Moving time',unit:'time'}]);
  assert.match(csv,/Moving time \(seconds\)/);
  assert.match(csv,/"'=1\+1"/);
  assert.match(csv,/"1500"/);
  const signed=running.runningCSV([{name:'  =example',averageTemperature:-4.5}], [{key:'averageTemperature',label:'Temperature'}]);
  assert.match(signed,/"'  =example"/);
  assert.match(signed,/"-4\.5"/);
});
test('comparison respects missing values and the sign of pace improvement',()=>{
  const rows=running.compareRunning({pace:350},{pace:320,hr:140},[{key:'pace'},{key:'hr'}]);
  assert.equal(rows[0].change,-30);assert.equal(rows[1].change,null);
});
test('complete detail renders zones, dynamics, time-series, laps and comparison',()=>{
  runningState.view='runs';runningState.tab='overview';runningState.type='all';runningState.search='';runningState.selected='1';runningState.details.clear();
  runningState.details.set('1',{summary:{...runs[0],primaryBenefit:'<Base>',averagePace:300,cadence:174,strideLengthM:1.1,groundContactMs:245,aerobicEffect:3.4,averagePower:260},
    samples:[{seconds:0,distanceKm:0,pace:300,heartRate:140,cadence:174},{seconds:30,distanceKm:.1,pace:310,heartRate:145,cadence:176}],
    laps:[{index:1,intensity:'Active',distanceKm:1,averagePace:300,averageHR:145}],
    zones:[{zone:1,seconds:60,lowBpm:100},{zone:2,seconds:0,lowBpm:120}],notes:['Synthetic note'],syncedAt:'2026-11-01T12:00:00Z'});
  const overview=renderRunningDashboard(runs,{});
  assert.doesNotMatch(overview,/<Base>/);
  assert.match(overview,/&lt;Base&gt;/);
  assert.match(overview,/Training impact/);assert.match(overview,/Heart-rate zones/);
  assert.doesNotMatch(overview,/Inside the run|run-laps|run-comparison-picker/);
  for(const [tab,label] of [['charts','Inside the run'],['metrics','Running dynamics'],['laps','Laps & intervals'],['compare','Compare runs']]){
    runningState.tab=tab;
    const html=renderRunningDashboard(runs,{});
    assert.ok(html.includes(label),label);
    assert.doesNotMatch(html,/<select\b|<option\b|<test>/);
    assert.match(html,/&lt;test&gt;/);
    if(tab==='charts'){assert.match(html,/data-run-sample/);assert.match(html,/data-run-axis="distanceKm"/);}
    if(tab==='metrics')assert.match(html,/1.1 m/);
  }
  runningState.view='progress';
  const progress=renderRunningDashboard(runs,{});
  assert.match(progress,/Weekly distance/);assert.match(progress,/Progress over time/);
  assert.doesNotMatch(progress,/<select\b|run-analysis-tabs/);
  runningState.details.clear();runningState.view='runs';runningState.tab='overview';
});

test('running trend uses elapsed calendar time and breaks at a missing observation',()=>{
  Object.assign(runningState,{view:'progress',trend:'averageHR',type:'all',search:''});
  runningState.details.clear();
  const dates=['2026-03-01','2026-03-02','2026-03-05','2026-03-11'];
  const records=dates.map((date,i)=>({id:String(i),name:'Run '+i,type:'running',date,time:date+'T12:00:00Z',averageHR:[135,140,null,150][i]}));
  const html=renderRunningDashboard(records,{});
  const cx=[...html.matchAll(/<circle cx="([^"]+)"/g)].map(match=>Number(match[1]));
  assert.deepEqual(cx,[45,110,695]);
  const path=html.match(/<path d="([^"]+)" class="run-trend-line"/)[1];
  assert.equal((path.match(/M/g)||[]).length,2);
  assert.match(html,/3 of 4 runs recorded/);
});

test('a long track can display isolated readings and keep its last raw sample inspectable',()=>{
  Object.assign(runningState,{selected:'1',view:'runs',tab:'charts',metric:'heartRate',axis:'seconds',type:'all',search:'',sampleIndex:139999});
  const samples=Array.from({length:140000},(_,i)=>({seconds:i,heartRate:i===1?null:i===0?133:140}));
  runningState.details.set('1',{summary:runs[0],samples,laps:[],zones:[],notes:[]});
  try {
    const html=renderRunningDashboard(runs,{});
    assert.match(html,/<circle class="run-series series-heartRate"/);
    assert.match(html,/max="139999" value="139999"/);
    assert.doesNotMatch(html,/NaN|Infinity/);
  } finally {runningState.details.clear();runningState.sampleIndex=0;}
});

test('dense chart reduces display points while preserving a single spike, trough and endpoints in order',()=>{
  const samples=Array.from({length:10000},(_,i)=>({seconds:i,heartRate:140}));
  samples[105].heartRate=190;
  samples[107].heartRate=92;
  const display=running.plotSamples(samples,'heartRate','seconds',0,9999,50);
  assert.ok(display.length<=104);
  assert.equal(display[0],samples[0]);
  assert.equal(display.at(-1),samples.at(-1));
  assert.ok(display.includes(samples[105])&&display.includes(samples[107]));
  assert.ok(display.every((p,i)=>i===0||p.seconds>display[i-1].seconds));
  assert.equal(samples.length,10000);
});
