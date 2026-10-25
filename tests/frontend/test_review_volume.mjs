import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
import {renderMuscleMap} from '../../src/reptrace/web/static/muscle-map.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
test('muscle-map comparison applies identical volume settings outside the selected date range',()=>{
  let rendered;
  const context={...model,renderMuscleMap:value=>{rendered=value;return renderMuscleMap(value);},document:{},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\ntoday=()=> '2026-10-25';this.app={state,current,weeklyMuscleMap};`,context);
  const a=context.app;
  const set=(date,id)=>({date,id,sessionId:id,time:date+'T09:00:00Z',exercise:'Leg Press',weight:100,reps:10,volume:1000,source:'garmin'});
  a.state.data={sets:[set('2026-10-14','old'),set('2026-10-21','new')],workouts:[],recovery:[],volumeSettings:{exercises:{'Leg Press':{multiplier:.5,loadCopies:1,bodyweight:0}}}};
  // Include an earlier history start so the previous full week is available.
  a.state.data.sets.unshift({...set('2026-10-01','start'),exercise:'Pull Up'});
  Object.assign(a.state,{range:'custom',from:'2026-10-19',to:'2026-10-25',mapMuscle:'Glutes'});
  const html=a.weeklyMuscleMap(a.current());
  const current=rendered.summary.groups.find(g=>g.name==='Glutes'),baseline=rendered.comparison.groups.find(g=>g.name==='Glutes');
  assert.equal(current.volume,500);assert.equal(baseline.volume,500);
  assert.match(html,/Adjusted volume · kg·reps/);
  assert.doesNotMatch(html,/>-500 less</);
});
