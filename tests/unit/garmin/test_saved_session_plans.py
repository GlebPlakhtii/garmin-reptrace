"""Only verified manual edits override the next occurrence of an exercise."""
from contextlib import closing
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from reptrace.coaching.assistant import TrainingTools
from reptrace.exports.plans import render_plan, plan_caption, target_count_label
from reptrace.garmin.workouts import GarminWorkouts, saved_session_plan, target_groups
from reptrace.telegram.bot import fetch_plans
from reptrace.training.planning import build_next_sessions
from tests.unit.garmin.test_garmin_workouts import fixture


class SavedSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = Mock()
        self.workout = fixture(3)
        self.workout['workoutName'] = 'Leg Day 2'
        self.client.list.return_value = [self.workout]
        self.client.get.side_effect = lambda _: deepcopy(self.workout)
        self.service = GarminWorkouts(Path(self.directory.name) / 'isolated.sqlite', lambda: self.client)
        self.plans = build_next_sessions({"sets": [], "workouts": []}, date(2026, 11, 17))
        self.plan = next(p for p in self.plans if p['type'] == 'lower2')
        self.plan.pop('lastPerformed')  # These tests supply individual history explicitly.
        self.plan.pop('sharedLastPerformed')
        self.plan['exercises'] = [{
            'name': 'Barbell Bench Press', 'previous': [{'weight': 75, 'reps': 7}],
            'proposed': [{'weight': 85, 'reps': 10}] * 2, 'status': 'weight_progress',
        }]
        self.record_manual_save()

    def record_manual_save(self, names=None):
        with closing(self.service.connect()) as db, db:
            db.execute('DELETE FROM updates')
            db.execute('INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?)', (
                'saved', 1794913933.0, 123, 'lower2', 'synthetic', json.dumps(fixture()),
                json.dumps(self.workout), json.dumps({'manualExercises': list(target_groups(self.workout)) if names is None else names}), 'done',
            ))

    def read(self):
        return self.service.call({'operation': 'next_sessions', 'planType': 'lower2'}, self.plans)['plans'][0]

    def test_leg_day_uses_saved_values_and_set_count_without_mutating_suggestions(self):
        before = deepcopy(self.plans)
        result = self.read()
        self.assertEqual(result['source'], 'manual_override')
        self.assertEqual(result['name'], 'Lower 2')
        self.assertEqual(result['exercises'][0]['proposed'], [{'weight': 80, 'unit': 'kg', 'reps': 8}] * 3)
        self.assertEqual(result['exercises'][0]['previous'], [{'weight': 75, 'reps': 7}])
        self.assertEqual(self.plans, before)
        self.assertTrue(render_plan(result).startswith(b'\x89PNG'))
        self.assertIn('one-time manual targets', plan_caption(result))
        self.client.update.assert_not_called()
        with closing(self.service.connect()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM updates').fetchone()[0], 1)
        step = self.workout['workoutSegments'][0]['workoutSteps'][0]['workoutSteps'][0]
        step['weightValue'] = 72.5
        step['endConditionValue'] = 11
        self.record_manual_save()
        self.assertEqual(self.read()['exercises'][0]['proposed'][0], {'weight': 72.5, 'unit': 'kg', 'reps': 11})

    def test_order_new_exercises_units_and_missing_values_are_preserved(self):
        group = self.workout['workoutSegments'][0]['workoutSteps'][0]
        extra = deepcopy(group['workoutSteps'][0])
        extra.update(exerciseName='', category='CORE', description='Custom hold', weightValue=None, weightUnit=None,
                     endCondition={'conditionTypeKey': 'time'}, endConditionValue=45)
        group['workoutSteps'].insert(1, extra)
        group['workoutSteps'][0]['weightUnit']['unitKey'] = 'pound'
        result = saved_session_plan(self.plan, self.workout)
        self.assertEqual([e['name'] for e in result['exercises']], ['Barbell Bench Press', 'Custom hold'])
        self.assertEqual([len(e['proposed']) for e in result['exercises']], [3, 3])
        self.assertEqual(result['executionOrder'], [
            {'exerciseIndex': exercise, 'setIndex': iteration}
            for iteration in range(3) for exercise in range(2)
        ])
        self.assertIn('grouped by exercise', result['notice'])
        self.assertEqual(result['exercises'][0]['proposed'][0]['unit'], 'lb')
        target = result['exercises'][1]['proposed'][0]
        self.assertIsNone(target['weight'])
        self.assertIsNone(target['reps'])
        self.assertEqual(target_count_label(target), '45 sec')
        self.assertTrue(render_plan(result).startswith(b'\x89PNG'))

    def test_interleaved_sets_keep_individual_saved_targets_and_history(self):
        original = deepcopy(self.workout)
        active, rest = original['workoutSegments'][0]['workoutSteps'][0]['workoutSteps']
        steps = []
        for weight, reps in [(65, 12), (70, 10), (75, 8)]:
            steps.extend([
                dict(deepcopy(active), weightValue=weight, endConditionValue=reps),
                dict(deepcopy(active), exerciseName='SQUAT', weightValue=40, endConditionValue=15),
                deepcopy(rest),
            ])
        self.workout['workoutSegments'][0]['workoutSteps'] = steps
        previous = [{'weight': 60, 'reps': 12}, {'weight': 65, 'reps': 10}, {'weight': 70, 'reps': 8}]
        self.plan['exercises'][0]['previous'] = deepcopy(previous)
        before = deepcopy(self.workout)
        self.record_manual_save()
        result = self.read()
        self.assertEqual(len(result['exercises']), 2)
        self.assertEqual(result['exercises'][0]['previous'], previous)
        self.assertEqual([(s['weight'], s['reps']) for s in result['exercises'][0]['proposed']], [(65, 12), (70, 10), (75, 8)])
        self.assertEqual(len(result['exercises'][1]['proposed']), 3)
        self.assertEqual(self.workout, before)
        self.client.update.assert_not_called()

    def test_no_match_is_labelled_and_ambiguity_or_outage_never_uses_suggestions(self):
        self.client.list.return_value = []
        result = self.read()
        self.assertEqual(result['source'], 'history_suggestion')
        self.assertIn('No matching saved Garmin', result['notice'])
        self.client.list.return_value = [self.workout, dict(self.workout, workoutId=456, workoutName='Lower 2')]
        with self.assertRaisesRegex(ValueError, 'Multiple Garmin'):
            self.read()
        self.client.list.side_effect = RuntimeError('Unavailable')
        with self.assertRaisesRegex(RuntimeError, 'Unavailable'):
            self.read()

    def test_coach_and_image_export_use_current_template(self):
        garmin = Mock(side_effect=lambda body: self.service.call(body, self.plans))
        tools = TrainingTools({}, {}, garmin=garmin)
        result = tools.call('get_next_workout', {'workout_type': 'lower2'})
        self.assertEqual(result['source'], 'manual_override')
        tools.call('export_next_workout_image', {'workout_type': 'lower2'})
        self.assertEqual(tools.artifacts[0]['exercises'], result['exercises'])
        self.assertEqual(garmin.call_args.args[0], {'operation': 'next_sessions', 'planType': 'lower2'})

    def test_bot_fetches_saved_template_endpoint(self):
        with patch('reptrace.telegram.bot.fetch_garmin', return_value={'plans': [self.read()]}) as fetch:
            self.assertEqual(fetch_plans()[0]['source'], 'manual_override')
            fetch.assert_called_once_with({'operation': 'next_sessions'})

    def test_unedited_or_automatic_templates_do_not_replace_suggestions(self):
        for status in ('preview', 'sending', 'done'):
            with self.subTest(status=status):
                self.record_manual_save([] if status == 'done' else None)
                with closing(self.service.connect()) as db, db:
                    db.execute('UPDATE updates SET status=?', (status,))
                self.workout['updatedDate'] = '2026-11-17T12:00:00Z'
                result = self.read()
                self.assertEqual(result['source'], 'history_suggestion')
                self.assertEqual(result['exercises'], self.plan['exercises'])

    def test_manual_override_expires_after_that_exercise_is_performed(self):
        history = [{'date': '2026-11-16', 'time': '2026-11-16T10:00:00Z', 'sets': [{'weight': 75, 'reps': 7}]}]
        self.plan['exercises'][0]['history'] = history
        self.assertEqual(self.read()['source'], 'manual_override')
        # A request/restart does not consume the override.
        self.service = GarminWorkouts(self.service.path, lambda: self.client)
        self.assertEqual(self.read()['source'], 'manual_override')
        history.insert(0, {'date': '2026-11-18', 'time': '2026-11-18T10:00:00Z', 'sets': []})
        self.assertEqual(self.read()['source'], 'manual_override')
        history[0]['sets'] = [{'weight': 80, 'reps': 8}]
        result = self.read()
        self.assertEqual(result['source'], 'history_suggestion')
        self.assertEqual(result['exercises'], self.plan['exercises'])

    def test_same_day_timestamps_and_date_only_history(self):
        self.plan['baselineDate'] = '2026-11-17'
        self.plan['baselineTime'] = '2026-11-17T10:00:00+02:00'
        self.assertEqual(self.read()['source'], 'manual_override')
        self.plan['baselineTime'] = '2026-11-17T15:00:00+02:00'
        self.assertEqual(self.read()['source'], 'history_suggestion')
        self.plan['baselineTime'] = None
        self.assertEqual(self.read()['source'], 'history_suggestion')

    def test_omitted_exercise_is_consumed_only_when_it_is_performed(self):
        self.plan['baselineDate'] = '2026-11-20'
        self.plan['baselineTime'] = '2026-11-20T10:00:00Z'
        self.plan['lastPerformed'] = {'Barbell Bench Press': {'date': '2026-11-16', 'time': '2026-11-16T10:00:00Z'}}
        self.plan['exercises'] = []
        self.assertEqual(self.read()['source'], 'manual_override')
        self.plan['lastPerformed']['Barbell Bench Press'] = {'date': '2026-11-21', 'time': '2026-11-21T10:00:00Z'}
        self.assertEqual(self.read()['source'], 'history_suggestion')

    def test_unmatched_custom_exercise_does_not_override_forever(self):
        self.plan['lastPerformed'] = {}
        self.plan['baselineDate'] = '2026-11-18'
        self.plan['baselineTime'] = '2026-11-18T10:00:00Z'
        self.assertEqual(self.read()['source'], 'history_suggestion')

    def test_only_manually_changed_exercise_uses_garmin(self):
        other = {'name': 'Squat', 'previous': [{'weight': 45, 'reps': 10}],
                 'proposed': [{'weight': 45, 'reps': 11}], 'status': 'progress', 'reason': 'Add one rep.'}
        self.plan['exercises'].append(other)
        group = self.workout['workoutSegments'][0]['workoutSteps'][0]
        group['workoutSteps'].insert(1, dict(deepcopy(group['workoutSteps'][0]), exerciseName='SQUAT', weightValue=20))
        self.record_manual_save(['Barbell Bench Press'])
        result = self.read()
        self.assertEqual(result['exercises'][0]['status'], 'saved')
        self.assertEqual(result['exercises'][1], other)
        self.assertTrue(render_plan(result).startswith(b'\x89PNG'))

    def test_changed_remote_targets_do_not_reuse_an_old_manual_save(self):
        self.workout['workoutSegments'][0]['workoutSteps'][0]['workoutSteps'][0]['weightValue'] = 99
        self.assertEqual(self.read()['source'], 'history_suggestion')

    def test_legacy_manual_revision_is_identified_from_automatic_preview(self):
        automatic = deepcopy(self.workout)
        automatic['workoutSegments'][0]['workoutSteps'][0]['workoutSteps'][0]['weightValue'] = 85
        with closing(self.service.connect()) as db, db:
            db.execute("UPDATE updates SET preview_json='{}'")
            row = db.execute('SELECT * FROM updates').fetchone()
            db.execute('INSERT INTO updates VALUES(?,?,?,?,?,?,?,?,?)', (
                'ancestor', row['created'] - 10, 123, 'lower2', row['plan_hash'], row['before_json'],
                json.dumps(automatic), '{}', 'superseded',
            ))
        self.assertEqual(self.read()['source'], 'manual_override')
        with closing(self.service.connect()) as db, db:
            db.execute("UPDATE updates SET after_json=? WHERE id='saved'", (json.dumps(automatic),))
        self.workout = automatic
        self.assertEqual(self.read()['source'], 'history_suggestion')

    def test_preview_tracks_manual_edits_separately_from_automatic_targets(self):
        preview = self.service.call({'operation': 'preview', 'workoutId': 123}, self.plans)
        self.assertEqual(preview['manualExercises'], [])
        auto = self.service.call({'operation': 'revise', 'previewId': preview['previewId'],
                                  'useSuggestions': True, 'manualTargets': []}, self.plans)
        self.assertEqual(auto['manualExercises'], [])
        manual = self.service.call({'operation': 'revise', 'previewId': auto['previewId'],
                                    'useSuggestions': True, 'manualTargets': [{'index': 0, 'weight': 72.5}]}, self.plans)
        self.assertEqual(manual['manualExercises'], ['Barbell Bench Press'])

    def test_requesting_one_routine_uses_manual_load_from_the_other(self):
        other = next(p for p in self.plans if p['type'] == 'lower1')
        other['exercises'] = deepcopy(self.plan['exercises'])
        result = self.service.call({'operation': 'next_sessions', 'planType': 'lower1'}, self.plans)['plans']
        self.assertEqual(len(result), 1)
        exercise = result[0]['exercises'][0]
        self.assertEqual([s['weight'] for s in exercise['proposed']], [80, 80])
        self.assertEqual(exercise['status'], 'saved')
        self.assertEqual(exercise['sharedLoad']['sourceType'], 'lower2')
        self.assertEqual(exercise['manualSourceType'], 'lower2')

    def test_manual_override_is_consumed_by_completion_in_another_routine(self):
        self.plan['lastPerformed'] = {'Barbell Bench Press': {'date': '2026-11-16', 'time': '2026-11-16T09:00:00Z'}}
        self.plan['sharedLastPerformed'] = {'Barbell Bench Press': {'date': '2026-11-18', 'time': '2026-11-18T09:00:00Z'}}
        self.assertEqual(self.read()['source'], 'history_suggestion')
