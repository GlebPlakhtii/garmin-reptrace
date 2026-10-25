import test from 'node:test';
import assert from 'node:assert/strict';
import {barMotionPlan, animateChangedCharts, finishChartMotion} from '../../src/reptrace/web/static/chart-motion.mjs';

test('stacked segments rise together from the chart baseline', () => {
  const bars = [{x:30,y:150,height:50,value:10}, {x:30,y:100,height:50,value:10}, {x:80,y:140,height:60,value:12}];
  const plan = barMotionPlan(bars, 200);
  assert.deepEqual(plan.map(item => item.origin), ['0px 200px','0px 200px','0px 200px']);
  assert.equal(plan[0].delay, plan[1].delay);
  assert.ok(plan[2].delay > plan[1].delay);
  assert.equal(plan[0].duration, 460);
  assert.deepEqual(bars[1], {x:30,y:100,height:50,value:10});
});

test('missing and zero measurements are not animated as positive bars; long histories stay fast', () => {
  const bars = Array.from({length:200}, (_,x)=>({x,y:100,height:50,value:10}));
  bars.push({x:500,y:197,height:3,value:0}, {x:510,y:190,height:10,value:null}, {x:520,y:190,height:10,value:NaN});
  const plan = barMotionPlan(bars,200);
  assert.equal(plan.length,200);
  assert.ok(Math.max(...plan.map(item=>item.delay)) <= 120);
  assert.equal(barMotionPlan(bars,NaN).length,0);
});

function fixture(chartClass = 'workout-bars-svg', barClass = 'workout-bar') {
  const listeners={}, animations=[];
  const document={hidden:false,addEventListener:(name,fn)=>listeners[name]=fn};
  let chart;
  function makeChart(value=10,label='Bench press') {
    const attributes={x:'30',y:String(200-value*5),width:'20',height:String(value*5),'data-point-value':String(value),'data-session':'synthetic-session'};
    const node={isConnected:true,dataset:{pointValue:String(value)},style:{transformBox:'',transformOrigin:''},getAttribute:key=>attributes[key]??null,
      animate(frames,options){const animation={frames,options,cancelled:false,cancel(){this.cancelled=true},finished:new Promise(()=>{})};animations.push(animation);return animation;}};
    chart={dataset:{plotBottom:'200'},getAttribute:key=>key==='aria-label'?label:key==='viewBox'?'0 0 800 270':null,
      querySelectorAll:selector=>selector.split(',').some(part=>part.trim()===`.${barClass}`)?[node]:[],node};
    return chart;
  }
  const root={ownerDocument:document,querySelectorAll:selector=>chart&&selector.split(',').some(part=>part.trim()===`.${chartClass}`)?[chart]:[]};
  return {root,document,listeners,animations,makeChart};
}

test('switching data animates again, but replacing identical chart DOM does not replay', () => {
  const f=fixture();let old=f.makeChart();
  animateChangedCharts(f.root,{route:'motion-test-switch'});
  assert.equal(f.animations.length,1);
  old.node.isConnected=false;f.makeChart();
  animateChangedCharts(f.root,{route:'motion-test-switch'});
  assert.equal(f.animations.length,1);
  assert.equal(f.animations[0].cancelled,true);
  f.makeChart(12,'Squat');animateChangedCharts(f.root,{route:'motion-test-switch'});
  f.makeChart(10,'Bench press');animateChangedCharts(f.root,{route:'motion-test-switch'});
  assert.equal(f.animations.length,3);
  finishChartMotion();
});

test('reduced motion and hidden tabs reveal final geometry and restore inline styles', () => {
  const f=fixture();const chart=f.makeChart();
  animateChangedCharts(f.root,{route:'motion-test-reduced'});
  assert.equal(chart.node.style.transformOrigin,'0px 200px');
  animateChangedCharts(f.root,{route:'motion-test-reduced',reduced:true});
  assert.equal(chart.node.style.transformOrigin,'');
  assert.equal(chart.node.style.transformBox,'');
  assert.equal(f.animations[0].cancelled,true);
  f.makeChart(14);f.document.hidden=true;
  animateChangedCharts(f.root,{route:'motion-test-reduced'});
  assert.equal(f.animations.length,1);
  f.document.hidden=false;f.makeChart(15);
  animateChangedCharts(f.root,{route:'motion-test-reduced'});
  f.document.hidden=true;f.listeners.visibilitychange();
  assert.equal(f.animations.at(-1).cancelled,true);
});

test('weekly history and mini charts animate changed metrics and dates, not week selection', () => {
  for (const [chartClass, barClass] of [['volume-history-svg','volume-value-bar'], ['volume-history-svg','volume-exercise-segment'], ['volume-mini-svg','volume-value-bar']]) {
    const f=fixture(chartClass,barClass),chart=f.makeChart(10,'Chest weekly history');
    const route=`weekly-${chartClass}-${barClass}`;
    chart.dataset.timeStart='2026-10-05';
    chart.dataset.timeEnd='2026-10-19';
    chart.dataset.motionMetric='sets';
    animateChangedCharts(f.root,{route});
    assert.equal(f.animations.length,1);
    assert.equal(chart.node.style.transformOrigin,'0px 200px');
    // Selection does not change measurements or dates and must not replay bars.
    animateChangedCharts(f.root,{route});
    assert.equal(f.animations.length,1);
    chart.dataset.motionMetric='reps';
    animateChangedCharts(f.root,{route});
    assert.equal(f.animations.length,2);
    assert.equal(f.animations[0].cancelled,true);
    chart.dataset.timeStart='2026-10-12';
    animateChangedCharts(f.root,{route});
    assert.equal(f.animations.length,3);
    finishChartMotion();
  }
});

function nativeFixture(descriptions, chartData = {}) {
  const animations = [], listeners = {};
  const document = {hidden: false, addEventListener: (name, fn) => listeners[name] = fn};
  function element(dataset, attributes = {}) {
    return {dataset, isConnected: true, style: {transformBox: '', transformOrigin: '', height: '60%', width: '40%'},
      getAttribute: name => attributes[name] ?? null,
      animate(frames, options) {
        const animation = {node: this, frames, options, cancelled: false, cancel() {this.cancelled = true;}, finished: new Promise(() => {})};
        animations.push(animation);
        return animation;
      }};
  }
  const marks = descriptions.map(description => element(description.dataset, description.attributes));
  const chart = element({motionChart: 'true', motionKey: 'native-fixture', ...chartData});
  chart.querySelectorAll = () => marks;
  const root = {ownerDocument: document, querySelectorAll: selector => selector.includes('[data-motion-chart]') ? [chart] : []};
  return {root, chart, marks, animations, document, listeners};
}

test('HTML chart bars grow only positive measurements and restore original styles on interruption', () => {
  const f = nativeFixture([
    {dataset: {motionBar: 'y', pointValue: '60'}},
    {dataset: {motionBar: 'x', pointValue: '40'}},
    {dataset: {motionBar: 'height', pointValue: '3'}},
    {dataset: {motionBar: 'y', pointValue: '0'}},
    {dataset: {motionBar: 'y', pointValue: ''}},
    {dataset: {motionBar: 'y', pointValue: 'Infinity'}},
  ]);
  animateChangedCharts(f.root, {route: 'native-bars'});
  assert.equal(f.animations.length, 3);
  assert.deepEqual(f.animations[0].frames, [{transform: 'scaleY(0)'}, {transform: 'none'}]);
  assert.equal(f.marks[0].style.transformOrigin, 'center bottom');
  assert.equal(f.marks[1].style.transformOrigin, 'left center');
  assert.deepEqual(f.animations[2].frames, [{height: '0%'}, {height: '60%'}]);
  assert.equal(f.marks[2].style.height, '60%');
  animateChangedCharts(f.root, {route: 'native-bars'});
  assert.equal(f.animations.length, 3, 'unchanged native bars must not replay');
  animateChangedCharts(f.root, {route: 'native-bars', reduced: true});
  assert.ok(f.animations.every(animation => animation.cancelled));
  assert.ok(f.marks.every(mark => mark.style.transformOrigin === ''));
});

test('line reveals keep missing-data paths and dash styles intact, and stacked strips preserve widths', () => {
  const f = nativeFixture([
    {dataset: {motionLine: 'true'}, attributes: {d: 'M0,10 L10,15 M30,20 L40,25', 'stroke-dasharray': '6 4'}},
    {dataset: {motionArea: 'true'}, attributes: {d: 'M0,10 L10,15 L10,20 Z'}},
  ]);
  animateChangedCharts(f.root, {route: 'line-reveal'});
  assert.equal(f.animations.length, 2);
  assert.deepEqual(f.animations[0].frames, [{clipPath: 'inset(0 100% 0 0)'}, {clipPath: 'inset(0 0% 0 0)'}]);
  assert.equal(f.marks[0].getAttribute('d'), 'M0,10 L10,15 M30,20 L40,25');
  assert.equal(f.marks[0].getAttribute('stroke-dasharray'), '6 4');
  assert.deepEqual(f.animations[1].frames, [{opacity: 0}, {}]);
  finishChartMotion();
  const stack = nativeFixture([{dataset: {pointValue: '90'}}], {motionReveal: 'x'});
  animateChangedCharts(stack.root, {route: 'sleep-reveal'});
  assert.equal(stack.animations.length, 1);
  assert.equal(stack.animations[0].node, stack.chart);
  assert.equal(stack.marks[0].style.width, '40%');
  finishChartMotion();
});
