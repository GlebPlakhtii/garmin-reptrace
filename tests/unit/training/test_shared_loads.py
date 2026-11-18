"""Shared loads use the latest exercise proposal without changing performed sets."""
from copy import deepcopy
import unittest

from reptrace.training.planning import build_next_sessions, share_exercise_loads
from tests.unit.training.test_next_sessions import workout, row


class SharedLoadTests(unittest.TestCase):
    def data(self):
        name = 'Seated Rear Lateral Raise'
        return {'workouts': [workout('a', '2026-11-01', 'Upper 1'),
                             workout('b', '2026-11-08', 'Upper 1'),
                             workout('c', '2026-11-06', 'Upper 2')],
                'sets': [row('a', 9, 12, name), row('a', 9, 12, name, order=2),
                         row('b', 9, 12, name), row('b', 9, 12, name, order=2),
                         row('c', 8, 12, name), row('c', 8, 11, name, order=2),
                         row('c', 8, 10, name, order=3)],
                'progressionRules': {name: {'repMin': 8, 'repMax': 12, 'weightStep': 1}}}

    def test_rear_raise_uses_whole_kg_and_same_load_with_different_set_counts(self):
        data = self.data()
        original = deepcopy(data)
        plans = build_next_sessions(data, '2026-11-09')
        left, right = plans[0]['exercises'][0], plans[1]['exercises'][0]
        # 9 -> 10 exceeds the existing 10% automatic-increase limit: hold 9,
        # never manufacture 9.5 kg when the user specified one-kilogram steps.
        self.assertEqual([s['weight'] for s in left['proposed']], [9, 9])
        self.assertEqual([s['weight'] for s in right['proposed']], [9, 9, 9])
        self.assertEqual([s['weight'] for s in right['previous']], [8, 8, 8])
        self.assertEqual(right['sharedLoad']['sourceType'], 'upper1')
        self.assertEqual(data, original)

    def test_latest_exercise_not_largest_load_wins_for_leg_days(self):
        data = self.data()
        data['workouts'][0]['name'] = data['workouts'][1]['name'] = 'Leg Day 1'
        data['workouts'][2]['name'] = 'Leg Day 2'
        data['workouts'][2].update(date='2026-11-09', time='2026-11-09T09:00:00Z')
        plans = build_next_sessions(data, '2026-11-10')
        self.assertEqual([s['weight'] for s in plans[2]['exercises'][0]['proposed']], [8, 8])
        self.assertEqual([s['weight'] for s in plans[3]['exercises'][0]['proposed']], [8, 8, 8])

    def test_explicit_session_adaptation_keeps_its_own_loads(self):
        result = build_next_sessions(self.data(), '2026-11-09', baseline_id='c')[0]
        self.assertEqual([s['weight'] for s in result['exercises'][0]['proposed']], [8, 8, 8])
        self.assertNotIn('sharedLoad', result['exercises'][0])

    def test_top_and_backoff_loads_remain_distinct(self):
        plans = build_next_sessions(self.data(), '2026-11-09')
        left, right = plans[0]['exercises'][0], plans[1]['exercises'][0]
        left['proposed'] = [{'weight': 80, 'reps': 8}, {'weight': 70, 'reps': 10}]
        right['proposed'] = [{'weight': 75, 'reps': 8}, {'weight': 65, 'reps': 10}]
        share_exercise_loads(plans)
        self.assertEqual([s['weight'] for s in right['proposed']], [80, 70])
        right['proposed'].append({'weight': 60, 'reps': 10})
        before = deepcopy(right['proposed'])
        share_exercise_loads(plans)
        self.assertEqual(right['status'], 'review')
        self.assertEqual(right['proposed'], before)
        self.assertIn('top/back-off', right['reason'])

    def test_manual_load_has_priority_and_preserves_each_routines_sets(self):
        plans = build_next_sessions(self.data(), '2026-11-09')
        left, right = plans[0]['exercises'][0], plans[1]['exercises'][0]
        right.update(status='saved', manualSavedAt=1794211200)
        for target in right['proposed']:
            target['weight'] = 8
        share_exercise_loads(plans)
        self.assertEqual([s['weight'] for s in left['proposed']], [8, 8])
        self.assertEqual(len(right['proposed']), 3)
        self.assertEqual(left['status'], 'saved')
        self.assertEqual(plans[0]['source'], 'manual_override')
        first = deepcopy(plans)
        share_exercise_loads(plans)
        self.assertEqual(plans, first)

    def test_distinct_exercises_and_future_records_are_not_shared(self):
        data = self.data()
        for entry in data['sets']:
            if entry['sessionId'] == 'c':
                entry['exercise'] = 'Cable Rear Lateral Raise'
        data['workouts'].append(workout('future', '2026-12-01', 'Upper 1'))
        data['sets'].append(row('future', 99, 10, 'Seated Rear Lateral Raise'))
        plans = build_next_sessions(data, '2026-11-09')
        self.assertEqual([s['weight'] for s in plans[1]['exercises'][0]['proposed']], [8, 8, 8])
        self.assertNotIn('sharedLoad', plans[1]['exercises'][0])
