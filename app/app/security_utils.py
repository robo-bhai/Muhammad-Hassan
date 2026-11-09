"""Purani copy hata di gayi. Asal code: app/security/security_utils.py
(Original _backups/dedupe_2026-11-09/ mein mehfooz ha.)"""
from .security.security_utils import (  # noqa: F401
    GENERIC_ERROR,
    _key,
    blocked,
    clear_failures,
    client_ip,
    failures,
    generate_password,
    logger,
    phone_digits,
    phones_match,
    register_failure,
    safe_error,
)
