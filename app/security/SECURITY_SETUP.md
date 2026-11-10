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
    "app.middleware.account_lockout.AccountLockoutMiddleware",    # NEW: account lockout
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

Tests: `python manage.py test app.tests_suite.tests_security_totp`

## 4. Abhi bhi baqi (agla step)
* APIKey banti hain lekin koi API unhe check nahi karti; api_rate_limit enforce nahi hota.
* Per-account (username) lockout nahi, sirf per-IP (jaan boojh kar, taake koi dusre ko lock na kare).
* Content-Security-Policy: pehle SECURITY_CSP_REPORT_ONLY se test karein, templates mein inline scripts hain.

## 5. Hacker ko rokna, aapko batana, record rakhna
| Kaam | Kaise | Kahan dekhein |
|---|---|---|
| Galat password baar baar | IP khud block (max_login_attempts, lockout_time) | Security -> IP Blacklist |
| Aap ko inform | Email: Security Settings ka `alert_email` (khali ho to superusers ko). Ek hi IP ki mail 10 min mein ek. | Inbox + Security -> Alerts |
| Hacker ka record | IP, tried usernames, browser/tool, pehli/aakhri koshish, har login attempt | Security -> Alerts, Security -> Logs, LoginAttempt |
| Har badlao ka record | AuditLogMiddleware (kaun, kahan se, kya) | Security -> Logs |

Email ke liye settings.py mein EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL zaroori hain.
Test: `python manage.py test app.tests_suite.tests_security_alerts`

## 6. Account lockout (username)
IP block sirf ek IP rokta hai. Agar hacker kai IP se ek hi account par guess kare, to account khud lock ho jata hai.
* Lock: `max(max_login_attempts x 2, 6)` galat logins, `lockout_time` minutes ke andar, **kisi bhi IP se**. Sahi login ya admin unlock count zero kar deta hai.
* Lock mein sahi password bhi qubool nahi (HTTP 429). Message mojood aur na-mojood username ke liye ek jaisa hai (usernames ka pata nahi chalta).
* Owner ko email (ek lock par ek), aur Security -> Alerts mein entry (IPs, browser/tool ke saath).
* Unlock: `/security/locked-accounts/`. History delete nahi hoti.
* IP whitelist wali IP (office) kabhi lock nahi hoti, taake hacker owner ko bahar na nikal sake.
* settings.py MIDDLEWARE mein `"app.middleware.account_lockout.AccountLockoutMiddleware"` AuthenticationMiddleware ke baad, TwoFactorMiddleware se pehle daalein.
* Test: `python manage.py test app.tests_suite.tests_account_lock`

## 7. Naye device se login ka alert
Kisi user ka account pehli dafa naye browser/OS se khule to user ko email jati hai ("Was this you?") jis mein device, IP aur waqt hota hai. Security -> Alerts mein low-severity entry bhi banti hai.
* Device = browser + OS (jaise Chrome|Windows). Browser update par alert nahi aata.
* Account ka sab se pehla login kabhi flag nahi hota. Email na ho to sirf alert entry banti hai.
* Owner ko har user ke har naye device ki email nahi jati (shor se bachne ke liye); sirf asli khatron ki jati hai.
* Band karne ke liye settings.py mein `SECURITY_NEW_DEVICE_ALERTS = False`. Koi middleware nahi chahiye - login signal se khud chalta hai.
* Test: `python manage.py test app.tests_suite.tests_new_device`

## 8. Active sessions (kahan kahan login hai)
Page: `/security/sessions/` (har logged-in user ke liye). Har login ab SessionLog mein likha jata hai (pehle koi row banti hi nahi thi, is liye "active sessions" hamesha 0 dikhte the).
* User apni sab devices dekhta hai (browser, OS, IP, kab login, aakhri activity), aur ek ko ya "baqi sab devices" ko sign-out kar sakta hai. Current device ko yahan se sign-out nahi kar sakta (Logout button use kare).
* Sign-out server par session delete karta hai, to doosri device agle click par login page par chali jati hai.
* Security admin `?all=1` se sab users ke sessions dekh kar kisi ko bhi nikal sakta hai.
* Session keys kabhi page ya URL mein nahi aati; sirf row id. Doosre ka session koi chhoo nahi sakta.
* Zaroori: `SESSION_ENGINE` database/cache/file ho (Django default theek hai). `signed_cookies` engine mein remote sign-out mumkin nahi.
* Sign-out ke POST ka record audit log mein khud aata hai.
* Test: `python manage.py test app.tests_suite.tests_active_sessions`
