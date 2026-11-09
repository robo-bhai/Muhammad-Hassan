# Security upgrade - wiring (settings.py)

Zip mein settings.py nahi tha, is liye yeh lines apni settings.py mein daalni hain.

## 1. MIDDLEWARE (is order mein)
```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "app.middleware.security_headers.SecurityHeadersMiddleware",   # NEW
    ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "app.middleware.middleware.SecurityMiddleware",               # IP block + session timeout (pehle se)
    "app.middleware.security_2fa.TwoFactorMiddleware",            # pehle se (ab authenticator bhi)
    "app.middleware.password_expiry.PasswordExpiryMiddleware",    # NEW
    "app.middleware.audit_log.AuditLogMiddleware",                # NEW
    ...
]
```

## 2. Production settings (HTTPS server par)
```python
DEBUG = False
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]          # code mein na rakhein
DATA_ENCRYPTION_KEY = os.environ["DATA_ENCRYPTION_KEY"]
ALLOWED_HOSTS = ["your-domain.com"]
CSRF_TRUSTED_ORIGINS = ["https://your-domain.com"]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")   # sirf agar nginx/proxy ke peeche hain
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURITY_TRUSTED_PROXY_COUNT = 1                      # proxy ke peeche ho to

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
CACHES = {...}   # brute-force / OTP limits cache par chalte hain: production mein Redis/Memcached
                 # (LocMem har process ka alag hota hai)
```

## 3. Naya kya hai
| Feature | File | URL |
|---|---|---|
| Authenticator app 2FA (Google/Microsoft Authenticator) + 10 backup codes | security/totp.py, security/views_totp.py | /security/authenticator/ |
| Security headers (nosniff, HSTS, Referrer, Permissions, no-store, optional CSP) | middleware/security_headers.py | - |
| Password expiry (SecuritySettings.password_expiry_days) | middleware/password_expiry.py | forces /security/change-password/ |
| Audit trail (har POST/PUT/DELETE aur 403, sirf field names, values nahi) | middleware/audit_log.py | Security -> Logs |

Authenticator ke liye "Two-factor authentication" Security Settings mein on honi chahiye.
Authenticator wale users ko email OTP ke bajaye app code poocha jata hai. Naya migration nahi chahiye.

Tests: `python manage.py test app.tests_security_totp`

## 4. Abhi bhi baqi (agla step)
* APIKey banti hain lekin koi API unhe check nahi karti; api_rate_limit enforce nahi hota.
* Per-account (username) lockout nahi, sirf per-IP (jaan boojh kar, taake koi dusre ko lock na kare).
* Content-Security-Policy: pehle SECURITY_CSP_REPORT_ONLY se test karein, templates mein inline scripts hain.
