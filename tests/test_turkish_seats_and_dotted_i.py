"""Turkish Airlines: seats on the document, and a city name that isn't mangled.

Both found on a real one-way KYA→IST→RUH ticket (2026-09-24).

1. The PDF writes place names with Turkish locale capitals — RİYADH, SAUDİ
   ARABİA. Python lowercases U+0130 (İ) to "i" PLUS a combining dot (U+0307), so
   a plain .title() rendered the destination as "Ri̇yadh" on a client document.

2. The same PDF carries an "Additional services / Seat selection" block listing
   a seat per leg. The extractor dropped it — the note in the code said Turkish
   carried no seat data, which was true of the two files it was written against
   in July but not of this one. A seat the client had paid for never reached the
   itinerary.
"""
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(PROJ))

import extractors as E  # noqa: E402


def _booking():
    src = (FIX / "turkish_seats_and_turkish_i.txt").read_text(encoding="utf-8")
    return E.extract_turkish_airlines(src, {"date": "24 Sep 2026"})


def test_qc_passes():
    assert E.qc_check(_booking()) is None


def test_turkish_dotted_capital_does_not_reach_the_city_name():
    legs = _booking()["segments"][0]["flights"]
    arr = legs[-1]["arr_city"]
    assert arr == "Riyadh"
    assert "̇" not in arr          # the combining dot, the actual defect
    assert "İ" not in arr


def test_fold_leaves_other_characters_alone():
    """Only the two Turkish-only letters are touched — not every accent."""
    assert E._tr_clean("TÜRKİYE") == "TÜRKIYE"
    assert E._tr_title("RİYADH") == "Riyadh"
    assert E._tr_clean("München") == "München"
    assert E._tr_clean("") == ""


def test_seat_is_attached_to_the_leg_it_belongs_to():
    legs = _booking()["segments"][0]["flights"]
    assert legs[0]["dep_iata"], legs[0]["arr_iata"] == ("KYA", "IST")
    assert legs[0]["pax"][0]["seat"] == ""      # source states "-" — no seat taken
    assert legs[1]["pax"][0]["seat"] == "19A"   # IST - RUH : 19A


def test_seats_are_not_guessed_for_a_multi_passenger_booking():
    """The block repeats per passenger and its shape there is unverified, so a
    seat must never be attached to a traveller it might not belong to."""
    src = (FIX / "turkish_seats_and_turkish_i.txt").read_text(encoding="utf-8")
    src = src.replace(
        "TEST PASSENGER 0000000000000 The Frequent Flyer Program account has not been",
        "TEST PASSENGER 0000000000000 x\nSECOND PASSENGER 0000000000001 The Frequent Flyer Program account has not been")
    d = E.extract_turkish_airlines(src, {"date": "24 Sep 2026"})
    if len(d["passengers"]) > 1:
        for leg in d["segments"][0]["flights"]:
            for px in leg["pax"]:
                assert px["seat"] == ""
