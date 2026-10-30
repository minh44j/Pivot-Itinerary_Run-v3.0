#!/usr/bin/env python3
"""
Pivot Travel Management — Itinerary PDF Generator v4  (Apple-guidelines redesign, 2026-10-30)

Layout: light page, no dark header/footer bands · one large PNR reference · grouped traveller
list · boarding-pass flight cards (perforation + notches) · per-leg passenger table with the
seat as the boldest figure · light footer with page numbers.
Type: Inter only (variable, optical sizing) — inlined from assets/fonts so rendering needs no
network. Gold #c9a84c is an accent/ornament; gold TEXT is #85660f (5.4:1 on white).

Usage:
    python3 generate_itinerary_v3.py --data '<json>' --out-dir '/path/'
"""

import json, sys, os, tempfile, base64, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from datetime import datetime


# ── Logo ──────────────────────────────────────────────────────────────────────
def _logo_b64(project_dir: str = None) -> str:
    candidates = []
    if project_dir:
        candidates += [
            Path(project_dir) / "logo.png",
            Path(project_dir) / "Claude Pivot Logo.png",
            Path(project_dir) / "pivot_logo.png",
        ]
    candidates += [
        Path(__file__).parent / "logo.png",
        Path(__file__).parent / "Claude Pivot Logo.png",
        Path(__file__).parent / "pivot_logo.png",
    ]
    for p in candidates:
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode()
    return ""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _weekday_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str.strip(), "%d %b %Y")
        return dt.strftime("%A, %d %b %Y")
    except Exception:
        return date_str


def booking_refs(data: dict) -> list:
    """Every airline reference on the booking, in itinerary order.

    Almost always a single value. A SPLIT-CARRIER booking — two airlines sold
    under one agency reference, e.g. Flyadeal out / Saudia back on Akbar booking
    AS261347760 — carries one reference per airline, and a traveller cannot check
    in for a leg whose reference is not on their document. Extractors put the
    list on data["pnrs"]; anything that predates that key falls back to the
    single data["pnr"], so single-reference documents are unaffected.
    """
    refs = [str(r).strip() for r in (data.get("pnrs") or []) if str(r).strip()]
    if not refs:
        one = str(data.get("pnr") or "").strip()
        refs = [one] if one else []
    out = []
    for r in refs:
        if r.upper() not in {x.upper() for x in out}:
            out.append(r)
    return out



def _title_name(name: str) -> str:
    # Title Case: first letter of each word upper, rest lower (e.g. "MR. NURHAK COSKUN" -> "Mr. Nurhak Coskun")
    return " ".join(w.capitalize() for w in name.split())


def _na(v) -> str:
    # Any empty / "Not specified" field is displayed as "N/A".
    if v is None:
        return "N/A"
    s = str(v).strip()
    if s == "" or s.lower() == "not specified":
        return "N/A"
    return s


def _norm_bag(v: str, pax_type: str = "") -> str:
    # Baggage values show weight only. "1 pc 7kg + personal item 3kg" -> "7kg + 3kg".
    # Multiple weights joined with " + ". Piece-only values (no kg) -> "<n>Pcs". No dimensions/extras.
    if not v:
        return "N/A"
    s = v.strip()
    # "None" is a VALUE THE SOURCE ACTUALLY PRINTS, not a Python artifact: aJet
    # writes "Total Check-in Baggage None" / "Cabin Baggage None" on a leg that
    # carries no allowance (real booking 4B0NA3, 2026-08-15). Rendering it
    # verbatim put the word "None" on a client's flight card, which reads like a
    # software fault. It means "not stated" -> N/A, same as an empty value.
    if s.lower() in ("not specified", "none", "n/a", "-"):
        return "N/A"
    # A fare can state SEVERAL PASSENGER TYPES in one string:
    #   "Adult - 2 Pieces | 1 BAG UP TO 32KG | Infant - 1 Piece | 1 Piece equals 23KG"
    # (real Akbar/Saudia booking AS261379552). Those 32KG and 23KG belong to
    # DIFFERENT travellers, so merging them rendered "32kg + 23kg" on every
    # passenger's row — a claim of 55kg that no one on the booking holds (§7:
    # a wrong fact, not a missing one). Keep only the FIRST type's block; the
    # rest describes somebody else's allowance. Strings with no type marker
    # (e.g. aJet's "7kg + 3kg", one traveller with two bags) are untouched,
    # so every previously-correct value renders exactly as before.
    _types = list(re.finditer(r'\b(Adult|Child|Infant|Adt|Chd|Inf)\b', s, flags=re.I))
    if len(_types) > 1:
        # Split into one block per type and take the block for THIS passenger.
        # An infant's allowance is genuinely different from an adult's on the
        # same fare (real booking AS261379552: adults 2 x 32kg checked and 12kg
        # cabin, the infant 1 x 23kg checked and NO cabin piece at all), so a
        # passenger whose type is known must be shown their own line. Falls back
        # to the first block when the type is unknown — an unknown type is the
        # common case and the first block is the fare's primary (adult) one.
        _blocks = []
        for _i, _m in enumerate(_types):
            _end = _types[_i + 1].start() if _i + 1 < len(_types) else len(s)
            _blocks.append((_m.group(1).lower()[:3], s[_m.start():_end].rstrip(" |,;-")))
        _want = (pax_type or "").strip().lower()[:3]
        s = next((b for k, b in _blocks if k == _want), _blocks[0][1])
    # An EXPLICIT zero ("Infant 0Pc :") is not a missing value — the fare states
    # that this passenger carries nothing. N/A would read as "not stated" and
    # would also trip the card's "every fare includes a cabin piece" fallback,
    # handing the infant a piece the ticket does not give them.
    if re.search(r'\b0\s*(?:pcs?|pieces?|pc|p)\b', s, flags=re.I) and not re.search(
            r'\d+(?:\.\d+)?\s*(?:kilograms?|kgs?|kg|k)\b', s, flags=re.I):
        return "&mdash;"
    weights = re.findall(r'(\d+(?:\.\d+)?)\s*(?:kilograms?|kgs?|kg|k)\b', s, flags=re.I)
    if weights:
        out = []
        for w in weights:
            f = float(w)
            out.append(f"{int(f)}kg" if f.is_integer() else f"{f}kg")
        body = " + ".join(out)
        # PIECE COUNT (2026-08-19, approved). Weight alone UNDERSTATES a
        # multi-piece allowance: Saudia via Akbar states "Adult - 2 Pieces | 1 BAG
        # UP TO 23KG" (real booking 8CP5SK), which is 2 bags of 23kg. Rendering
        # just "23kg" reads as a single bag, so a passenger could leave a whole
        # 23kg entitlement unused. Prefix the count when the source states more
        # than one piece AND a single weight — "2 x 23kg".
        #
        # Deliberately narrow. A count is NOT added when several weights were
        # found ("7kg + 3kg" already enumerates the pieces), and never when the
        # count is 1, so every single-piece booking renders byte-identically to
        # before and the locked weight-only look is unchanged for them.
        if len(out) == 1:
            # "2 Pieces | ... 23KG" and Saudia's "2X23 KG" both state a
            # multi-piece allowance for one weight; either form loses its count
            # under the weight-only rule and understates the entitlement. The
            # NxWEIGHT match requires the kg unit right after the second number
            # so packing dimensions like "55x40x23 cm" can never be read as a
            # piece count.
            _pc = (re.search(r'(\d+)\s*(?:pcs?|pieces?|pc)\b', s, flags=re.I)
                   or re.search(r'(\d+)\s*[x\u00d7]\s*\d+\s*K[gG]\b', s, flags=re.I))
            if _pc and int(_pc.group(1)) > 1:
                body = f"{int(_pc.group(1))} &times; {body}"
        return body
    pcs = re.search(r'(\d+)\s*(?:pcs?|pieces?|pc|p)\b', s, flags=re.I)
    if pcs:
        return f"{int(pcs.group(1))}Pcs"
    return s



# ── Terms & Conditions (static, identical on every itinerary) ─────────────────
_TERMS = [
    ("1.", "Ticket Validity &amp; Changes",
     "Travel is valid only for the date, flight, and class specified. Name changes are not permitted after ticketing. Date or routing changes are subject to carrier fare rules and applicable fees. Refunds are governed by the purchased fare conditions. Unused outbound segments may result in automatic cancellation of onward flights (no-show policy)."),
    ("2.", "Check-In &amp; Boarding",
     "Passengers must arrive at the airport with sufficient time to complete check-in and boarding. Check-in deadlines and gate closing times are set by the operating carrier &mdash; confirm prior to travel. Denied boarding due to late arrival is not the liability of Pivot Travel Management. Valid photo ID or passport matching the ticket name is mandatory at all times."),
    ("3.", "Baggage &mdash; Inclusions",
     "Cabin and checked baggage allowances are determined by the operating carrier and fare class purchased. Confirm weight limits, piece count, and size restrictions directly with the carrier before travel. Allowances are per passenger and non-transferable."),
    ("4.", "Baggage &mdash; Exclusions &amp; Restrictions",
     "Excess baggage charges apply for any baggage exceeding permitted allowances and are payable directly to the carrier at airport rates. Prohibited items include explosives, flammable materials, compressed gases, and all items restricted under IATA Dangerous Goods Regulations. Liquids in cabin baggage are subject to airport security limits. Spare lithium batteries and power banks must be carried in cabin baggage only. Pivot Travel Management and the carrier accept no liability for fragile, valuable, or perishable items in checked baggage."),
    ("5.", "Travel Documents &amp; Visa",
     "Passengers are solely responsible for holding valid passports, visas, transit permits, and any health documentation required for all points of travel including transit countries. Pivot Travel Management may provide general guidance only. Denied boarding or deportation due to inadequate documents does not entitle the passenger to a refund."),
    ("6.", "Flight Disruptions",
     "In the event of cancellation, significant delay, or denied boarding, passenger rights are governed by the operating carrier's conditions of carriage and applicable GACA regulations. Pivot Travel Management will assist where possible but holds no financial liability for disruptions caused by the carrier, weather, force majeure, or events beyond its control."),
    ("7.", "Liability &amp; Governing Law",
     "Pivot Travel Management acts solely as a ticketing agent. Its liability is limited to the agency service fee paid. These terms are governed by the laws of the Kingdom of Saudi Arabia. Disputes are subject to the jurisdiction of the competent courts of Riyadh, KSA, without prejudice to applicable GACA regulations and international conventions."),
    ("8.", "Confidentiality",
     "This confirmation and all associated travel details, passenger information, pricing, and documentation are strictly confidential and issued solely for the named passenger(s). Disclosure, reproduction, or distribution to any third party without the prior written consent of Pivot Travel Management is prohibited. All client data is handled in accordance with the applicable data-protection regulations of the Kingdom of Saudi Arabia."),
]


def _terms_html() -> str:
    body = "".join(
        f'<div class="it"><h3><em>{n}</em>{h}</h3><p>{b}</p></div>' for (n, h, b) in _TERMS)
    return (f'<div class="tc"><h1>Terms &amp; conditions</h1>'
            f'<div class="sub">Flight booking confirmation &middot; Issued by Pivot Travel Management &middot; '
            f'{COMPANY_ADDRESS_SHORT} &middot; Clarifications: {COMPANY_EMAIL}</div>'
            f'<div class="cols">{body}</div></div>')


# ── Company identifiers (footer) ─────────────────────────────────────────────
# Both canonical (CLAUDE.md §2). The footer renders the VAT segment only when
# COMPANY_VAT is non-empty, so an unverified tax identifier can never reach a
# client document (§7 never fabricate). VAT supplied by the owner 2026-07-30
# from the registration certificate; 15 digits, the Saudi ZATCA format.
# NO LONGER RENDERED (owner's call, 2026-10-30: the footer carries the reference and website only).
# Kept defined — they are canonical company facts and restoring them is one line in build_pdf.
COMPANY_CR = "7043148696"
COMPANY_VAT = "311788697700003"

# Address printed on CLIENT-FACING documents (T&C page, Air Suvidha guide).
# Deliberately NOT cs@ — that is the automation's own monitored inbox, and the
# runner both reads from and can send as it (main.IMPERSONATE_USER). A client
# reading a PDF should be pointed at the staffed address instead.
COMPANY_EMAIL = "info@pivottmc.com"

# Website printed in every footer. A CONSTANT, not a literal: the same string had
# been hard-coded in five separate footers (itinerary, Air Suvidha guide, and the
# three alert/digest emails), so a domain change could update four of them and
# leave the fifth lying to a client. Stored lower-case; footers upper-case it.
COMPANY_WEBSITE = "www.pivottmc.com"

# Registered address. NO LONGER RENDERED IN THE HEADER (removed 2026-10-12 at
# the owner's request so the wordmark could grow). The address still prints on
# the Terms page, which carries its own copy, so the document does not lose it.
# Kept defined: it is a canonical company fact and putting it back is one line.
COMPANY_ADDRESS = ("Suite 20, 2nd Floor, Mobco Building, 2762 Ibn Al Anbari Street, "
                   "Al Amal District, Riyadh, Kingdom of Saudi Arabia")

# Header service bar. The owner asked for cs@ here specifically (2026-09-09),
# knowing it is the automation's own inbox: a client with a booking question is
# to reach the ticketing desk that watches it. The T&C page keeps COMPANY_EMAIL.
COMPANY_HOTLINE = "+966 11 220 0296"
HEADER_EMAIL = "cs@pivottmc.com"

# Riyadh is UTC+3 year-round (no DST), so a fixed offset is exact. The runner
# executes in CI on UTC; the stamp must read local to the issuing office.
_AST = timezone(timedelta(hours=3))


def _issued_stamp() -> str:
    """Date and time this copy was rendered, in Riyadh local time.

    A reissued booking otherwise produces a second PDF carrying the same PNR and
    the same 'Booked On' date, with nothing to say which copy is current — a
    passenger can end up travelling on a superseded print-out.
    """
    return datetime.now(timezone.utc).astimezone(_AST).strftime("%d %b %Y &middot; %H:%M AST")

# Services strapline under the wordmark — subtle, full uppercase, wide tracked.
# NO LONGER RENDERED: the service strip that carried this was removed from the
# header on 2026-10-12 (owner's request). Kept defined so it can be restored.
BRAND_STRAPLINE = "CORPORATE TRAVEL | CHAUFFEURS | CURATED ITINERARIES | PREMIUM PILGRIMAGE"

# Document state. The green CONFIRMED pill was retired 2026-09-09 (approved):
# it duplicated the label beside it and read as app rather than document
# language. The state now lives in the label itself, tinted by these colours.
_DOC_STATE = {
    "confirmed":   {"label": "Itinerary Confirmation",  "fg": "rgba(201,168,76,0.78)", "ink": "#1d1d1f"},
    "rebooked":    {"label": "Revised Itinerary &middot; Rebooked",    "fg": "#e79a95", "ink": "#b3261e"},
    "rescheduled": {"label": "Revised Itinerary &middot; Rescheduled", "fg": "#e6a86a", "ink": "#b45309"},
    "delayed":     {"label": "Revised Itinerary &middot; Delayed",     "fg": "#e0c675", "ink": "#85660f"},
    "revised":     {"label": "Revised Itinerary",       "fg": "#e0c675", "ink": "#85660f"},
}



# Terms-page address line: the short form printed there since the T&C page existed.
COMPANY_ADDRESS_SHORT = "Suite 20, 2762 Ibn Al Anbari Street, Al Amal District, Riyadh, Kingdom of Saudi Arabia"

# ── Fonts ────────────────────────────────────────────────────────────────────
# Inter (variable: optical size + weight), inlined as base64 so a render needs no network and
# cannot silently fall back to a system face. Latin-ext carries the Turkish letters in names.
_FONT_DIR = Path(__file__).parent / "assets" / "fonts"
_FONT_RANGES = {
    "latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD",
    "latin-ext": "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF",
}


def _font_face_css(subsets=("latin-ext", "latin")) -> str:
    out = []
    for name in subsets:
        p = _FONT_DIR / f"inter-var-{name}.woff2"
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            out.append("@font-face{font-family:'Inter';font-style:normal;font-weight:400 800;font-display:block;"
                       f"src:url(data:font/woff2;base64,{b64}) format('woff2');unicode-range:{_FONT_RANGES[name]};}}")
    return "".join(out)


def _dur(d: str) -> str:
    """'4H 45M' -> '4h 45m' (formatting only; the value is the source's)."""
    m = re.match(r"^\s*(\d+)\s*H\s*(\d+)?\s*M?\s*$", d or "", re.I)
    return f"{int(m.group(1))}h {int(m.group(2) or 0):02d}m" if m else (d or "")


def _sentence(s: str) -> str:
    s = (s or "").strip()
    return s[:1].upper() + s[1:].lower()


_CSS = r'''
:root{--ink:#1d1d1f;--sec:#5b6470;--hair:#e3e3e8;--grp:#f5f5f7;--gold:#c9a84c;--gold-ink:#85660f}
*{box-sizing:border-box;margin:0;padding:0}
@page{size:A4;margin:12mm 14mm 18mm 14mm}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-family:'Inter',-apple-system,'Helvetica Neue',Arial,sans-serif;color:var(--ink);font-size:12px;line-height:1.4;
     font-variant-numeric:tabular-nums;font-optical-sizing:auto;background:#fff}
.top{display:flex;justify-content:space-between;align-items:center;padding-bottom:12px;border-bottom:1px solid var(--hair)}
.brand{display:flex;align-items:center;gap:12px}
.tile{width:42px;height:42px;border-radius:10px;background:linear-gradient(160deg,#323234,#0e0e0f);display:flex;align-items:center;
      justify-content:center;outline:1px solid rgba(201,168,76,.55);outline-offset:-1px;flex:none}
.tile img{height:25px;width:auto}
.wordmark{font-size:22px;font-weight:400;letter-spacing:-.4px;color:var(--ink);line-height:1}
.wordmark b{font-weight:700}
.doc{text-align:right;line-height:1.35}
.doc-state{font-size:12.5px;font-weight:650}
.doc-meta{font-size:10.5px;color:var(--sec)}
.hero{padding:16px 0 12px}
.eyebrow{font-size:11px;font-weight:600;color:var(--sec);margin-bottom:4px}
.pnr{font-weight:700;color:var(--ink);line-height:1;letter-spacing:-1.8px}
.facts{display:flex;margin-top:12px;border-top:1px solid var(--hair)}
.fact{flex:1 1 0;min-width:0;padding:9px 14px 0 0}
.fact + .fact{padding-left:16px;border-left:1px solid var(--hair)}
.fact .k{font-size:10.5px;font-weight:600;color:var(--sec);margin-bottom:3px}
.fact .v{font-size:14px;font-weight:650}
.sec-t{font-size:15px;font-weight:700;margin:4px 0 8px}
.group{background:var(--grp);border-radius:16px;overflow:hidden;page-break-inside:avoid}
.row{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:10px 18px}
.row + .row{border-top:1px solid var(--hair)}
.row .name{font-size:16px;font-weight:650}
.row .tk{text-align:right}
.row .tk .k{font-size:10.5px;color:var(--sec);font-weight:600}
.row .tk .v{font-size:14px;font-weight:650;letter-spacing:.3px}
.seg{margin-top:18px}
.seg-h{break-after:avoid;page-break-after:avoid;display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:8px}
.seg-h .t{font-size:20px;font-weight:700;letter-spacing:-.2px}
.seg-h .r{font-size:13px;color:var(--sec);font-weight:500;margin-left:8px}
.seg-h .d{font-size:13px;font-weight:650;white-space:nowrap}
.chip{display:inline-block;margin-right:8px;border:1px solid var(--gold);color:var(--gold-ink);border-radius:999px;
      padding:1px 9px;font-size:10.5px;font-weight:650;letter-spacing:.4px;vertical-align:1px}
.card{position:relative;border:1px solid var(--hair);border-radius:20px;background:#fff;page-break-inside:avoid;break-inside:avoid}
.route{padding:14px 24px 12px}
.carrier{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.carrier .a{font-size:12.5px;color:var(--sec);font-weight:500}
.carrier .a b{color:var(--gold-ink);font-weight:700;font-size:14px;letter-spacing:.4px;margin-right:6px}
.carrier .du{font-size:12.5px;font-weight:650}
.leg{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(70px,.5fr) minmax(0,1.5fr);align-items:start;column-gap:8px}
.end.r{text-align:right}
.code{font-weight:700;font-size:38px;line-height:.95;letter-spacing:-1.4px}
.time{font-size:25px;font-weight:700;letter-spacing:-.4px;margin-top:5px;line-height:1}
.date{font-size:12px;color:var(--sec);font-weight:600;margin-top:3px}
.city{font-size:13.5px;font-weight:650;margin-top:6px}
.ap{font-size:11.5px;color:var(--sec);line-height:1.3;margin-top:1px}
.mid{align-self:start;margin-top:18px;display:flex;align-items:center;gap:6px}
.mid i{flex:1;height:0;border-top:1.5px solid var(--gold)}
.mid span{font-family:'DejaVu Sans',sans-serif;font-size:13px;color:var(--sec);line-height:1}
.perf{position:relative;height:0;border-top:1.5px dashed #d4d4da;margin:0 14px}
.perf::before,.perf::after{content:'';position:absolute;top:-10px;width:10px;height:20px;background:#fff;border:1px solid var(--hair)}
.perf::before{left:-15px;border-left:none;border-radius:0 20px 20px 0}
.perf::after{right:-15px;border-right:none;border-radius:20px 0 0 20px}
.stub{padding:11px 24px 12px}
.pt{width:100%;border-collapse:collapse}
.pt th{font-size:10.5px;color:var(--sec);font-weight:600;text-align:center;padding:0 0 6px}
.pt th:first-child,.pt td:first-child{text-align:left}
.pt td{font-size:13px;font-weight:600;text-align:center;padding:6px 0;border-top:1px solid var(--hair)}
.pt td.seat{font-size:15px;font-weight:700}
.lay{display:flex;align-items:center;justify-content:center;margin:8px 0;break-after:avoid;page-break-after:avoid}
.lay span{background:var(--grp);border-radius:999px;padding:6px 16px;font-size:12px;font-weight:600;color:var(--sec)}
.lay b{color:var(--ink);font-weight:700}
.tc{page-break-before:always}
.tc h1{font-size:22px;font-weight:700;letter-spacing:-.3px}
.tc .sub{font-size:11px;color:var(--sec);margin:6px 0 16px;line-height:1.5}
.tc .cols{column-count:2;column-gap:30px}
.tc .it{break-inside:avoid;margin-bottom:14px}
.tc .it h3{font-size:12px;font-weight:700;margin-bottom:3px}
.tc .it h3 em{font-style:normal;color:var(--gold-ink);margin-right:5px}
.tc .it p{font-size:10px;color:#454d5a;line-height:1.55}
'''


def _flight_card(f: dict, multi: bool = False) -> str:
    """One boarding-pass card: route + times on top, perforation, passenger table below."""
    rows, show_cabin, show_checked, show_seat = [], False, False, False
    for p in f.get("pax") or []:
        _pt = p.get("pax_type", "")
        c = _norm_bag(p.get("cabin_bag", ""), _pt)
        k = _norm_bag(p.get("checked_bag", ""), _pt)
        s = (p.get("seat") or "").strip()
        # standing rule (unchanged): every fare includes a cabin piece, so a stated checked
        # allowance with no cabin value shows 1Pcs rather than nothing.
        if c == "N/A" and k != "N/A":
            c = "1Pcs"
        show_cabin |= c != "N/A"
        show_checked |= k != "N/A"
        show_seat |= bool(s)
        rows.append((_title_name(p.get("name", "N/A")), c, k, s))
    table = ""
    if rows and (show_cabin or show_checked or show_seat):
        th = "<th>Passenger</th>"
        if show_cabin:   th += "<th>Cabin</th>"
        if show_checked: th += "<th>Checked</th>"
        if show_seat:    th += "<th>Seat</th>"
        trs = ""
        for n, c, k, s in rows:
            trs += f"<tr><td>{n}</td>"
            if show_cabin:   trs += f"<td>{c}</td>"
            if show_checked: trs += f"<td>{k}</td>"
            if show_seat:    trs += f'<td class="seat">{s or "&mdash;"}</td>'
            trs += "</tr>"
        table = f'<table class="pt"><tr>{th}</tr>{trs}</table>'

    def sub(name, term):
        s = name or ""
        if term:
            s = (s + " &middot; " if s else "") + f"Terminal {term}"
        return s

    dep_sub = sub(f.get("dep_airport"), f.get("terminal"))
    arr_sub = sub(f.get("arr_airport"), f.get("arr_terminal"))
    dep_ap = f'<div class="ap">{dep_sub}</div>' if dep_sub else ""
    arr_ap = f'<div class="ap">{arr_sub}</div>' if arr_sub else ""
    chip = f'<span class="chip">PNR {f["pnr"]}</span>' if (multi and f.get("pnr")) else ""
    duration = _dur(f.get("duration", ""))
    tail = _na(f.get("cabin", "N/A")) + (f" &middot; {duration}" if duration else "")
    return f"""
<div class="card">
  <div class="route">
    <div class="carrier"><div class="a"><b>{_na(f.get("flight_no", "N/A"))}</b>Operated by {_na(f.get("airline", "N/A"))}</div><div class="du">{chip}{tail}</div></div>
    <div class="leg">
      <div class="end"><div class="code">{f.get("dep_iata", "???")}</div><div class="time">{f.get("dep_time", "")}</div>
        <div class="date">{f.get("dep_date", "")}</div><div class="city">{f.get("dep_city", "")}</div>{dep_ap}</div>
      <div class="mid"><i></i><span>&#9992;</span><i></i></div>
      <div class="end r"><div class="code">{f.get("arr_iata", "???")}</div><div class="time">{f.get("arr_time", "")}</div>
        <div class="date">{f.get("arr_date", "")}</div><div class="city">{f.get("arr_city", "")}</div>{arr_ap}</div>
    </div>
  </div>
  <div class="perf"></div>
  <div class="stub">{table}</div>
</div>"""


def build_html(data: dict, project_dir: str = None, layout: str = "B") -> str:
    # `layout` is accepted for backward compatibility and ignored: pagination is now handled by
    # the browser (cards never split, banners stay with their card, T&C starts a fresh page).
    pnr          = data.get("pnr", "N/A")
    # Split-carrier bookings carry one airline reference per airline; both must
    # reach the traveller (see booking_refs). A single-reference booking gives a
    # one-item list and every string below is exactly what it always was.
    refs         = booking_refs(data) or [pnr]
    pnr_display  = " / ".join(refs)
    pnr_label    = "PNR Reference" if len(refs) < 2 else "PNR References"
    booking_ref  = data.get("booking_ref") or ""
    crs_ref      = data.get("crs_ref") or ""
    # _na(), not a .get() default: the default only fires when the KEY IS
    # ABSENT, so a key present-but-empty slipped through unprotected and the
    # rail drew a bare "BOOKED ON" label with nothing under it. extract_pegasus
    # sets booked_on = "" explicitly, and _finalize only backfills it when a ctx
    # date is supplied - so the cloud runner masked this and every manual build
    # (\process uploads included) showed the empty label. Missing = N/A (§6).
    booked_on    = _na(data.get("booked_on", ""))
    # Journey type label: exactly ONE-WAY or ROUND TRIP (no RETURN / MULTI-CITY /
    # CONNECTING wording — locked rule).
    _jt = (data.get("journey_type") or "ONE-WAY").upper()
    journey_type = "ROUND TRIP" if ("RETURN" in _jt or "ROUND" in _jt) else "ONE-WAY"
    passengers   = data.get("passengers", [])
    seg_groups   = data.get("segments", [])

    _cells = []
    if booking_ref:
        _cells.append(("Agency ref.", booking_ref))
    if crs_ref and crs_ref.upper() != pnr.upper():
        _cells.append(("CRS ref.", crs_ref))
    _cells.append(("Booked on", booked_on))
    _cells.append(("Journey", journey_type.title()))

    # Symmetric airport details: an airport that appears as a DEPARTURE anywhere in
    # the itinerary (with its name / terminal) is the same physical airport when it
    # appears as an ARRIVAL on another leg. Build an IATA -> (airport, terminal) map
    # from every reference, then backfill each segment's arrival (and departure) so
    # destination airport details render too — not just the departure side.
    # A TERMINAL is only evidence for legs sold on the SAME ticket (2026-09-30).
    # On a consolidated document covering two separately-ticketed journeys, the
    # same IATA does NOT imply the same terminal: RX12239 + BMGECWP (RUH-KUL on
    # Riyadh Air, then KUL-CAN on Spring Airlines) had Spring's stated KUL
    # Terminal 2 copied onto Riyadh Air's KUL arrival three days earlier, where
    # the Akbar ticket states no terminal at all — and a full-service carrier
    # into KLIA does not necessarily use the low-cost terminal. That is a WRONG
    # fact rather than a missing one (§7), so the terminal map is keyed per
    # reference. Airport NAMES stay global: an airport's name is the same fact
    # on every ticket, which is exactly why the static table is allowed (§8
    # 2026-08-02), and a single-reference booking behaves as it always did.
    _ap_name, _ap_term = {}, {}
    for grp in seg_groups:
        for fl in grp.get("flights", []):
            di, ai = fl.get("dep_iata", ""), fl.get("arr_iata", "")
            _ref = fl.get("pnr", "")
            if fl.get("dep_airport"):  _ap_name.setdefault(di, fl["dep_airport"])
            if fl.get("terminal"):     _ap_term.setdefault((_ref, di), fl["terminal"])
            if fl.get("arr_airport"):  _ap_name.setdefault(ai, fl["arr_airport"])
            if fl.get("arr_terminal"): _ap_term.setdefault((_ref, ai), fl["arr_terminal"])
    for grp in seg_groups:
        for fl in grp.get("flights", []):
            di, ai = fl.get("dep_iata", ""), fl.get("arr_iata", "")
            _ref = fl.get("pnr", "")
            if not fl.get("arr_airport")  and _ap_name.get(ai): fl["arr_airport"]  = _ap_name[ai]
            if not fl.get("arr_terminal") and _ap_term.get((_ref, ai)):
                fl["arr_terminal"] = _ap_term[(_ref, ai)]
            if not fl.get("dep_airport")  and _ap_name.get(di): fl["dep_airport"]  = _ap_name[di]
            # 2026-07-27: the DEPARTURE terminal was the one field this block never
            # backfilled (airport names went both ways, arrival terminal was filled,
            # departure terminal was not). On a round trip where the airline states a
            # hub's terminal only once — e.g. only on the outbound ARRIVAL into IST —
            # the inbound leg departing that same IST silently rendered no terminal.
            # This only ever copies a terminal the document itself stated for that
            # exact IATA; it never invents one (§7).
            if not fl.get("terminal")     and _ap_term.get((_ref, di)):
                fl["terminal"] = _ap_term[(_ref, di)]

    # Airport NAME of last resort (2026-08-02). Only Alhind states airport names
    # in a parseable form; the other four portals send the city and IATA code but
    # no name, so every non-Alhind itinerary rendered a bare city under the code.
    # extractors.AIRPORT_NAMES is a static IATA -> name reference table — a name
    # is a stable single-valued fact, unlike a terminal (see the note on that
    # table for why the equivalent terminal table stays rejected). Runs LAST and
    # only fills blanks, so anything the document itself said always wins, and an
    # unlisted IATA renders no name rather than a guessed one.
    try:
        from extractors import AIRPORT_NAMES as _AP_REF
    except Exception:
        _AP_REF = {}
    for grp in seg_groups:
        for fl in grp.get("flights", []):
            if not fl.get("dep_airport"):
                fl["dep_airport"] = _AP_REF.get(fl.get("dep_iata", ""), "")
            if not fl.get("arr_airport"):
                fl["arr_airport"] = _AP_REF.get(fl.get("arr_iata", ""), "")

    # Per-leg passenger baggage/seat: portals that expose per-segment data set
    # flight["pax"] themselves. For any leg that has none, fall back to the
    # booking-level passengers[] values — those genuinely apply to every leg, so
    # this is honest, and it means no portal regresses while extractors catch up.
    for grp in seg_groups:
        for fl in grp.get("flights", []):
            if fl.get("pax"):
                continue
            fl["pax"] = [{"name": p.get("name", ""),
                          "cabin_bag": p.get("cabin_bag", ""),
                          "checked_bag": p.get("checked_bag", ""),
                          "seat": p.get("seat", "")} for p in passengers]


    # ---- masthead ----
    _st = _DOC_STATE.get((data.get("doc_status") or "confirmed").lower(), _DOC_STATE["confirmed"])
    # Revision number: shown only from the SECOND copy onward ("Revision 1" tells the reader
    # nothing; "Revision 2" beside an older print-out settles which one to travel on).
    try:
        _rev = int(data.get("revision") or 0)
    except (TypeError, ValueError):
        _rev = 0
    _rev_stamp = f" &middot; Revision {_rev}" if _rev > 1 else ""
    logo_b64 = _logo_b64(project_dir)
    tile = (f'<div class="tile"><img src="data:image/png;base64,{logo_b64}" alt="Pivot Travel Management"></div>'
            if logo_b64 else "")
    multi = len(refs) > 1
    pnr_label_s = "PNR references" if multi else "PNR reference"
    pnr_px = 54 if len(pnr_display) <= 7 else (46 if len(pnr_display) <= 9 else 38)
    facts = "".join(
        f'<div class="fact"><div class="k">{lbl}</div><div class="v">{val}</div></div>' for lbl, val in _cells)

    # ---- travellers ----
    if not passengers:
        passengers = [{"name": "N/A"}]
    pax_rows = "".join(
        f'<div class="row"><div class="name">{_title_name(p.get("name", "N/A"))}</div>'
        f'<div class="tk"><div class="k">Ticket no.</div><div class="v">{_na(p.get("ticket_no", "N/A"))}</div></div></div>'
        for p in passengers)

    # ---- journeys ----
    segs_html = ""
    for grp in seg_groups:
        flights  = grp.get("flights", [])
        layovers = grp.get("layovers", [])
        if not flights:
            continue
        _ty = str(grp.get("type", ""))
        _title = _sentence(_ty) if _ty.lower() in ("outbound", "inbound") else "Flight"
        _frm = flights[0].get("dep_city", flights[0].get("dep_iata", ""))
        _to  = flights[-1].get("arr_city", flights[-1].get("arr_iata", ""))
        segs_html += (f'<div class="seg"><div class="seg-h"><div><span class="t">{_title}</span>'
                      f'<span class="r">{_frm} to {_to}</span></div>'
                      f'<div class="d">{_weekday_date(flights[0].get("dep_date", ""))}</div></div>')
        for fi, flight in enumerate(flights):
            segs_html += _flight_card(flight, multi)
            if fi < len(layovers):
                lay = layovers[fi]
                segs_html += (f'<div class="lay"><span>Layover in <b>{lay.get("airport", "")}</b>'
                              f' &middot; {_dur(lay.get("duration", ""))}</span></div>')
        segs_html += "</div>"

    font_css = _font_face_css()
    font_link = "" if font_css else (
        '<link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..800&display=swap" rel="stylesheet">')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Booking Confirmation — {pnr_display}</title>
{font_link}<style>{font_css}{_CSS}</style>
</head>
<body>
<div class="top"><div class="brand">{tile}<div class="wordmark"><b>Pivot</b> Travel Management</div></div>
  <div class="doc"><div class="doc-state" style="color:{_st['ink']};">{_st['label']}</div>
  <div class="doc-meta">Issued {_issued_stamp()}{_rev_stamp}</div>
  <div class="doc-meta">{COMPANY_HOTLINE} &middot; {HEADER_EMAIL}</div></div></div>
<div class="hero"><div class="eyebrow">{pnr_label_s}</div><div class="pnr" style="font-size:{pnr_px}px">{pnr_display}</div>
  <div class="facts">{facts}</div></div>
<div class="sec-t">Travellers</div><div class="group">{pax_rows}</div>
{segs_html}
{_terms_html()}
</body></html>"""


def _footer_template(pnr_display: str) -> str:
    """Chromium footer (repeats on every page, carries 'Page n of N'). The Inter latin subset is
    inlined so the footer matches the page. Reference + website only — CR/VAT are not printed."""
    return (f'<style>{_font_face_css(("latin",))}</style>'
            f'<div style="width:100%;padding:0 14mm;font-family:Inter,Helvetica,Arial,sans-serif;font-size:8.5px;'
            f'color:#5b6470;display:flex;justify-content:space-between;align-items:flex-end;'
            f'-webkit-print-color-adjust:exact;">'
            f'<div>PIVOT AUTOMATED ITINERARY &nbsp;|&nbsp; {pnr_display} &nbsp;|&nbsp; {COMPANY_WEBSITE.upper()}</div>'
            f'<div>Page <span class="pageNumber"></span> of <span class="totalPages"></span></div></div>')


def build_pdf(booking_data: dict, out_dir: str, project_dir: str = None) -> str:
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pnr = booking_data.get("pnr", "UNKNOWN")
    # File name carries EVERY airline reference on the booking, so a split-carrier
    # round trip is findable by either one (B9PS6D-8XMVR7.pdf). Single-reference
    # bookings are named exactly as before.
    _safe = lambda v: "".join(c for c in str(v) if c.isalnum() or c in "_-")
    _stem = "-".join(_safe(r) for r in booking_refs(booking_data) if _safe(r)) or _safe(pnr) or "UNKNOWN"
    pdf_path = out_dir / f"{_stem}.pdf"
    pnr_display = " / ".join(booking_refs(booking_data) or [pnr])

    f = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
    f.write(build_html(booking_data, project_dir=project_dir))
    f.close()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.emulate_media(media="screen")
            page.goto(f"file://{f.name}", wait_until="networkidle")
            page.pdf(path=str(pdf_path), format="A4", print_background=True,
                     display_header_footer=True, header_template="<span></span>",
                     footer_template=_footer_template(pnr_display),
                     margin={"top": "12mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
            page.close()
            browser.close()
    finally:
        os.unlink(f.name)

    print(f"✓ PDF saved: {pdf_path}")
    return str(pdf_path)


# ── CLI ─────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",        required=True)
    parser.add_argument("--out-dir",     required=True)
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args()
    build_pdf(json.loads(args.data), args.out_dir, args.project_dir)
