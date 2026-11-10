"""Purani copy hata di gayi. Asal code: app/customer/views_customer_auth.py
(Original _backups/dedupe_2026-11-09/ mein mehfooz ha.)"""
from ..customer.views_customer_auth import (  # noqa: F401
    auto_place_order,
    customer_login,
    customer_logout,
    customer_register,
    get_client_ip,
    is_valid_phone,
    logger,
    my_account,
    normalize_phone,
    place_order_direct,
    safe_login,
    save_payment_method,
    send_order_otp,
    verify_order_otp,
    verify_order_token,
    verify_otp_later,
)
