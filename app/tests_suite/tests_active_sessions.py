"""
Active sessions page + remote sign-out tests.

Run:  python manage.py test app.tests_suite.tests_active_sessions
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase

from app.models import SessionLog


class ActiveSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("farah", "f@example.com", "pw-12345-Ab")
        self.other = User.objects.create_user("omar", "o@example.com", "pw-12345-Ab")
        self.a, self.b = Client(), Client()
        self.a.force_login(self.user)
        self.b.force_login(self.user)

    def _rows(self, user=None):
        return SessionLog.objects.filter(user=user or self.user, is_active=True)

    def test_every_login_is_recorded(self):
        self.assertEqual(self._rows().count(), 2)

    def test_page_lists_own_sessions_and_hides_session_keys(self):
        r = self.a.get("/security/sessions/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["sessions"]), 2)
        self.assertEqual(sum(1 for s in r.context["sessions"] if s["current"]), 1)
        for row in self._rows():
            self.assertNotIn(row.session_key, r.content.decode())

    def test_sign_out_other_devices(self):
        self.a.post("/security/sessions/", {"action": "revoke_others"})
        self.assertEqual(self._rows().count(), 1)
        r = self.b.get("/security/sessions/")               # device B was signed out
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r["Location"])
        self.assertEqual(self.a.get("/security/sessions/").status_code, 200)   # A still in

    def test_sign_out_one_device_but_never_the_current_one(self):
        cur = self.a.session.session_key
        mine = self._rows().get(session_key=cur)
        self.a.post("/security/sessions/", {"action": "revoke", "id": mine.pk})
        self.assertEqual(self._rows().count(), 2)           # refused
        other = self._rows().exclude(session_key=cur).get()
        self.a.post("/security/sessions/", {"action": "revoke", "id": other.pk})
        self.assertEqual(self._rows().count(), 1)

    def test_cannot_touch_someone_elses_session(self):
        c = Client(); c.force_login(self.other)
        victim = self._rows().first()
        c.post("/security/sessions/", {"action": "revoke", "id": victim.pk})
        self.assertEqual(self._rows().count(), 2)

    def test_admin_can_see_all_and_sign_out_anyone(self):
        admin = User.objects.create_superuser("boss", "b@example.com", "pw-12345-Ab")
        c = Client(); c.force_login(admin)
        r = c.get("/security/sessions/?all=1")
        self.assertGreaterEqual(len(r.context["sessions"]), 3)
        victim = self._rows().first()
        c.post("/security/sessions/?all=1", {"action": "revoke", "id": victim.pk})
        self.assertEqual(self._rows().count(), 1)

    def test_logout_closes_the_record(self):
        self.b.get("/logout/")
        self.assertEqual(self._rows().count(), 1)

    def test_login_required(self):
        self.assertEqual(Client().get("/security/sessions/").status_code, 302)
