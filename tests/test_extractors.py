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
    # Flyadeal F3 — LD-shape (letter-then-digit) IATA designator, value sitting
    # several column-header lines below the "Flight Number" label. Regression
    # for the empty-flight-number QC flag on real booking (2026-07-21).
    "akbar_flyadeal_f3.txt":           (E.extract_akbar,   None),
    # Air Arabia G9 connection — Traveler table renders the name FUSED to the
    # ticket number with the baggage cell trailing on the same line, and the
    # ticket repeats once per leg. Also has no "Operated by:" line at all.
    # Regression for the "Passenger name missing" flag on real booking
    # AS261308499 (2026-08-13).
    "akbar_fused_name_ticket.txt":     (E.extract_akbar,   None),
    # Saudia via Akbar — the "Operated by:" cell WRAPS across two lines and the
    # date column bleeds onto the first, so the carrier arrived as "Saudi Mon".
    # Real booking 8CP5SK (2026-08-19).
    "akbar_wrapped_carrier.txt":       (E.extract_akbar,   None),
    # SPLIT-CARRIER round trip: two airlines under one agency ref, so each
    # direction has its OWN airline reference and its OWN baggage allowance, the
    # first Traveler table has no "Ticket No." column at all, and the second
    # Traveler/Baggage block repeats empty before the populated one.
    # Real booking AS261347760 (2026-08-20).
    "akbar_split_carrier.txt":         (E.extract_akbar,   None),
    # aJet "Basic" fare brand, written in mixed case unlike ECOJET/BIZJET/PREMIUM.
    # Regression for the round trip that rendered Economy outbound and N/A
    # inbound on one document (real booking 4B0NA3, 2026-08-15).
    "ajet_basic_fare.html":            (E.extract_ajet,    None),
    "neg_ajet_missing_pnr.html":       (E.extract_ajet,    "Missing PNR"),
    "neg_akbar_missing_flightno.txt":  (E.extract_akbar,   "missing flight number"),
    "turkish_airlines_connecting.txt": (E.extract_turkish_airlines, None),
    "neg_turkish_airlines_missing_flightno.txt": (E.extract_turkish_airlines, "No flight segments"),
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


# Booking-level dedup key for the disruption watch. Airlines re-send the same
# disruption for a booking repeatedly (each a new message_id); the key collapses
# identical re-sends while a genuinely NEW revision still alerts. Keyed on
# booking + type + the notice's flight FACTS (not the calendar day — an airline
# that backdates its Date header, or re-sends daily, defeated a day-based key).
_TK_SUBJ = "Turkish Airlines Flight Delay Information"
_TK_FROM = "onlineticket@mail.turkishairlines.com"
_IG_SUBJ = "Your Revised IndiGo Itinerary"
_IG_FROM = "services@goindigo.in"
_IG_BODY = ("Dear 6E customer, We apologize to inform you that your flight for PNR-VHZPNH, "
            "is affected due to operational reasons. Your itinerary revised flight details "
            "are 6E-85, on 17 Aug, HYD-DMM 0510-0755 . Our")


def test_disruption_dedup_identical_resends_collapse():
    # IndiGo re-sent this byte-identical notice 5x across TWO calendar days (and
    # backdated one Date header). All must collapse to a single alert.
    keys = {E.disruption_dedup_key(_IG_SUBJ, _IG_BODY, _IG_FROM, "schedule_change")
            for _ in range(5)}
    assert len(keys) == 1 and keys.pop()


def test_disruption_dedup_new_revision_alerts():
    base = E.disruption_dedup_key(_IG_SUBJ, _IG_BODY, _IG_FROM, "schedule_change")
    # a genuinely NEW revision (different flight number AND times) must re-alert,
    # even if it lands the same day — the old day-based key wrongly suppressed it.
    revised = _IG_BODY.replace("6E-85", "6E-92").replace("0510-0755", "0730-1015")
    assert E.disruption_dedup_key(_IG_SUBJ, revised, _IG_FROM, "schedule_change") != base


def test_disruption_dedup_distinguishes():
    prev = "Reservation code UCHMPF flight TK140"
    base = E.disruption_dedup_key(_TK_SUBJ, prev, _TK_FROM, "delay")
    # different booking, and an escalation to a cancellation, stay distinct
    assert E.disruption_dedup_key(
        _TK_SUBJ, "Reservation code WB2WKB flight TK140", _TK_FROM, "delay") != base
    assert E.disruption_dedup_key(_TK_SUBJ, prev, _TK_FROM, "cancellation") != base


def test_disruption_dedup_key_leaks_no_pnr():
    # Persisted to a PUBLIC repo (disruption_ids.json) — must be an opaque hash.
    k = E.disruption_dedup_key(_TK_SUBJ, "Reservation code UCHMPF flight TK140",
                               _TK_FROM, "delay")
    assert k and "UCHMPF" not in k
    assert all(c in "0123456789abcdef" for c in k)


@pytest.mark.parametrize("subject,preview", [
    ("Schedule Change", "your flight time has moved"),   # no reservation code at all
    ("PNR CHANGED", "your PNR CHANGED, please review"),  # stray uppercase word, not a code
])
def test_disruption_dedup_no_key_falls_back(subject, preview):
    # No reliable booking reference -> "" so main() falls back to per-message_id
    # alerting (never silently drops a warning).
    assert E.disruption_dedup_key(subject, preview, _TK_FROM, "schedule_change") == ""


def test_extract_ajet_change():
    src = (FIX / "ajet_change.html").read_text(encoding="utf-8")
    c = E.extract_ajet_change(src, dict(CTX))
    assert c is not None
    assert c["pnr"] == "AJ4X9Z"
    assert c["passenger_name"] == "JOHN DOE"       # not run-on into "Your flight"
    assert c["old_flight_no"] == "VF 100"          # cancel re-numbers VF100 -> VF200
    assert c["status"] == "cancelled"
    nf = c["new_flight"]
    assert (nf["dep_iata"], nf["dep_time"]) == ("LHR", "22:10")
    assert (nf["arr_iata"], nf["arr_time"]) == ("CDG", "02:05")
    assert nf["flight_no"] == "VF 200"
    assert nf["cabin"] == "Economy"


def test_extract_ajet_change_none_on_nonchange():
    # A normal (non-aJet-change) blob has no Reservation Code / New Flight panel.
    assert E.extract_ajet_change("<p>hello world, nothing here</p>") is None


def test_apply_flight_change_by_number():
    booking = {"pnr": "AJ4X9Z", "segments": [{"type": "Outbound", "flights": [
        {"flight_no": "VF 100", "dep_iata": "LHR", "arr_iata": "CDG",
         "dep_time": "01:00", "arr_time": "04:55", "cabin": "Economy"}]}]}
    change = {"old_flight_no": "VF 100", "new_flight": {
        "flight_no": "VF 200", "dep_iata": "LHR", "arr_iata": "CDG",
        "dep_time": "22:10", "arr_time": "02:05", "cabin": "Economy"}}
    assert E.apply_flight_change(booking, change) is True
    f = booking["segments"][0]["flights"][0]
    assert (f["flight_no"], f["dep_time"], f["arr_time"]) == ("VF 200", "22:10", "02:05")


def test_apply_flight_change_by_route_when_number_kept():
    # Delay: same flight number, only times change -> match by route still works.
    booking = {"segments": [{"flights": [
        {"flight_no": "VF 5218", "dep_iata": "HTY", "arr_iata": "SAW",
         "dep_time": "20:10", "arr_time": "21:55"}]}]}
    change = {"old_flight_no": "VF 5218", "new_flight": {
        "flight_no": "VF 5218", "dep_iata": "HTY", "arr_iata": "SAW",
        "dep_time": "22:40", "arr_time": "00:30"}}
    assert E.apply_flight_change(booking, change) is True
    assert booking["segments"][0]["flights"][0]["dep_time"] == "22:40"


def test_apply_flight_change_no_match():
    booking = {"segments": [{"flights": [
        {"flight_no": "VF 999", "dep_iata": "AAA", "arr_iata": "BBB"}]}]}
    change = {"old_flight_no": "VF 100", "new_flight": {
        "flight_no": "VF 200", "dep_iata": "LHR", "arr_iata": "CDG"}}
    assert E.apply_flight_change(booking, change) is False


def _sample_booking():
    return {
        "portal": "aJet", "pnr": "AJ4X9Z", "booking_ref": "AJ4X9Z", "crs_ref": "AJ4X9Z",
        "booked_on": "14 Jul 2026", "journey_type": "RETURN",
        "passengers": [{"name": "John Doe", "ticket_no": "6060000000001",
                        "cabin_bag": "7kg", "checked_bag": "20kg", "seat": "12A"}],
        "segments": [{"type": "Outbound", "flights": [
            {"airline": "aJet", "flight_no": "VF 200", "cabin": "Economy",
             "dep_iata": "LHR", "arr_iata": "CDG", "dep_city": "London", "arr_city": "Paris",
             "dep_date": "19 Jul 2026", "dep_time": "22:10",
             "arr_date": "19 Jul 2026", "arr_time": "02:05", "duration": "3H 55M"}], "layovers": []}],
    }


def test_iso_date():
    assert E._iso_date("19 Jul 2026") == "2026-07-19"
    assert E._iso_date("") is None
    assert E._iso_date("N/A") is None


def test_pivot_os_payload():
    p = E.pivot_os_payload(_sample_booking(), pdf_url="https://drive/x", source_ref="MID123")
    assert p["event"] == "itinerary.created"
    assert p["idempotency_key"] == "AJ4X9Z:confirmed:MID123"   # default status=confirmed
    assert p["reference"]["match_key"] == "AJ4X9Z:aJet"        # composite dup key
    assert p["reference"]["crs_ref"] is None                   # dropped when == pnr
    assert p["reference"]["portal"] == "aJet"
    assert p["journey_type"] == "ROUND TRIP"                   # normalised from RETURN
    assert p["segments"][0]["flights"][0]["dep_date"] == "2026-07-19"   # ISO
    assert p["segments"][0]["flights"][0]["dep_time"] == "22:10"        # time unchanged
    assert p["segments"][0]["flights"][0]["flight_no"] == "VF 200"      # flight-no unchanged
    assert p["route_summary"] == "LHR → CDG"
    assert p["first_dep_date"] == "2026-07-19"
    assert p["financials"] is None                             # always null


def test_pivot_os_payload_status_and_event():
    b = _sample_booking()
    b["doc_status"] = "rebooked"
    p = E.pivot_os_payload(b, event="itinerary.revised", source_ref="MID9")
    assert p["event"] == "itinerary.revised"
    assert p["status"] == "rebooked"
    assert p["idempotency_key"] == "AJ4X9Z:rebooked:MID9"


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
