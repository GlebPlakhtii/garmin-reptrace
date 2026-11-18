import {sumKnown, weekStart} from './model.mjs';

const known = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
export function runningHistory(runs = [], {from = '', to = ''} = {}) {
  return runs.filter(run => (!from || run.date >= from) && (!to || run.date <= to))
    .sort((a, b) => b.time.localeCompare(a.time));
}
export function runPace(run) {
  return known(run.distanceKm) && run.distanceKm > 0 && known(run.movingSeconds) && run.movingSeconds > 0
    ? run.movingSeconds / run.distanceKm : null;
}
export function runningSummary(runs) {
  const paired = runs.filter(run => runPace(run) !== null);
  return {
    count: runs.length,
    distance: sumKnown(runs.map(run => run.distanceKm)),
    moving: sumKnown(runs.map(run => run.movingSeconds)),
    pace: paired.length ? sumKnown(paired.map(run => run.movingSeconds)) / sumKnown(paired.map(run => run.distanceKm)) : null,
    distanceCount: runs.filter(run => known(run.distanceKm)).length,
    movingCount: runs.filter(run => known(run.movingSeconds)).length,
    paceCount: paired.length,
  };
}
export function runningWeeks(runs) {
  const weeks = new Map();
  for (const run of runs) {
    const week = weekStart(run.date);
    if (!weeks.has(week)) weeks.set(week, []);
    weeks.get(week).push(run);
  }
  return [...weeks].sort(([a], [b]) => a.localeCompare(b)).map(([date, entries]) => ({date, ...runningSummary(entries)}));
}
export function runningTime(seconds) {
  if (!known(seconds)) return '—';
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600), minutes = Math.floor(rounded / 60) % 60;
  const parts = hours ? [hours, String(minutes).padStart(2, '0')] : [minutes];
  return [...parts, String(rounded % 60).padStart(2, '0')].join(':');
}
export function paceLabel(seconds) {
  return known(seconds) && seconds > 0 ? `${Math.floor(Math.round(seconds) / 60)}:${String(Math.round(seconds) % 60).padStart(2, '0')}` : '—';
}

export const finite = value => typeof value === 'number' && Number.isFinite(value);
export function metricValue(value, spec = {}) {
  if (!finite(value)) return '—';
  if (spec.unit === 'time') return runningTime(value);
  if (spec.unit === 'pace') return paceLabel(value);
  return new Intl.NumberFormat('en-GB', {maximumFractionDigits:spec.digits ?? 0}).format(value);
}
export function compareRunning(left, right, catalog) {
  return catalog.filter(m=>finite(left[m.key])||finite(right[m.key])).map(m=>({...m,left:left[m.key],right:right[m.key],change:finite(left[m.key])&&finite(right[m.key])?right[m.key]-left[m.key]:null}));
}
export function runningCSV(rows, catalog) {
  const cell = value => {
    let text = String(value ?? '');
    if (typeof value === 'string' && /^\s*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  return [['Date','Run','Type',...catalog.map(m=>m.label+(m.unit?' ('+(m.unit==='time'?'seconds':m.unit==='pace'?'seconds/km':m.unit)+')':''))],...rows.map(r=>[r.date,r.name,r.type,...catalog.map(m=>r[m.key]??'')])].map(row=>row.map(cell).join(',')).join('\r\n');
}
export function chartSegments(samples, key, axis='seconds') {
  const segments=[];let segment=[];
  for (const row of samples) {
    if (!finite(row[key]) || !finite(row[axis])) {if(segment.length)segments.push(segment);segment=[];continue;}
    if(segment.length && (row[axis]<segment.at(-1)[axis] || (row.seconds-segment.at(-1).seconds)>60)){segments.push(segment);segment=[];}
    segment.push(row);
  }
  if(segment.length)segments.push(segment);
  return segments;
}

// Preserve extrema and time order within each horizontal pixel of a dense
// series. Segment boundaries are handled by the caller, so gaps stay visible.
export function plotSamples(points,key,axis,minimum,maximum,pixels) {
  if(points.length<=pixels*2 || maximum<=minimum)return points;
  const result=[points[0]];
  let bucket=-1,low=0,high=0;
  function finish(){
    for(const index of [Math.min(low,high),Math.max(low,high)]){
      if(result.at(-1)!==points[index])result.push(points[index]);
    }
  }
  for(let i=0;i<points.length;i++){
    const column=Math.floor((points[i][axis]-minimum)/(maximum-minimum)*pixels);
    if(column!==bucket){
      if(bucket>=0)finish();
      bucket=column;low=i;high=i;
    }else{
      if(points[i][key]<points[low][key])low=i;
      if(points[i][key]>points[high][key])high=i;
    }
  }
  finish();
  if(result.at(-1)!==points.at(-1))result.push(points.at(-1));
  return result;
}
