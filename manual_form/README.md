# Manual itinerary form

For the rare ticket that no portal e-mail covers (a partner, or an airline issued by hand). A ticketing
executive types the ticket into a Google Form; the cloud runner builds the **same** PDF through the **same**
QC gate and e-mails it to **the person who submitted** (cc cs@). Nothing goes to a client automatically.

```
Executive ── fills the Form ──▶ Response Sheet ──▶ runner (every poll, ~every few minutes)
                                     ▲                    │ reads new rows, validates, builds PDF
                                     │                    ├─▶ ok      : PDF e-mailed to the submitter (cc cs@) + Drive
                                     └── Runner status ◀──┴─▶ problems : "needs fixing" e-mail listing exactly what to correct
```

## For the executive (one page)

1. Open the **Manual itinerary** form (bookmark it). Sign in with your Pivot account.
2. **The booking:** PNR (required). Agency / CRS reference and *Booked on* only if the ticket shows them —
   leave them empty otherwise (the PDF then says N/A; nothing is invented).
3. **Passenger 1:** title, given name(s), surname, ticket number (digits). Answer **Add another passenger?**
   Yes/No. Up to 4 passengers.
4. **Flight 1:** flight number (`SV 774`), airline name, from/to airport codes **and cities**, departure and
   arrival **date + local time** (24-hour, e.g. `18:05`), cabin class. Optional: terminals, duration,
   baggage as printed (`7kg`, `2 pieces`), one seat box per passenger in the order you entered them.
   Answer **Add another flight?** Up to 6 flights; connecting flights are separate flights, in travel order.
5. Submit. The itinerary PDF arrives in **your** inbox in a few minutes (subject
   `Booking Confirmation — <PNR> (Manual) · …`). Check it against the ticket, then forward it to the client.
6. If something is wrong you get **"Nothing was built — N things to fix"** with each problem in plain words.
   Just submit the form again with the corrections; the earlier submission is ignored.

Rules the form enforces: PNR 5–8 letters/digits · ticket 10–14 digits · airport codes 3 letters · times
24-hour `HH:MM` · seats like `14A` · arrival not before departure. It never guesses a date or a time.

If **the airline gave a different reference for one flight** (two airlines on one ticket), fill *Airline
reference* on that flight only; both references then print on the document.

## For the owner — one-time setup (≈10 minutes)

1. https://script.google.com → **New project** → paste `create_manual_form.gs` → **Run**
   `createManualItineraryForm` → approve the permissions → **View → Logs**. It prints the **FORM** link
   (give to the executives), the **SHEET** link, and the **sheet id**. The sheet is shared with
   `cs@pivottmc.com` as Editor automatically.
2. **Workspace Admin → Security → API controls → Domain-wide delegation:** add the scope
   `https://www.googleapis.com/auth/spreadsheets` to the **existing** service-account client id (the one the
   runner already uses). This is separate from the Gmail/Drive scopes on purpose: until it is approved, only
   the manual form is affected — the inbox run is not.
3. **GitHub → Settings → Secrets → Actions:** add `MANUAL_SHEET_ID` (the sheet id) and, optionally,
   `MANUAL_FORM_URL` (the form link; it is added to the "needs fixing" e-mails).
4. Submit one test booking. The sheet's **Runner status** column (created by the runner) shows
   `PROCESSING` → `DONE …`, or `REJECTED …` / `ERROR …`.

Until `MANUAL_SHEET_ID` is set the feature is completely inert.

## How it behaves (so nothing surprises you)

* **No duplicates:** a row is picked up only while *Runner status* is empty, and is marked `PROCESSING`
  **before** building. A crash can leave a row at `PROCESSING` (it is not retried) — resubmit if so.
* **At most 10 rows per run.**
* **Privacy:** passenger data lives only in the Workspace sheet and the e-mails. The public Action log prints
  counts only (`"manual_form": {"built": 1, "rejected": 0, "errors": 0}`).
* **Revision stamp** works as usual: submitting the same booking again prints *Revision 2* on the PDF.
* **Editing a submitted row in the sheet does nothing** — the runner reads each row once. Submit again.
* **Limits:** 4 passengers, 6 flights; baggage is per flight (the same for everyone on that flight).
  A booking with more can be entered as two submissions or built by hand.
* **Questions can't be renamed** in the Form: the runner reads columns by title
  (`tests/test_manual_sheet.py` checks the titles match this script).
