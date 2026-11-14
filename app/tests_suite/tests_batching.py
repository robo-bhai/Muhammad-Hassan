from django.test import SimpleTestCase

from app.customer import batching as b


def O(no, status, vendor, store_ll, drop_ll, name='C'):
    return {'order_no': no, 'status': status, 'vendor_id': vendor, 'store_name': f'Store{vendor}',
            'store_ll': store_ll, 'store_addr': '', 'cust_name': name, 'drop_ll': drop_ll, 'cust_addr': ''}


class MatchOfferTests(SimpleTestCase):
    base = {'vendor_id': 1, 'store_ll': (31.50, 74.30), 'drop_ll': (31.55, 74.35)}

    def test_no_actives(self):
        self.assertIsNone(b.match_offer(self.base, []))

    def test_same_store(self):
        self.assertEqual(b.match_offer(dict(self.base), [dict(self.base)]), 'same_store')

    def test_near_store(self):
        a = {'vendor_id': 2, 'store_ll': (31.505, 74.305), 'drop_ll': (32.0, 75.0)}
        self.assertEqual(b.match_offer(self.base, [a]), 'near_store')

    def test_same_area_drop(self):
        a = {'vendor_id': 2, 'store_ll': (33.0, 73.0), 'drop_ll': (31.56, 74.36)}
        self.assertEqual(b.match_offer(self.base, [a]), 'same_area')

    def test_far_and_missing_coords(self):
        a = {'vendor_id': 2, 'store_ll': (33.0, 73.0), 'drop_ll': (34.0, 72.0)}
        self.assertIsNone(b.match_offer(self.base, [a]))
        self.assertIsNone(b.match_offer({'vendor_id': 9}, [{'vendor_id': 2}]))


class PlanRouteTests(SimpleTestCase):
    def test_needs_two_orders(self):
        self.assertIsNone(b.plan_route([O(1, 'assigned', 1, (31.5, 74.3), (31.6, 74.4))]))

    def test_pickups_before_drops_and_same_store_merged(self):
        orders = [O(1, 'assigned', 1, (31.50, 74.30), (31.70, 74.50), 'Far'),
                  O(2, 'assigned', 1, (31.50, 74.30), (31.52, 74.32), 'Near')]
        plan = b.plan_route(orders, start=(31.49, 74.29))
        kinds = [s['kind'] for s in plan['stops']]
        self.assertEqual(kinds, ['pickup', 'drop', 'drop'])
        self.assertEqual(plan['stops'][0]['orders'], [1, 2])          # ek hi store = ek stop
        self.assertEqual([s['label'] for s in plan['stops'][1:]], ['Near', 'Far'])  # qareeb pehle

    def test_picked_up_orders_skip_pickup(self):
        orders = [O(1, 'picked_up', 1, (31.5, 74.3), (31.6, 74.4)),
                  O(2, 'picked_up', 2, (31.5, 74.3), (31.7, 74.5))]
        plan = b.plan_route(orders)
        self.assertTrue(all(s['kind'] == 'drop' for s in plan['stops']))

    def test_google_url(self):
        orders = [O(1, 'assigned', 1, (31.5, 74.3), (31.6, 74.4)),
                  O(2, 'assigned', 2, (31.51, 74.31), (31.7, 74.5))]
        url = b.plan_route(orders)['google']
        self.assertIn('destination=', url)
        self.assertIn('waypoints=', url)
        self.assertEqual(len(b.plan_route(orders)['stops']), 4)
