# Exercise workload profiles

Reviewed against all 49 exercise names returned by the live dashboard on 2026-10-25. Additional catalog aliases use the corresponding profile.

## Meaning of the factors

**This is an estimated external-work proxy, not muscle force, fatigue, calories, or hypertrophy stimulus.** The individual numerical distances and bodyweight contributions below are engineering assumptions selected for each movement; they are not published or measured exercise-equivalence coefficients.

Reference: one rep moving 1 kg upward through 0.40 m = 1 adjusted kg·rep.

`score = max(0, signed recorded kg × load copies + bodyweight kg × work-equivalent bodyweight fraction) × reps × multiplier`

`multiplier = assumed effective travel in metres × assumed resistance ratio / 0.40 m`

The user confirmed kg are per dumbbell and unilateral/alternating reps are total across sides. Simultaneous bilateral dumbbell lifts use two load copies; one-sided movements do not get another side multiplier. Generic curls and shrugs remain explicitly marked for convention calibration. Cable stacks are NOT automatically doubled or halved.

A bodyweight fraction represents work-equivalent mass relative to the reference load path, allowing for body segments rising through a shorter path. It is not always the fraction of body mass statically supported. Squat/deadlift factors include an approximation of torso/body movement; arm-segment mass is omitted.

A leg press assumes a 45-degree sled and excludes unrecorded sled tare/friction. Cable/machine factors provisionally treat kg as effective resistance; actual pulleys, levers, and cams need machine identification. A long joint moment arm does not justify an invented muscle-force multiplier.

Zero external load on an externally loaded movement is treated as missing resistance. Unknown exercise identities are excluded from the score. Their sets and reps remain visible. No raw Garmin loads or 1RM values are rewritten. User overrides remain in effect and can be reset explicitly.

## Reviewed profiles

| Exercise | Factor | Load copies | BW fraction | Assumed travel (m) | Resistance ratio | Status | Reason |
|---|---:|---:|---:|---:|---:|---|---|
| Assisted Dip | 0.75 | 1 | 1 | 0.3 | 1 | estimate | Assisted dip with estimated 0.30 m body rise. Recorded kg are assistance and are subtracted from body mass. |
| Assisted Pull Up | 1.125 | 1 | 1 | 0.45 | 1 | estimate | Pull up with estimated 0.45 m body rise. Recorded kg are assistance and are subtracted from body mass. |
| Barbell Bench Press | 1 | 1 | 0 | 0.4 | 1 | estimate | Vertical barbell press; total bar weight through an assumed 0.40 m concentric rise. This defines the reference factor. |
| Barbell Deadlift | 1.5 | 1 | 0.25 | 0.6 | 1 | estimate | Floor-to-lockout bar rise estimated at 0.60 m. Adds a work-equivalent 25% body mass for the rising torso; not the entire body mass. |
| Barbell Shrug | 0.3 | 1 | 0 | 0.12 | 1 | estimate | Short vertical scapular elevation, estimated 0.12 m; total barbell load, not two independent hand loads. |
| Bent Over Rear Delt Fly | 0.875 | 2 | 0 | 0.35 | 1 | estimate | Two dumbbells rise on a shoulder-abduction arc; assumed vertical load rise 0.35 m. Logged kg are per dumbbell. |
| Bicep Curl | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Dumbbell elbow flexion, assumed 0.35 m vertical rise. Uses one dumbbell per counted rep: recorded reps are total across sides. If both arms move together, change load copies to 2. |
| Bulgarian Split Squat | 1 | 2 | 0.7 | 0.4 | 1 | calibrate | Split squat estimated 0.40 m load rise with two dumbbells; work-equivalent body mass 70%. Total reps already include both legs, so there is no extra side multiplier. Change load copies if using one dumbbell. |
| Cable Biceps Curl | 1 | 1 | 0 | 0.4 | 1 | calibrate | Elbow flexion against a cable over an assumed 0.40 m handle travel. One loaded handle per counted rep. Assumes displayed kg mean handle resistance; verify pulley ratio. |
| Cable Chest Fly | 1.5 | 1 | 0 | 0.6 | 1 | calibrate | Shoulder horizontal adduction over an estimated 0.60 m cable travel. Assumes logged load is the combined effective cable resistance; use 2 load copies if logging one of two simultaneously moving independent stacks. |
| Cable Crunch | 0.625 | 1 | 0.1 | 0.25 | 1 | calibrate | Kneeling trunk flexion, estimated 0.25 m cable travel; includes a small work-equivalent torso contribution (10% body mass). Verify pulley resistance and torso motion. |
| Cable Triceps Extension | 1 | 1 | 0 | 0.4 | 1 | calibrate | Pushdown through estimated 0.40 m cable travel. Both hands share one rope/bar and one stack; no doubling. Assumes displayed load is effective handle resistance. |
| Calf Raise Machine | 0.25 | 1 | 0.95 | 0.1 | 1 | calibrate | Assumes standing calf machine: only about 0.10 m rise, plus 95% body mass rising on the forefoot. Change bodyweight to 0 if this is a seated machine; verify machine leverage. |
| Captain's Chair Leg Raises | 1.25 | 1 | 0.16 | 0.5 | 1 | calibrate | Supported trunk; legs rotate upward. Uses 16% work-equivalent body mass over a 0.50 m reference path, allowing for lower-limb mass and smaller leg-centre-of-mass rise. Bent knees reduce the work further. |
| Chin Up | 1.125 | 1 | 1 | 0.45 | 1 | estimate | Supinated vertical pull, estimated 0.45 m rise of near-whole-body mass plus added load. |
| Curl | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Generic elbow-flexion label: assumes 0.35 m load rise and one load per rep. Equipment and kg convention are unidentified; recorded zero kg is treated as missing resistance, not bodyweight work. |
| Decline Crunch | 0.5 | 1 | 0.3 | 0.2 | 1 | calibrate | Short trunk-flexion movement, estimated 0.20 m reference travel and 30% work-equivalent body mass. Decline angle and torso excursion need calibration. |
| Dip | 0.75 | 1 | 1 | 0.3 | 1 | estimate | Near-whole-body vertical rise estimated 0.30 m; added load is added to body mass, assistance is subtracted. |
| Fly | 1.5 | 1 | 0 | 0.6 | 1 | calibrate | Shoulder horizontal adduction over an estimated 0.60 m cable travel. Assumes logged load is the combined effective cable resistance; use 2 load copies if logging one of two simultaneously moving independent stacks. |
| Flye | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Pec-deck shoulder adduction: both arms share a machine stack. Assumed effective load travel 0.35 m; cam and lever geometry unknown, no free-weight equivalence claimed. |
| Hip Abduction | 0.5 | 1 | 0 | 0.2 | 1 | calibrate | Seated bilateral hip abduction against one stack; assumed 0.20 m effective stack/load travel. Pads act through levers/cams: displayed kg cannot establish hip torque without machine geometry. |
| Hip Adduction | 0.5 | 1 | 0 | 0.2 | 1 | calibrate | Seated bilateral hip adduction against one stack; assumed 0.20 m effective load travel. Both legs share the stack; no doubling. Verify lever/cam ratio. |
| Incline Bench Press | 1.125 | 1 | 0 | 0.45 | 1 | estimate | Incline barbell press: total bar load with an assumed 0.45 m vertical rise; longer rise than the flat-press reference. |
| Incline Bicep Curl | 1 | 1 | 0 | 0.4 | 1 | calibrate | Elbow flexion from behind the torso with estimated 0.40 m dumbbell rise. One dumbbell per counted rep because reps include both sides; change load copies to 2 for simultaneous bilateral reps. |
| Incline Dumbbell Bench Press | 1.125 | 2 | 0 | 0.45 | 1 | estimate | Two dumbbells pressed together; each rises about 0.45 m. Multiply the per-dumbbell logged kg by 2, not the rep count. |
| Lat Pulldown | 1.375 | 1 | 0 | 0.55 | 1 | calibrate | Shoulder adduction and elbow flexion over estimated 0.55 m cable travel. Two hands share a single bar/stack; assumes labelled load is effective bar resistance. |
| Lateral Raise | 1.375 | 2 | 0 | 0.55 | 1 | estimate | Two dumbbells lifted together on a long arm; estimated vertical dumbbell rise 0.55 m. Factor reflects displacement, not a claim that shoulder joint force equals dumbbell weight. |
| Leg Press | 0.8839 | 1 | 0 | 0.5 | 0.7071 | calibrate | Assumes 45-degree plate-loaded sled, 0.50 m rail travel: gravity component sin(45 degrees) = 0.7071. Seated body stays supported. Excludes unknown sled tare/friction; horizontal or selectorized presses require a different factor. |
| Leg Press Calf Raise | 0.1768 | 1 | 0 | 0.1 | 0.7071 | calibrate | Same assumed 45-degree sled but ankle plantarflexion moves it only about 0.10 m, not a full leg-press stroke. Body remains supported; excludes unknown sled tare/friction. |
| Leg Raise | 1.5 | 1 | 0.16 | 0.6 | 1 | calibrate | Legs rotate against gravity while the trunk is supported/hanging. Estimated 0.60 m reference travel and 16% work-equivalent body mass; knee bend and pelvis movement change this substantially. |
| Lying Ez Bar Triceps Extension | 0.875 | 1 | 0 | 0.35 | 1 | estimate | Lying elbow extension, estimated 0.35 m vertical EZ-bar rise. Shared bar weight is counted once. |
| Lying Leg Curl | 0.75 | 1 | 0 | 0.3 | 1 | calibrate | Knee flexion against a roller/cam, assumed effective load travel 0.30 m. Both legs share one stack; pad-force/stack ratio requires calibration. |
| Machine Chest Fly | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Pec-deck shoulder adduction: both arms share a machine stack. Assumed effective load travel 0.35 m; cam and lever geometry unknown, no free-weight equivalence claimed. |
| Machine Leg Extension | 0.75 | 1 | 0 | 0.3 | 1 | calibrate | Seated knee extension: both shins share one stack. Assumed 0.30 m effective load travel; cam/pad lever changes joint torque and needs calibration. |
| Machine T-Bar Row | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Chest-supported lever row; estimated 0.35 m effective plate rise. Logged plates are counted once, not per hand. Pivot location and plate-vs-handle lever arms are unknown. |
| One Arm Cable Lateral Raise | 1.5 | 1 | 0 | 0.6 | 1 | calibrate | One cable handle travels an estimated 0.60 m on a shoulder-abduction arc. Total reps already include sides; no x2. Assumes effective handle resistance; verify pulley ratio. |
| Overhead Barbell Squat | 1.25 | 1 | 0.8 | 0.5 | 1 | calibrate | Squat pattern: estimated 0.50 m bar rise plus 80% work-equivalent body mass. Historical manual import maps Barbell Squat to this Garmin label; no extra overhead multiplier is assumed. |
| Overhead Cable Tricep Extension | 1.125 | 1 | 0 | 0.45 | 1 | calibrate | Overhead elbow extension over estimated 0.45 m cable travel. Both hands share one attachment/stack; verify pulley ratio. |
| Overhead Cable Triceps Extension | 1.125 | 1 | 0 | 0.45 | 1 | calibrate | Overhead elbow extension over estimated 0.45 m cable travel. Both hands share one attachment/stack; verify pulley ratio. |
| Pull Up | 1.125 | 1 | 1 | 0.45 | 1 | estimate | Near-whole-body vertical rise estimated 0.45 m. Logged kg are added weight; body mass is included once. Assistance reverses the external-load sign. |
| Push Up | 0.625 | 1 | 0.72 | 0.25 | 1 | estimate | Average supported bodyweight approximated as 72% (research reports position dependence); estimated 0.25 m upper-body rise. Added load assumes similar travel, with placement needing calibration. |
| Rear Delt Fly | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Historical loads of 40-45 kg suggest a reverse-fly machine, but the name alone cannot prove equipment. Assumes one shared stack and 0.35 m effective load travel; set 2 load copies only for simultaneous dumbbells. |
| Row | 1.25 | 1 | 0 | 0.5 | 1 | calibrate | Generic row: assumes one combined external load through 0.50 m effective travel. No evidence for inverted/bodyweight row. Zero recorded kg is missing resistance until exercise/load is identified. |
| Seated Cable Row | 1.25 | 1 | 0 | 0.5 | 1 | calibrate | Horizontal pull with estimated 0.50 m cable travel. A fixed direction-changing pulley does not halve resistance; assumes the stack label is effective handle resistance. |
| Seated Leg Curl | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | Seated knee flexion with estimated 0.35 m effective load travel. One shared stack, supported torso; machine cam ratio must be calibrated. |
| Seated Rear Lateral Raise | 0.875 | 1 | 0 | 0.35 | 1 | calibrate | History spans 8-50 kg, consistent with mixed dumbbell/machine conventions. Uses one combined load and 0.35 m effective travel provisionally; split/rename mixed equipment before comparing. Change load copies to 2 for simultaneous per-dumbbell logging. |
| Shrug | 0.3 | 1 | 0 | 0.12 | 1 | calibrate | Generic shrug has only about 0.12 m vertical travel. History spans 28-60 kg with unspecified equipment; assumes combined load. Set load copies to 2 if these are two per-dumbbell loads. |
| Single Arm Cable Tricep Extension | 1 | 1 | 0 | 0.4 | 1 | calibrate | One-arm elbow extension through estimated 0.40 m cable travel. Reps are total across arms, so one effective handle load per counted rep; verify pulley ratio. |
| Single Arm Cable Triceps Extension | 1 | 1 | 0 | 0.4 | 1 | calibrate | One-arm elbow extension through estimated 0.40 m cable travel. Reps are total across arms, so one effective handle load per counted rep; verify pulley ratio. |
| Single Arm Preacher Curl | 0.75 | 1 | 0 | 0.3 | 1 | estimate | Supported one-arm elbow flexion, estimated 0.30 m vertical dumbbell rise. One dumbbell and total reps across sides; no side multiplier. |
| Single Leg Calf Raise | 0.25 | 1 | 0.95 | 0.1 | 1 | estimate | Standing one-leg plantarflexion: estimated 0.10 m rise of 95% body mass plus one dumbbell. Total reps include both legs; body mass and load counted once per rep. |
| Sit Up | 1 | 1 | 0.3 | 0.4 | 1 | calibrate | Torso flexion/hip flexion: estimated 0.40 m reference travel with 30% work-equivalent body mass to account for supported lower body and smaller torso-centre-of-mass rise. |
| Squat | 1.25 | 1 | 0.8 | 0.5 | 1 | estimate | Squat with estimated 0.50 m load travel and 80% work-equivalent body mass. A zero added load still includes rising body mass. |
| Standing Ez Bar Biceps Curl | 0.875 | 1 | 0 | 0.35 | 1 | estimate | Standing elbow flexion, estimated 0.35 m vertical bar rise. Total EZ-bar load, counted once despite using both arms. |
| Straight Arm Pulldown | 1.625 | 1 | 0 | 0.65 | 1 | calibrate | Long shoulder-extension arc produces estimated 0.65 m cable travel. One shared attachment/stack; assumes labelled effective resistance, not an arbitrary bonus for a long moment arm. |
| Triceps Extension | 1 | 1 | 0 | 0.4 | 1 | calibrate | Pushdown through estimated 0.40 m cable travel. Both hands share one rope/bar and one stack; no doubling. Assumes displayed load is effective handle resistance. |
| Unknown | 1 | 1 | 0 | 0.4 | 1 | unidentified | Movement and equipment are unknown. Excluded from adjusted volume until identified; sets and reps still count. |
| Weighted Leg Curl | 0.75 | 1 | 0 | 0.3 | 1 | calibrate | Knee flexion against a roller/cam, assumed effective load travel 0.30 m. Both legs share one stack; pad-force/stack ratio requires calibration. |
| Weighted Leg Extensions | 0.75 | 1 | 0 | 0.3 | 1 | calibrate | Seated knee extension: both shins share one stack. Assumed 0.30 m effective load travel; cam/pad lever changes joint torque and needs calibration. |
| Weighted Seated Calf Raise | 0.1768 | 1 | 0 | 0.1 | 0.7071 | calibrate | Retired alias for Leg Press Calf Raise in this project; assumed 45-degree sled and 0.10 m ankle-driven travel, no rising torso. |

## References and limits

- [OpenStax, Simple Machines](https://openstax.org/books/physics/pages/9-3-simple-machines): work is force times travel; pulley and lever mechanical advantage depends on geometry. Supports the method, not the individual assumed distances.
- [Suprak et al. (2011)](https://pubmed.ncbi.nlm.nih.gov/20179649/): push-up supported body mass varies with position. The 0.72 default is an approximate central estimate, not a participant-specific measurement.
- [Life Fitness cable equipment manual](https://kb.cybexintl.com/Owners_Manuals/Strength/Life_Fitness_Cable_Motion_Owners_Manual_1011084-0001.pdf): actual 2:1 configurations show stack mass differs from user resistance. Machine identity is needed for correction.
- [Life Fitness Dual Adjustable Pulley](https://www.lifefitness.com/en-gb/catalog/strength-training/cable-machines-functional-trainers/life-fitness-dual-adjustable-pulley): a different model uses 4:1 resistance; there is no universal cable factor.
- [Life Fitness Linear Leg Press](https://www.lifefitness.com/en-us/catalog/strength-training/plate-loaded/life-fitness-linear-leg-press): starting resistance is model-specific and nonzero; no unknown tare is invented here.
- [Appropriate Reporting of Exercise Variables in Resistance Training Protocols](https://pmc.ncbi.nlm.nih.gov/articles/PMC9339067/): displacement, technique and other within-exercise variables matter beyond load × reps. This motivates an explicit workload proxy, not exact equivalence between exercises.
