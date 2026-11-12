# Customer Referral (Dost ko bulao)

Customer apna code / link dost ko bhejta hai. Dost us link se register kare aur uska **pehla order delivered**
ho jaye (minimum amount ka) to dono ko wallet me reward milta hai. Reward sirf wallet me jata hai (cash nahi).

## Chalu kaise karen
1. `python manage.py migrate` (migration `0072_customer_referral`; purane customers ko code mil jata hai).
2. Admin > Settings > Shop: **Wallet** ON karen (reward wallet me jata hai) phir **Customer referral** ON karen.
   Default band hai, is liye deploy se kisi shop par asar nahi.
3. Isi tab me raqmen: referrer ka reward, naye dost ka reward, minimum first order, referrer ka mahine ka cap
   (0 = koi had nahi).

## Flow
| Kab | Kya hota hai | Code |
|---|---|---|
| Dost link kholta hai `/shop/r/<CODE>/` | Code session me; register page par bheja jata hai | `views_customer_auth.referral_landing` |
| Register | `Referral` (pending) banta hai. Khud ko refer, galat code, ya doosra referral chup-chaap ignore | `referrals.create_pending` |
| Order delivered | Pehla delivered order, minimum amount ka, fraud checks pass -> dono ko wallet credit | `offers.sync_status` -> `referrals.award_for_order` |
| Cancel / return | Kuch nahi (reward pehle diya hi nahi gaya) | |

Wallet kind: referrer ka `referral`, dost ka `refbonus`. (WalletTransaction par `(order, kind)` unique hai,
is liye ek order par dono ka reward alag kind se hota hai.)

## Fraud checks (`referrals._blocked_reason`)
- Referee ka phone verify na ho -> **pending rehta hai** (reward nahi). Jaise hi phone verify hota hai
  (`referrals.award_on_phone_verified`, teen OTP jagahon se) aur referee ka pehla order pehle se delivered hai,
  reward khud mil jata hai. Delivered order na ho to agle delivered order par milta hai.
- Same phone / same address / same device (IP + browser ka HMAC hash; asal IP save nahi hota) -> **rejected**, wajah ke sath.
- Referrer ka account band ya mahine ka cap poora -> **rejected**.

## Admin
Admin > Referrals: filter (status), search (naam, phone, code). Actions:
- **Approve**: fraud checks / minimum / cap ke baghair reward (referee ka pehla delivered order zaroori).
- **Reject**: sirf pending ko. Jis ka reward ho chuka wapas nahi hota (wallet adjustment se hi sudhar sakte hain).

## Customer UI
Account page par "Invite a friend" card: code, link, copy, WhatsApp share, stats. Flag ya wallet band ho to nahi dikhta.

## Tests
`python manage.py test app.tests_suite.tests_referral`
