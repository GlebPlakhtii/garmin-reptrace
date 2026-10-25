import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function render(training,recovery=[]){
  const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+
    '\nstate.data={timezone:"Europe/Kyiv",training:signals,recovery:daily};state.range="all";this.html=trainingSignals();',
    Object.assign(context,{signals:training,daily:recovery}));
  return context.html;
}

test('training signals shows dated Garmin readiness, status, load and latest Body Battery',()=>{
  const html=render({
    readiness:[{date:'2026-10-23',time:'2026-10-23T06:50:35Z',score:64,level:'Moderate'}],
    status:[{date:'2026-10-23',time:'2026-10-23T06:50:34Z',label:'Maintaining',acuteLoad:228,chronicLoad:216,loadRatio:1}],
    bodyBatteryLatest:{date:'2026-10-23',time:'2026-10-23T09:27:00Z',level:83},
  },[{date:'2026-10-23',bodyBattery:82,bodyBatteryCharged:55,bodyBatteryDrained:17}]);
  assert.match(html,/Training readiness/);assert.match(html,/64 <small>\/100/);
  assert.match(html,/Maintaining/);assert.match(html,/Acute 228 · chronic 216/);
  assert.match(html,/Latest Body Battery/);assert.match(html,/Charged \+55/);
  assert.match(html,/23 Oct 2026/);
  assert.match(html,/class="readiness-bar steady"/);
  assert.match(html,/class="battery-mini"/);
  assert.match(html,/class="training-signal-card signal-info" data-signal="ratio"/);
});

test('load chart draws Garmin optimal range with acute and chronic trends',()=>{
  const html=render({readiness:[],bodyBatteryLatest:null,status:[
    {date:'2026-10-22',time:'2026-10-22T06:00:00Z',label:'Maintaining',acuteLoad:210,chronicLoad:215,loadRatio:.98,optimalMin:170,optimalMax:320},
    {date:'2026-10-23',time:'2026-10-23T06:00:00Z',label:'Maintaining',acuteLoad:228,chronicLoad:216,loadRatio:1,optimalMin:173,optimalMax:324},
  ]});
  assert.match(html,/class="load-optimal"/);
  assert.match(html,/class="load-acute"/);
  assert.match(html,/class="load-chronic"/);
  assert.match(html,/Garmin optimal range/);
});

test('missing Garmin signals stay absent rather than showing invented scores',()=>{
  const html=render({status:[],readiness:[],bodyBatteryLatest:null});
  assert.match(html,/No score recorded/);assert.match(html,/No status recorded/);
  assert.match(html,/No recent sample/);assert.doesNotMatch(html,/0 <small>\/100/);
});
