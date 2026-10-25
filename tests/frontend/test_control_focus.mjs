import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');

function app(tagName,attributes,{navigation=false,disabled=false}={}) {
  let controls=[];
  const document={body:{},querySelectorAll:selector=>controls.filter(node=>node.tagName===selector)};
  function control() {
    return {tagName,attributes:Object.entries(attributes).map(([name,value])=>({name,value})),
      isConnected:true,disabled,getAttribute:name=>attributes[name]??null,
      focus(options){document.activeElement=this;this.focusOptions=options;}};
  }
  const original=control();controls=[original];document.activeElement=original;
  function replace() {
    original.isConnected=false;
    controls=[control()];document.activeElement=document.body;
  }
  const nodes=new Map([
    ['#main',{set innerHTML(_value){if(!navigation)replace();}}],
    ['#footer-source',{}],['#sync-status',{}],
  ]);
  document.querySelector=selector=>nodes.get(selector);
  const context={document,window:{},replaceNavigation:()=>{if(navigation)replace();}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`
    nav=replaceNavigation;
    current=()=>({}); overview=()=>'<button>Updated view</button>'; bindChart=()=>{};
    state.data={sets:[],workouts:[],timezone:'UTC',refreshedAt:'2026-10-25T12:00:00Z'};
    this.render=render;
  `,context);
  return {render:context.render,document,original,replacement:()=>controls[0]};
}

test('filter redraw keeps keyboard focus on the same date preset',()=>{
  const a=app('BUTTON',{'data-range':'90'});
  a.render();
  assert.notEqual(a.document.activeElement,a.original);
  assert.equal(a.document.activeElement,a.replacement());
  assert.equal(a.document.activeElement.getAttribute('data-range'),'90');
  assert.equal(a.document.activeElement.focusOptions.preventScroll,true);
});

test('redrawing navigation retains the activated link rather than losing focus to the body',()=>{
  const a=app('A',{href:'#exercises'},{navigation:true});
  a.render();
  assert.equal(a.document.activeElement,a.replacement());
});

test('redrawing a select preserves its focus; disabled replacements are not focused',()=>{
  const select=app('SELECT',{id:'source-filter'});
  select.render();
  assert.equal(select.document.activeElement,select.replacement());
  const disabled=app('BUTTON',{'data-action':'save'},{disabled:true});
  disabled.render();
  assert.equal(disabled.document.activeElement,disabled.document.body);
});
