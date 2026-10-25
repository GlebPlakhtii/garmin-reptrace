import {estimatedStrengthHistory, recordedVolumeSets, exerciseMuscles, compareExerciseStack, muscleColor, exerciseColor, isAssistedExercise, adjustedVolumeSets, exerciseVolumeRule, present, sumKnown, exerciseSummaries, filterData, weeklyWorkouts, chartPoints, csvForSets, csvForRecovery, MUSCLE_GROUPS, DEFAULT_MUSCLES, matchingRepHistory, volumeByWeek, weeklyVolumeHistory, weekStart, plateauSignals, compareWorkouts, recoveryComparison, goalProgress, presetRange, chartDateRange, timeAxisDates, muscleMapWeeks, muscleWeekSummary, muscleWeekComparison} from './model.mjs'; import {renderMuscleMap} from './muscle-map.mjs'; import {recoveryPage as renderOperationHistory,recoveryReview} from './recovery.mjs';

const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (value, digits = 0) => present(value) ? new Intl.NumberFormat('en-GB', {maximumFractionDigits:digits}).format(value) : '—';
const loadLabel = (exercise,value) => ['Pull Up','Push Up','Dip'].includes(exercise)&&value===0?'BW':kg(value);
const kg = value => present(value) ? `${number(value, 1)} <span class="unit">kg</span>` : '—';
const date = (value, full = false) => value ? new Date(value + 'T12:00:00Z').toLocaleDateString('en-GB', {day:'numeric', month:'short', ...(full ? {year:'numeric'} : {}), timeZone:'UTC'}) : '—';
const duration = seconds => present(seconds) ? seconds >= 60 ? `${number(seconds / 60)} min` : `${number(seconds)} sec` : '—';
const icons = {
  menu:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  liftPress:'<path d="M3 17h16m-3 0v4M6 17v4M8 14h7l-2-4V5m-3 0h6M10 3v4m6-4v4"/><circle cx="5" cy="12" r="2"/>',
  liftPull:'<path d="M4 3h16M7 3v5l5 3 5-3V3m-5 8v5m0 0-4 5m4-5 4 5"/><circle cx="12" cy="7" r="2"/>',
  liftSquat:'<circle cx="12" cy="4" r="2"/><path d="M5 8h14M5 6v4m14-4v4m-7-2-2 5 5 3-3 5h5M10 13l-5 3 2 5"/>',
  liftHinge:'<circle cx="16" cy="5" r="2"/><path d="m14 8-7 4 3 4-2 5H5m2-9 5 2 2 7h3M14 8v9M9 18h11m-11-2v4m11-4v4"/>',
  liftCurl:'<path d="M6 20V9m0 11h11l3-8-4-2-3 6H9M13 6h8m-8-2v4m8-4v4"/>',
  liftCore:'<circle cx="5" cy="13" r="2"/><path d="m8 15 5 2 3-7 5 3M3 21h18m-8-4 6 2"/>',
  liftRow:'<circle cx="7" cy="5" r="2"/><path d="m8 8 3 5-3 5H3m8-5 4 5h5M8 8l6 2 5-3m0-2v5M3 21h18"/>',
  next:'<circle cx="12" cy="12" r="9"/><path d="m10 8 5 4-5 4V8Z"/>',
  insights:'<path d="M4 3v17h17M7 14l4-4 4 2 6-7m-5 0h5v5"/>',
  volume:'<path d="M3 21h18"/><rect x="5" y="12" width="3" height="6" rx="1"/><rect x="11" y="7" width="3" height="11" rx="1"/><rect x="17" y="3" width="3" height="15" rx="1"/>',
  compare:'<rect x="3" y="4" width="6" height="16" rx="1.5"/><rect x="15" y="4" width="6" height="16" rx="1.5"/><path d="M6 8v4m12 0v4m-7-8h2m-2 8h2"/>',
  logging:'<path d="M13 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 3l5 5M10 14l1-5 7-7 5 5-7 7-6 1Z"/>',
  goals:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  garmin:'<rect x="6" y="6" width="12" height="12" rx="3"/><path d="m8 6 1-4h6l1 4m-8 12 1 4h6l1-4M9 12h2l1-2 1 4 2-2"/>',
  preferences:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
  overview:'<rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/><rect x="3" y="14" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/>',
  exercises:'<path d="m6 6 12 12M3 9l6-6m6 18 6-6M2 6l4-4m12 20 4-4"/><path d="m4 11 7-7m2 16 7-7"/>',
  workouts:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-14 4h2m4 0h2m-8 3h2"/>',
  records:'<path d="M8 3h8v7a4 4 0 0 1-8 0V3Zm4 11v5m-4 2h8M8 5H4v3a4 4 0 0 0 4 4m8-7h4v3a4 4 0 0 1-4 4"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  up:'<path d="m6 15 9-9M6 6h9v9"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 15v5h16v-5"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  recovery:'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  nutrition:'<path d="M4 3v9a4 4 0 0 0 4 4h1m-1-13v18M4 8h8m6-5v18m0-18c4 3 4 8 0 11"/>',
  sync:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
  activity:'<path d="M2 12h4l3-8 6 16 3-8h4"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
};
const icon = (name, extra = '') => `<svg class="icon ${extra}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.activity}</svg>`;
const state = {data:null, page:'overview', range:'30', from:'', to:'', source:'all', selected:'all', muscleGroup:'all', search:'', metric:'weight', exerciseVolumeMode:readExerciseVolumeMode(), limit:24, workoutSearch:'', recordSort:'count', recoveryLimit:14, refreshError:false, repTarget:5, plateauWindow:4, insightExercise:'all', recoveryMetric:'sleepHours', recoveryThreshold:7, volumeMode:'muscle', volumeMetric:'volume', volumeGroup:{muscle:'all',exercise:'all'}, volumeWeek:'', mapWeek:'', mapWeekLimit:4, mapMuscle:'all', mapSecondary:true, mapCompare:1, volumeCards:12, volumeLimit:100, planType:'upper1', compareLeft:'', compareRight:'', draft:null, foodDeleteId:'', nutritionDate:''};
const pages = {operations:'Operation recovery',overview:'Overview', nutrition:'Nutrition', sync:'Garmin sync', next:'Next session', exercises:'Exercises', workouts:'Workouts', records:'Personal records', recovery:'Recovery', insights:'Insights', volume:'Weekly volume', compare:'Compare workouts', logging:'Log & edit', goals:'Goals',garmin:'Garmin workouts',preferences:'Preferences'};
let toastTimer;
let loadSequence = 0;
let operationSequence = 0;
let operationReviewSequence = 0;

function today() {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:state.data?.timezone || 'Europe/Kyiv', year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const part = key => parts.find(p => p.type === key).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function localDay(stamp) {
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:state.data?.timezone||'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(stamp));
  const part=key=>parts.find(p=>p.type===key).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function range() {
  if (state.range === 'custom') return {from:state.from, to:state.to};
  return presetRange(state.range,today());
}
function readExerciseVolumeMode() {
  try { return localStorage.getItem('reptrace.exerciseVolumeMode')==='adjusted'?'adjusted':'recorded'; } catch { return 'recorded'; }
}
function recordedExerciseVolume() { return state.page==='exercises'&&state.exerciseVolumeMode==='recorded'; }
function exerciseVolumeLabel() { return recordedExerciseVolume()?'Recorded load × reps':'Adjusted volume'; }
function exerciseVolumeExplanation(recorded=recordedExerciseVolume()) {
  return recorded
    ? 'Recorded kilograms × repetitions only. No bodyweight, movement factor, or per-dumbbell conversion is added. Assistance loads and missing inputs are excluded.'
    : 'Includes estimated bodyweight contributions and exercise factors from Preferences. Missing bodyweight and unreviewed movement profiles are excluded.';
}
function volumeCoverage(rows) {
  const known=rows.filter(r=>present(r.volume)).length;
  const reasons=[];
  if(rows.some(r=>r.missingBodyweight))reasons.push('Body weight is missing for some movements. Add dated weigh-ins in Recovery or a fallback in Preferences.');
  if(rows.some(r=>r.unreviewed))reasons.push('Some movement profiles need review in Preferences.');
  if(rows.some(r=>!present(r.weight)||!present(r.reps)))reasons.push('Some sets have no numeric load or rep count; see their source notes.');
  if(rows.some(r=>r.missingLoad))reasons.push('Some zero-load movements need their resistance convention identified.');
  if(recordedExerciseVolume()&&rows.some(r=>r.assistance))reasons.push('Assistance loads are excluded from recorded resistance volume.');
  return `${known} of ${rows.length} sets included. ${reasons.join(' ')}`;
}
function current() {
  const filtered = filterData(state.data, range(), state.source);
  filtered.sets=recordedExerciseVolume()?recordedVolumeSets(filtered.sets,state.data.volumeSettings||{}):adjustedVolumeSets(filtered.sets,state.data.recovery||[],state.data.volumeSettings||{});
  const exercises = exerciseSummaries(filtered.sets);
  if(state.muscleGroup!=='all'&&!exercises.some(e=>(state.data?.muscleOverrides?.[e.name]||DEFAULT_MUSCLES[e.name]||'Unassigned')===state.muscleGroup))state.muscleGroup='all';
  if (state.selected!=='all' && !exercises.some(e => e.name === state.selected)) state.selected = 'all';
  return {...filtered, exercises, selected:state.selected==='all'?allExerciseSummary(exercises):exercises.find(e => e.name === state.selected)};
}
function badge(source) {
  return `<span class="source-badge ${source === 'manual' ? 'manual' : 'garmin'}"><span></span>${source === 'manual' ? 'Manual log' : 'Garmin'}</span>`;
}
function nav() {
  const primary=['overview','exercises','workouts','volume','recovery','nutrition','garmin','insights'];
  const groups=[['Training',['next','records','compare','goals']],['Management',['logging','sync','operations','preferences']]];
  const link=(key,extra='')=>`<a href="#${key}" aria-label="${pages[key]}" title="${pages[key]}" class="topnav-link ${extra} ${key===state.page?'active':''}" ${key===state.page?'aria-current="page"':''}>${icon(key)}<span>${pages[key]}</span></a>`;
  const moreActive=!primary.includes(state.page);
  $('#navigation').innerHTML=`<div class="topnav-primary">${primary.map(key=>link(key)).join('')}<details class="topnav-more" id="more-navigation"><summary class="topnav-more-toggle ${moreActive?'active':''}" aria-label="More pages">${icon('menu')}<span>More</span>${icon('chevron','topnav-chevron')}</summary><div class="topnav-menu"><div class="topnav-menu-groups">${groups.map(([title,keys])=>`<div class="topnav-group" role="group" aria-label="${title}"><div class="topnav-group-label">${title}</div>${keys.map(key=>link(key,'topnav-menu-link')).join('')}</div>`).join('')}</div><div class="topnav-menu-footer"><div class="connection"><span class="status-dot"></span>${state.refreshError?'Connection unavailable':state.data?'Connected to your history':'Your training history'}</div></div></div></details></div>`;
  $('#breadcrumb-title').textContent = pages[state.page];
  $('#refresh').innerHTML = icon('refresh');
}

function filters() {
  if (['nutrition','sync','goals'].includes(state.page)) return '';
  return `<div class="header-actions"><label class="select-wrap" ${state.page==='recovery'?'hidden':''}><span class="sr-only">Record source</span><select id="source-filter"><option value="all" ${state.source === 'all' ? 'selected' : ''}>All records</option><option value="garmin" ${state.source === 'garmin' ? 'selected' : ''}>Garmin sets</option><option value="manual" ${state.source === 'manual' ? 'selected' : ''}>Manual sets</option></select></label><button class="button button-dark" data-action="export" aria-label="Download CSV" title="Export recorded loads and unadjusted kg × reps in the current date/source filters; workout search applies on Workouts">${icon('download')}<span>CSV</span></button><button class="button button-dark" data-action="export-excel" aria-label="Export sessions to Excel" title="Export sessions in the current date and source filters">${icon('download')}<span>Excel</span></button><button class="button button-dark" data-action="export-all" aria-label="Export all data, including every set" title="All history, all sources, every set including Unknown">${icon('download')}<span>All data</span></button></div>`;
}
function header(title, description) {
  return `<section class="page-heading"><div><div class="eyebrow">YOUR TRAINING, OVER TIME</div><h1>${title}<span class="heading-dot">.</span></h1><p>${description}</p></div>${filters()}</section>${dateRangeBar()}`;
}
function stats(view) {
  const weeks = weeklyWorkouts(view.workouts, today());
  const currentWeek = weeks.at(-1).count;
  const items = [
    {label:'Training sessions',value:number(view.workouts.length),sub:'Unique workouts in this range',icon:'workouts'},
    {label:'Recorded sets',value:number(view.sets.length),sub:`Across ${view.exercises.length} exercises`,icon:'exercises'},
    {label:'Recorded reps',value:number(sumKnown(view.sets.map(s => s.reps))),sub:`${view.sets.filter(s => !present(s.reps)).length} sets have no recorded reps`,icon:'activity'},
    {label:'Sessions this week',value:number(currentWeek),sub:'Monday to today · within your filters',icon:'overview'},
  ];
  return `<section class="stats-strip" aria-label="Training summary">${items.map(item => `<article class="stat"><div class="stat-top">${item.label}${icon(item.icon)}</div><strong>${item.value}</strong><small>${item.sub}</small></article>`).join('')}</section>`;
}
function sparkline(exercise) {
  const values = exercise.history.filter(h => present(h.weight)).map(h => h.weight);
  if (values.length < 2) return '<span class="spark-placeholder">—</span>';
  const min = Math.min(...values), max = Math.max(...values);
  const points = values.map((v,i) => `${2 + i / (values.length - 1) * 72},${24 - (v - min) / (max - min || 1) * 18}`).join(' ');
  return `<svg style="color:${exerciseVisual(exercise.name).color}" class="sparkline" viewBox="0 0 78 30" aria-hidden="true"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
// Shared exercise appearance for movement badges and workout bars.
function exerciseVisual(name) {
  const types=[
    [/squat|lunge|leg press|step.?up/i,'liftSquat'],
    [/deadlift|good morning|hip thrust|back extension/i,'liftHinge'],
    [/row/i,'liftRow'],
    [/pull.?up|chin.?up|pulldown|pull down/i,'liftPull'],
    [/curl/i,'liftCurl'],
    [/crunch|plank|sit.?up|leg raise|ab wheel|twist/i,'liftCore'],
    [/press|push.?up|dip|fly|flye/i,'liftPress'],
  ];
  const match=types.find(([pattern])=>pattern.test(name));
  return {icon:match?.[1]||'exercises',color:exerciseColor(name,state.data?.muscleOverrides||{})};
}
function exerciseBadge(name) {
  const visual=exerciseVisual(name);
  return `<span class="exercise-badge" style="--exercise-accent:${visual.color}" aria-hidden="true">${icon(visual.icon)}</span>`;
}
function muscleTag(name) {
  const group=state.data?.muscleOverrides?.[name]||DEFAULT_MUSCLES[name];
  return group&&group!=='Unassigned'?`<span class="muscle-tag" style="--muscle-accent:${volumeColor(group)}">${escape(group)}</span>`:'';
}
function filteredLibraryExercises(exercises) {
  const query=state.search.trim().toLowerCase();
  return exercises.filter(e=>{
    const muscle=state.data?.muscleOverrides?.[e.name]||DEFAULT_MUSCLES[e.name]||'Unassigned';
    return (state.muscleGroup==='all'||state.muscleGroup===muscle)&&(!query||e.name.toLowerCase().includes(query)||muscle.toLowerCase().includes(query));
  });
}
function allExerciseSummary(exercises) {
  const summaries=filteredLibraryExercises(exercises),rows=summaries.flatMap(e=>e.rows);
  return {all:true,name:state.muscleGroup==='all'?'All exercises':state.muscleGroup+' exercises',summaries,rows,count:rows.length};
}
function selectExerciseMuscle(group) {
  state.muscleGroup=group;state.selected='all';state.limit=24;
  for(const button of document.querySelectorAll('[data-exercise-muscle]')){
    const active=button.dataset.exerciseMuscle===group;
    button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));
  }
  refreshExerciseLibrary();
}
function refreshExerciseLibrary() {
  const view=current(),list=$('#exercise-list');
  list.innerHTML=libraryRows(view.exercises);list.scrollTop=0;
  if(state.selected==='all'){
    const detail=$('.exercise-detail');
    detail.innerHTML=progressPanel(view.selected)+setsTable(view.selected,state.page==='overview');bindChart(detail);
  }
}
function libraryRows(exercises) {
  const query=state.search.trim().toLowerCase();
  const groups=MUSCLE_GROUPS.filter(group=>state.muscleGroup==='all'||group===state.muscleGroup).map(group=>({group,exercises:exercises.filter(e=>{
    const muscle=state.data?.muscleOverrides?.[e.name]||DEFAULT_MUSCLES[e.name]||'Unassigned';
    return muscle===group&&(!query||e.name.toLowerCase().includes(query)||muscle.toLowerCase().includes(query));
  })})).filter(group=>group.exercises.length);
  return `<button class="exercise-row ${state.selected==='all'?'selected':''}" data-exercise="all" aria-pressed="${state.selected==='all'}">${icon('volume')}<span class="exercise-row-name"><strong>All exercises</strong><small>${filteredLibraryExercises(exercises).length} exercises · combined history</small></span>${icon('chevron')}</button>` + (groups.length ? groups.map(({group,exercises},index)=>`<section class="exercise-muscle-group" aria-labelledby="exercise-muscle-${index}"><h3 class="exercise-muscle-heading" id="exercise-muscle-${index}" style="--muscle-accent:${volumeColor(group)}"><span>${escape(group)}</span><span class="count-chip">${exercises.length}</span></h3>${exercises.map(e => `<button class="exercise-row ${e.name === state.selected ? 'selected' : ''}" data-exercise="${escape(e.name)}" aria-pressed="${e.name === state.selected}">${exerciseBadge(e.name)}<span class="exercise-row-name"><strong>${exerciseLabel(e.name)}</strong><small>${e.sessions} workouts <span>·</span> ${e.count} sets</small></span>${sparkline(e)}${icon('chevron')}</button>`).join('')}</section>`).join('') : '<div class="small-empty"><strong>No matching exercises</strong><p>Try an exercise or muscle group name, or clear the search field.</p></div>');
}
function muscleFilters(exercises) {
  const groups=MUSCLE_GROUPS.map(group=>({group,count:exercises.filter(e=>(state.data?.muscleOverrides?.[e.name]||DEFAULT_MUSCLES[e.name]||'Unassigned')===group).length})).filter(g=>g.count);
  return `<div class="library-muscle-filters" role="group" aria-label="Filter exercises by muscle group">${[{group:'all',count:exercises.length},...groups].map(({group,count})=>`<button type="button" class="muscle-filter ${state.muscleGroup===group?'active':''}" data-exercise-muscle="${escape(group)}" aria-pressed="${state.muscleGroup===group}" style="--muscle-accent:${group==='all'?'var(--green-strong)':volumeColor(group)}"><span class="muscle-filter-dot" aria-hidden="true"></span><span>${group==='all'?'All muscles':escape(group)}</span><small>${count}</small></button>`).join('')}</div>`;
}
function library(view) {
  return `<aside class="exercise-library panel"><div class="library-heading"><div><span class="eyebrow">YOUR LIFTS</span><h2>Exercises <span class="count-chip">${view.exercises.length}</span></h2></div></div>${muscleFilters(view.exercises)}<label class="search-box">${icon('search')}<span class="sr-only">Find an exercise or muscle group</span><input id="exercise-search" type="search" placeholder="Find an exercise or muscle…" value="${escape(state.search)}" autocomplete="off"></label><div class="list-caption">BY MUSCLE · MOST SETS FIRST</div><div class="exercise-list" id="exercise-list">${libraryRows(view.exercises)}</div><div class="library-footer"><span class="mini-dot"></span> Garmin + your manual history</div></aside>`;
}
function chart(exercise,metric=state.metric) {
  const field=metric==='matched'?'weight':metric;
  const history=metric==='matched'?matchingRepHistory(exercise.rows,state.repTarget):exercise.history;
  if(!history.length)return '<div class="chart-empty"><strong>No sets at this exact rep count.</strong><p>Choose another rep count or date range.</p></div>';
  const points=chartPoints(history,field),known=points.filter(p=>present(p.value));
  if(!known.length)return `<div class="chart-empty"><strong>${field==='volume'?exerciseVolumeLabel()+' is unavailable':`No recorded ${field==='estimatedMax'?'1RM estimates':'loads'} for this exercise`}</strong><p>${field==='volume'?escape(volumeCoverage(exercise.rows)):'Missing values stay missing. You can still explore recorded sets below.'}</p></div>`;
  const W=Math.max(800,points.length*14+90),H=270,pad={l:65,r:20,t:30,b:42};
  const width=W-pad.l-pad.r,height=H-pad.t-pad.b,step=width/points.length;
  const top=Math.max(1,...known.map(p=>p.value))*1.12;
  const x=i=>pad.l+step*(i+.5),y=value=>pad.t+height-value/top*height;
  const unit=field==='volume'?(recordedExerciseVolume()?'recorded kg·reps':'adjusted kg·reps'):'kg',color=exerciseVisual(exercise.name).color;
  const indices=[...new Set([0,Math.round((points.length-1)/3),Math.round((points.length-1)*2/3),points.length-1])];
  let previous=null;
  const bars=points.map((p,i)=>{
    const barWidth=Math.max(2,Math.min(38,step*.68));
    if(!present(p.value))return `<g class="workout-missing" data-session="${escape(p.id)}" tabindex="0" role="button" aria-label="${escape(date(p.date,true))}: metric not recorded; open workout"><title>${date(p.date,true)}: metric not recorded</title><text x="${x(i)}" y="${y(0)-8}" text-anchor="middle" class="chart-label">?</text></g>`;
    const label=`${date(p.date,true)} · ${number(p.value,1)} ${unit}`;
    const contributions=new Map();
    if(exercise.stacked)for(const row of history[i].rows){
      if(!present(row.volume))continue;
      const name=row.chartExercise;
      contributions.set(name,(contributions.get(name)||0)+row.volume);
    }
    let accumulated=0;
    const segments=[...contributions].sort(([a],[b])=>compareExerciseStack(a,b,state.data?.muscleOverrides||{})).filter(([,value])=>value>0).map(([name,value])=>{
      accumulated+=value;
      const segmentLabel=`${date(p.date,true)} · ${name} · ${number(value,1)} ${unit}`;
      return `<rect class="workout-segment" x="${x(i)-barWidth/2}" y="${y(accumulated)}" width="${barWidth}" height="${value/top*height}" fill="${exerciseVisual(name).color}" data-exercise-color="${escape(name)}" data-session="${escape(p.id)}" data-point-label="${escape(segmentLabel)}" data-point-value="${value}" data-point-unit="${unit}" data-point-no-comparison="true" tabindex="-1" role="button" aria-label="${escape(segmentLabel)}; open workout"><title>${escape(segmentLabel)}</title></rect>`;
    }).join('');
    const totalLabel=label+(exercise.stacked?'\n'+[...contributions].map(([name,value])=>`${name}: ${number(value,1)} ${unit}`).join('\n'):'');
    const result=`<rect class="chart-point workout-bar" x="${x(i)-barWidth/2}" y="${p.value===0?y(0)-3:y(p.value)}" width="${barWidth}" height="${Math.max(3,p.value/top*height)}" rx="3" fill="${segments?'transparent':color}" tabindex="0" role="button" data-session="${escape(p.id)}" data-point-previous="${previous??''}" data-point-value="${p.value}" data-point-unit="${unit}" data-point-label="${escape(totalLabel)}" aria-label="${escape(totalLabel)}; open workout"><title>${escape(totalLabel)}</title></rect>${segments}${points.length<=12?`<text x="${x(i)}" y="${y(p.value)-9}" text-anchor="middle" class="chart-label">${number(p.value,1)}</text>`:''}`;
    previous=p.value;return result;
  }).join('');
  return `<div class="workout-chart-scroll"><div class="chart-wrap" id="progress-chart" style="min-width:${Math.max(0,points.length*12+90)}px"><div class="chart-tooltip" role="status"></div><svg class="progress-svg workout-bars-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${escape(exercise.name)} ${field} per workout in ${unit}. One bar per workout. Select a bar to open its workout." data-time-start="${new Date(points[0].date).getTime()}" data-time-end="${new Date(points.at(-1).date).getTime()}" data-workout-dates="${escape(JSON.stringify(points.map(p=>p.date)))}" data-plot-left="${pad.l}" data-plot-right="${W-pad.r}" data-plot-top="${pad.t}" data-plot-bottom="${H-pad.b}">${[0,.25,.5,.75,1].map(f=>`<line x1="${pad.l}" x2="${W-pad.r}" y1="${y(top*f)}" y2="${y(top*f)}" stroke="var(--line)" stroke-dasharray="3 5"/><text x="${pad.l-10}" y="${y(top*f)+4}" text-anchor="end" class="chart-label">${number(top*f,top<10?1:0)}</text>`).join('')}${bars}${indices.map(i=>`<text x="${x(i)}" y="${H-12}" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}" class="chart-label">${date(points[i].date,true)}</text>`).join('')}</svg></div></div><p class="workout-chart-caption">One bar per workout · chronological order · ? means the metric was not recorded</p>`;
}
function allExercisesPanel(exercise) {
  const rows=exercise.rows,combined=exerciseSummaries(rows.map(r=>({...r,chartExercise:r.exercise,exercise:exercise.name})))[0];
  if(combined)combined.stacked=true;
  if(state.metric==='estimatedMax')state.metric='volume';
  return `<section class="panel progress-panel"><div class="panel-heading"><div><span class="eyebrow">COMBINED TRAINING</span><h2>${escape(exercise.name)}</h2><p>${exercise.summaries.length} exercises · ${new Set(rows.map(r=>r.sessionId)).size} workouts · ${rows.length} sets</p></div></div><div class="exercise-metrics"><div><small>Recorded sets</small><strong>${rows.length}</strong></div><div><small>Recorded reps</small><strong>${number(sumKnown(rows.map(r=>r.reps)))}</strong></div><div><small>${exerciseVolumeLabel()}</small><strong>${number(sumKnown(rows.map(r=>r.volume)))} <small>kg·reps</small></strong></div></div><div class="chart-controls"><span class="chart-key"><i></i>${exerciseVolumeLabel()} · one bar per workout</span></div>${combined?chart(combined,'volume'):'<p class="small-empty">No matching exercises in these filters.</p>'}<p class="feature-note">Each bar shows one workout, with colored segments for each exercise’s contribution. Colors match the exercise badges. Select a bar to open that workout. Strength records remain separate for each lift. ${exerciseVolumeExplanation()} ${escape(volumeCoverage(rows))}</p><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Sets</th><th>Best load / least assistance</th><th>Best est. 1RM</th><th>${exerciseVolumeLabel()}</th></tr></thead><tbody>${exercise.summaries.map(e=>`<tr><td><button class="record-exercise" data-exercise="${escape(e.name)}"><i class="exercise-color-dot" style="background:${exerciseVisual(e.name).color}" aria-hidden="true"></i>${exerciseLabel(e.name)}</button></td><td>${e.count}</td><td>${kg(e.bestWeight)}</td><td>${kg(e.bestMax)}</td><td>${number(e.volume)} kg·reps</td></tr>`).join('')}</tbody></table></div></section>`;
}
function progressPanel(exercise) {
  if(exercise?.all)return allExercisesPanel(exercise);
  if (!exercise) return '<section class="panel empty-panel"><h2>No exercise records in this range</h2><p>Choose a wider date range or a different record source.</p></section>';
  const isPositive = present(exercise.change) && (exercise.assisted?exercise.change<0:exercise.change>0);
  const change = present(exercise.change) ? `${exercise.change > 0 ? '+' : ''}${number(exercise.change,1)} kg` : '—';
  return `<section class="panel progress-panel" style="--metric-color:${exerciseVisual(exercise.name).color}"><div class="panel-heading"><div><span class="eyebrow">EXERCISE PROGRESS</span><h2>${exerciseLabel(exercise.name)}</h2>${muscleTag(exercise.name)}<p>${exercise.sessions} workouts <span>·</span> ${exercise.count} sets <span>·</span> Last trained ${date(exercise.latestDate,true)}</p></div>${exerciseBadge(exercise.name)}</div><div class="exercise-metrics"><div><small>${exercise.assisted?'Least recorded assistance':'Best recorded load'}</small><strong>${kg(exercise.bestWeight)}</strong></div><div><small>First → latest load</small><strong class="change ${isPositive ? 'positive' : ''}">${isPositive ? icon('up') : ''}${change}</strong><span>${present(exercise.firstWeight) ? `${number(exercise.firstWeight,1)} → ${number(exercise.latestWeight,1)} kg` : 'No recorded load'}</span></div><div><small>Estimated 1RM best</small><strong>${kg(exercise.bestMax)}</strong></div></div><div class="chart-controls"><div class="segmented" role="group" aria-label="Chart metric">${[['weight',exercise.assisted?'Least assistance':'Heaviest set'],['estimatedMax','Est. 1RM'],['volume',exerciseVolumeLabel()],['matched','Matching reps']].map(([key,label]) => `<button data-metric="${key}" class="${key===state.metric?'active':''}" aria-pressed="${key===state.metric}">${label}</button>`).join('')}</div><span class="chart-key"><i></i>${state.metric === 'volume' ? exerciseVolumeLabel() : state.metric === 'estimatedMax' ? 'Estimate, not a measured max' : state.metric==='matched'?`${state.repTarget}-rep sets only`:'One bar per workout'}</span></div>${state.metric==='matched'?`<div class="matched-control">${repControl()}<span>Exactly ${state.repTarget} reps per set</span></div>`:''}${chart(exercise)}<div class="chart-footnote">${state.metric === 'estimatedMax' ? 'Epley estimate from eligible weighted sets of 1–10 reps; bodyweight and assisted categories excluded.' : state.metric === 'volume' ? exerciseVolumeExplanation()+' '+escape(volumeCoverage(exercise.rows)) : exercise.assisted?'Assistance is subtracted from resistance: lower kg means less help. Each bar shows the least recorded assistance; zero means unassisted. Compare at matching reps.':'Compare load with reps and exercise technique. Missing loads remain gaps; recorded zero is preserved.'}</div></section>`;
}
function setsTable(exercise, compact = false) {
  if (!exercise) return '';
  const rows = [...exercise.rows].sort((a,b) => b.date.localeCompare(a.date) || b.time.localeCompare(a.time) || (a.number||0)-(b.number||0));
  const limit = compact ? 6 : state.limit;
  return `<section class="panel sets-panel"><div class="table-heading"><div><h2>${compact ? 'Latest sets' : 'Set history'}</h2><p>Every recorded set, with its original source.</p></div>${compact ? '<a href="#exercises" class="text-link" data-action="all-sets">All sets '+icon('arrow')+'</a>' : `<span class="count-chip">${exercise.count} sets</span>`}</div><div class="table-scroll"><table><thead><tr><th>Workout date</th>${exercise.all?'<th>Exercise</th>':''}<th>Set</th><th>Load</th><th>Reps</th><th>${exerciseVolumeLabel()} <span class="th-unit">kg·reps</span></th><th>Source</th><th><span class="sr-only">Open workout</span></th></tr></thead><tbody>${rows.slice(0,limit).map(s => `<tr><td><button class="table-date" data-session="${escape(s.sessionId)}">${date(s.date,true)}</button>${s.note ? `<span class="data-note" title="${escape(s.note)}">Needs context</span>` : ''}</td>${exercise.all?`<td><button class="record-exercise" data-exercise="${escape(s.exercise)}">${exerciseLabel(s.exercise)}</button></td>`:''}<td class="muted">${number(s.number)}</td><td class="weight-cell">${loadLabel(s.exercise,s.weight)}</td><td class="reps-cell">${number(s.reps)}</td><td class="volume-cell">${number(s.volume,1)}</td><td>${badge(s.source)}</td><td><button class="row-arrow" data-session="${escape(s.sessionId)}" aria-label="Open workout on ${escape(date(s.date,true))}">${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>${!compact && rows.length > limit ? `<button class="load-more" data-action="more-sets">Show more sets <span>${Math.min(limit,rows.length)} of ${rows.length}</span></button>` : ''}</section>`;
}
function weeklyPanel(view) {
  const weeks = weeklyWorkouts(view.workouts,today());
  const max = Math.max(5,...weeks.map(w=>w.count));
  return `<section class="panel weekly-panel"><div class="table-heading"><div><span class="eyebrow">CONSISTENCY</span><h2>A week at a time</h2></div><span class="subtle-label">LAST 12 WEEKS</span></div><div class="weekly-subtitle">One bar. One week. Your workout count on top.</div><div class="weekly-chart" data-motion-chart="true" data-motion-key="weekly-workouts" role="img" aria-label="Weekly strength workouts: ${weeks.map(w=>`${w.date}: ${w.count}`).join('; ')}">${weeks.map((w,i)=>`<div class="week-column ${i===weeks.length-1?'current':''}"><div class="week-bar-space"><div class="week-bar ${w.count?'':'zero'}" data-motion-bar="height" data-point-value="${w.count}" style="height:${w.count ? Math.max(8,w.count/max*100) : 2}%"><span>${w.count}</span></div></div><small>${date(w.date)}</small></div>`).join('')}</div><div class="weekly-footer"><span><i class="legend-square"></i> Week starting Monday</span><span>This week is still in progress</span></div></section>`;
}
function workoutCard(workout, sets, compact = false) {
  const names = [...new Set(sets.map(s=>s.exercise))];
  const hasManual = sets.some(s=>s.source==='manual');
  return `<button class="workout-card ${compact?'compact':''}" data-session="${escape(workout.id)}"><div class="workout-card-top"><span class="date-tile"><strong>${new Date(workout.date+'T12:00:00Z').getUTCDate()}</strong><small>${new Date(workout.date+'T12:00:00Z').toLocaleDateString('en-GB',{month:'short',timeZone:'UTC'})}</small></span><div><strong>${escape(workout.name)}</strong><small>${date(workout.date,true)}</small></div>${icon('arrow')}</div><div class="workout-card-info"><span>${names.length} exercises</span><i></i><span>${sets.length} sets</span>${present(workout.duration)?`<i></i><span>${duration(workout.duration)}</span>`:''}</div>${compact?'':`<p>${escape(names.slice(0,3).join(' · '))}${names.length>3?' + '+(names.length-3)+' more':''}</p>`}<div class="workout-card-bottom">${badge(hasManual?'manual':workout.source)}${hasManual && workout.source==='garmin'?'<span class="merged-label">Garmin workout timing</span>':''}<span>${number(sumKnown(sets.map(s=>s.reps)))} reps</span></div></button>`;
}
function recentPanel(view) {
  const workouts = [...view.workouts].sort((a,b)=>b.date.localeCompare(a.date)||b.time.localeCompare(a.time));
  return `<section class="panel recent-panel"><div class="table-heading"><div><span class="eyebrow">KEEP SHOWING UP</span><h2>Recent workouts</h2></div><a href="#workouts" class="text-link">View all ${icon('arrow')}</a></div><div class="recent-list">${workouts.slice(0,3).map(w=>workoutCard(w,view.sets.filter(s=>s.sessionId===w.id),true)).join('') || '<div class="small-empty"><strong>No workouts in this range</strong><p>Choose a wider date range or select All records above.</p><a class="text-link" href="#logging">Log a workout →</a></div>'}</div></section>`;
}
const recoveryMetrics = [
  {key:'sleepHours',label:'Sleep duration',unit:'',color:'var(--metric-sleepHours, #b6a0ff)',format:sleepDuration,description:'Total recorded sleep, excluding time awake.'},
  {key:'hrv',label:'Overnight HRV',unit:'ms',color:'var(--metric-hrv, #59dcc5)',description:'Garmin’s average overnight heart-rate variability.'},
  {key:'restingHR',label:'Resting heart rate',unit:'bpm',color:'var(--metric-restingHR, #ff9caa)',description:'Daily resting heart rate, with sleep-summary values used if daily data is missing.'},
  {key:'bodyBattery',label:'Body Battery at wake',unit:'/100',color:'var(--metric-bodyBattery, #d4b1fa)',description:'Body Battery at wake time, as recorded by Garmin.'},
  {key:'bodyWeightKg',label:'Body weight',unit:'kg',color:'var(--metric-bodyWeightKg, #ffbd75)',format:value=>number(value,1),description:'Latest recorded weigh-in on each date, in kilograms. Missing days are not filled. Body weight is separate from added exercise load.'},
  {key:'sleepScore',label:'Sleep score',unit:'/100',color:'var(--metric-sleepScore, #94c8ff)',description:'Garmin’s recorded overall sleep score.'},
];
function sleepDuration(hours) {
  if(!present(hours))return '—';
  const mins=Math.round(hours*60);
  return `${Math.floor(mins/60)}<span class="duration-unit">h</span> ${mins%60}<span class="duration-unit">m</span>`;
}
function recoveryRows() {
  const {from,to}=range();
  return (state.data.recovery||[]).filter(row=>(!from||row.date>=from)&&(!to||row.date<=to));
}
function recoverySnapshot(full = false, explicitRows = null) {
  const rows=explicitRows||recoveryRows();
  const metrics=full?recoveryMetrics:recoveryMetrics.slice(0,5);
  return `<section class="recovery-snapshot ${full?'full':''}">${full?'':`<div class="snapshot-heading"><div><h2>Recovery context</h2><span>Latest available readings in your date range</span></div><a class="text-link" href="#recovery">Explore recovery ${icon('arrow')}</a></div>`}<div class="recovery-cards">${metrics.map(m=>{
    const latest=[...rows].reverse().find(r=>present(r[m.key]));
    return `<article class="recovery-card" style="--metric-color:${m.color}" title="${escape(m.description)}"><div class="recovery-label"><i></i>${m.label}</div><strong>${latest?(m.format?m.format(latest[m.key]):number(latest[m.key],['sleepHours','bodyWeightKg'].includes(m.key)?1:0)):'—'}${latest&&m.unit?` <small>${m.unit}</small>`:''}</strong><span>${latest?date(latest.date,true):'Not recorded in this range'}</span></article>`;
  }).join('')}</div></section>`;
}
function signalDaily(rows,key) {
  const byDate=new Map();
  for(const row of [...rows].sort((a,b)=>a.time.localeCompare(b.time)))if(present(row[key]))byDate.set(row.date,row);
  return [...byDate.values()].sort((a,b)=>a.date.localeCompare(b.date));
}
function readinessChart(rows,selected) {
  const scores=new Map(signalDaily(rows,'score').map(row=>[row.date,row.score]));
  const end=selected.to||today(),days=[];
  for(let offset=13;offset>=0;offset--){
    const day=new Date(end+'T00:00:00Z');day.setUTCDate(day.getUTCDate()-offset);
    const key=day.toISOString().slice(0,10);
    if(!selected.from||key>=selected.from)days.push(key);
  }
  return `<div class="readiness-plot" data-motion-chart="true" data-motion-key="readiness" data-time-start="${days[0]||''}" data-time-end="${days.at(-1)||''}" role="img" aria-label="Training readiness scores over the last ${days.length} days; empty bars mean no Garmin reading"><div class="readiness-axis"><span>100</span><span>50</span><span>0</span></div><div class="readiness-days">${days.map(day=>{
    const score=scores.get(day),tone=!present(score)?'missing':score>=80?'strong':score>=50?'steady':score>=25?'caution':'low';
    return `<div class="readiness-day" title="${escape(date(day,true))}: ${present(score)?number(score)+'/100':'No reading'}"><span class="readiness-bar-wrap">${present(score)?`<i class="readiness-bar ${tone}" data-motion-bar="y" data-point-value="${score}" style="height:${Math.max(2,Math.min(100,score))}%"></i>`:'<i class="readiness-missing"></i>'}</span><small>${day.slice(8)}</small></div>`;
  }).join('')}</div></div>`;
}
function loadChart(rows) {
  const points=signalDaily(rows,'acuteLoad').slice(-30);
  if(!points.length)return '<p class="signal-chart-empty">No training-load readings in this period yet.</p>';
  const W=600,H=200,left=36,right=16,top=18,bottom=30;
  const values=points.flatMap(row=>[row.acuteLoad,row.chronicLoad,row.optimalMax]).filter(present);
  const ceiling=Math.max(100,Math.ceil(Math.max(...values)*1.15/50)*50);
  const first=Date.parse(points[0].date+'T00:00:00Z'),last=Date.parse(points.at(-1).date+'T00:00:00Z');
  const x=row=>first===last?(left+W-right)/2:left+(Date.parse(row.date+'T00:00:00Z')-first)/(last-first)*(W-left-right);
  const y=value=>H-bottom-value/ceiling*(H-top-bottom);
  const splitRuns=rows=>{
    const runs=[];let run=[];
    for(const row of rows){
      if(run.length&&Date.parse(row.date+'T00:00:00Z')-Date.parse(run.at(-1).date+'T00:00:00Z')>86400000){runs.push(run);run=[];}
      run.push(row);
    }
    if(run.length)runs.push(run);
    return runs;
  };
  const line=key=>splitRuns(points.filter(row=>present(row[key]))).map(run=>run.map((row,i)=>`${i?'L':'M'}${x(row).toFixed(1)},${y(row[key]).toFixed(1)}`).join(' ')).join(' ');
  const band=points.filter(row=>present(row.optimalMin)&&present(row.optimalMax));
  const bandPaths=splitRuns(band).filter(run=>run.length>=2).map(run=>`M${run.map(row=>`${x(row).toFixed(1)},${y(row.optimalMax).toFixed(1)}`).join(' L')} L${[...run].reverse().map(row=>`${x(row).toFixed(1)},${y(row.optimalMin).toFixed(1)}`).join(' L')} Z`);
  return `<svg class="load-signal-plot" data-motion-chart="true" data-motion-key="training-load" data-time-start="${first}" data-time-end="${last}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Garmin acute and chronic training load with the recorded optimal range"><line class="load-grid" x1="${left}" x2="${W-right}" y1="${y(ceiling/2)}" y2="${y(ceiling/2)}"/><line class="load-grid" x1="${left}" x2="${W-right}" y1="${y(0)}" y2="${y(0)}"/><text class="load-axis" x="${left-7}" y="${y(ceiling/2)+4}" text-anchor="end">${number(ceiling/2)}</text><text class="load-axis" x="${left-7}" y="${y(0)+4}" text-anchor="end">0</text>${bandPaths.map(path=>`<path class="load-optimal" data-motion-area="true" d="${path}"/>`).join('')}${points.length>1?`<path class="load-chronic" data-motion-line="true" d="${line('chronicLoad')}"/><path class="load-acute" data-motion-line="true" d="${line('acuteLoad')}"/>`:''}${points.map(row=>`<circle class="load-dot" cx="${x(row)}" cy="${y(row.acuteLoad)}" r="3" tabindex="0"><title>${escape(date(row.date,true))}: acute ${number(row.acuteLoad)}, chronic ${number(row.chronicLoad)}, Garmin target ${number(row.optimalMin)}–${number(row.optimalMax)}</title></circle>`).join('')}<text class="load-axis" x="${left}" y="${H-7}">${date(points[0].date,true)}</text><text class="load-axis" x="${W-right}" y="${H-7}" text-anchor="end">${date(points.at(-1).date,true)}</text></svg>`;
}
function trainingSignals() {
  const signals=state.data.training||{},selected=range();
  const within=row=>row&&(!selected.from||row.date>=selected.from)&&(!selected.to||row.date<=selected.to);
  const statuses=(signals.status||[]).filter(within),readinessRows=(signals.readiness||[]).filter(within);
  const status=statuses.at(-1),readiness=readinessRows.at(-1);
  const battery=within(signals.bodyBatteryLatest)?signals.bodyBatteryLatest:null;
  const daily=(state.data.recovery||[]).find(r=>r.date===battery?.date);
  const wakeRows=recoveryRows().filter(row=>present(row.bodyBattery)).slice(-14);
  const stamp=row=>row?date(row.date,true):'No reading in this range';
  const old=row=>row&&row.date<new Date(Date.parse(today()+'T00:00:00Z')-2*86400000).toISOString().slice(0,10);
  const card=(metric,label,value,unit,detail,row,tone,extra='')=>`<article class="training-signal-card signal-${tone}" data-signal="${metric}"><span>${label}</span><strong>${value}${unit?` <small>${unit}</small>`:''}</strong><p>${detail}</p>${extra}<time>${stamp(row)}${old(row)?' · older reading':''}</time></article>`;
  const charged=present(daily?.bodyBatteryCharged)?`Charged +${number(daily.bodyBatteryCharged)}`:null;
  const drained=present(daily?.bodyBatteryDrained)?`Drained −${number(daily.bodyBatteryDrained)}`:null;
  const batteryTime=battery?new Date(battery.time).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:state.data.timezone||'Europe/Kyiv'}):null;
  const batteryBars=wakeRows.length?`<div class="battery-mini" data-motion-chart="true" data-motion-key="body-battery" role="img" aria-label="Body Battery at wake on the last ${wakeRows.length} recorded days">${wakeRows.map(row=>`<i data-motion-bar="y" data-point-value="${row.bodyBattery}" style="height:${Math.max(2,Math.min(100,row.bodyBattery))}%" title="${escape(date(row.date,true))}: ${number(row.bodyBattery)}/100"></i>`).join('')}</div><small class="signal-mini-caption">At wake · recorded days</small>`:'';
  const readinessTone=!present(readiness?.score)?'neutral':readiness.score>=80?'good':readiness.score>=50?'info':readiness.score>=25?'warn':'alert';
  const statusTone=['Productive','Peaking'].includes(status?.label)?'good':['Strained','Overreaching','Unproductive'].includes(status?.label)?'alert':'info';
  const ratioTone=present(status?.loadRatio)?'info':'neutral';
  return `<section class="panel training-signals"><div class="table-heading"><div><span class="eyebrow">FROM YOUR GARMIN</span><h2>Training signals</h2><p>Recorded values in this period. Garmin calculates these; missing days remain blank.</p></div></div><div class="training-signal-grid">${card('readiness','Training readiness',present(readiness?.score)?number(readiness.score):'—','/100',escape(readiness?.level||'No score recorded'),readiness,readinessTone)}${card('status','Training status',escape(status?.label||'—'),'',status?.label?'Garmin training status':'No status recorded',status,statusTone)}${card('ratio','Load ratio',present(status?.loadRatio)?number(status.loadRatio,2):'—','',`Acute ${present(status?.acuteLoad)?number(status.acuteLoad):'—'} · chronic ${present(status?.chronicLoad)?number(status.chronicLoad):'—'}`,status,ratioTone)}${card('battery','Latest Body Battery',present(battery?.level)?number(battery.level):'—','/100',[batteryTime?`Last reading ${batteryTime}`:'No recent sample',charged,drained].filter(Boolean).join(' · '),battery,'battery',batteryBars)}</div><div class="training-chart-grid"><section class="training-chart"><div class="training-chart-head"><div><h3>Training readiness</h3><p>Latest Garmin score each day · last 14 days</p></div><span>0–100</span></div>${readinessChart(readinessRows,selected)}</section><section class="training-chart"><div class="training-chart-head"><div><h3>Training load</h3><p>Garmin acute and chronic load · up to 30 recorded days</p></div></div>${loadChart(statuses)}<div class="load-legend"><span class="acute">Acute</span><span class="chronic">Chronic</span><span class="optimal">Garmin optimal range</span></div></section></div></section>`;
}
function recoveryChart(rows, metric) {
  const points=rows.map(row=>({date:row.date,value:row[metric.key]}));
  const known=points.filter(p=>present(p.value));
  if(!known.length)return '<div class="chart-empty"><strong>No readings in this range</strong><p>Choose a wider date range. Missing watch data is not estimated.</p></div>';
  const W=600,H=225,pad={l:43,r:19,t:22,b:32},width=W-pad.l-pad.r,height=H-pad.t-pad.b;
  const max=Math.max(...known.map(p=>p.value));
  const weight=metric.key==='bodyWeightKg';
  const min=Math.min(...known.map(p=>p.value));
  const step=weight?Math.max(.5,Math.ceil((max-min)/4*2)/2):metric.key==='sleepHours'?2:max>80?25:max>40?20:10;
  const bottom=weight?Math.max(0,Math.floor((min-step)/step)*step):0;
  const top=Math.max(bottom+step,Math.ceil(max/step)*step);
  const first=new Date(points[0].date).getTime(),last=new Date(points.at(-1).date).getTime();
  const x=p=>pad.l+(last===first?width/2:(new Date(p.date).getTime()-first)/(last-first)*width);
  const y=v=>pad.t+height-(v-bottom)/(top-bottom)*height;
  let runs=[],run=[];
  for(const p of points){
    if(run.length&&Date.parse(p.date+'T00:00:00Z')-Date.parse(run.at(-1).date+'T00:00:00Z')>86400000){runs.push(run);run=[];}
    if(present(p.value))run.push(p);else{if(run.length)runs.push(run);run=[];}
  }
  if(run.length)runs.push(run);
  const path=group=>group.map((p,i)=>`${i?'L':'M'}${x(p).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const indices=[...new Set([0,Math.floor((points.length-1)/2),points.length-1])];
  return `<div class="chart-wrap daily-chart"><div class="chart-tooltip" role="status"></div><svg data-time-start="${first}" data-time-end="${last}" data-plot-left="${pad.l}" data-plot-right="${W-pad.r}" data-plot-top="${pad.t}" data-plot-bottom="${H-pad.b}" class="progress-svg" data-motion-chart="true" data-motion-key="recovery:${metric.key}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${escape(metric.label)} daily history"><defs><linearGradient id="recovery-fill-${metric.key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${metric.color}" stop-opacity=".14"/><stop offset="100%" stop-color="${metric.color}" stop-opacity="0"/></linearGradient></defs>${[0,.25,.5,.75,1].map(f=>`<line x1="${pad.l}" x2="${W-pad.r}" y1="${y(bottom+(top-bottom)*f)}" y2="${y(bottom+(top-bottom)*f)}" stroke="hsl(var(--theme-hue) calc(18.58% * var(--theme-chroma)) 22.16%)" stroke-dasharray="3 5"/><text class="chart-label" x="${pad.l-11}" y="${y(bottom+(top-bottom)*f)+4}" text-anchor="end">${number(bottom+(top-bottom)*f,['sleepHours','bodyWeightKg'].includes(metric.key)?1:0)}</text>`).join('')}${runs.map(group=>`<path data-motion-area="true" d="${path(group)} L${x(group.at(-1))},${y(bottom)} L${x(group[0])},${y(bottom)} Z" fill="url(#recovery-fill-${metric.key})"/><path data-motion-line="true" d="${path(group)}" fill="none" stroke="${metric.color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`).join('')}${known.map((p,i)=>`<circle class="chart-point daily-point" cx="${x(p)}" cy="${y(p.value)}" r="3" fill="hsl(var(--theme-hue) calc(16.13% * var(--theme-chroma)) 12.16%)" stroke="${metric.color}" stroke-width="1.5" tabindex="${p===known.at(-1)?'0':'-1'}" role="img" data-point-previous="${i?known[i-1].value:''}" data-point-value="${p.value}" data-point-unit="${metric.key==='sleepHours'?'h':metric.unit==='/100'?'points':metric.unit}" data-point-label="${escape(date(p.date,true))} · ${number(p.value,['sleepHours','bodyWeightKg'].includes(metric.key)?2:0)} ${metric.key==='sleepHours'?'h':metric.unit}" aria-label="${escape(date(p.date,true))}, ${number(p.value,['sleepHours','bodyWeightKg'].includes(metric.key)?2:0)} ${metric.key==='sleepHours'?'hours':metric.unit}"/>`).join('')}${indices.map(i=>`<text class="chart-label" x="${x(points[i])}" y="${H-9}" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}">${date(points[i].date,true)}</text>`).join('')}</svg></div>`;
}
function sleepStages(rows) {
  const row=[...rows].reverse().find(r=>['deepSeconds','lightSeconds','remSeconds'].some(key=>present(r[key])));
  if(!row)return `<section class="panel stages-panel"><div class="table-heading"><div><h2>Sleep stages</h2><p>No sleep-stage records in this range.</p></div></div></section>`;
  const stages=[{key:'deepSeconds',name:'Deep',color:'var(--stage-deep,#9f9ce3)'},{key:'lightSeconds',name:'Light',color:'var(--stage-light,#bbc6e3)'},{key:'remSeconds',name:'REM',color:'var(--metric-hrv,#59dcc5)'},{key:'awakeSeconds',name:'Awake',color:'var(--stage-awake,#d9bd86)'}];
  const total=sumKnown(stages.map(s=>row[s.key]))||1;
  return `<section class="panel stages-panel"><div class="table-heading"><div><span class="eyebrow">LATEST RECORDED NIGHT</span><h2>Sleep stages</h2><p>${date(row.date,true)} · Awake time is shown separately from total sleep.</p></div><strong class="stage-sleep-total">${sleepDuration(row.sleepHours)}</strong></div><div class="sleep-stages-bar" data-motion-chart="true" data-motion-reveal="x" data-motion-key="sleep-stages" role="img" aria-label="Sleep stages on ${escape(date(row.date,true))}">${stages.filter(s=>present(row[s.key])).map(s=>`<span data-point-value="${row[s.key]}" style="width:${row[s.key]/total*100}%;background:${s.color}" title="${s.name}: ${duration(row[s.key])}"></span>`).join('')}</div><div class="stages-legend">${stages.map(s=>`<div><span><i style="background:${s.color}"></i>${s.name}</span><strong>${duration(row[s.key])}</strong></div>`).join('')}</div></section>`;
}
function recoveryPage() {
  const rows=recoveryRows();
  return header('Recovery & daily health','Sleep, HRV, resting heart rate and body weight alongside your training. Daily data follows your date range.')+trainingSignals()+recoverySnapshot(true)+`<div class="recovery-charts">${recoveryMetrics.slice(0,5).map(m=>`<section class="panel recovery-chart-panel" style="--metric-color:${m.color}"><div class="table-heading"><div><span class="eyebrow">DAILY READINGS</span><h2>${m.label}</h2></div><span class="chart-unit">${m.key==='sleepHours'?'hours / night':m.unit}</span></div>${recoveryChart(rows,m)}<div class="chart-footnote">${m.description} Gaps indicate missing records.</div></section>`).join('')}</div>${sleepStages(rows)}<section class="panel recovery-table"><div class="table-heading"><div><h2>Daily recovery log</h2><p>Readings are shown as recorded. No combined readiness score is invented.</p></div><span class="count-chip">${rows.length} days</span></div><div class="table-scroll"><table><thead><tr><th>Date</th><th>Sleep</th><th>Sleep score</th><th>HRV</th><th>Resting HR</th><th>Body Battery at wake</th><th>Body weight</th></tr></thead><tbody>${[...rows].reverse().slice(0,state.recoveryLimit).map(r=>`<tr><td>${date(r.date,true)}</td><td>${sleepDuration(r.sleepHours)}</td><td>${number(r.sleepScore)}${present(r.sleepScore)?' <span class="muted">/100</span>':''}</td><td>${number(r.hrv)}${present(r.hrv)?' <span class="muted">ms</span>':''}</td><td>${number(r.restingHR)}${present(r.restingHR)?' <span class="muted">bpm</span>':''}</td><td>${number(r.bodyBattery)}${present(r.bodyBattery)?' <span class="muted">/100</span>':''}</td><td>${number(r.bodyWeightKg,1)}${present(r.bodyWeightKg)?' <span class="muted">kg</span>':''}</td></tr>`).join('')||'<tr><td colspan="7">No readings in this date range.</td></tr>'}</tbody></table></div>${rows.length>state.recoveryLimit?`<button class="load-more" data-action="more-recovery">Show more days <span>${state.recoveryLimit} of ${rows.length}</span></button>`:''}</section>`;
}

const overviewSections={summary:'Training summary',calendar:'Workout calendar',nutrition:'Food today',recovery:'Recovery',consistency:'Weekly consistency',recent:'Recent workouts'};
let savedOverview;
function overviewLayout(){
  if(savedOverview)return savedOverview;
  let saved;try{saved=JSON.parse(localStorage.getItem('form-overview-layout'));}catch{}
  const keys=Object.keys(overviewSections);
  const order=Array.isArray(saved?.order)?[...new Set(saved.order.filter(k=>keys.includes(k)))]:[];
  savedOverview={order:[...order,...keys.filter(k=>!order.includes(k))],hidden:Array.isArray(saved?.hidden)?[...new Set(saved.hidden.filter(k=>keys.includes(k)))]:[]};
  return savedOverview;
}
function saveOverviewLayout(){
  try{localStorage.setItem('form-overview-layout',JSON.stringify(overviewLayout()));}catch{toast('Layout changed for this session. Browser storage is unavailable.');}
}
function overviewControls(){
  const layout=overviewLayout();
  return `<details class="panel layout-controls" ${state.layoutOpen?'open':''}><summary>Customize overview <span>Show, hide & reorder sections</span></summary><div class="layout-options">${layout.order.map((key,i)=>`<div class="layout-option"><label><input type="checkbox" data-layout-visible="${key}" ${layout.hidden.includes(key)?'':'checked'}> ${overviewSections[key]}</label><div><button class="button" data-layout-move="${key}" data-direction="-1" ${i?'':'disabled'} aria-label="Move ${overviewSections[key]} up">↑</button><button class="button" data-layout-move="${key}" data-direction="1" ${i===layout.order.length-1?'disabled':''} aria-label="Move ${overviewSections[key]} down">↓</button></div></div>`).join('')}</div><div class="layout-footer"><span>Saved in this browser.</span><button class="button" data-layout-reset>Restore default layout</button></div></details>`;
}
function shiftCalendar(month,offset){
  const [year,m]=month.split('-').map(Number),d=new Date(Date.UTC(year,m-1+offset,1));
  return d.toISOString().slice(0,7);
}
function workoutCalendar(view){
  const month=state.calendarMonth||((range().to||today()).slice(0,7));
  const [year,m]=month.split('-').map(Number),first=new Date(Date.UTC(year,m-1,1));
  const days=new Date(Date.UTC(year,m,0)).getUTCDate(),offset=(first.getUTCDay()+6)%7;
  const monthWorkouts=view.workouts.filter(w=>w.date.startsWith(month));
  const byDay=new Map();for(const workout of monthWorkouts){if(!byDay.has(workout.date))byDay.set(workout.date,[]);byDay.get(workout.date).push(workout);}
  const selected=state.calendarDay?.startsWith(month)?state.calendarDay:null;
  const selectedWorkouts=selected?(byDay.get(selected)||[]):[];
  const title=first.toLocaleDateString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'});
  return `<section class="panel workout-calendar"><div class="table-heading"><div><span class="eyebrow">YOUR TRAINING RHYTHM</span><h2>Workout calendar</h2><p>${monthWorkouts.length} workouts · ${byDay.size} training days in this month · respects your filters</p></div><div class="calendar-controls"><button class="button" data-calendar-shift="-1" aria-label="Previous month">←</button><strong aria-live="polite">${title}</strong><button class="button" data-calendar-shift="1" aria-label="Next month">→</button><button class="button" data-calendar-today>This month</button></div></div><div class="calendar-body"><div><div class="calendar-weekdays" aria-hidden="true">${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d=>`<span>${d}</span>`).join('')}</div><div class="calendar-days" role="group" aria-label="${title}">${'<span class="calendar-blank" aria-hidden="true"></span>'.repeat(offset)}${Array.from({length:days},(_,i)=>{const day=`${month}-${String(i+1).padStart(2,'0')}`,rows=byDay.get(day)||[];return `<button class="calendar-day ${rows.length?'has-workout':''} ${day===today()?'is-today':''}" data-calendar-day="${day}" aria-pressed="${day===selected}" aria-label="${escape(date(day,true))}: ${rows.length} recorded workouts"><span>${i+1}</span><div class="calendar-dots" aria-hidden="true">${rows.slice(0,3).map(w=>`<i class="${w.source==='manual'?'manual':'garmin'}"></i>`).join('')}${rows.length>3?'<small>+</small>':''}</div><small>${rows.length?rows.length+' session'+(rows.length===1?'':'s'):''}</small></button>`;}).join('')}</div><div class="calendar-legend"><span><i class="garmin"></i>Garmin</span><span><i class="manual"></i>Manual</span><span>Empty days: no recorded workouts in these filters</span></div></div><aside class="calendar-detail" aria-live="polite"><h3>${selected?date(selected,true):'Choose a training day'}</h3>${selectedWorkouts.length?selectedWorkouts.map(w=>`<button class="calendar-session" data-session="${escape(w.id)}"><span>${icon('workouts')}<strong>${escape(w.name)}</strong></span><small>${w.source==='manual'?'Manual log':'Garmin'} · View workout →</small></button>`).join(''):`<p>${selected?'No workouts recorded for this day with the current filters.':'Select a date to see its sessions, then open a workout to explore its exercises and sets.'}</p>`}</aside></div></section>`;
}
function overview(view) {
  const todayLocal=today();
  const food=(state.data.foodLog||[]).filter(e=>localDay(e.time)===todayLocal);
  const nutrition=food.reduce((a,e)=>{a.calories+=e.calories;a.protein+=e.protein_g;a.carbs+=e.carbs_g;a.fat+=e.fat_g;return a;},{calories:0,protein:0,carbs:0,fat:0});
  const sections={summary:()=>stats(view),calendar:()=>workoutCalendar(view),nutrition:()=>`<section class="panel overview-nutrition"><div><span class="eyebrow">FOOD TODAY · ESTIMATED</span><h2>${food.length?number(nutrition.calories)+' kcal':'No food logged yet'}</h2><p>${food.length?`Protein ${number(nutrition.protein,1)} g · Carbs ${number(nutrition.carbs,1)} g · Fat ${number(nutrition.fat,1)} g`:'Send a food photo or a short description to your Telegram bot.'}</p></div><a class="button" href="#nutrition">View nutrition ${icon('arrow')}</a></section>`,recovery:()=>recoverySnapshot(),consistency:()=>weeklyPanel(view),recent:()=>recentPanel(view)};
  const layout=overviewLayout();
  return header('Training overview','Your lifts, your consistency, and the progress behind every session.')+layout.order.filter(key=>!layout.hidden.includes(key)).map(key=>`<div class="overview-section" data-overview-section="${key}">${sections[key]()}</div>`).join('')+(layout.hidden.length===layout.order.length?'<div class="panel small-empty"><strong>Your overview is clear</strong><p>Open Preferences to bring back a section.</p><a class="button" href="#preferences">Customize overview →</a></div>':'');
}
function exercisesPage(view) {
  if(!view.sets.length)return header('Your exercise library','A complete history for every lift, grouped by muscle.')+'<section class="panel empty-panel"><h2>No exercise sets in these filters</h2><p>Broaden the date or source filters, log a workout, or identify Unknown exercises in Log &amp; edit.</p><a class="button button-dark" href="#logging">Open Log &amp; edit</a></section>';
  return header('Your exercise library','A complete history for every lift, grouped by muscle. Most recorded exercises come first within each group.') + `<div class="training-grid exercises-page">${library(view)}<div class="exercise-detail">${progressPanel(view.selected)}${setsTable(view.selected)}</div></div>`;
}
function workoutsPage(view) {
  const workouts = [...view.workouts].sort((a,b)=>b.date.localeCompare(a.date)||b.time.localeCompare(a.time)).filter(w=>w.name.toLowerCase().includes(state.workoutSearch.toLowerCase()));
  return header('Workout history','Open a session to see every exercise, set, rep, and recorded rest.') + `<div class="workout-toolbar"><span id="workout-count"><strong>${workouts.length}</strong> ${state.workoutSearch?`matching workouts · ${view.workouts.length} in date range`:'workouts in your selected range'}</span><label class="search-box">${icon('search')}<span class="sr-only">Search workout names</span><input id="workout-search" type="search" placeholder="Find a workout…" value="${escape(state.workoutSearch)}"></label></div><div class="workouts-grid" id="workout-list">${workouts.map(w=>workoutCard(w,view.sets.filter(s=>s.sessionId===w.id))).join('') || '<div class="empty-panel">No matching workouts.</div>'}</div>`;
}
function recordsPage(view) {
  const rows = [...view.exercises].sort((a,b)=>state.recordSort === 'name' ? a.name.localeCompare(b.name) : state.recordSort === 'change' ? (b.change??-Infinity)-(a.change??-Infinity) : b.count-a.count);
  return header('Personal records','Your best recorded sets, with the context to read them correctly.') + `<div class="record-banner"><span class="record-icon">${icon('records')}</span><div><h2>Progress has more than one number.</h2><p>Load, reps, and estimated max are separate records. They may come from different sets.</p></div><span>${view.exercises.length}<small>exercises tracked</small></span></div><section class="panel"><div class="table-heading"><div><h2>Records by exercise</h2><p>All values follow your date and source filters.</p></div><label class="select-wrap"><span class="sr-only">Sort records</span><select id="record-sort"><option value="count" ${state.recordSort==='count'?'selected':''}>Most recorded</option><option value="name" ${state.recordSort==='name'?'selected':''}>Exercise name</option><option value="change" ${state.recordSort==='change'?'selected':''}>Load change</option></select></label></div><div class="table-scroll"><table class="records-table"><thead><tr><th>Exercise</th><th>Sets</th><th>Best load / least assistance</th><th>Rep record</th><th>Best est. 1RM</th><th>First → latest load</th><th>History</th></tr></thead><tbody>${rows.map(e=>`<tr><td><button class="record-exercise" data-view-exercise="${escape(e.name)}">${exerciseLabel(e.name)}</button><small>${e.sessions} workouts</small></td><td>${e.count}</td><td class="weight-cell">${kg(e.bestWeight)}${e.assisted?'<small>assistance</small>':''}</td><td>${number(e.bestReps)}</td><td>${kg(e.bestMax)}</td><td class="${(e.assisted?e.change<0:e.change>0)?'positive':''}">${present(e.change)?(e.change>0?'+':'')+number(e.change,1)+' kg':'—'}<small>${present(e.firstWeight)?number(e.firstWeight,1)+' → '+number(e.latestWeight,1)+' kg':'No recorded load'}</small></td><td><button class="record-spark" data-view-exercise="${escape(e.name)}" aria-label="Explore ${escape(e.name)}">${sparkline(e)}${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div><div class="records-note">Estimated 1RM uses eligible weighted sets of 1–10 reps. For assisted exercises the best is the least recorded assistance, and lower kg means less help. Other loads are not corrected for bodyweight or equipment changes.</div></section>`;
}
function nutritionDay() { return state.nutritionDate || today(); }
function dateRangeBar() {
  if(state.page==='goals')return '';
  if(state.page==='nutrition')return `<section class="date-range-bar nutrition-date-bar" aria-label="Choose nutrition day"><div><strong>${nutritionDay()===today()?'Today':date(nutritionDay(),true)}</strong><p>Logged calories and macros for this day</p></div><div class="range-dates"><label><span>Day</span><input type="date" id="nutrition-date" value="${escape(nutritionDay())}" max="${today()}"></label><button class="button" data-action="nutrition-today">Today</button></div></section>`;

  const dates=(state.page==='recovery'?(state.data?.recovery||[]):state.page==='nutrition'?(state.data?.foodLog||[]).map(e=>({date:localDay(e.time)})):(state.data?.workouts||[])).map(r=>r.date).sort();
  const selected=range(),from=selected.from||dates[0]||today(),to=selected.to||today();
  return `<section class="date-range-bar" aria-label="Choose a date range"><div class="range-main"><div class="range-presets" role="group" aria-label="Quick date ranges">${[['all','All history'],['7','1 week'],['14','2 weeks'],['30','30 days'],['90','90 days'],['6m','6 months'],['1y','1 year']].map(([key,label])=>`<button data-range="${key}" class="${state.range===key?'active':''}" aria-pressed="${state.range===key}">${label}</button>`).join('')}</div><div class="range-dates"><label><span>From</span><input type="date" id="from-date" value="${escape(from)}" max="${today()}"></label><span class="range-arrow">→</span><label><span>To</span><input type="date" id="to-date" value="${escape(to)}" max="${today()}"></label><button class="button range-apply ${state.range==='custom'?'chosen':''}" data-action="apply-range">Apply dates</button></div></div><div class="range-caption"><span>${date(from,true)} — ${date(to,true)} <span class="muted">· ${state.range==='custom'?'Custom dates':'Preset range'}</span></span><span id="range-error" role="status"></span>${state.zoomHistory?.length?'<button class="button" data-action="undo-zoom">Undo zoom</button><button class="button" data-action="reset-zoom">Reset zoom</button>':''}</div></section>`;
}
function repControl() {
  return `<label class="inline-input">Compare sets at <input id="rep-target" type="number" min="1" max="500" value="${state.repTarget}"> reps <span class="muted">exactly</span></label>`;
}
function allRecoveryComparisons(view,metric,unit) {
  const comparisons=view.exercises.map(e=>({exercise:e.name,...recoveryComparison(view.sets,recoveryRows(),e.name,state.repTarget,metric,metric==='sleepHours'?state.recoveryThreshold:null)}));
  const paired=comparisons.filter(c=>c.pairs.length);
  return `<div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Split (${unit})</th><th>Below split · avg load</th><th>At or above · avg load</th><th>Paired workouts</th></tr></thead><tbody>${comparisons.map(c=>`<tr><td>${exerciseLabel(c.exercise)}</td><td>${number(c.threshold,1)}</td><td>${kg(c.low.mean)}<small>${c.low.n} workouts</small></td><td>${kg(c.high.mean)}<small>${c.high.n} workouts</small></td><td>${c.pairs.length}<small>${c.enough?'At least 3 per group':'More data needed'}</small></td></tr>`).join('')||'<tr><td colspan="5">No exercises in these filters.</td></tr>'}</tbody></table></div><p class="feature-note">Each lift is compared separately at exactly ${state.repTarget} reps. Loads from different exercises are never averaged together. ${metric==='sleepHours'?'The same sleep threshold applies to every lift.':'Each lift uses its own paired-sample median.'} These are descriptive comparisons, not evidence of causation.</p><div class="table-scroll"><table><thead><tr><th>Workout date</th><th>Exercise</th><th>${state.repTarget}-rep load</th><th>${metric==='sleepHours'?'Sleep duration':metric==='hrv'?'Overnight HRV':'Resting HR'}</th><th>Group</th></tr></thead><tbody>${paired.flatMap(c=>c.pairs.map(p=>({...p,exercise:c.exercise,threshold:c.threshold}))).sort((a,b)=>b.date.localeCompare(a.date)||a.exercise.localeCompare(b.exercise)).map(p=>`<tr><td><button class="table-date" data-session="${escape(p.id)}">${date(p.date,true)}</button></td><td>${exerciseLabel(p.exercise)}</td><td>${kg(p.weight)}</td><td>${number(p.recovery,1)} ${unit}</td><td>${p.recovery<p.threshold?'Below split':'At or above split'}</td></tr>`).join('')||'<tr><td colspan="5">No paired readings for these matching-rep sets.</td></tr>'}</tbody></table></div>`;
}
function insightsPage(view) {
  const signals=plateauSignals(view.sets,today(),state.plateauWindow);
  const matches=view.exercises.map(e=>({name:e.name,assisted:e.assisted,history:matchingRepHistory(e.rows,state.repTarget)})).filter(e=>e.history.length);
  if(state.insightExercise!=='all'&&!view.exercises.some(e=>e.name===state.insightExercise))state.insightExercise=view.exercises[0]?.name||'';
  const metric=state.recoveryMetric,unit={sleepHours:'hours',hrv:'ms',restingHR:'bpm'}[metric];
  const comparison=recoveryComparison(view.sets,recoveryRows(),state.insightExercise,state.repTarget,metric,metric==='sleepHours'?state.recoveryThreshold:null);
  const cut=number(comparison.threshold,1);
  const statusName={watch:'Potential plateau',progressing:'Recent load best',inactive:'Older history',insufficient:'More data needed'};
  return header('Training insights','Compare like-for-like sets and inspect patterns in your own training history.')+
    `<section class="panel feature-panel"><div class="table-heading"><div><span class="eyebrow">MATCHING-REP PROGRESS</span><h2>Compare the same lift at the same reps</h2><p>Each point uses the highest load, or lowest assistance, at exactly your chosen rep count in that workout.</p></div>${repControl()}</div><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Workouts</th><th>First load</th><th>Latest load</th><th>Change</th><th>Best load / least assistance</th><th>Explore</th></tr></thead><tbody>${matches.map(e=>{const first=e.history[0].weight,last=e.history.at(-1).weight;return `<tr><td>${exerciseLabel(e.name)}</td><td>${e.history.length}</td><td>${kg(first)}</td><td>${kg(last)}</td><td class="${(e.assisted?last<first:last>first)?'positive':''}">${last>first?'+':''}${number(last-first,1)} kg</td><td>${kg(e.history.reduce((best,r)=>e.assisted?Math.min(best,r.weight):Math.max(best,r.weight),e.assisted?Infinity:-Infinity))}</td><td><button class="text-link" data-match-exercise="${escape(e.name)}">${state.repTarget}-rep history ${icon('arrow')}</button></td></tr>`;}).join('')||'<tr><td colspan="7">No sets with this exact rep count in your filters. Try another rep count.</td></tr>'}</tbody></table></div></section>`+
    `<section class="panel feature-panel"><div class="table-heading"><div><span class="eyebrow">PLATEAU TRACKING</span><h2>Where to review your recent trend</h2><p>Uses each exercise’s most-recorded rep count. A flag means no better matching-rep load (or lower assistance) across recent workouts, not a diagnosis.</p></div><label class="inline-input">Last <input id="plateau-window" type="number" min="3" max="12" value="${state.plateauWindow}"> workouts</label></div><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Status</th><th>Compared reps</th><th>Comparable workouts</th><th>Last recorded</th></tr></thead><tbody>${signals.map(s=>`<tr><td><button class="record-exercise" data-view-exercise="${escape(s.exercise)}">${exerciseLabel(s.exercise)}</button><small class="cell-description">${escape(s.reason)}</small></td><td><span class="signal ${s.status}">${statusName[s.status]}</span></td><td>${number(s.reps)}</td><td>${s.eligible}</td><td>${date(s.lastDate,true)}</td></tr>`).join('')}</tbody></table></div><p class="feature-note">Requires at least ${state.plateauWindow+1} comparable workouts, a 14-day span across the recent window, and a workout within 60 days. Program changes, technique and equipment can explain a flag.</p></section>`+
    `<section class="panel feature-panel"><div class="table-heading"><div><span class="eyebrow">TRAINING & RECOVERY</span><h2>How do your recorded loads differ?</h2><p>Same exercise and rep count, paired with watch readings from the workout date.</p></div></div><div class="feature-controls"><label>Exercise<select id="insight-exercise"><option value="all" ${state.insightExercise==='all'?'selected':''}>All exercises</option>${view.exercises.map(e=>`<option ${e.name===state.insightExercise?'selected':''}>${escape(e.name)}</option>`).join('')}</select></label><label>Compare by<select id="recovery-metric">${[['sleepHours','Sleep duration'],['hrv','Overnight HRV'],['restingHR','Resting heart rate']].map(([key,label])=>`<option value="${key}" ${key===metric?'selected':''}>${label}</option>`).join('')}</select></label>${metric==='sleepHours'?`<label>Split at (hours)<input id="recovery-threshold" type="number" min="0" max="24" step="0.5" value="${state.recoveryThreshold}"></label>`:`<div class="threshold-label">${state.insightExercise==='all'?'Split at each exercise’s paired-sample median':`Split at the paired-sample median: <strong>${cut} ${unit}</strong>`}</div>`}<div class="threshold-label">Exactly <strong>${state.repTarget} reps</strong></div></div>${state.insightExercise==='all'?allRecoveryComparisons(view,metric,unit):`<div class="comparison-cards"><article><small>Below ${cut} ${unit}</small><strong>${kg(comparison.low.mean)}</strong><span>Average recorded load · ${comparison.low.n} workouts</span></article><article><small>${cut} ${unit} or above</small><strong>${kg(comparison.high.mean)}</strong><span>Average recorded load · ${comparison.high.n} workouts</span></article><article><small>Paired workouts</small><strong>${comparison.pairs.length}</strong><span>${comparison.enough?'At least 3 in each group':'Fewer than 3 in one or both groups'}</span></article></div><p class="feature-note">A descriptive comparison, not evidence that sleep, HRV or RHR caused a performance change. Training programs and time trends also affect load. Unpaired dates and missing readings are excluded.</p><div class="table-scroll"><table><thead><tr><th>Workout date</th><th>${state.repTarget}-rep load</th><th>${{sleepHours:'Sleep duration',hrv:'Overnight HRV',restingHR:'Resting HR'}[metric]}</th><th>Group</th></tr></thead><tbody>${[...comparison.pairs].reverse().map(p=>`<tr><td><button class="table-date" data-session="${escape(p.id)}">${date(p.date,true)}</button></td><td>${kg(p.weight)}</td><td>${number(p.recovery,1)} ${unit}</td><td>${p.recovery<comparison.threshold?'Below split':'At or above split'}</td></tr>`).join('')||'<tr><td colspan="4">No paired readings for these matching-rep sets. Try a different exercise, rep count or date range.</td></tr>'}</tbody></table></div>`}</section>`;
}
const volumeColor=name=>MUSCLE_GROUPS.includes(name)?muscleColor(name):['All muscles','All exercises'].includes(name)?'var(--muted)':exerciseColor(name,state.data?.muscleOverrides||{});
function exerciseLabel(name) {
  return `<span class="exercise-identity" style="--exercise-accent:${exerciseColor(name,state.data?.muscleOverrides||{})}">${escape(name)}</span>`;
}
function volumeExerciseImpact(sets,field) {
  const rows=volumeByWeek(sets,'exercise').sort((a,b)=>(b[field]??-Infinity)-(a[field]??-Infinity)||a.group.localeCompare(b.group));
  const total=rows.reduce((sum,row)=>sum+(row[field]??0),0);
  const unit={volume:'adjusted kg·reps',sets:'sets',reps:'reps',estimatedMax:'kg estimated 1RM'}[field];
  return `<div class="volume-exercise-impact"><div class="table-heading"><div><h3>Exercise impact this week</h3><p>Each exercise’s share of recorded ${unit}. Open an exercise to explore its history.</p></div></div><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Sets</th><th>Reps</th><th>Adjusted kg·reps</th><th>Share of ${unit}</th></tr></thead><tbody>${rows.map(row=>{
    const share=present(row[field])&&total>0?row[field]/total*100:null;
    return `<tr><td><button class="record-exercise" data-view-exercise="${escape(row.group)}">${exerciseLabel(row.group)}</button>${muscleTag(row.group)}</td><td>${row.sets}</td><td>${number(row.reps)}<small>${row.repsKnown}/${row.sets} sets recorded</small></td><td>${number(row.volume)}<small>${row.volumeKnown}/${row.sets} sets have inputs</small></td><td>${present(share)?`<div class="exercise-impact-share" data-motion-chart="true" data-motion-key="exercise-share:${escape(row.group)}" data-motion-metric="${field}"><span data-motion-bar="x" data-point-value="${share}" style="width:${share}%;background:${volumeColor(row.group)}"></span></div>${number(share,1)}%`:'—'}</td></tr>`;
  }).join('')||'<tr><td colspan="5">No exercises recorded in this week.</td></tr>'}</tbody></table></div><p class="feature-note">Shares use known values only; missing inputs are excluded. Adjusted volume estimates work, not muscle stimulus.</p></div>`;
}
function volumeHistoryPanel(view) {
  const specificExercise=state.volumeMode==='exercise'&&view.exercises.some(e=>e.name===state.volumeGroup.exercise);
  if(!specificExercise&&state.volumeMetric==='estimatedMax')state.volumeMetric='volume';
  const strengthMode=state.volumeMetric==='estimatedMax';
  const series=weeklyVolumeHistory(view.sets,state.volumeMode,state.data.muscleOverrides||{},range());
  if(strengthMode)for(const item of series){
    const estimates=new Map(estimatedStrengthHistory(view.sets,item.group,true,range()).map(p=>[p.date,p]));
    for(const week of item.history){const estimate=estimates.get(week.week);week.estimatedMax=estimate?.value??null;week.eligibleSets=estimate?.eligibleSets??0;}
  }
  if(!series.length)return '<section class="panel empty-panel">No volume history in the selected dates.</section>';
  const aggregate={...weeklyVolumeHistory(view.sets.map(r=>({...r,exercise:state.volumeMode==='exercise'?'All exercises':'All muscles'})),'exercise',{},range())[0],all:true};
  const contributions=volumeByWeek(view.sets,'exercise');
  for(const week of aggregate.history)week.exercises=contributions.filter(row=>row.week===week.week).sort((a,b)=>compareExerciseStack(a.group,b.group,state.data?.muscleOverrides||{}));
  const selected=strengthMode?(series.find(s=>s.group===state.volumeGroup.exercise)||series.find(s=>s.history.some(w=>present(w.estimatedMax)))||series[0]):state.volumeGroup[state.volumeMode]==='all'?aggregate:series.find(s=>s.group===state.volumeGroup[state.volumeMode])||aggregate;state.volumeGroup[state.volumeMode]=selected.all?'all':selected.group;
  const field=state.volumeMetric,unit={volume:'adjusted kg·reps',sets:'sets',reps:'reps',estimatedMax:'kg estimated 1RM'}[field];
  if(!selected.history.some(w=>w.week===state.volumeWeek))state.volumeWeek=[...selected.history].reverse().find(w=>w.sets)?.week||selected.history.at(-1).week;
  const week=selected.history.find(w=>w.week===state.volumeWeek);
  const recorded=selected.history.filter(w=>w.sets>0&&present(w[field]));
  const peak=recorded.length?Math.max(...recorded.map(w=>w[field])):null;
  const matchesGroup=s=>{
    if(state.volumeMode==='exercise')return s.exercise===selected.group;
    const roles=exerciseMuscles(s.exercise,state.data.muscleOverrides||{});
    return [...roles.primary,...roles.secondary].includes(selected.group);
  };
  const details=view.sets.filter(s=>(selected.all||matchesGroup(s))&&s.date>=week.from&&s.date<=week.to);
  const workouts=view.workouts.filter(w=>details.some(s=>s.sessionId===w.id));
  return `<section class="panel volume-history-panel"><div class="table-heading"><div><span class="eyebrow">VOLUME OVER TIME</span><h2>Historical weekly trends</h2><p>Pick any muscle or exercise. Click a week to inspect its records.</p></div></div><div class="feature-controls"><div class="segmented" role="group" aria-label="Group volume history">${[['muscle','Muscle involvement'],['exercise','Exercise']].map(([key,label])=>`<button data-volume-mode="${key}" class="${state.volumeMode===key?'active':''}" aria-pressed="${state.volumeMode===key}">${label}</button>`).join('')}</div><div class="segmented" role="group" aria-label="Historical metric">${[['volume','Adjusted volume'],['sets','Sets'],['reps','Reps'],...(specificExercise?[['estimatedMax','Est. 1RM']]:[])].map(([key,label])=>`<button data-volume-metric="${key}" class="${field===key?'active':''}" aria-pressed="${field===key}">${label}</button>`).join('')}</div></div><div class="volume-group-picker" role="group" aria-label="Choose muscle or exercise">${[aggregate,...series].map(s=>`<button data-volume-group="${s.all?'all':escape(s.group)}" class="${s.group===selected.group?'active':''}" aria-pressed="${s.group===selected.group}"><i style="background:${volumeColor(s.group)}"></i>${escape(s.group)} <small>${s.count}</small></button>`).join('')}</div><div class="volume-history-title"><h3>${escape(selected.group)}</h3><span>${selected.history.length} calendar weeks · peak recorded week ${number(peak,field==='estimatedMax'?1:0)} ${unit}</span></div>${volumeHistoryChart(selected,field)}${strengthMode?'<p class="feature-note">Best eligible Epley estimate per week for the selected exercise, from positive loads and 1–10 reps. Different exercises are never added or averaged. Missing estimates stay blank. Select a week to open its source workouts below.</p>':''}${selected.all?'<p class="feature-note">Each weekly bar is split by exercise. Hover a segment for its contribution; select a week for the breakdown below. Segments run bottom-to-top from calves through legs, hips and core to upper body, grouped by primary muscle. Exercise shades follow that group.</p>':''}<div class="volume-week-detail"><div><span class="eyebrow">WEEK STARTING ${escape(date(week.week,true).toUpperCase())}${week.partial?' · PARTIAL WEEK':''}</span><strong>${number(week[field],field==='estimatedMax'?1:0)} ${unit}</strong><span>${week.sets} recorded sets · ${number(week.reps)} recorded reps · ${number(week.volume)} kg·reps</span><small>${week.noRecords?'No sets recorded for this group in this week.':`${week.volumeKnown}/${week.sets} sets have volume · ${week.repsKnown}/${week.sets} have reps`}</small></div><div class="volume-week-workouts">${workouts.map(w=>`<button class="text-link" data-session="${escape(w.id)}">${date(w.date)} · ${escape(w.name)} ${icon('arrow')}</button>`).join('')}</div></div>${selected.all?volumeExerciseImpact(details,field):''}<p class="feature-note">Each involved primary and secondary muscle receives the set’s full sets, reps and adjusted volume. Muscle totals overlap and must not be added together; All muscles and All exercises count each set once. Secondary work is not equivalent to direct work or measured muscle stimulus. Weeks start Monday. Bars show recorded totals within your date and source filters. Empty weeks mean no recorded sets; a ? means sets exist but the selected metric is missing. Partial boundaries and the current week are marked. Adjusted volume includes your configured bodyweight fractions and exercise multipliers. Missing bodyweight, zero or missing external resistance, and unidentified movements are excluded; Sets and Reps still count.</p></section><section class="volume-history-cards" aria-label="Trends for each muscle or exercise">${series.slice(0,state.volumeCards).map(s=>`<button class="panel volume-mini ${s.group===selected.group?'selected':''}" data-volume-group="${escape(s.group)}"><span><strong>${escape(s.group)}</strong><small>${s.count} sets in range</small></span>${volumeMiniChart(s,field)}<small>Weekly ${unit} · open detailed history ${icon('arrow')}</small></button>`).join('')}</section>${series.length>state.volumeCards?'<button class="button volume-more" data-action="more-volume-cards">Show more exercise histories</button>':''}`;
}
function volumeHistoryChart(series,field,interactive=true) {
  const weeks=series.history,color=volumeColor(series.group),W=1000,H=280,pad={l:72,r:20,t:24,b:45},width=W-pad.l-pad.r,height=H-pad.t-pad.b;
  const max=Math.max(1,...weeks.filter(w=>present(w[field])).map(w=>w[field]));const top=max*1.1;
  const step=width/weeks.length,bar=Math.max(2,Math.min(34,step*.75)),x=i=>pad.l+step*(i+.5),y=v=>pad.t+height-v/top*height;
  const unit={volume:'adjusted kg·reps',sets:'sets',reps:'reps',estimatedMax:'kg estimated 1RM'}[field];
  const label=w=>`${date(w.week,true)}: ${present(w[field])?number(w[field],field==='estimatedMax'?1:0)+' '+unit:'metric not recorded'}; ${w.sets} recorded sets; ${w.partial?'partial week; ':''}${field==='estimatedMax'?`${w.eligibleSets}/${w.sets} eligible sets`:`${w.volumeKnown}/${w.sets} sets have volume`}`;
  const segments=(week,i)=>{
    let accumulated=0;
    return [...(week.exercises||[])].sort((a,b)=>compareExerciseStack(a.group,b.group,state.data?.muscleOverrides||{})).filter(row=>present(row[field])&&row[field]>0).map(row=>{
      accumulated+=row[field];
      const description=`${row.group}: ${number(row[field],1)} ${unit} · ${number(row[field]/week[field]*100,1)}% of week`;
      return `<rect class="volume-exercise-segment" data-exercise-color="${escape(row.group)}" data-point-value="${row[field]}" x="${x(i)-bar/2}" y="${y(accumulated)}" width="${bar}" height="${row[field]/top*height}" fill="${exerciseVisual(row.group).color}" opacity="${week.partial?.65:1}"><title>${escape(description)}</title></rect>`;
    }).join('');
  };
  const indices=[...new Set([0,Math.round((weeks.length-1)/4),Math.round((weeks.length-1)/2),Math.round((weeks.length-1)*.75),weeks.length-1])];
  return `<div class="volume-chart-scroll"><svg data-time-start="${new Date(weeks[0].week).getTime()}" data-time-end="${new Date(weeks.at(-1).week).getTime()+7*86400000-1}" data-plot-left="${pad.l}" data-plot-right="${W-pad.r}" data-plot-top="${pad.t}" data-plot-bottom="${H-pad.b}" class="volume-history-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${escape(series.group)} weekly ${unit} history">${[0,.25,.5,.75,1].map(f=>`<line x1="${pad.l}" x2="${W-pad.r}" y1="${y(top*f)}" y2="${y(top*f)}" stroke="var(--line)" stroke-dasharray="3 5"/><text x="${pad.l-12}" y="${y(top*f)+5}" text-anchor="end" class="chart-label">${number(top*f,top<10?1:0)}</text>`).join('')}${weeks.map((w,i)=>`<g class="volume-week-bar ${w.week===state.volumeWeek?'selected':''}" ${interactive?`data-volume-week="${w.week}" role="button" tabindex="0" aria-pressed="${w.week===state.volumeWeek}"`:''} aria-label="${escape(label(w))}"><title>${escape(label(w)+(w.exercises?' · '+w.exercises.map(row=>row.group+': '+number(row[field],1)+' '+unit).join('; '):''))}</title><rect x="${x(i)-step/2}" y="${pad.t}" width="${step}" height="${height+8}" fill="transparent"/><rect class="volume-value-bar" data-point-value="${present(w[field])?w[field]:''}" x="${x(i)-bar/2}" y="${present(w[field])?y(w[field]):y(0)-12}" width="${bar}" height="${present(w[field])?Math.max(2,w[field]/top*height):12}" rx="2" fill="${w.exercises?.some(row=>row[field]>0)?'transparent':present(w[field])?color:'var(--muted)'}" opacity="${w.noRecords?.22:w.partial?.55:1}"/>${segments(w,i)}${!present(w[field])?`<text x="${x(i)}" y="${y(0)-18}" text-anchor="middle" class="chart-label">?</text>`:''}${w.partial?`<circle cx="${x(i)}" cy="${y(0)+9}" r="2" fill="var(--muted)"/>`:''}</g>`).join('')}${indices.map(i=>`<text x="${x(i)}" y="${H-10}" text-anchor="${i===0?'start':i===weeks.length-1?'end':'middle'}" class="chart-label">${date(weeks[i].week,true)}</text>`).join('')}</svg></div>`;
}
function volumeMiniChart(series,field) {
  const W=300,H=70,values=series.history,max=Math.max(1,...values.filter(w=>present(w[field])).map(w=>w[field]));
  const step=280/values.length;
  return `<svg class="volume-mini-svg" data-motion-key="volume-mini:${escape(series.group)}" data-motion-metric="${field}" data-time-start="${values[0]?.week||''}" data-time-end="${values.at(-1)?.week||''}" data-plot-bottom="60" viewBox="0 0 ${W} ${H}" aria-hidden="true">${values.map((w,i)=>present(w[field])?`<rect class="volume-value-bar" data-point-value="${w[field]}" x="${10+i*step}" y="${60-w[field]/max*50}" width="${Math.max(1,step*.7)}" height="${Math.max(1,w[field]/max*50)}" fill="${volumeColor(series.group)}" opacity="${w.noRecords?.2:w.partial?.55:1}"/>`:'').join('')}</svg>`;
}

function weeklyMuscleMap(view) {
  const selectedRange=range(),weeks=muscleMapWeeks(view.sets,selectedRange,today());
  if(!weeks.length)return '<section class="panel empty-panel">No weeks in this date range.</section>';
  if(!weeks.includes(state.mapWeek))state.mapWeek=weeks.at(-1);
  const summary=muscleWeekSummary(view.sets,state.mapWeek,state.data.muscleOverrides||{},state.mapSecondary);
  const historySets=adjustedVolumeSets(state.data.sets.filter(s=>state.source==='all'||s.source===state.source),state.data.recovery||[],state.data.volumeSettings||{});
  const historyStart=state.data.sets.map(s=>s.date).sort()[0];
  const comparison=muscleWeekComparison(historySets,state.mapWeek,{count:state.mapCompare,range:selectedRange,asOf:today(),historyStart,overrides:state.data.muscleOverrides||{},includeSecondary:state.mapSecondary});
  return renderMuscleMap({summary,weeks,comparison,weekLimit:state.mapWeekLimit,selected:state.mapMuscle,includeSecondary:state.mapSecondary,overrides:state.data.muscleOverrides||{},...selectedRange,asOf:today()});
}
function updateMuscleMap(focusId) {
  const host=$('#weekly-muscle-map');if(!host)return;
  const {scrollX,scrollY}=window;
  host.innerHTML=weeklyMuscleMap(current());
  if(focusId)document.getElementById(focusId)?.focus({preventScroll:true});
  window.scrollTo({left:scrollX,top:scrollY,behavior:'instant'});
}

function volumeSettingsEditor(sets, expanded = false) {
  const settings=state.data.volumeSettings||{};
  const names=[...new Set([...state.data.sets.map(s=>s.exercise),...Object.keys(settings.exercises||{})])].sort((a,b)=>a.localeCompare(b));
  const missing=sets.filter(s=>s.missingBodyweight).length,unreviewed=sets.filter(s=>s.unreviewed).length,missingLoads=sets.filter(s=>s.missingLoad&&!s.unreviewed).length;
  return `<details id="volume-settings" class="panel muscle-editor" ${expanded?'open':''}><summary>Adjust exercise volume factors</summary><p>Available movement profiles and their assumptions are shown below. Exercises without a reviewed profile are excluded until you explicitly enable custom factors. Scores estimate external work relative to lifting 1 kg through 0.40 m once. They do not measure muscle force or make exercises equivalent for muscle growth.</p><p>Adjusted volume = max(0, signed load × load copies + body weight × fraction) × reps × multiplier. The default multiplier is estimated movement travel × resistance ratio ÷ 0.40 m. The distances and bodyweight fractions are starting assumptions, not measurements. Assisted loads are subtracted.</p><p>Your logging convention: kg per dumbbell; total reps across sides. Simultaneous two-dumbbell lifts use 2 load copies. One-arm/one-leg reps are already counted across sides and get no extra side multiplier. Cable pulley and machine lever ratios need equipment-specific calibration; a cable is not automatically half resistance.</p><p>Body weight uses the latest reading on or before each workout date, then your fallback. The bodyweight fraction is a work-equivalent contribution: torso/limb movement may be shorter than the load path. Saved custom values take priority; resetting a row restores its reviewed defaults when you save. Changes recalculate all weekly history.</p><p class="feature-note">Method: <a href="https://openstax.org/books/physics/pages/9-3-simple-machines" target="_blank" rel="noreferrer">force, travel and mechanical advantage</a> · <a href="https://pubmed.ncbi.nlm.nih.gov/20179649/" target="_blank" rel="noreferrer">push-up supported body mass</a> · <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC9339067/" target="_blank" rel="noreferrer">limits of load × reps</a>. These sources support the method, not the individual assumed distances.</p>${missing?`<p class="notice">${missing} sets need a bodyweight reading. Enter a fallback to include them.</p>`:''}${unreviewed?`<p class="notice">${unreviewed} sets have no reviewed volume profile and are excluded. Correct misidentified exercises in Log & edit, or review and enable custom factors below.</p>`:''}${missingLoads?`<p class="notice">${missingLoads} externally loaded sets have zero recorded kg. Their resistance needs correction in Log & edit; a factor cannot recover a missing load.</p>`:''}<form id="volume-form" data-revision="${escape(state.data.metadataRevision)}"><label>Fallback body weight (kg)<input name="bodyWeightKg" type="number" min="1" max="500" step="0.1" value="${settings.bodyWeightKg??''}" placeholder="Used when no earlier reading exists"></label><div class="table-scroll"><table class="volume-factors-table"><thead><tr><th>Exercise and default reasoning</th><th>Multiplier</th><th>Load copies</th><th>BW fraction (0–1)</th><th>Recorded load means</th><th>Defaults</th></tr></thead><tbody>${names.map(name=>{
    const rule=exerciseVolumeRule(name,settings),profile=exerciseVolumeRule(name);
    const status={estimate:'Movement estimate',calibrate:'Needs calibration',unidentified:rule.reviewed?'Custom estimate':'Excluded: no reviewed profile'}[profile.confidence];
    return `<tr data-volume-exercise="${escape(name)}"><td><strong>${exerciseLabel(name)}</strong><small class="cell-description">${status}${rule.custom?' · Custom values':''}</small>${profile.confidence==='unidentified'?`<label class="custom-volume-review"><input type="checkbox" data-factor="reviewed" aria-label="Use custom volume factors for ${escape(name)}" ${rule.reviewed?'checked':''}> Use my reviewed factors</label>`:''}<small class="volume-factor-reason">${escape(profile.rationale)}</small><small class="volume-factor-reason">Default factor ${number(profile.multiplier,4)}${profile.travelM?` = ${number(profile.travelM,2)} m × ${number(profile.forceRatio,4)} ÷ 0.40 m`:''}; load copies ${profile.loadCopies}; BW ${number(profile.bodyweight*100)}%.</small></td><td><input aria-label="${escape(name)} multiplier" data-factor="multiplier" type="number" required min="0.0001" max="10" step="0.0001" value="${rule.multiplier}"></td><td><select aria-label="${escape(name)} load copies" data-factor="loadCopies"><option value="1" ${rule.loadCopies===1?'selected':''}>1 load</option><option value="2" ${rule.loadCopies===2?'selected':''}>2 loads</option></select></td><td><input aria-label="${escape(name)} bodyweight fraction" data-factor="bodyweight" type="number" required min="0" max="1" step="0.01" value="${rule.bodyweight}"></td><td><select aria-label="${escape(name)} load meaning" data-factor="assistance"><option value="false" ${!rule.assistance?'selected':''}>Added weight</option><option value="true" ${rule.assistance?'selected':''}>Assistance</option></select></td><td><button class="button" type="button" data-volume-reset="${escape(name)}">Reset row</button></td></tr>`;
  }).join('')}</tbody></table></div><button class="button button-dark" type="submit">Save volume factors</button><span class="form-error" role="status"></span></form></details>`;
}

function volumePage(view) {
  if(state.volumeMetric==='estimatedMax'&&(state.volumeMode!=='exercise'||!view.exercises.some(e=>e.name===state.volumeGroup.exercise)))state.volumeMetric='volume';
  const sets=view.sets;
  const rows=volumeByWeek(sets,state.volumeMode,state.data.muscleOverrides||{}),groups=[...new Set(rows.map(r=>r.group))];
  const currentWeek=weekStart(today()),previous=new Date(currentWeek+'T00:00:00Z');previous.setUTCDate(previous.getUTCDate()-7);const previousWeek=previous.toISOString().slice(0,10);
  const totals=groups.map(group=>{const a=rows.filter(r=>r.group===group);return {group,sets:a.reduce((n,r)=>n+r.sets,0),reps:sumKnown(a.map(r=>r.reps)),volume:sumKnown(a.map(r=>r.volume)),known:a.reduce((n,r)=>n+r.volumeKnown,0),current:a.find(r=>r.week===currentWeek)?.sets||0,prior:a.find(r=>r.week===previousWeek)?.sets||0};}).sort((a,b)=>b.sets-a.sets);
  const overrides=state.data.muscleOverrides||{};
  return header('Weekly training volume','Explore your weekly muscle map, then follow your sets, reps and load over time.')+`<div id="weekly-muscle-map">${weeklyMuscleMap(view)}</div>`+`<p class="feature-note">Tune bodyweight contributions and exercise multipliers in <a class="text-link" href="#preferences">Preferences → Volume factors</a>.${sets.some(s=>s.missingBodyweight)?' Some sets need a bodyweight reading or fallback weight before they can count toward adjusted volume.':''}</p>`+volumeHistoryPanel(view)+`<section class="panel feature-panel"><div class="table-heading"><div><h2>Your weekly workload</h2><p>Each set counts once per involved muscle, or once per exercise. Volume uses your bodyweight fractions and exercise multipliers; missing inputs are excluded.</p></div></div><div class="feature-controls"><div class="segmented">${[['muscle','Muscle involvement'],['exercise','Exercise']].map(([key,label])=>`<button data-volume-mode="${key}" class="${state.volumeMode===key?'active':''}">${label}</button>`).join('')}</div><span class="muted">Using the date range above</span></div><div class="table-scroll"><table><thead><tr><th>${state.volumeMode==='muscle'?'Muscle involvement':'Exercise'}</th><th>Sets</th><th>Reps</th><th>Adjusted volume</th><th>This week</th><th>Previous week</th><th>Set change</th></tr></thead><tbody>${totals.map(r=>`<tr><td>${escape(r.group)}</td><td>${r.sets}</td><td>${number(r.reps)}</td><td>${number(r.volume)} <small class="cell-description">kg·reps · ${r.known}/${r.sets} sets have the required inputs</small></td><td>${r.current}</td><td>${r.prior}</td><td class="${r.current>r.prior?'positive':''}">${r.current>r.prior?'+':''}${r.current-r.prior}</td></tr>`).join('')||'<tr><td colspan="7">No recorded sets in this date range. Choose a wider range above.</td></tr>'}</tbody></table></div><p class="feature-note">The current week is partial. Muscle groups include primary and secondary involvement, using the same assignments as the historical charts. Muscle totals overlap; secondary work is not equivalent to direct work. Saved primary-muscle overrides take precedence.</p></section><section class="panel feature-panel"><div class="table-heading"><div><h2>Week-by-week details</h2><p>Dates mark the Monday that starts each week.</p></div><span class="count-chip">${rows.length} entries</span></div><div class="table-scroll"><table><thead><tr><th>Week starting</th><th>Group</th><th>Sets</th><th>Recorded reps</th><th>Adjusted kg·reps</th></tr></thead><tbody>${rows.slice(0,state.volumeLimit).map(r=>`<tr><td>${date(r.week,true)}</td><td>${escape(r.group)}</td><td>${r.sets}</td><td>${number(r.reps)}</td><td>${number(r.volume)}</td></tr>`).join('')}</tbody></table></div>${rows.length>state.volumeLimit?'<button class="load-more" data-action="more-volume">Show more weeks</button>':''}</section><details class="panel muscle-editor"><summary>Edit primary muscle groups</summary><p>Choose one primary group per exercise. Ambiguous exercises remain Unassigned until you choose.</p><form id="muscle-form" data-revision="${escape(state.data.metadataRevision)}"><div class="muscle-grid">${view.exercises.map(e=>`<label>${exerciseLabel(e.name)}<select data-muscle="${escape(e.name)}">${MUSCLE_GROUPS.map(g=>`<option ${(overrides[e.name]||DEFAULT_MUSCLES[e.name]||'Unassigned')===g?'selected':''}>${g}</option>`).join('')}</select></label>`).join('')}</div><button class="button button-dark" type="submit">Save muscle mappings</button><span class="form-error" role="status"></span></form></details>`;
}
function comparePage(view) {
  const workouts=[...view.workouts].sort((a,b)=>b.date.localeCompare(a.date)||b.time.localeCompare(a.time));
  if(workouts.length<2)return header('Compare workouts','Compare two sessions side by side.')+'<section class="panel empty-panel">Choose a date range containing at least two workouts.</section>';
  if(!workouts.some(w=>w.id===state.compareRight))state.compareRight=workouts[0].id;
  if(!workouts.some(w=>w.id===state.compareLeft)||state.compareLeft===state.compareRight)state.compareLeft=(workouts.find(w=>w.id!==state.compareRight&&w.name===workouts.find(w=>w.id===state.compareRight).name)||workouts.find(w=>w.id!==state.compareRight)).id;
  const a=workouts.find(w=>w.id===state.compareLeft),b=workouts.find(w=>w.id===state.compareRight);
  const rows=compareWorkouts(view,a.id,b.id);
  const select=(id,selected)=>`<select id="${id}">${workouts.map(w=>`<option value="${escape(w.id)}" ${w.id===selected?'selected':''}>${date(w.date,true)} · ${escape(w.name)}</option>`).join('')}</select>`;
  return header('Compare workouts','See what changed between two sessions, including sets at matching reps.')+`<div class="compare-picker"><label>Baseline workout${select('compare-left',a.id)}</label><button class="icon-button" data-action="swap-compare" title="Swap workouts" aria-label="Swap workouts">⇄</button><label>Comparison workout${select('compare-right',b.id)}</label></div><div class="comparison-cards">${[a,b].map(w=>`<article><small>${w.id===a.id?'BASELINE':'COMPARISON'} · ${date(w.date,true)}</small><strong class="workout-comparison-name">${escape(w.name)}</strong><span>${view.sets.filter(s=>s.sessionId===w.id).length} sets · ${duration(w.duration)}</span><button class="text-link" data-session="${escape(w.id)}">Open workout ${icon('arrow')}</button></article>`).join('')}</div><section class="panel feature-panel"><div class="table-heading"><div><h2>Exercise-by-exercise comparison</h2><p>Load and rep records can come from different sets. Matching-rep comparisons below use the same rep count. For assisted exercises, lower kg means less help.</p></div></div><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Baseline sets / reps</th><th>Comparison sets / reps</th><th>Best load: baseline → comparison</th><th>Adjusted volume change</th><th>Matching-rep loads</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${exerciseLabel(r.name)}</td><td>${r.left?`${r.left.count} / ${number(r.left.reps)}`:'—'}</td><td>${r.right?`${r.right.count} / ${number(r.right.reps)}`:'—'}</td><td>${kg(r.left?.bestWeight)} → ${kg(r.right?.bestWeight)}</td><td>${present(r.volumeChange)?(r.volumeChange>0?'+':'')+number(r.volumeChange)+' kg·reps':r.left&&r.right?'Incomplete inputs':'—'}</td><td>${r.matched.map(m=>`<span class="match-chip">${m.reps} reps: ${number(m.left,1)} → ${number(m.right,1)} kg</span>`).join('')||'No shared recorded rep count'}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function goalsPage() {
  const goals=state.data.goals||[],archived=state.data.archivedGoals||[];
  return header('Training goals','Targets checked against real recorded sets, across your full training history.')+`<div class="workout-toolbar"><span>${goals.length} active targets · independent of date filters</span><button class="button button-dark" data-action="new-goal">+ Add a goal</button></div><div class="goals-grid">${goals.map(g=>{const p=goalProgress(g,state.data.sets,state.data.volumeSettings||{});return `<article class="panel goal-card"><div class="goal-card-top"><span class="signal ${p.achieved?'progressing':'insufficient'}">${p.achieved?'Recorded target achieved':'In progress'}</span><button class="text-link" data-edit-goal="${g.id}">Edit</button></div><h2>${exerciseLabel(g.exercise)}</h2><strong class="goal-target">${g.mode==='reps'?`${g.reps} reps`:`${p.assisted?'≤ ':''}${number(g.weight,1)} kg${p.assisted?' assistance':''} × ${g.reps} reps`}</strong><div class="goal-track" data-motion-chart="true" data-motion-key="goal:${g.id}"><span data-motion-bar="x" data-point-value="${p.percent??0}" style="width:${p.percent??0}%"></span></div><p>${p.achieved?`Reached in recorded history on ${date(p.date,true)}`:present(p.best)?`Best qualifying record: ${number(p.best,1)} ${g.mode==='reps'?'reps':(p.assisted?'kg assistance at ':'kg at ')+g.reps+'+ reps'}`:'No qualifying recorded set yet.'}</p><p class="muted">${g.deadline?'Target date: '+date(g.deadline,true):'No target date'}</p><div class="goal-actions">${p.sessionId?`<button class="text-link" data-session="${escape(p.sessionId)}">View achieved set’s workout ${icon('arrow')}</button>`:''}<button class="text-link muted" data-archive-goal="${g.id}">Archive</button></div></article>`;}).join('')||'<section class="panel empty-panel"><h2>Choose your next target</h2><p>Add a load-and-reps goal or a reps-only goal. Progress comes from actual sets; nothing is pre-filled as an achievement.</p><button class="button button-dark" data-action="new-goal">Add your first goal</button></section>'}</div>${archived.length?`<details class="panel muscle-editor"><summary>Archived goals (${archived.length})</summary>${archived.map(g=>`<div class="archive-goal"><span>${exerciseLabel(g.exercise)} · ${g.reps} reps</span><button class="text-link" data-restore-goal="${g.id}">Restore</button></div>`).join('')}</details>`:''}`;
}
function loggingPage(view) {
  const drafts=Object.entries(storedDrafts()).filter(([,draft])=>draft&&Array.isArray(draft.sets));
  const resume=drafts.length?`<section class="panel draft-resume"><h2>Unsaved workouts</h2><p>Kept only in this browser. Resume a draft to finish or discard it.</p>${drafts.map(([key,draft])=>`<button class="button" data-resume-draft="${escape(key)}">Resume ${escape(draft.name||'workout')} · ${escape(draft.date||'')}</button>`).join('')}</section>`:'';
  const workouts=[...view.workouts].sort((a,b)=>b.date.localeCompare(a.date)||b.time.localeCompare(a.time));
  return header('Log & edit training','Add a manual session, correct exercise names, or fill in missing loads and reps.')+resume+`<div class="workout-toolbar"><span>Saved changes update the shared training database.</span><button class="button button-dark" data-action="new-workout">+ Log workout</button></div><section class="panel feature-panel"><div class="table-heading"><div><h2>Your workouts</h2><p>Garmin timing and health measurements are retained when you edit its sets.</p></div></div><div class="table-scroll"><table><thead><tr><th>Date</th><th>Workout</th><th>Recorded sets</th><th>Missing load / reps</th><th>Edit</th></tr></thead><tbody>${workouts.length?'':'<tr><td colspan="5">No workouts in these filters. Log a workout or broaden the date range.</td></tr>'}${workouts.map(w=>{const rows=[...state.data.sets,...(state.data.hiddenSets||[])].filter(s=>s.sessionId===w.id),unknown=rows.filter(s=>s.exercise.trim().toLowerCase()==='unknown').length;return `<tr><td>${date(w.date,true)}</td><td><button class="record-exercise" data-session="${escape(w.id)}">${escape(w.name)}</button></td><td>${rows.length}${unknown?`<small>${unknown} unidentified</small>`:''}</td><td>${rows.filter(s=>!present(s.weight)).length} / ${rows.filter(s=>!present(s.reps)).length}</td><td><button class="button" data-edit-workout="${escape(w.id)}">Edit sets</button></td></tr>`;}).join('')}</tbody></table></div></section><section class="panel feature-panel"><div class="table-heading"><div><h2>Recent changes</h2><p>Originals are backed up. Undo is available when that workout has no newer changes.</p></div></div><div class="edit-history">${(state.data.edits||[]).map(e=>`<div><span><strong>${escape(e.name)}</strong><small>${escape(new Date(e.created).toLocaleString())}</small></span>${e.undone?'<span class="muted">Undone</span>':`<button class="button" data-undo-edit="${e.id}">Undo this edit</button>`}</div>`).join('')||'<p class="small-empty">No app edits yet. Existing Garmin and CSV records are unchanged.</p>'}</div></section>`;
}
async function saveAction(body, savedForm=null) {
  const response=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({requestId:crypto.randomUUID(),...body}),signal:AbortSignal.timeout(30000)});
  const result=await response.json();
  if(!response.ok){const error=new Error(result.error||'Could not save the change');error.status=response.status;throw error;}
  if(savedForm){delete savedForm.dataset.dirty;settingsDrafts.delete(savedForm.id);}
  await load(true,true);return result;
}
async function deleteFood(identity) {
  try {
    const response=await fetch('/api/food',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',id:identity})});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Could not delete food entry');
    state.foodDeleteId='';await load(true,true);toast('Food entry deleted.');
  } catch(error) {toast(error.message||'Could not delete food entry.');}
}
function openEditor(content) {
  $('#editor-content').innerHTML=content;
  if(!$('#editor-dialog').open)$('#editor-dialog').showModal();
}
function showGoalEditor(id=null) {
  const g=(state.data.goals||[]).find(g=>g.id===id)||{exercise:state.selected==='all'?'':state.selected,reps:5,weight:'',mode:'load_reps',deadline:''};
  openEditor(`<form id="goal-form" data-id="${id||crypto.randomUUID()}"><div class="dialog-heading"><div><span class="eyebrow">TRAINING TARGET</span><h2 id="editor-title">${id?'Edit goal':'Set a goal'}</h2></div><button type="button" class="icon-button close-editor" aria-label="Close editor">${icon('close')}</button></div><div class="editor-fields"><label>Exercise<input name="exercise" list="exercise-options" required maxlength="120" value="${escape(g.exercise)}"></label><label>Goal type<select name="mode" id="goal-mode"><option value="load_reps" ${g.mode==='load_reps'?'selected':''}>Load and reps in the same set</option><option value="reps" ${g.mode==='reps'?'selected':''}>Reps only</option></select></label><label>Target load / assistance (kg)<input name="weight" type="number" min="0" max="2000" step="any" value="${g.weight??''}" ${g.mode==='reps'?'disabled':''}></label><label>Target reps<input name="reps" type="number" min="1" max="500" required value="${g.reps}"></label><label>Target date (optional)<input name="deadline" type="date" value="${g.deadline||''}"></label></div><div class="form-error" role="alert"></div><div class="dialog-footer"><span>One actual set must meet both targets. For assisted exercises, the kg target is maximum assistance; less assistance qualifies.</span><button type="submit" class="button button-dark">Save goal</button></div></form>${exerciseOptions()}`);
}
function exerciseOptions(){return `<datalist id="exercise-options">${exerciseSummaries(state.data.sets).map(e=>`<option value="${escape(e.name)}"></option>`).join('')}</datalist>`;}
// Drafts stay in this browser, keyed by workout so opening another cannot erase work.
const draftStorageKey = 'form-workout-drafts-v1';
function storedDrafts() {
  try { const value=JSON.parse(localStorage.getItem(draftStorageKey)||'{}'); return value&&typeof value==='object'&&!Array.isArray(value)?value:{}; }
  catch { return {}; }
}
function persistDraft() {
  if(!state.draft)return;
  try { const drafts=storedDrafts();drafts[state.draft.sessionId||'new']=state.draft;localStorage.setItem(draftStorageKey,JSON.stringify(drafts)); }
  catch { const status=$('#draft-status');if(status)status.textContent='Draft storage is unavailable. Keep this tab open until you save.'; }
}
function removeStoredDraft(id) {
  try { const drafts=storedDrafts();delete drafts[id||'new'];localStorage.setItem(draftStorageKey,JSON.stringify(drafts)); } catch {}
}
function draftRows() {
  return state.draft.sets.map((s,i)=>`<tr><td class="draft-number">Set ${i+1}</td><td data-label="Exercise"><input style="color:${exerciseVisual(s.exercise).color}" data-row="${i}" data-field="exercise" list="exercise-options" value="${escape(s.exercise)}" required maxlength="120" aria-label="Exercise for set ${i+1}"></td><td data-label="Load (kg)"><input data-row="${i}" data-field="weight" type="number" inputmode="decimal" min="0" max="2000" step="any" value="${s.weight??''}" aria-label="Load for set ${i+1}"></td><td data-label="Reps"><input data-row="${i}" data-field="reps" type="number" inputmode="numeric" min="0" max="500" value="${s.reps??''}" aria-label="Reps for set ${i+1}"></td><td data-label="Note (optional)"><input data-row="${i}" data-field="note" maxlength="1000" value="${escape(s.note)}" aria-label="Note for set ${i+1}"></td><td class="draft-actions"><button type="button" class="row-arrow" data-copy-draft="${i}" title="Duplicate set" aria-label="Duplicate set ${i+1}">+</button><button type="button" class="row-arrow" data-remove-draft="${i}" title="Remove set" aria-label="Remove set ${i+1}">×</button></td></tr>`).join('');
}
function showWorkoutEditor(id=null, fresh=false) {
  const w=state.data.workouts.find(w=>w.id===id),saved=storedDrafts()[id||'new'];
  const usable=saved&&Array.isArray(saved.sets)&&saved.sets.length&&saved.requestId;
  state.draft=!fresh&&usable?saved:{requestId:crypto.randomUUID(),sessionId:id,revision:w?.revision,
    expectedMetadata:w?{name:w.name,date:w.date,duration:w.duration}:undefined,
    name:w?.name||'Manual workout',date:w?.date||today(),durationMinutes:present(w?.duration)?w.duration/60:'',
    sets:w?[...state.data.sets,...(state.data.hiddenSets||[])].filter(s=>s.sessionId===id).sort((a,b)=>(a.order||0)-(b.order||0)).map(s=>({id:s.id,exercise:s.exercise,weight:s.weight,reps:s.reps,note:s.note||''})):[{exercise:state.selected==='all'?'Barbell Bench Press':state.selected||'Barbell Bench Press',weight:null,reps:null,note:''}]};
  const draft=state.draft;
  openEditor(`<form id="workout-form"><div class="dialog-heading"><div><span class="eyebrow">TRAINING JOURNAL</span><h2 id="editor-title">${w?'Edit workout':'Log a workout'}</h2><p>${w?'Correct details and sets. Unrelated watch measurements are retained.':'Add the date and actual sets you recorded. Leave unknown measurements blank.'}</p></div><button type="button" class="icon-button close-editor" aria-label="Close editor">${icon('close')}</button></div><p id="draft-status" class="feature-note" role="status">${!fresh&&usable?'Restored your unsaved draft.':'Your draft is kept in this browser until saved or discarded.'}</p><fieldset class="workout-inputs" ${draft.pending?'disabled':''}><div class="editor-fields"><label>Workout name<input name="name" required maxlength="180" value="${escape(draft.name)}"></label><label>Date<input name="date" type="date" required max="${today()}" value="${escape(draft.date)}"></label><label>Recorded duration (minutes, optional)<input name="durationMinutes" type="number" min="0" max="1440" step="any" value="${draft.durationMinutes??''}"></label></div><div class="draft-help">Each row is one set. Blank means unknown; zero means recorded zero. Load is in kg, using the same equipment and per-side convention as your history. Unknown exercises are included here so you can identify them.</div><div class="table-scroll"><table class="draft-table"><thead><tr><th>#</th><th>Exercise</th><th>kg</th><th>Reps</th><th>Note (optional)</th><th>+ / remove</th></tr></thead><tbody id="draft-rows">${draftRows()}</tbody></table></div><button type="button" class="button add-set" data-action="add-draft-set">+ Add set</button></fieldset><div class="form-error" role="alert">${draft.pending?'The last save has not been confirmed. Retry the same save to check its result safely.':''}</div><div class="dialog-footer"><button type="button" class="button" data-action="discard-draft" ${draft.pending?'disabled':''}>Discard draft</button><button type="submit" class="button button-dark">${draft.pending?'Retry save':'Save workout'}</button></div></form>${exerciseOptions()}`);
}

function proposedSets(rows,exercise='') {
  return rows.map((s,i)=>`<span class="plan-set"><small>${i+1}</small>${loadLabel(exercise,s.weight)} <span class="muted">×</span> ${number(s.reps)} <span class="muted">reps</span></span>`).join('');
}
function progressionSettings(plan) {
  if(!plan.exercises.length)return '';
  return `<details class="panel muscle-editor"><summary>Rep ranges & equipment increments</summary><p>Settings apply to this exercise across all workout types and Telegram images. Use your actual equipment increment; recorded loads are not converted per dumbbell or machine.</p><form id="progression-form" data-revision="${escape(state.data.metadataRevision)}"><div class="table-scroll"><table><thead><tr><th>Exercise</th><th>Lower rep target</th><th>Rep ceiling</th><th>Increase by (kg)</th></tr></thead><tbody>${plan.exercises.map(e=>`<tr data-progression-name="${escape(e.name)}"><td>${exerciseLabel(e.name)}</td><td><input aria-label="${escape(e.name)} lower reps" data-rule="repMin" type="number" min="1" max="29" required value="${e.rule.repMin}"></td><td><input aria-label="${escape(e.name)} rep ceiling" data-rule="repMax" type="number" min="2" max="30" required value="${e.rule.repMax}"></td><td><input aria-label="${escape(e.name)} weight increment" data-rule="weightStep" type="number" min="0.25" max="50" step="0.25" required value="${e.rule.weightStep}"><small class="cell-description">${e.rule.stepSource==='equipment'?'Using '+escape(e.rule.equipmentName)+' available loads':e.rule.stepSource==='custom'?'Your increment':'Suggested — check equipment'}</small></td></tr>`).join('')}</tbody></table></div><button class="button button-dark" type="submit">Save progression settings</button><span class="form-error" role="status"></span></form></details>`;
}

function nextSessionPage() {
  const plans=state.data.nextSessions||[],plan=plans.find(p=>p.type===state.planType)||plans[0];
  const heading=`<section class="page-heading"><div><div class="eyebrow">YOUR NEXT WORKOUT</div><h1>Next session<span class="heading-dot">.</span></h1><p>Proposed targets from your named workout history. Refresh after syncing a completed session.</p></div></section>`;
  if(!plan)return heading+'<section class="panel empty-panel">Proposals will appear after the training history refreshes.</section>';
  const names={weight_progress:'Increase weight',progress:'Add one rep',repeat:'Repeat & build',review:'Review first'};
  const latest=(state.data.recovery||[]).find(r=>r.date===today());
  return heading+`<div class="plan-types" role="group" aria-label="Choose workout type">${plans.map(p=>`<button class="panel plan-type ${p.type===plan.type?'selected':''}" data-plan-type="${p.type}" aria-pressed="${p.type===plan.type}"><strong>${escape(p.name)}</strong><span>Last: ${date(p.baselineDate,true)}</span><small>${p.exercises.length} exercises · ${p.evidenceCount} named sessions</small></button>`).join('')}</div><section class="panel plan-intro"><div><span class="eyebrow">PROPOSAL · ${escape(plan.name.toUpperCase())}</span><h2>${escape(plan.name)} — next targets</h2><p>${escape(plan.notice)}</p><p class="muted">Uses full history. Leg Day 1 / 2 are treated as Lower 1 / 2. Generic “Strength” workouts are not assigned a type; future sessions are ignored.</p></div><div class="plan-downloads">${Array.from({length:plan.imagePages},(_,i)=>`<a class="button button-dark" href="/api/plan.png?type=${plan.type}&page=${i}" download="form-${plan.type}-${i+1}.png">${icon('download')} Download image${plan.imagePages>1?' '+(i+1):''}</a>`).join('')}${plan.baselineId?`<button class="text-link" data-session="${escape(plan.baselineId)}">Open baseline workout ${icon('arrow')}</button>`:''}</div></section>${latest?`<div class="plan-recovery"><span>Today’s context · ${date(latest.date,true)}</span><span>Sleep <strong>${number(latest.sleepHours,1)} h</strong></span><span>HRV <strong>${number(latest.hrv)} ms</strong></span><span>RHR <strong>${number(latest.restingHR)} bpm</strong></span><small>Context only; targets are not scaled by watch readings.</small></div>`:''}<section class="panel feature-panel"><div class="table-heading"><div><h2>Set-by-set proposal</h2><p>Build reps to the ceiling, then increase eligible loads and reset reps. BW means bodyweight only; missing measurements remain blank.</p></div></div><div class="table-scroll"><table class="plan-table"><thead><tr><th>Exercise</th><th>Last session · ${date(plan.baselineDate)}</th><th>Proposed next session</th><th>Why this target?</th></tr></thead><tbody>${plan.exercises.map(e=>`<tr><td><button class="record-exercise" data-view-exercise="${escape(e.name)}">${exerciseLabel(e.name)}</button><span class="signal ${['progress','weight_progress'].includes(e.status)?'progressing':e.status==='review'?'watch':'insufficient'}">${names[e.status]}</span></td><td>${proposedSets(e.previous,e.name)}</td><td class="proposed-targets">${proposedSets(e.proposed,e.name)}</td><td><p>${escape(e.reason)}</p><details class="plan-evidence"><summary>Recent ${escape(plan.name)} records</summary>${e.history.map(h=>`<div><button class="table-date" data-session="${escape(h.id)}">${date(h.date,true)}</button>${proposedSets(h.sets,e.name)}</div>`).join('')}</details></td></tr>`).join('')||'<tr><td colspan="4">No recorded exercise sets for this type yet. Name a completed workout Upper 1, Upper 2, Lower 1 or Lower 2 to establish its history.</td></tr>'}</tbody></table></div></section>${progressionSettings(plan)}${plan.omittedExercises.length?`<section class="panel plan-intro"><div><h2>Seen earlier, absent from your latest session</h2><p>${plan.omittedExercises.map(e=>escape(e.name)+' ('+date(e.lastDate,true)+')').join(' · ')}</p><p class="muted">These were not added automatically; the proposal follows your latest exercise list.</p></div></section>`:''}<details class="panel muscle-editor"><summary>How the proposal works</summary><p>Exercise order and set counts come from the latest named session. For each load group, all sets must reach the rep ceiling in two comparable sessions before its load increases by the equipment increment and its reps reset to the lower target. Top sets and back-off sets are checked separately. Until then, one set can gain one rep within the range. Default range: 8–12. Suggested increments: 2.5 kg at loads of 25+ kg, 1 kg at 10–25 kg, otherwise 0.5 kg; confirm or change these to match your equipment. An increase over 10%, falling reps, incomplete data, unclear bodyweight loads or a long break pauses progression.</p><p>These are editable-in-practice targets, not a prediction or a completed log. Choose achievable reps with consistent technique and adjust to how you feel. <a class="text-link" href="https://acsm.org/resistance-training-guidelines-update-2026/" target="_blank" rel="noreferrer">ACSM training background ↗</a></p></details>`;
}

function operationsPage() {
  return renderOperationHistory({operations:state.operations??null,loading:Boolean(state.operationsLoading),error:state.operationsError||''});
}
async function operationRequest(identity=null, resume=false) {
  const response=await fetch(resume?'/api/garmin-workouts':'/api/garmin-operations'+(identity?'?id='+encodeURIComponent(identity):''),{
    cache:'no-store',signal:AbortSignal.timeout(resume?45000:10000),
    ...(resume?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation:'integration_resume',requestId:identity})}:{}),
  });
  const result=await response.json();
  if(!response.ok)throw new Error(result.error||'Operation status is unavailable.');
  return result;
}
async function loadOperationHistory() {
  const sequence=++operationSequence;
  state.operationsLoading=true;state.operationsError='';
  if(state.page==='operations')render();
  try {
    const result=await operationRequest();
    if(!Array.isArray(result.operations))throw new Error('Operation history is unavailable.');
    if(sequence===operationSequence)state.operations=result.operations;
  } catch(error) {
    if(sequence===operationSequence)state.operationsError=error.message||'Operation history is unavailable.';
  } finally {
    if(sequence===operationSequence){state.operationsLoading=false;if(state.page==='operations')render();}
  }
}
async function reviewOperation(identity) {
  const sequence=++operationReviewSequence;
  const operation=await operationRequest(identity);
  if(sequence!==operationReviewSequence)return;
  state.operationReview=operation;
  openEditor(recoveryReview(operation));
}
async function continueOperation(identity) {
  if(state.operationSaving||state.operationReview?.id!==identity)return;
  state.operationSaving=true;
  openEditor(recoveryReview(state.operationReview,{busy:true}));
  try {
    const result=await operationRequest(identity,true);
    state.operationReview=result;
    openEditor(recoveryReview(result));
    await loadOperationHistory();
    if(result.status==='done'){toast('Operation completed.');load(true,true);}
    else toast('Progress checked. Review the remaining steps.');
  } catch(error) {
    openEditor(recoveryReview(state.operationReview,{error:(error.message||'Progress could not be confirmed.')+' Refresh status before continuing again; the original confirmation is retained.'}));
  } finally {state.operationSaving=false;}
}
function garminPage() {
  const rows=state.garminWorkouts;
  return `<section class="page-heading"><div><div class="eyebrow">GARMIN CONNECT</div><h1>Garmin workouts<span class="heading-dot">.</span></h1><p>Edit your Garmin strength templates or fill next-session targets. <a class="text-link" href="#operations">View operation recovery →</a></p></div><button class="button button-dark" data-action="load-garmin">${rows?'Refresh workouts':'Load Garmin workouts'}</button></section><div class="notice">Full edit lets you change exercises, sets, order, rest, repeat blocks, title and notes. Every save has a review step.</div><section class="panel feature-panel"><div class="table-heading"><h2>Your Garmin workout library</h2></div>${rows?`<div class="table-scroll"><table><thead><tr><th>Garmin workout</th><th>Next-session plan</th><th>Update</th></tr></thead><tbody>${rows.map(w=>`<tr><td>${escape(w.name)}</td><td>${escape((state.data.nextSessions||[]).find(p=>p.type===w.planType)?.name||'Manual edits available')}</td><td><div class="garmin-library-actions"><button class="button button-dark" data-full-garmin="${w.id}">Full edit</button><button class="button" data-preview-garmin="${w.id}">Quick weights & reps</button></div></td></tr>`).join('')||'<tr><td colspan="3">No strength workout templates found in Garmin Connect.</td></tr>'}</tbody></table></div>`:'<p class="small-empty">Load your existing Garmin workouts to choose one to update.</p>'}</section>`;
}
async function garminRequest(body) {
  const response=await fetch('/api/garmin-workouts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok)throw new Error(result.error||'Garmin request failed');
  return result;
}
function groupGarminRows(rows) {
  const groups=new Map();
  for(const row of rows){
    const key=row.exercise.toLocaleLowerCase();
    if(!groups.has(key))groups.set(key,{exercise:row.exercise,rows:[],sets:0});
    const group=groups.get(key),start=group.sets+1;
    group.sets+=row.sets;
    group.rows.push({...row,setLabel:row.sets===1?`Set ${start}`:`Sets ${start}–${group.sets}`});
  }
  return [...groups.values()];
}
function groupGarminChanges(changes) {
  const groups=new Map();
  for(const change of changes){
    const key=change.exercise.toLocaleLowerCase();
    if(!groups.has(key))groups.set(key,{exercise:change.exercise,changes:[]});
    groups.get(key).changes.push(change);
  }
  return [...groups.values()];
}
function showGarminEditor(result) {
  state.garminPreview=result;
  const groups=groupGarminRows(result.editable);
  openEditor(`<form id="garmin-form" data-preview="${result.previewId}" class="garmin-editor"><div class="dialog-heading"><div><span class="eyebrow">EDIT GARMIN WORKOUT</span><h2 id="editor-title">${escape(result.name)}</h2><p>Exercises are grouped below. Change only the weight and reps for each set target.</p></div><button type="button" class="icon-button close-editor" aria-label="Close editor">${icon('close')}</button></div><div class="garmin-toolbar"><div><strong>${groups.length} exercises · ${groups.reduce((total,g)=>total+g.sets,0)} sets</strong><span>Garmin step numbers stay visible within each exercise.</span></div><button type="button" class="button" data-action="fill-garmin-targets">Fill next-session targets</button></div><div class="garmin-groups">${groups.map((group,i)=>`<section class="garmin-group" aria-labelledby="garmin-group-${i}"><div class="garmin-group-heading"><div><span class="garmin-group-number">${String(i+1).padStart(2,'0')}</span><div><h3 id="garmin-group-${i}">${exerciseLabel(group.exercise)}</h3><p>${group.sets} ${group.sets===1?'set':'sets'} · ${group.rows.length} ${group.rows.length===1?'target':'targets'}</p></div></div>${group.rows.some(r=>r.sets>1)?'<span class="garmin-shared-badge">Shared target</span>':''}</div><div class="garmin-set-list">${group.rows.map(r=>`<div class="garmin-set-row" data-garmin-row="${r.index}"><div class="garmin-set-identity"><strong>${r.setLabel}</strong><small>Garmin step ${number(r.stepOrder)}${r.sets>1?' · edits all '+r.sets+' sets':''}</small></div><div class="garmin-current"><small>Loaded target</small><strong>${r.weightEditable?number(r.weight,2)+' kg':'Other unit'} × ${number(r.reps)} reps</strong></div><label>Weight <span>kg</span><input aria-label="${escape(group.exercise)} ${r.setLabel} weight" data-garmin-weight type="number" min="0" max="2000" step="any" value="${r.weight??''}" ${r.weightEditable?'':'disabled'}></label><label>Reps<input aria-label="${escape(group.exercise)} ${r.setLabel} reps" data-garmin-reps type="number" min="1" max="500" step="1" value="${r.reps??''}"></label></div>`).join('')}</div></section>`).join('')||'<p class="garmin-empty">No editable rep-based steps were found in this workout.</p>'}</div><div id="garmin-fill-notes" class="garmin-skipped" role="status"></div><div class="form-error" role="alert"></div><div class="dialog-footer"><span>A shared target edits every set shown in its range. Filling suggestions can separate them.</span><button type="submit" class="button button-dark" ${result.editable.length?'':'disabled'}>Review changes</button></div></form>`);
}

function showGarminPreview(result) {
  const groups=groupGarminChanges(result.changes);
  openEditor(`<div class="garmin-editor"><div class="dialog-heading"><div><span class="eyebrow">GARMIN UPDATE PREVIEW</span><h2 id="editor-title">${escape(result.name)}</h2><p>Changes are grouped by exercise. Check each target before updating Garmin.</p></div><button class="icon-button close-editor" aria-label="Close preview">${icon('close')}</button></div><div class="garmin-groups">${groups.map((group,i)=>`<section class="garmin-group" aria-labelledby="garmin-preview-group-${i}"><div class="garmin-group-heading"><div><span class="garmin-group-number">${String(i+1).padStart(2,'0')}</span><div><h3 id="garmin-preview-group-${i}">${exerciseLabel(group.exercise)}</h3><p>${group.changes.length} ${group.changes.length===1?'change':'changes'}</p></div></div></div><div class="garmin-preview-list">${group.changes.map(c=>`<div class="garmin-preview-row"><span>Step ${number(c.stepOrder)} · ${c.sets} ${c.sets===1?'set':'sets'}</span><strong>${c.field==='weight'?'Weight':'Reps'}</strong><span>${number(c.before,2)} ${c.field==='weight'?'kg':'reps'}</span><span class="garmin-preview-arrow" aria-hidden="true">→</span><strong class="garmin-preview-value">${number(c.after,2)} ${c.field==='weight'?'kg':'reps'}</strong></div>`).join('')}</div></section>`).join('')||`<p class="garmin-empty">${result.structureChanged?'Target values stay the same; repeat blocks will be regrouped as described below.':'No applicable changes. Targets may already match or need review below.'}</p>`}</div>${result.skipped.length?`<div class="garmin-skipped"><h3>Workout notes</h3><ul>${result.skipped.map(s=>`<li><strong>${exerciseLabel(s.exercise)}${s.field?' · '+escape(s.field):''}:</strong> ${escape(s.reason)}</li>`).join('')}</ul></div>`:''}<div class="form-error" role="alert"></div><div class="dialog-footer"><span>Exercise order and rest steps are preserved.</span><button class="button button-dark" data-apply-garmin="${result.previewId}" ${result.changes.length||result.structureChanged?'':'disabled'}>Update Garmin workout</button></div></div>`);
}

function fullList(path) {
  const parts=path.split('/').filter(Boolean).map(Number);
  let items=state.garminFull.segments[parts.shift()].workoutSteps;
  for(const index of parts)items=items[index].workoutSteps;
  return items;
}
function fullItem(path) {
  const parts=path.split('/');const index=Number(parts.pop());
  return {items:fullList(parts.join('/')+'/'),index};
}
function fullExerciseCodes() {
  if(state.garminFullCatalog)return state.garminFullCatalog;
  const found=new Map();
  const walk=items=>{for(const item of items){if(item.workoutSteps)walk(item.workoutSteps);else if(item.exerciseName&&item.category)found.set(item.exerciseName,item.category);}};
  for(const segment of state.garminFull.segments)walk(segment.workoutSteps);
  return found;
}
function fullTemplate(kind) {
  const walk=items=>{for(const item of items){if((item.stepType||{}).stepTypeKey===kind)return structuredClone(item);if(item.workoutSteps){const found=walk(item.workoutSteps);if(found)return found;}}};
  for(const segment of state.garminFull.segments){const found=walk(segment.workoutSteps);if(found)return found;}
  if(kind==='repeat')return {type:'RepeatGroupDTO',stepType:{stepTypeId:6,stepTypeKey:'repeat',displayOrder:6},endCondition:{conditionTypeId:7,conditionTypeKey:'iterations',displayOrder:7,displayable:false},numberOfIterations:2,endConditionValue:2,skipLastRestStep:false,smartRepeat:false,workoutSteps:[]};
  if(kind==='rest')return {type:'ExecutableStepDTO',stepType:{stepTypeId:5,stepTypeKey:'rest',displayOrder:5},endCondition:{conditionTypeId:2,conditionTypeKey:'time',displayOrder:2},endConditionValue:90};
  throw new Error('Add an exercise by duplicating an existing exercise step.');
}
function freshStep(item) {
  const copy=structuredClone(item);delete copy.stepId;copy.childStepId=null;
  if(copy.workoutSteps)copy.workoutSteps=copy.workoutSteps.map(freshStep);
  return copy;
}
function validateFullStructure(segments) {
  if(!Array.isArray(segments)||!segments.length||segments.length>20)throw new Error('A workout needs 1–20 segments.');
  let total=0;
  const walk=(items,depth=0)=>{
    if(!Array.isArray(items)||items.length>500||depth>5)throw new Error('Invalid or oversized workout structure.');
    for(const item of items){
      if(!item||typeof item!=='object'||Array.isArray(item)||++total>2000)throw new Error('Invalid or oversized workout steps.');
      if('workoutSteps' in item){
        if(!Number.isInteger(item.numberOfIterations)||item.numberOfIterations<2||item.numberOfIterations>100)throw new Error('Repeat blocks need 2–100 iterations.');
        walk(item.workoutSteps,depth+1);
      }
    }
  };
  for(const segment of segments){if(!segment||typeof segment!=='object')throw new Error('Invalid segment.');walk(segment.workoutSteps);}
}
function splitRepeat(group,budget={remaining:5000}) {
  const out=[];
  const expand=item=>{if(item.workoutSteps)return splitRepeat(item,budget);if(--budget.remaining<0)throw new Error('Splitting would exceed 5,000 steps. Keep the repeat block or reduce iterations.');return [freshStep(item)];};
  for(let i=0;i<group.numberOfIterations;i++){
    const children=i===group.numberOfIterations-1&&group.skipLastRestStep&&group.workoutSteps.at(-1)?.stepType?.stepTypeKey==='rest'?group.workoutSteps.slice(0,-1):group.workoutSteps;
    for(const child of children)out.push(...expand(child));
  }
  return out;
}
function fullStepHtml(step,path) {
  const kind=step.stepType?.stepTypeKey||'interval';
  const actions=`<div class="full-step-actions"><button type="button" class="button" data-full-action="up" data-full-path="${path}" aria-label="Move step up">↑</button><button type="button" class="button" data-full-action="down" data-full-path="${path}" aria-label="Move step down">↓</button><button type="button" class="button" data-full-action="copy" data-full-path="${path}">Duplicate</button><button type="button" class="button" data-full-action="delete" data-full-path="${path}">Remove</button></div>`;
  if(step.workoutSteps)return `<article class="full-step full-repeat"><div class="full-step-head"><strong>Repeat block</strong>${actions}<button type="button" class="button" data-full-action="split" data-full-path="${path}">Split into steps</button></div><div class="full-fields"><label>Iterations<input data-full-path="${path}" data-full-field="numberOfIterations" type="number" min="2" max="100" value="${escape(step.numberOfIterations)}"></label><label class="full-check"><input data-full-path="${path}" data-full-field="skipLastRestStep" type="checkbox" ${step.skipLastRestStep?'checked':''}> Skip last rest</label></div><div class="full-children">${step.workoutSteps.map((child,i)=>fullStepHtml(child,`${path}/${i}`)).join('')}</div>${fullAddButtons(`${path}/`)}</article>`;
  const condition=step.endCondition?.conditionTypeKey||'reps';
  const unit=({kilogram:'kg',pound:'lb'})[step.weightUnit?.unitKey]||step.weightUnit?.unitKey||'unit unspecified';
  return `<article class="full-step"><div class="full-step-head"><strong>${step.exerciseName?exerciseLabel(step.exerciseName.replaceAll('_',' ')):escape(kind)}</strong>${actions}</div><div class="full-fields"><label>Step type<select data-full-path="${path}" data-full-field="stepType">${['interval','warmup','cooldown','rest'].map(x=>`<option value="${x}" ${kind===x?'selected':''}>${x}</option>`).join('')}</select></label><label>Target type<select data-full-path="${path}" data-full-field="endCondition">${['reps','time','lap.button'].map(x=>`<option value="${x}" ${condition===x?'selected':''}>${x==='time'?'Seconds':x==='reps'?'Reps':'Lap button'}</option>`).join('')}</select></label><label>Target<input data-full-path="${path}" data-full-field="endConditionValue" type="number" min="1" step="1" value="${escape(step.endConditionValue??'')}" ${condition==='lap.button'?'disabled':''}></label>${kind==='rest'?'':`<label>Garmin category<input data-full-path="${path}" data-full-field="category" value="${escape(step.category||'')}"></label><label>Garmin exercise code<input list="full-garmin-exercises" data-full-path="${path}" data-full-field="exerciseName" value="${escape(step.exerciseName||'')}"></label><label>Weight (${escape(unit)})<input data-full-path="${path}" data-full-field="weightValue" type="number" min="0" max="2000" step="any" value="${escape(step.weightValue??'')}"></label>`}<label class="full-note">Step note<input data-full-path="${path}" data-full-field="description" value="${escape(step.description||'')}"></label></div></article>`;
}
function fullAddButtons(path) {return `<div class="full-add"><button type="button" class="button" data-full-action="add-exercise" data-full-path="${path}">+ Exercise</button><button type="button" class="button" data-full-action="add-rest" data-full-path="${path}">+ Rest</button><button type="button" class="button" data-full-action="add-repeat" data-full-path="${path}">+ Repeat</button></div>`;}
function showFullEditor() {
  const draft=state.garminFull;
  openEditor(`<form id="garmin-full-form" class="garmin-editor"><div class="dialog-heading"><div><span class="eyebrow">FULL GARMIN EDITOR</span><h2 id="editor-title">${escape(draft.name)}</h2><p>Edit the complete strength workout, then review every change before updating Garmin.</p></div><button type="button" class="icon-button close-editor" aria-label="Close editor">${icon('close')}</button></div><datalist id="full-garmin-exercises">${[...fullExerciseCodes()].map(([code])=>`<option value="${escape(code)}">`).join('')}</datalist><div class="full-meta"><label>Workout name<input data-full-root="name" required maxlength="120" value="${escape(draft.name)}"></label><label>Description<textarea data-full-root="description" maxlength="1000">${escape(draft.description||'')}</textarea></label></div><div class="garmin-groups">${draft.segments.map((segment,i)=>`<section class="garmin-group"><div class="garmin-group-heading"><div><span class="garmin-group-number">${i+1}</span><h3>Segment ${i+1}</h3></div><button type="button" class="button" data-full-action="remove-segment" data-full-path="${i}" ${draft.segments.length===1?'disabled':''}>Remove segment</button></div><div class="full-children">${segment.workoutSteps.map((step,j)=>fullStepHtml(step,`${i}/${j}`)).join('')}</div>${fullAddButtons(`${i}/`)}</section>`).join('')}<button type="button" class="button" data-full-action="add-segment">+ Segment</button></div><details class="full-advanced"><summary>Advanced workout structure (JSON)</summary><p>Edit Garmin fields that are not shown above. Load the JSON to update the visual editor before reviewing.</p><textarea id="full-json" spellcheck="false">${escape(JSON.stringify(draft.segments,null,2))}</textarea><button type="button" class="button" data-full-action="load-json">Load JSON into editor</button></details><div class="form-error" role="alert"></div><div class="dialog-footer"><span>Changes are saved only after review.</span><button type="submit" class="button button-dark">Review full workout</button></div></form>`);
}
function showFullPreview(result) {
  openEditor(`<div class="garmin-editor"><div class="dialog-heading"><div><span class="eyebrow">GARMIN WORKOUT PREVIEW</span><h2 id="editor-title">${escape(result.name)}</h2><p>Review the full workout before saving it to Garmin.</p></div><button class="icon-button close-editor" aria-label="Close preview">${icon('close')}</button></div><div class="garmin-groups">${result.changes.map(c=>`<section class="garmin-group"><div class="garmin-group-heading"><h3>${escape(c.label)}</h3></div><div class="full-preview-change"><span>${escape(c.before??'Empty')}</span><span aria-hidden="true">→</span><strong>${escape(c.after??'Empty')}</strong></div></section>`).join('')||'<p>No changes to save.</p>'}<details class="full-advanced"><summary>Review exact workout structure</summary><div class="full-diff"><div><h3>Before</h3><pre>${escape(JSON.stringify(result.before.segments,null,2))}</pre></div><div><h3>After</h3><pre>${escape(JSON.stringify(result.after.segments,null,2))}</pre></div></div></details></div><div class="form-error" role="alert"></div><div class="dialog-footer"><button class="button" data-full-action="back">Back to editor</button><button class="button button-dark" data-apply-garmin="${result.previewId}" ${result.changes.length?'':'disabled'}>Update Garmin workout</button></div></div>`);
}

function equipmentRow(id,profile={name:'',loads:[]}) {
  return `<div class="equipment-row" data-equipment-id="${escape(id)}"><label>Profile name<input data-equipment-name required maxlength="120" placeholder="e.g. Gym dumbbells" value="${escape(profile.name)}"></label><label>Available loads (kg)<input data-equipment-loads required placeholder="e.g. 10, 12, 14, 16, 18, 20" value="${escape(profile.loads.join(', '))}"></label><button class="button" type="button" data-remove-equipment>Remove</button></div>`;
}
function equipmentPanel() {
  const equipment=state.data.equipment||{profiles:{},assignments:{}};
  const names=[...new Set([...state.data.sets.map(s=>s.exercise),...Object.keys(equipment.assignments)])].sort();
  return `<section class="panel equipment-panel"><div class="table-heading"><div><h2>Equipment profiles</h2><p>Make next-session targets match the weights available at your gym.</p></div></div><form id="equipment-form" data-revision="${escape(state.data.metadataRevision)}"><p class="equipment-help">List every available load, separated by commas. Use the same kg convention as your recorded sets: total barbell weight including the bar, or per-dumbbell weight if that is how you log it. No automatic per-hand conversion is applied. Assigned profiles take priority over fixed weight increments.</p><div id="equipment-rows">${Object.entries(equipment.profiles).map(([id,p])=>equipmentRow(id,p)).join('')}</div><button type="button" class="button" data-action="add-equipment">+ Add equipment profile</button><h3>Assign equipment to exercises</h3><div class="equipment-assignments">${names.map(name=>`<label>${exerciseLabel(name)}<select data-equipment-exercise="${escape(name)}"><option value="">Use existing increment</option>${Object.entries(equipment.profiles).map(([id,p])=>`<option value="${escape(id)}" ${equipment.assignments[name]===id?'selected':''}>${escape(p.name)}</option>`).join('')}</select></label>`).join('')||'<p>Exercises appear here after you log your first workout.</p>'}</div><div class="form-error" role="alert"></div><button type="submit" class="button button-dark">Save equipment profiles</button></form></section>`;
}

function exerciseVolumePreferences() {
  return `<section class="panel feature-panel exercise-volume-controls" aria-label="Exercise volume calculation"><div class="table-heading"><div><h2>Exercise volume</h2><p>Choose how volume is shown in the exercise library and charts.</p></div></div><div class="segmented" role="group" aria-label="Volume calculation">${[['recorded','Recorded load × reps'],['adjusted','Adjusted volume']].map(([mode,label])=>`<button data-exercise-volume="${mode}" class="${state.exerciseVolumeMode===mode?'active':''}" aria-pressed="${state.exerciseVolumeMode===mode}">${label}</button>`).join('')}</div><p>${exerciseVolumeExplanation(state.exerciseVolumeMode==='recorded')} Applies only to Exercises and is remembered in this browser.</p></section>`;
}
function preferencesPage() {
  const active=document.documentElement.dataset.theme;
  return `<section class="page-heading"><div><div class="eyebrow">MAKE IT YOURS</div><h1>Preferences<span class="heading-dot">.</span></h1><p>Customize your appearance, exercise volume factors, and equipment for training targets.</p></div></section><section class="panel appearance-panel"><div class="table-heading"><div><h2>Color theme</h2><p>Changes apply immediately and are remembered in this browser.</p></div></div><div class="theme-grid" role="group" aria-label="Color theme">${window.FormTheme.themes.map(t=>`<button class="theme-card ${t.id===active?'selected':''}" data-theme-choice="${t.id}" data-multicolor="${Boolean(t.palette)}" aria-pressed="${t.id===active}"><span class="theme-preview" style="--preview-hue:${t.hue};--preview-chroma:${t.chroma};${t.palette?Object.entries(t.palette).map(([role,color])=>`--preview-${role}:${color}`).join(';'):''}" aria-hidden="true"><span class="preview-sidebar"><i></i><i></i><i></i></span><span class="preview-content"><span class="preview-title"></span><span class="preview-stats"><i></i><i></i><i></i></span><span class="preview-chart"><i></i><i></i><i></i><i></i><i></i><i></i></span></span></span><span class="theme-card-heading"><strong>${t.name}</strong><span class="theme-check">${t.id===active?icon('check'):''}</span></span><span class="theme-description">${t.description}</span></button>`).join('')}</div><p class="appearance-note">Choose Daylight for a bright workspace, or one of the three dark palettes. Every theme keeps distinct metric colors. Your choice is saved in this browser.</p></section>`+overviewControls()+equipmentPanel()+exerciseVolumePreferences()+volumeSettingsEditor(adjustedVolumeSets(state.data.sets,state.data.recovery||[],state.data.volumeSettings||{}));
}

function nutritionPage() {
  const zone=state.data.timezone||'Europe/Kyiv';
  const dayOf=localDay;
  const selected={from:nutritionDay(),to:nutritionDay()};
  const entries=(state.data.foodLog||[]).filter(e=>(!selected.from||dayOf(e.time)>=selected.from)&&(!selected.to||dayOf(e.time)<=selected.to));
  const totals=entries.reduce((a,e)=>{for(const key of ['calories','protein_g','carbs_g','fat_g'])a[key]+=Number(e[key])||0;return a;},{calories:0,protein_g:0,carbs_g:0,fat_g:0});
  const grouped={};for(const e of (state.data.foodLog||[])){const day=dayOf(e.time);grouped[day]=(grouped[day]||0)+e.calories;}
  const days=Object.entries(grouped).sort(([a],[b])=>compareExerciseStack(a,b,state.data?.muscleOverrides||{}));const top=Math.max(1,...days.map(([,v])=>v));
  const daily=(state.data.recovery||[]).filter(r=>(!selected.from||r.date>=selected.from)&&(!selected.to||r.date<=selected.to));
  const burn=new Map(daily.map(r=>[r.date,r]));
  const comparisonDays=entries.length||daily.length?[selected.from]:[];
  const comparisonMax=Math.max(1,...comparisonDays.flatMap(day=>[grouped[day]||0,burn.get(day)?.totalCalories||0]));
  return header('Nutrition','Estimated food intake from your private Telegram bot. Send a food photo, optionally with your hand in frame, or a short description such as “3 bananas”.')+
    `<section class="nutrition-stats" aria-label="Nutrition totals for ${escape(nutritionDay())}">${[['calories','Calories','kcal'],['protein_g','Protein','g'],['carbs_g','Carbs','g'],['fat_g','Fat','g']].map(([key,label,unit])=>`<article class="panel" style="--metric-color:var(--metric-${key})"><span>${label}</span><strong>${entries.length?number(totals[key],1):'—'} <small>${unit}</small></strong></article>`).join('')}</section><p class="feature-note">${entries.length?'Totals include logged entries only; they may not cover the full day.':'No food entries for this day. Missing intake is not zero intake.'}</p>`+
    `<section class="panel nutrition-panel"><div class="table-heading"><div><h2>Daily calorie history</h2><p>Select a day to view its calories, macros and food log.</p></div></div>${days.length?`<div class="nutrition-bars" data-motion-chart="true" data-motion-key="nutrition-history" role="group" aria-label="Select a nutrition day">${days.map(([day,value])=>`<button type="button" class="nutrition-day ${day===nutritionDay()?'selected':''}" data-nutrition-day="${escape(day)}" aria-pressed="${day===nutritionDay()}" title="${escape(day)} · ${number(value)} kcal"><span>${number(value)}</span><i data-motion-bar="y" data-point-value="${value}" data-motion-label="${day}" style="height:${Math.max(3,value/top*100)}%"></i><small>${date(day)}</small></button>`).join('')}</div>`:'<p class="nutrition-empty">No food logged for this day. Send a photo to your Telegram bot or type /food 3 bananas.</p>'}</section>`+
    `<section class="panel nutrition-panel"><div class="table-heading"><div><h2>Food and Garmin calorie burn</h2><p>Food intake is an estimate from approved entries. Garmin total burn is active plus resting calories when both are recorded. Missing days stay blank.</p></div></div>${comparisonDays.length?`<div class="nutrition-compare-scroll"><div class="nutrition-compare" data-motion-chart="true" data-motion-key="nutrition-comparison" data-time-start="${nutritionDay()}" role="img" aria-label="Food intake and Garmin total calorie burn by day">${comparisonDays.map(day=>{const intake=grouped[day],total=burn.get(day)?.totalCalories;return `<div class="nutrition-compare-day" title="${escape(day)} · Food ${present(intake)?number(intake):'missing'} kcal · Garmin total burn ${present(total)?number(total):'missing'} kcal"><div class="nutrition-compare-bars"><i class="intake" data-motion-bar="y" data-point-value="${intake??''}" style="height:${present(intake)?Math.max(3,intake/comparisonMax*100):0}%"></i><i class="burn" data-motion-bar="y" data-point-value="${total??''}" style="height:${present(total)?Math.max(3,total/comparisonMax*100):0}%"></i></div><small>${date(day)}</small></div>`;}).join('')}</div></div><div class="nutrition-legend"><span><i class="intake"></i>Food intake</span><span><i class="burn"></i>Garmin total burn</span></div><div class="table-scroll"><table><thead><tr><th>Date</th><th>Food</th><th>Protein</th><th>Garmin active</th><th>Garmin resting</th><th>Garmin total</th><th>Body weight</th></tr></thead><tbody>${[...comparisonDays].reverse().map(day=>{const r=burn.get(day)||{},food=entries.filter(e=>dayOf(e.time)===day);return `<tr><td>${date(day,true)}</td><td>${present(grouped[day])?number(grouped[day])+' kcal':'—'}</td><td>${food.length?number(food.reduce((sum,e)=>sum+e.protein_g,0),1)+' g':'—'}</td><td>${present(r.activeCalories)?number(r.activeCalories)+' kcal':'—'}</td><td>${present(r.restingCalories)?number(r.restingCalories)+' kcal':'—'}</td><td>${present(r.totalCalories)?number(r.totalCalories)+' kcal':'—'}</td><td>${present(r.bodyWeightKg)?number(r.bodyWeightKg,1)+' kg':'—'}</td></tr>`;}).join('')}</tbody></table></div>`:'<p class="nutrition-empty">No food or Garmin calorie readings for this day.</p>'}</section>`+
    `<section class="panel nutrition-panel"><div class="table-heading"><div><h2>Food log · ${date(nutritionDay(),true)}</h2><p>Portions and nutrition are estimates; check labels or weighed amounts when precision matters.</p></div></div>${entries.length?`<div class="nutrition-list">${entries.map(e=>`<article><div><strong>${escape(e.name)}</strong><small>${escape(dayOf(e.time))} · ${new Date(e.time).toLocaleTimeString('en-GB',{timeZone:zone,hour:'2-digit',minute:'2-digit'})}${e.items?.length?' · '+escape(e.items.map(i=>i.name+' '+i.portion).join(', ')):''}</small>${e.note?`<small>${escape(e.note)}</small>`:''}</div><div class="nutrition-values"><strong>${number(e.calories)} kcal</strong><span>P ${number(e.protein_g,1)} · C ${number(e.carbs_g,1)} · F ${number(e.fat_g,1)} g</span>${state.foodDeleteId===e.id?`<span class="nutrition-delete-confirm">Delete this entry? <button type="button" data-action="food-delete-confirm" data-food-id="${escape(e.id)}">Yes, delete</button><button type="button" data-action="food-delete-cancel">Cancel</button></span>`:`<button type="button" class="nutrition-delete" data-action="food-delete" data-food-id="${escape(e.id)}" aria-label="Delete ${escape(e.name)}">Delete</button>`}</div></article>`).join('')}</div>`:'<p class="nutrition-empty">No entries to show.</p>'}</section>`;
}

function syncPage() {
  const sync=state.data.sync||{},zone=state.data.timezone||'Europe/Kyiv';
  const stamp=value=>value?new Date(value).toLocaleString('en-GB',{timeZone:zone,day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'No record';
  const age=value=>{
    if(!value)return 'Never recorded';
    const hours=Math.max(0,(Date.now()-new Date(value).getTime())/3600000);
    return hours<1?'Less than 1 hour ago':hours<48?`${Math.floor(hours)} hours ago`:`${Math.floor(hours/24)} days ago`;
  };
  const status={updated:'Data fetch completed',partial:'Some dates were skipped',no_new_data:'No new watch upload'}[sync.collectorResult]||'No collector check recorded';
  const sources=Object.entries(sync.sources||{}),daily=new Set(['Daily health','Sleep','Training status','Training readiness','Body Battery']);
  return `<section class="page-heading"><div><div class="eyebrow">FROM YOUR GARMIN</div><h1>Garmin sync<span class="heading-dot">.</span></h1><p>See when the watch uploaded, when the collector last checked, and the latest stored reading for each source.</p></div></section>`+
    `<section class="sync-cards"><article class="panel"><span>Watch upload</span><strong>${escape(stamp(sync.watchUploadAt))}</strong><small>${escape(age(sync.watchUploadAt))}${sync.deviceName?' · '+escape(sync.deviceName):''}</small></article><article class="panel"><span>Collector check</span><strong>${escape(stamp(sync.collectorPollAt))}</strong><small>${escape(status)} · ${escape(age(sync.collectorPollAt))}</small></article><article class="panel"><span>Dashboard refresh</span><strong>${escape(stamp(state.data.refreshedAt))}</strong><small>This page read the local database, not Garmin directly.</small></article></section>`+
    `<section class="panel sync-panel"><div class="table-heading"><div><h2>Latest data by source</h2><p>These are measurement times. Strength workouts and weigh-ins only change when you record them.</p></div></div><div class="table-scroll"><table><thead><tr><th>Source</th><th>Latest reading</th><th>Age</th><th>Signal</th></tr></thead><tbody>${sources.map(([name,value])=>{const hours=value?(Date.now()-new Date(value).getTime())/3600000:null;const stale=daily.has(name)&&hours!==null&&hours>48;return `<tr><td>${escape(name)}</td><td>${escape(stamp(value))}</td><td>${escape(age(value))}</td><td><span class="sync-signal ${!value?'missing':stale?'stale':'recorded'}">${!value?'No data':stale?'Older than 2 days':'Recorded'}</span></td></tr>`;}).join('')||'<tr><td colspan="4">No Garmin source data is available.</td></tr>'}</tbody></table></div><p class="feature-note">A recent collector check does not prove every Garmin metric was available. A delayed watch upload can leave otherwise healthy collection without new samples. Daily readings may arrive after the day ends.</p></section>`;
}

const settingsDrafts=new Map();
const settingsFormSelector='#equipment-form,#volume-form,#muscle-form,#progression-form';
function markSettingsDirty(target) {
  const form=target.closest(settingsFormSelector);
  if(!form)return;
  form.dataset.dirty='true';
  if(!form.querySelector('.settings-draft-notice'))form.insertAdjacentHTML('afterbegin','<p class="settings-draft-notice feature-note" role="status">Unsaved changes are kept while you navigate this tab. <button type="button" class="text-link" data-reset-settings>Discard changes and reload settings</button></p>');
}
function restoreRenderFocus(focused) {
  if(!focused||focused===document.body)return;
  if(focused.isConnected){focused.focus({preventScroll:true});return;}
  // Rendering replaces controls. Match their stable identity, not their position
  // or changing text, so keyboard users can continue from the same control.
  const identity=[...focused.attributes].filter(a=>a.name==='id'||a.name==='href'||a.name.startsWith('data-'));
  if(!identity.length)return;
  const replacement=[...document.querySelectorAll(focused.tagName)].find(node=>identity.every(a=>node.getAttribute(a.name)===a.value));
  if(replacement&&!replacement.disabled)replacement.focus({preventScroll:true});
}
function render() {
  const focused=document.activeElement;
  nav();
  document.title=`${pages[state.page]} · Garmin RepTrace`;
  if(state.data){
  $('#footer-source').textContent = `${state.data.workouts.length} workouts · ${state.data.sets.length.toLocaleString()} sets · ${state.data.timezone}`;
  const time = new Date(state.data.refreshedAt).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
  $('#sync-status').textContent = state.refreshError ? (state.refreshBusy?'Update in progress':'Refresh unavailable') : `Refreshed ${time}`;
  }
  if(state.page==='operations'){
    $('#main').innerHTML=operationsPage();
    restoreRenderFocus(focused);
    return;
  }
  if(!state.data){$('#main').innerHTML=state.refreshError?unavailableDashboard():loadingSkeleton();return;}
  const view = current();
  const templates = {overview,nutrition:nutritionPage,sync:syncPage,next:nextSessionPage,exercises:exercisesPage,workouts:workoutsPage,records:recordsPage,recovery:recoveryPage,insights:insightsPage,volume:volumePage,compare:comparePage,logging:loggingPage,goals:goalsPage,garmin:garminPage,preferences:preferencesPage};
  const warning=state.refreshError?`<div class="refresh-notice" role="status"><div><strong>Showing previously loaded history</strong><span>${state.refreshBusy?'Training records are being updated. Try again shortly for a complete snapshot.':'The latest refresh failed. Your saved data is still available below.'}</span></div><button class="button" data-action="retry">Try again</button></div>`:'';
  for(const form of document.querySelectorAll(settingsFormSelector))if(form.dataset.dirty)settingsDrafts.set(form.id,form);
  $('#main').innerHTML = warning+templates[state.page](view);
  for(const [id,form] of settingsDrafts){const replacement=document.getElementById(id);if(replacement){replacement.replaceWith(form);const disclosure=form.closest('details');if(disclosure)disclosure.open=true;}}
  restoreRenderFocus(focused);
  bindChart();
}
let chartClickUntil=0;
function zoomToDates(dates) {
  if(!dates)return;
  state.zoomHistory??=[];
  state.zoomHistory.push({range:state.range,from:state.from,to:state.to});
  state.range='custom';state.from=dates.from;state.to=dates.to>today()?today():dates.to;
  state.limit=24;state.volumeWeek='';render();
  toast(`Showing ${date(state.from,true)} – ${date(state.to,true)}. Use Undo zoom to return.`);
}
function bindTimeSelection(root=document) {
  for(const svg of root.querySelectorAll('svg[data-time-start]')){
    const start=Number(svg.dataset.timeStart),end=Number(svg.dataset.timeEnd);
    if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)continue;
    const left=Number(svg.dataset.plotLeft),right=Number(svg.dataset.plotRight),top=Number(svg.dataset.plotTop),bottom=Number(svg.dataset.plotBottom);
    svg.classList.add('time-selectable');svg.setAttribute('tabindex','0');
    const hint=document.createElement('div');hint.className='chart-zoom-hint';
    hint.textContent='Drag across the graph to select dates · Esc cancels · Date inputs also available above';
    svg.parentElement.append(hint);
    let drag=null,overlay=null;
    const position=event=>{
      const matrix=svg.getScreenCTM();if(!matrix)return null;
      const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
      return point.matrixTransform(matrix.inverse());
    };
    const clear=()=>{
      if(drag&&svg.hasPointerCapture(drag.id))svg.releasePointerCapture(drag.id);
      overlay?.remove();overlay=null;drag=null;svg.classList.remove('selecting-time');
      hint.textContent='Drag across the graph to select dates · Esc cancels · Date inputs also available above';
    };
    svg.addEventListener('pointerdown',event=>{
      if(!event.isPrimary||event.button!==0)return;
      const point=position(event);
      if(!point||point.x<left||point.x>right||point.y<top||point.y>bottom)return;
      drag={id:event.pointerId,x:point.x,clientX:event.clientX,clientY:event.clientY,active:false};
    });
    svg.addEventListener('pointermove',event=>{
      if(!drag||event.pointerId!==drag.id)return;
      const point=position(event);if(!point)return;
      if(!drag.active){
        const dx=Math.abs(event.clientX-drag.clientX),dy=Math.abs(event.clientY-drag.clientY);
        if(dx<6||dx<dy)return;
        drag.active=true;svg.setPointerCapture(event.pointerId);svg.focus({preventScroll:true});
        svg.classList.add('selecting-time');
        overlay=document.createElementNS('http://www.w3.org/2000/svg','rect');
        overlay.setAttribute('class','time-selection');overlay.setAttribute('y',top);overlay.setAttribute('height',bottom-top);svg.append(overlay);
      }
      const x=Math.max(left,Math.min(right,point.x));
      overlay.setAttribute('x',Math.min(drag.x,x));overlay.setAttribute('width',Math.abs(x-drag.x));
      const dates=chartDateRange(start,end,left,right,drag.x,x,svg.dataset.workoutDates?JSON.parse(svg.dataset.workoutDates):null);
      hint.textContent=`${date(dates.from,true)} – ${date(dates.to,true)} · Release to zoom`;
      event.preventDefault();
    });
    svg.addEventListener('pointerup',event=>{
      if(!drag||event.pointerId!==drag.id)return;
      const point=position(event);
      const dates=drag.active&&point?chartDateRange(start,end,left,right,drag.x,point.x,svg.dataset.workoutDates?JSON.parse(svg.dataset.workoutDates):null):null;
      if(drag.active)chartClickUntil=Date.now()+350;
      clear();if(dates)zoomToDates(dates);
    });
    svg.addEventListener('pointercancel',clear);
    svg.addEventListener('pointerleave',()=>{if(drag&&!drag.active)clear();});
    svg.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();clear();}});
  }
}

function bindChart(root=document) {
  bindTimeSelection(root);
  for(const container of root.querySelectorAll('.chart-wrap')) {
    for(const missing of container.querySelectorAll('.workout-missing'))missing.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();openWorkout(missing.dataset.session);}
    });
    const tooltip=container.querySelector('.chart-tooltip');
    if(!tooltip)continue;
    for(const point of container.querySelectorAll('[data-point-label]')) {
      const show=()=>{
        const previous=point.dataset.pointPrevious;
        const delta=previous!==undefined&&previous!==''?Number(point.dataset.pointValue)-Number(previous):null;
        const change=delta===null?'First recorded reading':`${delta>0?'+':''}${number(delta,2)} ${point.dataset.pointUnit||''} vs previous reading`;
        tooltip.textContent=point.dataset.pointLabel+(point.dataset.pointNoComparison?'':'\n'+change)+(point.dataset.session?'\nSelect to open workout':'');
        tooltip.classList.add('visible');
        const box=point.getBoundingClientRect(),parent=container.getBoundingClientRect();
        const half=tooltip.offsetWidth/2;
        tooltip.style.left=`${Math.max(half,Math.min(parent.width-half,box.left-parent.left+box.width/2))}px`;
        tooltip.style.top=`${Math.max(0,box.top-parent.top-tooltip.offsetHeight-12)}px`;
        tooltip.classList.add('visible');
      };
      point.addEventListener('mouseenter',show);point.addEventListener('focus',show);
      point.addEventListener('pointerdown',show);
      point.addEventListener('keydown',event=>{
        if(event.key==='Escape'){tooltip.classList.remove('visible');return;}
        if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
        event.preventDefault();
        const points=[...container.querySelectorAll('[data-point-label]')];
        const next=points[points.indexOf(point)+(event.key==='ArrowRight'?1:-1)];
        if(next){if(point.classList.contains('daily-point')){point.tabIndex=-1;next.tabIndex=0;}next.focus();}
      });
      point.addEventListener('mouseleave',()=>tooltip.classList.remove('visible'));
      point.addEventListener('blur',()=>tooltip.classList.remove('visible'));
      if(point.dataset.session)point.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openWorkout(point.dataset.session);}});
    }
  }
}
function workoutRecovery(day) {
  const row=(state.data.recovery||[]).find(r=>r.date===day);
  if(!row)return '';
  return `<div class="workout-recovery"><div class="eyebrow">DAILY CONTEXT · ${escape(date(day,true))}</div><div>${recoveryMetrics.filter(m=>['sleepHours','hrv','restingHR','bodyWeightKg'].includes(m.key)).map(m=>`<span><small>${m.label}</small><strong>${present(row[m.key])?(m.format?m.format(row[m.key]):number(row[m.key],m.key==='bodyWeightKg'?1:0)):'—'} ${present(row[m.key])&&m.unit?`<small>${m.unit}</small>`:''}</strong></span>`).join('')}</div></div>`;
}
function openWorkout(id) {
  const workout = state.data.workouts.find(w=>w.id===id);
  if (!workout) { toast('This workout has no stored summary.'); return; }
  const sets = state.data.sets.filter(s=>s.sessionId===id);
  const groups = new Map();
  for (const set of sets) {if(!groups.has(set.exercise)) groups.set(set.exercise,[]);groups.get(set.exercise).push(set);}
  $('#dialog-content').innerHTML = `<div class="dialog-heading"><div><span class="eyebrow">WORKOUT DETAILS</span><h2 id="dialog-title">${escape(workout.name)}</h2><p>${date(workout.date,true)} ${workout.dateOnly?'· Date recorded; time not recorded':''}</p></div><button class="icon-button close-dialog" aria-label="Close workout details">${icon('close')}</button></div><div class="dialog-stats"><div><small>Exercises</small><strong>${groups.size}</strong></div><div><small>Sets</small><strong>${sets.length}</strong></div><div><small>Recorded duration</small><strong>${duration(workout.duration)}</strong></div><div><small>Average heart rate</small><strong>${present(workout.averageHR)?number(workout.averageHR)+' <small>bpm</small>':'—'}</strong></div></div>${workoutRecovery(workout.date)}<div class="dialog-exercises">${[...groups].map(([name,entries])=>`<section><div class="dialog-exercise-title"><h3>${exerciseLabel(name)}</h3><button class="text-link" data-view-exercise="${escape(name)}">View progress ${icon('arrow')}</button></div><div class="table-scroll"><table><thead><tr><th>Set</th><th>Load</th><th>Reps</th><th>Rest after</th><th>Source</th></tr></thead><tbody>${entries.sort((a,b)=>(a.number||0)-(b.number||0)).map(s=>`<tr><td>${number(s.number)}</td><td>${loadLabel(s.exercise,s.weight)}</td><td>${number(s.reps)}</td><td>${duration(s.rest)}</td><td>${badge(s.source)}</td></tr>${s.note?`<tr class="note-row"><td colspan="5">${escape(s.note)}</td></tr>`:''}`).join('')}</tbody></table></div></section>`).join('')||'<p>No exercise sets recorded for this workout.</p>'}</div><div class="dialog-footer"><span>Missing measurements are shown as —.</span><button class="button button-dark" data-export-session="${escape(id)}">${icon('download')} Excel</button><button class="button" data-edit-workout="${escape(id)}">Edit sets</button>${workout.url?`<a class="button button-dark" href="${escape(workout.url)}" target="_blank" rel="noreferrer">Open in Garmin ${icon('arrow')}</a>`:''}</div>`;
  if (!$('#workout-dialog').open) $('#workout-dialog').showModal();
}
async function downloadExcel(sessionId=null,full=false) {
  const params=new URLSearchParams();
  if(full)params.set('full','1');
  else if(sessionId)params.set('session',sessionId);
  else {
    const selected=range();if(selected.from)params.set('from',selected.from);if(selected.to)params.set('to',selected.to);
    params.set('source',state.source);
    if(state.page==='workouts'&&state.workoutSearch)params.set('search',state.workoutSearch);
  }
  toast('Preparing your Excel workbook…');
  try {
    const response=await fetch('/api/sessions.xlsx?'+params);
    if(!response.ok)throw new Error(response.status===400?await response.text():'Excel export is temporarily unavailable.');
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'reptrace-sessions.xlsx';
    document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast(full?'Full Excel export downloaded, including every set and source records.':'Excel workbook downloaded: Sessions, Sets and Body weight.');
  } catch(error){toast(error.message||'Could not export sessions.');}
}
function toast(message) {
  clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.add('visible');
  toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);
}
function loadingSkeleton() {
  return `<section class="loading-dashboard" aria-busy="true" aria-label="Loading training history"><p role="status">Bringing your training history together…</p><div class="skeleton-heading skeleton" aria-hidden="true"></div><div class="skeleton-cards" aria-hidden="true">${'<div class="skeleton"></div>'.repeat(4)}</div><div class="skeleton-chart skeleton" aria-hidden="true"></div><p class="muted">Reading your recorded workouts and daily health data.</p></section>`;
}
function unavailableDashboard() {
  return `<section class="error-state"><span>${icon('activity')}</span><h1>${state.refreshBusy?'Training update in progress.':'Let’s reconnect your history.'}</h1><p>${state.refreshBusy?'Records are being updated. Try again shortly for a complete snapshot.':'Your training database is temporarily unavailable.'}</p><button class="button button-dark" data-action="retry">${icon('refresh')} Try again</button><p><a class="text-link" href="#operations">View operation recovery</a></p></section>`;
}
async function load(silent = false, force = false) {
  const sequence=++loadSequence;
  if(!state.data&&state.page!=='operations')$('#main').innerHTML=loadingSkeleton();
  $('#refresh').classList.add('spinning');
  $('#refresh').disabled=true;
  $('#sync-status').textContent='Refreshing…';
  try {
    const response=await fetch('/api/data'+(silent&&!force?'':'?refresh=1'),{cache:'no-store',signal:AbortSignal.timeout(30000)});
    if(!response.ok){
      const error=new Error('Data unavailable');
      error.busy=response.status===503&&Boolean(response.headers?.get('Retry-After'));
      throw error;
    }
    const data=await response.json();
    if(sequence!==loadSequence)return;
    if(!Array.isArray(data.sets)||!Array.isArray(data.workouts))throw new Error('Invalid data');
    data.hiddenSets=data.sets.filter(s=>s.exercise.trim().toLowerCase()==='unknown');
    data.sets=data.sets.filter(s=>s.exercise.trim().toLowerCase()!=='unknown');
    state.data=data;state.refreshError=false;state.refreshBusy=false;document.body.classList.remove('offline');render();
    $('.connection').innerHTML='<span class="status-dot"></span> Connected to your history';
    if(!silent)toast('Your training history is up to date.');
  } catch(error) {
    if(sequence!==loadSequence)return;
    state.refreshBusy=Boolean(error.busy);state.refreshError=true;
    if(state.data||state.page==='operations'){state.refreshError=true;render();}
    else $('#main').innerHTML=unavailableDashboard();
    $('#sync-status').textContent=state.refreshBusy?'Update in progress':'Connection unavailable';
    document.body.classList[state.refreshBusy?'remove':'add']('offline');
    $('.connection').innerHTML='<span class="status-dot"></span> '+(state.refreshBusy?'Training update in progress':'Connection unavailable');
  } finally {
    if(sequence===loadSequence){
      $('#refresh').classList.remove('spinning');
      $('#refresh').disabled=false;
    }
  }
}
function navigate(page) {
  if(!pages[page])page='overview';
  state.page=page;render();
  if(page==='operations')loadOperationHistory();
  window.scrollTo({top:0,behavior:'auto'});
}
document.addEventListener('click',event=>{
  if(event.target.closest('.skip-link')){event.preventDefault();$('#main').focus();$('#main').scrollIntoView({block:'start'});return;}
  const reset=event.target.closest('[data-reset-settings]');
  if(reset){const form=reset.closest('form');delete form.dataset.dirty;settingsDrafts.delete(form.id);load(true,true);}
});
document.addEventListener('input',event=>markSettingsDirty(event.target));
document.addEventListener('change',event=>markSettingsDirty(event.target));
document.addEventListener('click',event=>{
  if(Date.now()<chartClickUntil){event.preventDefault();event.stopImmediatePropagation();}
},true);
document.addEventListener('click',event=>{
  const more=$('#more-navigation');
  if(more?.open&&(!event.target.closest('#more-navigation')||event.target.closest('#more-navigation a')))more.open=false;
  const mapMuscle=event.target.closest('[data-map-muscle]');
  if(mapMuscle){state.mapMuscle=mapMuscle.dataset.mapMuscle;updateMuscleMap(mapMuscle.id);return;}
  const mapWeek=event.target.closest('[data-map-week]');
  if(mapWeek){state.mapWeek=mapWeek.dataset.mapWeek;updateMuscleMap(mapWeek.id);return;}
  if(event.target.closest('[data-map-more-weeks]')){state.mapWeekLimit+=8;updateMuscleMap('map-more-weeks');return;}
  const mapCompare=event.target.closest('[data-map-compare]');
  if(mapCompare){state.mapCompare=Number(mapCompare.dataset.mapCompare);updateMuscleMap(mapCompare.id);return;}
  const mapRoles=event.target.closest('[data-map-roles]');
  if(mapRoles){state.mapSecondary=mapRoles.dataset.mapRoles==='all';updateMuscleMap(mapRoles.id);return;}
  const close=event.target.closest('.close-dialog');
  if(close){$('#workout-dialog').close();return;}
  const excel=event.target.closest('[data-export-session]');
  if(excel){downloadExcel(excel.dataset.exportSession);return;}
  const session=event.target.closest('[data-session]');
  if(session){openWorkout(session.dataset.session);return;}
  const muscleFilter=event.target.closest('[data-exercise-muscle]');
  if(muscleFilter){
    selectExerciseMuscle(muscleFilter.dataset.exerciseMuscle);
    return;
  }
  const exercise=event.target.closest('[data-exercise]');
  if(exercise){
    state.selected=exercise.dataset.exercise;state.limit=24;
    // Keep the library and focused button mounted so its scroll position survives.
    const detail=$('.exercise-detail'),view=current();
    const {scrollX,scrollY}=window;
    for(const row of document.querySelectorAll('[data-exercise]')){
      const selected=row.dataset.exercise===state.selected;
      row.classList.toggle('selected',selected);row.setAttribute('aria-pressed',String(selected));
    }
    detail.innerHTML=progressPanel(view.selected)+setsTable(view.selected,state.page==='overview');
    bindChart(detail);
    window.scrollTo({left:scrollX,top:scrollY,behavior:'instant'});
    return;
  }
  const explore=event.target.closest('[data-view-exercise]');
  if(explore){state.selected=explore.dataset.viewExercise;state.search='';state.limit=24;$('#workout-dialog').close();location.hash='exercises';navigate('exercises');return;}
  const exerciseVolume=event.target.closest('[data-exercise-volume]');
  if(exerciseVolume){
    state.exerciseVolumeMode=exerciseVolume.dataset.exerciseVolume;
    try { localStorage.setItem('reptrace.exerciseVolumeMode',state.exerciseVolumeMode); } catch {}
    render();return;
  }
  const metric=event.target.closest('[data-metric]');
  if(metric){state.metric=metric.dataset.metric;render();return;}
  const nutritionDate=event.target.closest('[data-nutrition-day]');
  if(nutritionDate){state.nutritionDate=nutritionDate.dataset.nutritionDay;state.foodDeleteId='';render();return;}
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='nutrition-today'){state.nutritionDate='';state.foodDeleteId='';render();return;}
  if(action==='food-delete'){state.foodDeleteId=event.target.closest('[data-food-id]').dataset.foodId;render();return;}
  if(action==='food-delete-cancel'){state.foodDeleteId='';render();return;}
  if(action==='food-delete-confirm'){
    const identity=event.target.closest('[data-food-id]').dataset.foodId;
    if(identity===state.foodDeleteId)deleteFood(identity);
    return;
  }
  if(action==='retry')load();
  if(action==='more-sets'){state.limit+=24;render();}
  if(action==='more-recovery'){state.recoveryLimit+=14;render();}
  if(action==='all-sets'){state.limit=24;state.search='';}
  if(action==='export-all'){downloadExcel(null,true);return;}
  if(action==='export-excel'){downloadExcel();return;}
  if(action==='export'){
    const recovery=state.page==='recovery';
    const filtered=filterData(state.data,range(),state.source);
    const workoutIds=new Set(filtered.workouts.filter(w=>w.name.toLowerCase().includes(state.workoutSearch.toLowerCase())).map(w=>w.id));
    const rows=recovery?recoveryRows():filtered.sets.filter(s=>state.page!=='workouts'||workoutIds.has(s.sessionId));
    if(!rows.length){toast('No records to export in this range.');return;}
    const csv=recovery?csvForRecovery(rows):csvForSets(rows);
    const link=document.createElement('a');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    link.href=url;link.download=`garmin-reptrace-${recovery?'recovery':'training'}-${today()}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(`Exported ${rows.length} ${recovery?'days':'sets'} from your current filters.`);
  }
});
document.addEventListener('change',event=>{
  if(event.target.id==='nutrition-date'){
    if(event.target.value && event.target.validity.valid){state.nutritionDate=event.target.value;state.foodDeleteId='';render();}
    return;
  }
  if(event.target.id==='source-filter'){state.source=event.target.value;state.limit=24;render();}
  if(event.target.id==='record-sort'){state.recordSort=event.target.value;render();}

});
document.addEventListener('input',event=>{
  if(event.target.id==='exercise-search'){state.search=event.target.value;refreshExerciseLibrary();}
  if(event.target.id==='workout-search'){
    state.workoutSearch=event.target.value;
    const view=current();const rows=[...view.workouts].sort((a,b)=>b.date.localeCompare(a.date)||b.time.localeCompare(a.time)).filter(w=>w.name.toLowerCase().includes(state.workoutSearch.toLowerCase()));
    $('#workout-count').textContent=`${rows.length} matching workouts · ${view.workouts.length} in date range`;
    $('#workout-list').innerHTML=rows.map(w=>workoutCard(w,view.sets.filter(s=>s.sessionId===w.id))).join('')||'<div class="empty-panel">No matching workouts.</div>';
  }
});
$('#refresh').addEventListener('click',()=>load());
$('#workout-dialog').addEventListener('click',event=>{if(event.target===$('#workout-dialog'))$('#workout-dialog').close();});
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
document.addEventListener('click',async event=>{
  const operationRefresh=event.target.closest('[data-operation-refresh]');
  if(operationRefresh){await loadOperationHistory();return;}
  const operationReview=event.target.closest('[data-operation-review]');
  if(operationReview){
    operationReview.disabled=true;
    try{await reviewOperation(operationReview.dataset.operationReview);}catch(error){toast(error.message||'Operation unavailable.');}
    finally{operationReview.disabled=false;}
    return;
  }
  const operationResume=event.target.closest('[data-operation-resume]');
  if(operationResume){await continueOperation(operationResume.dataset.operationResume);return;}
  const week=event.target.closest('[data-volume-week]');
  if(week){state.volumeWeek=week.dataset.volumeWeek;render();document.querySelector(`[data-volume-week="${state.volumeWeek}"]`)?.focus();return;}
  const target=event.target.closest('button');if(!target)return;
  const errorToast=error=>toast(error.message||'Could not save');
  if(target.dataset.action==='load-garmin'||target.dataset.previewGarmin||target.dataset.fullGarmin||target.dataset.applyGarmin){
    target.disabled=true;
    try{
      if(target.dataset.action==='load-garmin'){
        target.textContent='Loading…';
        const result=await garminRequest({operation:'list'});state.garminWorkouts=result.workouts;render();
      }else if(target.dataset.previewGarmin){
        const result=await garminRequest({operation:'preview',workoutId:target.dataset.previewGarmin});state.garminUseSuggestions=false;showGarminEditor(result);
      }else if(target.dataset.fullGarmin){
        state.garminFull=await garminRequest({operation:'details',workoutId:target.dataset.fullGarmin});state.garminFullCatalog=null;state.garminFullCatalog=fullExerciseCodes();showFullEditor();
      }else{
        $('#editor-content .form-error').textContent='';
        await garminRequest({operation:'apply',previewId:target.dataset.applyGarmin});
        $('#editor-dialog').close();toast('Garmin workout updated and verified.');
      }
    }catch(error){
      if(target.dataset.applyGarmin){$('#editor-content .form-error').textContent=error.message;}
      else errorToast(error);
    }finally{target.disabled=false;if(target.dataset.action==='load-garmin')target.textContent='Refresh workouts';}
    return;
  }
  if(target.dataset.fullAction){
    try{
      const action=target.dataset.fullAction,path=target.dataset.fullPath||'';
      if(action==='back'){showFullEditor();return;}
      if(action==='load-json'){
        const parsed=JSON.parse($('#full-json').value);
        validateFullStructure(parsed);
        state.garminFull.segments=parsed;showFullEditor();return;
      }
      if(action==='add-segment'){
        const segment=structuredClone(state.garminFull.segments[0]);segment.workoutSteps=[];
        state.garminFull.segments.push(segment);
      }else if(action==='remove-segment'){
        if(state.garminFull.segments.length>1)state.garminFull.segments.splice(Number(path),1);
      }else if(action.startsWith('add-')){
        const kind=action==='add-exercise'?'interval':action==='add-rest'?'rest':'repeat';
        const step=freshStep(fullTemplate(kind));
        if(kind==='repeat'){step.workoutSteps=[freshStep(fullTemplate('interval'))];step.numberOfIterations=2;step.endConditionValue=2;step.skipLastRestStep=false;}
        if(kind==='rest'){step.endCondition={conditionTypeId:2,conditionTypeKey:'time',displayOrder:2};step.endConditionValue=90;}
        fullList(path).push(step);
      }else{
        const {items,index}=fullItem(path);
        if(action==='up'&&index>0)[items[index-1],items[index]]=[items[index],items[index-1]];
        if(action==='down'&&index<items.length-1)[items[index+1],items[index]]=[items[index],items[index+1]];
        if(action==='copy')items.splice(index+1,0,freshStep(items[index]));
        if(action==='delete')items.splice(index,1);
        if(action==='split'&&items[index].workoutSteps)items.splice(index,1,...splitRepeat(items[index]));
      }
      showFullEditor();
    }catch(error){const box=$('#garmin-full-form .form-error');if(box)box.textContent=error.message;else toast(error.message);}
    return;
  }
  if(target.dataset.planType){state.planType=target.dataset.planType;render();return;}
  if(target.dataset.themeChoice){const id=window.FormTheme.apply(target.dataset.themeChoice);render();document.querySelector(`[data-theme-choice="${id}"]`).focus({preventScroll:true});toast('Color theme saved.');return;}
  if(target.matches('.close-editor')){if(!state.workoutSaving&&!state.operationSaving)$('#editor-dialog').close();return;}
  if(target.dataset.range){state.zoomHistory=[];state.range=target.dataset.range;state.limit=24;render();return;}
  if(target.dataset.matchExercise){state.selected=target.dataset.matchExercise;state.metric='matched';state.search='';location.hash='exercises';navigate('exercises');return;}
  if(target.hasAttribute('data-volume-reset')){
    markSettingsDirty(target);
    const row=target.closest('[data-volume-exercise]'),rule=exerciseVolumeRule(target.dataset.volumeReset);
    for(const field of ['multiplier','bodyweight','loadCopies','assistance'])row.querySelector(`[data-factor="${field}"]`).value=String(rule[field]);
    const reviewed=row.querySelector('[data-factor="reviewed"]');if(reviewed)reviewed.checked=false;
    toast('Row reset to reviewed defaults. Save volume factors to apply.');return;
  }
  if(target.dataset.volumeMode){if(target.dataset.volumeMode==='muscle'&&state.volumeMetric==='estimatedMax')state.volumeMetric='volume';state.volumeMode=target.dataset.volumeMode;state.volumeWeek='';state.volumeCards=12;render();return;}
  if(target.dataset.volumeMetric){state.volumeMetric=target.dataset.volumeMetric;if(state.volumeMetric==='estimatedMax')state.volumeMode='exercise';render();return;}
  if(target.dataset.volumeGroup){const move=target.classList.contains('volume-mini');state.volumeGroup[state.volumeMode]=target.dataset.volumeGroup;state.volumeWeek='';render();if(move)document.querySelector('.volume-history-panel')?.scrollIntoView({behavior:'smooth',block:'start'});return;}
  if(target.dataset.action==='more-volume-cards'){state.volumeCards+=12;render();return;}
  if(target.dataset.editWorkout){$('#workout-dialog').close();showWorkoutEditor(target.dataset.editWorkout);return;}
  if(target.dataset.editGoal){showGoalEditor(target.dataset.editGoal);return;}
  if(target.dataset.archiveGoal||target.dataset.restoreGoal||target.dataset.undoEdit){
    target.disabled=true;
    try{
      if(target.dataset.archiveGoal)await saveAction({action:'goal_archive',id:target.dataset.archiveGoal});
      if(target.dataset.restoreGoal){const g=state.data.archivedGoals.find(g=>g.id===target.dataset.restoreGoal);await saveAction({action:'goal_save',goal:g});}
      if(target.dataset.undoEdit)await saveAction({action:'undo_workout',id:target.dataset.undoEdit});
      toast(target.dataset.undoEdit?'Edit undone. Original records restored.':'Goal updated.');
    }catch(error){errorToast(error);target.disabled=false;}
    return;
  }
  if(target.dataset.removeDraft!==undefined||target.dataset.copyDraft!==undefined){
    const index=Number(target.dataset.removeDraft??target.dataset.copyDraft);
    if(target.dataset.removeDraft!==undefined){if(state.draft.sets.length===1){toast('Keep at least one set.');return;}state.draft.sets.splice(index,1);}
    else{const row=state.draft.sets[index];state.draft.sets.splice(index+1,0,{exercise:row.exercise,weight:row.weight,reps:row.reps,note:row.note});}
    $('#draft-rows').innerHTML=draftRows();persistDraft();return;
  }
  if(target.hasAttribute('data-remove-equipment')){
    markSettingsDirty(target);
    const row=target.closest('[data-equipment-id]');
    for(const select of document.querySelectorAll('[data-equipment-exercise]')){
      for(const option of [...select.options])if(option.value===row.dataset.equipmentId)option.remove();
    }
    row.remove();return;
  }
  if(target.dataset.resumeDraft){showWorkoutEditor(target.dataset.resumeDraft==='new'?null:target.dataset.resumeDraft);return;}
  const action=target.dataset.action;
  if(action==='fill-garmin-targets'){
    target.disabled=true;
    try{
      const result=await garminRequest({operation:'revise',previewId:state.garminPreview.previewId,useSuggestions:true,manualTargets:[]});
      state.garminUseSuggestions=true;showGarminEditor(result);
      $('#garmin-fill-notes').textContent=result.changes.length?'Suggested values filled. Review and adjust each set above.':'No automatic changes available; edit the values manually.';
      for(const item of result.skipped){const note=document.createElement('p');note.textContent=item.exercise+': '+item.reason;$('#garmin-fill-notes').append(note);}
    }catch(error){toast(error.message||'Could not fill suggestions');target.disabled=false;}
    return;
  }
  if(action==='undo-zoom'||action==='reset-zoom'){
    const prior=action==='reset-zoom'?state.zoomHistory?.[0]:state.zoomHistory?.at(-1);
    if(prior){Object.assign(state,prior);if(action==='reset-zoom')state.zoomHistory=[];else state.zoomHistory.pop();state.volumeWeek='';render();}return;
  }
  if(action==='add-equipment'){
    markSettingsDirty(target);
    const id=crypto.randomUUID();
    $('#equipment-rows').insertAdjacentHTML('beforeend',equipmentRow(id));
    for(const select of document.querySelectorAll('[data-equipment-exercise]'))select.add(new Option('New profile',id));
    $('#equipment-rows').lastElementChild.querySelector('input').focus();return;
  }
  if(action==='discard-draft'){removeStoredDraft(state.draft.sessionId);state.draft=null;$('#editor-dialog').close();render();return;}
  if(action==='new-workout')showWorkoutEditor();
  if(action==='new-goal')showGoalEditor();
  if(action==='more-volume'){state.volumeLimit+=100;render();}
  if(action==='swap-compare'){[state.compareLeft,state.compareRight]=[state.compareRight,state.compareLeft];render();}
  if(action==='add-draft-set'){state.draft.sets.push({exercise:state.draft.sets.at(-1)?.exercise||(state.selected==='all'?'':state.selected),weight:null,reps:null,note:''});$('#draft-rows').innerHTML=draftRows();persistDraft();}
  if(action==='apply-range'){
    const from=$('#from-date').value,to=$('#to-date').value;
    if(!from||!to||from>to||to>today()){$('#range-error').textContent='Choose a start and end date, in order, no later than today.';return;}
    state.zoomHistory=[];state.range='custom';state.from=from;state.to=to;state.limit=24;render();
  }
});
document.addEventListener('change',event=>{
  const element=event.target;
  if(element.dataset.fullField==='stepType'){
    const {items,index}=fullItem(element.dataset.fullPath),step=items[index],kind=element.value;
    const ids={interval:3,warmup:1,cooldown:4,rest:5};
    step.stepType={stepTypeId:ids[kind],stepTypeKey:kind,displayOrder:ids[kind]};
    if(kind==='rest'){step.endCondition={conditionTypeId:2,conditionTypeKey:'time',displayOrder:2};step.endConditionValue=90;}
    showFullEditor();return;
  }
  if(element.dataset.fullField==='endCondition'){
    const {items,index}=fullItem(element.dataset.fullPath),step=items[index],key=element.value;
    const ids={'lap.button':1,time:2,reps:10};
    step.endCondition={conditionTypeId:ids[key],conditionTypeKey:key,displayOrder:ids[key],displayable:true};
    step.endConditionValue=key==='reps'?8:key==='time'?90:null;
    showFullEditor();return;
  }
  if(element.dataset.fullField==='exerciseName'){
    const {items,index}=fullItem(element.dataset.fullPath),code=element.value.trim().toUpperCase().replaceAll(' ','_');
    const category=fullExerciseCodes().get(code);
    if(category){items[index].category=category;showFullEditor();}
    return;
  }
  if(element.id==='rep-target'){state.repTarget=Math.max(1,Math.min(500,Number(element.value)||5));render();}
  if(element.id==='plateau-window'){state.plateauWindow=Math.max(3,Math.min(12,Number(element.value)||4));render();}
  if(element.id==='insight-exercise'){state.insightExercise=element.value;render();}
  if(element.id==='recovery-metric'){state.recoveryMetric=element.value;render();}
  if(element.id==='recovery-threshold'){state.recoveryThreshold=Math.max(0,Math.min(24,Number(element.value)||0));render();}
  if(element.id==='compare-left'){state.compareLeft=element.value;render();}
  if(element.id==='compare-right'){state.compareRight=element.value;render();}
  if(element.id==='goal-mode'){$('#goal-form input[name="weight"]').disabled=element.value==='reps';}
});
document.addEventListener('input',event=>{
  const input=event.target;
  if(input.dataset.fullRoot){state.garminFull[input.dataset.fullRoot]=input.value;return;}
  if(input.dataset.fullField){
    const {items,index}=fullItem(input.dataset.fullPath),field=input.dataset.fullField;
    items[index][field]=field==='skipLastRestStep'?input.checked:['numberOfIterations','endConditionValue','weightValue'].includes(field)?(input.value===''?null:Number(input.value)):['category','exerciseName'].includes(field)?input.value.trim().toUpperCase().replaceAll(' ','_'):input.value;
    if(field==='numberOfIterations')items[index].endConditionValue=items[index].numberOfIterations;
    return;
  }
  if(input.hasAttribute('data-equipment-name')){
    const id=input.closest('[data-equipment-id]').dataset.equipmentId;
    for(const select of document.querySelectorAll('[data-equipment-exercise]')){
      for(const option of select.options)if(option.value===id)option.textContent=input.value||'New profile';
    }
  }
  if(input.closest?.('#workout-form')&&input.name){state.draft[input.name]=input.value;persistDraft();}
  if(input.dataset.row!==undefined){
    const row=state.draft.sets[Number(input.dataset.row)];
    row[input.dataset.field]=['weight','reps'].includes(input.dataset.field)?(input.value===''?null:Number(input.value)):input.value;
    if(input.dataset.field==='exercise')input.style.color=exerciseVisual(input.value).color;
    persistDraft();
  }
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(!['volume-form','goal-form','workout-form','muscle-form','progression-form','equipment-form','garmin-form','garmin-full-form'].includes(form.id))return;
  event.preventDefault();const button=form.querySelector('[type="submit"]'),error=form.querySelector('.form-error');
  if(button.disabled)return;
  button.disabled=true;error.textContent='';
  try{
    if(form.id==='garmin-full-form'){
      const draft=state.garminFull;
      const preview=await garminRequest({operation:'edit',workoutId:draft.workoutId,expectedRevision:draft.revision,name:draft.name,description:draft.description,segments:draft.segments});
      showFullPreview(preview);
    }
    if(form.id==='garmin-form'){
      const manualTargets=[...form.querySelectorAll('[data-garmin-row]')].map(row=>{
        const weight=row.querySelector('[data-garmin-weight]'),reps=row.querySelector('[data-garmin-reps]');
        return {index:Number(row.dataset.garminRow),weight:weight.disabled||weight.value===''?null:Number(weight.value),reps:reps.value===''?null:Number(reps.value)};
      });
      const preview=await garminRequest({operation:'revise',previewId:form.dataset.preview,useSuggestions:Boolean(state.garminUseSuggestions),manualTargets});
      showGarminPreview(preview);
    }
    if(form.id==='equipment-form'){
      const profiles={},assignments={};
      for(const row of form.querySelectorAll('[data-equipment-id]')){
        const tokens=row.querySelector('[data-equipment-loads]').value.split(',').map(v=>v.trim());
        if(tokens.some(v=>!v||!Number.isFinite(Number(v))))throw new Error('Enter available loads as comma-separated numbers.');
        profiles[row.dataset.equipmentId]={name:row.querySelector('[data-equipment-name]').value,loads:tokens.map(Number)};
      }
      for(const select of form.querySelectorAll('[data-equipment-exercise]'))if(select.value)assignments[select.dataset.equipmentExercise]=select.value;
      await saveAction({action:'equipment_save',metadataRevision:form.dataset.revision,equipment:{profiles,assignments}},form);
      toast('Equipment saved. Next-session targets now use your available loads.');
    }
    if(form.id==='goal-form'){
      const values=Object.fromEntries(new FormData(form));
      if(form.dataset.id)values.id=form.dataset.id;
      await saveAction({action:'goal_save',goal:values});$('#editor-dialog').close();toast('Goal saved.');
    }
    if(form.id==='workout-form'){
      const draft=state.draft;
      if(!draft.pending){
        Object.assign(draft,Object.fromEntries(new FormData(form)));
        draft.pending={action:'workout_save',requestId:draft.requestId,sessionId:draft.sessionId,revision:draft.revision,expectedMetadata:draft.expectedMetadata,name:draft.name,date:draft.date,durationMinutes:draft.durationMinutes,sets:structuredClone(draft.sets)};
      }
      persistDraft();state.workoutSaving=true;form.querySelector('fieldset').disabled=true;form.querySelector('[data-action="discard-draft"]').disabled=true;
      try {
        await saveAction(draft.pending);
        removeStoredDraft(draft.sessionId);state.draft=null;$('#editor-dialog').close();toast('Workout saved to your training database.');
      } catch(failure) {
        if([400,401,403,409].includes(failure.status)){delete draft.pending;draft.requestId=crypto.randomUUID();button.textContent='Save workout';form.querySelector('fieldset').disabled=false;form.querySelector('[data-action="discard-draft"]').disabled=false;}
        else {button.textContent='Retry save';failure.message+=' Your draft is retained. Retry uses the same save identity to prevent duplicates.';}
        persistDraft();throw failure;
      } finally {state.workoutSaving=false;}
    }
    if(form.id==='progression-form'){
      const mappings={...(state.data.progressionRules||{})};
      for(const row of form.querySelectorAll('[data-progression-name]')){
        const rule={};for(const input of row.querySelectorAll('[data-rule]'))rule[input.dataset.rule]=Number(input.value);
        if(rule.repMin>=rule.repMax)throw new Error('Each lower rep target must be below its rep ceiling.');
        mappings[row.dataset.progressionName]=rule;
      }
      await saveAction({action:'progression_save',metadataRevision:form.dataset.revision,mappings},form);toast('Progression settings saved.');
    }
    if(form.id==='volume-form'){
      const exercises={...(state.data.volumeSettings?.exercises||{})};
      for(const row of form.querySelectorAll('[data-volume-exercise]')){
        exercises[row.dataset.volumeExercise]={multiplier:Number(row.querySelector('[data-factor="multiplier"]').value),bodyweight:Number(row.querySelector('[data-factor="bodyweight"]').value),loadCopies:Number(row.querySelector('[data-factor="loadCopies"]').value),assistance:row.querySelector('[data-factor="assistance"]').value==='true',reviewed:row.querySelector('[data-factor="reviewed"]')?.checked||false};
      }
      const weight=form.elements.bodyWeightKg.value;
      await saveAction({action:'volume_save',metadataRevision:form.dataset.revision,settings:{bodyWeightKg:weight===''?null:Number(weight),exercises}},form);
      toast('Volume factors saved. Weekly history recalculated.');
    }
    if(form.id==='muscle-form'){
      const mappings={...(state.data.muscleOverrides||{})};for(const input of form.querySelectorAll('[data-muscle]'))mappings[input.dataset.muscle]=input.value;
      await saveAction({action:'muscle_save',metadataRevision:form.dataset.revision,mappings},form);toast('Primary muscle groups saved.');
    }
  }catch(e){error.textContent=e.message+(e.status===409&&form.matches(settingsFormSelector)?' Your input is retained. Discard these changes to load the latest settings before reapplying your edits.':'');button.disabled=false;}
});
$('#editor-dialog').addEventListener('click',event=>{if(event.target===$('#editor-dialog')&&!state.workoutSaving&&!state.operationSaving)$('#editor-dialog').close();});

$('#editor-dialog').addEventListener('cancel',event=>{if(state.workoutSaving||state.operationSaving)event.preventDefault();});
$('#editor-dialog').addEventListener('close',()=>{if(state.page==='logging'&&state.data)render();});

window.addEventListener('storage',event=>{if(event.key===window.FormTheme.key&&state.data)render();});

state.page=pages[location.hash.slice(1)]?location.hash.slice(1):'overview';nav();
if(state.page==='operations'){render();loadOperationHistory();}
load(true);
setInterval(()=>load(true),300000);

document.addEventListener('keydown',event=>{
  if(event.key==='Escape'){
    const more=$('#more-navigation');
    if(more?.open){more.open=false;more.querySelector('summary').focus();}
  }
});
document.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-volume-week],g[data-map-muscle]')){event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});

document.addEventListener('toggle',event=>{if(event.target.matches?.('.layout-controls')&&event.target.isConnected)state.layoutOpen=event.target.open;},true);
document.addEventListener('change',event=>{
  const key=event.target.dataset.layoutVisible;if(!key||!overviewSections[key])return;
  const layout=overviewLayout();layout.hidden=layout.hidden.filter(k=>k!==key);if(!event.target.checked)layout.hidden.push(key);
  state.layoutOpen=true;saveOverviewLayout();render();document.querySelector(`[data-layout-visible="${key}"]`)?.focus();
});
document.addEventListener('click',event=>{
  const move=event.target.closest('[data-layout-move]'),reset=event.target.closest('[data-layout-reset]');
  if(move||reset){
    if(reset)savedOverview={order:Object.keys(overviewSections),hidden:[]};
    else{const order=overviewLayout().order,i=order.indexOf(move.dataset.layoutMove),j=i+Number(move.dataset.direction);if(i>=0&&j>=0&&j<order.length)[order[i],order[j]]=[order[j],order[i]];}
    state.layoutOpen=true;saveOverviewLayout();render();
    document.querySelector(reset?'[data-layout-reset]':`[data-layout-move="${move.dataset.layoutMove}"][data-direction="${move.dataset.direction}"]`)?.focus();return;
  }
  const day=event.target.closest('[data-calendar-day]'),shift=event.target.closest('[data-calendar-shift]'),now=event.target.closest('[data-calendar-today]');
  if(day||shift||now){
    if(day)state.calendarDay=day.dataset.calendarDay;
    if(shift){state.calendarMonth=shiftCalendar(state.calendarMonth||(range().to||today()).slice(0,7),Number(shift.dataset.calendarShift));state.calendarDay='';}
    if(now){state.calendarMonth=today().slice(0,7);state.calendarDay=today();}
    render();document.querySelector(day?`[data-calendar-day="${day.dataset.calendarDay}"]`:shift?`[data-calendar-shift="${shift.dataset.calendarShift}"]`:'[data-calendar-today]')?.focus();
  }
});
