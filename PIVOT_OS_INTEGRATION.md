# Pivot OS ⇄ Itinerary Automation — Integration Contract

> **Purpose:** connect the itinerary automation (this repo) to **Pivot OS** so every
> itinerary it produces surfaces in a **"Entries to Be Done"** card, pre-fills the
> booking-entry form, and disappears once the booking is saved.
>
> **Direction:** one-way push. Itinerary automation = **Producer**. Pivot OS = **Consumer**.
> Pivot OS owns all state (dedup, pending list, saved bookings). The Producer is
> stateless with respect to Pivot OS — it just emits an idempotent event per itinerary.
>
> **Scope note:** this system handles **flights only**. There is **no hotel data** and
> **no fare/financial data** — financials are intentionally left for the user to enter
> in Pivot OS. "Supplier" ≈ the booking **portal** (Alhind / Akbar Travels / aJet / Pegasus).

---

## ✅ STATUS: v1.0 AGREED & IMPLEMENTED (Producer side)

The Pivot OS session answered §7; the Producer is now built to this locked contract:

- **Transport:** webhook — `POST https://<pivot-os-host>/api/itinerary-sync`.
- **Auth:** `Authorization: Bearer <secret>`. Same value both sides
  (`PIVOT_OS_SYNC_SECRET` here = `ITINERARY_SYNC_SECRET` there). **No** company field in the body
  (Pivot OS stamps `companyId` itself). No HMAC for now.
- **Dates:** departure/arrival dates sent as **ISO `YYYY-MM-DD`**. Times (`HH:MM`, local) and
  `flight_no` (`"VF 200"`) sent as-is (display-only on their side; not persisted).
- **Duplicate key:** composite — payload carries `reference.match_key = "<pnr>:<portal>"`.
- **Idempotency:** `idempotency_key = "<pnr>:<status>:<source_ref>"`; Pivot OS upserts on it.
- **Responses:** `2xx` = accepted · `200 {"status":"duplicate"}` = already a saved booking (ignored,
  not an error) · `400` malformed · `401` bad token · `503` secret unset their side (retry later) ·
  `500` transient (retry).
- **Supplier mapping (their side):** `Alhind`→"Alhind KSA" & `Akbar Travels`→"Akbar Travels KSA"
  = `SUPPLIER_PORTAL`; `aJet`/`Pegasus` = `DIRECT_AIRLINE` (no supplier row). Producer keeps sending
  the exact portal strings unchanged.

**To go live, Minhaj sets two GitHub Secrets** (until then the Producer is inert):
`PIVOT_OS_SYNC_URL` (the production Vercel host + `/api/itinerary-sync`) and
`PIVOT_OS_SYNC_SECRET` (the shared Bearer value, matching Pivot OS's `ITINERARY_SYNC_SECRET`).

The reference schema below is unchanged except the date format (now ISO). Historical detail retained.

---

## 1. Transport — how Pivot OS receives an entry

Pick **ONE** (A recommended):

### Option A — Webhook (recommended)
Pivot OS exposes an HTTPS endpoint; the Producer `POST`s one JSON event per itinerary.

```
POST  https://<pivot-os-host>/api/itinerary-sync
Authorization: Bearer <PIVOT_OS_TOKEN>          # shared secret, or HMAC (see §7)
Content-Type: application/json
Idempotency-Key: <idempotency_key>              # also in body; see §4
```
- **200/201** → accepted (new or updated pending entry)
- **200** with `{"status":"duplicate"}` → already a saved booking, ignored
- **4xx/5xx** → Producer logs a private failure and retries next run (safe; idempotent)

### Option B — Shared Supabase table (if Pivot OS is on Supabase)
Producer inserts/upserts into a `pending_entries` table; Pivot OS reads via realtime
subscription (instant badge, no polling). Needs the project ref + a service key.
Same field set as the webhook body below.

---

## 2. Database changes in Pivot OS

Two tables (names illustrative):

### `pending_entries`  — the "Entries to Be Done" inbox
| column | type | notes |
|---|---|---|
| `id` | uuid / pk | |
| `idempotency_key` | text, **unique** | dedupes re-sends (see §4) |
| `pnr` | text, indexed | primary match key |
| `booking_ref` | text | portal/agency ref |
| `crs_ref` | text, nullable | only when ≠ pnr |
| `portal` | text | Alhind / Akbar Travels / aJet / Pegasus (≈ supplier) |
| `source_ref` | text | Gmail message id — private trace back to the source email |
| `status` | text | confirmed \| rebooked \| rescheduled \| delayed \| revised |
| `journey_type` | text | ONE-WAY \| ROUND TRIP |
| `payload` | jsonb | the full event body (§3) — drives the prefill |
| `pdf_url` | text | Drive link to the branded PDF |
| `route_summary` | text | e.g. `LHR → CDG` (display convenience) |
| `lead_pax` | text | first passenger name (display) |
| `first_dep_date` | date | earliest departure (sort/display) |
| `received_at` | timestamptz | |
| `state` | text | `pending` \| `done` \| `superseded` |

### `bookings` — your existing saved bookings
- Ensure a **`pnr`** column exists and is indexed (needed for the duplicate check).
- Recommended uniqueness key: **(`pnr`, `portal`)** — see §4 for why not `pnr` alone.

---

## 3. Event payload — exact shape & fields

Grounded in this repo's real data model. Example (synthetic):

```json
{
  "schema_version": "1.0",
  "event": "itinerary.created",
  "idempotency_key": "AJ4X9Z:confirmed:19f6102a9adb4993",
  "produced_at": "2026-07-19T20:05:00Z",
  "source": "itinerary-automation",

  "reference": {
    "pnr": "AJ4X9Z",
    "booking_ref": "AJ4X9Z",
    "crs_ref": null,
    "portal": "aJet",
    "source_ref": "19f6102a9adb4993"
  },

  "status": "confirmed",
  "journey_type": "ROUND TRIP",
  "booked_on": "14 Jul 2026",

  "passengers": [
    { "name": "John Doe", "ticket_no": "6060000000001",
      "cabin_bag": "7kg", "checked_bag": "20kg", "seat": "12A" }
  ],

  "segments": [
    { "type": "Outbound",
      "flights": [
        { "airline": "aJet", "flight_no": "VF 200", "cabin": "Economy",
          "dep_iata": "LHR", "dep_city": "London", "dep_airport": "", "terminal": "",
          "dep_date": "19 Jul 2026", "dep_time": "22:10",
          "arr_iata": "CDG", "arr_city": "Paris", "arr_airport": "", "arr_terminal": "",
          "arr_date": "19 Jul 2026", "arr_time": "02:05", "duration": "3H 55M" }
      ],
      "layovers": []
    }
  ],

  "route_summary": "LHR → CDG",
  "india_arrival": false,
  "pdf_url": "https://drive.google.com/file/d/.../view",
  "financials": null
}
```

**Field notes**
- `event`: `itinerary.created` (new) or `itinerary.revised` (rebooked/rescheduled/delayed draft).
- `status`: mirrors the itinerary's header pill. `confirmed` = normal; the rest = a revision.
- Dates are currently **`"DD Mon YYYY"`** and times **`"HH:MM"` (local, no timezone)**. If Pivot OS
  prefers ISO (`YYYY-MM-DD`, `HH:MM` 24h), say so — the Producer will convert before sending.
- `flight_no` format is `"VF 200"` (airline code + space + number). Tell me your canonical format.
- Empty strings (`dep_airport`, `terminal`, …) mean "not supplied by the portal" — treat as blank.
- `financials` is **always `null`** — this system never has price data. This is the field set the
  user completes in Pivot OS.
- `layovers[]`: `{ "airport": "IST", "duration": "2H 10M" }` when a segment connects.

---

## 4. Duplicate detection (by PNR)

1. **Idempotency (re-sends):** the Producer re-emits the same itinerary on every run until it
   confirms delivery. Pivot OS must upsert on **`idempotency_key`** (unique) so re-sends never
   create duplicate rows. Key = `"<pnr>:<status>:<source_ref>"`.
2. **"Already a booking?"** On receipt, Pivot OS checks `bookings` for a row matching the PNR.
   - Match found → **do not** add to `pending_entries` (respond `{"status":"duplicate"}`; optionally
     store as `superseded` for audit).
   - No match → upsert into `pending_entries` as `state = pending`.
3. **"Entries to Be Done" list** = `pending_entries WHERE state = 'pending'` **AND** `pnr NOT IN (SELECT pnr FROM bookings)`.
4. **On save** (user completes the form) → insert into `bookings` → set the pending row `state = 'done'`
   (or delete). The item vanishes from the card.
5. **Why (pnr, portal) not pnr alone:** airline/CRS PNRs are only unique *per airline per timeframe* and
   can recycle. Keying saved bookings on **(pnr, portal)** avoids a rare cross-airline PNR collision
   hiding a real booking. If your bookings are already PNR-unique in practice, `pnr` alone is fine —
   your call; tell me which so the Producer sends a matching key.
6. **Revised itineraries:** an `itinerary.revised` event for a PNR that is **already saved** should
   **not** silently vanish — surface it (e.g. a "booking changed — review" flag on the saved booking or
   a distinct pending row). For a PNR still pending, it simply **updates** the pending row's payload.

---

## 5. "Entries to Be Done" card behaviour

- Lists pending items, most-recent or soonest-departure first; each row shows
  `lead_pax · route_summary · first_dep_date · portal · status-pill`.
- A **revision** (`rebooked` / `rescheduled` / `delayed`) shows the same coloured pill as the
  itinerary/alert (red / orange / amber) so the user sees at a glance it's a change, not a fresh booking.
- Click a row → open the **normal booking-entry form**, pre-filled from `payload` (§6).
- Show the `pdf_url` (link/preview of the branded itinerary) beside the form for verification.
- On successful save → remove the row (state → done). On dismiss → optional `state = dismissed`.
- Badge count = number of `pending` rows.

---

## 6. Mapping itinerary → booking-entry form

| Booking form field | From payload |
|---|---|
| PNR / airline ref | `reference.pnr` |
| Booking ref | `reference.booking_ref` |
| CRS ref | `reference.crs_ref` |
| Supplier / source | `reference.portal` |
| Passenger name(s) | `passengers[].name` |
| Ticket number(s) | `passengers[].ticket_no` |
| Seat / baggage | `passengers[].seat` / `cabin_bag` / `checked_bag` |
| Trip type | `journey_type` |
| Sector(s) / route | `segments[].flights[]` → `dep_iata`/`arr_iata` (+ cities) |
| Flight number / airline | `flights[].flight_no` / `airline` |
| Travel dates & times | `flights[].dep_date`/`dep_time` / `arr_date`/`arr_time` |
| Cabin class | `flights[].cabin` |
| Layovers | `segments[].layovers[]` |
| Itinerary PDF | `pdf_url` |
| **Financials, cost, selling price, margin** | **left blank — user enters** |
| **Hotel / non-flight items** | **not provided — user adds if needed** |

---

## 7. What I need from Pivot OS to connect

Send these back and I'll implement the Producer side (config-driven, gated behind
GitHub Secrets, best-effort, never blocks a run, never logged publicly):

1. **Transport choice** — Option A (webhook) or B (Supabase).
2. **If webhook:** the **endpoint URL** + **auth** — a Bearer token *or* an HMAC signing secret
   (I'll `X-Signature: sha256=…` over the raw body). Tell me which.
   **If Supabase:** project ref + a service role key (I'll insert into `pending_entries`).
3. **Canonical formats** Pivot OS wants: date format (keep `DD Mon YYYY` or convert to ISO?),
   time format, and `flight_no` format (`"VF 200"` vs `"VF200"` vs split code/number).
4. **PNR uniqueness rule** in Pivot OS: `pnr` alone, or `(pnr, portal)`? (decides the match key)
5. **Response contract:** confirm `2xx` = accepted, and how you'll signal "duplicate / already booked"
   (e.g. body `{"status":"duplicate"}`) so I don't treat it as an error.
6. **Supplier vocabulary:** the exact strings Pivot OS uses for suppliers, so I map
   `portal → supplier` cleanly (Alhind / Akbar Travels / aJet / Pegasus → your names).
7. **Retry/idempotency expectations:** confirm upsert-on-`idempotency_key` so my re-sends are safe.

Once I have #1–#2 (and ideally #3–#6), wiring the Producer is a small, isolated addition here.
```
