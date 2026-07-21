#!/usr/bin/env python3
"""Akbar extraction debugger (§9 workflow).

Pulls the PDF attachment of a single Akbar 'Booking Success' email straight
from Gmail, runs the REAL extractors.extract_akbar() + qc_check() against the
live pdfplumber text (NOT the HTML body — the two are not equivalent, see
CLAUDE.md §9), and prints:

  1. a PII-REDACTED structural view of the pdfplumber text, and
  2. the parse result with name/ticket fields masked.

This repo is PUBLIC and Action logs are world-readable, so EVERYTHING printed
here is redacted first: titled passenger names, 9+ digit numbers (tickets /
phones), e-mail addresses, and the PNR / booking reference are masked. Flight
codes, airports, cities, dates and times stay visible — they are what we need
to diagnose a parser miss and are not personal data on their own.

Usage (in the debug workflow): AKBAR_DEBUG_MSG_ID=<gmail-message-id> python tools/akbar_debug.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402  (auth + akbar_attachment_text live here)
import extractors  # noqa: E402


def redact(text):
    """Mask PII before anything reaches the public Action log."""
    if not text:
        return text
    # e-mail addresses
    text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "<EMAIL>", text)
    # titled passenger names (Mr/Mrs/Ms/Mstr/Master/Miss/Dr + CAPS run)
    text = re.sub(
        r"\b((?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.?\s+[A-Z][A-Z .'\-]{1,40})",
        "<PAX>", text)
    # 9+ digit runs (ticket numbers, phone numbers)
    text = re.sub(r"\b\d{9,}\b", "<NUM>", text)
    return text


def redact_result(d):
    """Mask name / ticket_no on the parsed booking; keep structure visible."""
    import copy
    d = copy.deepcopy(d)
    # PNR / refs — sensitive in this repo's convention; mask but show shape.
    for k in ("pnr", "booking_ref", "crs_ref"):
        if d.get(k):
            d[k] = f"<{k.upper()}:{len(str(d[k]))} chars>"
    for p in d.get("passengers", []):
        if p.get("name"):
            p["name"] = "<PAX>"
        if p.get("ticket_no") and p["ticket_no"] != "Not specified":
            p["ticket_no"] = "<TKT>"
    return d


def main_debug():
    msg_id = os.environ.get("AKBAR_DEBUG_MSG_ID", "").strip()
    if not msg_id:
        print("ERROR: set AKBAR_DEBUG_MSG_ID")
        return 2
    gmail, _drive = main._services()
    msg = gmail.users().messages().get(
        userId="me", id=msg_id, format="full").execute(num_retries=main.API_RETRIES)

    text = main.akbar_attachment_text(gmail, msg)
    print("=" * 70)
    print(f"pdfplumber text length: {len(text)} chars")
    print("=" * 70)
    print("REDACTED pdfplumber TEXT (numbered lines):")
    print("-" * 70)
    for i, line in enumerate(redact(text).splitlines(), 1):
        print(f"{i:3d}| {line}")
    print("-" * 70)

    # Highlight every token that LOOKS like an IATA flight designator + number,
    # so a miss on the F3/G9/U2 (letter-then-digit) shape is obvious.
    print("Flight-code-shaped tokens found in raw text:")
    for m in re.finditer(r"\b((?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z]))\s?-?\s?(\d{2,4})\b", text):
        print(f"   -> {m.group(0)!r}")
    print("-" * 70)

    try:
        result = extractors.extract_akbar(text)
        print("extract_akbar() SUCCEEDED. Redacted result:")
        import json
        print(json.dumps(redact_result(result), indent=2, ensure_ascii=False))
        flags = extractors.qc_check(result)
        print("-" * 70)
        print(f"qc_check() flags: {flags if flags else 'NONE — would produce a PDF'}")
    except Exception as e:  # noqa: BLE001
        print(f"extract_akbar() RAISED: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_debug())
