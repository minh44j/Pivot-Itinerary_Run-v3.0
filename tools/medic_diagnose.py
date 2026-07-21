#!/usr/bin/env python3
"""Medic diagnosis — redacted, any-portal extraction debugger.

Given ONE Gmail message id (a booking that failed qc_check and got flagged for
manual review), this fetches the SAME source the poll uses (Akbar → the PDF
attachment via pdfplumber; every other portal → the email body), runs the live
extractor + qc_check(), and prints a PII-REDACTED diagnosis:

  1. which portal matched (or none),
  2. a redacted, line-numbered view of the source text the extractor sees,
  3. the redacted parse result, and
  4. the qc_check() verdict + a per-field breakdown of what's missing.

This repo is PUBLIC and Action logs are world-readable, so EVERYTHING printed
is redacted first: titled passenger names, 9+ digit numbers (tickets / phones),
e-mail addresses, and the PNR / booking / CRS references are masked. Flight
codes, airports, cities, dates and times stay visible — they are what a parser
miss turns on and are not personal data on their own.

Used by the medic loop (see MEDIC.md) to diagnose a flag WITHOUT any PII ever
reaching the public log. Manual/dispatch use: MEDIC_MSG_ID=<id> python tools/medic_diagnose.py
"""
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402  (auth + per-portal source acquisition live here)
import extractors  # noqa: E402


def redact(text):
    """Mask PII before anything reaches the public Action log."""
    if not text:
        return text
    text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "<EMAIL>", text)
    text = re.sub(
        r"\b((?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.?\s+[A-Z][A-Z .'\-]{1,40})",
        "<PAX>", text)
    text = re.sub(r"\b\d{9,}\b", "<NUM>", text)
    return text


def redact_result(d):
    """Mask name / ticket_no / refs on the parsed booking; keep structure visible."""
    d = copy.deepcopy(d or {})
    for k in ("pnr", "booking_ref", "crs_ref"):
        if d.get(k):
            d[k] = f"<{k.upper()}:{len(str(d[k]))} chars>"
    for p in d.get("passengers", []):
        if p.get("name"):
            p["name"] = "<PAX>"
        if p.get("ticket_no") and p["ticket_no"] != "Not specified":
            p["ticket_no"] = "<TKT>"
    return d


def _source_for(gmail, drive, msg, portal):
    """The exact source the poll feeds the extractor for this portal."""
    if portal["source"] == "drive_pdf":
        src = main.akbar_attachment_text(gmail, msg)
        if not src:
            from datetime import datetime, timezone
            epoch = int(msg["internalDate"]) / 1000
            date_str = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")
            src = main.akbar_pdf_text(drive, date_str, msg_epoch=epoch)
        return src
    return main._plain_body(msg)


def _missing_fields(data):
    """Per-flight breakdown of which qc-gated fields are blank (guides the fix)."""
    out = []
    for si, seg in enumerate((data or {}).get("segments", [])):
        for fi, f in enumerate(seg.get("flights", [])):
            blank = [k for k in ("flight_no", "dep_iata", "arr_iata", "dep_time", "arr_time")
                     if not f.get(k)]
            if blank:
                out.append(f"segment[{si}].flight[{fi}] missing: {', '.join(blank)}")
    return out


def run():
    msg_id = os.environ.get("MEDIC_MSG_ID", "").strip()
    if not msg_id:
        print("ERROR: set MEDIC_MSG_ID")
        return 2
    gmail, drive = main._services()
    msg = gmail.users().messages().get(
        userId="me", id=msg_id, format="full").execute(num_retries=main.API_RETRIES)

    subject = main._header(msg, "Subject")
    portal = main._portal_for(msg)
    print("=" * 72)
    print(f"message_id : {msg_id}")
    print(f"subject    : {redact(subject)}")
    print(f"portal     : {portal['name'] if portal else 'NONE — no portal matched'}")
    print("=" * 72)

    if not portal:
        # Not a recognised ticket confirmation at all → this is a NEEDS-HUMAN case,
        # not a parser bug (could be a non-confirmation, a new portal, spam).
        print("VERDICT: needs-human (sender/subject match no known portal).")
        return 0

    src = _source_for(gmail, drive, msg, portal)
    print(f"source length: {len(src or '')} chars")
    print("-" * 72)
    print("REDACTED SOURCE (numbered lines):")
    for i, line in enumerate(redact(src or "").splitlines(), 1):
        print(f"{i:3d}| {line}")
    print("-" * 72)
    print("Flight-code-shaped tokens (LL | LD | DL) in raw source:")
    for m in re.finditer(r"\b((?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z]))\s?-?\s?(\d{2,4})\b", src or ""):
        print(f"   -> {m.group(0)!r}")
    print("-" * 72)

    try:
        data = portal["fn"](src, {"date": main._email_date_ddmon(msg)})
        data["portal"] = data.get("portal") or portal["name"]
    except Exception as e:  # noqa: BLE001
        print(f"extractor RAISED: {type(e).__name__}: {e}")
        print("VERDICT: parser-error (extractor threw) — likely a code bug.")
        return 0

    print("REDACTED PARSE RESULT:")
    print(json.dumps(redact_result(data), indent=2, ensure_ascii=False))
    print("-" * 72)
    qc = extractors.qc_check(data)
    if qc:
        print(f"qc_check FLAG: {qc}")
        for line in _missing_fields(data):
            print(f"   {line}")
        print("VERDICT: parser-bug candidate — see the missing fields above and the "
              "raw source; patch the matching extractor in extractors.py + add a "
              "zero-PII regression fixture.")
    else:
        print("qc_check: PASS — extractor now produces a clean booking.")
        print("VERDICT: resolved — reprocesses cleanly on the next poll "
              "(the earlier flag was transient or already fixed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
