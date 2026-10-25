import test from 'node:test';
import assert from 'node:assert/strict';
import {createBodyMotion} from '../../src/reptrace/web/static/body-motion.mjs';

function fixture() {
  const animations = [];
  const muscle = name => {
    const node = {isConnected: true, dataset: {bodyMuscle: name, bodyState: 'primary|6|0', bodySelected: 'false'},
      toggleAttribute(name,value) {this.hovered = value;},
      querySelectorAll(selector) {assert.equal(selector,'[data-muscle-rest]');return this.shapes;}};
    node.shapes=[{get isConnected(){return node.isConnected;},dataset:{muscleRest:'M0 0 Q5 10 10 0 Z',muscleFlexed:'M0 0 Q5 12 10 0 Z'},
      animate(frames,options){
        const animation={node:this,frames,options,cancelled:false,finished:new Promise(()=>{}),cancel(){this.cancelled=true;}};
        animations.push(animation);return animation;
      }}];
    return node;
  };
  const muscles=[muscle('Chest'),muscle('Shoulders')];
  const figure={dataset:{bodyKey:'body-work-front',bodyContext:'2026-10-19|0'},
    querySelectorAll(selector){assert.equal(selector,'.body-muscle-art[data-body-muscle]');return muscles;}};
  const root={querySelectorAll(selector){assert.equal(selector,'.body-map-svg');return [figure];}};
  return {animations,muscles,figure,root};
}

test('map updates grow every muscle, then smoothly settle at normal size',()=>{
  const f=fixture(),motion=createBodyMotion();
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,2);
  const {frames,options}=f.animations[0];
  assert.equal(frames[0].d,'path("M0 0 Q5 10 10 0 Z")');
  assert.equal(frames[1].d,'path("M0 0 Q5 12 10 0 Z")');
  assert.equal(frames[2].d,frames[1].d,'finish growing before returning');
  assert.equal(frames.at(-1).d,frames[0].d,'always end at the original size');
  assert.deepEqual(frames.map(frame=>frame.offset),[0,.42,.52,1]);
  assert.equal(options.duration,900);
  assert.deepEqual(f.animations[1].frames,frames,'all muscles grow together');
  assert.ok(frames.every(frame=>!('clipPath' in frame)&&!('transform' in frame)),'pulse never starts by hiding or shrinking the artwork');
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,2,'unchanged rendering does not pulse again');
  f.figure.dataset.bodyContext='2026-10-12|0';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,4,'week change pulses every muscle even with identical values');
  assert.ok(f.animations.slice(0,2).every(animation=>animation.cancelled));
  motion.finish();
});

test('selection and hover do not change geometry; a data update pulses all muscles',()=>{
  const f=fixture(),motion=createBodyMotion();
  motion.update(f.root,{route:'#volume',reduced:true});
  f.muscles[0].dataset.bodySelected='true';
  motion.update(f.root,{route:'#volume'});
  motion.setHovered('Shoulders');
  assert.equal(f.muscles[0].hovered,false);
  assert.equal(f.muscles[1].hovered,true);
  assert.equal(f.animations.length,0,'selecting and hovering only change highlights');
  f.muscles[0].dataset.bodySelected='false';
  f.muscles[1].dataset.bodySelected='true';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,0);
  f.muscles[0].dataset.bodyState='primary|9|0';
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,2,'both changed and unchanged muscle groups pulse');
  motion.setHovered(null);
  assert.ok(f.muscles.every(node=>!node.hovered));
  motion.finish();
});

test('a change in one body map pulses all visible body maps',()=>{
  const a=fixture(),b=fixture(),motion=createBodyMotion();
  b.figure.dataset.bodyKey='body-change-front';
  const root={querySelectorAll:()=>[a.figure,b.figure]};
  motion.update(root,{route:'#volume',reduced:true});
  a.muscles[0].dataset.bodyState='primary|12|0';
  motion.update(root,{route:'#volume'});
  assert.equal(a.animations.length,2);
  assert.equal(b.animations.length,2);
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
  assert.equal(f.animations.length,2,'reduced motion skips the growth cycle');
  assert.ok(f.animations.every(animation=>animation.cancelled));
  motion.update({querySelectorAll:()=>[]},{route:'#overview'});
  f.muscles[0].isConnected=true;
  motion.update(f.root,{route:'#volume'});
  assert.equal(f.animations.length,4);
  motion.finish();
});
