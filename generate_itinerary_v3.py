#!/usr/bin/env python3
"""
Pivot Travel & Tourism — Itinerary PDF Generator v3
Design: 7BBKYN approved reference.
White header · light ref strip · dark navy segment bars · white flight cards · dark navy footer.
Gold accent #c9a84c · Navy #0b1724 · Fonts: Cormorant Garamond + Inter.

Usage:
    python3 generate_itinerary_v3.py --data '<json>' --out-dir '/path/'
"""

import json, sys, os, tempfile, base64, re
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


def _segment_header(seg_type: str, flights: list) -> str:
    if not flights:
        return ""
    first    = flights[0]
    last     = flights[-1]
    dep_city = first.get("dep_city", first.get("dep_iata", "")).upper()
    arr_city = last.get("arr_city",  last.get("arr_iata",  "")).upper()
    dep_date = first.get("dep_date", "")
    label    = seg_type.upper()
    route    = f"{dep_city} TO {arr_city}"
    full_date = _weekday_date(dep_date)
    return f"""
    <div class="seg-header">
      <span class="seg-route">&#x2794; {label} &mdash; {route}</span>
      <span class="seg-date">{full_date}</span>
    </div>"""


def _flight_card(seg: dict, standalone: bool = False) -> str:
    dep_iata     = seg.get("dep_iata", "???")
    arr_iata     = seg.get("arr_iata", "???")
    dep_city     = seg.get("dep_city", "")
    arr_city     = seg.get("arr_city", "")
    dep_airport  = seg.get("dep_airport", "")
    arr_airport  = seg.get("arr_airport", "")
    dep_terminal = seg.get("terminal", "")
    dep_date     = seg.get("dep_date", "")
    dep_time     = seg.get("dep_time", "")
    arr_date     = seg.get("arr_date", "")
    arr_time     = seg.get("arr_time", "")
    flight_no    = _na(seg.get("flight_no", "N/A"))
    airline      = _na(seg.get("airline", "N/A"))
    cabin        = _na(seg.get("cabin", "N/A"))
    duration     = seg.get("duration", "")

    dep_sub = dep_airport or ""
    if dep_terminal and dep_sub:
        dep_sub += f" &middot; Terminal {dep_terminal}"
    elif dep_terminal:
        dep_sub = f"Terminal {dep_terminal}"
    arr_sub = arr_airport or ""

    dep_sub_html  = f'<div class="ap-detail">{dep_sub}</div>' if dep_sub else ""
    arr_sub_html  = f'<div class="ap-detail">{arr_sub}</div>' if arr_sub else ""
    duration_html = (
        f'<div class="meta-item">'
        f'<span class="meta-lbl">DURATION</span>'
        f'<span class="meta-val">{duration}</span>'
        f'</div>'
    ) if duration else ""

    card_cls = "flight-card standalone" if standalone else "flight-card"
    return f"""
    <div class="{card_cls}">
      <div class="route-row">
        <div class="ap-block">
          <div class="iata">{dep_iata}</div>
          <div class="ap-city">{dep_city}</div>
          {dep_sub_html}
          <div class="flight-time">{dep_time}</div>
          <div class="flight-date">{dep_date}</div>
        </div>

        <div class="connector">
          <div class="conn-dot"></div>
          <div class="conn-line">
            <div class="conn-center">
              <div class="conn-flight-no">{flight_no}</div>
              <div class="conn-airline">{airline}</div>
            </div>
          </div>
          <div class="conn-dot"></div>
        </div>

        <div class="ap-block ap-right">
          <div class="iata">{arr_iata}</div>
          <div class="ap-city">{arr_city}</div>
          {arr_sub_html}
          <div class="flight-time">{arr_time}</div>
          <div class="flight-date">{arr_date}</div>
        </div>
      </div>

      <div class="meta-row">
        <div class="meta-item">
          <span class="meta-lbl">FLIGHT NO.</span>
          <span class="meta-val">{flight_no}</span>
        </div>
        <div class="meta-item">
          <span class="meta-lbl">OPERATED BY</span>
          <span class="meta-val">{airline}</span>
        </div>
        <div class="meta-item">
          <span class="meta-lbl">CABIN CLASS</span>
          <span class="meta-val">{cabin}</span>
        </div>
        {duration_html}
      </div>
    </div>"""


def _layover_bar(layover: dict) -> str:
    airport  = layover.get("airport", "")
    duration = layover.get("duration", "")
    return f"""
    <div class="layover-bar">
      <div class="lay-line"></div>
      <div class="lay-badge">LAYOVER &nbsp;{airport} &middot; {duration}</div>
      <div class="lay-line"></div>
    </div>"""


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


def _norm_bag(v: str) -> str:
    # Baggage values show weight only. "1 pc 7kg + personal item 3kg" -> "7kg + 3kg".
    # Multiple weights joined with " + ". Piece-only values (no kg) -> "<n>Pcs". No dimensions/extras.
    if not v:
        return "N/A"
    s = v.strip()
    if s.lower() == "not specified":
        return "N/A"
    weights = re.findall(r'(\d+(?:\.\d+)?)\s*(?:kilograms?|kgs?|kg|k)\b', s, flags=re.I)
    if weights:
        out = []
        for w in weights:
            f = float(w)
            out.append(f"{int(f)}kg" if f.is_integer() else f"{f}kg")
        return " + ".join(out)
    pcs = re.search(r'(\d+)\s*(?:pcs?|pieces?|pc|p)\b', s, flags=re.I)
    if pcs:
        return f"{int(pcs.group(1))}Pcs"
    return s


def _pax_card(pax: dict) -> str:
    name    = _title_name(pax.get("name", "N/A"))
    tkt     = _na(pax.get("ticket_no", "N/A"))
    cabin   = _norm_bag(pax.get("cabin_bag", "N/A"))
    checked = _norm_bag(pax.get("checked_bag", "N/A"))
    seat    = pax.get("seat", "")
    seat_html = (
        f'<div class="pax-col">'
        f'<div class="pax-lbl">SEAT</div>'
        f'<div class="pax-val">{seat}</div>'
        f'</div>'
    ) if seat else ""
    return f"""
    <div class="pax-card">
      <div class="pax-col pax-name-col">
        <div class="pax-lbl">PASSENGER NAME</div>
        <div class="pax-name">{name}</div>
      </div>
      <div class="pax-col">
        <div class="pax-lbl">TICKET NO.</div>
        <div class="pax-val">{tkt}</div>
      </div>
      <div class="pax-col">
        <div class="pax-lbl">CABIN BAGGAGE</div>
        <div class="pax-val">{cabin}</div>
      </div>
      <div class="pax-col">
        <div class="pax-lbl">CHECKED BAGGAGE</div>
        <div class="pax-val">{checked}</div>
      </div>
      {seat_html}
    </div>"""


# ── Terms & Conditions (static, identical on every itinerary) ─────────────────
def _terms_block() -> str:
    items = [
        ("1.", "Ticket Validity &amp; Changes",
         "Travel is valid only for the date, flight, and class specified. Name changes are not permitted after ticketing. Date or routing changes are subject to carrier fare rules and applicable fees. Refunds are governed by the purchased fare conditions. Unused outbound segments may result in automatic cancellation of onward flights (no-show policy)."),
        ("2.", "Check-In &amp; Boarding",
         "Passengers must arrive at the airport with sufficient time to complete check-in and boarding. Check-in deadlines and gate closing times are set by the operating carrier &mdash; confirm prior to travel. Denied boarding due to late arrival is not the liability of Pivot Travel &amp; Tourism. Valid photo ID or passport matching the ticket name is mandatory at all times."),
        ("3.", "Baggage &mdash; Inclusions",
         "Cabin and checked baggage allowances are determined by the operating carrier and fare class purchased. Confirm weight limits, piece count, and size restrictions directly with the carrier before travel. Allowances are per passenger and non-transferable."),
        ("4.", "Baggage &mdash; Exclusions &amp; Restrictions",
         "Excess baggage charges apply for any baggage exceeding permitted allowances and are payable directly to the carrier at airport rates. Prohibited items include explosives, flammable materials, compressed gases, and all items restricted under IATA Dangerous Goods Regulations. Liquids in cabin baggage are subject to airport security limits. Spare lithium batteries and power banks must be carried in cabin baggage only. Pivot Travel &amp; Tourism and the carrier accept no liability for fragile, valuable, or perishable items in checked baggage."),
        ("5.", "Travel Documents &amp; Visa",
         "Passengers are solely responsible for holding valid passports, visas, transit permits, and any health documentation required for all points of travel including transit countries. Pivot Travel &amp; Tourism may provide general guidance only. Denied boarding or deportation due to inadequate documents does not entitle the passenger to a refund."),
        ("6.", "Flight Disruptions",
         "In the event of cancellation, significant delay, or denied boarding, passenger rights are governed by the operating carrier's conditions of carriage and applicable GACA regulations. Pivot Travel &amp; Tourism will assist where possible but holds no financial liability for disruptions caused by the carrier, weather, force majeure, or events beyond its control."),
        ("7.", "Liability &amp; Governing Law",
         "Pivot Travel &amp; Tourism acts solely as a ticketing agent. Its liability is limited to the agency service fee paid. These terms are governed by the laws of the Kingdom of Saudi Arabia. Disputes are subject to the jurisdiction of the competent courts of Riyadh, KSA, without prejudice to applicable GACA regulations and international conventions."),
    ]
    items_html = "\n".join(
        f'<div class="tc-item"><span class="tc-n"><span class="tc-acc">{n}</span> {h}</span>{body}</div>'
        for (n, h, body) in items
    )
    return f"""
  <div class="tc">
    <div class="tc-title">TERMS &amp; CONDITIONS <span class="tc-acc">&mdash;</span> FLIGHT BOOKING CONFIRMATION</div>
    <div class="tc-issued">Issued by Pivot Travel &amp; Tourism &middot; Suite 20, 2762 Ibn Al Anbari Street, Al Amal District, Riyadh, Kingdom of Saudi Arabia &middot; Clarifications: cs@pivot-travels.com</div>
    <div class="tc-rule"></div>
    <div class="tc-cols">
      {items_html}
    </div>
    <div class="tc-close">This document is system-generated and valid without a signature. &nbsp; Pivot Travel &amp; Tourism &middot; cs@pivot-travels.com</div>
  </div>"""


# ── HTML Builder ──────────────────────────────────────────────────────────────
def build_html(data: dict, project_dir: str = None, layout: str = "B") -> str:
    pnr          = data.get("pnr", "N/A")
    booking_ref  = data.get("booking_ref") or ""
    crs_ref      = data.get("crs_ref") or ""
    booked_on    = data.get("booked_on", "N/A")
    # Journey type label: exactly ONE-WAY or ROUND TRIP (no RETURN / MULTI-CITY /
    # CONNECTING wording — locked rule).
    _jt = (data.get("journey_type") or "ONE-WAY").upper()
    journey_type = "ROUND TRIP" if ("RETURN" in _jt or "ROUND" in _jt) else "ONE-WAY"
    passengers   = data.get("passengers", [])
    seg_groups   = data.get("segments", [])

    logo_b64 = _logo_b64(project_dir)
    if logo_b64:
        logo_html = (
            f'<img class="logo-img" src="data:image/png;base64,{logo_b64}" '
            f'alt="Pivot Travel &amp; Tourism">'
        )
        footer_logo_html = (
            f'<img class="footer-logo-img" src="data:image/png;base64,{logo_b64}" '
            f'alt="Pivot Travel &amp; Tourism">'
        )
    else:
        logo_html = (
            '<div class="logo-fallback">'
            '<span class="logo-text-main">Pivot Travel &amp; Tourism</span>'
            '</div>'
        )
        footer_logo_html = '<span style="font-family:Inter,sans-serif;font-size:13px;font-weight:700;color:#fff;">Pivot Travel &amp; Tourism</span>'

    # Ref strip — show booking_ref if present; crs_ref only if differs from pnr
    booking_ref_col = f"""
      <div class="ref-col">
        <div class="ref-lbl">Booking Ref.</div>
        <div class="ref-val">{booking_ref}</div>
      </div>""" if booking_ref else ""

    show_crs = crs_ref and crs_ref.upper() != pnr.upper()
    crs_col = f"""
      <div class="ref-col">
        <div class="ref-lbl">CRS Ref.</div>
        <div class="ref-val">{crs_ref}</div>
      </div>""" if show_crs else ""

    pax_html  = "\n".join(_pax_card(p) for p in passengers) if passengers else _pax_card({"name": "N/A"})

    segs_html = ""
    for grp in seg_groups:
        flights  = grp.get("flights", [])
        layovers = grp.get("layovers", [])
        segs_html += _segment_header(grp.get("type", "ONE-WAY"), flights)
        for fi, flight in enumerate(flights):
            segs_html += _flight_card(flight, standalone=(fi > 0))
            if fi < len(layovers):
                segs_html += _layover_bar(layovers[fi])

    footer_line  = f'PIVOT AUTOMATED ITINERARY &nbsp;|&nbsp; {pnr} &nbsp;|&nbsp; WWW.PIVOT-TRAVELS.COM'
    footer_html  = f'<div class="footer"><span class="footer-line">{footer_line}</span></div>'
    terms_html   = _terms_block()

    header_html = f"""
  <div class="header">
    <div class="header-left">
      {logo_html}
      <div>
        <div class="doc-label">Official Travel Document</div>
        <div class="doc-title">
          <span class="doc-title-bold">Booking </span><span class="doc-title-light">Confirmation</span>
        </div>
      </div>
    </div>
    <div class="header-center"></div>
    <div class="header-right">
      <div class="confirmed-pill">
        <span class="pill-dot"></span>
        <span class="pill-text">Confirmed</span>
      </div>
      <div class="pnr-block">
        <div class="pnr-value">{pnr}</div>
        <div class="pnr-label">PNR Reference</div>
      </div>
    </div>
  </div>"""

    ref_html = f"""
  <div class="ref-strip">
    {booking_ref_col}
    {crs_col}
    <div class="ref-col">
      <div class="ref-lbl">Booked On</div>
      <div class="ref-val">{booked_on}</div>
    </div>
    <div class="ref-col">
      <div class="ref-lbl">Journey Type</div>
      <div class="ref-val">{journey_type}</div>
    </div>
  </div>"""

    content_html = f"""
  <div class="content">
    <div class="section">
      <div class="section-hdr">
        <div class="section-icon"></div>
        <div class="section-title">Passenger Information</div>
        <div class="section-rule"></div>
      </div>
      {pax_html}
    </div>
    <div class="section">
      <div class="section-hdr">
        <div class="section-icon"></div>
        <div class="section-title">Flight Itinerary</div>
        <div class="section-rule"></div>
      </div>
      {segs_html}
    </div>
  </div>"""

    if layout == "A":
        # Itinerary fits one page → page 1 = itinerary + footer; page 2 = T&C + footer.
        body_html = f"""
  <div class="sheet sheet-itin">
    {header_html}{ref_html}{content_html}{footer_html}
  </div>
  <div class="sheet sheet-tc">
    {terms_html}
    {footer_html}
  </div>"""
    elif layout == "measure":
        # Measurement pass — itinerary + its footer only, natural height.
        body_html = f"""
  <div class="page-measure">
    {header_html}{ref_html}{content_html}{footer_html}
  </div>"""
    else:
        # layout "B" — itinerary spills: no page-1 footer; cards flow, then T&C,
        # then a single footer pinned to the bottom of the last page.
        footer_abs = footer_html.replace('class="footer"', 'class="footer footer-abs"')
        body_html = f"""
  <div class="page-flow">
    {header_html}{ref_html}{content_html}
    {terms_html}
    {footer_abs}
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Booking Confirmation — {pnr}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
/* Full-bleed first page (navy header touches the top edge); every following
   page gets a top margin so flowing flight cards never butt against the edge. */
@page {{ size: A4; margin: 12mm 0 0 0; }}
@page :first {{ margin: 0; }}
body {{
  font-family: 'Inter', Helvetica, Arial, sans-serif;
  background: #eef0f3;
  color: #1a2332;
  font-size: 13px;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}
.page {{
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  background: #fff;
  box-shadow: 0 4px 40px rgba(0,0,0,0.10);
  display: flex;
  flex-direction: column;
}}

/* ── Header ── */
.header {{
  background: linear-gradient(135deg, #071220 0%, #0b1f38 45%, #112d4e 100%);
  padding: 14px 28px 12px;
  display: flex;
  align-items: center;
  border-bottom: 2px solid #c9a84c;
}}
/* Layout: LEFT = logo + title stacked  |  RIGHT = pill + PNR */
.header-left {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 10px;
}}
.logo-img {{
  height: 52px;
  width: auto;
  object-fit: contain;
  display: block;
  filter: brightness(0) invert(1);
}}
.logo-fallback {{
  display: flex;
  flex-direction: column;
  gap: 2px;
}}
.logo-text-main {{
  font-family: 'Inter', sans-serif;
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
}}
.header-center {{ display: none; }}
.doc-label {{
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: 3px;
  color: #c9a84c;
  text-transform: uppercase;
  margin-bottom: 5px;
  display: block;
}}
.doc-title {{
  font-family: 'Cormorant Garamond', serif;
  font-style: normal;
  font-size: 26px;
  color: #ffffff;
  line-height: 1.1;
  letter-spacing: 0.5px;
  white-space: nowrap;
  display: block;
}}
.doc-title-bold {{
  font-weight: 700;
}}
.doc-title-light {{
  font-weight: 400;
}}
.header-right {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 8px;
}}
.confirmed-pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1.5px solid #c9a84c;
  border-radius: 20px;
  padding: 4px 12px;
}}
.pill-dot {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #c9a84c;
  flex-shrink: 0;
}}
.pill-text {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #c9a84c;
  text-transform: uppercase;
}}
.pnr-block {{ text-align: right; }}
.pnr-value {{
  font-family: 'Cormorant Garamond', serif;
  font-style: normal;
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 3px;
  line-height: 1;
  font-variant-numeric: lining-nums;
  font-feature-settings: "lnum" 1;
}}
.pnr-label {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 2px;
  color: rgba(201,168,76,0.80);
  text-transform: uppercase;
  margin-top: 3px;
  text-align: right;
}}

/* ── Ref Strip — navy gradient, centred, ALL CAPS values ── */
.ref-strip {{
  background: linear-gradient(135deg, #071220 0%, #0b1f38 45%, #112d4e 100%);
  padding: 10px 28px;
  display: flex;
  gap: 0;
  border-bottom: 2px solid rgba(201,168,76,0.35);
}}
.ref-col {{
  flex: 1;
  text-align: center;
  padding: 0 8px;
  border-right: 1px solid rgba(201,168,76,0.20);
}}
.ref-col:last-child {{
  border-right: none;
}}
.ref-lbl {{
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 1.5px;
  color: rgba(201,168,76,0.75);
  text-transform: uppercase;
  margin-bottom: 5px;
}}
.ref-val {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 15px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 1px;
  text-transform: uppercase;
  font-variant-numeric: lining-nums;
  font-feature-settings: "lnum" 1;
}}

/* ── Content ── */
.content {{
  padding: 10px 28px 6px;
  background: #fff;
}}
.section {{ margin-bottom: 10px; }}
.section-hdr {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}}
.section-icon {{
  width: 14px;
  height: 14px;
  background: #0b1724;
  border-radius: 3px;
  flex-shrink: 0;
}}
.section-title {{
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 2.5px;
  color: #0b1724;
  text-transform: uppercase;
}}
.section-rule {{
  flex: 1;
  height: 1px;
  background: #e2e5ea;
}}

/* ── Passenger card ── */
.pax-card {{
  display: flex;
  gap: 0;
  border: 1px solid #e2e5ea;
  border-radius: 8px;
  padding: 9px 20px;
  background: #fafbfc;
  margin-bottom: 8px;
  flex-wrap: wrap;
  page-break-inside: avoid;
}}
.pax-col {{
  flex: 1;
  min-width: 100px;
  padding: 0 8px;
  text-align: center;
}}
.pax-name-col {{ flex: 1.4; }}
.pax-lbl {{
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 1.5px;
  color: #8a9bb0;
  text-transform: uppercase;
  margin-bottom: 6px;
}}
.pax-name, .pax-val {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 18px;
  font-weight: 700;
  color: #0b1724;
  letter-spacing: 0.5px;
  line-height: 1.2;
  font-variant-numeric: lining-nums;
  font-feature-settings: "lnum" 1;
}}
/* Long passenger names wrap cleanly within the column instead of overflowing. */
.pax-name {{
  overflow-wrap: break-word;
  word-break: break-word;
}}

/* ── Segment header ── */
.seg-header {{
  background: #0b1724;
  padding: 7px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-radius: 7px 7px 0 0;
  page-break-inside: avoid;
  page-break-after: avoid;
  break-after: avoid;
}}
.seg-route {{
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}}
.seg-date {{
  font-size: 10px;
  font-weight: 400;
  color: rgba(255,255,255,0.55);
  letter-spacing: 0.3px;
}}

/* ── Flight card ── */
.flight-card {{
  border: 1px solid #e2e5ea;
  border-top: none;
  border-radius: 0 0 7px 7px;
  background: #fff;
  padding: 6px 20px 5px;
  margin-bottom: 6px;
  page-break-inside: avoid;
}}
/* A flight card that follows a layover stands on its own (full border, all corners rounded). */
.flight-card.standalone {{
  border-top: 1px solid #e2e5ea;
  border-radius: 7px;
}}
.route-row {{
  display: flex;
  align-items: flex-start;
  margin-bottom: 6px;
}}
.ap-block {{
  display: flex;
  flex-direction: column;
  width: 160px;
}}
.ap-right {{
  align-items: flex-end;
  text-align: right;
}}
.iata {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 40px;
  font-weight: 700;
  color: #0b1724;
  letter-spacing: -1.5px;
  line-height: 1;
  margin-bottom: 1px;
}}
.ap-city {{
  font-size: 11px;
  font-weight: 700;
  color: #0b1724;
  margin-bottom: 1px;
}}
.ap-detail {{
  font-size: 8.5px;
  color: #8a9bb0;
  line-height: 1.15;
  margin-bottom: 1px;
}}
.flight-time {{
  font-size: 20px;
  font-weight: 700;
  color: #0b1724;
  letter-spacing: 0.5px;
  margin-bottom: 1px;
}}
.flight-date {{
  font-size: 9px;
  color: #8a9bb0;
  font-weight: 500;
}}

/* ── Connector ── */
.connector {{
  flex: 1;
  display: flex;
  align-items: center;
  padding: 0 6px;
  margin-top: 11px;        /* drop the line onto the horizontal mid-line of the IATA codes */
}}
.conn-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c9a84c;
  flex-shrink: 0;
}}
.conn-line {{
  flex: 1;
  position: relative;
  border-top: 1.5px solid #c9a84c;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.conn-center {{
  position: absolute;
  left: 50%;
  top: 0;
  transform: translate(-50%, -50%);   /* centre the flight label ON the line */
  background: #fff;
  padding: 0 12px;
  text-align: center;
  white-space: nowrap;
}}
.conn-plane {{
  font-size: 15px;
  color: #c9a84c;
  line-height: 1;
  margin-bottom: 1px;
}}
.conn-flight-no {{
  font-size: 11px;
  font-weight: 700;
  color: #0b1724;
  letter-spacing: 0.5px;
  line-height: 1.1;
}}
.conn-airline {{
  font-size: 9px;
  color: #8a9bb0;
  font-weight: 400;
  line-height: 1;
}}

/* ── Meta row ── */
.meta-row {{
  display: flex;
  justify-content: space-around;
  align-items: flex-start;
  border-top: 1px solid #f0f2f5;
  padding-top: 6px;
  width: 100%;
}}
.meta-item {{
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 3px;
  flex: 1;
}}
.meta-lbl {{
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 1.5px;
  color: #8a9bb0;
  text-transform: uppercase;
}}
.meta-val {{
  font-size: 12px;
  font-weight: 600;
  color: #1a2332;
}}

/* ── Layover — detached, centred transit badge ── */
.layover-bar {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin: 6px 6px;
  padding: 0;
  background: transparent;
  page-break-inside: avoid;
  break-after: avoid;
  page-break-after: avoid;
}}
.lay-line {{
  flex: 1;
  height: 0;
  border-top: 1px dashed rgba(201,168,76,0.55);
}}
.lay-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #fbf8ef;
  color: #0b1724;
  border: 1px solid #c9a84c;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.5px;
  padding: 6px 16px;
  border-radius: 16px;
  text-transform: uppercase;
  white-space: nowrap;
  box-shadow: 0 1px 3px rgba(11,23,36,0.06);
}}
.lay-icon {{
  color: #c9a84c;
  font-size: 11px;
  line-height: 1;
}}

/* ── Footer ── */
.footer {{
  flex-shrink: 0;            /* never compress; sits at the bottom of the (last) page */
  page-break-inside: avoid;
  break-inside: avoid;
  text-align: center;
  padding: 6px 28px 8px;
  border-top: 1px solid #e7e9ee;
  margin-top: 2px;
}}
.footer-line {{
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #9aa6b4;            /* low-key muted grey */
}}

/* ── Page sheets (layout wrappers) ── */
.sheet {{
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  background: #fff;
  display: flex;
  flex-direction: column;
}}
.sheet-itin .content {{ flex: 1 0 auto; }}   /* push the page-1 footer to the bottom */
.sheet-tc {{
  min-height: 285mm;                         /* page 2 printable = 297mm - 12mm top margin */
  justify-content: space-between;            /* T&C at top, footer at the bottom */
  page-break-before: always;
  break-before: page;
}}
.page-flow {{
  position: relative;          /* anchor for the absolutely-pinned footer */
  width: 210mm;
  min-height: 297mm;
  margin: 0 auto;
  background: #fff;
  display: flex;
  flex-direction: column;
}}
/* Layout-B footer: out of flow, pinned to the bottom edge of the (grown) sheet so
   it sits at the bottom of the LAST page without fighting the T&C break rules. */
.footer-abs {{
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
}}
.page-measure {{ width: 210mm; margin: 0 auto; background: #fff; }}

/* ── Terms & Conditions (static, ~half page) ── */
.tc {{
  padding: 16px 28px 8px;
  page-break-inside: avoid;
  break-inside: avoid;
}}
.tc-title {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 17px;
  font-weight: 700;
  color: #0b1724;
  letter-spacing: 0.4px;
  text-transform: uppercase;
}}
.tc-issued {{
  font-size: 8px;
  color: #6b7a8d;
  line-height: 1.45;
  margin-top: 4px;
}}
.tc-rule {{
  height: 2px;
  background: linear-gradient(90deg, #c9a84c 0%, rgba(201,168,76,0) 100%);
  margin: 8px 0 10px;
}}
.tc-cols {{
  column-count: 2;
  column-gap: 22px;
}}
.tc-item {{
  break-inside: avoid;
  margin-bottom: 7px;
  font-size: 7.4px;
  line-height: 1.45;
  color: #46525f;
  text-align: justify;
}}
.tc-n {{
  display: block;
  font-size: 8px;
  font-weight: 700;
  color: #0b1724;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-bottom: 2px;
}}
.tc-acc {{ color: #c9a84c; }}
.tc-close {{
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid #e7e9ee;
  font-size: 7px;
  font-style: italic;
  color: #6b7a8d;
  text-align: center;
}}

@media print {{
  body {{ background: #fff; }}
  .page, .sheet, .page-flow {{ box-shadow: none; }}
}}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


# ── PDF Builder ───────────────────────────────────────────────────────────────
def build_pdf(booking_data: dict, out_dir: str, project_dir: str = None) -> str:
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pnr = booking_data.get("pnr", "UNKNOWN")
    pdf_path = out_dir / f"{pnr}.pdf"

    # No explicit margin → the CSS @page rules apply (page 1 full-bleed,
    # pages 2+ get a 12mm top margin).
    pdf_opts = dict(format="A4", print_background=True)

    def _count(p) -> int:
        try:
            import pdfplumber
            with pdfplumber.open(str(p)) as _pdf:
                return len(_pdf.pages)
        except Exception:
            return 1

    def _write(html: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        f.write(html)
        f.close()
        return f.name

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page    = browser.new_page()
        page.emulate_media(media="screen")

        # ── Pass 1: measure the itinerary (incl. its footer) to choose a layout ──
        #   itinerary fits 1 page  → layout "A": page1 = itinerary + footer,
        #                                         page2 = Terms & Conditions + footer.
        #   itinerary spills        → layout "B": no page-1 footer; cards flow on,
        #                                         then T&C, then ONE footer pinned
        #                                         to the bottom of the last page.
        m_html = _write(build_html(booking_data, project_dir=project_dir, layout="measure"))
        m_pdf  = str(out_dir / f".{pnr}_measure.pdf")
        page.goto(f"file://{m_html}", wait_until="networkidle")
        page.pdf(path=m_pdf, **pdf_opts)
        os.unlink(m_html)
        itin_pages = _count(m_pdf)
        try:
            os.unlink(m_pdf)
        except OSError:
            pass
        layout = "A" if itin_pages == 1 else "B"

        # ── Pass 2: final render ──
        f_html = _write(build_html(booking_data, project_dir=project_dir, layout=layout))
        page.goto(f"file://{f_html}", wait_until="networkidle")
        page.pdf(path=str(pdf_path), **pdf_opts)

        # Layout B: cards flow on, then the T&C block. The footer is absolutely
        # positioned (out of flow) so it never adds a page. Count the content
        # pages, then grow the sheet to exactly that many pages (minus 6mm safety)
        # so the absolute footer lands at the bottom of the LAST page.
        if layout == "B":
            n = _count(pdf_path)
            # Page 1 is full height (297mm); pages 2+ lose 12mm to the top margin
            # (285mm printable). Grow the sheet to the bottom of page n (−6mm safe).
            target = 297 + (n - 1) * 285 - 6
            page.evaluate(
                "(mm) => { const e = document.querySelector('.page-flow');"
                " if (e) e.style.minHeight = mm + 'mm'; }",
                target,
            )
            page.pdf(path=str(pdf_path), **pdf_opts)

        os.unlink(f_html)
        page.close()
        browser.close()

    print(f"✓ PDF saved ({layout}): {pdf_path}")
    return str(pdf_path)


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",        required=True)
    parser.add_argument("--out-dir",     required=True)
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args()
    build_pdf(json.loads(args.data), args.out_dir, args.project_dir)
