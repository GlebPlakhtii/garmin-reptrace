/* Animate changed measurements without changing their values or chart hit targets. */
const chartSelector = '.workout-bars-svg, .volume-history-svg, .volume-mini-svg, [data-motion-chart]';
const barSelector = '.workout-bar, .workout-segment, .volume-value-bar, .volume-exercise-segment';
const markSelector = `${barSelector}, [data-motion-bar], [data-motion-line], [data-motion-area], .sleep-stages-bar > span`;
const active = new Set();
const activeByNode = new WeakMap();
const observedDocuments = new WeakSet();
let previousRoute = null;
let previousCharts = new Map();

export function barMotionPlan(bars, baseline) {
  if (!Number.isFinite(baseline)) return [];
  const valid = bars.filter(bar => Number.isFinite(bar.x) && Number.isFinite(bar.y)
    && Number.isFinite(bar.height) && bar.height > 0 && Number.isFinite(bar.value) && bar.value > 0);
  const columns = [...new Set(valid.map(bar => bar.x))].sort((a, b) => a - b);
  const delays = new Map(columns.map((x, index) => [x, index * Math.min(18, 120 / Math.max(1, columns.length - 1))]));
  return valid.map(bar => ({bar, origin: `0px ${baseline}px`, duration: 460, delay: delays.get(bar.x)}));
}

function restore(entry) {
  if (!active.delete(entry)) return;
  activeByNode.delete(entry.node);
  entry.animation.cancel();
  entry.node.style.transformBox = entry.box;
  entry.node.style.transformOrigin = entry.origin;
}

// Removing the animation reveals the untouched final SVG geometry immediately.
export function finishChartMotion() {
  for (const entry of [...active]) restore(entry);
}

function chartSignature(chart, marks) {
  return JSON.stringify([chart.getAttribute('aria-label'), chart.getAttribute('viewBox'), chart.dataset.plotBottom,
    chart.dataset.timeStart, chart.dataset.timeEnd, chart.dataset.motionMetric,
    marks.map(mark => [['x', 'y', 'width', 'height', 'd', 'fill', 'title', 'data-session', 'data-exercise-color',
      'data-point-value', 'data-point-unit', 'data-motion-label', 'data-motion-bar'].map(attribute => mark.getAttribute(attribute)),
      mark.style.width, mark.style.height])]);
}

function play(node, frames, {duration = 460, delay = 0, origin, box} = {}) {
  if (typeof node.animate !== 'function') return;
  const previous = activeByNode.get(node);
  if (previous) restore(previous);
  const entry = {node, box: node.style.transformBox, origin: node.style.transformOrigin};
  if (box) node.style.transformBox = box;
  if (origin) node.style.transformOrigin = origin;
  entry.animation = node.animate(frames, {duration, delay, easing: 'cubic-bezier(.22, .8, .3, 1)', fill: 'backwards'});
  active.add(entry);
  activeByNode.set(node, entry);
  entry.animation.finished.then(() => restore(entry), () => restore(entry));
}

export function animateChangedCharts(root, {reduced = false, route = ''} = {}) {
  const document = root.ownerDocument || root;
  if (!observedDocuments.has(document)) {
    document.addEventListener('visibilitychange', () => { if (document.hidden) finishChartMotion(); });
    observedDocuments.add(document);
  }
  for (const entry of [...active]) if (!entry.node.isConnected) restore(entry);
  if (route !== previousRoute) {
    finishChartMotion();
    previousCharts = new Map();
    previousRoute = route;
  }
  if (reduced || document.hidden) finishChartMotion();
  const nextCharts = new Map();
  for (const [index, chart] of [...root.querySelectorAll(chartSelector)].entries()) {
    const marks = [...chart.querySelectorAll(markSelector)];
    const signature = chartSignature(chart, marks);
    const slot = chart.dataset.motionKey || `chart:${index}`;
    nextCharts.set(slot, signature);
    if (reduced || document.hidden || previousCharts.get(slot) === signature) continue;
    // Both a total bar and every stacked segment use the same baseline and delay.
    const bars = marks.filter(node => !node.dataset.motionBar && !node.dataset.motionLine && !node.dataset.motionArea);
    const values = bars.map(node => ({node, x: Number(node.getAttribute('x')), y: Number(node.getAttribute('y')),
      height: Number(node.getAttribute('height')), value: Number(node.dataset.pointValue)}));
    const plan = barMotionPlan(values, Number(chart.dataset.plotBottom));
    for (const {bar, origin, duration, delay} of plan) {
      play(bar.node, [{transform: 'scaleY(0)'}, {transform: 'scaleY(1)'}], {duration, delay, origin, box: 'view-box'});
    }
    const htmlBars = marks.filter(node => node.dataset.motionBar
      && Number.isFinite(Number(node.dataset.pointValue)) && Number(node.dataset.pointValue) > 0);
    for (const [i, node] of htmlBars.entries()) {
      const axis = node.dataset.motionBar;
      const delay = i * Math.min(18, 120 / Math.max(1, htmlBars.length - 1));
      // The overview count labels follow the bar's height without being scaled.
      if (axis === 'height') play(node, [{height: '0%'}, {height: node.style.height}], {delay});
      else play(node, [{transform: axis === 'x' ? 'scaleX(0)' : 'scaleY(0)'}, {transform: 'none'}],
        {delay, origin: axis === 'x' ? 'left center' : 'center bottom'});
    }
    for (const node of marks) {
      // A clip preserves the load chart's dashed line and all missing-data gaps.
      if (node.dataset.motionLine) play(node, [{clipPath: 'inset(0 100% 0 0)'}, {clipPath: 'inset(0 0% 0 0)'}]);
      // One keyframe returns to the authored opacity, including translucent bands.
      if (node.dataset.motionArea) play(node, [{opacity: 0}, {}], {duration: 380});
    }
    if (chart.dataset.motionReveal === 'x') play(chart, [{clipPath: 'inset(0 100% 0 0)'}, {clipPath: 'inset(0 0% 0 0)'}]);
  }
  previousCharts = nextCharts;
}

// Observe chart replacements, including exercise/muscle changes that leave the
// library mounted. Tooltip text updates do not restart or rescan the animation.
if (typeof document !== 'undefined') {
  const main = document.getElementById('main');
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const update = () => animateChangedCharts(document, {
    reduced: preference.matches,
    route: document.querySelector('#navigation [aria-current="page"]')?.getAttribute('href') || location.hash,
  });
  const includesChart = node => node.nodeType === 1
    && (node.matches(chartSelector) || node.querySelector(chartSelector));
  if (main) new MutationObserver(records => {
    if (records.some(record => [...record.addedNodes, ...record.removedNodes].some(includesChart))) update();
  }).observe(main, {childList: true, subtree: true});
  preference.addEventListener('change', () => { if (preference.matches) finishChartMotion(); });
  update();
}
