import exerciseCatalog from '../../training/exercise_catalog.json' with {type:'json'};

export const present = value => typeof value === 'number' && Number.isFinite(value);
export const sumKnown = values => {
  const known = values.filter(present);
  return known.length ? known.reduce((a, b) => a + b, 0) : null;
};
export const maxKnown = values => {
  const known = values.filter(present);
  return known.length ? known.reduce((best,value)=>Math.max(best,value),-Infinity) : null;
};
export const isAssistedExercise = (name, settings={}) => typeof settings.exercises?.[name]?.assistance==='boolean'?settings.exercises[name].assistance:/\bassisted\b|\bassistance\b/i.test(name);
const minKnown = values => {const known=values.filter(present);return known.length?known.reduce((best,value)=>Math.min(best,value),Infinity):null;};
export function filterData(data, range, source = 'all') {
  const within = row => (!range.from || row.date >= range.from) && (!range.to || row.date <= range.to);
  const sets = data.sets.filter(row => within(row) && (source === 'all' || row.source === source));
  const ids = new Set(sets.map(row => row.sessionId));
  const workouts = data.workouts.filter(row => within(row) && (source === 'all' || ids.has(row.id)));
  return { sets, workouts };
}
export function exerciseSummaries(sets) {
  const groups = new Map();
  for (const set of sets) {
    if (!groups.has(set.exercise)) groups.set(set.exercise, []);
    groups.get(set.exercise).push(set);
  }
  return [...groups.entries()].map(([name, rows]) => {
    const assisted=rows.some(s=>typeof s.assistance==='boolean')?rows.some(s=>s.assistance===true):isAssistedExercise(name);
    const bestLoad=assisted?minKnown:maxKnown;
    const sessions = new Map();
    for (const row of rows) {
      if (!sessions.has(row.sessionId)) sessions.set(row.sessionId, []);
      sessions.get(row.sessionId).push(row);
    }
    const history = [...sessions.entries()].map(([id, entries]) => ({
      id, date: entries[0].date, time: entries[0].time, sets: entries.length,
      weight: bestLoad(entries.map(s => s.weight)),
      estimatedMax: assisted?null:maxKnown(entries.map(s => s.estimatedMax)),
      reps: sumKnown(entries.map(s => s.reps)), volume: sumKnown(entries.map(s => s.volume)),
      rows: entries,
    })).sort((a, b) => a.date.localeCompare(b.date) || a.time.localeCompare(b.time));
    const weighted = history.filter(row => present(row.weight));
    const first = weighted[0]?.weight ?? null;
    const last = weighted.at(-1)?.weight ?? null;
    return { name, assisted, rows, history, count: rows.length, sessions: history.length,
      bestWeight: bestLoad(rows.map(s => s.weight)), bestReps: maxKnown(rows.map(s => s.reps)),
      bestMax: assisted?null:maxKnown(rows.map(s => s.estimatedMax)),
      reps: sumKnown(rows.map(s => s.reps)), volume: sumKnown(rows.map(s => s.volume)),
      firstWeight: first, latestWeight: last,
      change: present(first) && present(last) ? last - first : null,
      latestDate: history.at(-1)?.date ?? '',
    };
  }).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}
export function weeklyWorkouts(workouts, today, length = 12) {
  const current = new Date(today + 'T00:00:00Z');
  current.setUTCDate(current.getUTCDate() - (current.getUTCDay() + 6) % 7);
  const weeks = Array.from({length}, (_, index) => {
    const date = new Date(current);
    date.setUTCDate(date.getUTCDate() - (length - 1 - index) * 7);
    return {date: date.toISOString().slice(0, 10), count: 0};
  });
  for (const workout of workouts) {
    const date = new Date(workout.date + 'T00:00:00Z');
    date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    const bucket = weeks.find(week => week.date === date.toISOString().slice(0, 10));
    if (bucket) bucket.count++;
  }
  return weeks;
}
export function chartPoints(history, field) {
  // Missing metrics remain gaps; recorded zero is a real point.
  return history.map(row => ({date: row.date, time: row.time, value: row[field], id: row.id}));
}
// Quoting CSV alone does not stop spreadsheet apps evaluating imported formulas.
function csvCell(value) {
  let text=String(value ?? '');
  if(typeof value==='string' && /^[\s]*[=+@-]|^[\t\r\n]/.test(text))text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
}
export function csvForSets(sets) {
  const columns = ['Date','Exercise','Workout ID','Set','Load (kg)','Reps','Volume (kg·reps)','Estimated 1RM (kg)','Source','Original exercise','Note'];
  const rows = sets.map(s => [s.date,s.exercise,s.sessionId,s.number,s.weight,s.reps,s.volume,s.estimatedMax,s.source,s.originalExercise,s.note]);
  return '\uFEFF' + [columns,...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
}
export function csvForRecovery(rows) {
  const columns = ['Date','Sleep (hours)','Sleep score','Overnight HRV (ms)','Resting HR (bpm)','Body Battery at wake','Deep sleep (seconds)','Light sleep (seconds)','REM sleep (seconds)','Awake (seconds)','Body weight (kg)'];
  return '\uFEFF' + [columns,...rows.map(r => [r.date,r.sleepHours,r.sleepScore,r.hrv,r.restingHR,r.bodyBattery,r.deepSeconds,r.lightSeconds,r.remSeconds,r.awakeSeconds,r.bodyWeightKg])].map(row => row.map(csvCell).join(',')).join('\r\n');
}

export const MUSCLE_GROUPS = exerciseCatalog.muscleGroups;
export const EXERCISE_NAME_ALIASES = exerciseCatalog.aliases;
export const BODYWEIGHT_CATEGORIES = exerciseCatalog.bodyweightCategories;
export const DEFAULT_MUSCLES = Object.fromEntries(Object.entries(exerciseCatalog.exercises).filter(([,entry])=>'muscle' in entry).map(([name,entry])=>[name,entry.muscle]));

// Display order for stacked bars: lower body to upper body; unknown groups last.
export const MUSCLE_STACK_ORDER=['Calves','Quads','Hamstrings','Adductors','Glutes','Core','Back','Chest','Biceps','Triceps','Shoulders','Unassigned'];
export function compareExerciseStack(a,b,overrides={}) {
  const rank=name=>{
    const group=overrides[name]||DEFAULT_MUSCLES[name]||'Unassigned';
    const index=MUSCLE_STACK_ORDER.indexOf(group);
    return index<0?MUSCLE_STACK_ORDER.length-1:index;
  };
  return rank(a)-rank(b)||a.localeCompare(b);
}

// Stable identity colors, shared by every exercise presentation.
const MUSCLE_COLORS=['#94c8ff','#59dcc5','#b6a0ff','#ffd66e','#ff9caa','#bada7a','#ffbd75','#e9a2e5','#70d4ed','#d4b1fa','#e0c59b','#aebdce'];
export function muscleColor(group) {
  const index=Math.max(0,MUSCLE_GROUPS.indexOf(group));
  return `var(--series-${index},${MUSCLE_COLORS[index]})`;
}
export function exerciseColor(name,overrides={}) {
  const group=overrides[name]||DEFAULT_MUSCLES[name]||'Unassigned';
  const base=muscleColor(MUSCLE_GROUPS.includes(group)?group:'Unassigned');
  const hash=[...String(name)].reduce((n,c)=>(Math.imul(n,31)+c.charCodeAt(0))>>>0,0);
  // Keep the group hue; small stable shade differences distinguish its exercises.
  return `color-mix(in srgb,${base} ${78+hash%23}%,var(--exercise-shade,#ffffff))`;
}

// Broad movement roles shared by the body map and volume history,
// not estimates of muscle activation.
// Reference: https://www.nasm.org/workout-exercise-guidance
const MUSCLE_INVOLVEMENT = Object.fromEntries(Object.entries(exerciseCatalog.exercises).filter(([,entry])=>'roles' in entry).map(([name,entry])=>[name,entry.roles]));

export function exerciseMuscles(name, overrides={}) {
  const roles=MUSCLE_INVOLVEMENT[name];
  const assigned=overrides[name];
  // The legacy editor submits every exercise, including unchanged defaults.
  // Saving that form must not erase a compound lift's other primary muscles.
  const changedAssignment=assigned && assigned!==DEFAULT_MUSCLES[name];
  const primary=changedAssignment ? [assigned] : roles?.primary || [assigned || DEFAULT_MUSCLES[name] || 'Unassigned'];
  const secondary=primary.includes('Unassigned') ? [] : (roles?.secondary || []).filter(group=>!primary.includes(group));
  return {primary:[...new Set(primary)],secondary:[...new Set(secondary)]};
}

export function shiftDay(day, days) {
  const value=new Date(day+'T00:00:00Z');value.setUTCDate(value.getUTCDate()+days);
  return value.toISOString().slice(0,10);
}

export function muscleMapWeeks(sets, range={}, asOf) {
  const dates=sets.map(s=>s.date).sort();
  const to=range.to || asOf, from=range.from || (dates[0] && dates[0]<to ? dates[0] : to);
  if(!from||!to||from>to)return [];
  const weeks=[];
  for(let week=weekStart(from);week<=to;week=shiftDay(week,7))weeks.push(week);
  return weeks;
}

export function muscleWeekSummary(sets, week, overrides={}, includeSecondary=true) {
  const end=shiftDay(week,6),rows=sets.filter(s=>s.date>=week&&s.date<=end);
  const summarize=entries=>({sets:entries.length,reps:sumKnown(entries.map(s=>s.reps)),volume:sumKnown(entries.map(s=>s.volume)),
    repsKnown:entries.filter(s=>present(s.reps)).length,volumeKnown:entries.filter(s=>present(s.volume)).length});
  const groups=MUSCLE_GROUPS.map(name=>({name,primaryRows:[],secondaryRows:[]}));
  const byName=new Map(groups.map(group=>[group.name,group]));
  for(const row of rows){
    const roles=exerciseMuscles(row.exercise,overrides);
    for(const group of roles.primary)byName.get(group)?.primaryRows.push(row);
    if(includeSecondary)for(const group of roles.secondary)byName.get(group)?.secondaryRows.push(row);
  }
  const allExercises=[...new Set(rows.map(s=>s.exercise))].map(name=>({name,role:'all',...summarize(rows.filter(s=>s.exercise===name))})).sort((a,b)=>compareExerciseStack(a.name,b.name,overrides));
  return {week,end,...summarize(rows),exercises:allExercises,workouts:new Set(rows.map(s=>s.sessionId)).size,
    groups:groups.map(({name,primaryRows,secondaryRows})=>{
      const entries=[...primaryRows,...secondaryRows];
      const exercises=new Map();
      for(const [role,items] of [['primary',primaryRows],['secondary',secondaryRows]])for(const row of items){
        if(!exercises.has(row.exercise))exercises.set(row.exercise,{name:row.exercise,role,rows:[]});
        exercises.get(row.exercise).rows.push(row);
      }
      return {name,...summarize(entries),primary:primaryRows.length,secondary:secondaryRows.length,
        exercises:[...exercises.values()].map(e=>({name:e.name,role:e.role,...summarize(e.rows)}))
          .sort((a,b)=>a.role.localeCompare(b.role)||b.sets-a.sets||a.name.localeCompare(b.name))};
    })};
}

// Compare the same weekdays, even when the page's date filter hides prior weeks.
// Empty calendar weeks inside recorded history contribute zero to the average.
export function muscleWeekComparison(sets, week, {count=1,range={},asOf,historyStart,overrides={},includeSecondary=true}={}) {
  if(![1,4].includes(count))return null;
  const from=range.from&&range.from>week?range.from:week;
  const end=shiftDay(week,6);
  let to=range.to&&range.to<end?range.to:end;
  if(asOf&&week<=asOf&&asOf<to)to=asOf;
  const first=historyStart || sets.map(s=>s.date).sort()[0];
  const periods=Array.from({length:count},(_,i)=>({from:shiftDay(from,-7*(i+1)),to:shiftDay(to,-7*(i+1))}));
  const available=Boolean(first&&from<=to&&(!asOf||week<=asOf)&&periods.at(-1).from>=first);
  if(!available)return {count,from,to,periods,available:false,groups:[]};
  const summaries=periods.map(period=>muscleWeekSummary(sets.filter(s=>s.date>=period.from&&s.date<=period.to),weekStart(period.from),overrides,includeSecondary));
  const average=(rows,field)=>rows.reduce((n,row)=>n+row[field],0)/count;
  return {count,from,to,periods,available:true,sets:average(summaries,'sets'),workouts:average(summaries,'workouts'),
    reps:summaries.every(s=>s.repsKnown===s.sets)?summaries.reduce((n,s)=>n+(s.reps??0),0)/count:null,
    volume:summaries.every(s=>s.volumeKnown===s.sets)?summaries.reduce((n,s)=>n+(s.volume??0),0)/count:null,
    groups:MUSCLE_GROUPS.map(name=>{
      const rows=summaries.map(s=>s.groups.find(g=>g.name===name));
      const complete=field=>rows.every(r=>r[field+'Known']===r.sets);
      return {name,sets:average(rows,'sets'),primary:average(rows,'primary'),secondary:average(rows,'secondary'),
        reps:complete('reps')?rows.reduce((n,r)=>n+(r.reps??0),0)/count:null,
        volume:complete('volume')?rows.reduce((n,r)=>n+(r.volume??0),0)/count:null};
    })};
}
export function weekStart(date) {
  const d=new Date(date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return d.toISOString().slice(0,10);
}
export function matchingRepHistory(sets, reps) {
  const matching=sets.filter(s=>s.reps===Number(reps)&&present(s.weight));
  return exerciseSummaries(matching).flatMap(e=>e.history.map(h=>({...h,exercise:e.name}))).sort((a,b)=>a.date.localeCompare(b.date)||a.time.localeCompare(b.time));
}
export function volumeByWeek(sets, mode='exercise', overrides={}) {
  const groups=new Map();
  for(const s of sets){
    const roles=exerciseMuscles(s.exercise,overrides);
    const names=mode==='muscle'?[...roles.primary,...roles.secondary]:[s.exercise];
    for(const group of names){
      const week=weekStart(s.date),key=week+'|'+group;
      if(!groups.has(key))groups.set(key,{week,group,sets:0,reps:0,repsKnown:0,volume:0,volumeKnown:0});
      const row=groups.get(key);row.sets++;
      if(present(s.reps)){row.reps+=s.reps;row.repsKnown++;}
      if(present(s.volume)){row.volume+=s.volume;row.volumeKnown++;}
    }
  }
  return [...groups.values()].map(r=>({...r,reps:r.repsKnown?r.reps:null,volume:r.volumeKnown?r.volume:null})).sort((a,b)=>b.week.localeCompare(a.week)||b.sets-a.sets||a.group.localeCompare(b.group));
}
export function plateauSignals(sets, asOf, window=4) {
  return exerciseSummaries(sets).map(e=>{
    const comparable=e.rows.filter(s=>present(s.weight)&&(e.assisted?s.weight>=0:s.weight>0)&&present(s.reps)&&s.reps>0);
    const bands=new Map();
    for(const s of comparable){
      if(!bands.has(s.reps))bands.set(s.reps,new Set());bands.get(s.reps).add(s.sessionId);
    }
    const target=[...bands].sort((a,b)=>b[1].size-a[1].size||a[0]-b[0])[0]?.[0];
    const history=target?matchingRepHistory(comparable,target):[];
    const last=history.at(-1),tail=history.slice(-window);
    const age=last?(new Date(asOf)-new Date(last.date))/86400000:Infinity;
    const span=tail.length?(new Date(tail.at(-1).date)-new Date(tail[0].date))/86400000:0;
    const bestLoad=e.assisted?minKnown:maxKnown;
    const prior=history.slice(0,-window),bestPrior=bestLoad(prior.map(h=>h.weight));
    let status='insufficient',reason=`Needs at least ${window+1} comparable workouts spanning 14 days.`;
    if(!history.length&&e.rows.some(s=>s.weight===0)&&!e.assisted)reason='No positive external loads to compare. Review bodyweight-only progress using reps in exercise history.';
    if(history.length>=window+1&&span>=14){
      if(age>60){status='inactive';reason='Last comparable workout was over 60 days ago.';}
      else if(e.assisted?bestLoad(tail.map(h=>h.weight))>=bestPrior:bestLoad(tail.map(h=>h.weight))<=bestPrior){status='watch';reason=`No ${e.assisted?'lower assistance':'higher load'} at ${target} reps in the last ${window} comparable workouts.`;}
      else{status='progressing';reason=`A new ${target}-rep ${e.assisted?'assistance':'load'} best appears in the last ${window} comparable workouts.`;}
    }
    return {exercise:e.name,assisted:e.assisted,reps:target??null,status,reason,eligible:history.length,lastDate:last?.date??e.latestDate,baseline:bestPrior,latest:last?.weight??null};
  }).sort((a,b)=>({watch:0,progressing:1,inactive:2,insufficient:3}[a.status]-{watch:0,progressing:1,inactive:2,insufficient:3}[b.status]));
}
export function compareWorkouts(data, leftId, rightId) {
  const a=exerciseSummaries(data.sets.filter(s=>s.sessionId===leftId));
  const b=exerciseSummaries(data.sets.filter(s=>s.sessionId===rightId));
  const names=[...new Set([...a,...b].map(e=>e.name))];
  const delta=(x,y)=>present(x)&&present(y)?y-x:null;
  return names.map(name=>{
    const left=a.find(e=>e.name===name),right=b.find(e=>e.name===name);
    const reps=[...new Set((left?.rows||[]).filter(s=>present(s.reps)&&present(s.weight)).map(s=>s.reps))].filter(rep=>(right?.rows||[]).some(s=>s.reps===rep&&present(s.weight)));
    const bestLoad=(left?.assisted||right?.assisted)?minKnown:maxKnown;
    const matched=reps.map(rep=>({reps:rep,left:bestLoad(left.rows.filter(s=>s.reps===rep).map(s=>s.weight)),right:bestLoad(right.rows.filter(s=>s.reps===rep).map(s=>s.weight))}));
    const volumeComplete=Boolean(left&&right&&left.rows.every(s=>present(s.volume))&&right.rows.every(s=>present(s.volume)));
    return {name,left,right,loadChange:delta(left?.bestWeight,right?.bestWeight),volumeComplete,volumeChange:volumeComplete?delta(left.volume,right.volume):null,matched};
  });
}
export function recoveryComparison(sets, recovery, exercise, reps, metric='sleepHours', threshold=null) {
  const daily=new Map(recovery.map(r=>[r.date,r]));
  const pairs=matchingRepHistory(sets.filter(s=>s.exercise===exercise),reps).filter(h=>present(daily.get(h.date)?.[metric])).map(h=>({...h,recovery:daily.get(h.date)[metric]}));
  const sorted=pairs.map(p=>p.recovery).sort((a,b)=>a-b);
  const median=sorted.length?(sorted[Math.floor((sorted.length-1)/2)]+sorted[Math.ceil((sorted.length-1)/2)])/2:null;
  const cut=present(threshold)?threshold:median;
  const low=pairs.filter(p=>p.recovery<cut),high=pairs.filter(p=>p.recovery>=cut);
  const mean=rows=>rows.length?sumKnown(rows.map(r=>r.weight))/rows.length:null;
  return {pairs,threshold:cut,low:{n:low.length,mean:mean(low)},high:{n:high.length,mean:mean(high)},enough:low.length>=3&&high.length>=3};
}
export function goalProgress(goal, sets, settings={}) {
  const rows=sets.filter(s=>s.exercise===goal.exercise);
  const repsOnly=goal.mode==='reps',assisted=!repsOnly&&isAssistedExercise(goal.exercise,settings);
  const candidates=rows.filter(s=>present(s.reps)&&(repsOnly||(present(s.weight)&&s.reps>=goal.reps)));
  const best=(assisted?minKnown:maxKnown)(candidates.map(s=>repsOnly?s.reps:s.weight));
  const target=repsOnly?goal.reps:goal.weight;
  const achieved=rows.filter(s=>present(s.reps)&&s.reps>=goal.reps&&(repsOnly||(present(s.weight)&&(assisted?s.weight<=goal.weight:s.weight>=goal.weight)))).sort((a,b)=>a.date.localeCompare(b.date))[0];
  return {best,assisted,percent:achieved?100:present(best)&&target>0?Math.max(0,Math.min(100,(assisted?target/best:best/target)*100)):null,achieved:Boolean(achieved),date:achieved?.date??null,sessionId:achieved?.sessionId??null};
}
export function presetRange(preset, today) {
  if(preset==='all')return {from:'',to:today};
  const d=new Date(today+'T00:00:00Z');
  if(preset==='6m'||preset==='1y'){
    const year=d.getUTCFullYear()-(preset==='1y'?1:0),month=d.getUTCMonth()-(preset==='6m'?6:0),day=d.getUTCDate();
    const end=new Date(Date.UTC(year,month+1,0)).getUTCDate();
    d.setTime(Date.UTC(year,month,Math.min(day,end)));
  }else d.setUTCDate(d.getUTCDate()-(Number(preset)-1));
  return {from:d.toISOString().slice(0,10),to:today};
}

export function weeklyVolumeHistory(sets,mode='muscle',overrides={},range={}) {
  const filtered=sets.filter(s=>(!range.from||s.date>=range.from)&&(!range.to||s.date<=range.to));
  if(!filtered.length)return [];
  const dates=filtered.map(s=>s.date).sort(),from=range.from||dates[0],to=range.to||dates.at(-1);
  const weeks=[];
  for(const d=new Date(weekStart(from)+'T00:00:00Z');d.toISOString().slice(0,10)<=to;d.setUTCDate(d.getUTCDate()+7))weeks.push(d.toISOString().slice(0,10));
  const buckets=volumeByWeek(filtered,mode,overrides),names=[...new Set(buckets.map(r=>r.group))];
  return names.map(group=>{
    const rows=buckets.filter(r=>r.group===group),lookup=new Map(rows.map(r=>[r.week,r]));
    const history=weeks.map(week=>{
      const end=new Date(week+'T00:00:00Z');end.setUTCDate(end.getUTCDate()+6);const last=end.toISOString().slice(0,10);
      return {...(lookup.get(week)||{week,group,sets:0,reps:0,volume:0,repsKnown:0,volumeKnown:0}),from:week<from?from:week,to:last>to?to:last,partial:week<from||last>to,noRecords:!lookup.has(week)};
    });
    return {group,count:rows.reduce((n,r)=>n+r.sets,0),history};
  }).sort((a,b)=>b.count-a.count||a.group.localeCompare(b.group));
}

// Map a drag in plot coordinates to inclusive UTC calendar dates.
export function chartDateRange(start,end,left,right,a,b,workoutDates=null){
  if(![start,end,left,right,a,b].every(Number.isFinite)||end<start||right<=left)return null;
  const clamp=x=>Math.max(0,Math.min(1,(x-left)/(right-left)));
  const dates=[a,b].map(x=>workoutDates?.length?workoutDates[Math.min(workoutDates.length-1,Math.floor(clamp(x)*workoutDates.length))]:new Date(start+clamp(x)*(end-start)).toISOString().slice(0,10)).sort();
  return {from:dates[0],to:dates[1]};
}

// Calendar-spaced ticks avoid collisions when workouts cluster at one end.
export function timeAxisDates(first,last,count=4){
  const start=Date.parse(first+'T00:00:00Z'),end=Date.parse(last+'T00:00:00Z');
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<start)return [];
  if(start===end)return [first];
  const days=Math.round((end-start)/86400000),ticks=Math.min(Math.max(2,count),days+1);
  return Array.from({length:ticks},(_,i)=>new Date(start+Math.round(days*i/(ticks-1))*86400000).toISOString().slice(0,10));
}

// Workload proxy normalized to lifting 1 kg through 0.40 m once.
// Distances and work-equivalent body mass are explicit engineering priors,
// NOT measured ROM, muscle-force estimates, or validated stimulus conversions.
// Movement identities and profiles are maintained in the shared catalog.
export const DEFAULT_VOLUME_PROFILES = Object.fromEntries(Object.entries(exerciseCatalog.exercises).filter(([,entry])=>'volume' in entry).map(([name,entry])=>[name,entry.volume]));

export function exerciseVolumeRule(name, settings = {}) {
  const normalize=value=>value.toLowerCase().replace(/[-_]/g,' ').replace(/\s+/g,' ').trim();
  const key=Object.keys(DEFAULT_VOLUME_PROFILES).find(key=>normalize(key)===normalize(name));
  const profile=DEFAULT_VOLUME_PROFILES[key]||{multiplier:1,bodyweight:0,loadCopies:1,assistance:false,confidence:'unidentified',rationale:'No reviewed movement profile. Check the exercise identity, load convention, and factors before enabling this custom estimate.'};
  const override=settings.exercises?.[name]||{};
  return {...profile,...override,custom:Object.keys(override).length>0};
}
export function adjustedVolumeSets(sets, recovery = [], settings = {}) {
  const weights=recovery.filter(r=>present(r.bodyWeightKg)&&r.bodyWeightKg>0).sort((a,b)=>a.date.localeCompare(b.date));
  const rules=new Map(),bodyWeights=new Map();
  return sets.map(set=>{
    if(!rules.has(set.exercise))rules.set(set.exercise,{...exerciseVolumeRule(set.exercise,settings),recordedAssistance:isAssistedExercise(set.exercise,settings)});
    const rule=rules.get(set.exercise);
    if(!bodyWeights.has(set.date))bodyWeights.set(set.date,weights.findLast(r=>r.date<=set.date)?.bodyWeightKg ?? settings.bodyWeightKg);
    const bodyWeight=bodyWeights.get(set.date);
    const missingBodyweight=rule.bodyweight>0&&(!present(bodyWeight)||bodyWeight<=0);
    const unreviewed=rule.confidence==='unidentified'&&!rule.reviewed;
    const missingLoad=rule.bodyweight===0&&set.weight===0;
    // Only catalog-approved unweighted defaults may fill an unspecified added load.
    const assumedUnloaded=set.weight==null&&rule.unloadedWhenUnspecified===true&&rule.bodyweight>0&&!rule.assistance&&!rule.recordedAssistance;
    const externalLoad=assumedUnloaded?0:set.weight;
    const valid=present(externalLoad)&&externalLoad>=0&&present(set.reps)&&set.reps>=0&&!missingBodyweight&&!unreviewed&&!missingLoad;
    const load=valid?Math.max(0,(rule.assistance?-1:1)*externalLoad*rule.loadCopies+(rule.bodyweight?bodyWeight*rule.bodyweight:0)):null;
    return {...set,assistance:rule.recordedAssistance,volume:valid?load*set.reps*rule.multiplier:null,missingBodyweight,missingLoad,unreviewed,assumedUnloaded:valid&&assumedUnloaded};
  });
}

// Recorded external load is independent of bodyweight and movement estimates.
export function recordedVolumeSets(sets, settings = {}) {
  return sets.map(set => {
    const assistance=isAssistedExercise(set.exercise,settings);
    const valid=present(set.weight)&&set.weight>=0&&present(set.reps)&&set.reps>=0&&!assistance;
    return {...set,assistance,volume:valid?set.weight*set.reps:null};
  });
}

// One lift at a time. Weekly estimates are maxima, never sums across sets/lifts.
export function estimatedStrengthHistory(sets, exercise, weekly=false, range={}) {
  const rows=sets.filter(s=>s.exercise===exercise&&(!range.from||s.date>=range.from)&&(!range.to||s.date<=range.to));
  if(!rows.length)return [];
  const groups=new Map();
  for(const row of rows){
    const key=weekly?weekStart(row.date):row.sessionId;
    if(!groups.has(key))groups.set(key,{date:weekly?key:row.date,time:row.time||row.date,value:null,sets:0,eligibleSets:0,sessionId:null});
    const point=groups.get(key);point.sets++;
    if((typeof row.assistance==='boolean'?row.assistance:isAssistedExercise(row.exercise))||!present(row.estimatedMax)||row.estimatedMax<=0||!present(row.weight)||row.weight<=0||!Number.isInteger(row.reps)||row.reps<1||row.reps>10)continue;
    point.eligibleSets++;
    if(point.value===null||row.estimatedMax>point.value){point.value=row.estimatedMax;point.sessionId=row.sessionId;}
  }
  if(!weekly)return [...groups.values()].sort((a,b)=>a.date.localeCompare(b.date)||a.time.localeCompare(b.time));
  const dates=rows.map(s=>s.date).sort(),from=range.from||dates[0],to=range.to||dates.at(-1),history=[];
  for(const d=new Date(weekStart(from)+'T00:00:00Z');d.toISOString().slice(0,10)<=to;d.setUTCDate(d.getUTCDate()+7)){
    const day=d.toISOString().slice(0,10),end=new Date(d);end.setUTCDate(end.getUTCDate()+6);
    history.push({...groups.get(day)||{date:day,value:null,sets:0,eligibleSets:0,sessionId:null},partial:day<from||end.toISOString().slice(0,10)>to});
  }
  return history;
}
