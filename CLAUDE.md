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

- **2026-07-22 — disruption alert repeating (airline re-sends) fixed:**
  Staff saw the ⚠️ ACTION REQUIRED digest repeat every poll. Cause (diagnosed
  against the live cs@ mailbox): airlines **re-send the same disruption for a
  booking repeatedly** — Turkish Airlines sent "Flight Delay Information" for
  reservation UCHMPF (and WB2WKB) twice, ~30 min apart, each a **new
  message_id** — and the watch de-duped only by message_id, so every re-send read
  as brand-new. Fix: **booking-level dedup** — new pure `extractors.disruption_dedup_key`
  keys on `<sender-domain>:<PNR>:<category>:<day>` (PNR pulled from a strong label
  like "Reservation code", uppercase-only capture + stopword guard so "PNR CHANGED"
  can't become a bogus code). `scan_disruptions` skips a candidate whose key was
  already alerted (persisted in `disruption_ids.json` as `{"message_id","key"}`)
  and collapses re-sends within a single scan too. No reliable PNR → key "" →
  falls back to per-message alerting, so a warning is **never silently dropped**
  (§7). Re-alerts still fire for a new booking, a new day, or a worse disruption
  type (cancellation after delay). 78 tests pass.
- **2026-07-21 — self-healing "medic" loop (flag → diagnosed PR, human merges):**
  A scheduled Claude session turns a manual-review flag into a reviewed pull
  request so the diagnose→fix→test toil runs on its own while a human keeps the
  final gate before anything touches a client document. Flow (full runbook in
  **`MEDIC.md`**): the medic computes the *unresolved* flag set (in
  `flagged_ids.json`, not in `processed_ids.json`, not in `medic_ids.json`) →
  dispatches **`medic-diagnose.yml`** per flag (redacted, any-portal diagnosis via
  `tools/medic_diagnose.py`, so the real PDF/body never leaves CI) → reads the
  `VERDICT:` → classifies **resolved** (record & skip) / **needs-human** (open a
  short issue, no code change) / **parser-bug** (patch the matching `extract_*` +
  add a zero-PII fixture, verify tests, open a PR). Deliberately **never
  auto-merges** — an AI-written regex could ship a factually wrong document (§7),
  so `main` only changes on a human merge. `medic_ids.json` (message_id only,
  public-safe) dedupes so each flag is worked once; poll.yml persists it beside
  the other logs. `_IATA_DESIG` and the §9 diagnosis method are what the medic
  reuses to fix parser misses.
- **2026-07-21 — Akbar Flyadeal (F3) missing-flight-number flag fixed:**
  A real Akbar "Booking Success" (Flyadeal DMM→JED) kept failing `qc_check`
  ("A segment is missing flight number / airport / time") and re-flagging every
  poll. Diagnosed per §9 against the *actual* PDF's pdfplumber text (redacted
  debug run in CI, not the HTML body): everything parsed except `flight_no`,
  which came back `""`. Root cause — every flight-code pattern in
  `extract_akbar._flight_no_for` used `[0-9]?[A-Z]{1,2}`, which matches LL (SV)
  and DL (9P) designators but **not the LD (letter-then-digit) shape** like
  Flyadeal **`F3`** / Air Arabia `G9` / easyJet `U2` when the code appears
  singly (`F3 310`, not the doubled `G9 G9148` the earlier fix handled). Fix:
  new module constant **`_IATA_DESIG`** = `(?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z])`
  used in all four `_flight_no_for` patterns. Also fixed the **operating
  carrier** for this layout: pdfplumber splits the cell as `Operated …\nby:Flyadeal`,
  so the contiguous `Operated by:` match missed it and the airline silently fell
  back to the "IndiGo" default (a Flyadeal booking labelled IndiGo — a factual
  error on a client doc); the pattern now tolerates up to a line of junk between
  `Operated` and `by:`. New zero-PII regression fixture `akbar_flyadeal_f3.txt`
  (74 tests pass). Cleared the `flagged_ids.json` seed so the now-fixed booking
  processes normally next poll and any genuine future failure still surfaces.
- **2026-07-19 — Pivot OS sync (Producer) + scenario status pill:**
  - **Pivot OS sync:** each produced itinerary is pushed to Pivot OS's "Entries
    to Be Done" via a best-effort webhook (`main.notify_pivot_os` → `POST
    /api/itinerary-sync`, Bearer auth). Payload built by
    `extractors.pivot_os_payload` (contract in `PIVOT_OS_INTEGRATION.md`, v1.0):
    ISO dates, `idempotency_key` = `<pnr>:<status>:<source_ref>`, composite
    `match_key` = `<pnr>:<portal>`, `financials: null`. Fires
    `itinerary.created` on new bookings and `itinerary.revised` on revised
    drafts. INERT until `PIVOT_OS_SYNC_URL` + `PIVOT_OS_SYNC_SECRET` GitHub
    Secrets are set; PII only over TLS, never in the public Action log. Summary
    gains `pivot_os_sync` tallies.
  - **Scenario status pill:** revised itineraries show a coloured pill matching
    the disruption (`rebooked`=red / `rescheduled`=orange / `delayed`=amber /
    `revised`=gold) via `data["doc_status"]`; default `confirmed` (green) is
    byte-identical to the locked original.
- **2026-07-19 — auto-draft REVISED itinerary on aJet schedule change:**
  - When the disruption watch flags an **aJet** change/cancel/delay, the runner
    now rebuilds the affected booking and attaches a **revised branded PDF** to
    the alert for staff to verify + forward. Flow: `extractors.extract_ajet_change`
    parses the blue "New Flight Information" panel (reuses the ticket segment
    shape) → `main._find_original_ajet_booking` finds the original ticket email in
    cs@ by PNR and re-extracts the full booking → `extractors.apply_flight_change`
    patches ONLY the affected leg (match by old flight-no, else route) →
    `main.build_revised_itinerary` renders `REVISED-<PNR>.pdf` (QC-gated; India
    guide re-appended). **Safe-by-default:** can't parse / can't find original /
    no leg matches / QC fails → returns None and the alert ships with no draft.
    The draft is a convenience for the human who already reviews every alert —
    never auto-sent to a client. Summary gains `revised_drafts`. aJet only for
    now (dominant disruption source); other airlines follow the same pattern.
- **2026-07-19 — disruption watch + brand-matched alert + wordmark case:**
  - **Disruption watch:** cloud runner now also raises ONE private, colour-coded
    ⚠️ ACTION-REQUIRED digest to cs@ for NEW cancellation / schedule-change /
    delay emails (whole-mailbox subject-keyword scan; de-duped via
    `disruption_ids.json`). Keyword rule + `disruption_category()` live in
    `extractors.py`, cross-checked against real airline/B2B templates. Alert is
    skinned to the itinerary brand (Model B charcoal/gold, feather logo).
  - **Wordmark → Title Case:** the "Pivot Travel Management" wordmark is now
    Title Case (was CSS-uppercased) with tighter 0.04em tracking, applied
    everywhere the brand header lives — itinerary (`.company-name`/
    `.logo-text-main`), Air Suvidha guide (`.company-name`), and the alert email.
    Other uppercase elements (CONFIRMED, PNR REFERENCE, footer tags) unchanged.
  - **Air Suvidha generator** `OUT_PDF` now points straight at the runtime asset
    `air_suvidha_guide.pdf` (was a "pretty" name that needed manual renaming);
    the committed guide was regenerated with the Title Case wordmark.
- **2026-07-18 — Air Suvidha guide auto-attach (India arrivals):**
  - New static guide `air_suvidha/air_suvidha_guide.pdf` (generated by
    `air_suvidha/generate_air_suvidha_guide.py` — WeasyPrint; Model B header
    matching the itinerary; QR to the official portal). Self-contained (fonts +
    logo embedded), committed as a runtime asset — the cloud runner never runs
    WeasyPrint.
  - `extractors.india_arrival(data)` returns True when a booking has an
    INTERNATIONAL flight arriving in India (arr in `INDIA_IATA`, dep outside).
    Purely domestic Indian hops do NOT trigger it. Covered by offline tests.
  - **2026-07-18 (later) — merged into a SINGLE PDF, not a second attachment:**
    `main._append_air_suvidha()` uses `pypdf` to append the guide's page(s)
    directly onto the itinerary PDF right after `build_pdf()` (before Drive
    upload), so Drive and the email both get one file — itinerary + T&C +
    guide as trailing pages. `email_pdf` sends that single file; the body note
    says the guide is "included as extra page(s)". Fails safe (no-op, itinerary
    ships alone) if the guide asset is missing. Verified end-to-end with a real
    Playwright-rendered PDF (3 pages: itinerary, T&C, guide).
- **2026-07-18 — reliability pass (tests + notifications + idempotency + retries):**
  - **Offline test suite (`tests/`)** — synthetic, zero-PII fixtures for all four
    portals + 2 negative cases, run through the real extractors + `qc_check()`:
    QC assertions plus a golden-snapshot comparison (regenerate with
    `UPDATE_GOLDEN=1`). New `.github/workflows/test.yml` runs pytest on every
    push/PR (pure-stdlib; no Google/Playwright). Locks in every parser fix.
  - **Manual-review notifications (`email_flags`)** — a booking that fails
    `qc_check` (or whose email send fails) now triggers ONE private digest email
    to cs@ (portal, reason, subject, Source Ref) instead of vanishing into a
    public count. Inbox-only, so it can name the message id.
  - **Idempotency** — a booking is marked processed + the log checkpointed to
    disk right after the PDF lands on Drive, BEFORE emailing; the send is
    best-effort. A failed send (or a mid-run crash) can no longer cause a
    duplicate PDF/email next run — it surfaces as a manual-review flag instead.
  - **Retries** — every Google API call passes `num_retries=API_RETRIES` (4) so
    transient 5xx / rate-limit responses back off and retry instead of flagging.
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
the PDF's pdfplumber text). Airline IATA codes come in three shapes: LL (SV, TK, XY), LD (F3, G9, U2),
DL (9P, 6E) — any flight-no regex must handle all three. Use the `_IATA_DESIG` constant
(`(?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z])`); the old `[0-9]?[A-Z]{1,2}` silently drops the LD
(letter-then-digit) shape (Flyadeal F3 flag, 2026-07-21).

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
