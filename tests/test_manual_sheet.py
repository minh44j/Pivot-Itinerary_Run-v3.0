"""
Offline tests for the manual-itinerary form (manual_sheet.py).

What matters here is what a person is protected from: a wrong date, a mangled time, a missing field or a
non-existent passenger must be REFUSED with a plain sentence — never guessed, never issued (§7).
Sheets hands back dates/times as numbers (UNFORMATTED_VALUE), so both numeric and text shapes are covered.
"""
import pathlib

import pytest

import extractors as E
import manual_sheet as M

ROOT = pathlib.Path(__file__).resolve().parent.parent
D1, D2 = 46373, 46410          # 17 Dec 2026, 23 Jan 2027 as Sheet serial numbers


def _headers():
    h = [M.TIMESTAMP_HEADER, M.EMAIL_HEADER, "PNR", "Agency reference", "CRS reference", "Booked on"]
    for n in range(1, M.MAX_PASSENGERS + 1):
        h += [M.pax_title(n, f) for f in M.PAX_FIELDS]
    for n in range(1, M.MAX_FLIGHTS + 1):
        h += [M.flight_title(n, f) for f in M.FLIGHT_FIELDS]
        h += [M.flight_title(n, M.SEAT_FIELD.format(k=k)) for k in range(1, M.MAX_PASSENGERS + 1)]
    return h


def _row(**cells):
    h = _headers()
    base = {M.TIMESTAMP_HEADER: "2026-10-31 10:00", M.EMAIL_HEADER: "exec@pivottmc.com", "PNR": "9yp3rj",
            "Booked on": 46300,
            M.pax_title(1, "Title"): "Mr", M.pax_title(1, "Given name(s)"): "Johnson",
            M.pax_title(1, "Surname"): "Mavilayil Samuel", M.pax_title(1, "Ticket number"): "065 2400504044",
            M.flight_title(1, "Flight number"): "sv774", M.flight_title(1, "Operated by (airline)"): "Saudia",
            M.flight_title(1, "From (airport code)"): "ruh", M.flight_title(1, "From city"): "Riyadh",
            M.flight_title(1, "To (airport code)"): "cok", M.flight_title(1, "To city"): "Cochin",
            M.flight_title(1, "Departure date"): D1, M.flight_title(1, "Departure time"): 0.4826,
            M.flight_title(1, "Arrival date"): D1, M.flight_title(1, "Arrival time"): "18:50",
            M.flight_title(1, "Cabin class"): "Economy", M.flight_title(1, "Duration"): "4h 45m",
            M.flight_title(1, "Checked baggage"): "2 pieces", M.flight_title(1, M.SEAT_FIELD.format(k=1)): "33d"}
    base.update(cells)
    return h, [base.get(x, "") for x in h]


def test_a_complete_row_becomes_a_booking_that_passes_qc():
    d, problems, meta = M.parse_row(*_row())
    assert problems == [] and E.qc_check(d) is None
    f = d["segments"][0]["flights"][0]
    assert d["pnr"] == "9YP3RJ" and d["portal"] == "Manual"
    assert d["passengers"] == [{"name": "Mr. Johnson Mavilayil Samuel", "ticket_no": "0652400504044"}]
    assert (f["flight_no"], f["dep_iata"], f["arr_iata"]) == ("SV 774", "RUH", "COK")
    assert (f["dep_time"], f["arr_time"], f["dep_date"], f["duration"]) == ("11:35", "18:50", "17 Dec 2026", "4H 45M")
    assert f["pax"][0]["seat"] == "33D" and f["pax"][0]["checked_bag"] == "2 pieces"
    assert d["booked_on"] == "05 Oct 2026"
    assert meta["email"] == "exec@pivottmc.com" and meta["pnr"] == "9YP3RJ"


def test_a_round_trip_with_two_passengers_and_a_separate_airline_reference():
    h, r = _row(**{M.pax_title(2, "Title"): "Mrs", M.pax_title(2, "Given name(s)"): "Mary", M.pax_title(2, "Surname"): "Samuel",
                   M.pax_title(2, "Ticket number"): "0652400504045", M.flight_title(1, M.SEAT_FIELD.format(k=2)): "33E",
                   M.flight_title(2, "Flight number"): "SV 775", M.flight_title(2, "Operated by (airline)"): "Saudia",
                   M.flight_title(2, "From (airport code)"): "COK", M.flight_title(2, "From city"): "Cochin",
                   M.flight_title(2, "To (airport code)"): "RUH", M.flight_title(2, "To city"): "Riyadh",
                   M.flight_title(2, "Departure date"): D2, M.flight_title(2, "Departure time"): "20:20",
                   M.flight_title(2, "Arrival date"): D2, M.flight_title(2, "Arrival time"): "23:20",
                   M.flight_title(2, "Cabin class"): "Economy", M.flight_title(2, "Airline reference"): "zz9yy8"})
    d, problems, _ = M.parse_row(h, r)
    assert problems == []
    assert d["journey_type"].upper() in ("ROUND TRIP", "RETURN")
    assert [p["name"] for p in d["passengers"]] == ["Mr. Johnson Mavilayil Samuel", "Mrs. Mary Samuel"]
    flights = [f for s in d["segments"] for f in s["flights"]]
    assert [p["seat"] for p in flights[0]["pax"]] == ["33D", "33E"]
    assert flights[0]["pnr"] == "9YP3RJ" and flights[1]["pnr"] == "ZZ9YY8"
    assert d["pnrs"] == ["9YP3RJ", "ZZ9YY8"]          # both references reach the document


@pytest.mark.parametrize("cell,value,fragment", [
    ("PNR", "AB", "PNR must be"),
    (M.pax_title(1, "Ticket number"), "12345", "ticket number must be 10 to 14 digits"),
    (M.flight_title(1, "From (airport code)"), "RYD1", "airport code must be 3 letters"),
    (M.flight_title(1, "Flight number"), "S", "flight number should look like"),
    (M.flight_title(1, "Departure time"), "25:99", "departure time must look like"),
    (M.flight_title(1, "Departure date"), "03/04/2026", "departure date could not be read"),
    (M.flight_title(1, "Duration"), "long", "duration not understood"),
    (M.flight_title(1, M.SEAT_FIELD.format(k=1)), "seat 14", "seat for passenger 1 should look like 14A"),
    (M.flight_title(1, M.SEAT_FIELD.format(k=3)), "14A", "there is no passenger 3"),
])
def test_bad_values_are_refused_with_a_plain_sentence(cell, value, fragment):
    d, problems, _ = M.parse_row(*_row(**{cell: value}))
    assert d is None
    assert any(fragment in p for p in problems), problems


def test_a_missing_required_field_names_it():
    d, problems, _ = M.parse_row(*_row(**{M.flight_title(1, "Arrival time"): ""}))
    assert d is None and any("Flight 1: missing arrival time" in p for p in problems)


def test_arrival_before_departure_date_is_refused():
    d, problems, _ = M.parse_row(*_row(**{M.flight_title(1, "Arrival date"): D1 - 1}))
    assert d is None and any("arrival date is before the departure date" in p for p in problems)


def test_an_empty_form_asks_for_passenger_and_flight():
    h = _headers()
    d, problems, _ = M.parse_row(h, [""] * len(h))
    assert d is None
    assert any("PNR" in p for p in problems) and any("Passenger 1" in p for p in problems) and any("Flight 1" in p for p in problems)


def test_booked_on_is_optional_and_renders_na_not_a_guess():
    d, problems, _ = M.parse_row(*_row(**{"Booked on": ""}))
    assert problems == [] and d["booked_on"] == ""


@pytest.mark.parametrize("raw,expected", [(0.4826, "11:35"), (0.0, "00:00"), ("9:05", "09:05"), ("11:35:00", "11:35"),
                                          ("24:00", None), ("noon", None), (1.5, None), ("", None)])
def test_time_shapes(raw, expected):
    assert M.to_time(raw) == expected


@pytest.mark.parametrize("raw,expected", [(46373, "2026-12-17"), ("2026-12-17", "2026-12-17"), ("17 Dec 2026", "2026-12-17"),
                                          ("12/17/2026", None), ("", None), (None, None)])
def test_date_shapes_and_ambiguous_text_is_refused(raw, expected):
    d = M.to_date(raw)
    assert (d.isoformat() if d else None) == expected


def test_every_question_title_the_runner_reads_exists_in_the_apps_script():
    """manual_sheet.py reads the sheet BY TITLE; if create_manual_form.gs renames one, rows stop parsing."""
    gs = (ROOT / "manual_form" / "create_manual_form.gs").read_text(encoding="utf-8")
    for f in M.BOOKING_FIELDS:
        assert f"'{f}'" in gs, f
    for f in M.PAX_FIELDS:
        assert f"' - {f}'" in gs, f
    for f in M.FLIGHT_FIELDS:
        assert f"P + '{f}'" in gs, f
    assert "P + 'Seat, passenger '" in gs
    assert f"var MAX_PASSENGERS = {M.MAX_PASSENGERS};" in gs and f"var MAX_FLIGHTS = {M.MAX_FLIGHTS};" in gs
