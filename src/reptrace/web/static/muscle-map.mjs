import {weekStart,shiftDay,MUSCLE_GROUPS,muscleColor,exerciseColor} from './model.mjs';
// Original stylized SVG artwork. Regions remain real keyboard-accessible controls.
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=value=>typeof value==='number'&&Number.isFinite(value)?new Intl.NumberFormat('en-GB',{maximumFractionDigits:1}).format(value):'—';
const day=value=>new Date(value+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const silhouette='M99 59 C91 54 88 43 89 29 C89 11 98 5 110 5 C122 5 131 11 131 29 C132 43 129 54 121 59 L122.77 70 C135.36 76 157.94 78 173.07 90 C185.48 104 189.82 124 192.71 142 L196.63 174 L204 212 L210.72 233 L217.47 248 L216.54 259 L210.85 263 L203.81 255 L198.45 239 L187.7 220 L172.9 198 L165.88 172 L156.94 147 L149.27 137 C143.69 154 139.97 175 140.74 195 L152.24 221 C160.38 240 163.02 259 159.56 279 L147.7 325 C147.11 341 155.25 355 152.31 376 L138.27 423 L139.87 447 L152.23 458 Q154.29 465 143.99 467 L123.39 467 Q115.15 466 117.21 454 L119.29 429 L116.73 390 L119.03 354 L112.16 325 L111.18 283 L110 262 L108.82 283 L107.84 325 L100.97 354 L103.27 390 L100.71 429 L102.79 454 Q104.85 466 96.61 467 L76.01 467 Q65.71 465 67.77 458 L80.13 447 L81.73 423 L67.69 376 C64.75 355 72.89 341 72.3 325 L60.44 279 C56.98 259 59.62 240 67.76 221 L79.26 195 C80.03 175 76.31 154 70.73 137 L63.06 147 L54.12 172 L47.1 198 L32.3 220 L21.55 239 L16.19 255 L9.15 263 L3.46 259 L2.53 248 L9.28 233 L16 212 L23.37 174 L27.29 142 C30.18 124 34.52 104 46.93 90 C62.05 78 84.64 76 97.23 70 Z';
// Paths for the left half; mirrored around the centre line for bilateral regions.
const anatomy={
  front:{
    Shoulders:['M70 82 C49 79 34 97 33 122 C43 117 57 108 67 96 Z'],
    Chest:['M75 84 C83 80 101 83 107 91 L107 119 C105 135 78 138 66 121 C61 112 64 96 75 84 Z'],
    Biceps:['M56 119 C44 120 34 137 31 155 C28 170 35 177 43 165 C52 153 60 131 56 119 Z'],
    Triceps:['M32 130 C25 143 23 164 26 179 L31 174 C28 160 34 145 36 137 Z'],
    Core:[
      'M93 138 Q99 134 107 137 L107 154 Q99 157 91 153 Z',
      'M92 158 Q99 156 107 159 L107 174 Q99 177 92 173 Z',
      'M93 179 Q100 177 107 179 L107 194 Q101 197 94 193 Z',
      'M95 199 Q101 197 107 199 L106 220 Q98 215 95 207 Z',
      'M73 133 Q78 135 87 143 L87 158 Q78 152 73 143 Z',
      'M76 151 L87 161 L88 178 Q78 169 76 160 Z',
      'M79 173 L89 182 L92 203 L100 220 Q85 212 81 194 Z'],
    Quads:[
      'M74 228 C64 237 59 259 65 284 C67 299 73 314 78 320 C74 293 80 255 84 236 Z',
      'M85 229 C96 239 98 262 94 284 C92 297 87 307 82 313 C77 288 79 251 85 229 Z',
      'M97 283 C102 299 98 320 90 326 C83 322 87 306 97 283 Z'],
    Adductors:['M94 229 Q104 230 108 246 L105 282 L101 300 Q101 258 94 229 Z'],
  },
  back:{
    Shoulders:['M72 82 C52 79 37 94 33 120 Q50 119 65 103 Z'],
    Back:[
      'M99 61 L107 70 L107 119 Q93 98 72 94 Q94 82 99 61 Z',
      'M72 101 Q93 105 106 129 L104 141 Q81 134 65 119 Z',
      'M65 125 Q81 137 103 146 L102 182 L90 207 Q80 190 77 166 Q74 140 65 125 Z',
      'M105 151 L107 217 L95 214 Q103 193 105 151 Z'],
    Triceps:[
      'M56 123 C44 123 33 138 30 156 Q27 171 34 173 Q49 158 56 123 Z',
      'M56 135 Q54 155 43 172 L37 178 Q40 156 56 135 Z'],
    Glutes:['M80 218 C89 211 101 215 107 229 L107 251 C98 264 79 267 67 254 C66 239 71 225 80 218 Z'],
    Hamstrings:[
      'M68 263 Q76 269 83 267 C87 287 82 312 77 322 Q65 308 65 281 Z',
      'M87 268 Q97 266 103 261 Q102 296 95 321 Q90 331 84 322 Q91 294 87 268 Z'],
    Calves:[
      'M79 341 C67 352 70 375 80 395 Q87 399 87 382 L88 345 Z',
      'M91 341 Q101 337 101 355 C102 372 94 392 87 410 L88 379 Z'],
    Adductors:['M104 270 L108 267 L107 307 L101 324 L98 315 Z'],
  },
};
// Preserve each curve's commands while rounding out the belly of each lobe.
// Tips stay anchored; left/right pieces deform in their own local coordinates.
export function flexMusclePath(path){
  const values=path.match(/-?\d+(?:\.\d+)?/g).map(Number);
  const xs=values.filter((_,i)=>i%2===0),ys=values.filter((_,i)=>i%2===1);
  const left=Math.min(...xs),top=Math.min(...ys),width=Math.max(...xs)-left,height=Math.max(...ys)-top;
  const cx=left+width/2,cy=top+height/2;
  let index=0;
  return path.replace(/-?\d+(?:\.\d+)?/g,()=>{
    const pair=index-index%2,x=values[pair],y=values[pair+1];
    const value=index++%2===0
      ?Math.min(109,cx+(x-cx)*(1+.24*Math.sin(Math.PI*(y-top)/(height||1))))
      :cy+(y-cy)*(1+.08*Math.sin(Math.PI*(x-left)/(width||1)));
    return String(Number(value.toFixed(3)));
  });
}
function muscleShape(path,selected){
  const flexed=flexMusclePath(path);
  return `data-muscle-rest="${path}" data-muscle-flexed="${flexed}" d="${selected?flexed:path}"`;
}
// Fibres follow the long axis of each lobe and are clipped to its exact outline.
// These decorative paths never create extra hit targets or extra set credits.
function muscleFibres(path,id,name,selected){
  const values=path.match(/-?\d+(?:\.\d+)?/g).map(Number);
  const xs=values.filter((_,i)=>i%2===0),ys=values.filter((_,i)=>i%2===1);
  const x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;
  const across=name==='Chest'||name==='Glutes'||(name==='Back'&&h<65);
  const lines=Array.from({length:18},(_,i)=>{
    const t=(i+1)/19;
    return across
      ? `M${x-3} ${y+h*t} Q${x+w*.5} ${y+h*t-h*.28} ${x+w+3} ${y+h*t+h*.16}`
      : `M${x+w*t} ${y-3} Q${x+w*t-w*.3} ${y+h*.5} ${x+w*t+w*.12} ${y+h+3}`;
  }).join(' ');
  return `<defs><clipPath id="${id}"><path ${muscleShape(path,selected)}/></clipPath></defs><g class="muscle-fibres" clip-path="url(#${id})" aria-hidden="true"><path d="${lines}"/><path d="${lines}" transform="translate(.55 .6)"/></g>`;
}
// Curved footprints bridge the internal seams without adding rectangular targets.
// A single interaction layer sits above pointer-inert artwork for uniform hover.
const groupContours={
  front:{
    Core:'M72 133 Q81 135 91 137 Q101 133 110 137 L110 220 Q95 222 81 201 Q77 173 72 133 Z',
    Quads:'M74 228 Q88 223 97 240 Q103 268 100 303 Q99 320 90 328 Q79 326 73 313 Q60 284 62 262 Q64 240 74 228 Z',
  },
  back:{
    Back:'M99 61 L110 70 L110 219 L90 216 Q78 192 75 163 Q72 139 64 123 L71 94 Q92 80 99 61 Z',
    Triceps:'M56 123 Q39 122 30 148 Q23 166 35 178 Q53 166 56 123 Z',
    Hamstrings:'M68 262 Q86 270 103 261 Q105 293 97 320 Q91 334 77 323 Q64 310 64 281 Z',
    Calves:'M79 341 Q92 333 100 342 Q107 368 94 393 L87 411 Q79 400 73 382 Q67 357 79 341 Z',
  },
};
function areaPaths(side,paths,name,attributes,bridgeSeams=false,selected=false){
  const contours=bridgeSeams&&groupContours[side][name]?[groupContours[side][name]]:paths;
  return contours.map(path=>{
    const geometry=bridgeSeams?`d="${path}"`:muscleShape(path,selected);
    return `<path ${geometry} ${attributes}/><path ${geometry} transform="translate(220 0) scale(-1 1)" ${attributes}/>`;
  }).join('');
}
const roleClass=group=>group.primary?'primary':group.secondary?'secondary':'inactive';
export function muscleChange(group,baseline,available){
  if(!available||!baseline)return {status:'unknown',label:'Not enough history'};
  const delta=group.sets-baseline.sets;
  if(!group.sets&&!baseline.sets)return {status:'no-work',label:'No sets in either period'};
  if(Math.abs(delta)<1e-9)return {status:'same',label:`Same sets: ${number(group.sets)}`};
  return {status:delta>0?'more':'less',label:`${number(Math.abs(delta))} ${delta>0?'more':'fewer'} sets: ${number(group.sets)} vs ${number(baseline.sets)}`};
}
function bodyMaterials(id){
  const tones={...Object.fromEntries(MUSCLE_GROUPS.map((name,i)=>[name,'--series-'+i])),primary:'--map-primary',secondary:'--map-secondary',inactive:'--map-idle','change-more':'--change-more','change-less':'--change-less','change-same':'--change-same','change-no-work':'--change-no-work','change-unknown':'--change-unknown'};
  return `<defs><linearGradient id="${id}-bevel" x1="0" y1="0" x2="1" y2=".8"><stop stop-color="#e1f7ff" stop-opacity=".45"/><stop offset=".35" stop-color="#b7e7ff" stop-opacity=".12"/><stop offset=".65" stop-color="#020913" stop-opacity=".15"/><stop offset="1" stop-color="#010611" stop-opacity=".85"/></linearGradient><radialGradient id="${id}-sheen" cx="28%" cy="18%" r="75%"><stop stop-color="#fff" stop-opacity=".25"/><stop offset=".3" stop-color="#d6eeff" stop-opacity=".13"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000916" stop-opacity=".25"/></radialGradient><linearGradient id="${id}-shell" x1="0" x2="1"><stop stop-color="#101c29"/><stop offset=".27" stop-color="#374b60"/><stop offset=".48" stop-color="#6c8192"/><stop offset=".57" stop-color="#354a60"/><stop offset=".84" stop-color="#182837"/><stop offset="1" stop-color="#426177"/></linearGradient><radialGradient id="${id}-head" cx="35%" cy="23%" r="80%"><stop stop-color="#a2b9c9"/><stop offset=".35" stop-color="#506b80"/><stop offset=".75" stop-color="#182b3e"/><stop offset="1" stop-color="#0b1421"/></radialGradient><radialGradient id="${id}-halo"><stop stop-color="#61bbdf" stop-opacity=".17"/><stop offset="1" stop-color="#61bbdf" stop-opacity="0"/></radialGradient>${Object.entries(tones).map(([name,variable])=>`<radialGradient id="${id}-${name}" cx="30%" cy="22%" r="78%" gradientTransform="translate(0 -.07) scale(1 1.1)"><stop style="stop-color:color-mix(in srgb,var(${variable},${MUSCLE_GROUPS.includes(name)?muscleColor(name):'var(--map-idle)'}) 48%,white)"/><stop offset=".25" style="stop-color:var(${variable},${MUSCLE_GROUPS.includes(name)?muscleColor(name):'var(--map-idle)'})"/><stop offset=".7" style="stop-color:color-mix(in srgb,var(${variable},${MUSCLE_GROUPS.includes(name)?muscleColor(name):'var(--map-idle)'}) 52%,#07111e)"/><stop offset="1" style="stop-color:color-mix(in srgb,var(${variable},${MUSCLE_GROUPS.includes(name)?muscleColor(name):'var(--map-idle)'}) 25%,#030812)"/></radialGradient>`).join('')}</defs>`;
}
function figure(side,groups,selected,comparison=null,week=''){
  const lookup=new Map(groups.map(group=>[group.name,group])),material=`body-${comparison?'change':'work'}-${side}`;
  const drawings=[];
  const controls=Object.entries(anatomy[side]).map(([name,paths])=>{
    const group=lookup.get(name),change=comparison?muscleChange(group,comparison.groups.find(g=>g.name===name),comparison.available):null,label=change?`${name}: ${change.label}`:`${name}: ${group.primary} primary sets, ${group.secondary} secondary sets`;
    const tone=change?`change-${change.status}`:roleClass(group);
    const shapes=paths.map((path,index)=>[false,true].map(mirrored=>`<g${mirrored?' transform="translate(220 0) scale(-1 1)"':''}><g class="body-muscle-piece"><path class="muscle-surface" style="fill:url(#${material}-${!comparison&&group.sets?name:tone});opacity:${!comparison&&!group.primary&&group.secondary?.65:1}" ${muscleShape(path,name===selected)}/><path class="muscle-sheen" aria-hidden="true" style="fill:url(#${material}-sheen);stroke:url(#${material}-bevel)" ${muscleShape(path,name===selected)}/><path class="muscle-hover-wash" aria-hidden="true" ${muscleShape(path,name===selected)}/><path class="muscle-selection-glow" aria-hidden="true" ${muscleShape(path,name===selected)}/>${muscleFibres(path,`${material}-${name}-${index}-${mirrored?1:0}`,name,name===selected)}</g></g>`).join('')).join('');
    drawings.push(`<g class="body-muscle-art ${tone}" data-body-muscle="${escape(name)}" data-body-state="${escape([tone,group.primary,group.secondary,change?.label||''].join('|'))}" data-body-selected="${name===selected}" aria-hidden="true">${shapes}</g>`);
    return `<g id="map-${comparison?'change-':''}${side}-${name}" class="body-muscle ${change?`change-${change.status}`:roleClass(group)} ${name===selected?'selected':''}" role="button" tabindex="0" aria-pressed="${name===selected}" aria-label="${label}" data-map-muscle="${name}"><title>${label}</title>${areaPaths(side,paths,name,'class="muscle-group-hit" aria-hidden="true"',true)}${areaPaths(side,paths,name,'class="muscle-group-area" aria-hidden="true"',false,name===selected)}</g>`;
  }).join('');
  return `<figure class="body-map-figure"><figcaption>${side==='front'?'Front':'Back'}</figcaption><svg viewBox="0 0 220 480" class="body-map-svg" data-body-key="${material}" data-body-context="${escape(week+'|'+(comparison?.count||0))}" role="group" aria-label="${side==='front'?'Front':'Back'} ${comparison?'comparison':'muscle'} map">${bodyMaterials(material)}<g class="body-stage" aria-hidden="true"><ellipse cx="110" cy="237" rx="108" ry="230" fill="url(#${material}-halo)"/><path d="M16 114h188M16 214h188M16 314h188M16 414h188M40 90v334M110 80v350M180 90v334"/><ellipse class="stage-orbit" cx="110" cy="465" rx="96" ry="14"/><ellipse cx="110" cy="465" rx="76" ry="10"/><ellipse cx="110" cy="465" rx="53" ry="5"/><path class="stage-brackets" d="M12 80V65h20 M188 65h20v15 M12 385v20h20 M188 405h20v-20 M8 235h10 M202 235h10"/><path class="stage-scale" d="M13 110h6m-6 20h3m-3 20h3m-3 20h6m-6 20h3m188-80h-6m6 20h-3m3 20h-3m3 20h-6m6 20h-3"/></g><path class="body-outline" style="fill:url(#${material}-shell)" d="${silhouette}"/><g class="body-shell-details" aria-hidden="true"><path d="M99 59 C91 54 88 43 89 29 C89 11 98 5 110 5 C122 5 131 11 131 29 C132 43 129 54 121 59 L113.09 65 L106.91 65 Z" fill="url(#${material}-head)"/><path class="body-rim" d="M97 17 Q94 26 96 37 M100.66 66 L100.3 72 M119.34 66 L119.7 72 M46.81 94 Q34.42 107 30.18 124 M173.19 94 Q185.58 107 189.82 124 M18.09 216 L12 235 M201.91 216 L208 235 M81.86 425 L83.22 447 M138.14 425 L136.78 447"/><path class="body-joint" d="M75.99 331 Q86.05 340 97.24 331 M122.76 331 Q133.95 340 144.01 331 M27.76 180 L36.05 184 M183.95 184 L192.24 180"/><g class="body-tendons">${[false,true].map(mirror=>`<g${mirror?' transform="translate(220 0) scale(-1 1)"':''}><path class="forearm-shading" fill="url(#${material}-head)" opacity=".35" d="M28 183 Q35 186 41 181 C37 199 25 216 20 229 C22 211 23 197 28 183 Z"/>${side==='front'?`<path class="front-shin-shading" fill="url(#${material}-head)" opacity=".35" d="M78 345 C70 356 73 382 81 405 Q85 416 84 426 C90 402 96 374 94 351 Q89 339 78 345 Z"/>`:`<path fill="url(#${material}-head)" d="M76 342 Q83 339 86 348 L86 413 L83 431 Q71 384 76 342 Z"/>`}<path class="body-rim" d="${side==='back'?'M83 351 L83 418':''} M98 62 Q96 77 78 82 M9 241l-2 12m6-10l-2 15m6-12l-2 13 M76 459l1 5m5-7v8m5-8v8m5-8v8"/></g>`).join('')}</g></g>${drawings.join('')}${controls}<g class="body-contours" aria-hidden="true">${side==='front'?'<path d="M91.44 155 L105.36 155 M92.12 172 L105.53 172 M92.8 189 L105.7 189 M114.64 155 L128.56 155 M114.47 172 L127.88 172 M114.3 189 L127.2 189 M110 88 L110 221 M81.31 331 L88.28 339 L96.19 331 M123.81 331 L131.72 339 L138.69 331"/>':'<path d="M110 81 L110 221 M70 258 L85.22 262 M150 258 L134.78 262 M81.28 329 L89.59 335 L98.3 329 M121.7 329 L130.41 335 L138.72 329 M87.76 418 L86.31 444 M132.24 418 L133.69 444"/>'}</g></svg></figure>`;
}

function comparisonMetrics(group,baseline,comparison,isCurrent){
  const previousLabel=comparison.count===4?'4-week average':'Previous week';
  return `<div class="map-comparison-cards" aria-label="Muscle volume comparison">${[['sets','Involved sets'],['reps','Recorded reps'],['volume','Adjusted volume · kg·reps']].map(([field,label])=>{
    const current=group.sets?group[field]:0,previous=baseline?.[field];
    const complete=field==='sets'||group[field+'Known']===group.sets;
    const available=comparison.available&&previous!==null&&previous!==undefined;
    const delta=available&&complete?current-previous:null;
    const change=!comparison.available?'Not enough history':delta===null?'Incomplete records':delta===0?'No change':`${delta>0?'+':''}${number(delta)} ${delta>0?'more':'less'}`;
    return `<section class="map-comparison-card"><h4>${label}</h4><div class="map-comparison-values"><div><span>${isCurrent?'This week':'Selected week'}</span><strong>${number(current)}</strong></div><div><span>${previousLabel}</span><strong>${available?number(previous):'—'}</strong></div><div class="map-change"><span>Difference</span><b>${change}</b></div></div></section>`;
  }).join('')}</div>`;
}
function exerciseRow(exercise,overrides={}){
  return `<button class="map-exercise" data-view-exercise="${escape(exercise.name)}" aria-label="View ${escape(exercise.name)} history"><span class="map-exercise-name"><strong class="exercise-identity" style="--exercise-accent:${exerciseColor(exercise.name,overrides)}">${escape(exercise.name)}</strong><small class="map-role-label ${exercise.role}">${exercise.role==='all'?'Recorded':exercise.role==='primary'?'Primary':'Secondary'}</small></span><span class="map-exercise-values"><strong>${exercise.sets} ${exercise.sets===1?'set':'sets'} <span>·</span> ${number(exercise.reps)} reps</strong><small>${number(exercise.volume)} adjusted kg·reps${exercise.volumeKnown<exercise.sets?` · ${exercise.volumeKnown}/${exercise.sets} recorded`:''} <span aria-hidden="true">↗</span></small></span></button>`;
}

export function renderMuscleMap({overrides={},summary,weeks,selected,includeSecondary,from,to,asOf,comparison=null,weekLimit=4}){
  const all=selected==='all'||!summary.groups.some(g=>g.name===selected);
  const group=all?{...summary,name:'All muscles',primary:summary.sets,secondary:0,exercises:summary.exercises||[]}:summary.groups.find(g=>g.name===selected);
  const end=summary.end,partial=(from&&from>summary.week)||(to&&to<end)||asOf<end;
  const currentWeek=weekStart(asOf),isCurrent=summary.week===currentWeek;
  const recentWeeks=[...weeks].reverse(),visibleWeeks=recentWeeks.slice(0,Math.max(weekLimit,recentWeeks.indexOf(summary.week)+1));
  const baseline=all?comparison:comparison?.groups.find(g=>g.name===group.name);
  const weekday=value=>new Date(value+'T12:00:00Z').toLocaleDateString('en-GB',{weekday:'short',timeZone:'UTC'});
  const comparisonLabel=comparison?.count===4?'previous 4-week average':'previous week';
  const compareNote=comparison ? `Compared with ${comparisonLabel} · ${weekday(comparison.from)}–${weekday(comparison.to)} in each week` : '';

  const detailLabel=group.name==='Unassigned'?'Exercises without a muscle assignment':`${group.name} · ${includeSecondary?'all involvement':'primary work'}`;
  return `<section class="panel muscle-map-panel" aria-labelledby="muscle-map-title">
    <div class="muscle-map-header"><div><span class="eyebrow">YOUR WEEK, MUSCLE BY MUSCLE</span><h2 id="muscle-map-title">Where you put the work in<span class="heading-dot">.</span></h2><p>Tap a muscle to explore its training this week.</p></div><div class="map-role-switch segmented" role="group" aria-label="Muscle involvement"><button id="map-role-all" data-map-roles="all" class="${includeSecondary?'active':''}" aria-pressed="${includeSecondary}">Primary + secondary</button><button id="map-role-primary" data-map-roles="primary" class="${!includeSecondary?'active':''}" aria-pressed="${!includeSecondary}">Primary only</button></div></div>
    <div class="muscle-map-toolbar"><div class="map-week-choices"><span class="map-week-heading">Choose a week</span><div class="map-week-grid" role="group" aria-label="Week shown on muscle map">${visibleWeeks.map(week=>`<button id="map-week-${week}" data-map-week="${week}" aria-pressed="${week===summary.week}" class="map-week-button ${week===summary.week?'active':''}"><span>${week===currentWeek?'This week':week===shiftDay(currentWeek,-7)?'Last week':new Date(week+'T12:00:00Z').toLocaleDateString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'})}</span><strong>${new Date(week+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'})} – ${new Date(shiftDay(week,6)+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'})}</strong></button>`).join('')}</div>${visibleWeeks.length<weeks.length?'<button id="map-more-weeks" class="text-link" data-map-more-weeks>Show older weeks</button>':''}${partial?`<span class="map-week-status">Selected week: ${isCurrent?'in progress':'filtered week'}</span>`:''}</div><div class="map-compare-control"><span>Compare with</span><div class="map-compare-options" role="group" aria-label="Comparison period">${[[1,'Previous week'],[4,'4-week average'],[0,'Off']].map(([count,label])=>`<button id="map-compare-${count}" data-map-compare="${count}" aria-pressed="${(comparison?.count||0)===count}" class="${(comparison?.count||0)===count?'active':''}">${label}</button>`).join('')}</div></div></div>
    <div class="muscle-map-layout ${comparison?'with-comparison-body':''}"><div class="muscle-map-visual"><div class="map-visuals"><section class="map-body-section"><h3 class="map-body-title">Muscles trained</h3><p class="map-body-subtitle">${day(summary.week)} – ${day(end)}</p><div class="body-map-pair">${figure('front',summary.groups,group.name,null,summary.week)}${figure('back',summary.groups,group.name,null,summary.week)}</div><div class="body-map-legend"><span>Muscle-group colors · full tone: primary</span><span>Muted tone: secondary only</span><span><i class="inactive"></i>No recorded work</span></div><p class="map-selection-hint">Highlighted area = selected muscle group · primary work takes priority</p></section>${comparison?`<section class="map-body-section map-change-body" aria-label="Weekly muscle comparison"><h3 class="map-body-title">Where your training changed</h3><p class="map-body-subtitle">Sets vs ${comparisonLabel} · ${weekday(comparison.from)}–${weekday(comparison.to)}</p><div class="body-map-pair">${figure('front',summary.groups,group.name,comparison,summary.week)}${figure('back',summary.groups,group.name,comparison,summary.week)}</div><div class="body-map-legend change-legend"><span><i class="change-more"></i>More sets</span><span><i class="change-less"></i>Fewer sets</span><span><i class="change-same"></i>Same sets</span><span><i class="change-no-work"></i>No work</span>${!comparison.available?'<span><i class="change-unknown"></i>Not enough history</span>':''}</div><p class="map-selection-hint">${comparison.available?'Tap a muscle to compare its numbers. Colours show set changes, not strength gains.':'Not enough recorded history for this comparison.'}</p></section>`:''}</div><div class="map-week-summary"><span><strong>${number(summary.workouts)}</strong> workouts</span><span><strong>${number(summary.sets)}</strong> recorded sets${comparison?.available?`<small class="map-total-comparison">${summary.sets-comparison.sets>0?'+':''}${number(summary.sets-comparison.sets)} vs ${comparison.count===4?'4-week avg':'previous week'}</small>`:''}</span><span><strong>${summary.groups.filter(g=>g.name!=='Unassigned'&&g.sets).length}</strong> muscle groups</span></div></div>
    <div class="muscle-map-detail"><div class="map-detail-heading"><span class="eyebrow">${all?'ALL TRAINING':'SELECTED MUSCLE'}</span><h3 style="color:${all?'var(--ink)':muscleColor(group.name)}">${escape(group.name)}</h3><p>${group.primary} ${all?'recorded sets · each set counted once':'primary sets'}${!all&&includeSecondary?` <span>·</span> ${group.secondary} secondary sets`:''}</p></div>${comparison?`<p class="map-comparison-note">${compareNote}${!comparison.available?' · not enough recorded history':''}</p>`:''}${comparison?comparisonMetrics(group,baseline,comparison,isCurrent):`<div class="map-detail-metrics" aria-label="${escape(detailLabel)}"><div><strong>${number(group.sets)}</strong><span>involved sets</span></div><div><strong>${number(group.sets?group.reps:0)}</strong><span>recorded reps</span></div><div><strong>${number(group.sets?group.volume:0)}</strong><span>adjusted kg·reps</span></div></div>`}<p class="map-data-coverage">${group.sets?`${group.volumeKnown}/${group.sets} sets have adjusted volume · ${group.repsKnown}/${group.sets} have reps`:'No recorded work for this muscle in the selected week.'}</p>
    <div class="map-exercise-heading"><h4>Contributing exercises</h4><span>${group.exercises.length}</span></div><div class="map-exercises">${(group.exercises.slice(0,4).map(exercise=>exerciseRow(exercise,overrides)).join('')+(group.exercises.length>4?`<details class="map-more-exercises"><summary>Show ${group.exercises.length-4} more ${group.exercises.length===5?'exercise':'exercises'}</summary>${group.exercises.slice(4).map(exercise=>exerciseRow(exercise,overrides)).join('')}</details>`:''))||`<div class="map-empty"><span aria-hidden="true">○</span><strong>${summary.sets?'No sets to show':'No training recorded this week'}</strong><p>${summary.sets?'Choose another muscle or week.':'Choose another week above. Your date and record-source filters apply here too.'}</p></div>`}</div>
    </div></div>
    <div class="map-muscle-picker" role="group" aria-label="Choose a muscle on the weekly map"><button id="map-pick-all" class="map-muscle-chip ${all?'selected':''}" data-map-muscle="all" aria-pressed="${all}">All muscles<span>${summary.sets}</span></button>${summary.groups.filter(g=>g.name!=='Unassigned'||g.sets||g.name===group.name).map(g=>`<button id="map-pick-${g.name}" class="map-muscle-chip ${roleClass(g)} ${g.name===group.name?'selected':''}" data-map-muscle="${g.name}" aria-pressed="${g.name===group.name}"><i style="background:${muscleColor(g.name)}"></i>${g.name}<span>${g.sets}</span></button>`).join('')}</div>
    <details class="map-method"><summary>How this map counts your training</summary><p>A set can involve more than one primary or secondary muscle. Each involved muscle gets one set credit; the workout total above counts each recorded set once. Muscle totals should not be added together. Secondary work includes assisting and stabilizing roles and is not equivalent to a direct set. Recorded sets can include warm-ups; effort and proximity to failure are not available.</p><p>These are broad exercise-based assignments, not measured activation or a recovery score. Your saved primary-muscle overrides take precedence. Adjusted volume uses the same bodyweight contributions and exercise factors in both periods. Missing inputs stay missing; use set and rep counts alongside these estimates. The historical charts below include both primary and secondary involvement; their overall totals count each recorded set once.</p><p>Comparisons use the same weekdays in the prior week or the average of four prior calendar weeks, with the same record-source filter. Comparison weeks can be outside the page date range. Empty weeks within recorded history count as zero; missing load or reps are not treated as zero. More volume is not automatically better.</p><p>Movement references: <a href="https://www.nasm.org/workout-exercise-guidance" target="_blank" rel="noreferrer">NASM exercise library ↗</a>. The map uses simplified muscle regions.</p></details>
  </section>`;
}
