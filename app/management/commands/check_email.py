"""Email setup ki jaanch:  python manage.py check_email [--to someone@example.com]

Bina --to: sirf report (kaun sa backend, kaunsi settings maujood hain; secrets ki qeemat kabhi nahi dikhata).
--to ke saath: ek test email bhejta hai aur asli error dikhata hai.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


def _flag(value):
    return 'SET' if value else 'MISSING'


class Command(BaseCommand):
    help = 'Email configuration check (aur optional test email)'

    def add_arguments(self, parser):
        parser.add_argument('--to', help='Is address par test email bhejein')

    def handle(self, *args, **opts):
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f'EMAIL_BACKEND        : {backend}')
        self.stdout.write(f'BREVO_API_KEY        : {_flag(getattr(settings, "BREVO_API_KEY", ""))}')
        self.stdout.write(f'BREVO_SENDER_EMAIL   : {_flag(getattr(settings, "BREVO_SENDER_EMAIL", ""))}')
        self.stdout.write(f'BREVO_SENDER_NAME    : {getattr(settings, "BREVO_SENDER_NAME", "") or "MISSING"}')
        self.stdout.write(f'DEFAULT_FROM_EMAIL   : {settings.DEFAULT_FROM_EMAIL or "MISSING"}')

        if 'console' in backend:
            self.stdout.write(self.style.WARNING(
                'Backend = console: emails sirf server log mein print hoti hain, kisi ko jati nahi. '
                'GitHub Secrets BREVO_API_KEY aur BREVO_SENDER_EMAIL set karein.'))
        elif 'brevo' in backend.lower():
            try:
                import importlib
                mod, _, cls = backend.rpartition('.')
                getattr(importlib.import_module(mod), cls)
                self.stdout.write(self.style.SUCCESS('Brevo backend module load ho gaya.'))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'Brevo backend load nahi hua: {exc}'))

        to = opts.get('to')
        if not to:
            return
        try:
            n = send_mail('Test email', 'Agar yeh mil gayi to email setup theek hai.',
                          settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
            self.stdout.write(self.style.SUCCESS(f'Test email bheji ({n}) -> {to}'))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'Test email FAIL: {exc}'))
