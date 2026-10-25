/* Animate decorative anatomy; group borders and hit targets stay stationary. */
export function createBodyMotion() {
  let previous = new Map(), previousRoute = '', hovered = null, artwork = [];
  const setHovered = name => {
    hovered = name;
    for (const node of artwork) node.toggleAttribute('data-body-hovered', node.dataset.bodyMuscle === name);
  };
  // Shape, reveal and highlight animate separate properties on the same SVG path.
  const running = new Map();
  const finish = () => {
    for (const channels of running.values()) for (const animation of channels.values()) animation.cancel();
    running.clear();
  };
  const play = (node, channel, frames, options = {}) => {
    if (typeof node.animate !== 'function') return;
    let channels = running.get(node);
    if (!channels) { channels = new Map(); running.set(node, channels); }
    channels.get(channel)?.cancel();
    const animation = node.animate(frames, {
      duration: 520, easing: 'cubic-bezier(.22, .8, .3, 1)', fill: 'backwards', ...options,
    });
    channels.set(channel, animation);
    const clean = () => {
      if (channels.get(channel) === animation) channels.delete(channel);
      if (!channels.size && running.get(node) === channels) running.delete(node);
    };
    animation.finished.then(clean, clean);
  };
  const pulse = (node, delay = 0) => {
    const rest = `path("${node.dataset.muscleRest}")`, flexed = `path("${node.dataset.muscleFlexed}")`;
    play(node, 'shape', [
      {d: rest, offset: 0, easing: 'cubic-bezier(.4, 0, .4, 1)'},
      {d: flexed, offset: .5, easing: 'cubic-bezier(.4, 0, .4, 1)'},
      {d: rest, offset: 1},
    ], {duration: 1200, delay, easing: 'linear'});
  };
  function update(root, {route = '', reduced = false} = {}) {
    for (const [node, channels] of running) if (!node.isConnected) {
      for (const animation of channels.values()) animation.cancel();
      running.delete(node);
    }
    const routeChanged = route !== previousRoute;
    if (routeChanged) { finish(); previousRoute = route; hovered = null; }
    if (reduced) finish();
    // Keep data snapshots to suppress unchanged redraws. Entering the page
    // explicitly replays appearance, including second and subsequent visits.
    const next = new Map(previous), updates = [], selections = [];
    artwork = [];
    for (const figure of root.querySelectorAll('.body-map-svg')) {
      const context = figure.dataset.bodyContext;
      const muscles = [...figure.querySelectorAll('.body-muscle-art[data-body-muscle]')];
      artwork.push(...muscles);
      muscles.forEach((node, index) => {
        const key = `${figure.dataset.bodyKey}:${node.dataset.bodyMuscle}`;
        const state = {context, value: node.dataset.bodyState, selected: node.dataset.bodySelected === 'true'};
        const before = previous.get(key);
        next.set(key, state);
        if (routeChanged || !before || before.context !== context || before.value !== state.value) {
          updates.push({node, delay: Math.min(index * 18, 110)});
        } else if (!routeChanged && state.selected && !before.selected) selections.push(node);
      });
    }
    previous = next;
    setHovered(hovered);
    if (reduced) return;
    for (const {node, delay} of updates) {
      // Keep the original reveal duration/stagger, overlapping the smooth growth
      // instead of starting a second animation stage after appearance finishes.
      // Replay on page entry, or when this group's displayed data changes.
      for (const piece of node.querySelectorAll('.body-muscle-piece')) play(piece, 'entry', [
        {clipPath: 'circle(0% at 50% 50%) fill-box'},
        {clipPath: 'circle(75% at 50% 50%) fill-box'},
      ], {duration: 520, delay, easing: 'cubic-bezier(.4, 0, .4, 1)'});
      for (const path of node.querySelectorAll('[data-muscle-rest]')) pulse(path, delay);
    }
    // Selection keeps its own animation without replaying appearance on the map.
    for (const node of selections) {
      for (const path of node.querySelectorAll('[data-muscle-rest]')) pulse(path);
      for (const glow of node.querySelectorAll('.muscle-selection-glow')) play(glow, 'selection', [
        {clipPath: 'circle(0% at 50% 50%) fill-box', opacity: 0},
        {clipPath: 'circle(45% at 50% 50%) fill-box', opacity: .24, offset: .45},
        {clipPath: 'circle(75% at 50% 50%) fill-box', opacity: .16},
      ]);
    }
  }
  return {update, finish, setHovered};
}
