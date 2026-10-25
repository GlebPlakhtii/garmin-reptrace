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
      {d: rest, offset: 0, easing: 'cubic-bezier(.4, 0, .2, 1)'},
      {d: flexed, offset: .42},
      {d: flexed, offset: .52, easing: 'cubic-bezier(.4, 0, .2, 1)'},
      {d: rest, offset: 1},
    ], {duration: 900, delay, easing: 'linear'});
  };
  function update(root, {route = '', reduced = false} = {}) {
    for (const [node, channels] of running) if (!node.isConnected) {
      for (const animation of channels.values()) animation.cancel();
      running.delete(node);
    }
    if (route !== previousRoute) { finish(); previous = new Map(); previousRoute = route; hovered = null; }
    if (reduced) finish();
    const next = new Map(), selections = [];
    let changed = false;
    artwork = [];
    for (const figure of root.querySelectorAll('.body-map-svg')) {
      const context = figure.dataset.bodyContext;
      const muscles = [...figure.querySelectorAll('.body-muscle-art[data-body-muscle]')];
      artwork.push(...muscles);
      for (const node of muscles) {
        const key = `${figure.dataset.bodyKey}:${node.dataset.bodyMuscle}`;
        const state = {context, value: node.dataset.bodyState, selected: node.dataset.bodySelected === 'true'};
        const before = previous.get(key);
        next.set(key, state);
        if (!before || before.context !== context || before.value !== state.value) changed = true;
        if (before && state.selected && !before.selected) selections.push(node);
      }
    }
    changed ||= previous.size !== next.size;
    previous = next;
    setHovered(hovered);
    if (reduced) return;
    if (changed) {
      for (const node of artwork) {
        // Reveal each left/right lobe from its own centre, then swell and settle.
        for (const piece of node.querySelectorAll('.body-muscle-piece')) play(piece, 'entry', [
          {clipPath: 'circle(0% at 50% 50%) fill-box'},
          {clipPath: 'circle(75% at 50% 50%) fill-box'},
        ], {duration: 320});
        for (const path of node.querySelectorAll('[data-muscle-rest]')) pulse(path, 320);
      }
    } else {
      // Selection animates just the chosen group; its border remains fixed.
      for (const node of selections) {
        for (const path of node.querySelectorAll('[data-muscle-rest]')) pulse(path);
        for (const glow of node.querySelectorAll('.muscle-selection-glow')) play(glow, 'selection', [
          {clipPath: 'circle(0% at 50% 50%) fill-box', opacity: 0},
          {clipPath: 'circle(45% at 50% 50%) fill-box', opacity: .24, offset: .45},
          {clipPath: 'circle(75% at 50% 50%) fill-box', opacity: .16},
        ]);
      }
    }
  }
  return {update, finish, setHovered};
}
