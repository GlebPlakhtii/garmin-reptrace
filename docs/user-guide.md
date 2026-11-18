# Using Garmin RepTrace

## Start with the filters

The default range is 30 days. Choose a preset or enter From/To dates and apply
them. Training views share date and record-source filters; a full reload returns
to the default range. Recovery follows the date range independently of the
training-set source filter. An empty range does not imply your records were deleted.

## Overview, exercises and workouts

Overview brings together a workout calendar, recent sessions, consistency,
recovery and available Garmin signals. Preferences controls the overview layout.
The summary includes run count, distance, moving time and distance-weighted moving pace.
The calendar marks strength sessions with a square and runs with a circle. Days with
both have a split highlight. Run days show recorded kilometres. Select a date to
see each session and open its details. Runs appear under All records and Garmin records.

The exercise library shows loads, reps, estimated 1RM and volume with underlying set logs.
Select an exercise from the existing muscle-group/exercise list, then choose
**Est. 1RM** in its graph’s metric selector. This option is hidden for group and
All exercises views;
estimates from different lifts are never combined. Select a bar to open its workout.
Date and record-source filters apply. Estimates require positive recorded load and
1–10 reps; missing or unsupported estimates stay blank. These are Epley estimates,
not measured maximums.

The exercise library defaults to **Adjusted volume**, using the configured factors
and explaining missing inputs. **Recorded load × reps** remains available in
Preferences and needs no bodyweight or movement profile. The choice is remembered in this browser and applies only to
the exercise library; other pages retain their labeled adjusted-volume calculations.
Assisted loads are excluded from recorded resistance volume.

Exercise colors follow their primary muscle group, including saved overrides.
Workouts provides searchable sessions, complete set detail, corrections and exports.
Workout detail includes unidentified sets in performed order. Exercise analysis omits Unknown sets until you identify them. The individual-session and full Excel exports include them.
On a phone, expand the date range to change it. **Export** groups CSV, filtered Excel and all-data Excel, with the scope on each choice.

## Weekly volume and insights

In **Historical weekly trends**, select **Est. 1RM** alongside volume, sets and
reps after selecting a specific exercise in Exercise grouping. The option is
hidden for muscle groups and All exercises. The same graph switches to the best eligible estimate per Monday–Sunday week.
This metric uses one exercise at a time: select it using the exercise buttons.
Missing estimates stay blank and partial weeks are marked. Select a week to inspect
its workouts. Switching back to muscle grouping restores the volume metric.

Weekly volume stacks each exercise's contribution and provides an interactive
muscle map. Choose sets, reps, or adjusted volume, select a week, and inspect the
exercise breakdown. Keyboard controls select the same muscle groups and weeks.
All-muscle totals avoid counting a compound set again for each secondary muscle.
Coverage describes how many sets have the required inputs.

Insights uses comparable recorded history to show exact-rep progress, potential
plateaus and descriptive recovery associations. Different loads, equipment,
missing inputs and sparse history limit what can be compared. A correlation is
not proof that a recovery metric caused a training result.

## Log, correct and undo

Choose **Log workout** on Workouts or open **More → Log & edit** to add a manual workout. To repeat a session, open its detail and choose **Repeat workout**. The editor copies its name and exercise order into a new draft for today. Previous loads and reps appear as references. Enter the sets you performed and remove any you skipped. An existing new-workout draft takes precedence.
Open **Edit sets** on a saved workout to correct its records.
Enter only known measurements: leave unknown loads/reps blank and use zero when
zero was actually recorded. Keep per-dumbbell, per-side, machine-stack, bodyweight
and assistance conventions clear.

Save feedback distinguishes success, failure and revision conflicts. If a save's
confirmation is lost, retry the pending request rather than recreating the workout.
Newer changes can prevent an older edit from being undone; undo in reverse order.
Original versions remain in the archive/audit records. Ordinary navigation and
refresh preserve dirty forms, subject to the app's save/discard controls.

## Next-session plans

Use **More → Next session → Short on time?** to choose any completed workout,
including a custom or generic name, and enter 10–180 minutes. Mark priority
exercises **Keep all sets** or exclude equipment that is unavailable today.
Preview shows reduced/removed sets, retained targets and whether the protected
work exceeds your budget. It never rewrites completed training.

Duration estimates use recorded set/rest durations when available, otherwise
recorded session time, or an explicit three-minute-per-set fallback. Five minutes
are reserved for preparation. Equipment waits and changed rests can extend the
session. Weekly recorded sets and the two alternative plans are shown separately;
planned sets are not added to completed totals. Generic names use only the chosen
session, avoiding progression comparisons across unrelated workouts.

In Telegram, ask: “I have 35 minutes today. Shorten my last workout and keep all
bench press sets.” The bot can substitute an exercise using its own recorded
targets, without converting loads between movements. To prescribe completely
new exercises, ask it to create a new Garmin workout instead.

The current planner recognizes **Upper 1**, **Upper 2**, **Lower 1**, and **Lower 2**;
Leg Day 1/2 map to the Lower types. Generic or unnamed workouts are not assigned
arbitrarily. The latest named session normally supplies the exercise order and set
counts. If it only leaves sets out of the previous same-type session within 42
days, that previous structure is retained: a single shortened workout does not
shrink the plan. Affected exercises repeat their earlier targets without automatic
progression, and the latest results still show only sets actually recorded.
Repeated reductions establish a new baseline; substitutions and added sets use
the latest structure. An explicitly selected session remains the exact template
for a one-off adaptation.

Review the rep range, equipment increments and evidence. A load group reaching
the rep ceiling in two comparable sessions can progress in weight; eligible
matching-load groups may progress in reps. Missing values, changed loads,
ambiguous bodyweight conventions, stale history and other uncertainty can pause
progression. Read the displayed reason rather than forcing every exercise upward.

Plans do not record completed sets. Download the PNG sheet or review a Garmin
workout update. Recorded recovery provides context without automatically scaling
all targets by a made-up score.

## Garmin templates

Telegram can create entirely new strength workouts with arbitrary names and
exercises, even without recorded history or existing Garmin templates. For
example: “Create a new Garmin workout called Hotel circuit with three rounds of
12 goblet squats, 10 push-ups and a 30-second plank.” Review the proposed targets
and **Save and send**. The four Upper/Lower commands remain convenience shortcuts.
For a movement absent from Garmin's exercise catalog, the bot uses an appropriate
generic category and preserves the exact custom name/equipment in its description.
This does not register a new official Garmin exercise code. Delivery is requested
only after creation/readback; syncing the watch is still required.

Garmin workouts lists your account's strength templates. Inspect exercises,
weights, reps, rest and repeat groups, or use quick adjustments. Review the preview
before applying. The backend reads back the saved template to check the result.
An uncertain result needs inspection before retrying. Template updates are real
external Garmin writes; editing a template does not change a completed workout.

Saved pre-session snapshots support planned-versus-completed comparisons. When
only a recent current template is available, the report labels it approximate;
it does not claim to know an older plan it never captured.

## Goals, records and comparisons

Goals can target load plus reps in the same set or reps alone, with optional dates.
Archive and restore goals rather than discarding their history. Assisted exercises
must account for less assistance meaning greater resistance.

Personal records and Compare workouts use the recorded data and expose missing
or incomplete comparisons. Matching-rep loads are more informative than comparing
unrelated rep ranges. Unsupported estimated 1RM remains absent.

## Recovery and nutrition

Recovery displays recorded sleep, HRV, resting HR, Body Battery and body weight.
Missing days remain gaps. Weigh-ins are separate from added exercise load.
Garmin sync shows separate watch-upload, collection-check and sample timestamps.

Nutrition shows approved food entries and estimates. Optional Telegram food-photo
or text estimation requires AI configuration; inspect portions and quantities before
saving. Use **Edit** beside an entry in Nutrition to correct its name, calories, macros or note. Deletion requires confirmation. If the entry changed elsewhere, refresh and review the latest version before submitting another correction.

## Exports

- **CSV** exports the relevant visible training/recovery records and current filters.
- **Excel** exports filtered sessions and sets; workout-name search also applies on Workouts.
- A workout's **Excel** action exports that complete session independently of global filters.
- **All data** ignores display filters and includes hidden Unknown sets, settings, goals,
  recovery and source/audit records for the training app. It does not contain credentials
  or every unrelated intraday Garmin series. Source records include reviewed TSV rows and running activity summaries. For individual running samples and laps, use Running.
- Plan PNGs and report HTML are portable snapshots. Editing an exported workbook
  does not write back into Garmin RepTrace.

## Telegram

Use `/menu` for controls; `/next` or `/upper1` etc. for workout sheets; `/weekly`
for the completed week; `/report` for the latest eligible session; `/export` for
full training data, `/export latest` or `/export 2026-10-01 2026-10-31` for narrower
exports. `/status` explains scheduled reports.

Use `/workout` for the latest completed workout as one image with every recorded
set and session totals. Long sheets arrive as a full-resolution PNG. The older
`/widget` shortcut now sends this image too.

With AI configured, normal private messages can ask about training, propose edits,
or estimate food. Review Save/Cancel and Undo controls. The bot is restricted to
its configured or securely paired private owner.

## Running

Open **Running** for a dedicated workspace for Garmin road, trail, track and
indoor/treadmill runs. The date range, run-type filter and name search control
the run list and progress calculations. **Runs** opens the activity log and a focused
analysis panel with **Overview**, **Charts**, **Metrics**, **Laps** and **Compare**
tabs. **Progress** shows period totals, weekly distance and trends. Visible buttons
select dates, run types, chart metrics and axes; there are no dropdown selectors. Progress charts
can show pace, distance, heart rate, cadence, power or exercise load. Select a
point or run card to inspect that activity. Points are spaced by date. A missing measurement breaks the trend line.

Opening a run imports its detail from Garmin when it is not cached. **Refresh** refreshes that run; **Sync period** imports the
filtered list sequentially and can be stopped after the current request. These
are read-only requests to Garmin: original activities and training records are
unchanged. Imported detail is kept privately so it remains available after restart
or when Garmin is unavailable. Each run shows its import time and any partial-data
or refresh failure notice.

The run workspace includes:

- Timer, moving and elapsed time, summary and moving pace, best recorded pace,
  heart rate, calories and ascent.
- Aerobic and anaerobic training effect, exercise load, Garmin's primary benefit
  and moderate/vigorous intensity minutes.
- Recorded heart-rate zone boundaries, times and percentages.
- Pace and heart-rate charts, plus selectable cadence, power, elevation, running
  dynamics, stamina, Body Battery and sensor-temperature traces when recorded.
  Switch between timer time and original sample distance; use the sample slider
  (including arrow keys) to inspect exact returned measurements.
- Cadence, stride length, ground-contact time/balance, vertical oscillation/ratio,
  steps, running power, potential/available stamina and estimated sweat loss.
- GPS route trace when coordinates exist, lap/interval tables, run comparison,
  the complete supported measurement table, and CSV exports of runs and laps.

Missing measurements remain **—**. The app does not invent outdoor elevation or
GPS for treadmill runs. Garmin average pace, moving pace and sample pace have
different time bases. Treadmill calibration can change summary distance without
rewriting chart samples; a notice calls this out. Cadence counts both feet and
stride length is shown in metres. Training-effect and stamina values are Garmin
estimates. Sensor temperature is not necessarily ambient weather. Comparisons do
not control for terrain, distance, weather or effort. CSV exports contain numeric
seconds and seconds/km, explicitly labelled in their headers.

In Telegram use **Running overview** or **Latest run report** in `/menu`:

- `/running` or `/running 7`, `30`, `90`, `all`: period totals and recent runs.
- `/runs`: all-history totals and the latest ten run buttons.
- `/run latest` or `/run RUN_ID`: a summary plus a complete HTML attachment with
  charts, zones, dynamics and lap data; tap a run button to avoid entering an ID.
- `/runcompare`: compare the latest two runs, or supply two known run IDs.

The coach can answer natural questions about running history and comparisons, or
send the complete running report. Running commands retain the bot's owner-only,
private-chat access restrictions and are independent of strength workout reports.


## Training conventions and incomplete records

Recorded kilograms follow the convention used on the equipment. Use distinct exercise names when two machine variants use different resistance or ranges of motion. In a repeated workout, previous numbers are references to the same setup. Simultaneous dumbbell work can have two load copies. Alternating reps in the reviewed profiles are total across sides. Adjusted volume uses the movement settings in Preferences.

Strength totals count recorded rep-based sets. A recorded set with reps can include warm-up or drop-set work. Garmin rest blocks supply rest time, and the session detail preserves their exercise order. The app does not infer a warm-up designation, superset pairing or machine resistance from the load alone.

If an interrupted reviewed TSV import affects a workout, the dashboard identifies the interruption and withholds that workout from totals until the import resumes. Source rows missing a workout identifier remain in the full Excel export. Sessions with missing or repeated set identifiers stay available for inspection and the editor explains why they need source reconciliation.
