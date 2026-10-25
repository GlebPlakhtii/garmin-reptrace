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

export const MUSCLE_GROUPS = ['Chest','Back','Shoulders','Biceps','Triceps','Quads','Hamstrings','Glutes','Calves','Core','Adductors','Unassigned'];
export const DEFAULT_MUSCLES = {
  'Barbell Bench Press':'Chest','Incline Bench Press':'Chest','Incline Dumbbell Bench Press':'Chest','Fly':'Chest','Cable Chest Fly':'Chest','Flye':'Chest','Machine Chest Fly':'Chest','Push Up':'Chest',
  'Barbell Deadlift':'Hamstrings','Weighted Leg Curl':'Hamstrings','Lying Leg Curl':'Hamstrings','Seated Leg Curl':'Hamstrings',
  'Barbell Shrug':'Back','Shrug':'Back','Lat Pulldown':'Back','Straight Arm Pulldown':'Back','Pull Up':'Back','Row':'Back','Seated Cable Row':'Back','Machine T-Bar Row':'Back',
  'Bent Over Rear Delt Fly':'Shoulders','Lateral Raise':'Shoulders','One Arm Cable Lateral Raise':'Shoulders','Seated Rear Lateral Raise':'Shoulders',
  'Bicep Curl':'Biceps','Cable Biceps Curl':'Biceps','Curl':'Biceps','Incline Bicep Curl':'Biceps','Single Arm Preacher Curl':'Biceps','Standing Ez Bar Biceps Curl':'Biceps',
  'Lying Ez Bar Triceps Extension':'Triceps','Overhead Cable Tricep Extension':'Triceps','Single Arm Cable Tricep Extension':'Triceps','Triceps Extension':'Triceps','Cable Triceps Extension':'Triceps',
  'Bulgarian Split Squat':'Quads','Overhead Barbell Squat':'Quads','Squat':'Quads','Leg Press':'Quads','Weighted Leg Extensions':'Quads','Machine Leg Extension':'Quads',
  'Hip Abduction':'Glutes','Hip Adduction':'Adductors','Calf Raise Machine':'Calves','Single Leg Calf Raise':'Calves','Weighted Seated Calf Raise':'Calves','Leg Press Calf Raise':'Calves',
  "Captain's Chair Leg Raises":'Core','Cable Crunch':'Core','Decline Crunch':'Core','Leg Raise':'Core','Sit Up':'Core',
};

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

// Broad movement roles for the body map, not estimates of muscle activation.
// The older primary-assignment charts deliberately retain their one-group totals.
// Reference: https://www.nasm.org/workout-exercise-guidance
const MUSCLE_INVOLVEMENT = Object.fromEntries([
  [['Barbell Bench Press','Incline Bench Press','Incline Dumbbell Bench Press','Push Up'], ['Chest'], ['Shoulders','Triceps']],
  [['Fly','Cable Chest Fly','Flye','Machine Chest Fly'], ['Chest'], ['Shoulders']],
  [['Pull Up','Lat Pulldown'], ['Back'], ['Biceps','Shoulders']],
  [['Row','Seated Cable Row','Machine T-Bar Row'], ['Back'], ['Biceps','Shoulders']],
  [['Straight Arm Pulldown'], ['Back'], ['Triceps']],
  [['Bent Over Rear Delt Fly','Seated Rear Lateral Raise'], ['Shoulders'], ['Back']],
  [['Squat','Overhead Barbell Squat','Bulgarian Split Squat'], ['Quads','Glutes'], ['Core','Adductors']],
  [['Leg Press'], ['Quads','Glutes'], ['Adductors']],
  [['Barbell Deadlift'], ['Hamstrings','Glutes','Quads'], ['Back','Core']],
  [['Weighted Leg Curl','Lying Leg Curl','Seated Leg Curl'], ['Hamstrings'], ['Calves']],
].flatMap(([names,primary,secondary])=>names.map(name=>[name,{primary,secondary}])));

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
    const group=mode==='muscle'?(overrides[s.exercise]||DEFAULT_MUSCLES[s.exercise]||'Unassigned'):s.exercise;
    const week=weekStart(s.date),key=week+'|'+group;
    if(!groups.has(key))groups.set(key,{week,group,sets:0,reps:0,repsKnown:0,volume:0,volumeKnown:0});
    const row=groups.get(key);row.sets++;
    if(present(s.reps)){row.reps+=s.reps;row.repsKnown++;}
    if(present(s.volume)){row.volume+=s.volume;row.volumeKnown++;}
  }
  return [...groups.values()].map(r=>({...r,reps:r.repsKnown?r.reps:null,volume:r.volumeKnown?r.volume:null})).sort((a,b)=>b.week.localeCompare(a.week)||b.sets-a.sets||a.group.localeCompare(b.group));
}
export function plateauSignals(sets, asOf, window=4) {
  return exerciseSummaries(sets).map(e=>{
    const bands=new Map();
    for(const s of e.rows)if(present(s.weight)&&(e.assisted?s.weight>=0:s.weight>0)&&present(s.reps)&&s.reps>0){
      if(!bands.has(s.reps))bands.set(s.reps,new Set());bands.get(s.reps).add(s.sessionId);
    }
    const target=[...bands].sort((a,b)=>b[1].size-a[1].size||a[0]-b[0])[0]?.[0];
    const history=target?matchingRepHistory(e.rows,target):[];
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
// Reviewed individually against the 49 names in the user's live history.
export const DEFAULT_VOLUME_PROFILES = {
  "Barbell Bench Press": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "estimate",
    "rationale": "Vertical barbell press; total bar weight through an assumed 0.40 m concentric rise. This defines the reference factor.",
    "assistance": false
  },
  "Barbell Deadlift": {
    "travelM": 0.6,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.25,
    "multiplier": 1.5,
    "confidence": "estimate",
    "rationale": "Floor-to-lockout bar rise estimated at 0.60 m. Adds a work-equivalent 25% body mass for the rising torso; not the entire body mass.",
    "assistance": false
  },
  "Barbell Shrug": {
    "travelM": 0.12,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.3,
    "confidence": "estimate",
    "rationale": "Short vertical scapular elevation, estimated 0.12 m; total barbell load, not two independent hand loads.",
    "assistance": false
  },
  "Bent Over Rear Delt Fly": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 2,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "estimate",
    "rationale": "Two dumbbells rise on a shoulder-abduction arc; assumed vertical load rise 0.35 m. Logged kg are per dumbbell.",
    "assistance": false
  },
  "Bicep Curl": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Dumbbell elbow flexion, assumed 0.35 m vertical rise. Uses one dumbbell per counted rep: recorded reps are total across sides. If both arms move together, change load copies to 2.",
    "assistance": false
  },
  "Bulgarian Split Squat": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 2,
    "bodyweight": 0.7,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "Split squat estimated 0.40 m load rise with two dumbbells; work-equivalent body mass 70%. Total reps already include both legs, so there is no extra side multiplier. Change load copies if using one dumbbell.",
    "assistance": false
  },
  "Cable Biceps Curl": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "Elbow flexion against a cable over an assumed 0.40 m handle travel. One loaded handle per counted rep. Assumes displayed kg mean handle resistance; verify pulley ratio.",
    "assistance": false
  },
  "Cable Chest Fly": {
    "travelM": 0.6,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.5,
    "confidence": "calibrate",
    "rationale": "Shoulder horizontal adduction over an estimated 0.60 m cable travel. Assumes logged load is the combined effective cable resistance; use 2 load copies if logging one of two simultaneously moving independent stacks.",
    "assistance": false
  },
  "Cable Crunch": {
    "travelM": 0.25,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.1,
    "multiplier": 0.625,
    "confidence": "calibrate",
    "rationale": "Kneeling trunk flexion, estimated 0.25 m cable travel; includes a small work-equivalent torso contribution (10% body mass). Verify pulley resistance and torso motion.",
    "assistance": false
  },
  "Cable Triceps Extension": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "Pushdown through estimated 0.40 m cable travel. Both hands share one rope/bar and one stack; no doubling. Assumes displayed load is effective handle resistance.",
    "assistance": false
  },
  "Calf Raise Machine": {
    "travelM": 0.1,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.95,
    "multiplier": 0.25,
    "confidence": "calibrate",
    "rationale": "Assumes standing calf machine: only about 0.10 m rise, plus 95% body mass rising on the forefoot. Change bodyweight to 0 if this is a seated machine; verify machine leverage.",
    "assistance": false
  },
  "Captain's Chair Leg Raises": {
    "travelM": 0.5,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.16,
    "multiplier": 1.25,
    "confidence": "calibrate",
    "rationale": "Supported trunk; legs rotate upward. Uses 16% work-equivalent body mass over a 0.50 m reference path, allowing for lower-limb mass and smaller leg-centre-of-mass rise. Bent knees reduce the work further.",
    "assistance": false
  },
  "Curl": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Generic elbow-flexion label: assumes 0.35 m load rise and one load per rep. Equipment and kg convention are unidentified; recorded zero kg is treated as missing resistance, not bodyweight work.",
    "assistance": false
  },
  "Decline Crunch": {
    "travelM": 0.2,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.3,
    "multiplier": 0.5,
    "confidence": "calibrate",
    "rationale": "Short trunk-flexion movement, estimated 0.20 m reference travel and 30% work-equivalent body mass. Decline angle and torso excursion need calibration.",
    "assistance": false
  },
  "Dip": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 1,
    "multiplier": 0.75,
    "confidence": "estimate",
    "rationale": "Near-whole-body vertical rise estimated 0.30 m; added load is added to body mass, assistance is subtracted.",
    "assistance": false
  },
  "Hip Abduction": {
    "travelM": 0.2,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.5,
    "confidence": "calibrate",
    "rationale": "Seated bilateral hip abduction against one stack; assumed 0.20 m effective stack/load travel. Pads act through levers/cams: displayed kg cannot establish hip torque without machine geometry.",
    "assistance": false
  },
  "Hip Adduction": {
    "travelM": 0.2,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.5,
    "confidence": "calibrate",
    "rationale": "Seated bilateral hip adduction against one stack; assumed 0.20 m effective load travel. Both legs share the stack; no doubling. Verify lever/cam ratio.",
    "assistance": false
  },
  "Incline Bench Press": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.125,
    "confidence": "estimate",
    "rationale": "Incline barbell press: total bar load with an assumed 0.45 m vertical rise; longer rise than the flat-press reference.",
    "assistance": false
  },
  "Incline Bicep Curl": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "Elbow flexion from behind the torso with estimated 0.40 m dumbbell rise. One dumbbell per counted rep because reps include both sides; change load copies to 2 for simultaneous bilateral reps.",
    "assistance": false
  },
  "Incline Dumbbell Bench Press": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 2,
    "bodyweight": 0,
    "multiplier": 1.125,
    "confidence": "estimate",
    "rationale": "Two dumbbells pressed together; each rises about 0.45 m. Multiply the per-dumbbell logged kg by 2, not the rep count.",
    "assistance": false
  },
  "Lat Pulldown": {
    "travelM": 0.55,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.375,
    "confidence": "calibrate",
    "rationale": "Shoulder adduction and elbow flexion over estimated 0.55 m cable travel. Two hands share a single bar/stack; assumes labelled load is effective bar resistance.",
    "assistance": false
  },
  "Lateral Raise": {
    "travelM": 0.55,
    "forceRatio": 1,
    "loadCopies": 2,
    "bodyweight": 0,
    "multiplier": 1.375,
    "confidence": "estimate",
    "rationale": "Two dumbbells lifted together on a long arm; estimated vertical dumbbell rise 0.55 m. Factor reflects displacement, not a claim that shoulder joint force equals dumbbell weight.",
    "assistance": false
  },
  "Leg Press": {
    "travelM": 0.5,
    "forceRatio": 0.7071,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.8839,
    "confidence": "calibrate",
    "rationale": "Assumes 45-degree plate-loaded sled, 0.50 m rail travel: gravity component sin(45 degrees) = 0.7071. Seated body stays supported. Excludes unknown sled tare/friction; horizontal or selectorized presses require a different factor.",
    "assistance": false
  },
  "Leg Press Calf Raise": {
    "travelM": 0.1,
    "forceRatio": 0.7071,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.1768,
    "confidence": "calibrate",
    "rationale": "Same assumed 45-degree sled but ankle plantarflexion moves it only about 0.10 m, not a full leg-press stroke. Body remains supported; excludes unknown sled tare/friction.",
    "assistance": false
  },
  "Leg Raise": {
    "travelM": 0.6,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.16,
    "multiplier": 1.5,
    "confidence": "calibrate",
    "rationale": "Legs rotate against gravity while the trunk is supported/hanging. Estimated 0.60 m reference travel and 16% work-equivalent body mass; knee bend and pelvis movement change this substantially.",
    "assistance": false
  },
  "Lying Ez Bar Triceps Extension": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "estimate",
    "rationale": "Lying elbow extension, estimated 0.35 m vertical EZ-bar rise. Shared bar weight is counted once.",
    "assistance": false
  },
  "Lying Leg Curl": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.75,
    "confidence": "calibrate",
    "rationale": "Knee flexion against a roller/cam, assumed effective load travel 0.30 m. Both legs share one stack; pad-force/stack ratio requires calibration.",
    "assistance": false
  },
  "Machine Chest Fly": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Pec-deck shoulder adduction: both arms share a machine stack. Assumed effective load travel 0.35 m; cam and lever geometry unknown, no free-weight equivalence claimed.",
    "assistance": false
  },
  "Machine Leg Extension": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.75,
    "confidence": "calibrate",
    "rationale": "Seated knee extension: both shins share one stack. Assumed 0.30 m effective load travel; cam/pad lever changes joint torque and needs calibration.",
    "assistance": false
  },
  "Machine T-Bar Row": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Chest-supported lever row; estimated 0.35 m effective plate rise. Logged plates are counted once, not per hand. Pivot location and plate-vs-handle lever arms are unknown.",
    "assistance": false
  },
  "One Arm Cable Lateral Raise": {
    "travelM": 0.6,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.5,
    "confidence": "calibrate",
    "rationale": "One cable handle travels an estimated 0.60 m on a shoulder-abduction arc. Total reps already include sides; no x2. Assumes effective handle resistance; verify pulley ratio.",
    "assistance": false
  },
  "Overhead Barbell Squat": {
    "travelM": 0.5,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.8,
    "multiplier": 1.25,
    "confidence": "calibrate",
    "rationale": "Squat pattern: estimated 0.50 m bar rise plus 80% work-equivalent body mass. Historical manual import maps Barbell Squat to this Garmin label; no extra overhead multiplier is assumed.",
    "assistance": false
  },
  "Overhead Cable Tricep Extension": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.125,
    "confidence": "calibrate",
    "rationale": "Overhead elbow extension over estimated 0.45 m cable travel. Both hands share one attachment/stack; verify pulley ratio.",
    "assistance": false
  },
  "Pull Up": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 1,
    "multiplier": 1.125,
    "confidence": "estimate",
    "rationale": "Near-whole-body vertical rise estimated 0.45 m. Logged kg are added weight; body mass is included once. Assistance reverses the external-load sign.",
    "assistance": false
  },
  "Push Up": {
    "travelM": 0.25,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.72,
    "multiplier": 0.625,
    "confidence": "estimate",
    "rationale": "Average supported bodyweight approximated as 72% (research reports position dependence); estimated 0.25 m upper-body rise. Added load assumes similar travel, with placement needing calibration.",
    "assistance": false
  },
  "Rear Delt Fly": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Historical loads of 40-45 kg suggest a reverse-fly machine, but the name alone cannot prove equipment. Assumes one shared stack and 0.35 m effective load travel; set 2 load copies only for simultaneous dumbbells.",
    "assistance": false
  },
  "Row": {
    "travelM": 0.5,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.25,
    "confidence": "calibrate",
    "rationale": "Generic row: assumes one combined external load through 0.50 m effective travel. No evidence for inverted/bodyweight row. Zero recorded kg is missing resistance until exercise/load is identified.",
    "assistance": false
  },
  "Seated Cable Row": {
    "travelM": 0.5,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.25,
    "confidence": "calibrate",
    "rationale": "Horizontal pull with estimated 0.50 m cable travel. A fixed direction-changing pulley does not halve resistance; assumes the stack label is effective handle resistance.",
    "assistance": false
  },
  "Seated Leg Curl": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Seated knee flexion with estimated 0.35 m effective load travel. One shared stack, supported torso; machine cam ratio must be calibrated.",
    "assistance": false
  },
  "Seated Rear Lateral Raise": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "History spans 8-50 kg, consistent with mixed dumbbell/machine conventions. Uses one combined load and 0.35 m effective travel provisionally; split/rename mixed equipment before comparing. Change load copies to 2 for simultaneous per-dumbbell logging.",
    "assistance": false
  },
  "Shrug": {
    "travelM": 0.12,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.3,
    "confidence": "calibrate",
    "rationale": "Generic shrug has only about 0.12 m vertical travel. History spans 28-60 kg with unspecified equipment; assumes combined load. Set load copies to 2 if these are two per-dumbbell loads.",
    "assistance": false
  },
  "Single Arm Cable Tricep Extension": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "One-arm elbow extension through estimated 0.40 m cable travel. Reps are total across arms, so one effective handle load per counted rep; verify pulley ratio.",
    "assistance": false
  },
  "Single Arm Preacher Curl": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.75,
    "confidence": "estimate",
    "rationale": "Supported one-arm elbow flexion, estimated 0.30 m vertical dumbbell rise. One dumbbell and total reps across sides; no side multiplier.",
    "assistance": false
  },
  "Single Leg Calf Raise": {
    "travelM": 0.1,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.95,
    "multiplier": 0.25,
    "confidence": "estimate",
    "rationale": "Standing one-leg plantarflexion: estimated 0.10 m rise of 95% body mass plus one dumbbell. Total reps include both legs; body mass and load counted once per rep.",
    "assistance": false
  },
  "Sit Up": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.3,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "Torso flexion/hip flexion: estimated 0.40 m reference travel with 30% work-equivalent body mass to account for supported lower body and smaller torso-centre-of-mass rise.",
    "assistance": false
  },
  "Squat": {
    "travelM": 0.5,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0.8,
    "multiplier": 1.25,
    "confidence": "estimate",
    "rationale": "Squat with estimated 0.50 m load travel and 80% work-equivalent body mass. A zero added load still includes rising body mass.",
    "assistance": false
  },
  "Standing Ez Bar Biceps Curl": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "estimate",
    "rationale": "Standing elbow flexion, estimated 0.35 m vertical bar rise. Total EZ-bar load, counted once despite using both arms.",
    "assistance": false
  },
  "Straight Arm Pulldown": {
    "travelM": 0.65,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.625,
    "confidence": "calibrate",
    "rationale": "Long shoulder-extension arc produces estimated 0.65 m cable travel. One shared attachment/stack; assumes labelled effective resistance, not an arbitrary bonus for a long moment arm.",
    "assistance": false
  },
  "Unknown": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "unidentified",
    "rationale": "Movement and equipment are unknown. Excluded from adjusted volume until identified; sets and reps still count.",
    "assistance": false
  },
  "Weighted Seated Calf Raise": {
    "travelM": 0.1,
    "forceRatio": 0.7071,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.1768,
    "confidence": "calibrate",
    "rationale": "Retired alias for Leg Press Calf Raise in this project; assumed 45-degree sled and 0.10 m ankle-driven travel, no rising torso.",
    "assistance": false
  },
  "Assisted Pull Up": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 1,
    "multiplier": 1.125,
    "confidence": "estimate",
    "rationale": "Pull up with estimated 0.45 m body rise. Recorded kg are assistance and are subtracted from body mass.",
    "assistance": true
  },
  "Chin Up": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 1,
    "multiplier": 1.125,
    "confidence": "estimate",
    "rationale": "Supinated vertical pull, estimated 0.45 m rise of near-whole-body mass plus added load.",
    "assistance": false
  },
  "Assisted Dip": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 1,
    "multiplier": 0.75,
    "confidence": "estimate",
    "rationale": "Assisted dip with estimated 0.30 m body rise. Recorded kg are assistance and are subtracted from body mass.",
    "assistance": true
  },
  "Fly": {
    "travelM": 0.6,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.5,
    "confidence": "calibrate",
    "rationale": "Shoulder horizontal adduction over an estimated 0.60 m cable travel. Assumes logged load is the combined effective cable resistance; use 2 load copies if logging one of two simultaneously moving independent stacks.",
    "assistance": false
  },
  "Flye": {
    "travelM": 0.35,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.875,
    "confidence": "calibrate",
    "rationale": "Pec-deck shoulder adduction: both arms share a machine stack. Assumed effective load travel 0.35 m; cam and lever geometry unknown, no free-weight equivalence claimed.",
    "assistance": false
  },
  "Triceps Extension": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "Pushdown through estimated 0.40 m cable travel. Both hands share one rope/bar and one stack; no doubling. Assumes displayed load is effective handle resistance.",
    "assistance": false
  },
  "Weighted Leg Curl": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.75,
    "confidence": "calibrate",
    "rationale": "Knee flexion against a roller/cam, assumed effective load travel 0.30 m. Both legs share one stack; pad-force/stack ratio requires calibration.",
    "assistance": false
  },
  "Weighted Leg Extensions": {
    "travelM": 0.3,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 0.75,
    "confidence": "calibrate",
    "rationale": "Seated knee extension: both shins share one stack. Assumed 0.30 m effective load travel; cam/pad lever changes joint torque and needs calibration.",
    "assistance": false
  },
  "Overhead Cable Triceps Extension": {
    "travelM": 0.45,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.125,
    "confidence": "calibrate",
    "rationale": "Overhead elbow extension over estimated 0.45 m cable travel. Both hands share one attachment/stack; verify pulley ratio.",
    "assistance": false
  },
  "Single Arm Cable Triceps Extension": {
    "travelM": 0.4,
    "forceRatio": 1,
    "loadCopies": 1,
    "bodyweight": 0,
    "multiplier": 1.0,
    "confidence": "calibrate",
    "rationale": "One-arm elbow extension through estimated 0.40 m cable travel. Reps are total across arms, so one effective handle load per counted rep; verify pulley ratio.",
    "assistance": false
  }
};
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
    const valid=present(set.weight)&&set.weight>=0&&present(set.reps)&&set.reps>=0&&!missingBodyweight&&!unreviewed&&!missingLoad;
    const load=valid?Math.max(0,(rule.assistance?-1:1)*set.weight*rule.loadCopies+(rule.bodyweight?bodyWeight*rule.bodyweight:0)):null;
    return {...set,assistance:rule.recordedAssistance,volume:valid?load*set.reps*rule.multiplier:null,missingBodyweight,missingLoad,unreviewed};
  });
}
