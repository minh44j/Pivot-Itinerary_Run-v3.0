# Pivot OS ⇄ Itinerary Automation — status & remaining work

Hand this to the **Pivot OS (Consumer)** session. The wire is **verified and live**; below is
what's done and the short list of things left to finish on each side.

## ✅ Verified live (2026-07-19)
The "Pivot OS wire test" (a dry-run from GitHub Actions) returned `HTTP 200` with the echo:
```json
{ "dryRun": true, "status": "pending", "matchedBookingRef": null,
  "row": { "pnr": "TEST0001", "portal": "aJet", "supplier": null,
           "routeSummary": "LHR → CDG", "leadPax": "Test Passenger",
           "firstDepDate": "2026-07-19", "itinStatus": "confirmed",
           "eventType": "itinerary.created" },
  "note": "dry run — nothing persisted" }
```
Confirmed working: auth (Bearer), endpoint, payload shape, ISO dates, `supplier:null` for
direct-airline aJet, and idempotency/dry-run. **The Producer now sends real
`itinerary.created` / `itinerary.revised` events on each 5-minute poll.**

## Done — no action
- Auth, endpoint, JSON contract, ISO departure dates, composite `pnr:portal` match key,
  `financials:null`, supplier mapping (Alhind/Akbar → supplier; aJet/Pegasus → direct airline).
- **PDF access:** `cs@` Drive output folder shared to the pivot-travels.com domain (Viewer).
  Operators open `pdf_url` while signed into their `@pivot-travels.com` account.

## Remaining on Pivot OS (Consumer) — please confirm/finish
1. **"Entries to Be Done" card** renders real inbound rows (badge count, list, sensible sort —
   e.g. soonest `firstDepDate` first).
2. **Click → prefilled booking form:** payload → your form fields; **financials left blank** for
   the operator. Show the `pdf_url` beside the form for verification.
3. **Save flow:** on save → create booking → mark the pending row done → it disappears; and a
   PNR that already matches a saved booking is auto-hidden.
4. **Revised events:** `itinerary.revised` for a still-pending PNR updates the row in place; for an
   already-saved PNR it surfaces the "booking changed — review" flag (never silently vanishes).
   Confirm this is visible in the UI.
5. **Live smoke test:** when the first REAL itinerary syncs, walk one entry end-to-end
   (appears → click → prefill correct → enter financials → save → disappears).

## Decisions we need from Pivot OS
- **Backfill:** do you want existing/past itineraries pushed as a one-off, or **new-only**?
  (Producer currently fires only on newly-processed bookings from go-live forward. If you want
  backfill, we can send a batch through the same endpoint — you already auto-hide saved PNRs.)
- **Any field** you still want that we're not sending? We can add it to the payload.

## Producer (our side) — done; can extend on request
- **Scoped Drive sharing** (per-file grant to a group) instead of the domain folder-share, if you
  prefer that model — just give us the group email.
- **More airlines for revised drafts** — auto-revised itinerary parsing is aJet-only today; other
  carriers (Qatar, Emirates, Turkish, IndiGo, Fly Jinnah…) follow the same pattern as follow-ups.

## Reference
Full field-by-field contract: `PIVOT_OS_INTEGRATION.md` (v1.0 AGREED, now marked VERIFIED LIVE).
