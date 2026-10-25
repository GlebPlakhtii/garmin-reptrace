// Read-only adapter over the exact calculation functions used by the web app.
import * as m from '../web/static/model.mjs';
import {readFileSync} from 'node:fs';

export function dashboard(data, a, today) {
  const range={from:a.from_date||'',to:a.to_date||''}, o=a.options||{};
  const raw=(data.sets||[]).filter(s=>s.exercise.trim().toLowerCase()!=='unknown').map(s=>({...s,time:s.time||s.date}));
  const all=m.recordedVolumeSets(raw,data.volumeSettings);
  const matches=s=>(!a.exercise||s.exercise===a.exercise)&&(!o.muscle_group||(data.muscleOverrides?.[s.exercise]||m.DEFAULT_MUSCLES[s.exercise]||'Unassigned')===o.muscle_group);
  const filtered=m.filterData({...data,sets:all,workouts:data.workouts||[]},range,a.source||'all');
  let sets=filtered.sets;
  sets=sets.filter(matches);
  if(o.search&&['exercises','sets','records'].includes(a.view))sets=sets.filter(s=>s.exercise.toLowerCase().includes(o.search.toLowerCase()));
  const adjusted=o.volume_mode==='adjusted'||(!['exercises','sets','strength','csv_sets','csv_recovery'].includes(a.view)&&o.volume_mode!=='recorded');
  if(adjusted)sets=m.adjustedVolumeSets(sets,data.recovery||[],data.volumeSettings);
  const compact=e=>{if(!e)return null;const {rows,history,...rest}=e;return rest;};
  const history=h=>{const {rows,...rest}=h;return rest;};
  let result={view:a.view,range,source:a.source||'all',volumeMode:adjusted?'adjusted':'recorded',
    note:adjusted?'Adjusted volume is an estimate, not measured effort or muscle stimulus.':'Recorded external load × reps; assisted resistance volume is unavailable.'},rows=[];
  const recovery=(data.recovery||[]).filter(r=>(!range.from||r.date>=range.from)&&(!range.to||r.date<=range.to));
  switch(a.view) {
    case 'overview':
      Object.assign(result,{sessions:filtered.workouts.length,sets:sets.length,reps:m.sumKnown(sets.map(s=>s.reps)),volume:m.sumKnown(sets.map(s=>s.volume)),volumeKnown:sets.filter(s=>m.present(s.volume)).length});
      rows=m.weeklyWorkouts(filtered.workouts,today,12);break;
    case 'exercises':
      rows=a.exercise?m.exerciseSummaries(sets).flatMap(e=>e.history.map(history)):m.exerciseSummaries(sets).map(compact);break;
    case 'sets': rows=sets.slice().sort((a,b)=>b.date.localeCompare(a.date)||(b.time||'').localeCompare(a.time||''));break;
    case 'workouts': rows=filtered.workouts.filter(w=>!o.search||w.name.toLowerCase().includes(o.search.toLowerCase())).sort((a,b)=>b.date.localeCompare(a.date)||(b.time||'').localeCompare(a.time||''));break;
    case 'records': rows=m.exerciseSummaries(sets).map(compact);break;
    case 'strength':
      if(!a.exercise)throw Error('Select one exact exercise for estimated 1RM.');
      rows=m.estimatedStrengthHistory(sets,a.exercise,Boolean(o.weekly),range);break;
    case 'weekly_volume':
      rows=m.weeklyVolumeHistory(sets,o.grouping||'muscle',data.muscleOverrides,range).flatMap(g=>g.history);
      rows.sort((a,b)=>b.week.localeCompare(a.week)||a.group.localeCompare(b.group));break;
    case 'muscle_map': {
      const week=o.week||m.weekStart(today);
      const summary=m.muscleWeekSummary(sets,week,data.muscleOverrides,o.include_secondary!==false);
      const full=m.adjustedVolumeSets(all.filter(s=>(a.source==='all'||!a.source||s.source===a.source)&&matches(s)),data.recovery||[],data.volumeSettings);
      const comparison=m.muscleWeekComparison(adjusted?full:all.filter(s=>(a.source==='all'||!a.source||s.source===a.source)&&matches(s)),week,{count:o.compare_weeks||1,range,asOf:today,overrides:data.muscleOverrides,includeSecondary:o.include_secondary!==false});
      const {groups,exercises,...totals}=summary;
      Object.assign(result,{totals,comparison,note:result.note+' Primary and secondary muscle contributions overlap; do not sum them as distinct sets.'});
      rows=groups;break;
    }
    case 'recovery': rows=recovery.slice().sort((a,b)=>b.date.localeCompare(a.date));result.note='Recorded and manually overridden recovery values; no causal inference.';break;
    case 'insights':
      rows=m.plateauSignals(sets,today,o.window||4);
      if(a.exercise){
        result.matchingReps=m.matchingRepHistory(sets,o.reps||5).map(history).slice(a.offset,a.offset+a.limit);
        const comparison=m.recoveryComparison(sets,recovery,a.exercise,o.reps||5,o.recovery_metric||'sleepHours',o.threshold??null);
        const {pairs,...summary}=comparison;
        result.recoveryAssociation={...summary,pairs:pairs.map(history).slice(a.offset,a.offset+a.limit),matchingPairs:pairs.length,truncated:pairs.length>a.offset+a.limit};
      }break;
    case 'goals':
      rows=[...(data.goals||[]).map(g=>({...g,archived:false})),...(data.archivedGoals||[]).map(g=>({...g,archived:true}))].map(g=>({...g,progress:m.goalProgress(g,all,data.volumeSettings)}));
      result.note='Goals use full history, matching the web Goals page; date/source filters do not change achievement.';break;
    case 'compare':
      if(!o.left_id||!o.right_id)throw Error('Provide both returned workout IDs.');
      if(![o.left_id,o.right_id].every(id=>filtered.workouts.some(w=>w.id===id)))throw Error('Workout is absent from the selected filters.');
      rows=m.compareWorkouts({sets},o.left_id,o.right_id).map(r=>({...r,left:compact(r.left),right:compact(r.right)}));break;
    case 'sync': Object.assign(result,{sync:data.sync||{},refreshedAt:data.refreshedAt,timezone:data.timezone,note:'Database refresh does not trigger Garmin collection.'});break;
    case 'preferences':
      Object.assign(result,{equipment:data.equipment,volumeSettings:data.volumeSettings,progressionRules:data.progressionRules,muscleOverrides:data.muscleOverrides,metadataRevision:data.metadataRevision,browserOnly:['theme','overview layout','unsaved browser drafts','last selected filters']});
      rows=[...new Set(raw.map(s=>s.exercise))].filter(n=>!a.exercise||n===a.exercise).map(name=>({name,...m.exerciseVolumeRule(name,data.volumeSettings)}));break;
    case 'csv_sets':
      sets=m.filterData({...data,sets:raw,workouts:data.workouts||[]},range,a.source||'all').sets.filter(matches);
      if(o.search){const ids=new Set(filtered.workouts.filter(w=>w.name.toLowerCase().includes(o.search.toLowerCase())).map(w=>w.id));sets=sets.filter(s=>ids.has(s.sessionId));}
      return {text:m.csvForSets(sets),count:sets.length};
    case 'csv_recovery': return {text:m.csvForRecovery(recovery),count:recovery.length};
    default: throw Error('Unknown dashboard view');
  }
  return {...result,matchingRows:rows.length,truncated:rows.length>a.offset+a.limit,offset:a.offset,rows:rows.slice(a.offset,a.offset+a.limit)};
}

if(process.argv[1]===new URL(import.meta.url).pathname){
  try {const {data,args,today}=JSON.parse(readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(dashboard(data,args,today)));}
  catch {process.stdout.write(JSON.stringify({error:'Dashboard calculation failed; verify the requested filters and IDs.'}));process.exitCode=1;}
}
