# Telegram tools and web-app coverage

Ask in ordinary language. The bot reads the local database at the start of each
chat request. Changes produce a preview; **Save** applies it and **Cancel** leaves
the data unchanged. A tool saying “queued” means an attachment or preview will
follow, not that a record was saved.

| Web feature | Telegram capability and tools |
| --- | --- |
| Overview, exercise library, workout history | `get_dashboard_view` (overview, exercises, sets, workouts); existing history/session tools |
| Exercise graphs and estimated 1RM | Dashboard exercises/strength views; select one lift for estimates; optional weekly grouping |
| Weekly volume and muscle involvement | Dashboard weekly_volume/muscle_map views, primary and secondary involvement, current versus previous week or four-week average |
| Recovery and Garmin sync | Dashboard recovery/sync views, all available recovery fields and collection timestamps |
| Insights | Dashboard insights: matched-rep load history, plateau flags and recovery associations |
| Personal records | Dashboard records: separate load, reps and estimated maximum, with assistance direction respected |
| Compare workouts | Dashboard compare or `compare_workouts`; exact-rep comparisons and missing-volume coverage |
| Goals | Dashboard goals; `propose_record_change` save/archive/restore/delete; full-history goal achievement |
| Log & edit | `get_editable_workout`, `propose_workout_change`: add/edit/delete workouts and individual sets; clear missing fields explicitly |
| Recent changes / undo | `get_change_history`, `propose_undo_change`; existing saved-edit Undo buttons |
| Equipment | `get_editable_records`, `propose_settings_change`: profiles, available loads and exercise assignments |
| Volume preferences | Settings proposals: fallback weight, multiplier, bodyweight fraction, load copies, assistance and custom-profile review |
| Muscle mapping / progression | `propose_record_change`; `set_progression_rule` now stages a preview too |
| Recovery overrides | Record proposals preserve Garmin readings; delete an override to restore those readings |
| Nutrition | `get_nutrition_history`, paginated `get_food_entries`, `propose_food_entry` for new food or saved-entry corrections, `propose_food_delete` |
| Next session | `get_next_workout`, `adapt_workout`, `export_next_workout_image` |
| Garmin templates | List/read; target-only update/addition tools; `get_garmin_workout_structure` and `propose_garmin_structure_change` for names, descriptions, exercises, order, repeat blocks, rests, durations, notes and targets |
| Downloads | Full/filtered Excel, `export_dashboard_csv` for sets/recovery, plan PNG, `create_html_report` for custom graphs/reports |
| Refresh | Every new chat request refreshes the local data; this does not trigger Garmin collection |

## Examples

- “Show my weekly adjusted volume for October, manual workouts only.”
- “Compare my last two Upper 1 workouts, including matching reps.”
- “Show my bench estimated 1RM by week.”
- “Set this dumbbell profile to 5, 7.5, 10 and 12.5 kg per hand.”
- “Change this exercise's volume multiplier to 1.5; keep its other settings.”
- “Archive my bench goal,” then “Restore that goal.”
- “Show recent edits,” then “Undo this workout correction.”
- “Change the saved food portion to half,” or “Delete this food entry.”
- “Change the rest periods in this Garmin template to 90 seconds.”
- “Send the recovery CSV for last month.”

## Filters and calculation rules

Dashboard reads support inclusive date bounds, Garmin/manual/all sources, exact
exercise selection and pagination. Optional settings include recorded versus
adjusted volume, primary-muscle library filtering, exercise/workout search,
matching reps, plateau window, recovery threshold, comparison workout IDs,
weekly strength grouping, and muscle-map comparison periods.

The bot executes the web app's existing `model.mjs` functions through a fixed
read-only Node adapter. Model output is never executed as code. Node.js 22+ is
required for these dashboard tools and is included in the Docker image. No
frontend build step was added.

Weekly muscle totals include overlapping primary and secondary involvement;
they must not be added together as distinct sets. Adjusted volume is an
estimate, not a measurement of effort. Missing values remain missing. Less
assistance means more resistance; unsupported assisted estimated 1RM is absent.
Goals use full history, matching the Goals page. CSV uses the web export's raw
recorded columns; it does not silently substitute adjusted chart volume.

Settings patches preserve omitted values and carry the metadata revision.
Stale previews fail rather than overwriting newer settings. Settings changes
are audited and can be undone in reverse order when the current state still
matches. Saved-food corrections keep the entry ID and time, retain original
values in the audit, and use stable request identities for retries. Food delete
previews also check the expected entry and retain an audit; there is no food
undo button.

## Boundaries

Theme, overview layout, selected filters and unsaved browser drafts live in that
browser. Telegram cannot change that browser's local storage. Shared training
preferences and records are editable through the tools above.

The web Sync page reports collection state; neither it nor the Telegram sync
tool starts collection. Full Garmin editing changes existing templates after
Save; it does not create performed activities or claim those templates were
sent to a watch. Live Garmin/Telegram actions require the owner's request and
confirmation. A model-generated answer is not proof of a successful save.

## Reviewed Garmin integration and voice

Completed Garmin strength-set corrections use `get_editable_garmin_activity_sets`
and `propose_garmin_activity_correction`. The server retains the complete original
Garmin payload and validates only requested exercise identity, repetitions and
recorded-load changes against stable set positions/timing. Review **Save to
RepTrace + Garmin**, **RepTrace only**, or **Cancel**. Manual-only sessions retain
the existing local editor. No Garmin activity creation/deletion or completed-set
insertion/removal is exposed.

Combined saves check revisions, journal intent, write Garmin, verify readback,
then use RepTrace's audited storage. A timeout is reconciled, never blindly
replayed. **Garmin saved / RepTrace pending** stays durable; retry only finishes a
conflict-free local step. Changed records require a fresh review. Use
`list_garmin_integration_operations` and `get_garmin_integration_status` to recover
unfinished work; `propose_garmin_correction_reversal` stages a new reviewed reversal
of a completed combined correction, and refuses intervening changes.

`propose_garmin_workout_creation` extracts program sessions through the existing
text/image assistant. It builds new templates from validated exercises, timed or
rep steps and repeat/superset blocks. Unspecified load means no load target;
unspecified rest means open/manual rest. Review all sessions or save/send one
selected session. Existing same-name templates are retained. The device list
resolves a unique fēnix 7 Pro or asks for a choice among multiple matches; confirmed
selection persists. Creation and delivery have separate states. Only verified
created templates are sent, and delivery retries reuse their workout IDs.
Ambiguous creation or delivery outcomes stop unresolved. **Delivery requested—sync
your watch** does not confirm physical arrival. No calendar entries or automatic
starting are supported.

Voice notes enter the same durable queue with their message and reply identities.
`OPENAI_TRANSCRIPTION_MODEL` defaults to `gpt-transcribe`, using the existing API
key. OGG is uploaded as `voice.ogg`, `audio/ogg`; limits are five minutes and
20 MB. Successful original-language transcripts persist for retry and appear as
**Heard: …** before normal assistant processing. Audio stays in memory only;
audio/transcripts are not written to operational logs. Failed/empty transcription
never invokes action tools. Measurements still appear in reviewed Save previews.

The synthetic `/carddemo` uses a separate SQLite file and `demo:` callbacks. Its
simulated save cannot invoke Garmin or training storage. Cards were rejected in
user review and are **not** the normal interface; existing previews remain.

For cross-process strength protection, every writer must share
`STRENGTH_MUTATION_LOCK_PATH` and `GARMIN_OPERATION_STATE_PATH`. Compose mounts the
same state volume into web and collector. The lock precedes web mutation locks;
collector batches recheck manual markers and unresolved operations immediately
before writing under that lock. External writers not using this lock are outside
this guarantee. The Influx replacement itself is still nontransactional, with
existing archives and reconciliation retained.
