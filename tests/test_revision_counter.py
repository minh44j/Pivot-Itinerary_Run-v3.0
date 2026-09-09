"""Revision counter — the number that tells two copies of one booking apart.

8JS4ID and 8JVF9L were both reissued in Sep 2026, and each time the client
received a second PDF carrying the same reference, the same "Booked On" date and
nothing to say which was current. A passenger travelling on the older print-out
goes to the wrong gate at the wrong hour.

Two properties matter and are asserted here: the key is PUBLIC-SAFE (the repo is
public, so no PNR may be written to the counter file — §11), and the number is
stable per booking however the reference is spelled or ordered.
"""
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))

import extractors as E                     # noqa: E402
import generate_itinerary_v3 as G          # noqa: E402


def test_key_never_contains_the_reference():
    """The whole point of hashing: the public repo must not carry the PNR."""
    key = E.revision_key("9L6WUH")
    assert "9L6WUH" not in key
    assert len(key) == 16 and all(c in "0123456789abcdef" for c in key)


def test_key_is_stable_across_case_order_and_whitespace():
    a = E.revision_key(["B9PS6D", "8XMVR7"])
    assert a == E.revision_key(["8XMVR7", "b9ps6d"])
    assert a == E.revision_key([" b9ps6d ", "8xmvr7"])
    assert a == E.revision_key(["B9PS6D", "", "8XMVR7", None])


def test_different_bookings_get_different_keys():
    assert E.revision_key("9L6WUH") != E.revision_key("8JS4ID")


def test_no_reference_gives_no_key():
    """An empty key must not lump unrelated bookings under one counter."""
    assert E.revision_key([]) == ""
    assert E.revision_key("") == ""
    assert E.revision_key(["   "]) == ""


def _hdr(rev):
    """Header markup for a minimal booking carrying the given revision."""
    data = {
        "pnr": "9L6WUH", "booking_ref": "AS000000001", "booked_on": "08 Sep 2026",
        "journey_type": "ONE-WAY", "status": "Confirmed",
        "passengers": [{"name": "Ms. Test Passenger", "ticket_no": "0650000000000"}],
        "segments": [{"type": "OUTBOUND", "layovers": [], "flights": [{
            "flight_no": "SV 310", "airline": "Saudi Arabian Airlines",
            "dep_iata": "CAI", "arr_iata": "RUH", "dep_city": "Cairo",
            "arr_city": "Riyadh", "dep_airport": "", "arr_airport": "",
            "terminal": "", "arr_terminal": "",
            "dep_time": "11:40", "dep_date": "16 Sep 2026",
            "arr_time": "14:25", "arr_date": "16 Sep 2026",
            "cabin": "Economy", "duration": "2H 45M", "pax": [],
        }]}],
    }
    if rev is not None:
        data["revision"] = rev
    return G.build_html(data, project_dir=str(PROJ), layout="A")


def test_first_issue_prints_no_revision():
    """"Revision 1" tells the reader nothing; the stamp starts at the reissue."""
    assert "Revision" not in _hdr(1)
    assert "Revision" not in _hdr(0)
    assert "Revision" not in _hdr(None)


def test_reissue_prints_its_number():
    assert "Revision 2" in _hdr(2)
    assert "Revision 7" in _hdr(7)


def test_a_junk_revision_value_prints_nothing_rather_than_guessing():
    for bad in ("", "two", {}, [], "3x"):
        assert "Revision" not in _hdr(bad)
