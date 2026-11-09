"""Purani copy hata di gayi. Asal code: app/backoffice/views_subscription.py
(Original _backups/dedupe_2026-11-09/ mein mehfooz ha.)"""
from .backoffice.views_subscription import (  # noqa: F401
    check_subdomain_availability,
    client_create,
    client_delete,
    client_detail,
    client_edit,
    client_reactivate,
    client_renew,
    client_suspend,
    clients_list,
    subscription_dashboard,
    subscription_expired,
    subscription_plan_create,
    subscription_plan_delete,
    subscription_plan_edit,
    subscription_plans_list,
)
