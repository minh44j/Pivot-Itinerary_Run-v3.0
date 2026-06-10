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
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROJECT_DIR, "out")


# ── auth ──────────────────────────────────────────────────────────────────
# Two supported modes (both impersonate cs@ via domain-wide delegation):
#   1. KEYLESS (Workload Identity Federation) — preferred. No downloadable key.
#      GitHub Actions gets ADC via google-github-actions/auth; we then mint a
#      DWD token for cs@ using the IAM Credentials API (signBlob), so the service
#      account never needs an exported JSON key. Requires env SERVICE_ACCOUNT_EMAIL
#      and the SA holding roles/iam.serviceAccountTokenCreator on itself.
#   2. KEY (fallback) — set env GOOGLE_SA_JSON to the full service-account JSON.
def _delegated_creds():
    subject = os.environ["IMPERSONATE_USER"]
    sa_email = os.environ["SERVICE_ACCOUNT_EMAIL"]
    # Source identity from Application Default Credentials (WIF in CI).
    source_creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    # Sign via IAM Credentials API (no private key) and apply DWD subject=cs@.
    signer = iam.Signer(Request(), source_creds, sa_email)
    return service_account.Credentials(
        signer=signer,
        service_account_email=sa_email,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
        subject=subject,
    )


def _services():
    if os.environ.get("GOOGLE_SA_JSON"):                       # fallback: exported key
        info = json.loads(os.environ["GOOGLE_SA_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES, subject=os.environ["IMPERSONATE_USER"])
    else:                                                       # preferred: keyless WIF
        creds = _delegated_creds()
    return build("gmail", "v1", credentials=creds, cache_discovery=False), \
        build("drive", "v3", credentials=creds, cache_discovery=False)


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
    res = gmail.users().messages().list(userId="me", q=q, maxResults=25).execute()
    return [m["id"] for m in res.get("messages", [])]


# ── Akbar Drive PDF -> text ────────────────────────────────────────────────
def akbar_pdf_text(drive, msg_date_str):
    import pdfplumber
    folder_name = os.environ.get("AKBAR_FOLDER_NAME", "Pivot AI - Ticket PDFs")
    fres = drive.files().list(q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                              fields="files(id)").execute().get("files", [])
    if not fres:
        return ""
    folder_id = fres[0]["id"]
    q = f"'{folder_id}' in parents and name contains 'AKBAR_' and mimeType='application/pdf'"
    files = drive.files().list(q=q, fields="files(id,name,modifiedTime)",
                               orderBy="modifiedTime desc").execute().get("files", [])
    if not files:
        return ""
    pick = next((f for f in files if msg_date_str in f["name"]), files[0])
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
    found = drive.files().list(q=q, fields="files(id)").execute().get("files", [])
    sub_id = found[0]["id"] if found else drive.files().create(
        body={"name": date_sub, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]},
        fields="id").execute()["id"]
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    f = drive.files().create(
        body={"name": os.path.basename(pdf_path), "parents": [sub_id]},
        media_body=media, fields="id,webViewLink").execute()
    return f.get("webViewLink", "")


# ── email delivery: cs@ self-emails the finished PDF (gmail.send, scoped) ──
# Approved 2026-06-08: cs@ keeps gmail.readonly for all reading/searching (no
# message is ever touched, replied to, forwarded, or deleted). It additionally
# holds gmail.send for exactly ONE purpose — emailing the finished PDF back to
# itself so the confirmation "arrives in gmail inbox" alongside the source email.
def email_pdf(gmail, pdf_path, data):
    sender = os.environ["IMPERSONATE_USER"]               # cs@pivot-travels.com
    to = os.environ.get("NOTIFY_TO") or sender             # defaults to self-email
    m = EmailMessage()
    m["Subject"] = f"Booking Confirmation — {data.get('pnr')} ({data.get('portal')})"
    m["From"] = sender
    m["To"] = to
    pax = ", ".join(p["name"] for p in data.get("passengers", []))
    m.set_content(f"PNR: {data.get('pnr')}\nPortal: {data.get('portal')}\n"
                  f"Passenger(s): {pax}\nBooked On: {data.get('booked_on')}\n\n"
                  f"PDF attached. (Automated — PIVOT AI AUTOMATED ITINERARY)")
    with open(pdf_path, "rb") as f:
        m.add_attachment(f.read(), maintype="application", subtype="pdf",
                         filename=os.path.basename(pdf_path))
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode("ascii")
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
    return True


# ── main ───────────────────────────────────────────────────────────────────
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    gmail, drive = _services()
    # SAFETY: a blank/unset SEARCH_WINDOW must NOT mean "scan everything".
    window = os.environ.get("SEARCH_WINDOW") or "newer_than:1d"
    # SAFETY: hard cap on PDFs per run so a fresh log can't blast the whole inbox.
    try:
        max_per_run = int(os.environ.get("MAX_PER_RUN") or "15")
    except ValueError:
        max_per_run = 15
    log = load_log()
    done_ids = processed_ids(log)
    created, skipped, flagged = [], [], []

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
                msg = gmail.users().messages().get(userId="me", id=mid, format="full").execute()
                subj = _header(msg, "Subject").lower()
                frm = _header(msg, "From").lower()
                if portal["subject"].lower() not in subj or portal["from"].lower() not in frm:
                    continue

                if portal["source"] == "drive_pdf":
                    epoch = int(msg["internalDate"]) / 1000
                    date_str = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")
                    src = akbar_pdf_text(drive, date_str)
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

                link = upload_to_drive(drive, pdf_path, date_sub)
                emailed = email_pdf(gmail, pdf_path, data)

                log["processed"].append({
                    "message_id": mid, "pnr": data["pnr"], "portal": data["portal"],
                    "processed_at": date_sub, "drive_link": link, "emailed": emailed,
                })
                done_ids.add(mid)
                created.append({"pnr": data["pnr"], "portal": data["portal"], "link": link})
            except Exception as e:
                flagged.append({"id": mid, "portal": portal["name"],
                                "reason": f"error: {e}", "trace": traceback.format_exc()[-500:]})

    save_log(log)
    print(json.dumps({"created": created, "skipped": len(skipped), "flagged": flagged}, indent=2))


if __name__ == "__main__":
    main()
