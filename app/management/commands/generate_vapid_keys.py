"""python manage.py generate_vapid_keys  ->  Web Push ki VAPID keys banata hai (cryptography chahiye)."""
import base64

from django.core.management.base import BaseCommand


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class Command(BaseCommand):
    help = 'Web Push ke liye VAPID public/private key banata hai'

    def handle(self, *args, **options):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            self.stderr.write('cryptography install nahi ha (pip install pywebpush usay saath le aata ha).')
            return
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, 'big')
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.stdout.write('Ye 3 lines settings.py mein (ya environment variables mein) rakhein:\n')
        self.stdout.write(f"VAPID_PUBLIC_KEY = '{_b64(public)}'")
        self.stdout.write(f"VAPID_PRIVATE_KEY = '{_b64(private)}'")
        self.stdout.write("VAPID_CONTACT_EMAIL = 'aap-ki-email@example.com'")
        self.stdout.write('\nPrivate key kisi ko na dikhayein aur GitHub par na daalein.')
