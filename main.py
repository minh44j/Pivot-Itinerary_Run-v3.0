#!/usr/bin/env python3
"""
Pivot Itinerary Automation — cloud runner (GitHub Actions).
=========================================================================
Runs on a schedule. For each NEW qualifying ticket email:
  scan Gmail -> extract -> QC gate -> render EXACT Playwright PDF
  (generate_itinerary_v3.py) -> upload to Drive -> email PDF back to cs@ -> log.

Reading/searching cs@ uses gmail.readonly (no message is ever modified, replied
to, forwarded, or deleted). Outbound delivery is a deliberate, narrowly-scoped
exception approved by Minh on 2026-06-08: the SAME impersonated cs@ account also
holds gmail.send, used SOLELY to email the finished booking-confirmation PDF back
to itself (self-email, "arrives in gmail inbox"). No other send/reply/forward
action is ever taken.

Auth: a Google service account with domain-wide delegation, impersonating
IMPERSONATE_USER (cs@pivot-travels.com). See SETUP_GITHUB.md.

Environment variables (set as GitHub secrets):
  GOOGLE_SA_JSON       full service-account JSON (string)
  IMPERSONATE_USER     cs@pivot-travels.com (default self-email recipient too)
  DRIVE_OUTPUT_FOLDER  Drive folder ID for output PDFs
  AKBAR_FOLDER_NAME    e.g. "Pivot AI - Ticket PDFs"   (optional)
  NOTIFY_TO            override recipient (defaults to IMPERSONATE_USER) (optional)
  SEARCH_WINDOW        Gmail window, default "newer_than:2d" (optional)
"""
import os
import io
import json
import base64
import traceback
from email.message import EmailMessage
from datetime import datetime, timezone

import google.auth
from google.auth import iam
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

import extractors
from generate_itinerary_v3 import build_pdf

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]
LOG_FILE = "processed_ids.json"
# Separate dedup log for the disruption watch (cancellation / schedule-change
# alerts). Same public-safe convention as processed_ids.json: message_id only.
DISRUPTION_LOG_FILE = "disruption_ids.json"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROJECT_DIR, "out")
# Transient 5xx / rate-limit responses from Google get retried with exponential
# backoff by googleapiclient when num_retries is passed to each API execute call.
API_RETRIES = 4
# Static India health-declaration guide, appended as extra page(s) to the
# itinerary PDF when a booking is an international arrival into India
# (see extractors.india_arrival).
AIR_SUVIDHA_PDF = os.path.join(PROJECT_DIR, "air_suvidha", "air_suvidha_guide.pdf")


def _append_air_suvidha(pdf_path):
    """Append the Air Suvidha guide's page(s) onto the itinerary PDF IN PLACE,
    so the single file (Drive + email) carries both. No-op if the guide asset
    is missing (fails safe — the itinerary still ships on its own)."""
    if not os.path.exists(AIR_SUVIDHA_PDF):
        return
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    for page in PdfReader(pdf_path).pages:
        writer.add_page(page)
    for page in PdfReader(AIR_SUVIDHA_PDF).pages:
        writer.add_page(page)
    tmp_path = pdf_path + ".tmp"
    with open(tmp_path, "wb") as f:
        writer.write(f)
    os.replace(tmp_path, pdf_path)


# ── auth ──────────────────────────────────────────────────────────────────
# Two supported modes (both impersonate cs@ via domain-wide delegation):
#   1. KEYLESS (Workload Identity Federation) — preferred. No downloadable key.
#      GitHub Actions gets ADC via google-github-actions/auth; we then mint a
#      DWD token for cs@ using the IAM Credentials API (signBlob), so the service
#      account never needs an exported JSON key. Requires env SERVICE_ACCOUNT_EMAIL
#      and the SA holding roles/iam.serviceAccountTokenCreator on itself.
#   2. KEY (fallback) — set env GOOGLE_SA_JSON to the full service-account JSON.
def _creds_for(subject, scopes):
    """Build delegated credentials impersonating `subject` (a domain user)."""
    if os.environ.get("GOOGLE_SA_JSON"):                       # exported key
        info = json.loads(os.environ["GOOGLE_SA_JSON"])
        return service_account.Credentials.from_service_account_info(
            info, scopes=scopes, subject=subject)
    # keyless WIF: sign via IAM Credentials API (no private key)
    sa_email = os.environ["SERVICE_ACCOUNT_EMAIL"]
    source_creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    signer = iam.Signer(Request(), source_creds, sa_email)
    return service_account.Credentials(
        signer=signer, service_account_email=sa_email,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=scopes, subject=subject)


def _services():
    creds = _creds_for(os.environ["IMPERSONATE_USER"], SCOPES)   # reads inbox as cs@
    return build("gmail", "v1", credentials=creds, cache_discovery=False), \
        build("drive", "v3", credentials=creds, cache_discovery=False)


def _sender_gmail():
    """Gmail service that SENDS the confirmation. Defaults to cs@ (IMPERSONATE_USER)
    unless SENDER_USER is set to another address in the same domain."""
    sender = os.environ.get("SENDER_USER") or os.environ["IMPERSONATE_USER"]
    creds = _creds_for(sender, ["https://www.googleapis.com/auth/gmail.send"])
    return build("gmail", "v1", credentials=creds, cache_discovery=False), sender


# ── processed log (message ids only — no passenger PII in the repo) ────────
def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            return json.load(f)
    return {"processed": []}


def save_log(log):
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def processed_ids(log):
    return {e["message_id"] for e in log["processed"]}


# ── disruption-watch log (message ids only — same public-safe convention) ──
def load_disruption_log():
    if os.path.exists(DISRUPTION_LOG_FILE):
        with open(DISRUPTION_LOG_FILE) as f:
            return json.load(f)
    return {"alerted": []}


def save_disruption_log(log):
    with open(DISRUPTION_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


# ── gmail helpers ──────────────────────────────────────────────────────────
def _header(msg, name):
    for h in msg["payload"].get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _html_to_text(h):
    """HTML -> text, mapping table cells/rows/blocks to newlines so the parsers
    see fields on separate lines (matches the format the extractors were tuned on)."""
    import re as _re
    import html as _html
    h = _re.sub(r"(?is)<(script|style|head).*?</\1>", " ", h)
    h = _re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = _re.sub(r"(?i)</(td|th|tr|div|p|li|h[1-6]|table)\s*>", "\n", h)
    h = _re.sub(r"<[^>]+>", " ", h)
    h = _html.unescape(h)
    h = _re.sub(r"[ \t\xa0]+", " ", h)
    return "\n".join(ln.strip() for ln in h.splitlines() if ln.strip())


def _plain_body(msg):
    """Return the RAW body for the extractors (HTML preferred). The extractors
    flatten or cell-parse internally — Alhind needs the HTML table structure,
    aJet/Pegasus flatten it themselves. Some portals (e.g. Alhind) put the HTML
    in the text/plain part, so we treat anything HTML-ish as HTML."""
    plain, html_raw = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime in ("text/plain", "text/html"):
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
            (plain if mime == "text/plain" else html_raw).append(decoded)
        for p in part.get("parts", []) or []:
            walk(p)

    walk(msg["payload"])
    html_join = "\n".join(html_raw).strip()
    plain_join = "\n".join(plain).strip()
    # Prefer real HTML; fall back to a plain part only if it carries HTML too.
    if html_join:
        return html_join
    return plain_join


def _email_date_ddmon(msg):
    from datetime import datetime, timezone
    epoch = int(msg["internalDate"]) / 1000
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%d %b %Y")


def search_messages(gmail, portal, window):
    q = f'from:({portal["from"]}) subject:("{portal["subject"]}") {window}'
    res = gmail.users().messages().list(userId="me", q=q, maxResults=25).execute(num_retries=API_RETRIES)
    return [m["id"] for m in res.get("messages", [])]


# ── Akbar PDF -> text ────────────────────────────────────────────────────
# ROOT CAUSE (found 2026-06-18): the "Pivot AI - Ticket PDFs" Drive folder is
# fed by a separate, external upload pipeline that silently stopped on
# 2026-06-06 (12 days stale at time of discovery) -- every Akbar Drive lookup
# after that date correctly found no safely-matched file. This was not a bug
# in the matching window; it was a dead upstream pipeline outside this repo.
#
# FIX: Akbar's "Booking Success" emails carry the ticket PDF as a direct
# Gmail attachment (filename "TKT_<ref>.pdf") -- confirmed by inspecting 3
# live emails on 2026-06-18. This is now the PRIMARY source: it travels with
# the email itself, so it can never be stale, and needs no extra scope (still
# plain gmail.readonly). The old Drive-folder lookup is kept only as a
# fallback for the rare case an Akbar email arrives with no attachment.
def akbar_attachment_text(gmail, msg):
    import pdfplumber

    def find_pdf_attachment_id(part):
        filename = (part.get("filename") or "")
        mime = part.get("mimeType") or ""
        att_id = part.get("body", {}).get("attachmentId")
        if att_id and (mime == "application/pdf" or filename.lower().endswith(".pdf")):
            return att_id
        for p in part.get("parts", []) or []:
            found = find_pdf_attachment_id(p)
            if found:
                return found
        return None

    att_id = find_pdf_attachment_id(msg["payload"])
    if not att_id:
        return ""   # no attachment on this email — caller falls back to Drive
    raw = gmail.users().messages().attachments().get(
        userId="me", messageId=msg["id"], id=att_id).execute(num_retries=API_RETRIES)
    data = base64.urlsafe_b64decode(raw["data"])
    text = ""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
    return text


# ── Akbar Drive PDF -> text (FALLBACK ONLY — see akbar_attachment_text) ────
def akbar_pdf_text(drive, msg_date_str, msg_epoch=None):
    import pdfplumber
    folder_name = os.environ.get("AKBAR_FOLDER_NAME", "Pivot AI - Ticket PDFs")
    fres = drive.files().list(q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                              fields="files(id)").execute(num_retries=API_RETRIES).get("files", [])
    if not fres:
        return ""
    folder_id = fres[0]["id"]
    q = f"'{folder_id}' in parents and name contains 'AKBAR_' and mimeType='application/pdf'"
    files = drive.files().list(q=q, fields="files(id,name,modifiedTime)",
                               orderBy="modifiedTime desc").execute(num_retries=API_RETRIES).get("files", [])
    if not files:
        return ""
    # SAFETY: never silently fall back to "whatever's newest in the whole
    # folder" — that can be an old/sample/unrelated PDF and would attach a
    # STALE booking's PNR/passengers to a brand-new email (the <ref>
    # incident). Only accept a file whose name contains the email's date
    # string (±1 day, for timezone drift) or one modified within 48h of the
    # email's own arrival. If neither matches, return "" so qc_check flags
    # the booking for manual review instead of mis-attributing data.
    from datetime import timedelta
    date_candidates = {msg_date_str}
    if msg_epoch is not None:
        base = datetime.fromtimestamp(msg_epoch, timezone.utc)
        date_candidates.add((base - timedelta(days=1)).strftime("%Y-%m-%d"))
        date_candidates.add((base + timedelta(days=1)).strftime("%Y-%m-%d"))
    exact = [f for f in files if any(c in f["name"] for c in date_candidates)]
    pick = exact[0] if exact else None
    if pick is None and msg_epoch is not None:
        def _age_seconds(f):
            ts = f["modifiedTime"]
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in ts else "%Y-%m-%dT%H:%M:%SZ"
            mt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return abs((mt - datetime.fromtimestamp(msg_epoch, timezone.utc)).total_seconds())
        close = [f for f in files if _age_seconds(f) <= 48 * 3600]   # within 48h of the email
        pick = min(close, key=_age_seconds) if close else None
    if pick is None:
        return ""   # no safely-matched file — do NOT guess
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=pick["id"]))
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    text = ""
    with pdfplumber.open(buf) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
    return text


# ── Drive upload ───────────────────────────────────────────────────────────
def upload_to_drive(drive, pdf_path, date_sub):
    parent = os.environ["DRIVE_OUTPUT_FOLDER"]
    # find/create date subfolder
    q = (f"'{parent}' in parents and name='{date_sub}' "
         f"and mimeType='application/vnd.google-apps.folder'")
    found = drive.files().list(q=q, fields="files(id)").execute(num_retries=API_RETRIES).get("files", [])
    sub_id = found[0]["id"] if found else drive.files().create(
        body={"name": date_sub, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]},
        fields="id").execute(num_retries=API_RETRIES)["id"]
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    f = drive.files().create(
        body={"name": os.path.basename(pdf_path), "parents": [sub_id]},
        media_body=media, fields="id,webViewLink").execute(num_retries=API_RETRIES)
    return f.get("webViewLink", "")


# ── email delivery: cs@ self-emails the finished PDF (gmail.send, scoped) ──
# Approved 2026-06-08: cs@ keeps gmail.readonly for all reading/searching (no
# message is ever touched, replied to, forwarded, or deleted). It additionally
# holds gmail.send for exactly ONE purpose — emailing the finished PDF back to
# itself so the confirmation "arrives in gmail inbox" alongside the source email.
def _b(v):
    """Body-safe field: blank/None -> 'N/A' (same convention as the PDF)."""
    v = (str(v).strip() if v is not None else "")
    return v or "N/A"


def _build_email_body(data, source_ref=""):
    """Full-detail internal summary for the cs@ inbox. Reads ONLY fields already
    present on `data` (no extra extraction). Every missing value renders 'N/A'.
    The confirmation PDF itself is attached; this body is the at-a-glance copy."""
    lines = []
    lines.append(f"PNR: {_b(data.get('pnr'))}")
    booking_ref = (data.get("booking_ref") or "").strip()
    if booking_ref and booking_ref != (data.get("pnr") or "").strip():
        lines.append(f"Booking Ref: {booking_ref}")
    crs_ref = (data.get("crs_ref") or "").strip()
    if crs_ref and crs_ref != (data.get("pnr") or "").strip():
        lines.append(f"CRS Ref: {crs_ref}")
    lines.append(f"Portal: {_b(data.get('portal'))}")
    lines.append(f"Journey: {_b(data.get('journey_type'))}")
    lines.append(f"Booked On: {_b(data.get('booked_on'))}")

    passengers = data.get("passengers", [])
    lines.append("")
    lines.append(f"Passengers ({len(passengers)}):")
    for p in passengers:
        lines.append(f"  • {_b(p.get('name'))}  — Ticket: {_b(p.get('ticket_no'))} | "
                     f"Seat: {_b(p.get('seat'))}")

    lines.append("")
    lines.append("Itinerary:")
    for seg in data.get("segments", []):
        flights = seg.get("flights", [])
        if not flights:
            continue
        stype = seg.get("type", "FLIGHT")
        first, last = flights[0], flights[-1]
        lines.append(f"  {stype}  {_b(first.get('dep_iata'))} → {_b(last.get('arr_iata'))}   "
                     f"{_b(first.get('dep_date'))}")
        for f in flights:
            extra = "   ".join(x for x in [f"({f.get('duration')})" if f.get('duration') else "",
                                           (f.get("cabin") or "")] if x)
            lines.append(f"    {_b(f.get('flight_no'))}   {_b(f.get('dep_time'))} → "
                         f"{_b(f.get('arr_time'))}   {extra}".rstrip())

    if extractors.india_arrival(data):
        lines.append("")
        lines.append("India arrival — the Air Suvidha 2.0 health-declaration guide is "
                     "included as extra page(s) in the attached PDF.")
    if source_ref:
        lines.append("")
        lines.append(f"Source Ref: {source_ref}")
    lines.append("")
    lines.append("PDF attached. (Automated — PIVOT AUTOMATED ITINERARY)")
    return "\n".join(lines)


def email_pdf(send_gmail, sender, pdf_path, data, source_ref=""):
    to = os.environ.get("NOTIFY_TO") or sender             # default recipient = sender
    m = EmailMessage()
    m["Subject"] = f"Booking Confirmation — {data.get('pnr')} ({data.get('portal')})"
    m["From"] = sender                                     # SENDER_USER or cs@
    m["To"] = to
    m.set_content(_build_email_body(data, source_ref))
    # pdf_path is a single file by this point — main() already merged the Air
    # Suvidha guide's page(s) into it (via _append_air_suvidha) for India-arrival
    # bookings, so there is only ever one attachment here.
    with open(pdf_path, "rb") as f:
        m.add_attachment(f.read(), maintype="application", subtype="pdf",
                         filename=os.path.basename(pdf_path))
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")
    send_gmail.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=API_RETRIES)
    return True


# ── manual-review notifications: private digest to Minh (inbox only) ────────
# When a booking fails qc_check (or its email failed), it must NOT vanish into a
# bare count in the public Action log — someone has to know to process it by hand.
# This sends ONE private digest per run to the cs@ inbox. Because it stays in the
# inbox (never the public repo/log), it can safely carry the subject + message_id
# needed to locate and fix each booking.
def email_flags(send_gmail, sender, flagged):
    if not flagged:
        return False
    to = os.environ.get("NOTIFY_TO") or sender
    lines = [f"{len(flagged)} booking(s) need manual review:", ""]
    for f in flagged:
        lines.append(f"• Portal:     {f.get('portal')}")
        lines.append(f"  Reason:     {f.get('reason')}")
        if f.get("subject"):
            lines.append(f"  Subject:    {f.get('subject')}")
        lines.append(f"  Source Ref: {f.get('id')}")
        lines.append("")
    lines.append("Find each in the cs@ inbox by its Source Ref (Gmail message id) "
                 "and process it manually.")
    lines.append("(Automated — PIVOT AUTOMATED ITINERARY)")
    m = EmailMessage()
    m["Subject"] = f"Itinerary — {len(flagged)} booking(s) need manual review"
    m["From"] = sender
    m["To"] = to
    m.set_content("\n".join(lines))
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")
    send_gmail.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=API_RETRIES)
    return True


# ── disruption watch: catch cancellations / schedule changes ────────────────
# The confirmation flow above only matches NEW ticket confirmations from the 4
# portals. Cancellation and schedule-change emails have different subjects, so
# they were invisible to the automation and kept getting missed. This does a
# READ-ONLY subject-keyword scan of the whole inbox (gmail.readonly — no message
# is opened, replied to, forwarded, or modified) and returns any NEW match not
# yet alerted. main() raises ONE private ACTION-REQUIRED digest to cs@ for them.
def scan_disruptions(gmail, alerted_ids):
    """Return alert dicts for NEW cancellation / schedule-change emails anywhere in
    the mailbox. Gmail's subject query is the coarse net; extractors.disruption_match()
    is the authoritative filter.

    NOT restricted to in:inbox on purpose — real schedule-change emails (e.g. IndiGo
    "Your Revised IndiGo Itinerary") are auto-labelled "Airline Updates" and skip the
    inbox, which is a big part of why they get missed. We exclude our OWN sent mail
    and automation sender (pivot-travels.com) so the alert can never trigger on itself
    or on a cancellation request WE sent to a portal. Window is dedicated + a little
    wider (default 2d) since missing a disruption is worse than reprocessing.

    Never breaks the confirmation run — the caller wraps this in try/except."""
    window = os.environ.get("DISRUPTION_WINDOW") or "newer_than:2d"
    terms = " OR ".join(f'subject:({t})' for t in extractors.DISRUPTION_QUERY_TERMS)
    q = (f"({terms}) {window} -in:sent -in:trash -in:spam -in:drafts "
         f"-from:pivot-travels.com")
    res = gmail.users().messages().list(
        userId="me", q=q, maxResults=50).execute(num_retries=API_RETRIES)
    alerts = []
    for m in res.get("messages", []):
        mid = m["id"]
        if mid in alerted_ids:
            continue
        msg = gmail.users().messages().get(
            userId="me", id=mid, format="metadata",
            metadataHeaders=["Subject", "From", "Date"]).execute(num_retries=API_RETRIES)
        subject = _header(msg, "Subject")
        kw = extractors.disruption_match(subject)   # authoritative — Gmail matches loosely
        if not kw:
            continue
        alerts.append({
            "id": mid,
            "from": _header(msg, "From"),
            "subject": subject,
            "date": _header(msg, "Date"),
            "keyword": kw,
            "snippet": (msg.get("snippet") or "")[:200],
        })
    return alerts


# Alert e-mail is skinned to the Pivot itinerary brand (Model B / dark luxury):
# charcoal->black gradient chrome, gold #c9a84c hairline + accents, feather logo +
# "Pivot Travel Management" wordmark, Cormorant Garamond (display) + Inter (body),
# dark footer. Severity is kept as a small coloured PILL on each card's dark strip
# so urgency still reads at a glance (cancellation=red, schedule change=orange,
# delay=amber). `rank` sorts the most urgent (cancellations) to the top.
_BRAND_GOLD = "#c9a84c"
_BRAND_CHARCOAL_GRAD = "linear-gradient(135deg,#323234 0%,#1e1e20 55%,#0e0e0f 100%)"
_FONT_SERIF = "'Cormorant Garamond',Georgia,'Times New Roman',serif"
_FONT_SANS = "'Inter',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_DISRUPTION_STYLE = {
    "cancellation":    {"label": "CANCELLATION",    "emoji": "🔴", "accent": "#B23A3A", "rank": 0},
    "schedule_change": {"label": "SCHEDULE CHANGE", "emoji": "🟠", "accent": "#C07A2B", "rank": 1},
    "delay":           {"label": "DELAY",           "emoji": "🟡", "accent": "#C99A3A", "rank": 2},
}

_LOGO_DATA_URI = None


def _logo_data_uri():
    """Return the feather logo as an inline data: URI (embedded so it always shows,
    no remote fetch / blocked-image issues). Cached; '' if the asset is missing —
    the header then falls back to the wordmark alone."""
    global _LOGO_DATA_URI
    if _LOGO_DATA_URI is None:
        try:
            with open(os.path.join(PROJECT_DIR, "logo.png"), "rb") as f:
                _LOGO_DATA_URI = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        except Exception:
            _LOGO_DATA_URI = ""
    return _LOGO_DATA_URI


def _disruption_enrich(alerts):
    """Attach the category + its style to each alert and sort most-urgent first."""
    out = []
    for a in alerts:
        cat = extractors.disruption_category(
            a.get("subject", ""), a.get("snippet", ""), a.get("keyword", ""))
        style = _DISRUPTION_STYLE[cat]
        out.append({**a, "category": cat, "style": style})
    out.sort(key=lambda a: a["style"]["rank"])
    return out


def _disruption_text(alerts):
    """Plain-text fallback body (for clients that don't render HTML)."""
    n = len(alerts)
    lines = [f"ACTION REQUIRED — {n} possible cancellation / schedule-change "
             f"email(s) found in the mailbox:", ""]
    for a in alerts:
        st = a["style"]
        lines.append(f"[{st['label']}]  {a.get('from')}")
        lines.append(f"  Subject:    {a.get('subject')}")
        lines.append(f"  Received:   {a.get('date')}")
        if a.get("snippet"):
            lines.append(f"  Preview:    {a['snippet']}")
        lines.append(f"  Source Ref: {a.get('id')}")
        if a.get("revised_pdf"):
            lines.append(f"  >> Auto-draft REVISED itinerary attached "
                         f"({os.path.basename(a['revised_pdf'])}) — VERIFY against the "
                         f"airline email before sending to the client.")
        lines.append("")
    lines.append("Open each in the cs@ inbox (search its Source Ref or subject), confirm")
    lines.append("whether it is a genuine cancellation / schedule change, and forward it to")
    lines.append("the affected client so it is never missed.")
    lines.append("(Automated watch — PIVOT AUTOMATED ITINERARY)")
    return "\n".join(lines)


def _disruption_html(alerts):
    """Structured HTML digest skinned to the Pivot itinerary brand — charcoal/gold
    Model-B header with the feather logo + wordmark, one card per alert with a dark
    segment-style strip carrying a coloured severity pill, and a dark footer. Uses
    tables + inline styles only (Gmail / Outlook / Apple Mail safe)."""
    import html as _html

    def esc(v):
        return _html.escape(str(v).strip()) if v is not None and str(v).strip() else "N/A"

    n = len(alerts)
    logo = _logo_data_uri()
    logo_img = (f'<img src="{logo}" height="34" alt="Pivot" '
                f'style="display:inline-block;border:0;margin:0 0 10px;">' if logo else "")

    def row(k, v):
        return (f'<tr><td style="font-family:{_FONT_SANS};font-size:11px;color:#9a8f77;'
                f'text-transform:uppercase;letter-spacing:.5px;vertical-align:top;'
                f'padding:5px 12px 5px 0;white-space:nowrap;">{k}</td>'
                f'<td style="font-family:{_FONT_SANS};font-size:13px;color:#26241f;'
                f'line-height:1.55;padding:5px 0;">{v}</td></tr>')

    cards = []
    for a in alerts:
        st = a["style"]
        details = "".join([
            row("From",     f'<b>{esc(a.get("from"))}</b>'),
            row("Subject",  esc(a.get("subject"))),
            row("Received", esc(a.get("date"))),
            row("Preview",  f'<span style="color:#5a5344;">{esc(a.get("snippet"))}</span>'),
            row("Ref",      f'<span style="color:#a99f8a;font-family:monospace;font-size:12px;">{esc(a.get("id"))}</span>'),
        ])
        revised_note = ""
        if a.get("revised_pdf"):
            revised_note = (
                f'<div style="margin-top:12px;background:#eaf6ee;border:1px solid #bfe2cb;'
                f'border-radius:8px;padding:9px 12px;font-family:{_FONT_SANS};font-size:12px;color:#1f6b3b;">'
                f'📎 <b>Auto-draft revised itinerary attached</b> '
                f'({esc(os.path.basename(a["revised_pdf"]))}) — verify against the airline '
                f'email, then forward to the client.</div>')
        cards.append(f'''
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 16px;border:1px solid #e7e1d3;border-radius:12px;border-collapse:separate;overflow:hidden;">
        <tr><td style="background:#1e1e20;background:{_BRAND_CHARCOAL_GRAD};padding:11px 16px;">
          <span style="display:inline-block;background:{st['accent']};color:#ffffff;font-family:{_FONT_SANS};font-size:11px;font-weight:700;letter-spacing:1.2px;padding:5px 12px;border-radius:20px;">{st['emoji']}&nbsp; {st['label']}</span>
        </td></tr>
        <tr><td style="background:{_BRAND_GOLD};font-size:2px;line-height:2px;height:2px;">&nbsp;</td></tr>
        <tr><td style="background:#ffffff;padding:14px 18px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{details}</table>
          {revised_note}
        </td></tr>
      </table>''')

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Inter:wght@400;500;600&display=swap');</style>
</head><body style="margin:0;padding:0;background:#eae7e0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eae7e0;padding:22px 0;">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;border-radius:14px;overflow:hidden;background:#f6f4ef;">
        <tr><td style="background:#1e1e20;background:{_BRAND_CHARCOAL_GRAD};padding:26px 24px 20px;text-align:center;">
          {logo_img}
          <div style="font-family:{_FONT_SERIF};font-size:22px;font-weight:400;letter-spacing:.8px;color:#f2efe6;">Pivot Travel Management</div>
          <div style="height:1px;background:{_BRAND_GOLD};line-height:1px;font-size:1px;max-width:170px;margin:15px auto;">&nbsp;</div>
          <div style="font-family:{_FONT_SANS};font-size:15px;font-weight:600;letter-spacing:1.5px;color:{_BRAND_GOLD};">⚠️ ACTION REQUIRED</div>
          <div style="font-family:{_FONT_SANS};font-size:13px;color:#b9b5ab;margin-top:6px;">{n} possible cancellation / schedule-change email(s)</div>
        </td></tr>
        <tr><td style="padding:22px 22px 6px;">
          {''.join(cards)}
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:2px 0 4px;">
            <tr><td style="background:#f7f2e4;border:1px solid #e6dcc0;border-radius:10px;padding:13px 16px;font-family:{_FONT_SANS};font-size:12.5px;color:#4a4436;line-height:1.6;">
              <b style="color:#8a6d1f;">Next step:</b> open each in the cs@ inbox (search its <i>Ref</i> or subject), confirm it is a genuine cancellation / schedule change, then <b>forward it to the affected client</b> so it is never missed.
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="background:#1e1e20;background:{_BRAND_CHARCOAL_GRAD};padding:16px 20px;text-align:center;">
          <div style="height:1px;background:{_BRAND_GOLD};opacity:.6;line-height:1px;font-size:1px;max-width:130px;margin:0 auto 12px;">&nbsp;</div>
          <div style="font-family:{_FONT_SANS};font-size:10px;letter-spacing:1.5px;color:#8f8b81;text-transform:uppercase;">PIVOT AUTOMATED ITINERARY &nbsp;|&nbsp; WWW.PIVOT-TRAVELS.COM</div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>'''


def email_disruptions(send_gmail, sender, alerts):
    """Send ONE private ACTION-REQUIRED digest of possible cancellation /
    schedule-change emails, so they stop getting buried. Colour-coded HTML
    (cancellation=red, schedule change=orange, delay=amber) with a plain-text
    fallback. Inbox-only (like email_flags), so it can safely name the subject +
    message id to locate each."""
    if not alerts:
        return False
    to = os.environ.get("DISRUPTION_NOTIFY_TO") or os.environ.get("NOTIFY_TO") or sender
    enriched = _disruption_enrich(alerts)
    m = EmailMessage()
    m["Subject"] = f"⚠️ ACTION REQUIRED — {len(alerts)} flight cancellation/change alert(s)"
    m["From"] = sender
    m["To"] = to
    m.set_content(_disruption_text(enriched))          # text/plain fallback
    m.add_alternative(_disruption_html(enriched), subtype="html")   # rich HTML
    # Attach any auto-drafted REVISED itinerary PDFs (aJet schedule changes we
    # could rebuild). Best-effort: a bad path never blocks the alert.
    for a in enriched:
        path = a.get("revised_pdf")
        if path and os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    m.add_attachment(f.read(), maintype="application", subtype="pdf",
                                     filename=os.path.basename(path))
            except Exception:
                pass
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")
    send_gmail.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=API_RETRIES)
    return True


# ── Pivot OS sync: push each produced itinerary to "Entries to Be Done" ─────
# Producer side of PIVOT_OS_INTEGRATION.md. Best-effort HTTPS POST (stdlib only,
# no new dependency). INERT until BOTH env vars are set, so it never affects runs
# until Minhaj configures the secret. PII travels only to the configured endpoint
# over TLS with a Bearer token; it is NEVER printed to the public Action log.
#   PIVOT_OS_SYNC_URL     e.g. https://<pivot-os-host>/api/itinerary-sync
#   PIVOT_OS_SYNC_SECRET  shared Bearer secret (== ITINERARY_SYNC_SECRET on their side)
def notify_pivot_os(booking, pdf_url="", event="itinerary.created", source_ref="", dry_run=None):
    """POST one itinerary event to Pivot OS. Returns a short outcome string
    ('ok' | 'duplicate' | 'http-<code>' | 'error'), or None if not configured.
    Never raises — a sync failure must not affect the itinerary run.
    dry_run=True (or env PIVOT_OS_DRY_RUN) adds the X-Dry-Run header so Pivot OS
    validates + echoes the mapping WITHOUT persisting — for a cautious first run."""
    url = os.environ.get("PIVOT_OS_SYNC_URL")
    secret = os.environ.get("PIVOT_OS_SYNC_SECRET")
    if not url or not secret:
        return None
    if dry_run is None:
        dry_run = bool(os.environ.get("PIVOT_OS_DRY_RUN"))
    import urllib.request
    import urllib.error
    payload = extractors.pivot_os_payload(booking, pdf_url, event, source_ref)
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {secret}",
        "Idempotency-Key": payload["idempotency_key"],
    }
    if dry_run:
        headers["X-Dry-Run"] = "1"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            try:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            except Exception:
                data = {}
            if isinstance(data, dict) and data.get("status") == "duplicate":
                return "duplicate"       # PNR already a saved booking — expected, not an error
            code = resp.getcode()
            return "ok" if 200 <= code < 300 else f"http-{code}"
    except urllib.error.HTTPError as e:
        return f"http-{e.code}"          # 400/401/503/500 — retried next run if transient
    except Exception:
        return "error"


# ── one-off backfill: re-send every processed booking to Pivot OS ───────────
# processed_ids.json holds ONLY message ids (privacy), so the backfill rebuilds
# each booking from its source email (fetch → detect portal → re-extract), then
# POSTs itinerary.created. Idempotent (upsert by idempotency_key = the same
# "<pnr>:confirmed:<message_id>" a normal send uses), so re-runs and overlap with
# the live poll never duplicate; PNRs already SAVED in Pivot OS are auto-hidden
# on their side. Set PIVOT_OS_DRY_RUN=1 to preview without persisting. Runs from
# CI (needs Google creds + egress). Public-safe summary: counts only.
def _portal_for(msg):
    subj = _header(msg, "Subject").lower()
    frm = _header(msg, "From").lower()
    for p in extractors.PORTALS:
        if p["subject"].lower() in subj and p["from"].lower() in frm:
            return p
    return None


def _find_drive_pdf(drive, pnr):
    """Best-effort: the branded PDF is uploaded as '<PNR>.pdf'. Return its Drive
    webViewLink (newest match), or '' if not found."""
    name = "".join(c for c in str(pnr) if c.isalnum() or c in "_-") + ".pdf"
    try:
        files = drive.files().list(
            q=f"name='{name}' and mimeType='application/pdf' and trashed=false",
            fields="files(id,webViewLink,modifiedTime)", orderBy="modifiedTime desc",
            pageSize=5).execute(num_retries=API_RETRIES).get("files", [])
    except Exception:
        return ""
    return files[0].get("webViewLink", "") if files else ""


def backfill_pivot_os():
    if not (os.environ.get("PIVOT_OS_SYNC_URL") and os.environ.get("PIVOT_OS_SYNC_SECRET")):
        print(json.dumps({"backfill": "skipped", "reason": "PIVOT_OS_SYNC_URL/SECRET not set"}))
        return
    gmail, drive = _services()
    dry = bool(os.environ.get("PIVOT_OS_DRY_RUN"))
    ids = [e["message_id"] for e in load_log()["processed"]]
    try:
        cap = int(os.environ.get("BACKFILL_LIMIT") or "0")   # 0 = all (for a small test run)
    except ValueError:
        cap = 0
    if cap:
        ids = ids[:cap]
    t = {"total": len(ids), "sent": 0, "duplicate": 0, "skipped": 0, "error": 0, "dry_run": dry}
    for mid in ids:
        try:
            msg = gmail.users().messages().get(
                userId="me", id=mid, format="full").execute(num_retries=API_RETRIES)
        except Exception:
            t["skipped"] += 1                     # email gone / inaccessible
            continue
        portal = _portal_for(msg)
        if not portal:
            t["skipped"] += 1
            continue
        try:
            if portal["source"] == "drive_pdf":
                src = akbar_attachment_text(gmail, msg)
                if not src:
                    epoch = int(msg["internalDate"]) / 1000
                    date_str = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")
                    src = akbar_pdf_text(drive, date_str, msg_epoch=epoch)
            else:
                src = _plain_body(msg)
            data = portal["fn"](src, {"date": _email_date_ddmon(msg)})
            data["portal"] = data.get("portal") or portal["name"]
            if extractors.qc_check(data):
                t["skipped"] += 1                 # can't rebuild cleanly — don't guess
                continue
            res = notify_pivot_os(data, _find_drive_pdf(drive, data.get("pnr", "")),
                                  "itinerary.created", mid, dry_run=dry)
            if res == "ok":
                t["sent"] += 1
            elif res == "duplicate":
                t["duplicate"] += 1
            else:
                t["error"] += 1
        except Exception:
            t["error"] += 1
    print(json.dumps({"pivot_os_backfill": t}, indent=2))


# ── auto-draft a REVISED itinerary on an aJet schedule change / cancellation ──
# When a disruption alert is an aJet change we can parse, rebuild the ORIGINAL
# booking (find its ticket email in cs@ by PNR, re-extract full pax/baggage/
# segments), patch ONLY the affected leg with the new flight/times, and render a
# fresh branded PDF for staff to VERIFY and forward. Safe-by-default: ANY
# uncertainty — can't parse the change, can't find the original booking, no leg
# matches, or QC fails — returns None and the alert ships with no draft. The
# draft is a convenience for the human who already reviews every alert; it is
# never sent to a client automatically.
def _find_original_ajet_booking(gmail, pnr):
    """Locate the original aJet ticket email for `pnr` in cs@ and re-extract it to
    a full finalised booking dict. Returns None if not found / not confidently the
    same PNR."""
    q = (f'from:onlineticket@mail.ajet.com subject:"Ticket information" {pnr} '
         f'-in:sent -in:trash')
    res = gmail.users().messages().list(
        userId="me", q=q, maxResults=5).execute(num_retries=API_RETRIES)
    for m in res.get("messages", []):
        msg = gmail.users().messages().get(
            userId="me", id=m["id"], format="full").execute(num_retries=API_RETRIES)
        booking = extractors.extract_ajet(_plain_body(msg), {"date": _email_date_ddmon(msg)})
        if (booking.get("pnr") or "").upper() == pnr.upper():
            booking["portal"] = "aJet"
            return booking
    return None


def build_revised_itinerary(gmail, alert):
    """Return a path to a freshly rendered REVISED itinerary PDF for a disruption
    `alert`, or None if one can't be produced confidently. aJet only for now."""
    if "onlineticket@mail.ajet.com" not in (alert.get("from") or "").lower():
        return None
    try:
        msg = gmail.users().messages().get(
            userId="me", id=alert["id"], format="full").execute(num_retries=API_RETRIES)
        change = extractors.extract_ajet_change(_plain_body(msg))
        if not change or not change.get("pnr"):
            return None
        booking = _find_original_ajet_booking(gmail, change["pnr"])
        if not booking:
            return None
        if not extractors.apply_flight_change(booking, change):
            return None                        # no leg matched — don't guess
        if extractors.qc_check(booking):
            return None                        # patched booking failed QC — abort
        # Scenario-based header pill (colour matches the alert coding): a cancelled
        # flight was rebooked onto a new one; else reschedule / delay; else generic.
        booking["doc_status"] = {"cancelled": "rebooked", "rescheduled": "rescheduled",
                                 "delayed": "delayed"}.get(change.get("status"), "revised")
        pnr = "".join(c for c in str(booking["pnr"]) if c.isalnum() or c in "_-") or "UNKNOWN"
        out_dir = os.path.join(OUT_DIR, "revised", datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = build_pdf(booking, out_dir, project_dir=PROJECT_DIR)
        revised = os.path.join(out_dir, f"REVISED-{pnr}.pdf")
        os.replace(pdf_path, revised)
        if extractors.india_arrival(booking):
            _append_air_suvidha(revised)       # keep the guide on India arrivals
        # Notify Pivot OS this booking changed (event=revised; best-effort, no-op
        # if unconfigured). The saved-booking side surfaces it as "review".
        try:
            notify_pivot_os(booking, "", "itinerary.revised", alert.get("id", ""))
        except Exception:
            pass
        return revised
    except Exception:
        return None                            # fail safe — alert still ships


# ── main ───────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    gmail, drive = _services()
    send_gmail, sender = _sender_gmail()       # confirmation From-address (SENDER_USER or cs@)
    # SAFETY: a blank/unset SEARCH_WINDOW must NOT mean "scan everything".
    # An empty string is treated as the safe default (last 1 day).
    window = os.environ.get("SEARCH_WINDOW") or "newer_than:1d"
    # SAFETY: hard cap on how many PDFs one run may create, so a fresh log can
    # never blast the whole inbox. Default 15; override with MAX_PER_RUN.
    try:
        max_per_run = int(os.environ.get("MAX_PER_RUN") or "15")
    except ValueError:
        max_per_run = 15
    log = load_log()
    done_ids = processed_ids(log)
    created, skipped, flagged = [], [], []
    pivot_os = {"ok": 0, "duplicate": 0, "error": 0}   # Pivot OS sync tallies (public-safe)

    def _bump(outcome):
        if outcome in ("ok", "duplicate"):
            pivot_os[outcome] += 1
        elif outcome:                                  # http-4xx/5xx / error (None = not configured)
            pivot_os["error"] += 1

    for portal in extractors.PORTALS:
        if len(created) >= max_per_run:
            break
        for mid in search_messages(gmail, portal, window):
            if len(created) >= max_per_run:
                break
            if mid in done_ids:
                skipped.append(mid)
                continue
            try:
                msg = gmail.users().messages().get(userId="me", id=mid, format="full").execute(num_retries=API_RETRIES)
                subj = _header(msg, "Subject").lower()
                frm = _header(msg, "From").lower()
                if portal["subject"].lower() not in subj or portal["from"].lower() not in frm:
                    continue

                if portal["source"] == "drive_pdf":
                    src = akbar_attachment_text(gmail, msg)   # primary: email's own PDF attachment
                    if not src:
                        epoch = int(msg["internalDate"]) / 1000
                        date_str = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")
                        src = akbar_pdf_text(drive, date_str, msg_epoch=epoch)   # fallback: Drive
                else:
                    src = _plain_body(msg)

                data = portal["fn"](src, {"date": _email_date_ddmon(msg)})
                data["portal"] = data.get("portal") or portal["name"]

                problem = extractors.qc_check(data)
                if problem:
                    flagged.append({"id": mid, "portal": portal["name"], "reason": problem,
                                    "subject": _header(msg, "Subject")})
                    continue

                pnr = "".join(c for c in str(data["pnr"]) if c.isalnum() or c in "_-") or "UNKNOWN"
                date_sub = datetime.now().strftime("%Y-%m-%d")
                pdf_path = build_pdf(data, os.path.join(OUT_DIR, date_sub), project_dir=PROJECT_DIR)
                if extractors.india_arrival(data):
                    _append_air_suvidha(pdf_path)   # single merged PDF: itinerary + guide

                link = upload_to_drive(drive, pdf_path, date_sub)

                # IDEMPOTENCY: record the booking as processed the moment its PDF is
                # on Drive — BEFORE emailing — and checkpoint the log to disk. If the
                # email send then fails (or the process dies), the next run will NOT
                # re-upload the PDF or re-send the email; the failed send is retried
                # best-effort and, if it still fails, surfaces as a manual-review flag.
                #
                # PRIVACY: this file is committed to a PUBLIC repo, so persist ONLY the
                # opaque Gmail message_id. PNR / passenger data / Drive links stay
                # private — they travel in the emailed confirmation (search cs@ for the
                # message_id via the email's "Source Ref" line).
                log["processed"].append({"message_id": mid})
                done_ids.add(mid)
                save_log(log)                                   # checkpoint per booking
                try:
                    email_pdf(send_gmail, sender, pdf_path, data, source_ref=mid)
                except Exception as e:
                    flagged.append({"id": mid, "portal": portal["name"],
                                    "reason": f"email-failed: {e}",
                                    "subject": _header(msg, "Subject")})
                created.append({"pnr": data["pnr"], "portal": data["portal"], "link": link})
                # Push to Pivot OS "Entries to Be Done" (best-effort; inert until
                # configured; failure never affects the booking that already shipped).
                try:
                    _bump(notify_pivot_os(data, link, "itinerary.created", mid))
                except Exception:
                    _bump("error")
            except Exception as e:
                flagged.append({"id": mid, "portal": portal["name"],
                                "reason": f"error: {e}", "trace": traceback.format_exc()[-500:]})

    save_log(log)
    # Privately notify Minh of anything needing manual review (inbox only, never
    # the public log). A failure here must not break the run summary.
    try:
        email_flags(send_gmail, sender, flagged)
    except Exception as e:
        print(json.dumps({"flag_email_error": str(e)[:120]}))

    # ── disruption watch ────────────────────────────────────────────────────
    # Alert on NEW cancellation / schedule-change emails so they stop getting
    # missed. Independent of the confirmation flow; de-duped by its own log
    # (message_id only, public-safe). The alert is recorded only AFTER a
    # successful send, so a failed send re-alerts next run rather than silently
    # dropping the warning. Fully wrapped: a disruption-watch failure must never
    # break the confirmation run or its summary.
    disruption_alerts = 0
    revised_drafts = 0
    try:
        dlog = load_disruption_log()
        alerted_ids = {e["message_id"] for e in dlog["alerted"]}
        new_alerts = scan_disruptions(gmail, alerted_ids)
        if new_alerts:
            # Try to auto-draft a REVISED itinerary for each alert (aJet only for
            # now; None whenever it can't be produced confidently). Attached to the
            # digest for the human to verify + forward.
            for a in new_alerts:
                a["revised_pdf"] = build_revised_itinerary(gmail, a)
                if a["revised_pdf"]:
                    revised_drafts += 1
            email_disruptions(send_gmail, sender, new_alerts)
            for a in new_alerts:
                dlog["alerted"].append({"message_id": a["id"]})
            save_disruption_log(dlog)
            disruption_alerts = len(new_alerts)
    except Exception as e:
        print(json.dumps({"disruption_watch_error": str(e)[:120]}))
    # PUBLIC-SAFE LOG: print COUNTS only — never PNRs, passenger names, Drive
    # links, message ids, subjects, or tracebacks (Action logs are world-readable
    # on a public repo). Per-portal tallies + generic flag reasons are enough to
    # monitor; the actual confirmations are delivered privately by email.
    by_portal = {}
    for c in created:
        by_portal[c["portal"]] = by_portal.get(c["portal"], 0) + 1
    summary = {
        "created_total": len(created),
        "created_by_portal": by_portal,
        "skipped": len(skipped),
        "flagged_total": len(flagged),
        "flagged_reasons": sorted({(f.get("reason") or "").split(":")[0] for f in flagged}),
        "disruption_alerts": disruption_alerts,
        "revised_drafts": revised_drafts,
        "pivot_os_sync": pivot_os,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    import sys
    if "--backfill-pivot-os" in sys.argv:
        backfill_pivot_os()          # one-off: re-send all processed bookings
    else:
        main()
