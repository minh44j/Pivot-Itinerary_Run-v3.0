# Itinerary Automation (Producer) → Pivot OS (Consumer) — reply

The Producer is **implemented to the v1.0 contract and merged** (see `PIVOT_OS_INTEGRATION.md`
§ "STATUS: v1.0 AGREED"). Before we flip it on and test end-to-end, here's what I need from your side.

> **Note:** the shared Bearer secret value is **not** in this file on purpose. Minhaj holds it and
> will set it on both sides via secrets — never commit it or paste it into a repo/PR/chat log.

## A. Go-live blockers
1. **Endpoint** — confirm `POST https://<host>/api/itinerary-sync` is **deployed and live**; give the
   exact production host.
2. **Shared secret** — confirm `ITINERARY_SYNC_SECRET` is set on your side. Minhaj sets the identical
   value here as `PIVOT_OS_SYNC_SECRET`. (A strong value has been generated — Minhaj will share it.)

## B. Safe first test
3. How do you want the **first end-to-end test** done without polluting real bookings? Pick one:
   (a) accept a sentinel PNR like `TEST0001` you can delete, (b) a `dry_run` flag/header that
   validates + echoes but doesn't persist, or (c) a staging deploy.
4. On accept, can you **echo back** what you stored (or a row id) so I can confirm the field mapping?

## C. Contract details to confirm
5. **Response bodies:** confirm `200 {"status":"duplicate"}` for already-booked, and the **`400`
   validation** body shape (field-level errors?) so my failure log is useful.
6. **Revised events:** confirm handling of `event:"itinerary.revised"` — update the pending payload
   if still pending; flag the **saved** booking as "changed / review" if already booked. Built now, or
   hold revised pushes for v1.1?
7. **Required fields / tolerances:** anything you reject as missing/blank? My payload may carry empty
   strings and nulls — e.g. no `seat`, no `terminal`, blank `dep_airport`, `crs_ref: null`, a single
   passenger. Confirm those are accepted.

## D. Practical — the PDF link (please read)
8. `pdf_url` is a **Google Drive** link owned by the `cs@` account. Can your operators open it as-is
   (are they in that Google Workspace, or is the file shared with them)? If not, we need a plan —
   share the Drive file with specific accounts, or I push a different link. **Avoid** "anyone-with-link
   public" — it's a passenger's PII. Tell me how operators will **view the PDF beside the form**.

## E. Scope
9. **Backfill vs new-only:** the Producer fires only on newly-processed bookings from go-live forward.
   Do you also want **existing/past** itineraries pushed (a separate one-off), or new-only?

Once **A + B** are settled we can run a live test with a single booking and watch it land in
"Entries to Be Done."
