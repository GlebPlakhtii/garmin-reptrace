import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
test('nutrition page totals the selected day and escapes food names',()=>{
  const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+
    `\nstate.data={timezone:'Europe/Kyiv',workouts:[],recovery:[{date:'2026-10-23',activeCalories:510,restingCalories:1650,totalCalories:2160,bodyWeightKg:72.5}],foodLog:[
      {id:'123e4567-e89b-12d3-a456-426614174000',time:'2026-10-23T09:00:00Z',name:'Banana <ripe>',items:[{name:'Banana',portion:'3 medium'}],calories:315,protein_g:3.9,carbs_g:81,fat_g:1.2,note:'Estimated size'},
      {time:'2026-10-21T09:00:00Z',name:'Older',items:[],calories:100,protein_g:1,carbs_g:20,fat_g:1,note:''}]};
     state.page='nutrition';state.nutritionDate='2026-10-23';state.range='all';this.html=nutritionPage();`,context);
  assert.match(context.html,/315 <small>kcal/);
  assert.match(context.html,/id="nutrition-date" value="2026-10-23"/);
  assert.doesNotMatch(context.html,/All history|Apply dates/);
  assert.match(context.html,/data-nutrition-day="2026-10-21"/);
  assert.match(context.html,/Banana &lt;ripe&gt;/);
  assert.doesNotMatch(context.html,/Older/);
  assert.match(context.html,/P 3\.9 · C 81 · F 1\.2 g/);
  assert.match(context.html,/Food and Garmin calorie burn/);
  assert.match(context.html,/2,160 <small>kcal/);
  assert.match(context.html,/72\.5 kg/);
  assert.match(context.html,/data-action="food-delete"/);
  vm.runInContext("state.foodDeleteId='123e4567-e89b-12d3-a456-426614174000';this.confirmHtml=nutritionPage();",context);
  assert.match(context.confirmHtml,/Delete this entry\?/);
  assert.match(context.confirmHtml,/data-action="food-delete-confirm"/);
  assert.match(context.confirmHtml,/data-action="food-delete-cancel"/);
});

test('sync page separates watch upload, collector poll and source samples',()=>{
  const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+
    `\nstate.data={timezone:'Europe/Kyiv',refreshedAt:'2026-10-23T10:00:00Z',sets:[],workouts:[],sync:{watchUploadAt:'2026-10-23T07:00:00Z',deviceName:'My Watch',collectorPollAt:'2026-10-23T09:00:00Z',collectorResult:'no_new_data',sources:{'Daily health':'2026-10-22T00:00:00Z','Body weight':null}}};this.html=syncPage();`,context);
  assert.match(context.html,/Watch upload/);
  assert.match(context.html,/Collector check/);
  assert.match(context.html,/No new watch upload/);
  assert.match(context.html,/Daily health/);
  assert.match(context.html,/Body weight/);
  assert.match(context.html,/No data/);
});

test('nutrition defaults to local today and isolates macros from historical range',()=>{
  const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+
    `\ntoday=()=>localDay('2026-10-23T22:30:00Z');
     state.page='nutrition';state.range='custom';state.from='2026-10-21';state.to='2026-10-23';
     state.data={timezone:'Europe/Kyiv',workouts:[],recovery:[],foodLog:[
       {time:'2026-10-23T22:30:00Z',name:'Local today',calories:500,protein_g:40,carbs_g:50,fat_g:10},
       {time:'2026-10-24T09:00:00Z',name:'Second meal',calories:200,protein_g:10,carbs_g:20,fat_g:5},
       {time:'2026-10-23T09:00:00Z',name:'Yesterday meal',calories:1200,protein_g:100,carbs_g:120,fat_g:30}]};
     this.html=nutritionPage();`,context);
  assert.match(context.html,/id="nutrition-date" value="2026-10-24"/);
  assert.match(context.html,/700 <small>kcal/);
  assert.match(context.html,/50 <small>g/);
  assert.doesNotMatch(context.html,/Yesterday meal/);
  assert.match(context.html,/Local today/);
  vm.runInContext("state.nutritionDate='2026-10-23';this.selectedHtml=nutritionPage();",context);
  assert.match(context.selectedHtml,/1,200 <small>kcal/);
  assert.match(context.selectedHtml,/100 <small>g/);
  assert.match(context.selectedHtml,/Yesterday meal/);
  assert.doesNotMatch(context.selectedHtml,/Local today|Second meal/);
  vm.runInContext("state.nutritionDate='2026-10-22';this.emptyHtml=nutritionPage();",context);
  assert.match(context.emptyHtml,/— <small>kcal/);
  assert.match(context.emptyHtml,/Missing intake is not zero intake/);
  assert.match(context.emptyHtml,/No entries to show/);
  assert.doesNotMatch(context.emptyHtml,/Yesterday meal|Local today/);
});

function comparison(entries,reading={}) {
  const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout,entries,reading};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`\nthis.html=nutritionComparison('2026-10-23',entries,reading);`,context);
  return context.html;
}

test('daily calorie comparison shares a scale and preserves zero readings',()=>{
  const html=comparison([{calories:1200},{calories:600}],{totalCalories:2400,activeCalories:600,restingCalories:1800,bodyWeightKg:72.5});
  assert.match(html,/data-point-value="1800" style="width:75%"/);
  assert.match(html,/data-point-value="2400" style="width:100%"/);
  assert.match(html,/2 approved entries/);
  assert.match(html,/Active calories<\/dt><dd>600 kcal/);
  assert.match(html,/Resting calories<\/dt><dd>1,800 kcal/);
  const zero=comparison([{calories:0}],{totalCalories:0,activeCalories:0,restingCalories:0});
  assert.equal((zero.match(/data-point-value="0" style="width:0%"/g)||[]).length,2);
  assert.doesNotMatch(zero,/Not recorded|is-missing|NaN|Infinity/);
});

test('missing intake and partial Garmin readings never become zero or a daily total',()=>{
  const html=comparison([],{activeCalories:480,bodyWeightKg:78});
  assert.equal((html.match(/class="calorie-track is-missing"/g)||[]).length,2);
  assert.match(html,/No food logged/);
  assert.match(html,/Waiting for a complete daily burn reading/);
  assert.match(html,/Active calories<\/dt><dd>480 kcal/);
  assert.match(html,/Resting calories<\/dt><dd>—/);
  assert.doesNotMatch(html,/data-point-value=|NaN|Infinity/);
  const foodOnly=comparison([{calories:450}]);
  assert.match(foodOnly,/data-point-value="450" style="width:100%"/);
  assert.match(foodOnly,/No Garmin calorie reading/);
});
