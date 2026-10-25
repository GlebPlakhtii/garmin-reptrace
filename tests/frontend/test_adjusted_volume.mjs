import test from 'node:test';
import assert from 'node:assert/strict';
import {adjustedVolumeSets,weeklyVolumeHistory,exerciseVolumeRule,DEFAULT_VOLUME_PROFILES,DEFAULT_MUSCLES} from '../../src/reptrace/web/static/model.mjs';
const row=(exercise,weight=0,reps=10,date='2026-10-20')=>({exercise,weight,reps,date,volume:weight*reps,sessionId:'a'});
test('bodyweight, added loads, assistance and machine factors produce distinct workload',()=>{
 const input=[row('Pull Up'),row('Pull Up',20),row('Push Up'),row('Sit Up'),row('Squat',100),row('Leg Press',100),row('Assisted Pull Up',30)];
 const result=adjustedVolumeSets(input,[{date:'2026-10-19',bodyWeightKg:80}]);
 assert.deepEqual(result.map(s=>s.volume),[900,1125,360,240,2050,883.9,562.5]);
 assert.equal(input[0].volume,0);assert.equal(result[0].weight,0);
 const history=weeklyVolumeHistory(result,'exercise',{}, {from:'2026-10-19',to:'2026-10-25'});
 assert.equal(history.find(s=>s.group==='Pull Up').history[0].volume,2025);
});
test('dated readings never use future weight and fallback applies before first reading',()=>{
 const sets=[row('Dip',0,10,'2026-10-01'),row('Dip',0,10,'2026-10-20')];
 const recovery=[{date:'2026-10-21',bodyWeightKg:90},{date:'2026-10-19',bodyWeightKg:80}];
 assert.deepEqual(adjustedVolumeSets(sets,recovery,{bodyWeightKg:75}).map(s=>s.volume),[562.5,600]);
 assert.equal(adjustedVolumeSets(sets,recovery)[0].volume,null);
 assert.equal(adjustedVolumeSets(sets,recovery)[0].missingBodyweight,true);
});
test('custom factors, unknown inputs and excess assistance',()=>{
 const settings={bodyWeightKg:80,exercises:{'Pull Up':{multiplier:1.5,bodyweight:1,assistance:false},'Leg Press':{multiplier:.3,bodyweight:0}}};
 assert.deepEqual(adjustedVolumeSets([row('Pull Up'),row('Leg Press',100),row('Pull Up',null),row('Squat',100,null),row('Assisted Pull Up',100)],[],settings).map(s=>s.volume),[1200,300,null,null,0]);
});

test('each live-history exercise and catalog movement has an explicit reviewed profile',()=>{
 const liveNames=["Barbell Bench Press", "Barbell Deadlift", "Barbell Shrug", "Bent Over Rear Delt Fly", "Bicep Curl", "Bulgarian Split Squat", "Cable Biceps Curl", "Cable Chest Fly", "Cable Crunch", "Cable Triceps Extension", "Calf Raise Machine", "Captain's Chair Leg Raises", "Curl", "Decline Crunch", "Dip", "Hip Abduction", "Hip Adduction", "Incline Bench Press", "Incline Bicep Curl", "Incline Dumbbell Bench Press", "Lat Pulldown", "Lateral Raise", "Leg Press", "Leg Press Calf Raise", "Leg Raise", "Lying Ez Bar Triceps Extension", "Lying Leg Curl", "Machine Chest Fly", "Machine Leg Extension", "Machine T-Bar Row", "One Arm Cable Lateral Raise", "Overhead Barbell Squat", "Overhead Cable Tricep Extension", "Pull Up", "Push Up", "Rear Delt Fly", "Row", "Seated Cable Row", "Seated Leg Curl", "Seated Rear Lateral Raise", "Shrug", "Single Arm Cable Tricep Extension", "Single Arm Preacher Curl", "Single Leg Calf Raise", "Sit Up", "Squat", "Standing Ez Bar Biceps Curl", "Straight Arm Pulldown", "Unknown"];
 assert.equal(liveNames.length,49);
 for(const name of new Set([...liveNames,...Object.keys(DEFAULT_MUSCLES)])){
  assert.ok(DEFAULT_VOLUME_PROFILES[name],`Missing explicit profile: ${name}`);
  const profile=exerciseVolumeRule(name);
  assert.ok(profile.rationale.length>50,name);
  assert.equal(profile.confidence,DEFAULT_VOLUME_PROFILES[name].confidence,`Profile resolution: ${name}`);
  assert.ok(['estimate','calibrate','unidentified'].includes(profile.confidence),name);
 }
 assert.ok(new Set(liveNames.map(n=>exerciseVolumeRule(n).multiplier)).size>=12);
});
test('simultaneous dumbbells count two loads, total unilateral reps do not double',()=>{
 const settings={bodyWeightKg:80};
 const input=[row('Incline Dumbbell Bench Press',20),row('Lateral Raise',10),row('Single Arm Preacher Curl',10),row('Single Arm Cable Tricep Extension',10),row('Single Leg Calf Raise',20)];
 const result=adjustedVolumeSets(input,[],settings);
 assert.deepEqual(result.map(s=>s.volume),[450,275,75,100,240]);
 assert.equal(exerciseVolumeRule('Incline Dumbbell Bench Press').loadCopies,2);
 assert.equal(exerciseVolumeRule('Single Arm Preacher Curl').loadCopies,1);
});
test('calf press scores shorter travel than leg press and squat includes bodyweight',()=>{
 const result=adjustedVolumeSets([row('Leg Press',100),row('Leg Press Calf Raise',100),row('Squat')],[],{bodyWeightKg:80});
 assert.equal(result[0].volume,883.9);
 assert.equal(result[1].volume,176.8);
 assert.equal(result[2].volume,800);
 assert.ok(result[1].volume<result[0].volume/4);
});
test('barbell squat uses the squat estimate while uncalibrated variants remain missing',()=>{
 const rows=adjustedVolumeSets([row('Barbell Squat',100),row('Romanian Deadlift',60),row('Cable Lateral Raise',10)],[],{bodyWeightKg:80});
 // (100 kg added load + 80 kg body mass × 0.8) × 10 reps × 1.25.
 assert.equal(rows[0].volume,2050);
 assert.equal(rows[1].volume,null);
 assert.equal(rows[2].volume,null);
});
test('unidentified exercises and zero external resistance remain missing, not fabricated',()=>{
 const rows=adjustedVolumeSets([row('Unknown'),row('New Unidentified Movement',100),row('Curl'),row('Row'),row('Barbell Bench Press')],[],{bodyWeightKg:80});
 assert.ok(rows.every(s=>s.volume===null));
 assert.equal(rows[0].unreviewed,true);
 assert.equal(rows[2].missingLoad,true);
 assert.equal(exerciseVolumeRule('Pull-up').bodyweight,1);
});
test('custom load conventions override reviewed assumptions and legacy values remain effective',()=>{
 const sets=[row('Incline Dumbbell Bench Press',20),row('Single Arm Preacher Curl',10)];
 const settings={exercises:{'Incline Dumbbell Bench Press':{multiplier:1,bodyweight:0,loadCopies:1},'Single Arm Preacher Curl':{multiplier:2,bodyweight:0}}};
 assert.deepEqual(adjustedVolumeSets(sets,[],settings).map(s=>s.volume),[200,200]);
});
