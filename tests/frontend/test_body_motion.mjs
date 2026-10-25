import test from 'node:test';
import assert from 'node:assert/strict';
import {createBodyMotion} from '../../src/reptrace/web/static/body-motion.mjs';

function fixture() {
  const animations = [];
  const muscle = name => { const node = {isConnected: true, dataset: {bodyMuscle: name, bodyState: 'primary|6|0', bodySelected: 'false'},
    toggleAttribute(name,value) {this.hovered = value;},
    querySelectorAll(selector) {return selector==='[data-muscle-rest]'?[this.shape]:this.pieces;},
    animate(frames, options) {
      const animation = {node: this, frames, options, cancelled: false, finished: new Promise(() => {}), cancel() {this.cancelled = true;}};
      animations.push(animation); return animation;
    }};
    const glow = {get isConnected() {return node.isConnected;}, animate: node.animate};
    node.shape = {isConnected:true, dataset:{muscleRest:'M0 0 Q5 10 10 0 Z',muscleFlexed:'M0 0 Q5 12 10 0 Z'},animate:node.animate};
    node.pieces = [{get isConnected() {return node.isConnected;}, animate: node.animate,
      glow, querySelector() {return glow;}}];
    return node;
  };
  const muscles = [muscle('Chest'), muscle('Shoulders')];
  const controls=muscles.map(node=>({dataset:{mapMuscle:node.dataset.bodyMuscle},shape:{...node.shape},querySelectorAll(){return [this.shape];}}));
  const figure = {dataset: {bodyKey: 'body-work-front', bodyContext: '2026-10-19|0'},
    querySelectorAll(selector) {return selector==='.body-muscle[data-map-muscle]'?controls:muscles;}};
  const root = {querySelectorAll(selector) {assert.equal(selector, '.body-map-svg'); return [figure];}};
  return {animations, muscles, controls, figure, root};
}

test('body artwork reveals on week changes, even with equal totals, without animating hit regions', () => {
  const f = fixture(), motion = createBodyMotion();
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 2);
  assert.equal(f.animations[0].frames[0].clipPath, 'circle(0% at 50% 50%) fill-box');
  assert.ok(f.animations[1].options.delay > f.animations[0].options.delay);
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 2, 'unchanged refresh does not replay');
  f.figure.dataset.bodyContext = '2026-10-12|0';
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 4);
  assert.ok(f.animations.slice(0, 2).every(animation => animation.cancelled));
  motion.finish();
});

test('selection flexes artwork and its outline together, and relaxes the previous muscle', () => {
  const f = fixture(), motion = createBodyMotion();
  motion.update(f.root, {route: '#volume', reduced: true});
  f.muscles[0].dataset.bodySelected = 'true';
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 3);
  const [shape,outline,glow]=f.animations;
  assert.equal(shape.node,f.muscles[0].shape);
  assert.equal(outline.node,f.controls[0].shape);
  assert.deepEqual(shape.frames,outline.frames,'the edge follows the same deformation');
  assert.equal(shape.frames[0].d,'path("M0 0 Q5 10 10 0 Z")');
  assert.equal(shape.frames[1].d,'path("M0 0 Q5 12 10 0 Z")');
  assert.equal(glow.node, f.muscles[0].pieces[0].glow);
  assert.equal(glow.frames[0].clipPath, 'circle(0% at 50% 50%) fill-box');
  assert.equal(glow.frames.at(-1).opacity, .16);
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 3,'unchanged selection does not flex again');
  f.muscles[0].dataset.bodySelected='false';
  f.muscles[1].dataset.bodySelected='true';
  motion.update(f.root,{route:'#volume'});
  assert.deepEqual(f.animations[3].frames,[...shape.frames].reverse(),'previous muscle relaxes');
  assert.equal(f.animations[5].node,f.muscles[1].shape);
  motion.finish();
});

test('each left/right piece reveals from its own centre and hover follows the muscle name', () => {
  const f = fixture(), motion = createBodyMotion();
  const right = {isConnected: true, animate: f.muscles[0].animate};
  f.muscles[0].pieces.push(right);
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 3);
  assert.equal(f.animations[1].node, right);
  assert.deepEqual(f.animations[0].frames, f.animations[1].frames);
  motion.setHovered('Chest');
  assert.equal(f.muscles[0].hovered, true);
  assert.equal(f.muscles[1].hovered, false);
  motion.setHovered('Shoulders');
  assert.equal(f.muscles[0].hovered, false);
  assert.equal(f.muscles[1].hovered, true);
  motion.setHovered(null);
  assert.ok(f.muscles.every(node => !node.hovered));
  motion.finish();
});

test('reduced motion, detached artwork and route changes cancel body animations', () => {
  const f = fixture(), motion = createBodyMotion();
  motion.update(f.root, {route: '#volume'});
  f.muscles[0].isConnected = false;
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations[0].cancelled, true);
  motion.update(f.root, {route: '#volume', reduced: true});
  assert.ok(f.animations.every(animation => animation.cancelled));
  f.figure.dataset.bodyContext = '2026-10-05|0';
  motion.update(f.root, {route: '#volume', reduced: true});
  assert.equal(f.animations.length, 2);
  motion.update({querySelectorAll: () => []}, {route: '#overview'});
  f.muscles[0].isConnected = true;
  motion.update(f.root, {route: '#volume'});
  assert.equal(f.animations.length, 4);
  motion.finish();
});
