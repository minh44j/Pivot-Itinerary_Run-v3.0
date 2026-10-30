"""
Pivot — internal e-mail bodies (redesign 2026-10-31).

Three e-mails reach the cs@ inbox, all internal (never sent to a client):
  * the CONFIRMATION that accompanies each finished itinerary PDF,
  * the MANUAL-REVIEW digest when a booking could not be built automatically,
  * the ACTION-REQUIRED digest when an airline cancels / changes / delays a flight.

Each is built for ONE question: "what do I do next, and can I trust it?" — the answer sits at the top
(status + next step), the facts below it, the reference to find the source e-mail last. HTML uses
tables and inline styles only (Gmail / Outlook / Apple Mail safe); a plain-text twin is provided for
each. This module is PURE (no Google imports) so the offline test-suite can import it.
"""
import html as _html
import os
import re
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime

import extractors
from generate_itinerary_v3 import booking_refs, COMPANY_WEBSITE, _weekday_date

# ── tokens (same as the itinerary) ──────────────────────────────────────────────
INK, SLATE, HAIR, GRP = "#1d1d1f", "#5b6470", "#e3e3e8", "#f5f5f7"
GOLD, GOLD_INK = "#c9a84c", "#85660f"
GREEN, RED, ORANGE, AMBER = "#1f7a4d", "#b3261e", "#b45309", "#8a6100"
# One sans stack: Apple Mail / iOS resolve -apple-system to SF; other clients get Inter (imported below)
# or the system sans.
SANS = "-apple-system,'SF Pro Display','Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif"
FONT_IMPORT = ("<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
               "&display=swap');</style>")
_AST = timezone(timedelta(hours=3))          # Riyadh, UTC+3 all year

# Severity: label, colour (white text on it passes AA), urgency order.
SEVERITY = {
    "cancellation":    {"label": "Cancellation",    "plural": "cancellations",    "color": RED,    "rank": 0,
                        "headline": "Flight cancelled"},
    "schedule_change": {"label": "Schedule change", "plural": "schedule changes", "color": ORANGE, "rank": 1,
                        "headline": "Schedule changed"},
    "delay":           {"label": "Delay",           "plural": "delays",           "color": AMBER,  "rank": 2,
                        "headline": "Flight delayed"},
}


def esc(v, na="N/A"):
    v = "" if v is None else str(v).strip()
    return _html.escape(v) if v else na


def gmail_link(message_id, mailbox="cs@pivottmc.com"):
    """Deep link to a message in the cs@ mailbox. Best-effort: Gmail resolves an API message id here."""
    return f"https://mail.google.com/mail/?authuser={mailbox}#all/{message_id}" if message_id else ""


def received(date_header):
    """'Fri, 30 Oct 2026 13:39:00 +0300' -> '30 Oct · 13:39' (Riyadh time); the raw value if unparsable."""
    try:
        d = parsedate_to_datetime(date_header).astimezone(_AST)
        return d.strftime("%d %b · %H:%M").lstrip("0")
    except Exception:
        return (date_header or "").strip() or "N/A"


# ── building blocks ───────────────────────────────────────────────────────────
def _logo(logo_cid):
    if not logo_cid:
        return ""
    return (f'<td style="width:42px;padding:0 12px 0 0;vertical-align:middle;">'
            f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="background:#1e1e20;border-radius:11px;padding:7px;line-height:0;">'
            f'<img src="cid:{logo_cid}" width="28" height="28" alt="Pivot" style="display:block;border:0;"></td></tr></table></td>')


def _shell(inner, logo_cid, title, preheader="", width=620):
    """White card on a neutral page: masthead (logo tile + wordmark + gold rule) · inner · footer."""
    pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{esc(preheader, "")}</div>'
           if preheader else "")
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title, "Pivot")}</title>
{FONT_IMPORT}</head><body style="margin:0;padding:0;background:{GRP};">{pre}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{GRP};padding:22px 0;">
<tr><td align="center">
<table role="presentation" width="{width}" cellpadding="0" cellspacing="0" style="max-width:{width}px;width:100%;background:#ffffff;border:1px solid {HAIR};border-radius:16px;overflow:hidden;">
<tr><td style="padding:18px 26px 14px;border-bottom:2px solid {GOLD};">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>{_logo(logo_cid)}
<td style="vertical-align:middle;font-family:{SANS};font-size:19px;letter-spacing:-.3px;color:{INK};"><b>Pivot</b> Travel Management</td></tr></table>
</td></tr>
{inner}
<tr><td style="border-top:1px solid {HAIR};padding:13px 26px;font-family:{SANS};font-size:11px;color:{SLATE};letter-spacing:.6px;">
PIVOT AUTOMATED ITINERARY &nbsp;|&nbsp; {COMPANY_WEBSITE.upper()}</td></tr>
</table></td></tr></table></body></html>'''


def _pill(text, color):
    return (f'<span style="display:inline-block;background:{color};color:#ffffff;font-family:{SANS};font-size:11px;'
            f'font-weight:700;letter-spacing:.6px;padding:4px 11px;border-radius:999px;">{esc(text)}</span>')


def _chip(text, color=SLATE, bg=GRP):
    return (f'<span style="display:inline-block;background:{bg};color:{color};font-family:{SANS};font-size:12px;'
            f'font-weight:600;padding:5px 11px;border-radius:999px;margin:0 6px 6px 0;">{text}</span>')


def _button(url, label, primary=True):
    if not url:
        return ""
    bg, fg, bd = (INK, "#ffffff", INK) if primary else ("#ffffff", INK, HAIR)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="display:inline-block;margin:0 8px 0 0;"><tr>'
            f'<td style="background:{bg};border:1px solid {bd};border-radius:10px;">'
            f'<a href="{_html.escape(url, quote=True)}" style="display:inline-block;padding:10px 18px;font-family:{SANS};'
            f'font-size:13px;font-weight:650;color:{fg};text-decoration:none;">{esc(label)}</a></td></tr></table>')


def _label(t):
    return f'<div style="font-family:{SANS};font-size:11px;font-weight:600;color:{SLATE};margin-bottom:3px;">{esc(t)}</div>'


def _section(title):
    return (f'<tr><td style="padding:22px 26px 8px;font-family:{SANS};font-size:15px;font-weight:700;color:{INK};'
            f'letter-spacing:-.2px;">{esc(title)}</td></tr>')


# ═════════════════════════════════════════════════════════════════════════════
# 1. CONFIRMATION — accompanies the finished itinerary PDF
# ═════════════════════════════════════════════════════════════════════════════
def _route_title(data):
    segs = [s for s in data.get("segments", []) if s.get("flights")]
    if not segs:
        return ""
    f0, f1 = segs[0]["flights"][0], segs[0]["flights"][-1]
    return f'{f0.get("dep_city") or f0.get("dep_iata", "")} → {f1.get("arr_city") or f1.get("arr_iata", "")}'


def _first_date(data):
    for s in data.get("segments", []):
        for f in s.get("flights", []):
            if f.get("dep_date"):
                return f["dep_date"]
    return ""


def confirmation_subject(data):
    segs = [s for s in data.get("segments", []) if s.get("flights")]
    codes = ""
    if segs:
        codes = f'{segs[0]["flights"][0].get("dep_iata", "")}→{segs[0]["flights"][-1].get("arr_iata", "")}'
    d = _first_date(data)
    tail = " · ".join(x for x in (codes, d[:6].strip() if d else "") if x)
    base = f"Booking Confirmation — {data.get('pnr')} ({data.get('portal')})"
    return f"{base} · {tail}" if tail else base


def attention_points(data):
    """Things a person should look at before forwarding. Computed from the data only — a missing value is
    reported, never filled in."""
    out = []
    try:
        rev = int(data.get("revision") or 0)
    except (TypeError, ValueError):
        rev = 0
    if rev >= 2:
        out.append(f"Revision {rev} — this replaces an earlier copy of the same booking; make sure the client uses this one.")
    if extractors.india_arrival(data):
        out.append("India arrival — the Air Suvidha 2.0 health-declaration guide is the last page of the PDF.")
    if len(booking_refs(data)) > 1:
        out.append("Two airline references — each flight card shows the reference to check in with.")
    if not (data.get("booked_on") or "").strip():
        out.append("Booked-on date was not in the source, so the PDF shows N/A.")
    for p in data.get("passengers", []):
        if not (p.get("ticket_no") or "").strip():
            out.append(f"No ticket number for {p.get('name') or 'a passenger'}.")
    return out


def _seat_text(flight):
    pax = [p for p in (flight.get("pax") or []) if (p.get("seat") or "").strip()]
    if not pax:
        return ""
    if len(flight.get("pax") or []) == 1:
        return f"Seat {pax[0]['seat'].strip()}"
    return " · ".join(f"{_short(p.get('name'))} {p['seat'].strip()}" for p in pax)


def _short(name):
    parts = (name or "").replace("Mr.", "").replace("Mrs.", "").replace("Ms.", "").split()
    return parts[0].title() if parts else "Pax"


def confirmation_html(data, source_ref="", logo_cid=None):
    refs = booking_refs(data) or [data.get("pnr")]
    pnr = " / ".join(esc(r, "") for r in refs)
    pnr_px = 44 if len(" / ".join(refs)) <= 7 else 30
    route, d0 = _route_title(data), _first_date(data)
    jt = "Round trip" if any(k in (data.get("journey_type") or "").upper() for k in ("RETURN", "ROUND")) else "One-way"
    notes = attention_points(data)

    status = (f'<tr><td style="padding:20px 26px 6px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
              f'style="background:#eef8f2;border:1px solid #cfe9db;border-radius:12px;"><tr><td style="padding:14px 18px;font-family:{SANS};">'
              f'<div style="font-size:15px;font-weight:700;color:{GREEN};">&#10003; Itinerary ready</div>'
              f'<div style="font-size:13px;color:{INK};margin-top:3px;line-height:1.5;">The PDF is attached. '
              f'<b>Next:</b> check it against the airline ticket, then forward it to the client.</div></td></tr></table></td></tr>')

    hero = (f'<tr><td style="padding:14px 26px 4px;font-family:{SANS};">{_label("PNR reference" if len(refs) < 2 else "PNR references")}'
            f'<div style="font-size:{pnr_px}px;font-weight:700;letter-spacing:-1.5px;line-height:1.05;color:{INK};">{pnr}</div>'
            f'<div style="font-size:14px;color:{SLATE};margin-top:6px;">{esc(route, "")}'
            f'{(" &middot; " + esc(d0, "")) if d0 else ""} &middot; {jt}</div></td></tr>')

    def fact(k, v):
        return (f'<td style="padding:10px 14px 0 0;vertical-align:top;font-family:{SANS};">{_label(k)}'
                f'<div style="font-size:14px;font-weight:650;color:{INK};">{esc(v)}</div></td>')
    facts = [("Booked on", data.get("booked_on")), ("Portal", data.get("portal"))]
    br, crs = (data.get("booking_ref") or "").strip(), (data.get("crs_ref") or "").strip()
    if br and br != (data.get("pnr") or "").strip():
        facts.insert(0, ("Agency ref.", br))
    if crs and crs != (data.get("pnr") or "").strip():
        facts.insert(1 if br else 0, ("CRS ref.", crs))
    fact_row = (f'<tr><td style="padding:6px 26px 0;"><table role="presentation" cellpadding="0" cellspacing="0" '
                f'style="border-top:1px solid {HAIR};margin-top:10px;"><tr>{"".join(fact(k, v) for k, v in facts)}</tr></table></td></tr>')

    attn = ""
    if notes:
        attn = (f'<tr><td style="padding:16px 26px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="background:#faf6ea;border-radius:12px;"><tr><td style="padding:12px 16px;font-family:{SANS};font-size:13px;color:{INK};line-height:1.6;">'
                f'<b style="color:{GOLD_INK};">Worth a look</b>'
                + "".join(f'<div style="margin-top:4px;">&bull; {esc(n)}</div>' for n in notes) + '</td></tr></table></td></tr>')

    pax_rows = ""
    pax = data.get("passengers", [])
    for i, p in enumerate(pax):
        top = f"border-top:1px solid {HAIR};" if i else ""
        pax_rows += (f'<tr><td style="padding:11px 16px;{top}font-family:{SANS};font-size:15px;font-weight:650;color:{INK};">{esc(p.get("name"))}</td>'
                     f'<td align="right" style="padding:11px 16px;{top}font-family:{SANS};font-size:13px;color:{SLATE};">Ticket '
                     f'<b style="color:{INK};letter-spacing:.3px;">{esc(p.get("ticket_no"))}</b></td></tr>')
    pax_block = (f'{_section("Travellers" if len(pax) != 1 else "Traveller")}<tr><td style="padding:0 26px;"><table role="presentation" width="100%" '
                 f'cellpadding="0" cellspacing="0" style="background:{GRP};border-radius:14px;">{pax_rows or "<tr><td style=padding:12px>N/A</td></tr>"}</table></td></tr>')

    legs = ""
    for seg in data.get("segments", []):
        fl = seg.get("flights", [])
        if not fl:
            continue
        ty = str(seg.get("type", "")).title() if str(seg.get("type", "")).lower() in ("outbound", "inbound") else "Flight"
        legs += (f'<tr><td style="padding:14px 26px 6px;font-family:{SANS};font-size:13px;font-weight:700;color:{INK};">{ty} '
                 f'<span style="font-weight:500;color:{SLATE};">&middot; {esc(_weekday_date(fl[0].get("dep_date", "")), "")}</span></td></tr>')
        for f in fl:
            meta = " · ".join(x for x in ((f.get("cabin") or "").strip(), (f.get("duration") or "").strip().lower().replace(" ", "")) if x)
            bag = " · ".join(x for x in ((f.get("pax") or [{}])[0].get("cabin_bag", ""), (f.get("pax") or [{}])[0].get("checked_bag", "")) if x) \
                if len({(p.get("cabin_bag"), p.get("checked_bag")) for p in (f.get("pax") or [])}) == 1 else ""
            seat = _seat_text(f)
            sub = "  ·  ".join(x for x in (meta, f"Bags {bag}" if bag else "") if x)
            legs += (f'<tr><td style="padding:0 26px 8px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                     f'style="border:1px solid {HAIR};border-radius:12px;"><tr>'
                     f'<td style="padding:11px 14px;font-family:{SANS};width:92px;vertical-align:top;font-size:14px;font-weight:700;color:{GOLD_INK};">{esc(f.get("flight_no"))}</td>'
                     f'<td style="padding:11px 4px;font-family:{SANS};vertical-align:top;">'
                     f'<div style="font-size:15px;font-weight:700;color:{INK};">{esc(f.get("dep_iata"))} {esc(f.get("dep_time"))} &rarr; {esc(f.get("arr_iata"))} {esc(f.get("arr_time"))}</div>'
                     f'<div style="font-size:12px;color:{SLATE};margin-top:2px;">{esc(sub, "")}</div>'
                     f'{("<div style=" + chr(34) + "font-size:13px;font-weight:650;color:" + INK + ";margin-top:5px;" + chr(34) + ">" + esc(seat) + "</div>") if seat else ""}</td>'
                     f'<td align="right" style="padding:11px 14px;font-family:{SANS};vertical-align:top;font-size:12px;color:{SLATE};">{esc(f.get("airline"), "")}</td></tr></table></td></tr>')
    itin = f'{_section("Itinerary")}{legs}' if legs else ""

    trace = (f'<tr><td style="padding:12px 26px 22px;font-family:{SANS};font-size:11.5px;color:{SLATE};line-height:1.6;">'
             f'Attachment <b style="color:{INK};">{esc("-".join(refs))}.pdf</b>'
             f'{(" &nbsp;&middot;&nbsp; Source ref " + esc(source_ref)) if source_ref else ""}</td></tr>')
    inner = status + hero + fact_row + attn + pax_block + itin + trace
    return _shell(inner, logo_cid, f"Booking Confirmation — {data.get('pnr')}", preheader=f"{route} · {d0} · PDF attached — check, then forward to the client.")


def confirmation_text(data, source_ref=""):
    refs = booking_refs(data) or [data.get("pnr")]
    L = ["✓ ITINERARY READY — the PDF is attached. Next: check it against the airline ticket, then forward it to the client.", "",
         f"PNR: {' / '.join(str(r) for r in refs)}   {_route_title(data)}   {_first_date(data)}", ""]
    br, crs = (data.get("booking_ref") or "").strip(), (data.get("crs_ref") or "").strip()
    if br and br != (data.get("pnr") or "").strip(): L.append(f"Agency ref: {br}")
    if crs and crs != (data.get("pnr") or "").strip(): L.append(f"CRS ref: {crs}")
    L += [f"Portal: {data.get('portal') or 'N/A'}   Booked on: {data.get('booked_on') or 'N/A'}", ""]
    notes = attention_points(data)
    if notes:
        L.append("WORTH A LOOK")
        L += [f"  • {n}" for n in notes] + [""]
    L.append(f"TRAVELLERS ({len(data.get('passengers', []))})")
    for p in data.get("passengers", []):
        L.append(f"  • {p.get('name') or 'N/A'}   ticket {p.get('ticket_no') or 'N/A'}")
    L.append("")
    L.append("ITINERARY")
    for seg in data.get("segments", []):
        fl = seg.get("flights", [])
        if not fl:
            continue
        L.append(f"  {str(seg.get('type', 'Flight')).title()} · {fl[0].get('dep_date', '')}")
        for f in fl:
            extra = "  ".join(x for x in ((f.get("cabin") or ""), (f.get("duration") or ""), _seat_text(f)) if x)
            L.append(f"    {f.get('flight_no') or 'N/A'}   {f.get('dep_iata')} {f.get('dep_time')} → {f.get('arr_iata')} {f.get('arr_time')}   {extra}".rstrip())
    if source_ref:
        L += ["", f"Source ref: {source_ref}"]
    L += ["", "(Automated — PIVOT AUTOMATED ITINERARY)"]
    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════════════════
# 2. MANUAL REVIEW — a booking could not be built automatically
# ═════════════════════════════════════════════════════════════════════════════
_PLAIN_REASON = [   # (substring of the technical reason, plain-language version)
    ("missing flight number", "A flight number, airport or time could not be read from the ticket."),
    ("missing pnr", "No booking reference (PNR) could be found in the ticket."),
    ("no passenger", "No passenger name could be found in the ticket."),
    ("missing passenger", "No passenger name could be found in the ticket."),
    ("no segment", "No flights could be found in the ticket."),
    ("not confirmed", "The ticket does not say the booking is confirmed."),
    ("status", "The ticket does not say the booking is confirmed."),
    ("email send", "The PDF was built but the confirmation e-mail failed to send."),
    ("send failed", "The PDF was built but the confirmation e-mail failed to send."),
]


def plain_reason(reason):
    r = (reason or "").lower()
    for key, text in _PLAIN_REASON:
        if key in r:
            return text
    return "The ticket could not be turned into an itinerary automatically."


def flags_subject(flagged):
    n = len(flagged)
    return f"Itinerary — {n} booking(s) need manual review"


def flags_html(flagged, logo_cid=None):
    n = len(flagged)
    head = (f'<tr><td style="padding:22px 26px 6px;font-family:{SANS};"><div style="font-size:22px;font-weight:700;letter-spacing:-.4px;color:{INK};">'
            f'{n} booking{"s" if n != 1 else ""} need{"s" if n == 1 else ""} a person</div>'
            f'<div style="font-size:13.5px;color:{SLATE};margin-top:5px;line-height:1.55;">The automation could not build {"these itineraries" if n != 1 else "this itinerary"} '
            f'safely, so nothing was sent to anyone. Open the e-mail, check the ticket, and issue the PDF by hand.</div></td></tr>')
    cards = ""
    for i, f in enumerate(flagged, 1):
        link = gmail_link(f.get("id"))
        subj_html = (f'<div style="font-size:13px;color:{INK};margin-top:10px;">{_label("Email subject")}{esc(f.get("subject"))}</div>'
                     if f.get("subject") else "")
        cards += (f'<tr><td style="padding:12px 26px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                  f'style="border:1px solid {HAIR};border-left:4px solid {ORANGE};border-radius:12px;"><tr><td style="padding:15px 18px;font-family:{SANS};">'
                  f'<div>{_pill(esc(f.get("portal")), ORANGE)} <span style="font-size:12px;color:{SLATE};margin-left:6px;">#{i}</span></div>'
                  f'<div style="font-size:16px;font-weight:700;color:{INK};margin:10px 0 4px;">{esc(plain_reason(f.get("reason")))}</div>'
                  f'<div style="font-size:12px;color:{SLATE};line-height:1.5;">Detail: {esc(f.get("reason"))}</div>'
                  f'{subj_html}'
                  f'<div style="margin-top:14px;">{_button(link, "Open the e-mail")}</div>'
                  f'<div style="font-size:11px;color:{SLATE};margin-top:10px;">Source ref {esc(f.get("id"))}</div></td></tr></table></td></tr>')
    steps = (f'<tr><td style="padding:18px 26px 22px;font-family:{SANS};font-size:12.5px;color:{SLATE};line-height:1.7;">'
             f'<b style="color:{INK};">How to fix it</b><br>1. Open the e-mail and its PDF.&nbsp; 2. Issue the itinerary by hand (or send its PDF through <b>\\process</b> in the assistant).'
             f'&nbsp; 3. Check names, ticket numbers and times against the ticket before it goes to the client.</td></tr>')
    return _shell(head + cards + steps, logo_cid, "Manual review needed", preheader=f"{n} booking(s) need manual review")


def flags_text(flagged):
    L = [f"{len(flagged)} booking(s) need a person — nothing was sent to anyone.", ""]
    for i, f in enumerate(flagged, 1):
        L += [f"{i}. {f.get('portal')} — {plain_reason(f.get('reason'))}",
              f"   Detail:     {f.get('reason')}"]
        if f.get("subject"):
            L.append(f"   Subject:    {f.get('subject')}")
        L += [f"   Open:       {gmail_link(f.get('id'))}", f"   Source ref: {f.get('id')}", ""]
    L += ["How to fix: open the e-mail, issue it by hand (or run its PDF through \\process), and check", "names, tickets and times before it goes to the client.", "(Automated — PIVOT AUTOMATED ITINERARY)"]
    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════════════════
# 3. DISRUPTION — an airline cancelled / changed / delayed a flight
# ═════════════════════════════════════════════════════════════════════════════
def enrich(alerts):
    out = []
    for a in alerts:
        cat = extractors.disruption_category(a.get("subject", ""), a.get("snippet", ""), a.get("keyword", ""))
        out.append({**a, "category": cat, "sev": SEVERITY[cat],
                    "sum": extractors.disruption_summary(a.get("subject", ""), a.get("snippet", ""), a.get("from", ""))})
    out.sort(key=lambda a: a["sev"]["rank"])
    return out


def count_phrase(enriched):
    order = ("cancellation", "schedule_change", "delay")
    parts = []
    for c in order:
        n = sum(1 for a in enriched if a["category"] == c)
        if n:
            parts.append(f'{n} {SEVERITY[c]["label"].lower() if n == 1 else SEVERITY[c]["plural"]}')
    return ", ".join(parts)


def disruption_subject(enriched):
    pnrs = [a["sum"]["pnr"] for a in enriched if a["sum"]["pnr"]]
    tail = f' ({", ".join(dict.fromkeys(pnrs))})' if pnrs else ""
    return f"⚠️ ACTION REQUIRED — {count_phrase(enriched)}{tail}"


def disruption_html(enriched, logo_cid=None):
    n = len(enriched)
    head = (f'<tr><td style="padding:22px 26px 4px;font-family:{SANS};"><div style="font-size:22px;font-weight:700;letter-spacing:-.4px;color:{INK};">'
            f'{n} flight alert{"s" if n != 1 else ""} to deal with</div>'
            f'<div style="font-size:14px;color:{SLATE};margin-top:4px;">{esc(count_phrase(enriched))} &middot; most urgent first</div></td></tr>'
            f'<tr><td style="padding:14px 26px 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{GRP};border-radius:12px;"><tr><td style="padding:13px 16px;font-family:{SANS};font-size:13px;color:{INK};line-height:1.65;">'
            f'<b>What to do, for each alert</b>'
            f'<div style="margin-top:5px;"><b style="color:{GOLD_INK};">1</b>&nbsp; Open the airline&rsquo;s e-mail.</div>'
            f'<div><b style="color:{GOLD_INK};">2</b>&nbsp; Confirm it is real and which booking it affects.</div>'
            f'<div><b style="color:{GOLD_INK};">3</b>&nbsp; Forward it to the client (use the attached revised itinerary if there is one).</div></td></tr></table></td></tr>')
    cards = ""
    for a in enriched:
        sev, s = a["sev"], a["sum"]
        link = gmail_link(a.get("id"))
        facts = []
        if s["pnr"]:     facts.append(("Booking ref.", s["pnr"]))
        if s["flights"]: facts.append(("Flight", " · ".join(s["flights"])))
        if s["routes"]:  facts.append(("Route", " · ".join(s["routes"])))
        if s["dates"]:   facts.append(("Date", " · ".join(s["dates"])))
        if s["times"]:   facts.append(("Times mentioned", " · ".join(s["times"])))
        fact_cells = "".join(
            f'<td style="padding:0 18px 8px 0;vertical-align:top;font-family:{SANS};">{_label(k)}'
            f'<div style="font-size:{"18" if k == "Booking ref." else "14"}px;font-weight:700;color:{INK};{"letter-spacing:.5px;" if k == "Booking ref." else ""}">{esc(v)}</div></td>'
            for k, v in facts)
        facts_html = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:12px;"><tr>{fact_cells}</tr></table>'
                      f'<div style="font-size:11px;color:{SLATE};margin:-2px 0 8px;">Read from the subject and preview — confirm in the e-mail.</div>') if facts else ""
        snip = f'<br><span style="color:{SLATE};">{esc(a.get("snippet"))}</span>' if a.get("snippet") else ""
        quote = (f'<div style="margin-top:10px;background:{GRP};border-radius:10px;padding:10px 13px;font-size:13px;color:{INK};line-height:1.55;">'
                 f'<span style="color:{SLATE};font-size:11px;font-weight:600;">THE AIRLINE WROTE</span><br>{esc(a.get("subject"))}{snip}</div>')
        revised = ""
        if a.get("revised_pdf"):
            revised = (f'<div style="margin-top:10px;background:#eef8f2;border:1px solid #cfe9db;border-radius:10px;padding:10px 13px;'
                       f'font-size:13px;color:{GREEN};line-height:1.5;">&#128206; <b>Draft revised itinerary attached</b> '
                       f'({esc(os.path.basename(a["revised_pdf"]))}). Check it against the airline e-mail before you forward it.</div>')
        cards += (f'<tr><td style="padding:12px 26px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                  f'style="border:1px solid {HAIR};border-left:5px solid {sev["color"]};border-radius:14px;"><tr><td style="padding:16px 18px;font-family:{SANS};">'
                  f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td>{_pill(sev["label"].upper(), sev["color"])}</td>'
                  f'<td align="right" style="font-size:12px;color:{SLATE};">Received {esc(received(a.get("date")))}</td></tr></table>'
                  f'<div style="font-size:17px;font-weight:700;color:{INK};margin-top:11px;">{esc(s["airline"])} — {esc(sev["headline"].lower())}</div>'
                  f'{facts_html}{quote}{revised}'
                  f'<div style="margin-top:14px;">{_button(link, "Open the airline e-mail")}</div>'
                  f'<div style="font-size:11px;color:{SLATE};margin-top:10px;">Source ref {esc(a.get("id"))}</div></td></tr></table></td></tr>')
    foot = (f'<tr><td style="padding:16px 26px 22px;font-family:{SANS};font-size:12px;color:{SLATE};line-height:1.6;">'
            f'This watch is automatic and read-only: it never replies to, forwards or changes any e-mail. Re-sent copies of the same notice are suppressed, '
            f'but a new revision, or a delay that becomes a cancellation, alerts again.</td></tr>')
    return _shell(head + cards + foot, logo_cid, "Flight alerts", preheader=f"{count_phrase(enriched)} — open each airline e-mail and forward it to the client.")


def disruption_text(enriched):
    L = [f"ACTION REQUIRED — {len(enriched)} flight alert(s): {count_phrase(enriched)}  (most urgent first)", "",
         "For each: open the airline's e-mail → confirm it is real and which booking it affects → forward it to the client", "(use the attached revised itinerary if there is one).", ""]
    for a in enriched:
        sev, s = a["sev"], a["sum"]
        L.append(f"[{sev['label'].upper()}]  {s['airline']} — {sev['headline'].lower()}   (received {received(a.get('date'))})")
        bits = [f"{k}: {v}" for k, v in (("Booking ref", s["pnr"]), ("Flight", " · ".join(s["flights"])), ("Route", " · ".join(s["routes"])),
                                         ("Date", " · ".join(s["dates"])), ("Times mentioned", " · ".join(s["times"]))) if v]
        if bits:
            L.append("  " + "   ".join(bits) + "   (read from the subject/preview — confirm in the e-mail)")
        L.append(f"  Subject:    {a.get('subject')}")
        if a.get("snippet"):
            L.append(f"  Preview:    {a['snippet']}")
        L.append(f"  Open:       {gmail_link(a.get('id'))}")
        L.append(f"  Source ref: {a.get('id')}")
        if a.get("revised_pdf"):
            L.append(f"  >> Draft revised itinerary attached ({os.path.basename(a['revised_pdf'])}) — check it against the airline e-mail before forwarding.")
        L.append("")
    L.append("(Automated, read-only watch — PIVOT AUTOMATED ITINERARY)")
    return "\n".join(L)
