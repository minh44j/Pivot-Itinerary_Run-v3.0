"""
Offline tests for the redesigned internal e-mails (email_templates.py, 2026-10-31).

Each e-mail answers "what do I do next, and can I trust it?" — so the tests lock the things a person
acts on: the next step is stated, every source e-mail has a working link, a missing value is reported
and never filled in, and a notice's facts are only ever the ones the text actually contains.
"""
import pathlib
import re

import pytest

import email_templates as T
import extractors as E

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


def _booking(**over):
    pax = lambda n, s: {"name": n, "cabin_bag": "7kg", "checked_bag": "2Pcs", "seat": s}
    leg = lambda no, di, ai, dc, ac, dt, dd, at, p: {
        "flight_no": no, "airline": "Test Air", "dep_iata": di, "arr_iata": ai, "dep_city": dc, "arr_city": ac,
        "dep_airport": "", "arr_airport": "", "terminal": "", "arr_terminal": "", "dep_time": dt, "dep_date": dd,
        "arr_time": at, "arr_date": dd, "cabin": "Economy", "duration": "4H 45M", "pax": p}
    base = dict(portal="Akbar", pnr="TEST01", booking_ref="AG123", crs_ref="CRS456", booked_on="26 Oct 2026", status="Confirmed",
                passengers=[{"name": "Mr. A One", "ticket_no": "111"}, {"name": "Mrs. B Two", "ticket_no": "222"}],
                flights=[leg("XX 1", "RUH", "COK", "Riyadh", "Cochin", "11:35", "17 Dec 2026", "18:50",
                             [pax("Mr. A One", "33D"), pax("Mrs. B Two", "33E")]),
                         leg("XX 2", "COK", "RUH", "Cochin", "Riyadh", "20:20", "23 Jan 2027", "23:20",
                             [pax("Mr. A One", "31C"), pax("Mrs. B Two", "31D")])])
    base.update(over)
    return E._finalize(base)


# ---- confirmation ---------------------------------------------------------------------------
def test_confirmation_says_what_to_do_next_and_shows_the_reference_large():
    h = T.confirmation_html(_booking(), "SRC1", None)
    assert "Itinerary ready" in h and "forward it to the client" in h
    assert re.search(r'font-size:44px[^>]*>TEST01<', h)


def test_confirmation_subject_keeps_the_old_prefix_and_adds_route_and_date():
    s = T.confirmation_subject(_booking())
    assert s.startswith("Booking Confirmation — TEST01 (Akbar)")
    assert "RUH→COK" in s and "17 Dec" in s


def test_each_passenger_seat_is_shown_per_leg():
    h = T.confirmation_html(_booking(), "", None)
    for seat in ("33D", "33E", "31C", "31D"):
        assert seat in h


def test_a_missing_booked_on_is_reported_not_filled_in():
    d = _booking(booked_on="")
    d["booked_on"] = ""
    notes = T.attention_points(d)
    assert any("Booked-on" in n for n in notes)
    assert "Worth a look" in T.confirmation_html(d, "", None)


def test_revision_two_and_india_arrival_are_flagged():
    d = _booking(revision=2)
    assert any(n.startswith("Revision 2") for n in T.attention_points(d))
    d["segments"][0]["flights"][0]["arr_iata"] = "COK"           # RUH -> COK is an international arrival in India
    assert any(n.startswith("India arrival") for n in T.attention_points(d))


def test_a_clean_booking_has_nothing_to_look_at():
    d = _booking()
    for seg in d["segments"]:
        for f in seg["flights"]:
            for k in ("dep_iata", "arr_iata"):
                if f[k] == "COK":
                    f[k] = "DXB"                     # no India arrival -> no Air Suvidha note
    assert E.india_arrival(d) is False
    assert T.attention_points(d) == []
    assert "Worth a look" not in T.confirmation_html(d, "", None)


def test_confirmation_text_twin_carries_the_same_facts():
    t = T.confirmation_text(_booking(revision=2), "SRC1")
    for needle in ("TEST01", "Mr. A One", "222", "XX 2", "33E", "Revision 2", "SRC1", "forward it to the client"):
        assert needle in t


# ---- manual review --------------------------------------------------------------------------
@pytest.mark.parametrize("reason,fragment", [
    ("A segment is missing flight number / airport / time", "flight number"),
    ("Missing PNR", "booking reference"),
    ("no passengers", "passenger"),
    ("Status not Confirmed", "confirmed"),
    ("something nobody anticipated", "could not be turned into an itinerary"),
])
def test_plain_language_reason(reason, fragment):
    assert fragment in T.plain_reason(reason).lower()


def test_flags_email_has_a_working_link_and_the_source_ref_for_every_booking():
    flagged = [{"portal": "Akbar", "reason": "Missing PNR", "subject": "Booking Success", "id": "abc123"},
               {"portal": "aJet", "reason": "x", "subject": "", "id": "def456"}]
    h, t = T.flags_html(flagged, None), T.flags_text(flagged)
    for mid in ("abc123", "def456"):
        assert T.gmail_link(mid) in h and T.gmail_link(mid) in t and mid in h
    assert "2 bookings need a person" in h
    assert "nothing was sent" in h


# ---- disruption -----------------------------------------------------------------------------
ALERTS = [
    {"from": "Turkish Airlines <onlineticket@mail.turkishairlines.com>", "subject": "Turkish Airlines - Flight Delay Information",
     "date": "Fri, 30 Oct 2026 13:39:00 +0300", "snippet": "Reservation code UCHMPF: TK 2255 IST-ESB on 30 Oct", "id": "m1", "keyword": "delay"},
    {"from": "aJet <x@mail.ajet.com>", "subject": "Your flight has been cancelled", "date": "Fri, 30 Oct 2026 09:05:00 +0300",
     "snippet": "PNR 8JS4ID cancelled", "id": "m2", "keyword": "cancel", "revised_pdf": "/tmp/REVISED-8JS4ID.pdf"},
]


def test_alerts_are_sorted_most_urgent_first_and_the_subject_names_the_bookings():
    en = T.enrich(ALERTS)
    assert [a["category"] for a in en] == ["cancellation", "delay"]
    s = T.disruption_subject(en)
    assert s.startswith("⚠️ ACTION REQUIRED") and "1 cancellation, 1 delay" in s and "8JS4ID" in s and "UCHMPF" in s


def test_alert_card_has_link_airline_name_and_the_revised_draft_note():
    h = T.disruption_html(T.enrich(ALERTS), None)
    assert T.gmail_link("m1") in h and T.gmail_link("m2") in h
    assert "Turkish Airlines — flight delayed" in h and "aJet — flight cancelled" in h
    assert "Draft revised itinerary attached" in h and "REVISED-8JS4ID.pdf" in h
    assert "What to do, for each alert" in h


def test_a_summary_contains_only_what_the_text_says():
    s = E.disruption_summary("Update", "Dear guest, your flight has changed.", "noreply@mail.flypgs.com")
    assert s["pnr"] == "" and s["flights"] == [] and s["routes"] == [] and s["dates"] == [] and s["times"] == []
    assert s["airline"] == "Pegasus"


def test_times_are_listed_not_arrowed_so_old_and_new_are_never_swapped():
    h = T.disruption_html(T.enrich([{**ALERTS[0], "snippet": "UCHMPF new time 22:40 instead of 21:15"}]), None)
    assert "22:40 · 21:15" in h and "22:40 → 21:15" not in h


@pytest.mark.parametrize("raw,expected", [
    ("Fri, 30 Oct 2026 13:39:00 +0300", "30 Oct · 13:39"),
    ("Fri, 30 Oct 2026 10:39:00 +0000", "30 Oct · 13:39"),      # converted to Riyadh time
    ("not a date", "not a date"),
    ("", "N/A"),
])
def test_received_is_shown_in_riyadh_time(raw, expected):
    assert T.received(raw) == expected


def test_no_serif_and_no_dark_band_in_any_email():
    en = T.enrich(ALERTS)
    for h in (T.confirmation_html(_booking(), "", None), T.flags_html([{"portal": "x", "reason": "y", "id": "z"}], None),
              T.disruption_html(en, None)):
        assert "Cormorant" not in h and "linear-gradient" not in h
