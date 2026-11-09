"""
Stock lock tests: do customers ek hi aakhri item order na kar sakein.

Copy this file to app/tests_stock_lock.py and run:
    python manage.py test app.tests_suite.tests_stock_lock
"""
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.customer import store_orders
from app.models import (Category, Customer, CustomerProfile, Inventory, Product, SaleOrder,
                        SaleOrderItem, StockBatch, Warehouse)


class Base(TestCase):
    def setUp(self):
        self.wh = Warehouse.objects.create(name='Main')
        self.cat = Category.objects.create(name='Food')
        self.item1 = self._product('Rice', 300)
        self.cust_user = User.objects.create_user('cust', 'c@x.com', 'secret12')
        self.customer = Customer.objects.create(
            name='Zara', contact_number='03003333333', address='Lahore')
        CustomerProfile.objects.create(customer=self.customer, user=self.cust_user)

    def _product(self, name, price):
        p = Product.objects.create(name=name, category=self.cat, vendor=None, price=Decimal(price),
                                   is_active=True, approval_status='approved')
        Inventory.objects.create(product=p, warehouse=self.wh, stock=50)
        StockBatch.objects.create(product=p, warehouse=self.wh, qty=50, remaining_qty=50,
                                  price=Decimal(price) * Decimal('0.9'), selling_price=Decimal(price))
        return p

    def add(self, product):
        return self.client.post(
            reverse('add_to_cart'), data=json.dumps({'product_id': product.id, 'quantity': 1}),
            content_type='application/json')


class StockLockTests(Base):
    def _cart(self, product, qty):
        return {str(product.id): {'product_id': product.id, 'quantity': qty, 'name': product.name}}

    def test_enough_stock_passes(self):
        self.assertIsNone(store_orders.check_and_lock_stock(self._cart(self.item1, 50), self.wh))

    def test_more_than_stock_is_refused(self):
        err = store_orders.check_and_lock_stock(self._cart(self.item1, 51), self.wh)
        self.assertIn('Not enough stock', err)
        self.assertIn('Available: 50', err)

    def test_pending_orders_are_counted(self):
        # pehle customer ka pending order 48 le chuka hai -> sirf 2 bachay
        order = SaleOrder.objects.create(order_no='WEB-1', customer=self.customer,
                                         warehouse=self.wh, status='pending')
        SaleOrderItem.objects.create(order=order, product=self.item1, qty=48, price=Decimal('300'))
        self.assertIsNone(store_orders.check_and_lock_stock(self._cart(self.item1, 2), self.wh))
        err = store_orders.check_and_lock_stock(self._cart(self.item1, 3), self.wh)
        self.assertIn('Available: 2', err)

    def test_cancelled_order_is_not_counted(self):
        order = SaleOrder.objects.create(order_no='WEB-2', customer=self.customer,
                                         warehouse=self.wh, status='cancelled')
        SaleOrderItem.objects.create(order=order, product=self.item1, qty=48, price=Decimal('300'))
        self.assertIsNone(store_orders.check_and_lock_stock(self._cart(self.item1, 50), self.wh))

    def test_reserved_items_are_not_double_counted(self):
        inv = Inventory.objects.get(product=self.item1, warehouse=self.wh)
        Inventory.objects.filter(pk=inv.pk).update(reserved_stock=10)
        order = SaleOrder.objects.create(order_no='ADM-1', customer=self.customer,
                                         warehouse=self.wh, status='confirmed')
        # reserved item: sirf reserved_stock mein ginti hoti hai
        SaleOrderItem.objects.filter(pk=SaleOrderItem.objects.create(
            order=order, product=self.item1, qty=10, price=Decimal('300')).pk).update(reserved=True)
        self.assertIsNone(store_orders.check_and_lock_stock(self._cart(self.item1, 40), self.wh))
        self.assertIsNotNone(store_orders.check_and_lock_stock(self._cart(self.item1, 41), self.wh))

    def test_same_product_twice_in_cart_is_summed(self):
        cart = {'a': {'product_id': self.item1.id, 'quantity': 30, 'name': 'Rice'},
                'b': {'product_id': self.item1.id, 'quantity': 30, 'name': 'Rice'}}
        self.assertIn('Not enough stock', store_orders.check_and_lock_stock(cart, self.wh))

    def test_place_order_refuses_second_customer(self):
        Inventory.objects.filter(product=self.item1).update(stock=2)
        order = SaleOrder.objects.create(order_no='WEB-3', customer=self.customer,
                                         warehouse=self.wh, status='pending')
        SaleOrderItem.objects.create(order=order, product=self.item1, qty=2, price=Decimal('300'))
        self.client.login(username='cust', password='secret12')
        for _ in range(2):
            self.add(self.item1)
        s = self.client.session
        s['order_verified'] = True
        s.save()
        d = self.client.post(reverse('place_order_direct'), data=json.dumps({'payment_method': 'cod'}),
                             content_type='application/json').json()
        self.assertFalse(d['success'])
        self.assertIn('Not enough stock', d['message'])
        self.assertEqual(SaleOrder.objects.count(), 1)
