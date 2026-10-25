/* Animate decorative anatomy only. The separate SVG controls stay stationary. */
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
  const play = (node, frames, delay = 0, duration = 520) => {
    if (typeof node.animate !== 'function') return;
    running.get(node)?.cancel();
    const animation = node.animate(frames, {
      duration, delay, easing: 'cubic-bezier(.22, .8, .3, 1)', fill: 'backwards',
    });
    running.set(node, animation);
    const clean = () => { if (running.get(node) === animation) running.delete(node); };
    animation.finished.then(clean, clean);
  };
  function update(root, {route = '', reduced = false} = {}) {
    for (const [node, animation] of running) if (!node.isConnected) { animation.cancel(); running.delete(node); }
    if (route !== previousRoute) { finish(); previous = new Map(); previousRoute = route; hovered = null; }
    if (reduced) finish();
    const next = new Map();
    artwork = [];
    for (const figure of root.querySelectorAll('.body-map-svg')) {
      const context = figure.dataset.bodyContext;
      const muscles = [...figure.querySelectorAll('.body-muscle-art[data-body-muscle]')];
      const controls = [...figure.querySelectorAll('.body-muscle[data-map-muscle]')];
      artwork.push(...muscles);
      muscles.forEach((node, index) => {
        const key = `${figure.dataset.bodyKey}:${node.dataset.bodyMuscle}`;
        const state = {context, value: node.dataset.bodyState, selected: node.dataset.bodySelected === 'true'};
        const before = previous.get(key);
        next.set(key, state);
        if (reduced) return;
        if (before && before.selected !== state.selected) {
          const control = controls.find(control => control.dataset.mapMuscle === node.dataset.bodyMuscle);
          const paths = [...node.querySelectorAll('[data-muscle-rest]'), ...(control?.querySelectorAll('[data-muscle-rest]') || [])];
          for (const path of paths) {
            const rest = path.dataset.muscleRest, flexed = path.dataset.muscleFlexed;
            play(path, [
              {d: `path("${before.selected ? flexed : rest}")`},
              {d: `path("${state.selected ? flexed : rest}")`},
            ], 0, 340);
          }
        }
        if (!before || before.context !== context || before.value !== state.value) {
          // Each anatomical piece has its own centre, including the mirrored
          // left/right muscles. Never clip the whole bilateral group or its controls.
          for (const piece of node.querySelectorAll('.body-muscle-piece')) play(piece, [
            {clipPath: 'circle(0% at 50% 50%) fill-box'},
            {clipPath: 'circle(75% at 50% 50%) fill-box'},
          ], Math.min(index * 18, 110));
        } else if (state.selected && !before.selected) {
          // A centre-out wash travels over the newly selected muscle; the
          // underlying anatomy stays fully visible, with a persistent selected tint.
          for (const piece of node.querySelectorAll('.body-muscle-piece')) {
            const glow = piece.querySelector('.muscle-selection-glow');
            if (glow) play(glow, [
              {clipPath: 'circle(0% at 50% 50%) fill-box', opacity: 0},
              {clipPath: 'circle(45% at 50% 50%) fill-box', opacity: .24, offset: .45},
              {clipPath: 'circle(75% at 50% 50%) fill-box', opacity: .16},
            ]);
          }
        }
      });
    }
    previous = next;
    setHovered(hovered);
  }
  return {update, finish, setHovered};
}
