import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(saved=null,blocked=false){
 const values=new Map(saved?[['form-overview-layout',saved]]:[]);
 const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout,localStorage:{getItem:key=>{if(blocked)throw Error();return values.get(key)},setItem:(key,value)=>{if(blocked)throw Error();values.set(key,value)}}};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\nthis.api={state,overview,overviewLayout,saveOverviewLayout,overviewControls,workoutCalendar,shiftCalendar,current};toast=()=>{};`,context);
 const a=context.api;a.state.data={sets:[],workouts:[],recovery:[],timezone:'Europe/Kyiv'};a.state.calendarMonth='2024-02';return {...a,values};
}
test('saved overview order is sanitized and hidden sections survive reload',()=>{
 const a=app(JSON.stringify({order:['calendar','exercises','calendar','bogus'],hidden:['signals','exercises','signals','bogus']}));
 assert.equal(a.overviewLayout().order[0],'calendar');assert.equal(a.overviewLayout().order.length,6);
 assert.deepEqual([...a.overviewLayout().hidden],[]);
 a.overviewLayout().hidden.push('summary');a.saveOverviewLayout();
 const b=app(a.values.get('form-overview-layout'));assert.deepEqual([...b.overviewLayout().hidden],['summary']);
 const html=b.overview(b.current());assert.doesNotMatch(html,/data-overview-section="signals"|data-overview-section="summary"/);
 assert.match(html,/data-overview-section="calendar"/);
 assert.doesNotMatch(html,/data-overview-section="exercises"|exercise-library|exercise-detail/);
 assert.doesNotMatch(b.overviewControls(),/Exercise progress|Training signals/);
});
test('invalid or unavailable storage still provides defaults and usable controls',()=>{
 for(const a of [app('broken'),app(null,true)]){assert.equal(a.overviewLayout().order.length,6);a.saveOverviewLayout();assert.match(a.overviewControls(),/Restore default layout/);}
});
test('hidden overview keeps an accessible path to restore sections',()=>{
 const a=app();a.overviewLayout().hidden=[...a.overviewLayout().order];const html=a.overview(a.current());
 assert.match(html,/Your overview is clear/);assert.match(html,/href="#preferences"/);assert.doesNotMatch(html,/data-overview-section=/);
});
test('calendar handles leap years and year transitions',()=>{
 const a=app();const html=a.workoutCalendar(a.current());
 assert.equal((html.match(/data-calendar-day=/g)||[]).length,29);
 assert.match(html,/data-calendar-day="2024-02-29"/);
 assert.equal(a.shiftCalendar('2024-01',-1),'2023-12');assert.equal(a.shiftCalendar('2024-12',1),'2025-01');
});
test('calendar shows multiple sessions and respects date and source filters',()=>{
 const a=app();a.state.range='custom';a.state.from='2024-02-01';a.state.to='2024-02-28';a.state.calendarDay='2024-02-12';
 a.state.data.workouts=[{id:'one',name:'Upper <1>',date:'2024-02-12',source:'garmin'},{id:'two',name:'Lower',date:'2024-02-12',source:'manual'},{id:'out',name:'Outside',date:'2024-02-29',source:'garmin'}];
 a.state.data.sets=[{sessionId:'one',exercise:'Row',date:'2024-02-12',source:'garmin',reps:5,weight:10}];
 let html=a.workoutCalendar(a.current());assert.match(html,/2 workouts · 1 training days/);assert.match(html,/data-session="one"/);assert.match(html,/data-session="two"/);assert.match(html,/Upper &lt;1&gt;/);assert.doesNotMatch(html,/Outside/);
 a.state.source='garmin';html=a.workoutCalendar(a.current());assert.match(html,/1 workouts · 1 training days/);assert.doesNotMatch(html,/data-session="two"/);
});
