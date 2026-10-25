import {createBodyMotion} from './body-motion.mjs';
/* Presentation only: rendering, focus, form state and native dismissal stay synchronous. */
const surfaces = [
  '.page-heading', '.panel', '.stat', '.panel-heading', '.table-heading', '.table-scroll',
  '.exercise-metrics', '.exercise-list', '.workout-card', '.calendar-days', '.calendar-detail',
  '.map-detail-heading', '.map-detail-metrics', '.map-comparison-cards',
  '.map-data-coverage', '.map-week-summary', '.volume-history-title', '.volume-week-detail',
  '.comparison-cards', '.record-banner', '.nutrition-list', '.edit-history', '.goal-card',
  '.empty-panel', '.error-state', '.form-error', '#range-error', '.refresh-notice',
  '.settings-draft-notice', '.dialog-heading', '.dialog-stats', '.dialog-exercise-title',
  '.editor-fields', '#draft-rows > *', '#equipment-rows > *',
].join(', ');
const controls = 'button[aria-pressed], button[aria-selected], .topnav-link, .segmented button, .topnav-more-toggle';
const transientClasses = /\b(?:active|selected|visible|is-today|spinning)\b/g;
const ease = 'cubic-bezier(.22, .8, .3, 1)';

export function surfaceSignature(markup, keepSelection = false) {
  // Ignore animation bookkeeping, keyboard focus and control selection. Those
  // changes must not make an otherwise identical table or calendar flash.
  let result = markup.replace(/\sstyle="[^"]*"/g, '').replace(/\s(?:tabindex|aria-expanded)="[^"]*"/g, '');
  if (!keepSelection) result = result.replace(/\saria-(?:pressed|selected|current)="[^"]*"/g, '')
    .replace(/class="([^"]*)"/g, (_, value) => `class="${value.replace(transientClasses, '').trim().replace(/\s+/g, ' ')}"`);
  return result;
}

export function changedSurfaces(previous, current, {routeChanged = false, suppressed = false} = {}) {
  if (suppressed) return [];
  return current.filter(item => item.visible && (routeChanged || previous.get(item.key)?.signature !== item.signature));
}

export function installUiMotion(document, window) {
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const bodyMotion = createBodyMotion();
  const running = new Map(), disclosureSizes = new WeakMap(), openDialogs = new WeakSet();
  let previous = new Map(), previousControls = new Map(), previousRoute = '', typing = false;
  const disabled = () => preference.matches || document.hidden;
  const finish = () => { for (const animation of running.values()) animation.cancel(); running.clear(); bodyMotion.finish(); };
  const play = (node, frames, options = {}) => {
    running.get(node)?.cancel();
    if (disabled() || !node.isConnected || typeof node.animate !== 'function') return;
    const animation = node.animate(frames, {duration: 340, easing: ease, fill: 'backwards', ...options});
    running.set(node, animation);
    const clean = () => { if (running.get(node) === animation) running.delete(node); };
    animation.finished.then(clean, clean);
  };
  const visible = rect => rect.height > 0 && rect.width > 0 && rect.bottom > 0
    && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;

  function update(initial = false, openings = []) {
    for (const [node, animation] of running) if (!node.isConnected) { animation.cancel(); running.delete(node); }
    if (disabled()) finish();
    const route = document.querySelector('#navigation [aria-current="page"]')?.getAttribute('href') || window.location.hash;
    const routeChanged = route !== previousRoute;
    if (routeChanged) finish();
    bodyMotion.update(document, {route, reduced: initial || disabled()});
    const keyCache = new WeakMap();
    const keyFor = node => {
      if (keyCache.has(node)) return keyCache.get(node);
      if (!node || node === document.body) return 'body';
      const identity = node.id || [...node.attributes].filter(attribute => /^data-(?:overview-section|session|exercise|equipment-id|volume-group)$/.test(attribute.name))
        .map(attribute => `${attribute.name}:${attribute.value}`).join('|');
      const stem = `${node.tagName}.${[...node.classList].filter(name => !/^(active|selected|visible|spinning)$/.test(name)).join('.')}`;
      const peers = node.parentElement ? [...node.parentElement.children].filter(peer => peer.tagName === node.tagName) : [];
      const key = identity ? `${node.tagName}:${identity}` : `${keyFor(node.parentElement)}/${stem}:${peers.indexOf(node)}`;
      keyCache.set(node, key);
      return key;
    };
    const roots = [document.getElementById('main'), ...document.querySelectorAll('dialog[open]')].filter(Boolean);
    const records = roots.flatMap(root => [...root.querySelectorAll(surfaces)]
      .filter(node => !node.matches('.volume-mini, [data-motion-chart]') && !node.querySelector(surfaces))
      .map(node => ({node, key: keyFor(node), visible: visible(node.getBoundingClientRect()),
        signature: surfaceSignature(node.innerHTML, node.matches('.map-visuals'))})));
    const freshDialogs = [...document.querySelectorAll('dialog[open]')].filter(node => !openDialogs.has(node));
    const animatedParents = [...freshDialogs, ...openings.filter(node => node.open)];
    const changed = changedSurfaces(previous, records, {routeChanged, suppressed: initial || typing || disabled()});
    // Animate only leaf regions, never their parents as well. Offscreen tables
    // and live search results are recorded without starting decorative work.
    changed.filter(item => !animatedParents.some(parent => parent.contains(item.node))).slice(0, 10).forEach(({node}, index) => {
      if (routeChanged) {
        const distance = node.contains(document.activeElement) ? 0 : 14;
        play(node, [{opacity: .15, translate: `0 ${distance}px`}, {opacity: 1, translate: '0 0'}],
          {delay: Math.min(index * 24, 96)});
      } else {
        // Keep in-page updates anchored and readable; reserve entrances for navigation.
        play(node, [{opacity: .92}, {opacity: 1}], {duration: 160});
      }
    });
    previous = new Map(records.map(item => [item.key, item]));

    const nextControls = new Map();
    for (const node of document.querySelectorAll(controls)) {
      if (node.namespaceURI !== 'http://www.w3.org/1999/xhtml' || !visible(node.getBoundingClientRect())) continue;
      const key = keyFor(node), selected = node.getAttribute('aria-pressed') || node.getAttribute('aria-selected')
        || node.getAttribute('aria-current') || String(node.classList.contains('active'));
      const style = window.getComputedStyle(node);
      const colors = {backgroundColor: style.backgroundColor, color: style.color};
      const before = previousControls.get(key);
      // Retained controls use their CSS color transition. Replaced controls
      // get the same transition without bouncing their label or hit area.
      if (!initial && !typing && (!routeChanged || node.closest('#navigation')) && before && before.selected !== selected) {
        if (before.node !== node) {
          const navigation = node.closest('#navigation');
          const chosen = selected !== 'false';
          play(node, navigation
            ? [{...before.colors, scale: chosen ? '.95' : '1'}, {...colors, scale: '1'}]
            : [before.colors, colors], {duration: navigation ? 300 : 180});
        }
      }
      nextControls.set(key, {node, selected, colors});
    }
    previousControls = nextControls;
    previousRoute = route;

    for (const dialog of document.querySelectorAll('dialog')) {
      if (dialog.open) {
        if (!initial && !openDialogs.has(dialog)) play(dialog, [{opacity: .15, translate: '0 16px'}, {opacity: 1, translate: '0 0'}]);
        openDialogs.add(dialog);
      } else {
        openDialogs.delete(dialog);
        running.get(dialog)?.cancel();
        running.delete(dialog);
      }
    }
    for (const details of openings) {
      if (!details.isConnected) continue;
      const from = disclosureSizes.get(details);
      running.get(details)?.cancel();
      running.delete(details);
      const to = details.getBoundingClientRect().height;
      // Menus are positioned outside the summary's flow; fade their content.
      if (details.matches('.topnav-more')) {
        if (details.open) {
          const menu = details.querySelector('.topnav-menu');
          if (menu) play(menu, [{opacity: 0, translate: '0 -8px'}, {opacity: 1, translate: '0 0'}], {duration: 280});
        }
      } else if (Number.isFinite(from) && Math.abs(from - to) > 1) {
        play(details, [{height: `${from}px`, overflow: 'clip'}, {height: `${to}px`, overflow: 'clip'}], {duration: 320});
      }
      disclosureSizes.set(details, to);
    }
    for (const details of document.querySelectorAll('details')) if (!running.has(details)) disclosureSizes.set(details, details.getBoundingClientRect().height);
  }

  const markInteraction = event => {
    typing = event.type === 'input' || event.type === 'compositionstart';
    if (typing) finish();
    const details = event.target.closest?.('summary')?.parentElement;
    if (details?.tagName === 'DETAILS') disclosureSizes.set(details, details.getBoundingClientRect().height);
  };
  const events = ['input', 'compositionstart', 'click', 'change', 'keydown', 'submit'];
  for (const event of events) document.addEventListener(event, markInteraction, true);
  const highlightBody = event => {
    if (event.pointerType === 'touch') return;
    const target = event.type === 'pointerout' || event.type === 'focusout' ? event.relatedTarget : event.target;
    bodyMotion.setHovered(target?.closest?.('[data-map-muscle]')?.dataset.mapMuscle || null);
  };
  const hoverEvents = ['pointerover', 'pointerout', 'focusin', 'focusout'];
  for (const event of hoverEvents) document.addEventListener(event, highlightBody);
  const observer = new window.MutationObserver(records => {
    const openings = records.filter(record => record.type === 'attributes' && record.attributeName === 'open' && record.target.tagName === 'DETAILS').map(record => record.target);
    const structural = records.some(record => {
      if (record.type === 'attributes') return true;
      if (record.target.closest?.('.chart-tooltip, #toast, #sync-status, select, option')) return false;
      return record.target.matches?.('.form-error, #range-error') || [...record.addedNodes, ...record.removedNodes].some(node => node.nodeType === 1);
    });
    if (structural) update(false, [...new Set(openings)]);
  });
  update(true);
  observer.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['open', 'aria-pressed', 'aria-selected']});
  const reduce = () => { if (preference.matches) finish(); };
  const hide = () => { if (document.hidden) finish(); };
  preference.addEventListener('change', reduce);
  document.addEventListener('visibilitychange', hide);
  return {finish, update, disconnect() {
    finish(); observer.disconnect();
    for (const event of events) document.removeEventListener(event, markInteraction, true);
    for (const event of hoverEvents) document.removeEventListener(event, highlightBody);
    preference.removeEventListener('change', reduce);
    document.removeEventListener('visibilitychange', hide);
  }};
}

if (typeof document !== 'undefined') installUiMotion(document, window);
