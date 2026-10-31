# Pivot Travel Management — Itinerary Automation (CLAUDE.md)

> Read this first. It is the at-a-glance memory of what this project is, how it works,
> and what has been polished so far. Repo: `minh44j/Pivot-Itinerary_Run-v3.0`
> (all runtime files live at the **repo root** on `main`).

---

## 1. What this project does

Turns airline ticket-confirmation emails (arriving at **cs@pivottmc.com**) into one
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
- **Primary domain is `pivottmc.com`** (Workspace primary changed 2026-10-11; every user
  renamed). **`pivot-travels.com` remains an ALIAS** — mail to the old addresses still
  delivers, so documents already in clients' hands keep working. Every client-facing
  string in this repo now prints the NEW domain.
- **info@pivottmc.com** (canonical public contact) · www.pivottmc.com ·
  monitored inbox: cs@pivottmc.com
- **The itinerary HEADER carries `cs@pivottmc.com` + hotline `+966 11 220 0296`**
  (`HEADER_EMAIL` / `COMPANY_HOTLINE`, owner's explicit call 2026-09-09, asked and confirmed): a
  client with a booking question is meant to reach the ticketing desk that watches that inbox. This
  is a deliberate exception to the line below, which still governs the T&C page and the guide.
- **info@ is what every issued PDF shows** (`COMPANY_EMAIL` in `generate_itinerary_v3.py`,
  mirrored in `air_suvidha/generate_air_suvidha_guide.py`). cs@ is the automation's own
  inbox and must NOT appear on a document a client reads.
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

## 5. The design (LOCKED — Apple-guidelines redesign, approved 2026-10-30)

Light page, **Inter only** (variable, optical sizing; inlined from `assets/fonts/` so a render needs
no network — Cormorant Garamond is retired). Ink `#1d1d1f`, secondary `#5b6470` (6.0:1 on white),
hairline `#e3e3e8`, grouped surface `#f5f5f7`. Gold `#c9a84c` is an **ornament** (rules, the plane
line, the logo ring); gold **text** is `#85660f` (5.4:1). Every text style passes WCAG AA; nothing on
the page is smaller than 10px except the footer (8.5px). Chosen by the owner from rendered candidates
(three layouts and a refresh were drawn through the real engine first); applied the same day.

- **Masthead:** one quiet line. The feather logo sits in a small dark rounded **tile** (the mark is
  light-on-dark, so it needs a dark ground; no brightness/invert filter, §3) beside the wordmark
  (`Pivot` 700 / `Travel Management` 400). Right-aligned stack: the document label (`_DOC_STATE`, tinted
  by `ink`), `Issued <date> · <HH:MM> AST[ · Revision N]`, and `COMPANY_HOTLINE · HEADER_EMAIL` on its
  own line. **There is no dark header band and no dark footer band** — the "black trim" went at the
  owner's request.
- **Hero:** `PNR reference` (or `PNR references`) with the reference set large (54px; 46/38px for long
  or split values). Below it the facts row — `Agency ref. / CRS ref. / Booked on / Journey` — each cell
  an equal share of the width, hairline-divided. `Booked on` is the one cell that can be empty, so it
  goes through `_na()` (§8 2026-10-25).
- **Travellers:** an inset grouped list, one row per passenger: name left, `Ticket no.` right.
- **Journeys:** a heading per segment (`Outbound` / `Inbound` / `Flight`, route, weekday date), then one
  **boarding-pass card per flight**: carrier line (`SV 774  Operated by Saudi Airline` · `Economy · 4h 45m`),
  codes + times + dates + cities + airport/terminal, a **perforation with side notches** (the signature),
  and a per-passenger table `Passenger | Cabin | Checked | Seat`. **The seat is the boldest figure.**
  A column is omitted entirely when no passenger on that leg has a value. Layovers are a grey pill
  between cards.
- **Split-carrier bookings:** the header shows the references joined (`B9PS6D / 8XMVR7`) under
  `PNR references`, and **each flight card carries its own `PNR <ref>` chip** (it used to sit on the
  segment banner, which mis-labelled a mixed-carrier segment with only its first carrier's reference —
  seen on 72CH2K, TK legs `UR8ANH` + SV leg `72CH2K`). Chips are suppressed on single-reference bookings.
- **Terms & conditions:** the eight clauses at 10px in two columns, always on a fresh last page, always
  issued by "Pivot Travel Management".
- **Footer:** Chromium footer template on every page — `PIVOT AUTOMATED ITINERARY | <PNR> | WWW.PIVOTTMC.COM`
  and `Page n of N`. **CR and VAT are no longer printed** (owner's call, 2026-10-30); `COMPANY_CR` /
  `COMPANY_VAT` stay defined, unrendered, so restoring them is one line in `_footer_template`.
- **Pagination:** browser-driven, single pass. Cards never split, a segment heading stays with its
  first card, layover pills stay with the card before them, T&C starts a new page. (The old two-pass
  Layout A/B measuring is gone; `build_html(..., layout=)` still accepts the argument and ignores it.)
- **NO `box-shadow` anywhere** (still true; §8 2026-07-30 explains why Apple's PDF viewer paints shadows
  as grey slabs). The perforation notches are bordered half-circles, not shadows.
- **Retired with the old design:** the dark header + reference rail, the dark footer and its second CR/VAT
  line, the black segment pills, the gold-outlined plane badge, the `OPERATED BY / CABIN CLASS / DURATION`
  chips (the same airline name was printed twice — now one line), the Cormorant serif.
  `COMPANY_ADDRESS` and `BRAND_STRAPLINE` remain defined and unrendered, as before.
- **Mirrored the same day:** the three alert/digest emails in `main.py` (confirmation digest, manual-review
  digest, disruption alert) — light white masthead with the logo on a dark tile, one sans stack
  (`-apple-system` → SF on Apple Mail/iOS, Inter elsewhere), light footer, gold text darkened to `#85660f`;
  and the Air Suvidha guide (`air_suvidha/generate_air_suvidha_guide.py`, regenerated PDF committed).
  The guide now renders with **Chromium** like the itinerary — WeasyPrint garbled every bold (700) heading
  with the variable Inter — and inlines the same `assets/fonts`. It is still ONE page and still appended
  after the itinerary by `main._append_air_suvidha`. **Regenerate `air_suvidha_guide.pdf` whenever that
  generator changes** (§8 2026-10-11).

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
Split-carrier bookings (two airlines, one agency ref) additionally carry
`pnrs[]` (ordered, de-duplicated) and a per-flight `pnr`; `generate_itinerary_v3.booking_refs()`
is the single reader. Single-reference bookings get a one-item list and render unchanged.

Generator normalises: journey type → ONE-WAY/ROUND TRIP only; names → Title Case; baggage →
weight-only ("7kg", "7kg + 3kg", "1Pcs") — **plus the piece count when the source states more
than one piece for a single weight** ("2 × 23kg", approved 2026-08-19; weight alone understated a
2-piece allowance); missing values → **N/A**; next-day arrival → `HH:MM (+1)`.

## 7. Accuracy rules (non-negotiable)

Never fabricate — missing value = `Not specified`/N/A. Verbatim for PNR, ticket no., flight no.,
names (re-read after writing). Times stay local (no timezone conversion). One booking = one PDF.
If a document is ambiguous / not a confirmation / missing PNR or passenger name → **flag for manual
review, do not produce a PDF**. `qc_check()` gates this (missing PNR / passengers / segments /
flight-no / airport / time; non-Confirmed status).

## 8. What has been polished (recent history)

- **2026-10-31 (later) — manual itinerary form (Google Form → response Sheet → runner → PDF), so a person can issue
  a rare partner ticket without Claude (`manual_sheet.py`, `manual_form/`):**
  Owner: "our ticketing executive could do that without need of me or Claude." Design constraints, all
  deliberate: (1) the repo is PUBLIC and GitHub `workflow_dispatch` inputs are visible in run logs, so passenger
  names and tickets can never be typed into GitHub — they live in a Workspace Form/Sheet and the runner PULLS
  them, exactly as it pulls Gmail; (2) the PDF is e-mailed to **the submitter** (cc cs@), never to a client, so a
  person always checks it first; (3) the same `_finalize` → `qc_check` → revision → `build_pdf` →
  Air-Suvidha path as every portal, so nothing about the document can differ; (4) §7 holds — nothing is guessed:
  `manual_sheet.parse_row` REFUSES an unreadable date (a locale-ambiguous `03/04/2026` is refused, not
  interpreted), a bad time/IATA/ticket/seat, an arrival before departure, or a seat for a passenger that does not
  exist, and the submitter gets "Nothing was built — N things to fix" in plain words. Names are entered as
  title / given name(s) / surname, which settles the surname-first ambiguity (the form builds `Mr. Given Surname`).
  `Booked on` is optional and prints N/A when empty. Sheets returns dates/times as numbers with
  `UNFORMATTED_VALUE` — serial dates and time fractions are decoded (`to_date`/`to_time`).
  **Safety of the rollout:** the Sheets scope is requested with its OWN credential only when `MANUAL_SHEET_ID` is
  set (`main._sheets_service`), so a scope not yet approved in Domain-wide delegation cannot break the Gmail/Drive
  run (adding it to `SCOPES` would have failed every poll); the whole step is wrapped; the log prints counts only.
  A row is picked up while its `Runner status` cell is empty and is marked `PROCESSING` BEFORE building (a crash
  cannot duplicate a PDF). One-time setup is `manual_form/create_manual_form.gs` (Apps Script) + one DWD scope +
  two secrets; see `manual_form/README.md`. Split-carrier: a flight's optional "Airline reference" makes every
  other flight inherit the booking PNR so both references print. Tested end to end against fake Sheets/Drive/Gmail
  clients (one row built → To submitter, Cc cs@, PDF attached; one rejected → fix-list e-mail; one already DONE →
  skipped). 325 tests pass (`tests/test_manual_sheet.py`, including a check that every title the runner reads
  exists in the Apps Script).

- **2026-10-31 — the three internal e-mails redesigned around "what do I do next?" (new `email_templates.py`):**
  Owner: "make it more useable and easy to understand", for the alert e-mail and for the e-mail that arrives
  with each itinerary. Before: the confirmation was a monospace data readout, the manual-review digest showed
  a raw reason string and a bare message id, and the disruption alert listed From / Subject / Received / Preview
  / Ref — nothing said which booking was hit, how urgent it was, or where to click.
  **Confirmation** (`Booking Confirmation — <PNR> (<portal>) · RUH→COK · 17 Dec`; the old prefix is kept so any
  mail filter still matches): a green "Itinerary ready" bar with the next step, the PNR large, route + date,
  a **"Worth a look"** box that lists what a person should check before forwarding — Revision N, India arrival
  (Air Suvidha page included), two airline references, a missing Booked-on date or ticket number (reported,
  never filled in) — then travellers + tickets and one card per flight with its **seat per passenger per leg**
  (this also retires `_bags_vary_by_leg`: allowances are now shown per leg). **Manual review**: a headline in
  plain words ("A flight number, airport or time could not be read from the ticket"), the technical detail in
  small type, an **Open the e-mail** button (Gmail deep link) and a three-line fix list. **Disruption alert**:
  "3 flight alerts to deal with — 1 cancellation, 1 schedule change, 1 delay", a 3-step what-to-do box, then a
  card per alert, most urgent first, with a severity pill, the **airline named** (`extractors.sender_label`),
  the booking ref / flight / route / date / times **read from the subject and preview only**
  (`extractors.disruption_summary`, same patterns as the dedup fingerprint; absent when not stated, and labelled
  "confirm in the e-mail"), what the airline wrote, the draft-revised-itinerary note, and an **Open the airline
  e-mail** button. The subject now carries the counts and the booking refs
  (`⚠️ ACTION REQUIRED — 1 cancellation, 1 delay (8JS4ID, UCHMPF)`). Times are listed with `·`, never `→`, because
  the order in an airline's sentence is not reliably old-then-new and an arrow would assert one.
  The templates live in a pure module so the offline suite can import them (`main.py` imports Google at load, so
  it never could be tested); `main.py` now only builds the message, attaches the logo and PDF, and sends.
  `tests/test_email_templates.py` (22 tests). 295 pass. The Gmail deep link uses the API message id and is
  best-effort; the Source ref stays printed beside it.

- **2026-10-30 — itinerary redesigned to Apple's guidelines; Inter only; dark bands gone; CR/VAT off the footer:**
  The owner asked for a redesign "according to the Apple design skill". Three completely different
  layouts (Poster, Timeline, Bento) and a refresh of the old look were rendered through the real data
  before anything was applied; the owner chose the boarding-pass layout (§5) and asked for no CR/VAT.
  **Why it was worth doing — measured, not taste:** on the old render **18 of 37 text styles failed WCAG
  AA** (gold `#c9a84c` on white is 2.29:1 and carried the labels, section titles, flight numbers and
  dates; the airport line was 2.84:1, the airline name 2.85:1, the footer ~3:1), and the smallest text was
  6.5px (4.9pt) — about 3pt once an A4 page is shrunk to a phone, below Apple's 11pt floor. New render:
  0 failures, lowest contrast 5.38:1, smallest body text 10px.
  **Fonts:** SF Pro was requested; it cannot be used (Apple's licence covers Apple-platform apps and
  mock-ups, not documents sent to clients, and the Linux runner does not have it). Inter with optical
  sizing is the open (SIL OFL) equivalent. The variable `latin` + `latin-ext` subsets are committed in
  `assets/fonts/` and **inlined as base64**, so rendering needs no network and cannot fall back to a system
  face (this also retires the 2026-10 sandbox problem where Chromium silently used Liberation). Latin-ext
  carries the Turkish letters in names (verified: `Şükrü Güllü İbrahim Çağlar` renders in Inter).
  **Code:** `generate_itinerary_v3.py` rewritten around the same data-prep (the airport/terminal/name
  backfills and the per-leg pax fallback are carried over verbatim); helpers, constants, `_norm_bag`, the
  T&C wording and `booking_refs` are unchanged. `build_pdf` is single-pass and uses Chromium's footer
  template for `Page n of N`. `_flight_card` keeps its name but takes `(flight, multi=False)`.
  **Tests:** 273 pass. Markup-coupled assertions were moved to the new classes (`hdr-val` → `fact`,
  `pnr-value` → `pnr`, `seg-pnr` → per-flight `chip`) without weakening what they check; the old
  `_pax_card` test became "the Traveller row never shows baggage or seat". `tests/test_new_design.py`
  adds guards: no serif, font inlined and latin-ext present, no dark bands, footer has reference + website
  and **no CR/VAT**, seat column, state colours, gold-text token.
  **Cost, stated plainly:** a round trip still fits one itinerary page plus the terms page; the 3-leg
  UR8ANH / 72CH2K booking still spills its last leg onto a second page, exactly as the old layout did.
  The footer is now a Chromium template, so a PDF is no longer one self-contained HTML render with a
  footer pinned inside it. The three alert emails and the Air Suvidha guide are NOT yet restyled (§5).

- **2026-10-25 — "BOOKED ON" could print as a bare label with nothing under it:**
  Found while hand-building a Saudia DOH→JED document from a portal quote screen. The
  header rail drew **`BOOKED ON` with no value beneath it**, out of alignment with
  `JOURNEY` beside it, because an empty value collapses the cell. Cause:
  `booked_on = data.get("booked_on", "N/A")` — a `.get()` default fires only when the KEY
  IS ABSENT, so a key present-but-empty went through unprotected, unlike every other field,
  which passes through `_na()`. Now `_na(data.get("booked_on", ""))`: missing renders **N/A** (§6).
  **Not only a hand-built-data problem:** `extract_pegasus` sets `booked_on = ""` outright
  and `_finalize` backfills it only when a ctx date is supplied. The cloud runner passes the
  email date, which masked it in production — but **every manual build and every `\process`
  upload would have shipped the empty label to a client**. Both routes were tested before fixing.
  "Booked On" is the ONLY cell that can be reached empty: Agency Ref. and CRS Ref. are appended
  only when they hold a value, and Journey always resolves to ONE-WAY or ROUND TRIP.
  New `tests/test_booked_on_na.py` locks in both shapes (absent key, present-but-empty), the
  real-date case, and the Pegasus production shape; the suite was re-run with the fix REVERTED
  to confirm the tests actually catch it (3 fail). 260 tests pass.


- **2026-10-13 — our OWN cancellation requests to Alhind / Akbar no longer raise alerts:**
  Staff ask the Alhind/Akbar B2B desk to cancel, refund or reissue a ticket; the desk
  replies inside that thread, and the watch raised an ⚠️ ACTION REQUIRED alert for a
  cancellation **we initiated and already knew about**. `-from:<our domains>` cannot
  catch it — the reply comes from THEIR domain, carrying our own wording
  (`RE: ALQ...- CANCELLATION AND REFUND REQUEST`, `REQUEST FOR TICKET CANCELLATION`),
  so `disruption_match` saw "cancel" and fired. Fix: a NEGATIVE rule
  (`_DISRUPTION_EXCLUDE_RE`) checked BEFORE the keywords — **a subject framing the
  matter as a REQUEST is our own ticket thread; an airline NOTIFIES, it does not send
  us requests.** Checked against every real example in the mailbox: the standalone noun
  is in **6/6** of our request threads and **0/4** genuine disruptions — including the
  two that arrive from Alhind's OWN address (`FLIGHT CANCELLATION INFORMATION //<ref>`
  forwarded from Himalaya, and `RE: ALQ...- FLIGHT DISRUPTED`), which both still alert.
  Deliberately matched as a WHOLE WORD (`\brequest\b`): every real subject uses the bare
  noun, while an airline might plausibly write "action requested" — that one still
  alerts, so the rule **fails open** per §7. The Gmail query is unchanged (it stays the
  coarse net; `disruption_match` keeps the final say, so the rule is unit-tested
  offline). 255 tests pass.

- **2026-10-12 — itinerary header redesigned (One Rail): the dead gap in the reference row is gone:**
  Asked and confirmed twice per §5, chosen from three directions drawn and rendered through the REAL
  generator rather than mocked up. The complaint was measurable, not a matter of taste: the
  2026-09-09 reference row left **a dead gap through its middle** — the reference sat left, the four
  cells huddled right as a fixed-width group, and the space between them was a function of the
  reference's length. On a 13-character Riyadh Air locator it was tolerable; on a 6-character PNR it
  was most of the row. It could not be closed while the cells were a group, so each cell now takes an
  equal share of the width and the rail spans the page. Rendered at both lengths and on the longest
  disruption label: **110px in every case, down from 120px**.
  Also at the owner's call: the **registered address is out of the header** and the wordmark grew
  into the space (24px → 30px, logo 34 → 40px), and the **service strip carrying the strapline is
  gone**. The address still prints on the T&C page, so the document does not lose it; both
  `COMPANY_ADDRESS` and `BRAND_STRAPLINE` are kept defined but rendered nowhere.
  The hotline and cs@ had been riding on the strapline row, so they moved into the right-hand stack
  as **their own line**. Appending them to the issue stamp was tried first and produced a single
  `nowrap` line that **overran the page edge, clipping both the state label and the email** — caught
  by rendering the candidate, not by reading it.
  Verified: 247 tests pass (checked by swapping the real file in, not by shadowing it on
  `PYTHONPATH`, which silently kept using the repo copy and proved nothing); three states rendered
  and measured. Confined to the itinerary header — grep confirmed nothing else renders the address,
  the strapline or any `.hdr-*` class, and the emails and guide keep their own simpler headers.


- **2026-10-11 — Workspace primary domain moved to `pivottmc.com`; every client-facing
  string follows, and two latent faults surfaced while doing it:**
  The Workspace primary became `pivottmc.com` and all users were renamed;
  `pivot-travels.com` stays an **alias**, so old addresses still deliver and documents
  already issued keep working — which makes this a safe cutover rather than a flag day.
  Changed: `COMPANY_EMAIL` → info@pivottmc.com (T&C page + Air Suvidha guide),
  `HEADER_EMAIL` → cs@pivottmc.com (header service bar), and the website in all five
  footers.
  (1) **The website was a bare literal repeated in five places** across three files —
  the itinerary footer, the guide footer, and the three alert/digest email footers.
  That is the same shape of drift that let the T&C page keep printing cs@ for months
  (§8 2026-08-02), and a domain change could easily have updated four and left the
  fifth lying to a client. It is now the single `COMPANY_WEBSITE` constant, imported by
  `main.py` and mirrored in the standalone guide generator exactly as `COMPANY_EMAIL` is.
  (2) **`scan_disruptions` excluded only `-from:pivot-travels.com`.** Since staff and the
  runner now send as pivottmc.com, that filter no longer matched our own mail and the
  disruption watch would have begun alerting on Pivot's **own** outbound messages —
  including cancellation requests WE send to portals. Both domains are now excluded.
  (3) **The Air Suvidha generator had been broken since 2026-09-09.** The wordmark
  bolding added that day wrote `.company-name b { font-weight: 700; }` with UNESCAPED
  braces inside the CSS f-string, so `build_html` died with
  `NameError: name 'font' is not defined` — the exact failure recorded in §8 2026-07-30
  (`name 'box' is not defined`). Nobody noticed because the guide is a committed runtime
  asset and had not been regenerated since. Escaped, regenerated and re-committed; the
  guide now prints the new domain. **Regenerating that PDF is a required step whenever
  the guide generator changes** — editing the generator alone ships nothing.
  Verified by extracting text from a freshly rendered itinerary (header, T&C and footer)
  and from the rebuilt guide: new domain present, old domain absent from both. The three
  email bodies were rendered and asserted too, since a non-f-string would have printed the
  brace literally. 247 tests pass.


- **2026-09-30 — "OPERATED BY: Riyadh" (a city as the carrier), and a terminal that crossed
  between two separate tickets:**
  Real Akbar booking AS261599740 (RX 863, RUH→KUL) shipped naming the operator **`Riyadh`**.
  Diagnosed per §9 against the real PDF's pdfplumber text (medic run, message 1a0f2950768a5fa3),
  which wraps the cell as `Operated by:Riyadh , Sat, 10 Oct 26 (08h:00m) Airport , Sun, 11 Oct 26`
  / `Air` — the carrier is **Riyadh Air**, a new RUH-hub airline, split over two lines. The
  2026-08-19 re-join only pulled a continuation back when it STARTED with
  `Airline(s)`/`Airways`/`Aviation`, and this one is the bare word `Air`. Matching `Air` loosely
  would have re-opened the 2026-08-20 defect — the To-column's `Airport , …` bleed begins with the
  same three letters — so **`Air` counts only when it is the ENTIRE continuation line**. Every
  previously-working shape is asserted unchanged (Saudi Airline, Air Sial, Flyadeal, Saudi Arabian
  Airlines, the airport bleed, no-match).
  **Second, found while consolidating two bookings onto one document** (RX12239 Riyadh Air RUH→KUL
  + BMGECWP Spring Airlines KUL→CAN, three days later): `build_html`'s terminal backfill copied
  Spring's stated **KUL Terminal 2** onto Riyadh Air's KUL arrival, where the Akbar ticket states
  no terminal at all — and a full-service carrier into KLIA need not use the low-cost terminal.
  The backfill's premise ("the same IATA is the same physical airport") holds for one ticket but
  **not across separately-ticketed journeys**, so the terminal map is now keyed
  `(reference, IATA)`. Airport NAMES stay global — a name is the same fact on every ticket, which
  is why the static table is allowed at all (§8 2026-08-02). A single-reference booking behaves
  exactly as before. 247 tests pass.

- **2026-09-24 — Turkish Airlines: a mangled city name and a dropped seat:**
  Real one-way KYA→IST→RUH ticket (T67TR3). Two defects on one document.
  (1) **"Ri̇yadh".** Turkish Airlines prints place names with Turkish locale capitals —
  `RİYADH (SAUDİ ARABİA)`, `TÜRKİYE`. Python lowercases U+0130 (İ) to "i" **plus a combining dot**
  (U+0307), so the plain `.title()` produced `Ri̇yadh` — a visibly broken destination on a client
  document. New `_tr_clean` / `_tr_title` fold the two Turkish-only letters (İ, ı) to ASCII and drop
  a stray combining dot; every other character, accents included, is left alone (asserted:
  `München` survives). (2) **The seat never reached the itinerary.** The same PDF carries an
  `Additional services / Seat selection` block listing `<DEP> - <ARR> : <SEAT>` per leg — this
  booking had 19A on the IST→RUH leg. The code's note said Turkish carried no seat data at all,
  which was true of the two files it was written against in July and **false for newer ones**; the
  client had paid for a seat that was silently dropped. Seats are now parsed per leg and attached by
  route, with a lone `-` correctly meaning none. Read **only for single-passenger bookings**: the
  block repeats per passenger and its shape there is unverified, so a seat is never attached to a
  traveller it might not belong to (§7 — wrong is worse than missing). Zero-PII fixture reproduces
  both. 242 tests pass.

- **2026-09-09 (later) — revision counter: two copies of one booking can finally be told apart:**
  The gap left open by the header redesign, closed. A reissue produced a second PDF carrying the
  same reference, the same "Booked On" date and no way to tell which copy was current — a passenger
  travelling on the older print-out goes to the wrong gate at the wrong hour (8JS4ID reissued
  07 Sep, 8JVF9L 27 Aug). The header now stamps `· Revision N` from the second copy onward.
  **The counter is keyed on a truncated SHA-256 of the reference** (`extractors.revision_key`), NOT
  the PNR: `revision_ids.json` is committed to a PUBLIC repo, and the disruption log made exactly
  that mistake on 2026-07-22 and had to be scrubbed (§11). The key normalises case, order and
  whitespace, so a split-carrier booking counts once however its two references are spelled.
  `main.next_revision` counts a render and returns which copy it is; it is called BEFORE `build_pdf`
  at both render sites (the poll loop and the revised-draft builder), and the log is checkpointed
  next to `processed_ids.json` so a crash between the two cannot issue the same number twice. A
  booking with no usable reference returns 0 and prints nothing — a number that cannot be tied to a
  booking is worse than none (§7). `poll.yml` persists the new file beside the other logs.
  Deliberately shown only from copy 2: "Revision 1" on a first issue tells the reader nothing, so
  every first-issue document is byte-identical to what it would have been. 237 tests pass.

- **2026-09-09 — header redesigned (Reference Block) and "Official Travel Document" retired:**
  Asked and confirmed twice per §5, chosen from three drawn directions. Three complaints, all
  measurable rather than matters of taste. (1) **The label was wrong.** In aviation and immigration
  language a *travel document* is a passport, visa or laissez-passer, and *official* implies an
  authority issued it — this page is neither, and calling it official invites a passenger to present
  it where it carries no weight. It now reads **Itinerary Confirmation**, flexing to *Revised
  Itinerary · Rescheduled* etc. (2) **The reference was set at 18px** on a 794px page — smaller than
  the wordmark above it, so the eye landed on the brand and never travelled to the code. It is now
  34px and reads first. (3) **The bottom row was half empty**: a pill left, the reference right, a
  wide dead gap through the middle. Filled with the reference cells lifted out of the capsule that
  used to sit BELOW the header — a move, not an addition, and the page is ~70px shorter for it.
  Also approved in the same pass: the wordmark goes inline with `Pivot` bold against `Travel
  Management` regular (mirrored in the Air Suvidha guide and all three alert/digest emails); the
  registered address prints under it; the strapline drops to a service bar carrying the hotline; and
  the **CONFIRMED pill is retired** — it duplicated the label beside it, and its dot glow was the
  last `box-shadow` in the file (the one primitive Apple's PDF viewer paints as a grey slab, §8
  2026-07-30). **Deliberately NOT done: the revision counter.** The header stamps the issue time,
  which is honest at render, but "Revision 2 of 2" needs state keyed on the PNR in
  `processed_log.json` — printing a guessed number would be exactly the fabrication §7 forbids. The
  gap it leaves is real: 8JS4ID and 8JVF9L were each reissued this fortnight and the client received
  a second PDF with the same reference, the same "Booked On" date and nothing to say which was
  current. **Built the same day** — see the entry above. Verified on a real Akbar booking (9L6WUH, CAI→RUH) and on the split-carrier fixture,
  where `AAA111 / BBB222` at 34px still clears the reference cells. 230 tests pass.

- **2026-08-25 — Akbar terminals now RENDER, attributed by column position; and
  two passenger types no longer merge into one baggage figure:**
  Real Akbar/Saudia booking AS261379552 (RUH↔CCJ, Business, 3 pax).
  (1) **Terminals.** Blank on Akbar since 2026-07-17 because a stated terminal
  flattens to a bare `Terminal <n>` line and an unstated one to nothing, so the
  token could not be tied to a side (an earlier guess put the fragment `North`
  on the wrong airport). This booking proves the flattened text can *never*
  settle it: the SAME airport (RUH, Terminal 2) is the departure on the outbound
  leg and the arrival on the inbound, rendering identically both times. In the
  PDF it is unambiguous — the token's left edge lines up with its column header
  (`From (Terminal)` x0≈101.7, `To (Terminal)` x0≈378.8). New pure
  **`akbar_terminals_from_words()`** reads pdfplumber's word boxes and returns
  one `{dep, arr}` per flight table; `main.akbar_attachment_text(..., with_words=True)`
  supplies them via `ctx["terminals"]`. A token matching neither column (or both)
  is DROPPED, not guessed. No boxes (Drive fallback, every `.txt` fixture) →
  blank, exactly as before. **The static IATA→terminal table stays rejected** —
  this reads what the document itself states, per segment.
  (2) **Baggage across passenger types.** The fare states
  `Adult - 2 Pieces | 1 BAG UP TO 32KG | Infant - 1 Piece | 1 Piece equals 23KG`;
  `_norm_bag` collected every weight and joined them, so all three travellers
  rendered **`32kg + 23kg`** — 55kg, which nobody on the booking holds (§7 wrong,
  not merely missing). Only the FIRST type's block is kept now → `2 × 32kg`.
  Strings with one type marker or none are untouched, so aJet's genuine
  two-bag `7kg + 3kg` still shows both weights. 203 tests pass; no golden changed.

- **2026-08-20 (later) — an airport named as the carrier, and a sentence
  printed as a baggage allowance:**
  Real Akbar/Saudia round trip AS261349396 (MED↔RUH) shipped a card reading
  `OPERATED BY: Saudi International Airport Airline` and `CABIN: baggage`.
  Two independent causes. (1) The From/To column's **airport name bleeds into
  the `Operated by:` cell** — `Operated by:Saudi International Airport , Fri, 02
  Oct 26 …` / `Airline Saudi Arabia,` — so cutting at the first comma kept the
  airport and the 2026-08-19 continuation re-join then appended `Airline` to it.
  No airline's name contains "Airport", so `_AIRPORT_TAIL` now cuts the value
  there (dropping an `International`/`Domestic`/`Regional` qualifier with it):
  `Saudi International Airport` → `Saudi` → + `Airline` = **`Saudi Airline`**,
  which is what the fare block states. The INBOUND leg of the same booking
  parsed correctly **by luck** (its wrap put the weekday, not the airport, next
  to the carrier) — one good leg is not evidence the cell parsed. (2) The Cabin
  Baggage column carries the fare-rules sentence *"Adult 1 Piece : Short
  conditions regarding carry-on baggage allowance details. - 1pc x 7kg"*.
  `_m` searches **case-insensitively** and the labels had an optional colon and
  no line anchor, so `…regarding carry-on baggage` satisfied `Carry-On` and
  captured the next word. Labels are now **line-anchored and require their
  colon**, which also stops a colon-less column HEADER (`Travel Class Check-In
  Baggage Cabin Baggage`) being read as a value. (3) Per-direction baggage now
  comes from the **ONWARD/RETURN traveller blocks** (`_akbar_direction_bags`)
  instead of the `Airline Ref :` slice — this layout puts both flight tables
  first and both traveller blocks after them, so the slice gave the outbound leg
  nothing and the inbound leg the OUTBOUND block. Layouts without those headings
  fall back to the booking-level values exactly as before. Checked baggage on
  this booking renders `1Pcs`: the source states a piece count and the weight is
  lost to the column bleed — incomplete, not wrong (§7). Three more of the same
  day's bookings (8ZNLAQ, 8ZFNBC, 8XUEGZ) had shipped with `CABIN: baggage` and
  were re-issued. 183 tests pass; regenerating the goldens changed no existing
  value.

- **2026-08-20 — split-carrier bookings: BOTH airline references now reach the
  traveller, and each leg carries its own baggage:**
  Real Akbar booking AS261347760 (Flyadeal EAM→RUH out, Saudia RUH→EAM back)
  sells two airlines under ONE agency reference, and each airline issues its own
  record locator — `B9PS6D` outbound, `8XMVR7` inbound. The PDF showed only the
  first, so the traveller had **nothing to check in with on the return leg**.
  Three defects, all from treating a two-airline booking as if it had one of
  everything: (1) one reference; (2) one baggage allowance applied to both legs —
  the document claimed **32 Kg on a Saudia leg that allows 1 × 23 Kg**, a wrong
  fact rather than a missing one (§7); (3) **no ticket number** — the search
  window ran from the first `Traveler` to the first `Carry-On`, and on this
  layout the first Traveler table has no `Ticket No.` column at all (the number
  sits in the second one, past that cut). Fixes: `extract_akbar` captures the
  per-segment `Airline Ref` onto each flight (`flight["pnr"]`) and reads each
  direction's OWN `Carry-On :` / `Baggage Allowance :` values into a per-leg
  `pax[]` (Akbar's block repeats EMPTY before the populated copy, so
  `_akbar_first_value` takes the first non-blank); the ticket window now spans
  every `Traveler` block. `_finalize` publishes the ordered, de-duplicated
  `pnrs` list for **every** portal, so one-airline bookings simply get a one-item
  list. **Approved design change** (asked and confirmed): both references render
  in the header (`AAA111 / BBB222`, label becomes `PNR References`), a gold
  `PNR <ref>` chip sits on **each segment banner**, the footer lists both, and
  the file is named `B9PS6D-8XMVR7.pdf`. All of it is conditional on there being
  more than one reference — a single-reference booking's HTML was verified
  **byte-identical** across all three layouts (A / B / measure) on four real
  Akbar fixtures. Goldens regenerated: **zero existing values changed**, only
  the new keys added. 167 tests pass.

- **2026-08-19 (later) — "OPERATED BY: Saudi Mon" — a carrier that does not exist:**
  Booking 8CP5SK shipped naming the operator **`Saudi Mon`**. The real Akbar PDF renders
  the cell WRAPPED, with the date column bled onto the first line:
  `Operated by:Saudi Mon, 24 Aug 26 (02h:45m) Egypt, Mon, 24 Aug 26` / `Airline Saudi Arabia,`
  — so the carrier is **`Saudi Airline`**, split over two lines, and the weekday `Mon` glued
  onto it. The 2026-08-02 widening (which correctly fixed `Air` → `Air Sial`) let the weekday
  through, because the cut-at-first-comma happens AFTER it. `_akbar_airline` now strips a
  trailing **weekday** and re-joins a continuation line that STARTS with a carrier suffix
  (`Airline(s)` / `Airways` / `Aviation`); anything else on that line is a different column and
  is left alone. Zero-PII fixture reproduces the wrapped layout. Every previously-working
  shape is asserted unchanged (Air Sial, Flyadeal, Saudi Arabian Airlines, TestAir, no-match).
  152 tests pass; regenerating goldens changed none of the existing ones.

- **2026-08-19 — multi-piece baggage no longer understated (approved design change):**
  Real Akbar/Saudia booking 8CP5SK stated `Adult - 2 Pieces | 1 BAG UP TO 23KG` — two 23kg
  bags — and the card rendered **`23kg`**, which reads as ONE bag. The weight-only rule
  (§6) extracts the weights and discards everything else, so the piece count was dropped and
  the traveller could have left a whole 23kg entitlement unused. `_norm_bag` now prefixes the
  count when the source states **>1 piece for a single weight** → `2 × 23kg`. Deliberately
  narrow: no count when several weights were found (`7kg + 3kg` already enumerates them) and
  never when the count is 1, so **every single-piece booking renders byte-identically** and
  the locked look is unchanged for them. Tests assert both directions. 143 tests pass.

- **2026-08-03 — disruption dedup keyed on FACTS, not the day (+ PNR removed from the public log):**
  The 2026-07-22 day-based key still repeated. Two real causes, both diagnosed
  against the live mailbox: (a) **IndiGo re-sends a byte-identical "Your Revised
  IndiGo Itinerary"** (PNR VHZPNH, `6E-85, 17 Aug, HYD-DMM 0510-0755`) for days —
  a new calendar day meant a new key, so it re-alerted on 27 Jul, 31 Jul, and
  twice on 3 Aug; the same-day double happened because **IndiGo backdates the
  Date header** (a notice that ARRIVED 03 Aug 10:33 was stamped 02 Aug 22:22, so
  `day` differed). (b) The day component also **suppressed genuinely new
  information** — Turkish's 17:14 "the departure time of your flight…" was
  dropped merely for sharing a day with the 13:39 notice. Fix: key is now
  `<sender-domain>:<PNR>:<category>:<facts-fingerprint>` where the fingerprint
  (`disruption_facts`) is the notice's flight number / route / date / times.
  Identical re-sends collapse **permanently**; a real revision alerts even
  minutes later; escalation (delay→cancellation) still alerts. Verified on the
  real Turkish VJG3IZ trio: initial delay alerts, the new-departure-time notice
  alerts, the boarding-gate call is suppressed as a dup of the first.
  **Privacy:** the 07-22 key stored a raw PNR in `disruption_ids.json` in the
  **public** repo (contra §11) — the key is now a truncated SHA-256 hash and the
  6 plaintext entries were scrubbed from the file (they remain in git history).
  80 tests pass.
- **2026-08-02 (later) — client-facing contact switched cs@ → info@:** an audit of every
  address in the repo found that both PDFs a client actually receives — the itinerary's
  T&C page ("Clarifications: …") and the Air Suvidha guide's "Need help?" footer — printed
  **cs@pivot-travels.com**, which is the automation's own monitored inbox (`IMPERSONATE_USER`,
  the address the runner reads and can send as). Clients were being pointed at the robot.
  Both now render the new `COMPANY_EMAIL = "info@pivot-travels.com"` constant, mirrored in
  the guide generator so the two documents can't drift apart; `air_suvidha_guide.pdf` was
  regenerated and re-committed. **Internal plumbing is unchanged** — the runner still READS
  cs@ and still sends its confirmation digests there; only the two client-visible strings moved.
  Verified by extracting text from both freshly rendered PDFs (info@ present, cs@ absent).
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
  **Terminals were then parsed by Alhind ONLY** — correct at the time; Akbar
  joined it on 2026-08-25 via column-position attribution (see the entry above).
  aJet / Pegasus / Turkish genuinely don't carry the data (re-verified 2026-07-27). 114 tests pass;
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
  **Turkish Airlines** per-direction baggage + PER-LEG seats (the seat block was added to
  their PDF later; parsed since 2026-09-24) ·
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
