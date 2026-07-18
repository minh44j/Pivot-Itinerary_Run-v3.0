# Pivot Travel Management — Itinerary Automation (CLAUDE.md)

> Read this first. It is the at-a-glance memory of what this project is, how it works,
> and what has been polished so far. Repo: `minh44j/Pivot-Itinerary_Run-v3.0`
> (all runtime files live at the **repo root** on `main`).

---

## 1. What this project does

Turns airline ticket-confirmation emails (arriving at **cs@pivot-travels.com**) into one
**print-ready A4 PDF booking confirmation** per booking, styled to the Pivot luxury brand.

Two ways it runs:
- **Cloud (hands-off):** `main.py` runs on GitHub Actions (triggered by cron-job.org every few
  minutes), scans the inbox, extracts, renders, and emails the finished PDF from info@ → cs@.
- **Assistant (`\run` / `\process`):** a person triggers it. `\run` = scan inbox + process new
  qualifying emails. `\process` = process an attached/uploaded PDF only. Nothing runs without an
  explicit trigger.

## 2. Company facts (canonical — renamed 2026-07-15)

- **Pivot Travel Management** *(formerly "Pivot Travel & Tourism" — do NOT use the old name)*
- CR No. **7043148696** · Suite 20, 2nd Floor, Mobco Building, 2762 Ibn Al Anbari Street,
  Al Amal District, Riyadh, Kingdom of Saudi Arabia
- sales@pivot-travels.com · www.pivot-travels.com · monitored inbox: cs@pivot-travels.com
- (Sister company Pivot Shipping: CR 7034458500, sales@pivotscl.com — not part of this repo.)

## 3. Core files

| File | Role |
|---|---|
| `generate_itinerary_v3.py` | **Design engine.** Builds the HTML and renders the A4 PDF via Playwright/Chromium. Contains the whole locked visual design + pagination. |
| `extractors.py` | **Portal parsers.** One `extract_*()` per portal + `qc_check()` + `PORTALS` registry. |
| `main.py` | Cloud runner (Gmail scan → extract → render → email). Public repo, so it deliberately strips PNRs/IDs from its Action-log summary. |
| `logo.png` | Brand logo (feather mark). Rendered as-is — do NOT apply a brightness/invert filter. |
| `PROJECT_INSTRUCTIONS.md`, `AGENTS.md` | Longer-form spec (kept in sync with this file). |

## 4. Portals (source of truth per portal)

| Portal | Sender | Subject contains | Extract from |
|---|---|---|---|
| **Alhind** | alhind@alhindsanchar.com | `Air Ticket` | Email **body** (HTML table cells) |
| **Akbar Travels** | sanoreply@akbartravels.com | `Booking Success` **or** `Ticket Copy` | **PDF attachment** (pdfplumber) — body unreliable |
| **aJet** | onlineticket@mail.ajet.com | `Ticket information` | Email **body** |
| **Pegasus** | pegasus@flypgs.com | `Your booking is confirmed! View your ticket now` | Email **body** |

Process only when sender AND subject both match. Ignore everything else.

## 5. The design (LOCKED — Model B header, dark luxury)

Palette: charcoal→black gradient `#323234 / #1e1e20 / #0e0e0f` for header/footer/segment
banners; **white body** with light `#f7f7f7` chips; gold `#c9a84c`; emerald `#4ea87a/#7fd0a6`
for the CONFIRMED status only. Fonts: **Cormorant Garamond** (display/figures) + **Inter** (body).

- **Header (Model B):** centred feather logo + "PIVOT TRAVEL MANAGEMENT" wordmark, gold hairline,
  then CONFIRMED pill (left) above "OFFICIAL TRAVEL DOCUMENT", and the PNR number (right) above
  its "PNR REFERENCE" label. There is intentionally **no "Booking Confirmation" title text**.
- Rounded ref-strip capsule · rounded passenger cards with a gold top strip + grey value chips ·
  dark rounded segment banners (OUTBOUND / INBOUND) · rounded flight cards with a white plane-badge
  connector · gold layover badge · dark footer with `PIVOT AUTOMATED ITINERARY | <PNR> | WWW.PIVOT-TRAVELS.COM`.
- **Terms & Conditions:** static 8-clause page, always issued by "Pivot Travel Management".
- **Pagination (two-pass in `build_pdf`):** *Layout A* (itinerary fits 1 page → page 1 itinerary +
  footer, page 2 T&C + footer). *Layout B* (spills → cards flow, T&C fills the tail, one footer
  pinned to the bottom of the last page). Rules held: footer pinned to page bottom; segment banner
  never orphaned from its first card (`page-break-after: avoid`); cards never split
  (`page-break-inside: avoid`); pages 2+ get a 12mm top margin.

**⚠️ Design is locked.** Before changing any layout/CSS, ask the user twice for explicit
confirmation, then apply the SAME change everywhere the generator lives.

## 6. Data model (one dict per booking → `build_pdf`)

```
pnr, booking_ref, crs_ref (shown only if != pnr), booked_on, journey_type (ONE-WAY | ROUND TRIP),
passengers[]: { name, ticket_no, cabin_bag, checked_bag, seat }
segments[]:  { type: Outbound|Inbound, flights[]: { dep_iata, arr_iata, dep_city, arr_city,
               dep_airport, arr_airport, terminal (dep), arr_terminal, dep_date, dep_time,
               arr_date, arr_time, flight_no, airline, cabin, duration }, layovers[]: {airport,duration} }
```
Generator normalises: journey type → ONE-WAY/ROUND TRIP only; names → Title Case; baggage →
weight-only ("7kg", "7kg + 3kg", "1Pcs"); missing values → **N/A**; next-day arrival → `HH:MM (+1)`.

## 7. Accuracy rules (non-negotiable)

Never fabricate — missing value = `Not specified`/N/A. Verbatim for PNR, ticket no., flight no.,
names (re-read after writing). Times stay local (no timezone conversion). One booking = one PDF.
If a document is ambiguous / not a confirmation / missing PNR or passenger name → **flag for manual
review, do not produce a PDF**. `qc_check()` gates this (missing PNR / passengers / segments /
flight-no / airport / time; non-Confirmed status).

## 8. What has been polished (recent history)

- **2026-07-18 — privacy + internal email upgrade (`main.py`):**
  - `processed_ids.json` (committed to the **public** repo) now stores **only** the opaque Gmail
    `message_id` per booking — no PNR / portal / Drive link. The 126 existing entries were scrubbed.
    De-dup is unchanged (it only ever read `message_id`).
  - The confirmation email to cs@ now carries the **full booking at a glance**: journey type,
    booking/CRS ref (only when ≠ PNR), per-passenger ticket + seat, full per-leg itinerary, and a
    **Source Ref** line (the `message_id`) so a public log entry can be traced back privately by
    searching the inbox. Missing fields render `N/A`.
  - Email footer corrected `PIVOT AI AUTOMATED ITINERARY` → `PIVOT AUTOMATED ITINERARY` (§11).
- **2026-07-16 — full redesign + rename** to Pivot Travel Management; navy → dark charcoal/gold;
  rounded CRED-style cards, plane connector, emerald pill; T&C + pagination preserved.
- **2026-07-17 — Model B header** adopted (centred wordmark, no "Booking Confirmation" text, pill
  left, PNR right with label below).
- **extractors.py fixes:**
  - **Air Arabia G9** connecting bookings (PNR <ref>) — doubled flight code "G9 G9148" now parsed
    (widened the IATA-designator group to cover letter+digit codes). Was flagging "missing flight number".
  - **aJet PREMIUM** fare → cabin "Premium Economy" (previously only ECOJET→Economy, BIZJET→Business).
  - **Terminals** — Alhind now extracts BOTH departure and arrival terminal (they live inside the
    Origin/Destination table cells). Akbar terminals left blank on purpose (the PDF's From/To terminal
    columns are empty and stray "Terminal X" tokens can't be reliably attributed — better blank than
    wrong). aJet/Pegasus tickets carry no terminal data.
- Verified against ~30 real emails across all four portals; Alhind/Pegasus/aJet and the Akbar
  Saudia/Air-India/Air-Arabia PDFs all extract clean.

## 9. Known Akbar fragility (check before re-diagnosing a flag)

`extract_akbar()` reads a multi-column PDF table that **pdfplumber linearizes non-deterministically**
— flight code, airport name, and terminal can land fused on one line. It has been patched several
times for Saudia (SV) business-class layouts and once for Air Arabia (G9). If an Akbar booking flags
"missing flight number / airport / time", pull the **real PDF attachment** and run the live
`extract_akbar()` against it directly — do NOT diagnose from the email HTML body (not equivalent to
the PDF's pdfplumber text). Airline IATA codes come in three shapes: LL (SV, TK, XY), LD (G9, U2),
DL (9P, 6E) — any flight-no regex must handle all three.

## 10. Rendering

Self-contained single HTML → PDF via **Playwright/Chromium**. A4, `print_background=True`,
`emulate_media("screen")`, zero PDF margins (CSS `@page` controls margins), no external network at
render time (logo embedded base64). On a normal machine: `pip install playwright && playwright
install chromium` and it works. (The old Cowork sandbox needed a libXdamage stub — not needed on a
real Mac / normal CI.)

## 11. Repo / deployment notes

- Keep `generate_itinerary_v3.py` and `extractors.py` identical between local and the repo — the
  cloud runner uses the repo versions. After changing either, commit both to `main` (repo root).
- `processed_log.json` de-dupes by Gmail `message_id`; manual `\process` uses `"message_id":"manual-upload"`.
- Do not add any AI/vendor references anywhere except the footer tag `PIVOT AUTOMATED ITINERARY`.
