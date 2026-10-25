import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {renderMuscleMap} from '../../src/reptrace/web/static/muscle-map.mjs';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(){
 const code=source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"));
 const context={...model,renderMuscleMap,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
 vm.createContext(context);vm.runInContext(code+'\nthis.app={state,current,volumePage};',context);
 const data={timezone:'Europe/Kyiv',muscleOverrides:{},workouts:[{id:'a',name:'Upper 1',date:'2026-10-20',time:'2026-10-20T10:00:00Z',source:'garmin'}],sets:[{id:'a:1',sessionId:'a',date:'2026-10-20',time:'2026-10-20T10:00:00Z',exercise:'Barbell Bench Press',weight:80,reps:6,volume:480,source:'garmin'},{id:'a:2',sessionId:'a',date:'2026-10-20',time:'2026-10-20T10:00:01Z',exercise:'Pull Up',weight:0,reps:8,volume:0,source:'garmin'}],recovery:[]};
 context.app.state.data=data;return context.app;
}
for(const mode of ['muscle','exercise'])for(const metric of ['volume','sets','reps']){
 test(`Weekly volume page renders ${mode}/${metric} without chart exceptions`,()=>{
  const a=app();a.state.volumeMode=mode;a.state.volumeMetric=metric;
  const output=a.volumePage(a.current());
  assert.match(output,/Historical weekly trends/);assert.match(output,/volume-history-svg/);
  assert.doesNotMatch(output,/NaN|undefined/);
 });
}
