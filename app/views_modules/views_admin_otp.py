"""Purani copy hata di gayi. Asal code: app/security/views_admin_otp.py
(Original _backups/dedupe_2026-11-09/ mein mehfooz ha.)"""
from ..security.views_admin_otp import (  # noqa: F401
    get_client_ip,
    otp_detail,
    otp_management,
    otp_quick_generate,
    otp_regenerate,
    superuser_required,
)
