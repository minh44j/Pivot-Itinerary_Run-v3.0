#!/usr/bin/env python3
"""
Validate a portal extractor against a REAL email before going live.

Usage:
  # Pull the latest matching email and print the parsed dict + QC result:
  python tools/test_extractor.py Pegasus

  # Or test against a saved .txt body (no Gmail call):
  python tools/test_extractor.py Pegasus path/to/body.txt
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extractors  # noqa: E402


def from_gmail(portal):
    from main import _services, _plain_body, _header, akbar_pdf_text
    from datetime import datetime, timezone
    gmail, drive = _services()
    window = os.environ.get("SEARCH_WINDOW", "newer_than:14d")
    ids = __import__("main").search_messages(gmail, portal, window)
    if not ids:
        print("No matching email found for", portal["name"])
        return None
    msg = gmail.users().messages().get(userId="me", id=ids[0], format="full").execute()
    if portal["source"] == "drive_pdf":
        epoch = int(msg["internalDate"]) / 1000
        ds = datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")
        return akbar_pdf_text(drive, ds)
    return _plain_body(msg)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    name = sys.argv[1]
    portal = next((p for p in extractors.PORTALS if p["name"].lower() == name.lower()), None)
    if not portal:
        print("Unknown portal. Options:", [p["name"] for p in extractors.PORTALS])
        return

    if len(sys.argv) >= 3:                       # from a saved file
        with open(sys.argv[2], encoding="utf-8") as f:
            src = f.read()
    else:                                        # from Gmail
        src = from_gmail(portal)
        if src is None:
            return

    data = portal["fn"](src, {})
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\nQC:", extractors.qc_check(data) or "PASS")


if __name__ == "__main__":
    main()
