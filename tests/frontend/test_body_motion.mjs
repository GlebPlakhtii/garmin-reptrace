import test from 'node:test';
import assert from 'node:assert/strict';
import {createBodyMotion} from '../../src/reptrace/web/static/body-motion.mjs';

function fixture() {
  const animations = [];
  const muscle = name => {
    const node = {isConnected: true, dataset: {bodyMuscle: name, bodyState: 'primary|6|0', bodySelected: 'false'},
      toggleAttribute(name,value) {this.hovered = value;},
      querySelectorAll(selector) {return selector==='.body-muscle-piece'?this.pieces:this.shapes;}};
    node.shapes=[{get isConnected(){return node.isConnected;},dataset:{muscleRest:'M0 0 Q5 10 10 0 Z',muscleFlexed:'M0 0 Q5 12 10 0 Z'},
      animate(frames,options){
        const animation={node:this,frames,options,cancelled:false,finished:new Promise(()=>{}),cancel(){this.cancelled=true;}};
        animations.push(animation);return animation;
      }}];
    node.pieces=[{get isConnected(){return node.isConnected;},animate:node.shapes[0].animate}];
    return node;
  };
  const muscles=[muscle('Chest'),muscle('Shoulders')];
  const figure={dataset:{bodyKey:'body-work-front',bodyContext:'2026-10-19|0'},
    querySelectorAll(selector){assert.equal(selector,'.body-muscle-art[data-body-muscle]');return muscles;}};
  const root={querySelectorAll(selector){assert.equal(selector,'.body-map-svg');return [figure];}};
  return {animations,muscles,figure,root};
}

test('map updates reveal each muscle from its center, then grow and smoothly return to normal',()=>{
  const f=fixture(),motion=createBodyMotion();
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,4);
  const entry=f.animations[0];
  assert.equal(entry.node,f.muscles[0].pieces[0]);
  assert.equal(entry.frames[0].clipPath,'circle(0% at 50% 50%) fill-box');
  assert.equal(entry.frames[1].clipPath,'circle(75% at 50% 50%) fill-box');
  assert.equal(entry.options.duration,320);
  const {frames,options}=f.animations[1];
  assert.equal(frames[0].d,'path("M0 0 Q5 10 10 0 Z")');
  assert.equal(frames[1].d,'path("M0 0 Q5 12 10 0 Z")');
  assert.equal(frames[2].d,frames[1].d,'finish growing before returning');
  assert.equal(frames.at(-1).d,frames[0].d,'always end at the original size');
  assert.deepEqual(frames.map(frame=>frame.offset),[0,.42,.52,1]);
  assert.equal(options.duration,900);
  assert.ok(options.delay>=entry.options.duration,'finish the center reveal before expansion starts');
  assert.deepEqual(f.animations[3].frames,frames,'all muscles grow together');
  assert.ok(frames.every(frame=>!('clipPath' in frame)&&!('transform' in frame)),'size pulse grows from the normal geometry');
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,4,'unchanged rendering does not pulse again');
  f.figure.dataset.bodyContext='2026-10-12|0';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,8,'week change reveals and pulses every muscle even with identical values');
  assert.ok(f.animations.slice(0,4).every(animation=>animation.cancelled));
  motion.finish();
});

test('selection keeps its center-out highlight and size animation without replaying every muscle',()=>{
  const f=fixture(),motion=createBodyMotion();
  motion.update(f.root,{route:'#volume',reduced:true});
  f.muscles[0].dataset.bodySelected='true';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,2);
  assert.ok(f.animations.every(animation=>animation.node===f.muscles[0].shapes[0]),'only the selected group animates');
  const [shape,glow]=f.animations;
  assert.equal(shape.frames.at(-1).d,shape.frames[0].d);
  assert.equal(glow.frames[0].clipPath,'circle(0% at 50% 50%) fill-box');
  assert.equal(glow.frames.at(-1).opacity,.16,'selected tint remains after the reveal');
  assert.equal(shape.cancelled,false,'highlight must not cancel simultaneous shape animation');
  assert.equal(glow.cancelled,false);
  motion.setHovered('Shoulders');
  assert.equal(f.muscles[0].hovered,false);
  assert.equal(f.muscles[1].hovered,true);
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,2,'hover or unchanged selection does not restart animations');
  f.muscles[0].dataset.bodySelected='false';
  f.muscles[1].dataset.bodySelected='true';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,4);
  assert.ok(f.animations.slice(2).every(animation=>animation.node===f.muscles[1].shapes[0]));
  f.muscles[0].dataset.bodyState='primary|9|0';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,8,'data update reveals and pulses all groups');
  motion.finish();
});

test('mirrored lobes reveal independently around their own centers',()=>{
  const f=fixture(),motion=createBodyMotion();
  f.muscles[0].pieces.push({...f.muscles[0].pieces[0]});
  motion.update(f.root,{route:'#volume'});
  const entries=f.animations.filter(animation=>'clipPath' in animation.frames[0]);
  assert.equal(entries.length,3);
  assert.notEqual(entries[0].node,entries[1].node);
  assert.deepEqual(entries[0].frames,entries[1].frames);
  assert.equal(entries[0].frames[0].clipPath,'circle(0% at 50% 50%) fill-box');
  motion.finish();
});

test('a change in one body map pulses all visible body maps',()=>{
  const a=fixture(),b=fixture(),motion=createBodyMotion();
  b.figure.dataset.bodyKey='body-change-front';
  const root={querySelectorAll:()=>[a.figure,b.figure]};
  motion.update(root,{route:'#volume',reduced:true});
  a.muscles[0].dataset.bodyState='primary|12|0';
  motion.update(root,{route:'#volume'});
  assert.equal(a.animations.length,4);
  assert.equal(b.animations.length,4);
  motion.finish();
});

test('reduced motion, detached artwork and route changes cancel pulses',()=>{
  const f=fixture(),motion=createBodyMotion();
  motion.update(f.root,{route:'#volume'});
  f.muscles[0].isConnected=false;
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations[0].cancelled,true);
  f.figure.dataset.bodyContext='2026-10-12|0';
  motion.update(f.root,{route:'#volume',reduced:true});
  assert.equal(f.animations.length,4,'reduced motion skips reveal and growth');
  assert.ok(f.animations.every(animation=>animation.cancelled));
  motion.update({querySelectorAll:()=>[]},{route:'#overview'});
  f.muscles[0].isConnected=true;
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,8);
  motion.finish();
});
