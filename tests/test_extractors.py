"""
Offline regression tests for the portal extractors.

These run with NO network and NO Google/Playwright — they feed saved SYNTHETIC
fixtures (fake PNRs/passengers; never real inbox data) through each extractor and
assert two things:

  1. qc_check() reaches the expected verdict (pass, or a specific flag).
  2. The full parsed dict still matches a committed "golden" snapshot, so any
     future edit that changes extractor output is caught immediately.

Regenerate the golden snapshots after an INTENTIONAL change:

    UPDATE_GOLDEN=1 python -m pytest tests/ -q

Then eyeball the git diff under tests/expected/ before committing.
"""
import json
import os
import pathlib

import pytest

import extractors as E

ROOT = pathlib.Path(__file__).resolve().parent
FIX = ROOT / "fixtures"
EXP = ROOT / "expected"
CTX = {"date": "01 Jan 2026"}   # fixed booked_on fallback -> deterministic output

# fixture filename -> (extractor, expected qc substring or None for "must pass")
CASES = {
    "ajet_connecting.html":            (E.extract_ajet,    None),
    "alhind_oneway.html":              (E.extract_alhind,  None),
    "pegasus_roundtrip.html":          (E.extract_pegasus, None),
    "akbar_oneway.txt":                (E.extract_akbar,   None),
    "neg_ajet_missing_pnr.html":       (E.extract_ajet,    "Missing PNR"),
    "neg_akbar_missing_flightno.txt":  (E.extract_akbar,   "missing flight number"),
}


def _run(fixture):
    fn, _ = CASES[fixture]
    src = (FIX / fixture).read_text(encoding="utf-8")
    return fn(src, dict(CTX))


@pytest.mark.parametrize("fixture", list(CASES))
def test_qc(fixture):
    _, expected = CASES[fixture]
    qc = E.qc_check(_run(fixture))
    if expected is None:
        assert qc is None, f"{fixture}: expected QC to PASS, got {qc!r}"
    else:
        assert qc and expected.lower() in qc.lower(), \
            f"{fixture}: expected QC flag containing {expected!r}, got {qc!r}"


@pytest.mark.parametrize("data,expected", [
    # international arrival into India -> True (triggers Air Suvidha attachment)
    ({"segments": [{"flights": [{"dep_iata": "IST", "arr_iata": "DEL"}]}]}, True),
    ({"segments": [{"flights": [{"dep_iata": "DXB", "arr_iata": "COK"}]}]}, True),
    # round trip India<->abroad: return leg lands in India -> True
    ({"segments": [{"flights": [{"dep_iata": "BOM", "arr_iata": "IST"}]},
                   {"flights": [{"dep_iata": "IST", "arr_iata": "BOM"}]}]}, True),
    # purely domestic Indian hop -> False (no international arrival)
    ({"segments": [{"flights": [{"dep_iata": "DEL", "arr_iata": "BOM"}]}]}, False),
    # nothing touching India -> False
    ({"segments": [{"flights": [{"dep_iata": "IST", "arr_iata": "SAW"}]}]}, False),
    # India -> abroad only (outbound, no arrival into India) -> False
    ({"segments": [{"flights": [{"dep_iata": "MAA", "arr_iata": "SIN"}]}]}, False),
])
def test_india_arrival(data, expected):
    assert E.india_arrival(data) is expected


@pytest.mark.parametrize("subject,should_match", [
    # REAL disruption subjects seen in the cs@ mailbox -> must flag for an alert.
    ("Flight change information", True),                 # aJet
    ("Flight Schedule Change Information", True),        # aJet
    ("Your Revised IndiGo Itinerary", True),            # IndiGo (note: "Revised"..."Itinerary" non-adjacent)
    ("Flight Delayed Notification", True),              # airblue
    ("Schedule Change", True),                          # Turkish Airlines
    ("✈ Booking cancelled #GVBO9U", True),         # flydubai
    ("Important: Flight change", True),                 # Etihad
    ("FLIGHT CANCELLATION INFORMATION", True),          # Himalaya
    ("SCHEDULE CHANGE // X6Y18Z", True),               # Alhind B2B
    ("schedule change GY7G4P", True),                   # Akbar B2B
    ("Important changes to your booking: Booking reference: GVBO9U", True),  # flydubai
    ("Your flight schedule has changed", True),         # Qatar Airways
    ("The departure time has changed for your flight to Jeddah", True),      # Emirates
    ("Delay of your flight to Rome", True),            # ITA Airways
    ("Gulf Air Flight Time Change", True),             # Gulf Air
    ("Fly Jinnah Booking Change Notification", True),   # Fly Jinnah
    ("RE: ALQ11072026094425106- FLIGHT DISRUPTED", True),   # Alhind B2B
    # REAL non-disruption subjects from the same mailbox -> must NOT flag.
    ("Update on your upcoming flight", False),          # Saudia marketing upsell
    ("Update on your flight to Riyadh", False),         # flynas upgrade bid
    ("Next steps for your upcoming flight to Riyadh", False),   # marketing
    ("Oman Air - Important Update", False),             # Oman Air upsell
    ("PIA Contact Change", False),                       # contact info change, NOT the flight
    ("Itinerary for the Reservation 4H9VD0", False),    # Air Arabia confirmation
    ("Check In for flight : XY-140", False),           # flynas check-in
    ("Check-in reminder", False),                       # aJet check-in
    ("Boarding Information", False),                     # aJet gate info
    ("Manage My Booking Activation Code", False),       # aJet OTP
    ("Pegasus Airlines Activation Code", False),        # Pegasus OTP
    ("Important Travel Information for Your Upcoming Flight", False),  # IndiGo check-in
    ("Air Ticket", False),                              # Alhind confirmation
    ("Ticket information", False),                       # aJet confirmation
    ("Booking Success", False),                          # Akbar confirmation
    ("Your booking is confirmed! View your ticket now", False),      # Pegasus confirmation
    # Trickier real traps that must NOT flag (not client-facing flight disruptions):
    ("Action Required: Submit Your Air Suvidha Self-Declaration Form", False),  # AI Express form
    ("RE: ALQ06072026120450106- REISSUE REQUEST", False),   # B2B reissue chatter
    ("Flight reissue request", False),                       # our own reissue request
    ("Flyadeal Notification - Gate Change", False),          # gate change (airport-level, not schedule)
    ("Action required for your Google Account", False),      # unrelated account mail
])
def test_disruption_match(subject, should_match):
    hit = E.disruption_match(subject)
    assert bool(hit) is should_match, f"{subject!r} -> {hit!r}"


@pytest.mark.parametrize("subject,preview,keyword,expected", [
    # cancellation wins even when the SUBJECT only says "flight change" — the real
    # aJet case: subject "Flight change information", body "has been canceled".
    ("Flight change information",
     "Your flight 19 July 2026, VF191, has been canceled due to operational reasons",
     "flight change", "cancellation"),
    ("Booking cancelled #GVBO9U", "Your booking has been cancelled", "cancel", "cancellation"),
    ("FLIGHT CANCELLATION INFORMATION", "flight is canceled", "cancel", "cancellation"),
    # delay
    ("Flight delay information", "estimated departure time ... has been changed", "delay", "delay"),
    ("Delay of your flight to Rome", "Your flight is delayed", "delay", "delay"),
    # everything else -> schedule_change
    ("Schedule Change", "There has been a change in your flight", "schedule change", "schedule_change"),
    ("Your Revised IndiGo Itinerary", "has been rescheduled", "revised", "schedule_change"),
    ("Your flight schedule has changed", "we've got flexible options", "has changed", "schedule_change"),
])
def test_disruption_category(subject, preview, keyword, expected):
    assert E.disruption_category(subject, preview, keyword) == expected


@pytest.mark.parametrize("fixture", list(CASES))
def test_snapshot(fixture):
    data = _run(fixture)
    golden_path = EXP / (fixture + ".json")
    if os.environ.get("UPDATE_GOLDEN"):
        golden_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        return
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert data == golden, (
        f"{fixture}: extractor output changed vs golden snapshot. "
        f"If intentional, re-run with UPDATE_GOLDEN=1 and review the diff."
    )
