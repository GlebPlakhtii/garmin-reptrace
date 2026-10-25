# Weekly muscle map

Weekly volume includes a front/back SVG map above the historical charts. Select a week and tap a muscle or use the named buttons beneath the figures. Each muscle shows its primary and secondary set counts, recorded reps, recorded load × reps, and the exercises contributing to those values. Exercise links open the existing history page.

The map respects the page's date range and record-source filter. Previous/next buttons move through calendar weeks, including empty weeks, and start at the latest week in the selected range. A “This week” shortcut returns to the current week when it is inside the date range. Monday starts each week. A partial date range or current week is labelled. Selecting a muscle or week updates only the map and preserves page position. The SVG regions support Tab, Enter and Space; named buttons offer an alternative to the illustration.

## Counting rules

- Each set counts once in the map's overall workout/set totals.
- A compound set may receive credit in several muscles. Each muscle receives at most one credit per set, either primary or secondary. Muscle totals are not additive and secondary credits are not equivalent to direct sets.
- Red means at least one primary set; yellow means secondary-only work; grey means no recorded work in the displayed scope. The selected region is outlined. Colour shows involvement, not volume intensity, activation, fatigue or recovery.
- Squats and leg presses include Quads and Glutes as primary roles. Barbell deadlifts include Hamstrings, Glutes and Quads. Stabilizing/assisting roles are listed separately.
- Broad defaults are based on the [NASM exercise library](https://www.nasm.org/workout-exercise-guidance), including its [deadlift](https://www.nasm.org/resource-center/exercise-library/barbell-deadlift) and [squat](https://www.nasm.org/resource-center/exercise-library/goblet-squat) descriptions. Roles are conventional approximations and cannot capture technique or individual differences.
- A changed user primary-muscle assignment takes precedence. Saving the legacy muscle editor with unchanged default assignments preserves the compound roles. An explicit Unassigned override disables secondary credits.
- Unknown exercise names remain Unassigned. No muscle mapping is inferred from arbitrary substrings.
- Missing weight or volume remains missing. Known zero is retained; the details report how many sets have recorded load × reps and reps. Bodyweight is not estimated or added.

The historical charts, existing bot tools and exports continue to use their original one-primary-assignment aggregation. The map's counting explanation makes this difference visible. Multi-muscle credits must not be compared directly with those totals.

## Implementation and validation

- `web/static/model.mjs`: role catalogue, calendar weeks and pure aggregation.
- `web/static/muscle-map.mjs`: original SVG regions and escaped accessible markup.
- `web/static/app.js`: map state and delegated interactions.
- `web/static/styles.css`: responsive layout and theme colours.
- `web/server.py`: static module route.

Run `node --test tests/test_muscle_map.mjs tests/test_volume_page.mjs tests/test_training_features.mjs tests/test_web_model.mjs tests/test_design_features.mjs` for aggregation and rendering regression checks. Browser verification covers actual SVG clicks, keyboard selection, primary-only mode, empty weeks, source filters and mobile layout.

## Compact comparisons

“Compare with” offers Previous week (default), Previous 4-week average and Off. The existing muscle metrics show absolute changes and baseline values; the weekly recorded-set total shows its change too. No percentage is calculated when the baseline is zero, and changes are not labelled good or bad.

The baseline uses the same weekdays as the displayed week, through today when the week is in progress. A custom date range narrowing the displayed week narrows each comparison window to the corresponding weekdays. Historical baseline records use the page's source filter but may fall outside its current date range. Empty periods within available recorded history contribute zero. If the earliest comparison period precedes the available history, the comparison is explicitly unavailable. Reps or load × reps comparisons require complete measurements in both sides; otherwise the UI shows “Incomplete records”.

The exercise breakdown has no inner scrollbar. Four exercises are shown initially; a native disclosure expands the rest. Comparisons and navigation update the map in place.
