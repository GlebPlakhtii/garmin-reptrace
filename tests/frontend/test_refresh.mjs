import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(fetch){
  const elements=new Map();
  const element=key=>{
    if(!elements.has(key))elements.set(key,{classList:{add(){},remove(){}},textContent:'',innerHTML:'',disabled:false});
    return elements.get(key);
  };
  const context={...model,fetch,AbortSignal,setTimeout,clearTimeout,document:{querySelector:element,body:element('body')},window:{}};
  vm.createContext(context);
  const code=source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"));
  vm.runInContext(code+"\nrender=()=>{};toast=()=>{};this.app={state,load,nav};",context);
  return {...context.app,element};
}
test('failed refresh retains loaded history and unlocks refresh control',async()=>{
  const a=app(async(_url,options)=>{assert.ok(options.signal);throw new Error('offline');});
  const data={sets:[],workouts:[]};a.state.data=data;
  await a.load();
  assert.equal(a.state.data,data);
  assert.equal(a.state.refreshError,true);
  assert.equal(a.element('#refresh').disabled,false);
  assert.equal(a.element('#sync-status').textContent,'Connection unavailable');
});
test('older refresh responses cannot replace newer history',async()=>{
  const pending=[];
  const a=app(()=>new Promise(resolve=>pending.push(resolve)));
  const first=a.load(true),second=a.load(true);
  const newest={sets:[],workouts:[],refreshedAt:'new'};
  pending[1]({ok:true,json:async()=>newest});await second;
  pending[0]({ok:true,json:async()=>({sets:[],workouts:[],refreshedAt:'old'})});await first;
  assert.equal(a.state.data.refreshedAt,'new');
  assert.equal(a.element('#refresh').disabled,false);
});
test('collapsed navigation keeps accessible labels',()=>{
  const a=app();a.nav();
  assert.match(a.element('#navigation').innerHTML,/aria-label="Overview"/);
  assert.match(a.element('#navigation').innerHTML,/aria-label="Log & edit"/);
});
