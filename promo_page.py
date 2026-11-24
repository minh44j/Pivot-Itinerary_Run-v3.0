"""
The "Thanks for choosing Pivot" promo page that sits between the itinerary and the Terms page (approved 2026-11-18).

Pure module (stdlib only), so the offline test suite can import it. It builds (a) the personal coupon code and (b) the
page's HTML; `generate_itinerary_v3` renders it to its own one-page PDF and splices it in before the Terms page.

THE COUPON CODE  (e.g. HDUR738HE: 4 letters, 3 digits, 2 letters)
  Derived from the booking's reference(s) with a SECRET (GitHub secret PROMO_SECRET) using HMAC-SHA256. So:
    * the same booking always gets the same code (a re-issue does not mint a second one);
    * staff can re-compute any code from a PNR (tools/verify_coupon.py) and check what a client quotes;
    * nobody without the secret can invent a valid one, although this repo is public.
  Without the secret NO promo page is printed at all — an unverifiable code would be worse than none.
  No I, O, L and no 0, 1, so a code cannot be misread when typed or spoken.
"""
import base64
import hashlib
import hmac
import os
import re

# ── the offer (change here, and the page + its terms follow) ───────────────────
PROMO_PCT = 5                      # percent off
PROMO_MIN_SAR = 1000               # services must be MORE than this
PROMO_MAX_SAR = 200                # largest discount per coupon
PROMO_VALID_DAYS = 90

COMPANY_WHATSAPP = "+966 53 925 0410"
PROMO_ADDRESS = "2762 Ibn Al Anbari Street, Al Amal District, Riyadh, KSA"

_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ"        # no I, O, L
_DIGITS = "23456789"                        # no 0, 1
CODE_RE = re.compile(rf"^[{_LETTERS}]{{4}}[{_DIGITS}]{{3}}[{_LETTERS}]{{2}}$")


def promo_key(refs) -> str:
    """Order- and case-insensitive key for a booking, so a split-carrier booking gets one code however it is listed."""
    return "|".join(sorted({re.sub(r"[^A-Z0-9]", "", str(r).upper()) for r in (refs or []) if r is not None} - {""}))


def coupon_code(refs, secret) -> str:
    """The personal code for a booking, or '' when there is no secret or no usable reference."""
    key = promo_key(refs)
    if not key or not secret:
        return ""
    d = hmac.new(str(secret).encode("utf-8"), key.encode("utf-8"), hashlib.sha256).digest()
    return ("".join(_LETTERS[b % len(_LETTERS)] for b in d[:4])
            + "".join(_DIGITS[b % len(_DIGITS)] for b in d[4:7])
            + "".join(_LETTERS[b % len(_LETTERS)] for b in d[7:9]))


def promo_eligible(data: dict, secret) -> bool:
    """A promo page goes only on a normal confirmation (never on a revised/rescheduled/delayed draft — nobody wants an
    advert on a 'your flight changed' document) and only when a secret exists to make the code verifiable."""
    return bool(secret) and (data.get("doc_status") or "confirmed").lower() == "confirmed"


TERMS = (f"*Terms and conditions apply. The {PROMO_PCT}% discount applies only to purchases of services of more than "
         f"SAR {PROMO_MIN_SAR:,}, with a maximum discount of SAR {PROMO_MAX_SAR} per coupon. Valid for one use on one "
         f"Pivot Travel Management service, for {PROMO_VALID_DAYS} days from issue. Not applicable to low-cost carrier "
         "flight tickets. Cannot be combined with other offers or exchanged for cash. Subject to availability and "
         "confirmation. Pivot Travel Management reserves the right to modify, suspend, deny or cancel this offer at any "
         "time, without prior notice, as the situation requires.")


import icons as _hero   # Heroicons (embedded set); replaced the hand-drawn contact icons on 2026-11-24


def _ic(name):
    return _hero.icon(name, size=22, color="#1d1d1f", stroke=1.6)


_PHONE = _ic("phone")
_MAIL = _ic("envelope")
_WA = _ic("chat-bubble-left-right")      # Heroicons has no WhatsApp logo; a chat bubble marks the WhatsApp number
_PIN = _ic("map-pin")


def background_b64(project_dir=None) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (project_dir, here):
        if base:
            p = os.path.join(base, "assets", "promo", "promo_bg.jpg")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    return base64.b64encode(f.read()).decode("ascii")
    return ""


def promo_html(code: str, font_css: str, logo_b64: str, bg_b64: str, hotline: str, email: str, website: str) -> str:
    """One A4 page, full bleed. Everything but the picture is live text (Inter, regular-weight headings)."""
    tile = (f'<div class="tile"><img src="data:image/png;base64,{logo_b64}" alt="Pivot Travel Management"></div>'
            if logo_b64 else "")
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Pivot — travel services</title><style>{font_css}
:root{{--ink:#1d1d1f}}
*{{box-sizing:border-box;margin:0;padding:0}} @page{{size:A4;margin:0}}
html{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
body{{font-family:'Inter',-apple-system,Arial,sans-serif;font-optical-sizing:auto;background:#fdf7f4;color:var(--ink)}}
.page{{width:210mm;height:297mm;position:relative;overflow:hidden;background:#fdf7f4}}
.bg{{position:absolute;left:0;top:32px;width:794px;height:1059px;background:url(data:image/jpeg;base64,{bg_b64}) center/100% 100% no-repeat}}
.abs{{position:absolute;left:45px;width:704px}}
.brand{{top:44px;display:flex;align-items:center;gap:12px}}
.tile{{width:46px;height:46px;border-radius:11px;background:linear-gradient(160deg,#323234,#0e0e0f);display:flex;align-items:center;justify-content:center;outline:1px solid rgba(201,168,76,.6);outline-offset:-1px}}
.tile img{{height:27px;width:auto}} .wm{{font-size:21px;font-weight:400;letter-spacing:-.4px;line-height:1}} .wm b{{font-weight:700}}
h1{{top:112px;font-size:51px;line-height:1.04;font-weight:400;letter-spacing:-1.8px}} h1 em{{font-style:normal;color:#a87a18}}
.msg{{top:322px;padding-left:17px;border-left:3px solid #b98a1f;width:690px;left:45px}}
.msg h3{{font-size:20px;font-weight:400;letter-spacing:-.3px;line-height:1.25}}
.msg p{{font-size:15.5px;line-height:1.45;color:#2a2a2d;margin-top:5px}}
.msg .tok{{font-size:17px;font-weight:800;letter-spacing:-.3px;margin-top:8px}} .chip{{background:#f6e2a0;color:#85660f;border-radius:6px;padding:1px 7px;font-weight:800}}
.row1{{top:878px;height:52px;display:flex;align-items:center;gap:20px}}
.use{{flex:1;font-size:18px;line-height:1.4;font-weight:500}} .use b{{font-weight:800;letter-spacing:1.2px;font-size:18px}}
.cta{{width:200px;height:52px;border-radius:26px;background:linear-gradient(180deg,#f8dc8e,#d6a94c);display:flex;align-items:center;justify-content:center;gap:8px;font-size:17px;font-weight:800;color:var(--ink);text-decoration:none}}
.hr{{height:1px;background:#e3dbd3}}
.row2{{top:962px;display:flex;align-items:center;justify-content:space-between}}
.ci{{display:flex;align-items:center;gap:10px;font-size:15px;font-weight:650;white-space:nowrap}}
.sep{{width:1.5px;height:26px;background:#d9d2cb}}
.addr{{top:1022px;display:flex;align-items:center;justify-content:center;gap:10px;font-size:14.5px;font-weight:600}}
.tc{{top:1062px;text-align:center;font-size:7.5px;line-height:1.45;color:#8a8f96}}
</style></head><body><div class="page"><div class="bg"></div>
<div class="abs brand">{tile}<div class="wm"><b>Pivot</b> Travel Management</div></div>
<h1 class="abs">Thanks for choosing<br>Pivot as your<br><em>travel partner.</em></h1>
<div class="msg abs"><h3>Wishing you a pleasant and comfortable journey!</h3>
<p>Whether you need a private chauffeur, airport transfers, corporate or group travel arrangements, premium Umrah packages, visa assistance or any other travel service, Pivot is here to take care of it.</p>
<div class="tok">As a token of appreciation, enjoy <span class="chip">{PROMO_PCT}% OFF*</span> your next booking with us.</div></div>
<div class="abs row1"><div class="use">Use coupon code <b>{code}</b><br>on your next booking.</div>
<a class="cta" href="mailto:{email}">Contact Us <span>&rarr;</span></a></div>
<div class="abs hr" style="top:948px"></div>
<div class="abs row2"><div class="ci">{_PHONE}{hotline}</div><div class="sep"></div><div class="ci">{_MAIL}{email}</div><div class="sep"></div><div class="ci">{_WA}{COMPANY_WHATSAPP}</div></div>
<div class="abs hr" style="top:1006px"></div>
<div class="abs addr">{_PIN}{PROMO_ADDRESS}</div>
<div class="abs tc">{TERMS}</div>
</div></body></html>'''
