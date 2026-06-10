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


# ── HTML Builder ──────────────────────────────────────────────────────────────
def build_html(data: dict, project_dir: str = None) -> str:
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
  flex: 1 0 auto;     /* grow to fill the page so the footer is pinned to the bottom */
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

@media print {{
  body {{ background: #fff; }}
  .page {{ box-shadow: none; }}
}}
</style>
</head>
<body>
<div class="page">

  <!-- Header: LEFT = logo + title  |  RIGHT = pill + PNR -->
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
  </div>

  <!-- Ref Strip -->
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
  </div>

  <!-- Content -->
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

  </div>

  <!-- Footer -->
  <div class="footer">
    <span class="footer-line">PIVOT AUTOMATED ITINERARY &nbsp;|&nbsp; {pnr} &nbsp;|&nbsp; WWW.PIVOT-TRAVELS.COM</span>
  </div>

</div>
</body>
</html>"""


# ── PDF Builder ───────────────────────────────────────────────────────────────
def build_pdf(booking_data: dict, out_dir: str, project_dir: str = None) -> str:
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pnr = booking_data.get("pnr", "UNKNOWN")

    html_content = build_html(booking_data, project_dir=project_dir)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html_content)
        tmp_html = f.name

    pdf_path = out_dir / f"{pnr}.pdf"

    pdf_opts = dict(format="A4", print_background=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page    = browser.new_page()
            page.emulate_media(media="screen")
            page.goto(f"file://{tmp_html}", wait_until="networkidle")
            page.pdf(path=str(pdf_path), **pdf_opts)
            # Pin the footer to the bottom of the LAST page: count the rendered
            # pages and, if multi-page, grow the sheet to exactly that many full
            # pages. The flex column then drops the footer to the bottom; the
            # cards stay put (the added space lands after the last card). The 4mm
            # trim keeps the footer clear of the print page boundary.
            n = 1
            try:
                import pdfplumber
                with pdfplumber.open(str(pdf_path)) as _pdf:
                    n = len(_pdf.pages)
            except Exception:
                n = 1
            if n > 1:
                page.evaluate("(mm) => { document.querySelector('.page').style.minHeight = mm + 'mm'; }",
                              n * 297 - 4)
                page.pdf(path=str(pdf_path), **pdf_opts)
            page.close()
            browser.close()
    finally:
        os.unlink(tmp_html)

    print(f"✓ PDF saved: {pdf_path}")
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
