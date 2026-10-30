"""
Offline regression test for the "Booked On" header cell.

The header facts row draws four cells. Three of them are conditional — Agency Ref.
and CRS Ref. are only appended when they hold a value, and Journey always
resolves to ONE-WAY or ROUND TRIP — so "Booked On" is the ONLY cell that can be
reached with nothing in it.

It used to be read as `data.get("booked_on", "N/A")`. A `.get()` default fires
only when the KEY IS ABSENT, so a key that was present but empty went through
unprotected and the rail drew a bare "BOOKED ON" label with no value beneath it,
sitting out of alignment with JOURNEY beside it.

That was not just a hand-built-data problem: `extract_pegasus` sets
`booked_on = ""` outright, and `_finalize` only backfills it when a ctx date is
supplied. The cloud runner passes the email date, which masked it — but every
manual build and every `\\process` upload rendered the empty label.

Missing values render N/A (§6), so both shapes are locked in here: absent key
and present-but-empty.

Pure stdlib: build_html() imports Playwright only inside build_pdf(), so this
runs with no browser and no network.
"""
import re

import extractors as E
import generate_itinerary_v3 as G


def _booking(**over):
    pax = {"name": "Mr. Test Passenger", "cabin_bag": "7kg",
           "checked_bag": "20kg", "seat": ""}
    base = dict(
        portal="Manual", pnr="TEST01", crs_ref="", booking_ref="",
        status="Confirmed",
        passengers=[{**pax, "ticket_no": "1234567890123"}],
        flights=[{
            "flight_no": "XX 100", "airline": "Test Air",
            "dep_iata": "DOH", "arr_iata": "JED",
            "dep_city": "Doha", "arr_city": "Jeddah",
            "dep_airport": "", "arr_airport": "",
            "terminal": "", "arr_terminal": "1",
            "dep_time": "12:50", "dep_date": "27 Oct 2026",
            "arr_time": "15:35", "arr_date": "27 Oct 2026",
            "cabin": "Economy", "duration": "2H 45M",
            "pax": [dict(pax)],
        }],
    )
    base.update(over)
    return E._finalize(base)


def _booked_on_value(html):
    """The text of the cell whose label is BOOKED ON, or None if it has none."""
    m = re.search(
        r'<div class="fact"><div class="k">Booked on</div><div class="v">(.*?)</div>',
        html, re.S)
    return None if m is None else m.group(1).strip()


def test_booked_on_empty_string_renders_na():
    """A present-but-empty key is the shape that slipped through before."""
    html = G.build_html(_booking(booked_on=""))
    assert _booked_on_value(html) == "N/A"


def test_booked_on_absent_key_renders_na():
    """The shape the old .get() default already handled — must keep working."""
    data = _booking()
    data.pop("booked_on", None)
    html = G.build_html(data)
    assert _booked_on_value(html) == "N/A"


def test_booked_on_real_date_is_untouched():
    """The fix must not disturb a booking that genuinely states a date."""
    html = G.build_html(_booking(booked_on="30 Sep 2026"))
    assert _booked_on_value(html) == "30 Sep 2026"


def test_the_cell_never_renders_a_bare_label():
    """The defect itself: a label with no value under it, at any input."""
    for value in ("", None, "   ", "Not specified"):
        data = _booking(booked_on=value)
        html = G.build_html(data)
        assert _booked_on_value(html), \
            f"BOOKED ON rendered an empty value for {value!r}"


def test_pegasus_manual_path_does_not_render_an_empty_cell():
    """extract_pegasus sets booked_on = "" and no ctx date is supplied here —
    exactly the production shape that reached a client document."""
    import pathlib
    fixture = pathlib.Path(__file__).parent / "fixtures" / "pegasus_roundtrip.html"
    d = E.extract_pegasus(fixture.read_text(encoding="utf-8"), None)
    assert d["booked_on"] == "", "fixture no longer reproduces the empty-date shape"
    assert _booked_on_value(G.build_html(d)) == "N/A"
