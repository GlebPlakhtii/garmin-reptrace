import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app() {
  const context={...model,document:{},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\ntoday=()=> '2026-11-11';this.api={state,current,weeklyPanel};`,context);
  const a=context.api;
  const workouts=[
    {id:'outside',date:'2026-08-23'},
    {id:'first',date:'2026-08-24'},
    {id:'older',date:'2026-10-19'},
    {id:'boundary',date:'2026-10-26'},
    {id:'recent',date:'2026-11-02'},
    {id:'current',date:'2026-11-11'},
    {id:'future',date:'2026-11-12'},
  ];
  const sets=workouts.map(w=>({sessionId:w.id,date:w.date,source:w.id==='older'?'manual':'garmin',exercise:'Leg Press',weight:100,reps:5}));
  // Mixed-source workouts count once, and source membership comes from their sets.
  sets.push({...sets.find(s=>s.sessionId==='recent'),source:'manual'});
  a.state.data={workouts,sets,recovery:[]};
  return a;
}
function counts(a) {
  return [...a.weeklyPanel(a.current()).matchAll(/data-point-value="(\d+)"/g)].map(m=>Number(m[1]));
}

test('12-week consistency retains older and boundary-week workouts across page date filters',()=>{
  const a=app();
  const expected=[1,0,0,0,0,0,0,0,1,1,1,1];
  a.state.range='14';
  assert.deepEqual(a.current().workouts.map(w=>w.id),['recent','current']);
  assert.deepEqual(counts(a),expected);
  for(const preset of ['7','30','90','all']){
    a.state.range=preset;
    assert.deepEqual(counts(a),expected,preset);
  }
  Object.assign(a.state,{range:'custom',from:'2026-01-01',to:'2026-01-02'});
  assert.equal(a.current().workouts.length,0);
  assert.deepEqual(counts(a),expected);
  assert.match(a.weeklyPanel(),/independent of the date filter/);
});

test('12-week consistency respects source filters and counts mixed workouts once',()=>{
  const a=app();a.state.range='14';
  a.state.source='manual';
  assert.deepEqual(counts(a),[0,0,0,0,0,0,0,0,1,0,1,0]);
  a.state.source='garmin';
  assert.deepEqual(counts(a),[1,0,0,0,0,0,0,0,0,1,1,1]);
});

test('empty consistency history keeps twelve genuine zero-count weeks',()=>{
  const a=app();a.state.data={workouts:[],sets:[],recovery:[]};
  assert.deepEqual(counts(a),Array(12).fill(0));
  assert.doesNotMatch(a.weeklyPanel(),/NaN|undefined/);
});

test('consistency bars split weekly totals between strength and running',()=>{
  const a=app();
  a.state.data.runs=[
    {date:'2026-08-31'},{date:'2026-11-02'},{date:'2026-11-08'},
    {date:'2026-11-11'},{date:'2026-11-12'},
  ];
  function bars() {
    return [...a.weeklyPanel().matchAll(/data-point-value="(\d+)" style="height:[^;]+;--strength-share:([\d.]+)%"/g)]
      .map(([,total,share])=>[Number(total),Number(share)]);
  }
  const weeks=bars();
  assert.deepEqual(weeks[0],[1,100]);
  assert.deepEqual(weeks[1],[1,0]);
  assert.deepEqual(weeks[2],[0,0]);
  assert.deepEqual(weeks[10],[3,100/3]);
  assert.deepEqual(weeks[11],[2,50]);
  assert.match(a.weeklyPanel(),/1 strength session · 2 runs/);
  assert.match(a.weeklyPanel(),/class="strength"><\/i>Strength.*class="running"><\/i>Running/);
  a.state.source='manual';
  assert.deepEqual(bars()[10],[1,100]);
  assert.deepEqual(bars()[11],[0,0]);
});
