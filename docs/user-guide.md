# Using Garmin RepTrace

## Start with the filters

The default range is 30 days. Choose a preset or enter From/To dates and apply
them. Training views share date and record-source filters; a full reload returns
to the default range. Recovery follows the date range independently of the
training-set source filter. An empty range does not imply your records were deleted.

## Overview, exercises and workouts

Overview brings together a workout calendar, recent sessions, consistency,
recovery and available Garmin signals. Preferences controls the overview layout.
Select a calendar day to open a session.

Exercises exposes loads, reps, estimated 1RM and volume with underlying set logs.
Choose **Est. 1RM** in the existing exercise graph’s metric selector to see
estimates per workout. Choose a muscle group and exercise from the existing exercise list;
estimates from different lifts are never combined. Select a bar to open its workout.
Date and record-source filters apply. Estimates require positive recorded load and
1–10 reps; missing or unsupported estimates stay blank. These are Epley estimates,
not measured maximums.

Exercises defaults to **Recorded load × reps**, which needs no bodyweight or
movement profile. **Adjusted volume** uses the configured factors and explains
missing inputs. The choice is remembered in this browser and applies only to
Exercises; other pages retain their labeled adjusted-volume calculations.
Assisted loads are excluded from recorded resistance volume.

Exercise colors follow their primary muscle group, including saved overrides.
Workouts provides searchable sessions, complete set detail, corrections and exports.
Unknown exercises are hidden in ordinary dashboard views but retained in a full export.

## Weekly volume and insights

In **Historical weekly trends**, select **Est. 1RM** alongside volume, sets and
reps. The same graph switches to the best eligible estimate per Monday–Sunday week.
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

Open **More → Log & edit** to add a manual workout or correct recorded sets.
Enter only known measurements: leave unknown loads/reps blank and use zero when
zero was actually recorded. Keep per-dumbbell, per-side, machine-stack, bodyweight
and assistance conventions clear.

Save feedback distinguishes success, failure and revision conflicts. If a save's
confirmation is lost, retry the pending request rather than recreating the workout.
Newer changes can prevent an older edit from being undone; undo in reverse order.
Original versions remain in the archive/audit records. Ordinary navigation and
refresh preserve dirty forms, subject to the app's save/discard controls.

## Next-session plans

The current planner recognizes **Upper 1**, **Upper 2**, **Lower 1**, and **Lower 2**;
Leg Day 1/2 map to the Lower types. Generic or unnamed workouts are not assigned
arbitrarily. The latest named session supplies the exercise order and set counts.

Review the rep range, equipment increments and evidence. A load group reaching
the rep ceiling in two comparable sessions can progress in weight; eligible
matching-load groups may progress in reps. Missing values, changed loads,
ambiguous bodyweight conventions, stale history and other uncertainty can pause
progression. Read the displayed reason rather than forcing every exercise upward.

Plans do not record completed sets. Download the PNG sheet or review a Garmin
workout update. Recorded recovery provides context without automatically scaling
all targets by a made-up score.

## Garmin templates

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
saving. Estimates are not laboratory measurements. Entries can be corrected or deleted.

## Exports

- **CSV** exports the relevant visible training/recovery records and current filters.
- **Excel** exports filtered sessions and sets; workout-name search also applies on Workouts.
- A workout's **Excel** action exports that complete session independently of global filters.
- **All data** ignores display filters and includes hidden Unknown sets, settings, goals,
  recovery and source/audit records for the training app. It does not contain credentials
  or every unrelated intraday Garmin series.
- Plan PNGs and report HTML are portable snapshots. Editing an exported workbook
  does not write back into Garmin RepTrace.

## Telegram

Use `/menu` for controls; `/next` or `/upper1` etc. for workout sheets; `/weekly`
for the completed week; `/report` for the latest eligible session; `/export` for
full training data, `/export latest` or `/export 2026-10-01 2026-10-31` for narrower
exports. `/status` explains scheduled reports.

With AI configured, normal private messages can ask about training, propose edits,
or estimate food. Review Save/Cancel and Undo controls. The bot is restricted to
its configured or securely paired private owner.
