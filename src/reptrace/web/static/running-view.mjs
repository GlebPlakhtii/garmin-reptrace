import catalog from '../../training/running_metrics.json' with {type:'json'};
import {runningHistory,runningSummary,runningWeeks,runningTime,paceLabel,runPace,finite,metricValue,compareRunning,runningCSV,chartSegments,plotSamples} from './running.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=1)=>finite(v)?v.toLocaleString('en-GB',{maximumFractionDigits:d}):'—';
const day=v=>new Date(v+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const unit=m=>m.unit==='time'?'':m.unit==='pace'?'/km':m.unit;
const value=(row,key)=>{const m=catalog.find(m=>m.key===key)||{};return `${metricValue(row?.[key],m)}${finite(row?.[key])&&unit(m)?' '+unit(m):''}`;};
const typeName=t=>({treadmill_running:'Treadmill',trail_running:'Trail',running:'Outdoor',track_running:'Track',indoor_running:'Indoor'}[t]||String(t||'running').replaceAll('_',' '));
const choices=(attribute,items,selected,label)=>`<div class="run-choices" role="group" aria-label="${esc(label)}">${items.map(([key,text])=>`<button type="button" data-${attribute}="${esc(key)}" aria-pressed="${key===selected}" class="${key===selected?'selected':''}">${esc(text)}</button>`).join('')}</div>`;
export const runningState={view:'runs',tab:'overview',sampleIndex:0,selected:'',details:new Map(),pending:new Set(),errors:new Map(),type:'all',search:'',metric:'cadence',axis:'seconds',trend:'averagePace',compare:'',syncing:false,cancelSync:false,syncProgress:'',visible:[],requests:new Map()};
// A period import can contain many hours of sensor samples. Keep full tracks
// only for the open comparison and a few recent runs. SQLite owns the archive.
const detailLimit=4;
let onImported=()=>{};
function rememberDetail(id,data){
  runningState.details.delete(id);
  runningState.details.set(id,data);
  for(const cached of runningState.details.keys()){
    if(runningState.details.size<=detailLimit)break;
    if(cached!==runningState.selected&&cached!==runningState.compare&&cached!==id)runningState.details.delete(cached);
  }
  if(data.syncedAt&&!data.stale)onImported(id,data.summary,data.syncedAt);
}
const streams={pace:['Pace','/km'],heartRate:['Heart rate','bpm'],cadence:['Cadence','spm'],power:['Power','W'],elevation:['Elevation','m'],groundContactMs:['Ground contact time','ms'],strideLengthM:['Stride length','m'],verticalOscillationCm:['Vertical oscillation','cm'],verticalRatio:['Vertical ratio','%'],stamina:['Available stamina','%'],potentialStamina:['Potential stamina','%'],bodyBattery:['Body Battery','points'],temperature:['Sensor temperature','°C']};
const formatPoint=(key,v)=>key==='pace'?paceLabel(v):num(v,key==='strideLengthM'?2:1);
function card(label,text,note='',extra=''){return `<article class="run-stat ${extra}"><span>${esc(label)}</span><strong>${text}</strong>${note?`<small>${esc(note)}</small>`:''}</article>`;}
function section(title,description,body,extra=''){return `<section class="panel run-section ${extra}" id="run-section-${title.toLowerCase().replace(/[^a-z]+/g,'-')}"><div class="run-section-heading"><div><h2>${title}</h2>${description?`<p>${esc(description)}</p>`:''}</div></div>${body}</section>`;}
function metricGrid(row,keys){return `<dl class="run-metric-grid">${keys.map(key=>{const spec=catalog.find(m=>m.key===key);return `<div><dt>${esc(spec.label)}</dt><dd>${value(row,key)}</dd></div>`;}).join('')}</dl>`;}
function historyTrend(runs){
  const key=runningState.trend,spec=catalog.find(m=>m.key===key),ordered=[...runs].reverse(),points=ordered.filter(r=>finite(r[key]));
  const controls=choices('run-trend',[['averagePace','Pace'],['distanceKm','Distance'],['averageHR','Heart rate'],['cadence','Cadence'],['averagePower','Power'],['trainingLoad','Load']],key,'Progress metric');
  if(!points.length)return section('Progress over time','Each point is one run. Different routes, distances and conditions affect comparisons.',controls+'<p class="run-placeholder">Import run details to explore this metric.</p>');
  let min=Infinity,max=-Infinity;
  for(const r of points){min=Math.min(min,r[key]);max=Math.max(max,r[key]);}
  const span=max-min||Math.max(1,max*.1),low=Math.max(0,min-span*.15),high=max+span*.15;
  const first=Date.parse(ordered[0].time),spanMs=Date.parse(ordered.at(-1).time)-first;
  const x=r=>45+(spanMs?(Date.parse(r.time)-first)/spanMs:.5)*650,y=v=>155-(v-low)/(high-low)*125;
  let connected=false;
  const path=ordered.map(r=>{
    if(!finite(r[key])){connected=false;return '';}
    const command=connected?'L':'M';connected=true;
    return command+x(r)+','+y(r[key]);
  }).join(' ');
  const plot=`<svg viewBox="0 0 740 200" role="group" aria-label="${esc(spec.label)} by run"><line x1="45" y1="155" x2="695" y2="155" class="run-grid-line"/><text x="6" y="30">${metricValue(high,spec)}</text><text x="6" y="155">${metricValue(low,spec)}</text>${points.length>1?`<path d="${path}" class="run-trend-line"/>`:''}${points.map(r=>`<circle cx="${x(r)}" cy="${y(r[key])}" r="5" data-run-select="${esc(r.id)}" tabindex="0" role="button" aria-label="${esc(r.name)}, ${esc(day(r.date))}: ${metricValue(r[key],spec)} ${unit(spec)}"><title>${esc(day(r.date))} · ${metricValue(r[key],spec)} ${unit(spec)}</title></circle>`).join('')}<text x="45" y="190">${esc(day(ordered[0].date))}</text><text x="695" y="190" text-anchor="end">${esc(day(ordered.at(-1).date))}</text></svg>`;
  return section('Progress over time','Select a point to inspect the run. Comparisons reflect the recorded conditions.',controls+plot+(points.length<ordered.length?`<p class="run-note">${points.length} of ${ordered.length} runs recorded this metric. Gaps mark missing readings.</p>`:''),'run-trend');
}
function weekly(runs){
  const weeks=runningWeeks(runs).slice(-12),max=Math.max(1,...weeks.map(w=>w.distance||0));
  return section('Weekly distance','Last 12 recorded weeks in this period · Monday starts.',`<div class="running-bars" role="list">${weeks.map(w=>`<div class="running-week" role="listitem"><strong>${num(w.distance)} <small>km</small></strong><div class="running-bar-space"><i style="height:${finite(w.distance)?Math.max(2,w.distance/max*100):0}%"></i></div><span>${esc(day(w.date).replace(/ \d{4}$/,''))}</span><small>${w.count} ${w.count===1?'run':'runs'}</small></div>`).join('')}</div>`,'run-weekly');
}
function chart(samples,key,axis=runningState.axis){
  const [label,units]=streams[key],segments=chartSegments(samples,key,axis),points=segments.flat();
  if(!points.length)return `<div class="run-chart"><h3>${label}</h3><p class="run-placeholder">Not recorded for this run.</p></div>`;
  let minX=Infinity,maxX=-Infinity,min=Infinity,max=-Infinity;
  for(const p of points){
    minX=Math.min(minX,p[axis]);maxX=Math.max(maxX,p[axis]);
    min=Math.min(min,p[key]);max=Math.max(max,p[key]);
  }
  const pad=(max-min||Math.max(1,max*.1))*.1;
  const low=(key==='elevation'||key==='temperature')?min-pad:Math.max(0,min-pad),high=max+pad;
  const x=v=>58+(v-minX)/(maxX-minX||1)*590,y=v=>170-(v-low)/(high-low||1)*135;
  return `<div class="run-chart" data-run-chart="${key}"><div class="run-chart-heading"><h3>${label}</h3><span>${units}</span></div><svg viewBox="0 0 680 205" tabindex="0" role="img" aria-label="${label} over ${axis==='distanceKm'?'sample distance':'timer time'}. Use the sample slider below to read measurements.">${[0,.5,1].map(f=>`<line x1="58" x2="648" y1="${35+f*135}" y2="${35+f*135}" class="run-grid-line"/><text x="4" y="${39+f*135}">${formatPoint(key,high-f*(high-low))}</text>`).join('')}${segments.map(points=>plotSamples(points,key,axis,minX,maxX,590)).map(points=>points.length===1?`<circle class="run-series series-${key}" r="2" cx="${x(points[0][axis])}" cy="${y(points[0][key])}"/>`:`<path class="run-series series-${key}" d="${points.map((p,i)=>`${i?'L':'M'}${x(p[axis]).toFixed(2)},${y(p[key]).toFixed(2)}`).join(' ')}"/>`).join('')}<text x="58" y="198">${axis==='distanceKm'?num(minX,2)+' km':runningTime(minX)}</text><text x="648" y="198" text-anchor="end">${axis==='distanceKm'?num(maxX,2)+' km':runningTime(maxX)}</text></svg></div>`;
}
function zones(detail){
  const total=detail.zones.reduce((s,z)=>s+z.seconds,0),max=Math.max(1,...detail.zones.map(z=>z.seconds));
  if(!detail.zones.length)return '<p class="run-placeholder">Heart-rate zones have not been recorded.</p>';
  return `<div class="run-zones">${detail.zones.map((z,i)=>`<div class="run-zone"><span><strong>Zone ${z.zone}</strong><small>${finite(z.lowBpm)?`${z.lowBpm}${detail.zones[i+1]?.lowBpm?'–'+(detail.zones[i+1].lowBpm-1):'+'} bpm`:'Garmin zone'}</small></span><div class="run-zone-track"><i class="zone-${z.zone}" style="width:${z.seconds/max*100}%"></i></div><span>${runningTime(z.seconds)}<small>${total?num(z.seconds/total*100,0):0}%</small></span></div>`).join('')}</div><p class="run-note">Percentages use time assigned to Garmin zones, which may not cover the entire run.</p>`;
}
function effects(summary){return `<div class="run-effect-pair">${[['aerobicEffect','Aerobic'],['anaerobicEffect','Anaerobic']].map(([key,label])=>`<div><span>${label}</span><strong>${num(summary[key])}<small> /5</small></strong><div class="run-effect-track"><i style="width:${finite(summary[key])?Math.min(100,summary[key]/5*100):0}%"></i></div></div>`).join('')}</div>${metricGrid(summary,['trainingLoad','moderateMinutes','vigorousMinutes'])}<p class="run-note">${summary.primaryBenefit?'Garmin primary benefit: <strong>'+esc(summary.primaryBenefit)+'</strong>. ':''}These are Garmin estimates, not a prescription for your next workout.</p>`;}
function route(detail){
  const points=detail.samples.filter(p=>finite(p.latitude)&&finite(p.longitude));
  if(points.length<2)return '';
  const lat=points.reduce((s,p)=>s+p.latitude,0)/points.length*Math.PI/180,lon0=points[0].longitude,lat0=points[0].latitude;
  const coords=points.map(p=>[(p.longitude-lon0)*Math.cos(lat),p.latitude-lat0]);
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
  for(const [x,y] of coords){
    minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
  }
  const scale=Math.min(580/(maxX-minX),210/(maxY-minY));
  if(!Number.isFinite(scale))return '';
  return section('Recorded route','GPS trace only; no external map requests.',`<svg class="run-route" viewBox="0 0 640 270" role="img" aria-label="Recorded GPS route"><path d="${coords.map((p,i)=>`${i?'L':'M'}${30+(p[0]-minX)*scale},${240-(p[1]-minY)*scale}`).join(' ')}"/><circle cx="${30+(coords[0][0]-minX)*scale}" cy="${240-(coords[0][1]-minY)*scale}" r="5"/><text x="20" y="260">Start marked with a dot · north is up</text></svg>`);
}
function laps(detail){
  if(!detail.laps.length)return section('Laps & intervals','Recorded Garmin splits.','<p class="run-placeholder">No lap data is available for this run.</p>');
  const keys=['distanceKm','timerSeconds','averagePace','averageHR','maxHR','cadence','averagePower','strideLengthM','groundContactMs','elevationGain'];
  const included=keys.filter(key=>detail.laps.some(l=>finite(l[key])));
  return section('Laps & intervals','Timer pace comes from each Garmin lap summary. Rest laps remain visible.',`<div class="table-scroll"><table class="run-laps"><thead><tr><th>Lap</th>${included.map(k=>`<th>${esc(catalog.find(m=>m.key===k).label)}</th>`).join('')}</tr></thead><tbody>${detail.laps.map(l=>`<tr><td><strong>${l.index}</strong><small>${esc(l.intensity)}</small></td>${included.map(k=>`<td>${value(l,k)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><button class="button" data-run-export="laps">Export laps CSV</button>`);
}
function compare(summary,runs){
  const others=runs.filter(r=>r.id!==summary.id),chosen=others.find(r=>r.id===runningState.compare)||others[0];
  if(chosen)runningState.compare=chosen.id;
  if(!chosen)return section('Compare runs','Put two efforts side by side.','<p class="run-placeholder">Choose a wider date range to include another run.</p>');
  const keys=['distanceKm','averagePace','movingSeconds','averageHR','cadence','averagePower','trainingLoad','elevationGain','strideLengthM','groundContactMs'];
  const changes=compareRunning(chosen,summary,catalog).filter(m=>keys.includes(m.key));
  return section('Compare runs','Change = selected run minus comparison. Faster pace has a negative change; conditions still matter.',`<div class="run-comparison-picker" role="group" aria-label="Comparison run">${others.map(r=>`<button data-run-compare="${esc(r.id)}" aria-pressed="${r.id===chosen.id}"><small>${esc(day(r.date))}</small><strong>${esc(r.name)}</strong><span>${num(r.distanceKm,2)} km · ${paceLabel(r.averagePace??runPace(r))} /km</span></button>`).join('')}</div><div class="table-scroll"><table><thead><tr><th>Metric</th><th>${esc(day(chosen.date))}</th><th>Selected run</th><th>Change</th></tr></thead><tbody>${changes.map(m=>`<tr><td>${m.label}</td><td>${metricValue(m.left,m)} ${unit(m)}</td><td>${metricValue(m.right,m)} ${unit(m)}</td><td>${finite(m.change)?`${m.change>0?'+':m.change<0?'−':''}${metricValue(Math.abs(m.change),{...m,unit:m.unit==='pace'?'time':m.unit})} ${unit(m)}`:'—'}</td></tr>`).join('')}</tbody></table></div>${!chosen.detailsSyncedAt&&!runningState.details.has(chosen.id)?'<p class="run-note">Import the comparison run for its full metrics.</p>':''}`);
}
function detailView(run,runs){
  const detail=runningState.details.get(run.id),busy=runningState.pending.has(run.id),summary={...run,...detail?.summary};
  const tabs=[['overview','Overview'],['charts','Charts'],['metrics','Metrics'],['laps','Laps'],['compare','Compare']];
  const stamp=detail?.syncedAt?`Synced ${new Date(detail.syncedAt).toLocaleDateString('en-GB',{day:'numeric',month:'short'})}`:'From Garmin Connect';
  const hero=`<div class="run-hero"><div class="run-hero-top"><div><div class="run-kicker"><span class="run-type-badge">${esc(typeName(run.type))}</span><span>${esc(day(run.date))}</span></div><h2>${esc(summary.name)}</h2></div><div class="run-hero-actions">${run.url?`<a href="${esc(run.url)}" target="_blank" rel="noreferrer" aria-label="Open this run in Garmin">Garmin ↗</a>`:''}<button data-run-refresh aria-label="Refresh run details" ${busy?'disabled':''}>${busy?'Syncing…':'↻ Refresh'}</button></div></div><div class="run-hero-numbers">${[['distanceKm','Distance'],['averagePace','Average pace'],['timerSeconds','Time'],['averageHR','Avg. heart rate']].map(([key,label],i)=>{const spec=catalog.find(m=>m.key===key);return `<div class="${i===0?'primary':''}"><span>${label}</span><strong>${metricValue(summary[key],spec)}<small>${finite(summary[key])?unit(spec):''}</small></strong></div>`;}).join('')}</div><div class="run-hero-meta"><span>${summary.primaryBenefit?esc(summary.primaryBenefit):'Recorded effort'}${finite(summary.trainingLoad)?' · '+num(summary.trainingLoad,0)+' exercise load':''}</span><span>${stamp}</span></div></div>`;
  const navigation=`<div class="run-analysis-tabs" role="tablist" aria-label="Run analysis">${tabs.map(([key,label])=>`<button role="tab" id="run-tab-${key}" data-run-tab="${key}" aria-selected="${key===runningState.tab}" aria-controls="run-analysis-panel" tabindex="${key===runningState.tab?0:-1}">${label}${key==='laps'&&detail?.laps.length?`<small>${detail.laps.length}</small>`:''}</button>`).join('')}</div>`;
  const warning=runningState.errors.get(run.id)||detail?.warning||(detail?.partial?'Some detail could not be refreshed. Available measurements are shown.':'');
  let body=warning?`<div class="run-warning" role="status"><span>${esc(warning)}</span><button data-run-refresh>Retry</button></div>`:'';
  if(!detail)body+=`<div class="run-loading" role="status"><span class="run-loading-dot"></span><h3>${busy?'Bringing your run into focus':'Run details unavailable'}</h3><p>${busy?'Loading charts, laps and running dynamics.':'Refresh this run to try again.'}</p></div>`;
  else {
    const available=Object.keys(streams).filter(key=>detail.samples.some(row=>finite(row[key])));
    if(!available.includes(runningState.metric))runningState.metric=available[0]||'pace';
    const dataNote=detail.notes?.length?`<details class="run-data-disclosure"><summary>About this run’s data <span>${detail.notes.length}</span></summary>${detail.notes.map(n=>`<p>${esc(n)}</p>`).join('')}</details>`:'';
    if(runningState.tab==='overview'){
      body+=`<div class="run-overview-plot">${section('The effort','Pace and heart rate across your run.',`<div class="run-chart-grid">${chart(detail.samples,'pace','seconds')}${chart(detail.samples,'heartRate','seconds')}</div><button class="run-inline-action" data-run-tab="charts">Explore interactive charts <span>↗</span></button>`,'run-effort')}${section('Training impact',summary.primaryBenefit||'Garmin training effect',effects(summary),'run-impact')}</div><div class="run-overview-bottom">${section('Heart-rate zones','Time spent in your Garmin zones.',zones(detail))}${section('Running form','A snapshot of your stride.',metricGrid(summary,['cadence','strideLengthM','groundContactMs','verticalRatio'])+`<button class="run-inline-action" data-run-tab="metrics">All running metrics <span>↗</span></button>`)}</div>`+dataNote;
    } else if(runningState.tab==='charts'){
      const active=runningState.metric,index=Math.min(runningState.sampleIndex,Math.max(0,detail.samples.length-1));
      body+=section('Inside the run','Choose a signal. Inspect the original recorded samples.',choices('run-metric',available.map(k=>[k,streams[k][0]]),active,'Chart metric')+`<div class="run-chart-topline">${choices('run-axis',[['seconds','Time'],['distanceKm','Distance']],runningState.axis,'Chart horizontal axis')}<span>${detail.samples.length.toLocaleString()} samples${detail.sourceSampleCount>detail.samples.length?' · reduced by Garmin':''}</span></div>`+chart(detail.samples,active)+`<div class="run-inspector"><label for="run-sample-slider">Inspect the run</label><input id="run-sample-slider" data-run-sample type="range" min="0" max="${Math.max(0,detail.samples.length-1)}" value="${index}" aria-label="Inspect recorded running sample"><output id="run-sample-values" class="run-sample-values" aria-live="polite">${sampleReadout(detail.samples[index])}</output></div>`,'run-explorer')+dataNote+route(detail);
    } else if(runningState.tab==='metrics'){
      const groups=['Running dynamics','Power','Stamina','Heart & energy','Elevation & environment','Overview','Training effect'];
      body+=`<div class="run-metrics-sections">${groups.map(group=>{const keys=catalog.filter(m=>m.group===group);const recorded=keys.filter(m=>finite(summary[m.key]));return section(group,`${recorded.length} of ${keys.length} metrics recorded`,recorded.length?metricGrid(summary,keys.map(m=>m.key)):'<p class="run-placeholder">Not recorded for this activity.</p>');}).join('')}</div>`+dataNote;
    } else if(runningState.tab==='laps')body+=lapProfile(detail)+laps(detail)+dataNote;
    else if(runningState.tab==='compare')body+=compare(summary,runs);
  }
  return hero+navigation+`<div class="run-analysis-body" id="run-analysis-panel" role="tabpanel" aria-labelledby="run-tab-${runningState.tab}">${body}</div>`;
}
function lapProfile(detail){
  const laps=detail.laps.filter(l=>finite(l.averagePace)),max=Math.max(1,...laps.map(l=>l.averagePace));
  if(!laps.length)return '';
  return section('Lap rhythm','Pace for each recorded lap. Lower is faster.',`<div class="run-lap-profile">${laps.map(l=>`<div><strong>${paceLabel(l.averagePace)}</strong><div><i style="height:${l.averagePace/max*100}%"></i></div><span>${l.index}</span></div>`).join('')}</div>`);
}
function sampleReadout(sample){if(!sample)return '';return `<strong>${runningTime(sample.seconds)} · ${num(sample.distanceKm,2)} km</strong>${Object.keys(streams).filter(k=>finite(sample[k])).map(k=>`<span>${streams[k][0]} <b>${formatPoint(k,sample[k])} ${streams[k][1]}</b></span>`).join('')}`;}
export function renderRunningDashboard(records,range){
  for(const run of records){
    const cached=runningState.details.get(run.id);
    if(cached&&run.detailsSyncedAt&&(!cached.syncedAt||cached.syncedAt<run.detailsSyncedAt)){
      runningState.details.delete(run.id);
      runningState.errors.delete(run.id);
    }
  }
  const enriched=records.map(r=>({...r,...runningState.details.get(r.id)?.summary}));
  const filtered=runningHistory(enriched,range),types=[...new Set(records.map(r=>r.type))];
  const runs=filtered.filter(r=>(runningState.type==='all'||r.type===runningState.type)&&(!runningState.search||r.name.toLowerCase().includes(runningState.search.toLowerCase())));
  runningState.visible=runs;
  if(!runs.some(r=>r.id===runningState.selected))runningState.selected=runs[0]?.id||'';
  const tools=`<div class="run-workspace-bar">${choices('run-view',[['runs','Runs'],['progress','Progress']],runningState.view,'Running view')}<div class="run-workspace-actions"><button data-run-export="history" ${!runs.length?'disabled':''}>↓ Export CSV</button><button data-run-sync-all ${!runs.length?'disabled':''}>${runningState.syncing?(runningState.cancelSync?'Stopping…':'Stop sync'):'↻ Sync period'}</button></div></div>${runningState.syncProgress?`<p class="run-sync-status" role="status">${esc(runningState.syncProgress)}</p>`:''}`;
  const search=`<label class="run-search"><span class="sr-only">Find a run</span><input type="search" data-run-search value="${esc(runningState.search)}" placeholder="Search runs…"></label>`;
  const typeControls=types.length>1?choices('run-type',[['all','All'],...types.map(t=>[t,typeName(t)])],runningState.type,'Run type'):'';
  if(!runs.length)return `<div class="running-view">${tools}<div class="run-empty-filters">${search}${typeControls}</div>${section(records.length?'No runs match these filters':'Your running history starts here','Choose a wider range, or save and sync a run in Garmin.',`<button class="button" data-run-reset>Reset running filters</button><a class="button" href="#sync">Check Garmin sync</a>`)}</div>`;
  const totals=runningSummary(runs);
  const list=`<aside class="run-list"><div class="run-list-heading"><div><h2>Activity log</h2><span>${runs.length} runs</span></div>${search}${typeControls}</div><div class="run-list-items">${runs.map(r=>`<button class="run-history-card ${r.id===runningState.selected?'selected':''}" data-run-select="${esc(r.id)}" aria-pressed="${r.id===runningState.selected}"><span>${esc(day(r.date))}<small>${esc(typeName(r.type))}</small></span><strong>${esc(r.name)}</strong><div><b>${num(r.distanceKm,2)} <small>km</small></b><span>${paceLabel(r.averagePace??runPace(r))} <small>/km</small></span></div></button>`).join('')}</div><div class="run-list-footer"><span>IN THIS PERIOD</span><strong>${num(totals.distance,2)} <small>km</small><i> / </i>${runs.length} <small>runs</small></strong></div></aside>`;
  if(runningState.view==='progress'){
    const longest=runs.filter(r=>finite(r.distanceKm)).sort((a,b)=>b.distanceKm-a.distanceKm)[0];
    const stats=`<div class="run-progress-stats">${card('Distance',num(totals.distance,2)+' <small>km</small>',`${totals.distanceCount} runs recorded`)}${card('Moving time',runningTime(totals.moving),`${totals.movingCount} runs recorded`)}${card('Moving pace',paceLabel(totals.pace)+' <small>/km</small>','Distance weighted')}${card('Longest run',longest?num(longest.distanceKm,2)+' <small>km</small>':'—',longest?day(longest.date):'')}</div>`;
    return `<div class="running-view">${tools}<div class="run-progress-filters">${typeControls}${search}</div>${stats}<div class="run-progress-charts">${historyTrend(runs)}${weekly(runs)}</div><p class="run-note">Select a point to open the run. Totals use recorded values only.</p></div>`;
  }
  return `<div class="running-view">${tools}<div class="run-workspace">${list}<div class="run-detail" id="run-detail">${detailView(runs.find(r=>r.id===runningState.selected),runs)}</div></div></div>`;
}
function loadOne(id,render,refresh=false){
  const active=runningState.requests.get(id);
  if(active){
    if(refresh&&!active.refresh)return active.task.then(()=>loadOne(id,render,true));
    return active.task;
  }
  const task=(async()=>{
  runningState.pending.add(id);runningState.errors.delete(id);render();
  try{
    const response=await fetch('/api/running',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,refresh}),signal:AbortSignal.timeout(90000)});
    const data=await response.json();if(!response.ok)throw Error(data.error||'Running detail is unavailable.');
    rememberDetail(id,data);
    return data.stale||data.warning?'failed':data.partial?'partial':'imported';
  }catch(error){runningState.errors.set(id,error.name==='TimeoutError'?'Garmin detail request timed out. Retry to read the imported result.':error.message);return 'failed';}
  finally{runningState.pending.delete(id);runningState.requests.delete(id);render();}
  })();
  runningState.requests.set(id,{task,refresh});return task;
}
export function ensureRunningDetail(render){
  if(runningState.view!=='runs')return;
  const ids=[runningState.selected];
  if(runningState.tab==='compare')ids.push(runningState.compare);
  for(const id of new Set(ids))if(id&&!runningState.details.has(id)&&!runningState.pending.has(id)&&!runningState.errors.has(id))queueMicrotask(()=>loadOne(id,render));
}
export function installRunning({render,updateSummary}){
  onImported=updateSummary||(()=>{});
  document.addEventListener('keydown',event=>{if(event.target.matches('[role=tab][data-run-tab]')&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const tabs=[...document.querySelectorAll('[role=tab][data-run-tab]')],i=tabs.indexOf(event.target),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(i+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;const key=tabs[next].dataset.runTab;runningState.tab=key;render();document.getElementById('run-tab-'+key)?.focus();return;}if(event.target.matches('circle[data-run-select]')&&['Enter',' '].includes(event.key)){event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
  document.addEventListener('click',async event=>{
    const controls={'runTab':'tab','runView':'view','runType':'type','runTrend':'trend','runMetric':'metric','runAxis':'axis','runCompare':'compare'};
    for(const [attribute,key] of Object.entries(controls)){
      const selector='[data-'+attribute.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())+']';
      const button=event.target.closest(selector);
      if(button){runningState[key]=button.dataset[attribute];render();return;}
    }
    const calendarRun=event.target.closest('[data-calendar-run]');
    if(calendarRun){
      Object.assign(runningState,{selected:calendarRun.dataset.calendarRun,view:'runs',tab:'overview',type:'all',search:'',sampleIndex:0});
      location.hash='running';
      return;
    }
    const select=event.target.closest('[data-run-select]');
    if(select){runningState.selected=select.dataset.runSelect;runningState.view='runs';runningState.sampleIndex=0;render();return;}
    if(event.target.closest('[data-run-refresh]')){await loadOne(runningState.selected,render,true);return;}
    if(event.target.closest('[data-run-reset]')){runningState.type='all';runningState.search='';document.querySelector('[data-range="all"]')?.click();render();return;}
    const exportButton=event.target.closest('[data-run-export]');
    if(exportButton){const laps=exportButton.dataset.runExport==='laps',detail=runningState.details.get(runningState.selected),rows=laps?(detail?.laps||[]).map(l=>({...l,date:detail.summary.date,name:'Lap '+l.index,type:l.intensity})):runningState.visible;
      const url=URL.createObjectURL(new Blob([runningCSV(rows,catalog)],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=laps?'running-laps.csv':'running-history.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
    if(event.target.closest('[data-run-sync-all]')){
      if(runningState.syncing){runningState.cancelSync=true;runningState.syncProgress='Stopping after the current run…';render();return;}
      const ids=runningState.visible.map(r=>r.id);runningState.syncing=true;runningState.cancelSync=false;
      const counts={imported:0,partial:0,failed:0};
      let attempted=0;
      for(const id of ids){
        if(runningState.cancelSync)break;
        runningState.syncProgress=`Importing ${++attempted} of ${ids.length} runs…`;
        counts[await loadOne(id,render,true)]++;
      }
      runningState.syncing=false;
      runningState.syncProgress=`${counts.imported} imported · ${counts.partial} partial · ${counts.failed} failed`+(attempted<ids.length?` · ${ids.length-attempted} unprocessed`:'');
      render();
    }
  });
  document.addEventListener('input',event=>{if(event.target.matches('[data-run-search]')){runningState.search=event.target.value;render();return;}if(event.target.matches('[data-run-sample]')){runningState.sampleIndex=Number(event.target.value);const sample=runningState.details.get(runningState.selected)?.samples[runningState.sampleIndex];const output=document.getElementById('run-sample-values');if(output)output.innerHTML=sampleReadout(sample);}});
}
