"""
Shop ke Support & Trust pages (sidebar SUPPORT section se link hote hain):
FAQ, Help Center, About Us, Terms, Privacy, Return Policy.

Koi model nahi: company ki details (naam, phone, email, address) context processor se aati hain.
Return/refund ke din neeche constants se badalte hain.
"""
from django.shortcuts import render

RETURN_WINDOW_DAYS = 7      # kitne din mein return request ho sakti hai
REFUND_DAYS = "3-5"         # refund process hone ke working days


def _page(request, template):
    return render(request, template, {
        'return_window_days': RETURN_WINDOW_DAYS,
        'refund_days': REFUND_DAYS,
    })


def faq(request):
    return _page(request, 'customer_portal/info/faq.html')


def help_center(request):
    return _page(request, 'customer_portal/info/help.html')


def about_us(request):
    return _page(request, 'customer_portal/info/about.html')


def terms(request):
    return _page(request, 'customer_portal/info/terms.html')


def privacy(request):
    return _page(request, 'customer_portal/info/privacy.html')


def return_policy(request):
    return _page(request, 'customer_portal/info/returns.html')
