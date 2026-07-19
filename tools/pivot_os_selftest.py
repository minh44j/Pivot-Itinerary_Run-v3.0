#!/usr/bin/env python3
"""Pivot OS wire self-test — fire ONE synthetic dry-run event and print the echo.

Deterministic end-to-end check of the Producer → Pivot OS connection, independent
of the inbox. Uses SENTINEL data only (PNR TEST0001, fake passenger) and always
sends `X-Dry-Run: 1`, so **nothing is persisted** in Pivot OS. Safe to run from a
public CI log (no real PII; GitHub masks the secret).

Run (locally or via the pivot-os-test workflow), with the two secrets in env:
    PIVOT_OS_SYNC_URL=... PIVOT_OS_SYNC_SECRET=... python tools/pivot_os_selftest.py

Stdlib only — does NOT import main.py (so no Google deps needed).
"""
import os
import sys
import json
import ssl
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extractors  # noqa: E402  (pure-stdlib module)

SENTINEL = {
    "portal": "aJet", "pnr": "TEST0001", "booking_ref": "TEST0001",
    "booked_on": "14 Jul 2026", "journey_type": "ROUND TRIP",
    "passengers": [{"name": "Test Passenger", "ticket_no": "0000000000001",
                    "cabin_bag": "7kg", "checked_bag": "20kg", "seat": "12A"}],
    "segments": [{"type": "Outbound", "flights": [
        {"airline": "aJet", "flight_no": "VF 200", "cabin": "Economy",
         "dep_iata": "LHR", "arr_iata": "CDG", "dep_city": "London", "arr_city": "Paris",
         "dep_date": "19 Jul 2026", "dep_time": "22:10",
         "arr_date": "19 Jul 2026", "arr_time": "02:05", "duration": "3H 55M"}], "layovers": []}],
}


def main():
    url = os.environ.get("PIVOT_OS_SYNC_URL")
    secret = os.environ.get("PIVOT_OS_SYNC_SECRET")
    if not url or not secret:
        print(json.dumps({"selftest": "skipped",
                          "reason": "set PIVOT_OS_SYNC_URL and PIVOT_OS_SYNC_SECRET"}))
        return 0

    payload = extractors.pivot_os_payload(
        SENTINEL, pdf_url="https://drive.example/selftest",
        event="itinerary.created", source_ref="selftest")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {secret}",
        "Idempotency-Key": payload["idempotency_key"],
        "X-Dry-Run": "1",          # never persists
    })
    ca = "/root/.ccr/ca-bundle.crt"
    ctx = ssl.create_default_context(cafile=ca) if os.path.exists(ca) else ssl.create_default_context()
    print(f"→ POST {url}  (X-Dry-Run, idempotency_key={payload['idempotency_key']})")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print(f"← HTTP {r.getcode()}")
            print(r.read().decode("utf-8")[:2000])
            return 0
    except urllib.error.HTTPError as e:
        print(f"← HTTP {e.code}")
        print(e.read().decode("utf-8")[:2000])
        return 1
    except Exception as e:
        print(f"← ERROR {type(e).__name__}: {str(e)[:300]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
