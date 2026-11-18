const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let draft = {session_id:'', time_minutes:35, priority_exercises:[], unavailable_exercises:[]};
let result = null;
let sequence = 0;

function exerciseChoices(data) {
  return [...new Set((data.sets || []).filter(s => s.sessionId === draft.session_id && s.exercise.toLowerCase() !== 'unknown').map(s => s.exercise))];
}

function choices(data) {
  return exerciseChoices(data).map(name => `<div class="time-budget-choice"><strong>${escape(name)}</strong><label><input type="checkbox" name="priority" aria-label="Keep all sets for ${escape(name)}" value="${escape(name)}" ${draft.priority_exercises.includes(name)?'checked':''}> Keep all sets</label><label><input type="checkbox" name="unavailable" aria-label="${escape(name)} unavailable today" value="${escape(name)}" ${draft.unavailable_exercises.includes(name)?'checked':''}> Unavailable today</label></div>`).join('');
}

export function renderTimeBudgetResult(plan) {
  const a = plan.adaptation;
  const set = s => `${s.weight == null ? '—' : escape(s.weight) + ' kg'} × ${s.reps == null ? '—' : escape(s.reps)}`;
  return `<div tabindex="-1" id="time-budget-result"><h3>${escape(plan.name)}</h3><p><strong>${a.budgetExceeded?'Needs more time':'Estimated duration'}: ${escape(a.estimatedMinutes)} min</strong> · budget ${escape(a.timeBudget)} min</p><p>${escape(a.limitations)}</p><ul>${a.changes.map(c=>`<li>${escape(c)}</li>`).join('')}</ul><div class="time-budget-targets">${plan.exercises.map(e=>`<article><h4>${escape(e.name)}${e.priority?' · priority':''}</h4><p>${e.proposed.map(set).join(' · ')}</p><small>${escape(e.reason)}</small><p class="muted">Timing: ${escape(a.timing[e.name].source)}</p></article>`).join('')}</div><details><summary>Weekly sets and proposed changes</summary><p>Recorded this Monday–today; the planned columns are alternatives, not completed sets.</p><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Recorded this week</th><th>Original plan</th><th>Shortened plan</th></tr></thead><tbody>${a.setImpact.map(r=>`<tr><td>${escape(r.exercise)}</td><td>${r.recordedThisWeek}</td><td>${r.originalPlannedSets}</td><td>${r.adaptedPlannedSets}</td></tr>`).join('')}</tbody></table></div></details></div>`;
}

export function renderTimeBudget(data, baselineId) {
  const ids = new Set((data.sets || []).filter(s=>s.exercise.toLowerCase()!=='unknown').map(s=>s.sessionId));
  const sessions = (data.workouts || []).filter(w=>ids.has(w.id)).slice().sort((a,b)=>(b.time || b.date).localeCompare(a.time || a.date));
  if (!sessions.length) return '<section class="panel time-budget"><h2>Short on time?</h2><p>Log or sync a workout to create a shorter proposal from its recorded sets.</p></section>';
  if (!sessions.some(w=>w.id===draft.session_id)) {
    draft = {...draft, session_id:sessions.find(w=>w.id===baselineId)?.id || sessions[0].id, priority_exercises:[], unavailable_exercises:[]};
    result = null;
  }
  return `<section class="panel time-budget"><h2>Short on time?</h2><p>Choose any completed workout and protect your priority exercises. Review the cuts before training; your history stays unchanged.</p><form id="time-budget-form"><div class="time-budget-fields"><label>Start from<select name="session_id">${sessions.map(w=>`<option value="${escape(w.id)}" ${w.id===draft.session_id?'selected':''}>${escape(w.name)} · ${escape(w.date)}</option>`).join('')}</select></label><label>Minutes available<input name="time_minutes" type="number" min="10" max="180" required value="${draft.time_minutes}"></label></div><div id="time-budget-choices">${choices(data)}</div><p class="muted">Priority exercises keep every set. Other exercises lose later sets first. If the protected work cannot fit, the proposal says so.</p><button class="button button-dark" type="submit">Preview shorter workout</button><p class="form-error" role="alert"></p></form><div id="time-budget-output" aria-live="polite">${result?renderTimeBudgetResult(result):''}</div></section>`;
}

export function installTimeBudget(getData) {
  function readForm(form) {
    draft.session_id = form.elements.session_id.value;
    draft.time_minutes = Number(form.elements.time_minutes.value);
    draft.priority_exercises = [...form.querySelectorAll('[name="priority"]:checked')].map(e=>e.value);
    draft.unavailable_exercises = [...form.querySelectorAll('[name="unavailable"]:checked')].map(e=>e.value);
  }
  function changed(event) {
    const form = event.target.closest('#time-budget-form');
    if (!form) return;
    ++sequence;
    result = null;
    const next = form.elements.session_id.value;
    if (draft.session_id !== next) {
      draft = {...draft, session_id:next, priority_exercises:[], unavailable_exercises:[]};
      form.querySelector('#time-budget-choices').innerHTML = choices(getData());
    }
    readForm(form);
    document.querySelector('#time-budget-output').innerHTML = '';
  }
  document.addEventListener('change', changed);
  document.addEventListener('input', changed);
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (form.id !== 'time-budget-form') return;
    event.preventDefault();
    readForm(form);
    const request = ++sequence;
    const button = form.querySelector('[type="submit"]');
    const error = form.querySelector('.form-error');
    button.disabled = true;
    error.textContent = '';
    try {
      const response = await fetch('/api/plan-preview', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(draft), signal:AbortSignal.timeout(15000)});
      const plan = await response.json();
      if (!response.ok) throw new Error(plan.error || 'Could not prepare a shorter workout.');
      if (request !== sequence || !form.isConnected) return;
      result = plan;
      document.querySelector('#time-budget-output').innerHTML = renderTimeBudgetResult(plan);
      document.querySelector('#time-budget-result').focus();
    } catch (e) {
      if (request === sequence) error.textContent = e.message;
    } finally {
      button.disabled = false;
    }
  });
}
