# Language system (English / اردو) — customer, vendor, rider

## How it works (3 layers)
1. **Page text** – `templates/components/i18n.html` replaces English text with Urdu in the browser using the
   dictionary (`Translation` table, edited in Settings → Translations). Source text in templates must be **English**.
2. **Messages written in Python** – `app/middleware/message_i18n.py` translates flash messages
   (`messages.success/error/...`) at render time using `app/i18n/portal_messages.py`.
   Messages with names/numbers use `{}` patterns, e.g. `('Order #{} placed!', 'آرڈر #{} دے دیا گیا!')`.
3. **Switcher + RTL + fonts** – `components/lang_switch.html`, cookie `erp_lang`, Jameel Noori Nastaleeq / Noto Naskh.

## Sentences with variables — `{% t %}`
The browser translator cannot match a sentence that contains a variable. Use the tag instead:

    {% load portal_i18n %}
    {% t "You are a Pro member until {}." active.ends_on|date:"d M Y" %}
    {% t "To see new orders, go <b>Online</b> using the switch above." %}

Add the same English text with its Urdu to `app/i18n/portal_messages.py` (same number of `{}` in both).
Values are HTML-escaped; the text itself may contain `<b>`, `<br>`, `<code>`.

## Add a new text
- Template text: write it in English. Add `('English', 'اردو', '')` to `app/i18n/i18n_portal_defaults.py`
  (or add it in Settings → Translations). New entries load with the "Seed" button in Settings → Translations.
- Python message: write it in English in the view; add one line to `portal_messages.py`. Keep the same number of `{}` in both texts.

## Check your work
    python manage.py check_translations                 # text without Urdu
    python manage.py check_translations --roman         # Roman-Urdu text that should be English
    python manage.py check_translations --strict        # for CI (exit code 1)

## Style rules for Urdu
- Short, everyday words (دکان، آرڈر، کارٹ، والٹ). Keep brand/technical words: OTP, COD, QR, PDF.
- Numbers, phone, order numbers, money stay in Latin digits (`Rs. 1,200`).
- Never put Roman Urdu in templates or Python messages.
