import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as model from '../../src/reptrace/web/static/model.mjs';
const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function page(data){
  const context={...model,document:{querySelector:()=>({})},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+'\nthis.app={state,equipmentPanel};',context);
  context.app.state.data=data;return context.app.equipmentPanel();
}
test('equipment editor handles first-use empty inventory',()=>{
  const html=page({sets:[],metadataRevision:'first'});
  assert.match(html,/Add equipment profile/);assert.match(html,/first workout/);
});
test('equipment editor restores assignments and escapes profile and exercise names',()=>{
  const html=page({sets:[{exercise:'Curl <test>'}],metadataRevision:'token',equipment:{profiles:{rack:{name:'Rack <test>',loads:[10,12.5]}},assignments:{'Curl <test>':'rack'}}});
  assert.match(html,/Rack &lt;test&gt;/);assert.match(html,/Curl &lt;test&gt;/);
  assert.match(html,/value="rack" selected/);assert.match(html,/10, 12.5/);
  assert.doesNotMatch(html,/<test>/);
});
