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
- CR No. **7043148696** · VAT No. **311788697700003** · Suite 20, 2nd Floor, Mobco Building, 2762 Ibn Al Anbari Street,
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
| **Turkish Airlines** | onlineticket@mail.turkishairlines.com | `Turkish Airlines - Ticket Details` | **PDF attachment** (`TicketDetails.pdf`, pdfplumber) — body is a scrambled summary only |

Process only when sender AND subject both match. Ignore everything else. Turkish Airlines sends
several OTHER subjects from the same address (Gate Change Information, Flight Delay Information,
Seat Selection Details) — none of those are booking confirmations; only the exact subject above is.

## 5. The design (LOCKED — Model B header, dark luxury)

Palette: charcoal→black gradient `#323234 / #1e1e20 / #0e0e0f` for header/footer/segment
banners; **white body** with light `#f7f7f7` chips; gold `#c9a84c`; emerald `#4ea87a/#7fd0a6`
for the CONFIRMED status only. Fonts: **Cormorant Garamond** (display/figures) + **Inter** (body).

- **Header (Model B):** centred feather logo + "PIVOT TRAVEL MANAGEMENT" wordmark, gold hairline,
  then CONFIRMED pill (left) above "OFFICIAL TRAVEL DOCUMENT", and the PNR number (right) above
  its "PNR REFERENCE" label. There is intentionally **no "Booking Confirmation" title text**.
  Directly under the wordmark sits the **brand strapline** `BRAND_STRAPLINE` —
  `CORPORATE TRAVEL | CHAUFFEURS | CURATED ITINERARIES | PREMIUM PILGRIMAGE`, 6.5px,
  2.6px tracking, `rgba(255,255,255,0.30)` (deliberately subtle) — above the gold hairline.
- Rounded ref-strip capsule · rounded passenger cards with a gold top strip + grey value chips ·
  dark rounded segment banners (OUTBOUND / INBOUND) · rounded flight cards with a white plane-badge
  connector · gold layover badge · dark footer with `PIVOT AUTOMATED ITINERARY | <PNR> | WWW.PIVOT-TRAVELS.COM`
  and a **second registration line** `CR 7043148696 · VAT 311788697700003`
  (`COMPANY_CR` / `COMPANY_VAT`). The VAT segment renders only when `COMPANY_VAT` is non-empty,
  so an unverified tax identifier can never reach a client document (§7).
- **Baggage + seat live on the FLIGHT card, not the passenger card** (2026-07-30, approved):
  one row per passenger inside each flight card (`PASSENGER | CABIN | CHECKED | SEAT`). They are
  per-SEGMENT facts — extra baggage is often bought on one leg only, and seats differ per leg.
  A column is **omitted entirely** when no passenger on that leg has a value. The flight card's
  pill row holds `OPERATED BY` + `CABIN CLASS` (+ `DURATION` when known) — the duplicate
  `FLIGHT NO.` pill was removed because the flight number already sits on the centre connector;
  `OPERATED BY` was removed with it on 2026-07-30 and **restored by request the same day** (the
  operating carrier can differ from the marketing one, so it earns its own pill).
  Passenger card is now just `PASSENGER NAME | TICKET NO.`, so long names no longer wrap.
- **Terms & Conditions:** static 8-clause page, always issued by "Pivot Travel Management".
- **Pagination (two-pass in `build_pdf`):** *Layout A* (itinerary fits 1 page → page 1 itinerary +
  footer, page 2 T&C + footer). *Layout B* (spills → cards flow, T&C fills the tail, one footer
  pinned to the bottom of the last page). Rules held: footer pinned to page bottom; segment banner
  never orphaned from its first card (`page-break-after: avoid`); cards never split
  (`page-break-inside: avoid`); pages 2+ get a 12mm top margin.

- **NO `box-shadow` anywhere** (removed 2026-07-30, approved). PDF has no shadow primitive, so
  Chromium rasterises each one into an image + soft mask; Apple's PDFKit (iOS Quick Look/Files,
  macOS Preview) then paints the shadow's **bounding box as a flat grey rectangle** — a visible
  "backdrop" behind every card. Cards carry 1px borders + radii, so nothing was lost. Do NOT
  reintroduce shadows, and note an `@media print` override CANNOT fix it (§10 renders with
  `emulate_media("screen")`, so print rules never apply). Exception kept on purpose: the tiny
  `0 0 5px` glow on the CONFIRMED pill dot.

**⚠️ Design is locked.** Before changing any layout/CSS, ask the user twice for explicit
confirmation, then apply the SAME change everywhere the generator lives.

## 6. Data model (one dict per booking → `build_pdf`)

```
pnr, booking_ref, crs_ref (shown only if != pnr), booked_on, journey_type (ONE-WAY | ROUND TRIP),
passengers[]: { name, ticket_no }                      # identity only (card shows just these)
segments[]:  { type: Outbound|Inbound, flights[]: { dep_iata, arr_iata, dep_city, arr_city,
               dep_airport, arr_airport, terminal (dep), arr_terminal, dep_date, dep_time,
               arr_date, arr_time, flight_no, airline, cabin, duration,
               pax[]: { name, cabin_bag, checked_bag, seat }   # PER-LEG (2026-07-30)
             }, layovers[]: {airport,duration} }
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

- **2026-08-02 — airport names now render on every portal + multi-word airline
  name fixed (both found on real Akbar booking A052SF, Air Sial JED→ISB):**
  1. **Airline truncated to its first word.** The card said the flight was
     "OPERATED BY: Air" — the source says **Air Sial**. `extract_akbar` captured
     `([A-Za-z]+)` after `Operated by:`, so EVERY multi-word carrier was cut
     (Air Sial, Air Arabia, Fly Jinnah, Saudi Arabian Airlines) — a factual
     error on a client document. Naively widening it would have broken Flyadeal,
     whose real pdfplumber line reads `by:Flyadeal Saudi Arabia,` (the From/To
     column's country bleeds in). New `_akbar_airline()` takes the line, cuts at
     the first comma, then strips a trailing **country** — so `Air Sial` survives
     whole, `Flyadeal Saudi Arabia` becomes `Flyadeal`, and `Saudi Arabian
     Airlines` (a carrier whose own name starts with a country word) is left
     intact. The `or "IndiGo"` default was **removed**: it had been stamping a
     real airline's name onto other carriers' tickets. A failed parse now
     returns `""` → renders N/A (incomplete, not wrong) per §7.
  2. **No airport name on 4 of 5 portals.** Only Alhind ever parsed them;
     Akbar/aJet/Pegasus/Turkish hardcoded `dep_airport`/`arr_airport` to `""`,
     so the card showed a bare city under the IATA code. Akbar's PDF *does*
     contain the name, but pdfplumber scrambles the From/To cells so badly that
     a name can't be reliably attributed to the departure vs arrival side (§9's
     linearisation problem — "King Fahd" under the wrong airport is worse than
     nothing). Names now come from a new static **`extractors.AIRPORT_NAMES`**
     IATA→name table, applied as a BACKFILL in `build_html` **after** the
     document-derived pass, so anything the source stated always wins and an
     unlisted IATA still renders nothing.
     **Why this is allowed when the terminal table was rejected (§8, 2026-07-27):**
     an airport's NAME is a stable, single-valued fact (JED is King Abdulaziz on
     every ticket, every airline, every season); a TERMINAL varies by carrier,
     route and season at hubs like IST/DXB/JED. A static terminal map stays
     rejected — a test asserts the name backfill never touches terminal fields.
  **Terminals are still parsed by Alhind ONLY** — that is unchanged and correct:
  the other four portals genuinely don't carry the data (re-verified 2026-07-27),
  and A052SF's own source shows empty From/To terminal columns. 114 tests pass;
  verified by re-rendering A052SF (airport names on both ends, `Air Sial` intact).
- **2026-07-30 (later) — brand strapline, footer CR line, OPERATED BY pill restored:**
  Three approved header/footer changes shipped together. (1) `OPERATED BY` is back in the
  flight-card pill row, before `CABIN CLASS`. (2) New `BRAND_STRAPLINE` under the wordmark —
  `CORPORATE TRAVEL | CHAUFFEURS | CURATED ITINERARIES | PREMIUM PILGRIMAGE`, deliberately
  low-contrast so it reads as a hairline label, not a second headline (the header must stay
  quiet: PNR and CONFIRMED are the only things that should draw the eye). The trailing period
  was dropped — a tracked all-caps micro-label reads as a label, and a full stop makes it read
  as a sentence. (3) Footer gained a second line, `CR 7043148696`, from the new `COMPANY_CR`
  constant; the footer became a 2-row column flex. `COMPANY_VAT` shipped EMPTY that day (§7
  forbids inventing a tax identifier for a client-facing document) and was **filled the same
  day** from the registration certificate the owner supplied: `VAT 311788697700003` (15 digits,
  Saudi ZATCA format). It now renders beside the CR on every document; the
  render-only-when-set guard stays, so a future blank can never print a bare `VAT` label.
  100 tests pass; verified on the real R2F3ES round trip and on a re-render after the VAT
  landed (footer reads `CR 7043148696 · VAT 311788697700003`).
- **2026-07-30 — baggage + seat moved to per-leg rows on the FLIGHT card (approved
  design change) + all 5 extractors upgraded:**
  Baggage/seat were booking-level on the passenger card, which could not express
  the real world: a passenger often buys extra baggage on **one segment only**, and
  seats differ per leg. Now each flight card carries one row per passenger
  (`PASSENGER | CABIN | CHECKED | SEAT`); the passenger card slims to
  `NAME | TICKET NO.` (long names stopped wrapping); and the duplicate
  `FLIGHT NO.`/`OPERATED BY` pills were dropped since both already appear on the
  centre connector. Columns are **omitted** (not N/A-padded) when a leg has no
  such value.
  **Cross-checked every portal against REAL emails first** — the finding was that
  Alhind, aJet and Pegasus already carry per-segment data and the extractors were
  *deliberately deduping it away* (aJet by ticket-no, Pegasus by name, Alhind by
  only reading the first row). That repetition WAS the per-leg data. Granularity
  now: **Alhind** per-segment (one table row per segment) · **aJet** per-leg (pax
  block repeats per segment; assigned by match POSITION relative to each segment
  block) · **Pegasus** per-direction (whole block repeats per direction) ·
  **Turkish Airlines** per-direction baggage, no seats in the PDF ·
  **Akbar** booking-level only → `build_html` backfills from `passengers[]` so it
  still shows the allowance that genuinely applies to every leg.
  **Latent Alhind bug fixed in passing:** continuation rows (2nd+ segment) have
  Name/Image/FFNo rowspan'd away, so every column shifts one earlier — cabin is
  `si+3`, not `si+4`. The old code always used `si+4`; harmless only because
  baggage was assigned once on the name row, but reading per-segment baggage made
  it matter. Verified on a real 4-leg booking. Golden snapshots re-generated and
  machine-checked: **zero** existing values changed, only the new `pax` key added.
  100 tests pass.

- **2026-07-30 — "grey backdrop behind every element" in Apple PDF viewers fixed
  (box-shadow removed, + a dead `@media print` rule retired):**
  Staff saw a hard-edged grey slab behind each card (and a **cream square** around
  the ✈ plane badge) when opening itineraries on iPhone / macOS Preview, though
  Chrome looked fine. Cause: PDF has no `box-shadow` primitive, so Chromium
  rasterises every CSS shadow into an image + soft mask inside a transparency
  group; **Apple's PDFKit drops the alpha falloff and fills the shadow's bounding
  box** with flat tint. The cream square was the gold `.plane-icon` shadow
  (`rgba(201,168,76,0.2)`) flattened. Verified on a real render, not theory —
  removing shadows took the file from **13→7 `/SMask`, 11→5 `/Transparency`,
  60→36 `/Image`, −61 KB**. Removed from `.page`, `.pax-card`, `.seg-header`,
  `.flight-card`, `.plane-icon`; all four cards already had `1px` borders +
  radii so the look is unchanged (visually diffed before/after). The pill-dot
  glow was deliberately kept.
  **Latent bug found in passing:** `@media print { .page … box-shadow: none }`
  had been written to strip the page shadow for output, but `build_pdf()` calls
  `page.emulate_media(media="screen")` (§10) — so that block **never applied** and
  a 40px page shadow had been shipping in every PDF since. Suppression now lives
  in the normal cascade; the dead line is gone and both spots carry comments so
  it can't regress. Also note: a stray single `{` in a CSS comment inside the
  f-string broke `build_html` with `NameError: name 'box' is not defined` — the
  offline suite caught it immediately. 92 tests pass.

- **2026-07-27 — terminal audit + departure-terminal backfill fix:**
  Cross-checked terminal handling across all 5 portals against REAL sources.
  **Finding: mostly not a parsing bug** — 4 of 5 portals genuinely carry no
  terminal data in the source, so `N/A` was correct: aJet (verified on a live
  email — only boilerplate "…at some terminals"), Pegasus, Turkish Airlines
  (verified on both real `TicketDetails.pdf` files — zero terminal fields), and
  Akbar (From/To terminal columns render empty; stray "Terminal X" tokens are
  unattributable — deliberately left blank since 2026-07-17). Alhind is the only
  portal whose source sometimes carries terminals, and it already extracted both
  correctly. Two REAL defects found and fixed:
  1. **`generate_itinerary_v3.build_html` never backfilled the DEPARTURE
     terminal.** Airport names propagated both ways and `arr_terminal` was
     filled, but `terminal` was not — so on a round trip where the airline
     stated a hub's terminal only once (e.g. only on the outbound ARRIVAL into
     IST), the inbound leg departing that same IST silently rendered nothing.
     One line added, mirroring the existing arrival-side backfill.
  2. **`arr_terminal` was missing entirely** from Akbar / aJet / Pegasus (and
     the generic fallback) flight dicts, so those portals structurally could
     never carry an arrival terminal. All portals now emit both keys.
  The backfill only ever copies a terminal the document itself stated for that
  exact IATA — it never invents one (§7) and never copies across airports; both
  guards are asserted in `tests/test_terminal_backfill.py`. 92 tests pass.
  **Deliberately NOT done:** a static IATA→terminal lookup table. Terminals vary
  by airline, route and season at hubs like IST/DXB, so a static map would print
  confidently WRONG terminals on client documents — worse than N/A.

- **2026-07-27 — 5th portal added: Turkish Airlines** (`extract_turkish_airlines`):
  Built from 2 real bookings (TDYWK8, WENFE5), both Gulf↔small-Turkish-city
  connections via Istanbul. **Source is the `TicketDetails.pdf` email
  attachment, not the body** — the body only shows a scrambled aggregate
  summary with no per-leg times; registered with `"source": "drive_pdf"`,
  reusing `main.akbar_attachment_text()` (genuinely generic — grabs the
  first PDF attachment regardless of filename, not Akbar-specific).
  Confirmed pdfplumber quirks on real files (see extractors.py comments for
  detail): (1) the header summary block is column-scrambled — only the
  detailed "Flight details" listing below it is reliable; (2) stops come in
  **departure/arrival PAIRS per leg**, not a continuous chain — zipping
  consecutive stops would fabricate a phantom 3rd leg out of the
  IST-arrival→IST-departure layover gap; (3) the 3-column Fare-Rules table
  interleaves by row, so "Check-in Baggage : ... 23" and its "kg" unit can
  land on different lines with an unrelated cell between them; (4) "Aircraft
  type" can render as a broken template placeholder
  (`planetypelookup.D21 - planemodellookup.D21`) — a real bug in Turkish
  Airlines' own PDF, confirmed on two different bookings (not extracted;
  aircraft type isn't part of this project's data model anyway). A **flat**
  list of legs (outbound then inbound) is handed to the existing
  `_finalize()` → `group_segments()` / `_layovers_for()` / `_mark_next_day()`
  machinery, which correctly finds the Outbound/Inbound split on its own —
  the week(s)-long gap between the last outbound leg and first inbound leg
  is always the largest connection gap. Verified end-to-end (extract →
  `qc_check` → `build_pdf`) against both real bookings before committing;
  synthetic zero-PII fixtures added to `tests/`.
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
