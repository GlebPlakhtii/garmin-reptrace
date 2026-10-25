/* Pulse decorative anatomy on map updates. Borders and hit targets stay fixed. */
export function createBodyMotion() {
  let previous = new Map(), previousRoute = '', hovered = null, artwork = [];
  const setHovered = name => {
    hovered = name;
    for (const node of artwork) node.toggleAttribute('data-body-hovered', node.dataset.bodyMuscle === name);
  };
  const running = new Map();
  const finish = () => {
    for (const animation of running.values()) animation.cancel();
    running.clear();
  };
  const pulse = node => {
    if (typeof node.animate !== 'function') return;
    running.get(node)?.cancel();
    const rest = `path("${node.dataset.muscleRest}")`, flexed = `path("${node.dataset.muscleFlexed}")`;
    const animation = node.animate([
      {d: rest, offset: 0, easing: 'cubic-bezier(.4, 0, .2, 1)'},
      {d: flexed, offset: .42},
      {d: flexed, offset: .52, easing: 'cubic-bezier(.4, 0, .2, 1)'},
      {d: rest, offset: 1},
    ], {duration: 900, easing: 'linear', fill: 'backwards'});
    running.set(node, animation);
    const clean = () => { if (running.get(node) === animation) running.delete(node); };
    animation.finished.then(clean, clean);
  };
  function update(root, {route = '', reduced = false} = {}) {
    for (const [node, animation] of running) if (!node.isConnected) { animation.cancel(); running.delete(node); }
    if (route !== previousRoute) { finish(); previous = new Map(); previousRoute = route; hovered = null; }
    if (reduced) finish();
    const next = new Map();
    let changed = false;
    artwork = [];
    for (const figure of root.querySelectorAll('.body-map-svg')) {
      const context = figure.dataset.bodyContext;
      const muscles = [...figure.querySelectorAll('.body-muscle-art[data-body-muscle]')];
      artwork.push(...muscles);
      for (const node of muscles) {
        const key = `${figure.dataset.bodyKey}:${node.dataset.bodyMuscle}`;
        const state = {context, value: node.dataset.bodyState};
        const before = previous.get(key);
        next.set(key, state);
        if (!before || before.context !== context || before.value !== state.value) changed = true;
      }
    }
    changed ||= previous.size !== next.size;
    previous = next;
    setHovered(hovered);
    // A measurement/week update pulses every muscle together. Selection alone
    // never changes geometry, and every pulse settles at the original full size.
    if (!reduced && changed) {
      for (const node of artwork) for (const path of node.querySelectorAll('[data-muscle-rest]')) pulse(path);
    }
  }
  return {update, finish, setHovered};
}
