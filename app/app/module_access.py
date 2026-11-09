"""Purani copy hata di gayi. Asal code: app/middleware/module_access.py
(Original _backups/dedupe_2026-11-09/ mein mehfooz ha.)"""
from .middleware.module_access import (  # noqa: F401
    ALWAYS_OPEN,
    ModuleAccessMiddleware,
    _PAGE,
    _url_prefixes,
    module_for_path,
)
