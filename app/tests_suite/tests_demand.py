from django.test import SimpleTestCase

from app.customer import demand as d

STORES = {1: {'name': 'A', 'lat': 31.500, 'lng': 74.300},
          2: {'name': 'B', 'lat': 31.502, 'lng': 74.301},   # A ke saath ek hi dabba
          3: {'name': 'C', 'lat': 31.600, 'lng': 74.400},
          4: {'name': 'NoGPS', 'lat': None, 'lng': None}}


class DemandTests(SimpleTestCase):
    def test_hour_profile_weekday_average(self):
        rows = [(4, 20, 1)] * 8                      # 4 Jumme, 8 orders, 20 baje
        self.assertEqual(d.hour_profile(rows, 4)[20], 2.0)
        self.assertEqual(d.hour_profile(rows, 0)[20], 0)

    def test_best_window(self):
        prof = [0] * 24
        prof[19], prof[20], prof[21] = 2, 4, 3
        self.assertEqual(d.best_window(prof), {'start': 19, 'end': 22, 'avg': 3.0})
        self.assertIsNone(d.best_window([0] * 24))

    def test_weekly_plan_has_seven_days(self):
        plan = d.weekly_plan([(1, 13, 1)] * 4)
        self.assertEqual(len(plan), 7)
        self.assertIsNotNone(plan[1]['window'])
        self.assertIsNone(plan[0]['window'])

    def test_zones_group_and_level(self):
        rows = [(0, 12, 1)] * 3 + [(0, 12, 2)] * 2 + [(0, 12, 3)] + [(0, 12, 4)] * 5
        z = d.zones(rows, STORES)
        self.assertEqual(len(z), 2)                  # NoGPS store ignore
        self.assertEqual(z[0]['count'], 5)
        self.assertEqual(z[0]['names'], ['A', 'B'])
        self.assertEqual(z[0]['level'], 1.0)
        self.assertEqual(z[1]['level'], 0.2)

    def test_zones_hour_filter(self):
        rows = [(0, 12, 1), (0, 18, 3)]
        z = d.zones(rows, STORES, hours={18})
        self.assertEqual([x['names'] for x in z], [['C']])
