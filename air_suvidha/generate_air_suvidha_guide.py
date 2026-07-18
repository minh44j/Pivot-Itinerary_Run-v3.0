#!/usr/bin/env python3
"""
Pivot Travel Management — Air Suvidha 2.0 Passenger Guide  (v4 — decluttered)
============================================================================
Trimmed to essentials: What it is · What to prepare · How to complete it.
Removed vs v3: the "Keep in mind" repetition, the status pill, the QR block,
and the heavy row of micro-labels/dividers — for calmer spacing and hierarchy.

Design language still mirrors the approved itinerary v3:
  charcoal-graphite header/footer (#323234 -> #0e0e0f), gold accent #c9a84c,
  Cormorant Garamond (italic titles) + Inter body, softly rounded cards.

Government attribution renders as a clean text line by default. If you drop
`moca_logo.png` and/or `mohfw_logo.png` next to this script, they are picked up
automatically (no code change). Renders with WeasyPrint.
"""
import base64
import io
from pathlib import Path

import qrcode

HERE       = Path(__file__).parent
OUT_PDF    = HERE / "Air_Suvidha_2.0_Passenger_Guide.pdf"
PORTAL     = "airsuvidha.civilaviation.gov.in"
PORTAL_URL = "https://airsuvidha.civilaviation.gov.in/"


def _b64(p):
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else None


def _qr_b64(data):
    buf = io.BytesIO()
    qrcode.make(data, border=1).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


QR_B64 = _qr_b64(PORTAL_URL)


def _find(name):
    """Look next to this script first, then the repo root (where logo.png lives)."""
    for p in (HERE / name, HERE.parent / name):
        if p.exists():
            return p
    return HERE / name


LOGO_B64  = _b64(_find("logo.png"))
MOCA_B64  = _b64(_find("moca_logo.png"))     # optional — text fallback if absent
MOHFW_B64 = _b64(_find("mohfw_logo.png"))    # optional — text fallback if absent

# ── SVG icons (stroke = currentColor) ────────────────────────────────────────
ICONS = {
    "passport": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="5" y="2.5" width="14" height="19" rx="2"/><circle cx="12" cy="10" r="3"/><path d="M9 16h6M8 19h8"/></svg>',
    "phone":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6.5 3h3l1.5 4.5-2 1.7a12 12 0 0 0 5.8 5.8l1.7-2L21 14.5v3a2 2 0 0 1-2 2.2C10.6 19.2 4.8 13.4 4.3 5A2 2 0 0 1 6.5 3z"/></svg>',
    "flight":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M10.5 20.5 12 17l1.5 3.5M3 14.5 21 8l-1 2.2L3 16.7z" stroke-linejoin="round"/><path d="M9 11 4 9.3 5.6 7.7 11 9z"/></svg>',
    "health":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M9 3h6v4h4v6h-4v4H9v-4H5V7h4z"/></svg>',
    "edit":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 20h4L18.5 9.5a2 2 0 0 0-3-3L5 17z"/><path d="M14 6l3 3"/></svg>',
    "download": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3v12M7 11l5 5 5-5M4 20h16"/></svg>',
    "show":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6z"/><circle cx="12" cy="12" r="2.6"/></svg>',
    "free":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-1.2-1.7-2-3-2-1.7 0-3 1.1-3 2.5 0 3 6 1.5 6 4.5 0 1.4-1.3 2.5-3 2.5-1.3 0-2.5-.8-3-2"/><path d="M12 6v12"/></svg>',
    "clock":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg>',
    "person":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7"/></svg>',
}


def icon(name, cls="ic"):
    return f'<span class="{cls}">{ICONS[name]}</span>'


# ── Header ───────────────────────────────────────────────────────────────────
def header():
    """Model B header — identical treatment to the itinerary: centred feather
    logo + Cormorant wordmark, gold hairline, then the document title below."""
    brand = (f'<img class="logo-img" src="data:image/png;base64,{LOGO_B64}" alt="Pivot">'
             if LOGO_B64 else "")
    return f"""
  <div class="header">
    <div class="brand-row">
      {brand}
      <span class="company-name">Pivot Travel Management</span>
    </div>
    <div class="header-divider"></div>
    <div class="doc-row">
      <div class="doc-title"><span class="t-bold">Air Suvidha</span> <span class="t-gold">2.0</span></div>
      <div class="doc-sub">Health self-declaration for international arrivals to India</div>
    </div>
  </div>"""


# ── Government attribution (text; logos auto-used if provided) ────────────────
def govt_strip():
    imgs = ""
    for b64, alt in [(MOHFW_B64, "MoHFW"), (MOCA_B64, "MoCA")]:
        if b64:
            imgs += f'<img class="govt-logo" src="data:image/png;base64,{b64}" alt="{alt}">'
    logos_html = f'<div class="govt-logos">{imgs}</div>' if imgs else ""
    return f"""
  <div class="govt-strip">
    {logos_html}
    <div class="govt-text">
      <span class="govt-1">Government of India</span>
      <span class="govt-2">Ministry of Civil Aviation &middot; Ministry of Health &amp; Family Welfare</span>
    </div>
    <div class="govt-date">Effective 25 Jun 2026</div>
  </div>"""


def section_hdr(title):
    return (f'<div class="sec-hdr"><span class="sec-dot"></span>'
            f'<span class="sec-title">{title}</span><span class="sec-rule"></span></div>')


# ── 1. What is it ────────────────────────────────────────────────────────────
def intro():
    facts = [("free", "Free to submit"),
             ("clock", "Up to 24 hrs before arrival"),
             ("person", "One form per traveller")]
    facts_html = "".join(
        f'<div class="fact">{icon(n, "fact-ic")}<span>{t}</span></div>' for n, t in facts)
    return f"""
  <div class="section">
    {section_hdr("What is Air Suvidha 2.0?")}
    <div class="intro">
      <div class="intro-main">
        <p class="intro-copy">A free online <strong>health self-declaration</strong> for passengers flying into
          India, screening for Ebola / Bundibugyo virus disease. Your details are shared in real time with
          Airport Health Officers, the Bureau of Immigration and public-health teams.</p>
        <div class="portal">
          <span class="portal-lbl">Official portal</span>
          <span class="portal-url">{PORTAL}</span>
        </div>
        <div class="facts">{facts_html}</div>
      </div>
      <div class="intro-qr">
        <img class="qr-img" src="data:image/png;base64,{QR_B64}" alt="QR to official portal">
        <div class="qr-cap">Scan to open</div>
      </div>
    </div>
  </div>"""


# ── 2. What to prepare ───────────────────────────────────────────────────────
def prepare():
    cards = [
        ("passport", "Identity &amp; documents",
         ["Full name as per passport", "Passport number &amp; nationality", "Visa / OCI details, if any"]),
        ("phone", "Contact details",
         ["Working mobile number", "Accessible email address", "Stay address in India, if asked"]),
        ("flight", "Flight &amp; travel",
         ["Airline, flight number &amp; seat", "Arrival airport, date &amp; time", "All countries visited in last 21 days"]),
        ("health", "Health declaration",
         ["Current symptoms, if any", "Ebola / Bundibugyo exposure", "Contact with suspected cases"]),
    ]

    def card(ic, title, items):
        lis = "".join(f'<li><span class="dot"></span><span>{x}</span></li>' for x in items)
        return (f'<div class="card"><div class="card-head">{icon(ic, "card-ic")}'
                f'<span class="card-title">{title}</span></div>'
                f'<ul class="card-list">{lis}</ul></div>')
    return f"""
  <div class="section">
    {section_hdr("What to prepare before you start")}
    <div class="prep-grid">{"".join(card(*c) for c in cards)}</div>
  </div>"""


# ── 3. How to complete it ────────────────────────────────────────────────────
def procedure():
    steps = [
        ("edit", "Complete the form", "Up to 24 hrs before arrival",
         "Open the <strong>official GOI portal only</strong> — avoid paid intermediaries. Enter your passport, "
         "contact, flight, 21-day travel and health details, then review and submit."),
        ("download", "Save the SDF", "Before boarding",
         "Immediately download or screenshot the Self-Declaration Form and email a copy to yourself. "
         "<strong>Do not close the page before saving.</strong>"),
        ("show", "Present on arrival", "At the health / immigration desk",
         "Show the saved SDF to airline staff before boarding, and at the <strong>Health or Immigration "
         "counter</strong> if asked. Follow any screening instructions."),
    ]

    def step(i, ic, title, tag, body):
        return (f'<div class="step"><div class="step-top">'
                f'<span class="step-num">{i}</span>'
                f'<span class="step-badge">{icon(ic, "step-ic")}</span></div>'
                f'<div class="step-title">{title}</div>'
                f'<div class="step-tag">{icon("clock", "tag-ic")}<span>{tag}</span></div>'
                f'<div class="step-body">{body}</div></div>')
    cells = "".join(step(i + 1, *s) for i, s in enumerate(steps))
    return f"""
  <div class="section">
    {section_hdr("When &amp; how to complete it")}
    <div class="step-grid">{cells}</div>
  </div>"""


# ── Footer ───────────────────────────────────────────────────────────────────
def footer_block():
    logo = (f'<img class="footer-logo" src="data:image/png;base64,{LOGO_B64}" alt="Pivot">'
            if LOGO_B64 else "")
    return f"""
  <div class="footer">
    {logo}
    <div class="footer-text">
      <div class="footer-line">PIVOT TRAVEL ADVISORY &nbsp;|&nbsp; AIR SUVIDHA 2.0 &nbsp;|&nbsp; WWW.PIVOT-TRAVELS.COM</div>
    </div>
    <div class="footer-contact">
      <div class="fc-lbl">Need help?</div>
      <div class="fc-val">cs@pivot-travels.com</div>
    </div>
  </div>"""


# ── HTML assembly ────────────────────────────────────────────────────────────
def build_html():
    body = f"""
  <div class="sheet">
    {header()}
    {govt_strip()}
    <div class="content">
      {intro()}
      {prepare()}
      {procedure()}
    </div>
    {footer_block()}
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Air Suvidha 2.0 — Passenger Guide</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500;1,600&family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
@page {{ size: A4; margin: 0; }}

:root {{
  --pg: 16mm;
  --gold: #c9a84c;
  --gold-lt: #e4c97a;
  --ink: #0b1724;
  --body: #46525f;
  --chip: #f7f7f7;
  --bd: #e8eaee;
}}

body {{ font-family: 'Inter', Helvetica, Arial, sans-serif; background: #fff; color: var(--ink);
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.sheet {{ width: 210mm; height: 297mm; position: relative; background: #fff; overflow: hidden; padding-bottom: 30mm; }}
.ic svg, .fact-ic svg, .card-ic svg, .step-ic svg, .tag-ic svg {{ display: block; }}

/* ── Header — Model B, identical to the itinerary: centred wordmark + hairline ── */
.header {{
  background: linear-gradient(150deg, #323234 0%, #1e1e20 50%, #0e0e0f 100%);
  border-bottom: 2px solid var(--gold);
  padding: 22px var(--pg) 18px;
}}
.brand-row {{ display: flex; align-items: center; justify-content: center; gap: 14px; }}
.logo-img {{ height: 46px; width: auto; object-fit: contain; display: block; }}
.company-name {{ font-family: 'Cormorant Garamond', Georgia, serif; font-size: 22px; font-weight: 600;
  letter-spacing: 0.16em; text-transform: uppercase; color: #f0ead8; }}
.header-divider {{ height: 1px; margin: 15px 0 14px;
  background: linear-gradient(90deg, transparent, rgba(201,168,76,0.55) 22%, rgba(201,168,76,0.55) 78%, transparent); }}
.doc-row {{ text-align: center; }}
.doc-title {{ font-family: 'Cormorant Garamond', Georgia, serif; font-size: 30px; font-style: italic;
  color: #f0ead8; line-height: 1; }}
.t-bold {{ font-style: normal; font-weight: 700; color: #fff; }}
.t-gold {{ font-style: normal; font-weight: 600; color: var(--gold); }}
.doc-sub {{ font-size: 10.5px; color: #b7bcc4; margin-top: 7px; letter-spacing: 0.2px; }}

/* ── Government attribution ── */
.govt-strip {{ display: flex; align-items: center; gap: 14px; padding: 9px var(--pg);
  background: var(--chip); border-bottom: 1px solid var(--bd); }}
.govt-logos {{ display: flex; align-items: center; gap: 10px; flex-shrink: 0; }}
.govt-logo {{ height: 26px; width: auto; object-fit: contain; }}
.govt-text {{ display: flex; flex-direction: column; gap: 1px; flex: 1; }}
.govt-1 {{ font-size: 10px; font-weight: 700; color: var(--ink); letter-spacing: 0.2px; }}
.govt-2 {{ font-size: 9px; color: #6b7a8d; }}
.govt-date {{ font-size: 8px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase;
  color: var(--gold); flex-shrink: 0; }}

/* ── Content + sections ── */
.content {{ padding: 22px var(--pg) 0; }}
.section {{ margin-top: 24px; }}
.section:first-child {{ margin-top: 4px; }}
.sec-hdr {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }}
.sec-dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--gold); flex-shrink: 0; }}
.sec-title {{ font-size: 9.5px; font-weight: 700; letter-spacing: 2.4px; text-transform: uppercase; color: var(--gold); }}
.sec-rule {{ flex: 1; height: 1px; background: var(--bd); }}

/* ── Intro ── */
.intro {{ display: flex; gap: 24px; align-items: center; border: 1px solid var(--bd); border-radius: 16px;
  padding: 20px 24px; position: relative; overflow: hidden; box-shadow: 0 3px 12px rgba(0,0,0,0.04); }}
.intro::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--gold), var(--gold-lt) 50%, var(--gold)); }}
.intro-main {{ flex: 1; min-width: 0; }}
.intro-qr {{ display: flex; flex-direction: column; align-items: center; gap: 6px; flex-shrink: 0; }}
.qr-img {{ width: 88px; height: 88px; border: 1px solid var(--bd); border-radius: 10px; padding: 5px; background: #fff; }}
.qr-cap {{ font-size: 7.5px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; color: var(--gold); }}
.intro-copy {{ font-size: 11px; line-height: 1.6; color: var(--body); }}
.intro-copy strong {{ color: var(--ink); font-weight: 700; }}
.portal {{ display: flex; align-items: baseline; gap: 10px; margin: 14px 0 0; }}
.portal-lbl {{ font-size: 7.5px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; color: var(--gold); }}
.portal-url {{ font-family: 'Cormorant Garamond', Georgia, serif; font-size: 19px; font-weight: 700;
  color: var(--ink); letter-spacing: 0.3px; }}
.facts {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }}
.fact {{ display: flex; align-items: center; gap: 6px; background: var(--chip); border: 1px solid var(--bd);
  border-radius: 18px; padding: 6px 14px; font-size: 9.5px; font-weight: 600; color: #3d4452; }}
.fact-ic {{ color: var(--gold); }}
.fact-ic svg {{ width: 13px; height: 13px; }}

/* ── Prepare (2x2) ── */
.prep-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.card {{ border: 1px solid var(--bd); border-radius: 16px; padding: 16px 18px; background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.035); }}
.card-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
.card-ic {{ color: var(--gold); flex-shrink: 0; }}
.card-ic svg {{ width: 18px; height: 18px; }}
.card-title {{ font-family: 'Cormorant Garamond', Georgia, serif; font-size: 16px; font-weight: 700; color: var(--ink); }}
.card-list {{ list-style: none; }}
.card-list li {{ display: grid; grid-template-columns: 10px 1fr; gap: 8px; align-items: start;
  font-size: 10px; color: var(--body); line-height: 1.4; margin-bottom: 7px; }}
.card-list li:last-child {{ margin-bottom: 0; }}
.card-list .dot {{ width: 5px; height: 5px; border-radius: 50%; background: var(--gold); margin-top: 5px; }}

/* ── Steps (3 across) ── */
.step-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }}
.step {{ border: 1px solid var(--bd); border-radius: 16px; padding: 18px; background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,0.035); position: relative; overflow: hidden; }}
.step::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--gold), var(--gold-lt)); }}
.step-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }}
.step-num {{ width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(150deg, #323234, #0e0e0f);
  color: var(--gold); font-family: 'Cormorant Garamond', Georgia, serif; font-size: 17px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; border: 1.5px solid var(--gold); }}
.step-badge {{ color: #c8ccd3; }}
.step-ic svg {{ width: 20px; height: 20px; }}
.step-title {{ font-family: 'Cormorant Garamond', Georgia, serif; font-size: 16px; font-weight: 700;
  color: var(--ink); line-height: 1.15; }}
.step-tag {{ display: inline-flex; align-items: center; gap: 5px; font-size: 8px; font-weight: 600;
  letter-spacing: 0.5px; text-transform: uppercase; color: var(--gold); margin: 5px 0 9px; }}
.tag-ic svg {{ width: 11px; height: 11px; }}
.step-body {{ font-size: 10px; line-height: 1.5; color: var(--body); }}
.step-body strong {{ color: var(--ink); font-weight: 700; }}

/* ── Footer ── */
.footer {{
  background: linear-gradient(150deg, #323234 0%, #1e1e20 55%, #0e0e0f 100%);
  border-top: 2px solid var(--gold); padding: 12px var(--pg);
  display: flex; align-items: center; gap: 16px;
  position: absolute; left: 0; right: 0; bottom: 0;
}}
.footer-logo {{ height: 26px; width: 26px; object-fit: contain; opacity: 0.85; flex-shrink: 0; }}
.footer-text {{ flex: 1; }}
.footer-line {{ font-size: 8px; letter-spacing: 1.8px; text-transform: uppercase; font-weight: 600;
  color: rgba(255,255,255,0.42); }}
.footer-contact {{ text-align: right; flex-shrink: 0; padding-left: 16px; border-left: 1px solid rgba(201,168,76,0.25); }}
.fc-lbl {{ font-size: 7px; text-transform: uppercase; letter-spacing: 1px; color: rgba(201,168,76,0.75); font-weight: 600; }}
.fc-val {{ font-size: 9px; color: #e8e2d2; font-weight: 600; white-space: nowrap; margin-top: 2px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def main():
    from weasyprint import HTML
    HTML(string=build_html(), base_url=str(HERE)).write_pdf(str(OUT_PDF))
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
