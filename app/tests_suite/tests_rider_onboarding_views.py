"""Rider onboarding (documents + approval) aur shift booking ke view-level tests."""
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import RiderDocument, RiderProfile, RiderShift, RiderShiftBooking

TMP_MEDIA = tempfile.mkdtemp()


def png():
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buf, 'PNG')
    return SimpleUploadedFile('doc.png', buf.getvalue(), content_type='image/png')


def make_rider(status='approved', n=1):
    phone = f'+9733300000{n}'
    u = User.objects.create_user('rider_' + phone[1:], password='pw-123456')
    return RiderProfile.objects.create(user=u, name=f'R{n}', phone=phone, approval_status=status)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class DocumentsAndApprovalTests(TestCase):
    def setUp(self):
        self.rider = make_rider('pending')
        self.admin = User.objects.create_superuser('boss', 'b@example.com', 'pw-123456')
        self.future = (timezone.localdate() + timedelta(days=365)).isoformat()

    def upload_all(self):
        self.client.force_login(self.rider.user)
        for kind in ('cpr', 'license', 'vehicle', 'photo'):
            data = {'kind': kind, 'file': png(), 'number': 'AB-1234', 'expiry': self.future}
            self.client.post(reverse('rider_documents'), data)

    def test_pending_rider_cannot_go_online(self):
        self.client.force_login(self.rider.user)
        self.client.post(reverse('rider_toggle_online'))
        self.rider.refresh_from_db()
        self.assertFalse(self.rider.is_online)

    def test_approved_rider_can_go_online(self):
        r = make_rider('approved', 2)
        self.client.force_login(r.user)
        self.client.post(reverse('rider_toggle_online'))
        r.refresh_from_db()
        self.assertTrue(r.is_online)

    def test_upload_creates_pending_documents(self):
        self.upload_all()
        self.assertEqual(RiderDocument.objects.filter(rider=self.rider, status='pending').count(), 4)

    def test_expired_document_is_refused(self):
        self.client.force_login(self.rider.user)
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.client.post(reverse('rider_documents'), {'kind': 'cpr', 'file': png(), 'number': 'AB-1234', 'expiry': past})
        self.assertFalse(RiderDocument.objects.filter(rider=self.rider).exists())

    def test_non_image_is_refused(self):
        self.client.force_login(self.rider.user)
        bad = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        self.client.post(reverse('rider_documents'), {'kind': 'photo', 'file': bad})
        self.assertFalse(RiderDocument.objects.filter(rider=self.rider).exists())

    def test_approving_all_documents_approves_rider(self):
        self.upload_all()
        self.client.force_login(self.admin)
        for doc in RiderDocument.objects.filter(rider=self.rider):
            self.client.post(reverse('rider_review', args=[self.rider.pk]),
                             {'action': 'doc_approve', 'doc_id': doc.pk})
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.approval_status, 'approved')

    def test_reject_needs_reason(self):
        self.upload_all()
        doc = RiderDocument.objects.filter(rider=self.rider).first()
        self.client.force_login(self.admin)
        self.client.post(reverse('rider_review', args=[self.rider.pk]), {'action': 'doc_reject', 'doc_id': doc.pk})
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'pending')
        self.client.post(reverse('rider_review', args=[self.rider.pk]),
                         {'action': 'doc_reject', 'doc_id': doc.pk, 'reason': 'Blurry'})
        doc.refresh_from_db()
        self.assertEqual((doc.status, doc.reject_reason), ('rejected', 'Blurry'))

    def test_document_file_is_private(self):
        self.upload_all()
        doc = RiderDocument.objects.filter(rider=self.rider).first()
        url = reverse('rider_document_file', args=[doc.pk])
        self.client.force_login(self.rider.user)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(make_rider('approved', 3).user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_only_admin_reviews(self):
        self.client.force_login(self.rider.user)
        resp = self.client.post(reverse('rider_review', args=[self.rider.pk]), {'action': 'rider_approve'})
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.approval_status, 'pending')
        self.assertEqual(resp.status_code, 302)


class ShiftBookingTests(TestCase):
    def setUp(self):
        self.r1, self.r2 = make_rider('approved', 1), make_rider('approved', 2)
        self.day = timezone.localdate() + timedelta(days=2)
        from datetime import time
        self.shift = RiderShift.objects.create(date=self.day, start_time=time(12), end_time=time(16), capacity=1)
        self.overlap = RiderShift.objects.create(date=self.day, start_time=time(15), end_time=time(19), capacity=5)

    def book(self, rider, shift):
        self.client.force_login(rider.user)
        return self.client.post(reverse('rider_shift_book', args=[shift.pk]))

    def count(self, rider, shift):
        return RiderShiftBooking.objects.filter(rider=rider, shift=shift, status='booked').count()

    def test_book_and_capacity(self):
        self.book(self.r1, self.shift)
        self.assertEqual(self.count(self.r1, self.shift), 1)
        self.book(self.r2, self.shift)                      # full
        self.assertEqual(self.count(self.r2, self.shift), 0)

    def test_overlapping_shift_refused(self):
        self.book(self.r1, self.shift)
        self.book(self.r1, self.overlap)
        self.assertEqual(self.count(self.r1, self.overlap), 0)

    def test_pending_rider_cannot_book(self):
        p = make_rider('pending', 3)
        self.book(p, self.overlap)
        self.assertEqual(self.count(p, self.overlap), 0)

    def test_cancel_and_rebook_frees_seat(self):
        self.book(self.r1, self.shift)
        self.client.post(reverse('rider_shift_cancel', args=[self.shift.pk]))
        self.assertEqual(self.count(self.r1, self.shift), 0)
        self.book(self.r2, self.shift)
        self.assertEqual(self.count(self.r2, self.shift), 1)
        self.book(self.r1, self.shift)                      # ab full
        self.assertEqual(self.count(self.r1, self.shift), 0)

    def test_late_cancel_refused(self):
        from datetime import time
        soon = timezone.localtime() + timedelta(minutes=30)
        s = RiderShift.objects.create(date=soon.date(), start_time=(soon + timedelta(hours=1)).time().replace(second=0, microsecond=0),
                                      end_time=time(23, 59), capacity=5)
        RiderShiftBooking.objects.create(shift=s, rider=self.r1)
        self.client.force_login(self.r1.user)
        self.client.post(reverse('rider_shift_cancel', args=[s.pk]))      # 2 ghante ka rule: 1.5 ghante bacha hai
        self.assertEqual(self.count(self.r1, s), 1)
