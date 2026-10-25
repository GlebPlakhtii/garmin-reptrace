# Equipment profiles

Open Preferences → Equipment profiles. Add a named profile, enter comma-separated available kg loads, assign it to exercises and save. A profile can represent a dumbbell rack, plate-loaded barbell or machine stack. Multiple profiles can share a name, but use distinct names for easy selection.

Use the same weight convention as your recorded sets. For barbells, list achievable total loads including the bar. For dumbbells, use per-hand or combined weights according to your existing records; the app does not convert these automatically.

Assigned profiles override fixed weight increments while retaining exercise rep ranges. Once the existing progression conditions are met, the next listed load is proposed. Jumps over 10%, exhausted inventories and historical weights absent from the assigned inventory require review. Historical records are never rounded or changed. Removing a profile clears its assignments; unassigned exercises use their existing progression rules.

Profiles are shared SQLite settings, included in full exports, with revision checks to reject stale saves. They affect the shared next-session generator used by the dashboard and plan images. No equipment values or assignments are guessed automatically.

# Garmin workout weights and reps

Open Garmin workouts → Load Garmin workouts. **Quick weights & reps** keeps the focused target editor: type values manually, or press Fill next-session targets. Matching is automatic: Upper 1/2 use their own next-session plans, and Leg Day 1/2 use Lower 1/2. **Full edit** opens the workout title, description, exercise and rest steps, repeats, set order and notes. You can add, duplicate, remove or move steps; split a repeat to edit its individual sets; and edit the complete Garmin segment JSON for fields outside the visual controls. Both flows require a preview before saving to Garmin.

When a matching set and rest immediately follow a repeat block, the app extends that repeat automatically if the full executed sequence stays identical. This also runs during quick target edits. Upper 2's first three incline dumbbell bench press sets are an example: its two-set repeat plus the next matching set become one three-set repeat.

The editor groups targets by exercise, numbers their sets and marks shared repeat targets. Review changes uses the same exercise grouping. Update Garmin workout commits the preview. Rep-based steps can change weightValue and endConditionValue; a repeat block is split where suggested weights or reps differ, then consecutive iterations with identical targets are kept in one loop. Already expanded identical steps can be grouped again. For example, three sets at the same weight/reps followed by one different set become a three-iteration loop plus one separate set. The executed exercise and rest sequence is preserved, including a skipped final rest. Non-kg weights remain unchanged.

The quick preview assigns each individual set its exact suggested values. No nearest-value approximation remains. A manual edit can still target existing shared blocks, or adjust each set after filling suggestions. Manual review can also group already expanded identical targets without changing their values. When logged and Garmin set counts differ, a uniform suggestion fills every existing Garmin set. Varying suggestions with mismatched counts, missing values and suggestions requiring review remain unchanged automatically.

Garmin templates with unrecognized names can still be edited manually. Automatic suggestions require a matching named plan.

The adapter uses the existing Garmin session tokens and the upstream in-place workout PUT endpoint, retaining the pinned ingestion library. Originals and proposed payloads are journaled in /var/lib/form/garmin-workouts.sqlite on the dashboard's persistent volume. Include this file in backups; it is separate from the app's normal Excel export.

Previews expire after 15 minutes. Apply checks both the current remote workout and current suggestion fingerprint, then reads back the updated segments. Garmin regenerates internal step IDs and child-step indices on save, so verification ignores those identifiers while checking all step contents, exercise order and rest, and the proposed repeat structure. A failed or uncertain write is never blindly retried; retrying the same confirmation first reads Garmin and marks the journal complete if the expected values are already there. The API retains the same preview ID for idempotent completed retries. This cannot provide an atomic remote compare-and-swap; avoid concurrent editing in Garmin during an update.

# Telegram

Use /garmin to list workout templates and preview suggested changes without a model call. The bot sends one in-chat PNG image with changes separated by exercise and any repeat-block notes. Save and Cancel buttons appear beneath that image.

With the coach configured, natural-language requests also work:

- Update my Garmin Lower 2 workout from the next-session suggestions.
- Set the bench press step in Garmin Upper 1 to 80 kg and 8 reps.
- Add Captain’s chair leg raise to Garmin Upper 1 and Upper 2, 2 sets of 15 reps, bodyweight, with the same rest as the existing template.

The coach can list templates, search the bundled FIT exercise catalogue, read editable step indices and draft appending an exercise, but cannot call apply. Exercise additions use text previews (or an HTML attachment for long previews), with separate Save/Cancel buttons per template. Missing sets/reps must be clarified. Omitted rest copies the last existing rest step; an explicit rest duration overrides it. Generic categories require an exercise note, so Captain’s chair leg raise can be represented as LEG_RAISE with an explicit equipment description rather than silently substituting a hanging variation. Duplicate additions and concurrent template edits are rejected. Existing exercise targets and playback are preserved. Only the authenticated owner's confirmation callback commits them. No misleading local-data undo button is offered for Garmin updates; request a new preview to make further changes. Completed activities and planned Garmin templates use separate tools.

# Drag-to-select graph dates

Drag horizontally across exercise progress, recovery/body-weight or weekly-volume graphs to set the shared inclusive date filter. Reverse dragging works too. Undo zoom returns one step; Reset zoom restores the range from before the first graph selection. Escape cancels a drag. Ordinary point clicks still open workouts; weekly bar clicks still select a week. Date inputs remain available as the keyboard alternative.

Validation: bash scripts/check.sh — 183 Python tests and 43 JavaScript tests. Includes immutable-field checks, manual revision, repeat splitting and regrouping, execution-order preservation, Telegram image preview and owner/confirmation enforcement, API origin checks, graph range calculations, editor rendering and Garmin editor theme contrast. Browser visual testing was denied by the browser permission gate.
