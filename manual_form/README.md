# Manual itinerary — Google Form

For the rare ticket no portal e-mail covers. An executive opens the **Form**, fills it from the ticket and
submits; within a few minutes the finished PDF is in **their inbox** (cc cs@). Nothing goes to a client.

```
open the Form ─▶ fill ─▶ Submit ─▶ runner (every poll, a few minutes) ─▶ PDF e-mailed to YOU (cc cs@)
                                         └─ something wrong? an e-mail lists exactly what to fix; submit the form again
```

## For the executive
1. Open the form link (bookmark it). It knows who you are — the PDF comes to your own e-mail.
2. **Booking:** PNR (required); agency/CRS reference and *Booked on* only if the ticket shows them.
3. **Passengers** (up to 4, one page each — answer *Add another passenger?*): title, given name(s), surname,
   ticket number typed as `070-6021922265` (3 digits, a dash, the rest — the dash keeps Google from dropping a leading 0).
4. **Flights** (up to 6, travel order; a connection is its own flight — answer *Add another flight?*): flight number
   `SV 774`, airline, airport codes **and cities**, departure/arrival date and **local** 24-hour time (`18:05`), cabin.
   Optional: terminals, duration, baggage as printed, a seat box per passenger. Two airlines on one ticket? Put the
   second airline's own reference in **Airline reference** on that flight.
5. Submit. Check the PDF against the ticket, then forward it.

Nothing is guessed: an unreadable date/time/code is refused with an e-mail saying what to fix (submit again). An
empty *Booked on* prints N/A. The Form accepts people signed in to the Pivot Workspace only.

## One-time setup (owner, ~5 min)
Already done: the Sheets permission (Domain-wide delegation), the Sheets API, and the GitHub secret `MANUAL_SHEET_ID`.
1. Signed in as **cs@pivottmc.com**, open <https://script.google.com> → **New project**, paste all of
   `manual_form/create_manual_form.gs`, **Save**.
2. Choose `createManualItineraryForm` in the toolbar → **Run** → approve the permissions (Forms, Sheets).
3. **Execution log** shows the **FORM** links. Give the first one to the executives.
4. Optional: add the form link as GitHub secret `MANUAL_FORM_URL` so the "needs fixing" e-mail has an *Open the form* button.

The Form writes its answers to a **Form responses** tab of the *Pivot — Manual itinerary* sheet — the runner reads that tab.
(The older typed-in-the-sheet entry, the **New booking** tab with BUILD NOW, still works too.)

## How it behaves
* **Claim first:** each answer row gets `Building…` before anything is built, so a crash cannot e-mail a PDF twice;
  the row then reads `DONE …` or `NOT BUILT — <reasons>` (column **Runner status**). A refused row is final — resubmit.
* **PDF goes only to a Pivot address** (`pivottmc.com` / `pivot-travels.com`) — it holds passenger data.
* **Privacy:** passenger data stays in Workspace (the sheet, e-mails). The public Action log prints counts only.
* **Revision stamp:** building the same booking again prints *Revision 2*.
* **History** tab: one line per attempt. **Limits:** 4 passengers, 6 flights; baggage is per flight.
* Changing a question title breaks the runner's reading: titles are a contract with `manual_sheet.py` (a test checks them).
