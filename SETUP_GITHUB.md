# Pivot Itinerary Automation — Cloud (GitHub Actions) Setup

True cloud automation, **completely free**, producing the **exact Playwright
PDF**. Runs on GitHub's servers on a schedule — your computer can be off.

- ✅ Exact design (runs your real `generate_itinerary_v3.py` + Chromium)
- ✅ Free (GitHub Actions free tier; never bills — it pauses if you exceed quota)
- ✅ `cs@` reads/searches with `gmail.readonly` only — no message is ever modified,
  replied to, forwarded, or deleted
- ✅ `cs@` ALSO self-emails the finished PDF (`gmail.send`, scoped to that one
  action only) — approved 2026-06-08 so the confirmation "arrives in gmail inbox"
- ⚠️ Polling, not instant push (every ~15 min; cron min is 5 min, can be delayed under load)

---

## How it works

```
GitHub Actions (cron, every 15 min)
  → Gmail API search (cs@, 4 portals)         [read-only search]
  → de-dupe vs processed_ids.json
  → extract per portal  (extractors.py)
  → QC gate  (flag, don't guess)
  → render EXACT PDF  (generate_itinerary_v3.py + Chromium)
  → upload to Google Drive folder              [archive]
  → cs@ emails the PDF to itself                [gmail.send, scoped]
  → commit processed_ids.json back to the repo
```

> **Why self-email is safe:** the service account's `gmail.send` grant is used
> for exactly one thing in this codebase — `email_pdf()` composing and sending
> the finished booking-confirmation PDF from `cs@` to `cs@` (or `NOTIFY_TO` if
> you set a different recipient). It never replies to, forwards, or modifies an
> existing thread. Reading/searching the inbox remains on `gmail.readonly`.

---

## Files in this folder

| File | Purpose |
|---|---|
| `main.py` | Cloud runner: auth, Gmail/Drive, QC, render, deliver, log. |
| `extractors.py` | Per-portal parsers + journey/layover/QC logic. **Validate before trusting.** |
| `generate_itinerary_v3.py` | Your exact Playwright PDF generator (unchanged). |
| `logo.png` | Brand logo embedded by the generator. |
| `requirements.txt` | Python deps. |
| `.github/workflows/poll.yml` | The schedule + job. |
| `tools/test_extractor.py` | Validate a portal against a real email. |
| `processed_ids.json` | De-dupe log (message ids only — no passenger names). |

---

## One-time setup (~25 min)

### 1. Create a Google Cloud project + service account
1. <https://console.cloud.google.com> → create a project (e.g. *Pivot Automation*).
2. **APIs & Services → Enable APIs**: enable **Gmail API** and **Google Drive API**.
3. **IAM & Admin → Service Accounts → Create**: name it `pivot-bot`. Create.
4. Open the service account → **Keys → Add key → JSON**. Download the JSON file.
5. Open the service account **Details** and copy its **Unique ID** (a long number) — needed next.

### 2. Authorize domain-wide delegation (Workspace admin)
Because `cs@pivot-travels.com` is Google Workspace, the service account must be
allowed to impersonate it.
1. <https://admin.google.com> → **Security → Access and data control → API controls → Domain-wide delegation → Add new**.
2. **Client ID** = the service account Unique ID from step 1.5.
3. **OAuth scopes** (comma-separated):
   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/drive
   ```
   `gmail.send` is included **only** so `cs@` can self-email the finished PDF —
   the code never uses it to reply, forward, or touch existing messages.
4. Authorize. (This grants read-only mail search + send (self-email only) + Drive,
   for impersonation of `cs@` only.)

### 3. Create the Drive output folder
1. In Google Drive (as `cs@` or shared with it), create a folder, e.g.
   **Pivot AI - Confirmations**.
2. Open it and copy the **folder ID** from the URL
   (`drive.google.com/drive/folders/<THIS_ID>`).

### 4. Create the GitHub repo
1. Create a **private** repo (private keeps passenger data out of public view).
2. Upload everything in this folder (keep the `.github/workflows/` path intact).

### 5. Add repository secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `GOOGLE_SA_JSON` | paste the **entire** service-account JSON file contents |
| `IMPERSONATE_USER` | `cs@pivot-travels.com` (also the default self-email recipient) |
| `DRIVE_OUTPUT_FOLDER` | the Drive folder ID from step 3 |
| `AKBAR_FOLDER_NAME` | `Pivot AI - Ticket PDFs` (only if you use Akbar) |
| `NOTIFY_TO` | only set this if you want the PDF emailed somewhere OTHER than `cs@` (optional — defaults to self-email) |
| `SEARCH_WINDOW` | `newer_than:2d` (optional) |

No SMTP credentials needed — delivery now goes through the Gmail API using the
same impersonated `cs@` session that reads the inbox (scoped `gmail.send`).

### 6. Validate extractors against REAL emails
**Status:** Alhind, aJet, and Pegasus parsers are hardened and verified against
**23 real inbox bookings (2026-06-09): 23/23 PASS.** Alhind now parses the email
**HTML tables by cell** (more reliable than the attached PDF); Pegasus handles
both simple and connecting layouts; journey type is ONE-WAY/ROUND TRIP only;
baggage is captured raw and normalised by the generator; RETURN detection,
layovers, overnight `(+1)`, and identifiers all confirmed. **Akbar** is now also
validated against a real Drive-PDF sample (2026-06-09): a connecting round trip
(JED→DEL→GOP / GOP→BOM→JED) parsed correctly — refs, 2 passengers, baggage,
ONWARD/RETURN grouping, layovers (DEL 2H20M / BOM 1H30M), and the `(+1)` final
arrival. **All four portals: 24/24 real bookings PASS.**

Re-validate any portal any time (e.g. if a sender changes their template):
```bash
pip install -r requirements.txt
export GOOGLE_SA_JSON="$(cat your-sa.json)"
export IMPERSONATE_USER="cs@pivot-travels.com"
python tools/test_extractor.py Pegasus      # then aJet, Alhind, "Akbar Travels"
```
Confirm the printed JSON has the right PNR, names, segments, times, and `QC: PASS`.
Adjust the regex in `extractors.py` until correct **for each portal**. The QC gate
fails safe — an incomplete parse is flagged, not shipped as a wrong PDF.

### 7. First run + go live
1. Repo → **Actions** tab → enable workflows if prompted.
2. Open **Pivot Itinerary Poll → Run workflow** (manual) to test.
3. Check: PDF appears in the Drive folder AND lands back in the `cs@` inbox
   (self-email) — or `NOTIFY_TO` if you set one.
4. After that, the 15-minute cron runs automatically. Done — hands-off.

---

## Free-minute budget

Private repos get **2,000 Action-minutes/month** free. A typical no-op run is
short, but Playwright install adds time. At **every 15 min** you may approach the
cap in a busy month. Options if you do:
- Widen to `*/20` or `*/30` in `poll.yml`.
- Or make the repo **public** for unlimited minutes — **only if** you keep PDFs
  out of the repo (this setup already does: PDFs go to Drive/email, `.gitignore`
  blocks `*.pdf`, and the committed log holds message ids only, no names).

GitHub never charges the free tier — if you hit the cap, Actions simply pause
until the next month. No payment method, no surprise bill.

---

## Compliance notes (matches your project rules)

- **Reading/searching `cs@` is read-only:** `gmail.readonly` scope. No existing
  message is ever modified, replied to, forwarded, or deleted.
- **Self-email is a deliberate, narrow exception (approved 2026-06-08):** `cs@`
  also holds `gmail.send`, used by exactly one function (`email_pdf()`) to
  compose and send a brand-new message — the finished PDF — from `cs@` to
  itself (or `NOTIFY_TO`). This is the ONLY send action the code performs.
- **No external rendering service:** Chromium runs inside the GitHub runner;
  passenger data never goes to a third-party PDF API.
- **One booking = one PDF; missing values = N/A; identifiers verbatim.**
- **Flag, don't guess:** QC failures are reported in the run log, not shipped.
