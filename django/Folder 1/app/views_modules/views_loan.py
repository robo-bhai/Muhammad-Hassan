"""Purani copy hata di gayi. Asal code: app/backoffice/views_loan.py
(Original _backups/dedupe_2026-11-09/ mein mehfooz ha.)"""
from ..backoffice.views_loan import (  # noqa: F401
    borrower_create,
    borrower_list,
    generate_emi_schedule,
    loan_approve,
    loan_create,
    loan_dashboard,
    loan_detail,
    loan_disburse,
    loan_list,
    loan_make_payment,
    loan_provider_create,
    loan_provider_list,
)
