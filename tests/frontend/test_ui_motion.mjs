import test from 'node:test';
import assert from 'node:assert/strict';
import {surfaceSignature, changedSurfaces, installUiMotion} from '../../src/reptrace/web/static/ui-motion.mjs';

test('selection and animation bookkeeping do not replay unchanged content', () => {
  const before='<button class="filter active" aria-pressed="true" tabindex="0" style="opacity:.7">Chest</button>';
  const after='<button class="filter" aria-pressed="false" tabindex="-1" style="opacity:1">Chest</button>';
  assert.equal(surfaceSignature(before),surfaceSignature(after));
  assert.notEqual(surfaceSignature(before,true),surfaceSignature(after,true));
  assert.notEqual(surfaceSignature('<strong>12 sets</strong>'),surfaceSignature('<strong>15 sets</strong>'));
  const previous=new Map([['chart',{signature:surfaceSignature(before)}]]);
  const same={key:'chart',signature:surfaceSignature(after),visible:true};
  assert.deepEqual(changedSurfaces(previous,[same]),[]);
  assert.deepEqual(changedSurfaces(previous,[same],{routeChanged:true}),[same]);
  assert.deepEqual(changedSurfaces(previous,[{...same,visible:false}],{routeChanged:true}),[]);
  assert.deepEqual(changedSurfaces(previous,[same],{routeChanged:true,suppressed:true}),[]);
});

function fixture() {
  const animations=[],listeners=new Map(),preferenceListeners=new Map();
  let mutation,panels=[],dialogs=[],details=[],controls=[];
  const add=(map,name,fn)=>{if(!map.has(name))map.set(name,new Set());map.get(name).add(fn);};
  const preference={matches:false,addEventListener:(name,fn)=>add(preferenceListeners,name,fn),removeEventListener:(name,fn)=>preferenceListeners.get(name)?.delete(fn)};
  const node=(id,html='',tagName='SECTION')=>({
    id,tagName,nodeType:1,isConnected:true,innerHTML:html,open:false,
    attributes:[],classList:Object.assign(new Set(),{contains(name){return this.has(name);}}),
    parentElement:null,children:[],namespaceURI:'http://www.w3.org/1999/xhtml',
    rect:{top:20,bottom:140,left:20,right:320,width:300,height:120},
    matches(){return false;},closest(){return null;},querySelector(){return null;},querySelectorAll(){return [];},contains(other){return this===other;},
    getBoundingClientRect(){return this.rect;},
    animate(frames,options){
      let resolve,reject;
      const animation={node:this,frames,options,cancelled:false,finished:new Promise((done,fail)=>{resolve=done;reject=fail;}),
        cancel(){this.cancelled=true;reject(new Error('cancelled'));},complete(){resolve();}};
      animations.push(animation);return animation;
    },
  });
  const body=node('body','','BODY'),main=node('main','','MAIN');main.parentElement=body;
  main.querySelectorAll=()=>panels;
  const document={body,hidden:false,
    getElementById:id=>id==='main'?main:null,
    querySelector:()=>null,
    querySelectorAll:selector=>selector==='dialog[open]'?dialogs.filter(dialog=>dialog.open):selector==='dialog'?dialogs:selector==='details'?details:selector.includes('button[aria-pressed]')?controls:[],
    addEventListener:(name,fn)=>add(listeners,name,fn),removeEventListener:(name,fn)=>listeners.get(name)?.delete(fn),
  };
  const window={innerHeight:720,innerWidth:1280,location:{hash:'#overview'},matchMedia:()=>preference,
    getComputedStyle:()=>({backgroundColor:'rgb(20, 30, 40)',color:'rgb(240, 240, 240)'}),
    MutationObserver:class {constructor(callback){mutation=callback;}observe(){}disconnect(){this.disconnected=true;}},
  };
  const setPanel=(html='12 sets')=>{
    for(const old of panels)old.isConnected=false;
    const panel=node('training-summary',html);panel.parentElement=main;panels=[panel];main.children=panels;return panel;
  };
  setPanel();
  return {document,window,animations,preference,node,setPanel,
    emit(name,target=main){for(const fn of listeners.get(name)||[])fn({type:name,target});},
    reduce(value){preference.matches=value;for(const fn of preferenceListeners.get('change')||[])fn();},
    mutate(records){mutation(records);},
    addDialog(){const dialog=node('workout-dialog','','DIALOG');dialog.parentElement=body;dialogs.push(dialog);return dialog;},
    addDetails(){const disclosure=node('settings','','DETAILS');disclosure.parentElement=main;details.push(disclosure);return disclosure;},
    addControl(){const control=node('muscle-choice','','BUTTON');control.selected='false';control.getAttribute=name=>name==='aria-pressed'?control.selected:null;controls.push(control);return control;},
    listenerCount(){return [...listeners.values(),...preferenceListeners.values()].reduce((n,set)=>n+set.size,0);},
  };
}

test('content updates skip initial and identical replacements, detached work is cancelled', async () => {
  const f=fixture(),motion=installUiMotion(f.document,f.window);
  assert.equal(f.animations.length,0);
  f.setPanel();motion.update();
  assert.equal(f.animations.length,0);
  f.setPanel('15 sets');motion.update();
  assert.equal(f.animations.length,1);
  const retained=f.setPanel('18 sets');motion.update();
  assert.equal(f.animations[0].cancelled,true);
  retained.innerHTML='21 sets';motion.update();
  assert.equal(f.animations[1].cancelled,true);
  assert.equal(f.animations.length,3);
  // Resolving/rejecting an older animation must not remove a newer one.
  await Promise.resolve();
  motion.finish();
  assert.equal(f.animations[2].cancelled,true);
  motion.disconnect();
  assert.equal(f.listenerCount(),0);
});

test('in-page selections stay anchored while page switches retain their entrance', () => {
  const f=fixture(),control=f.addControl(),motion=installUiMotion(f.document,f.window);
  control.selected='true';
  f.mutate([{type:'attributes',target:control,attributeName:'aria-pressed'}]);
  assert.equal(f.animations.length,0,'retained controls use CSS colors without a scale pulse');
  motion.update();
  assert.equal(f.animations.length,0,'an unchanged selection must not pulse again');
  const panel=f.setPanel('Editing a setting');f.document.activeElement=panel;
  motion.update();
  assert.equal(f.animations.at(-1).frames[0].translate,undefined);
  assert.ok(f.animations.at(-1).frames[0].opacity >= .9,'changed content should not blink away');
  f.document.activeElement=null;
  f.window.location.hash='#workouts';motion.update();
  assert.equal(f.animations.at(-1).frames[0].translate,'0 14px');
  assert.equal(f.animations.at(-1).options.duration,340);
  f.reduce(true);
  assert.ok(f.animations.every(animation=>animation.cancelled));
  motion.disconnect();
});

test('typing, offscreen updates, reduced motion and hidden tabs reveal content without animation', () => {
  const f=fixture(),motion=installUiMotion(f.document,f.window);
  const offscreen=f.setPanel('15 sets');offscreen.rect={...offscreen.rect,top:900,bottom:1020};motion.update();
  assert.equal(f.animations.length,0);
  f.emit('input');f.setPanel('Search result');motion.update();
  assert.equal(f.animations.length,0);
  f.emit('click');f.setPanel('Selected workout');motion.update();
  assert.equal(f.animations.length,1);
  f.reduce(true);
  assert.equal(f.animations[0].cancelled,true);
  f.setPanel('Updated while reduced');motion.update();
  assert.equal(f.animations.length,1);
  f.reduce(false);f.setPanel('New selection');motion.update();
  assert.equal(f.animations.length,2);
  f.document.hidden=true;f.emit('visibilitychange');
  assert.equal(f.animations[1].cancelled,true);
  f.setPanel('Updated while hidden');motion.update();
  assert.equal(f.animations.length,2);
  motion.disconnect();
});

test('dialog entry animation observes native open and close without changing either state', () => {
  const f=fixture(),dialog=f.addDialog(),motion=installUiMotion(f.document,f.window);
  dialog.open=true;
  f.mutate([{type:'attributes',target:dialog,attributeName:'open'}]);
  assert.equal(dialog.open,true);
  assert.equal(f.animations.length,1);
  assert.equal(f.animations[0].node,dialog);
  dialog.open=false;
  f.mutate([{type:'attributes',target:dialog,attributeName:'open'}]);
  assert.equal(dialog.open,false);
  assert.equal(f.animations[0].cancelled,true);
  motion.disconnect();
});


test('disclosure size feedback keeps native toggling immediate during rapid open and close', () => {
  const f=fixture(),details=f.addDetails();
  details.rect={...details.rect,height:40,bottom:60};
  const motion=installUiMotion(f.document,f.window);
  details.open=true;details.rect={...details.rect,height:200,bottom:220};
  f.mutate([{type:'attributes',target:details,attributeName:'open'}]);
  assert.equal(details.open,true);
  assert.equal(f.animations.length,1);
  assert.equal(f.animations[0].frames[0].height,'40px');
  details.open=false;details.rect={...details.rect,height:40,bottom:60};
  f.mutate([{type:'attributes',target:details,attributeName:'open'}]);
  assert.equal(details.open,false);
  assert.equal(f.animations[0].cancelled,true);
  assert.equal(f.animations.length,2);
  assert.equal(f.animations[1].frames.at(-1).height,'40px');
  motion.disconnect();
});
