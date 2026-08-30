"""
A connecting leg that departs after midnight must carry the NEXT day's date.

Real Pegasus booking 2BBZE2 (COV-SAW-JED) shipped to a corporate client with:

    PC2095  COV 20:40 (17 Sep)  ->  SAW 22:15 (17 Sep)
    PC698   SAW 00:50 (17 Sep)  ->  JED 04:35 (17 Sep)

00:50 cannot follow 22:15 on the same day. Pegasus states ONE "Flight Date" for
the whole journey and it was stamped on every leg, so the leg that actually
departs after midnight kept the previous day's date. The client spotted it and
wrote in: "For return ticket from SAW to JED, date should be 18 September."

Nothing surfaced it internally because _diff_hm wraps a negative gap into +24h,
so the layover printed a perfectly correct 2H 35M over an impossible pair of
dates. Two aJet connecting fixtures had frozen the same defect into their
golden snapshots, which is how long it had been shipping.

The correction only ever moves a leg FORWARD, and only when it starts before
the previous leg ended — impossible on a correctly-dated itinerary.
"""
import pytest

import extractors as E


def _leg(fno, di, ai, dd, dt, ad, at):
    return {"flight_no": fno, "airline": "Pegasus", "dep_iata": di, "arr_iata": ai,
            "dep_city": di, "arr_city": ai, "dep_airport": "", "arr_airport": "",
            "terminal": "", "arr_terminal": "", "dep_date": dd, "dep_time": dt,
            "arr_date": ad, "arr_time": at, "cabin": "", "duration": ""}


def test_the_2bbze2_shape_is_corrected():
    flights = [_leg("PC2095", "COV", "SAW", "17 Sep 2026", "20:40", "17 Sep 2026", "22:15"),
               _leg("PC698", "SAW", "JED", "17 Sep 2026", "00:50", "17 Sep 2026", "04:35")]
    E._roll_overnight_connections(flights)
    assert flights[0]["dep_date"] == "17 Sep 2026"      # first leg untouched
    assert flights[1]["dep_date"] == "18 Sep 2026"
    assert flights[1]["arr_date"] == "18 Sep 2026"


def test_layover_still_reads_the_real_connection_time():
    d = E._finalize({"portal": "Pegasus", "pnr": "TEST12", "flights": [
        _leg("PC2095", "COV", "SAW", "17 Sep 2026", "20:40", "17 Sep 2026", "22:15"),
        _leg("PC698", "SAW", "JED", "17 Sep 2026", "00:50", "17 Sep 2026", "04:35")]},
        {"date": "13 Aug 2026"})
    seg = d["segments"][0]
    assert seg["layovers"] == [{"airport": "SAW", "duration": "2H 35M"}]
    assert seg["flights"][1]["dep_date"] == "18 Sep 2026"


def test_a_correctly_dated_connection_is_untouched():
    """The guard is 'starts before the previous leg ended', which a good
    itinerary never does — so nothing correct can be moved."""
    flights = [_leg("XX 1", "AAA", "BBB", "10 Jul 2026", "08:00", "10 Jul 2026", "10:00"),
               _leg("XX 2", "BBB", "CCC", "10 Jul 2026", "13:00", "10 Jul 2026", "17:00")]
    before = [dict(f) for f in flights]
    E._roll_overnight_connections(flights)
    assert flights == before


def test_a_leg_already_dated_the_next_day_is_untouched():
    flights = [_leg("XX 1", "AAA", "BBB", "10 Jul 2026", "20:40", "10 Jul 2026", "23:35"),
               _leg("XX 2", "BBB", "CCC", "11 Jul 2026", "01:00", "11 Jul 2026", "04:55")]
    before = [dict(f) for f in flights]
    E._roll_overnight_connections(flights)
    assert flights == before


def test_a_return_leg_weeks_later_is_untouched():
    """The outbound/inbound split reads these dates, so a genuine round trip
    must not be dragged forward."""
    flights = [_leg("XX 1", "AAA", "BBB", "10 Jul 2026", "08:00", "10 Jul 2026", "10:00"),
               _leg("XX 2", "BBB", "AAA", "24 Jul 2026", "06:00", "24 Jul 2026", "08:00")]
    before = [dict(f) for f in flights]
    E._roll_overnight_connections(flights)
    assert flights == before


def test_an_implausible_gap_is_reported_not_guessed():
    """More than two days back is not a connection — leave the source's dates
    alone rather than invent a plausible-looking one (§7)."""
    flights = [_leg("XX 1", "AAA", "BBB", "10 Jul 2026", "08:00", "10 Jul 2026", "10:00"),
               _leg("XX 2", "BBB", "CCC", "05 Jul 2026", "09:00", "05 Jul 2026", "11:00")]
    before = [dict(f) for f in flights]
    E._roll_overnight_connections(flights)
    assert flights == before


@pytest.mark.parametrize("fixture", ["ajet_connecting.html", "ajet_basic_fare.html"])
def test_ajet_connections_carry_the_right_day(fixture):
    """Both aJet fixtures had the defect frozen into their goldens: leg 2
    departs 01:00 after leg 1 lands 23:35 the previous evening."""
    import pathlib
    fx = pathlib.Path(__file__).resolve().parent / "fixtures" / fixture
    d = E.extract_ajet(fx.read_text(encoding="utf-8"), {"date": "01 Jan 2026"})
    legs = [f for s in d["segments"] for f in s["flights"]]
    assert legs[0]["arr_date"] == "18 Jul 2026" and legs[0]["arr_time"] == "23:35"
    assert legs[1]["dep_date"] == "19 Jul 2026" and legs[1]["dep_time"] == "01:00"
