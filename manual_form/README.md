# Manual itinerary sheet

For the rare ticket that no portal e-mail covers (a partner, or an airline issued by hand). A ticketing
executive types it into **one Google Sheet** and chooses **BUILD NOW**; the cloud runner builds the **same**
PDF through the **same** QC gate and e-mails it to **that person** (cc cs@). Nothing goes to a client.

```
type the ticket ─▶ choose BUILD NOW ─▶ runner (every poll, a few minutes) ─▶ PDF e-mailed to YOU (cc cs@)
        ▲                                         │                         sheet says DONE and clears itself
        └──── fix it in place ◀── "NOT BUILT: …" ◀┘  (and an e-mail listing exactly what to fix)
```

## For the executive (half a page)

Open **Pivot — Manual itinerary** → tab **New booking** (bookmark it). Fill the cream cells from the ticket:

1. **The booking:** PNR, and **your e-mail** (B9 — where the PDF goes; must be a Pivot address). Agency/CRS ref
   and *Booked on* only if the ticket shows them — otherwise leave empty (the PDF then says N/A).
2. **Passengers** (up to 4): title (dropdown), given name(s), surname, ticket number (digits).
3. **Flights** (up to 6, in travel order; a connection is its own flight): flight number `SV 774`, airline,
   airport codes **and cities**, departure/arrival date + **local** time (24-hour `18:05`), cabin (dropdown).
   Optional: terminals, duration, baggage as printed, one seat box per passenger.
4. Choose **BUILD NOW** in B28. Within a few minutes **What happened** (B29) says **DONE**, the PDF is in your
   inbox, and the sheet clears for the next booking. Check the PDF against the ticket, then forward it.

If something is wrong, **nothing is built**: B29 and an e-mail list each problem in plain words
("Flight 2: missing arrival time"). Your typing stays — fix it and choose BUILD NOW again.

The sheet holds **one booking at a time** — wait for DONE before typing the next. Do not rename tabs or move
cells (the runner reads fixed positions). Type what is printed: nothing is guessed, an unreadable date/time is
refused, and an empty *Booked on* prints N/A. Two airlines on one ticket? Put the second airline's own
reference in **Airline ref.** on that flight; both references then print.

## One-time setup for the owner

The sheet already exists and is owned by cs@ (the mailbox the runner impersonates), so nothing needs sharing
with the runner. What remains:

1. **Workspace Admin → Security → API controls → Domain-wide delegation:** add the scope
   `https://www.googleapis.com/auth/spreadsheets` to the **existing** service-account client id. (Kept separate
   from the Gmail/Drive scopes on purpose: until it is approved only this feature is affected — the inbox run is not.)
2. **GitHub → Settings → Secrets → Actions:** add **`MANUAL_SHEET_ID`** = the id of the sheet (the text between
   `/d/` and `/edit` in its URL).
3. **Share the sheet** with each executive (Editor).
4. Do one test booking and watch B29 and the **History** tab.

Until `MANUAL_SHEET_ID` is set the feature is completely inert.

## How it behaves

* **Claim first:** choosing BUILD NOW is cleared the moment the runner picks it up (B29 shows *Building…*), so a
  crash can never produce a duplicate PDF; if it died mid-way B29 stays at *Building…* — choose BUILD NOW again.
* **PDF goes only to a Pivot address** (`pivottmc.com` / `pivot-travels.com`) — it contains passenger data.
* **Privacy:** passenger data lives only in the Workspace sheet and the e-mails. The public Action log prints
  counts only (`"manual_form": {"built": 1, "rejected": 0, "errors": 0}`).
* **Revision stamp:** building the same booking again prints *Revision 2*.
* **History** tab: one line per attempt (time, PNR, result, recipient).
* **Limits:** 4 passengers, 6 flights; baggage is per flight (same for everyone on it). A larger booking can be
  entered as two bookings.
* **Regenerating the sheet** (layout change): `python tools/build_manual_sheet.py out.xlsx` builds it from the
  same constants the runner reads (`manual_sheet.py`), so they cannot drift.
