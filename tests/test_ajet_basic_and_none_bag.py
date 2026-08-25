"""
Two defects found on real aJet round trip 4B0NA3 (RUH-SAW-RUH, 2026-08-15).

Both showed up on the SAME document, which is what made them obvious: the
outbound leg read "Economy / 8kg / 20kg" and the inbound leg read
"N/A / None / None" for a booking the traveller had actually paid baggage on.

  1. FARE BRAND. aJet sells "Basic" alongside ECOJET / BIZJET / PREMIUM, and
     writes it in MIXED case while the others are uppercase. It was missing from
     the brand alternation, so the leg's cabin fell through to "Not specified".
     Case-insensitivity is scoped to that one alternative — widening the whole
     segment regex would let the [A-Z]{3} IATA groups match lowercase text.

  2. LITERAL "None". aJet prints the word "None" when a leg carries no
     allowance ("Total Check-in Baggage None"). That is real source text, not a
     Python artifact, so it was rendered verbatim and the word "None" appeared
     on a client's flight card — which reads as a software fault. It means "not
     stated", so it normalises to N/A like any other empty value.
"""
import pathlib

import pytest

import extractors as E
import generate_itinerary_v3 as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


def test_basic_fare_brand_maps_to_economy():
    """Both legs must report a cabin — one ECOJET, one Basic."""
    data = E.extract_ajet((FIX / "ajet_basic_fare.html").read_text(encoding="utf-8"),
                          {"date": "01 Jan 2026"})
    cabins = [f["cabin"] for s in data["segments"] for f in s["flights"]]
    assert cabins == ["Economy", "Economy"], cabins


def test_uppercase_brands_still_map():
    """The scoped (?i:) must not disturb the pre-existing uppercase brands."""
    data = E.extract_ajet((FIX / "ajet_connecting.html").read_text(encoding="utf-8"),
                          {"date": "01 Jan 2026"})
    for s in data["segments"]:
        for f in s["flights"]:
            assert f["cabin"] == "Economy"


@pytest.mark.parametrize("raw", ["None", "none", "NONE", " None ", "N/A", "-",
                                 "Not specified", ""])
def test_empty_ish_baggage_renders_na(raw):
    assert G._norm_bag(raw) == "N/A"


@pytest.mark.parametrize("raw,expected", [
    ("8kg", "8kg"),
    ("20 kg", "20kg"),
    ("1 piece - 8 kg (55x40x23 cm)", "8kg"),
    ("Total Check-in Baggage 20 kg Maximum", "20kg"),
])
def test_real_values_survive(raw, expected):
    """The N/A shortcut must not swallow a genuine allowance."""
    assert G._norm_bag(raw) == expected


def test_none_never_reaches_a_flight_card():
    """End-to-end guard: the word 'None' must not render on the card."""
    html = G._flight_card({
        "flight_no": "VF 213", "airline": "aJet", "dep_iata": "SAW", "arr_iata": "RUH",
        "dep_city": "Istanbul", "arr_city": "Riyadh", "dep_airport": "", "arr_airport": "",
        "terminal": "", "arr_terminal": "", "dep_date": "22 Aug 2026", "dep_time": "21:15",
        "arr_date": "23 Aug 2026", "arr_time": "01:40 (+1)", "cabin": "Economy",
        "duration": "4H 25M",
        "pax": [{"name": "Test Pax", "cabin_bag": "None", "checked_bag": "None", "seat": ""}],
    })
    assert ">None<" not in html


# ── piece count on multi-piece allowances (2026-08-19, approved) ───────────
# Weight alone understates a multi-piece allowance. Saudia via Akbar states
# "Adult - 2 Pieces | 1 BAG UP TO 23KG" (real booking 8CP5SK) = two 23kg bags;
# rendering "23kg" reads as one bag and a passenger could leave 23kg unused.
@pytest.mark.parametrize("raw,expected", [
    ("Adult - 2 Pieces | 1 BAG UP TO 23KG", "2 &times; 23kg"),
    ("Adult - 3 Pieces | 1 BAG UP TO 32KG", "3 &times; 32kg"),
])
def test_multi_piece_shows_the_count(raw, expected):
    assert G._norm_bag(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # single piece -> unchanged, exactly as the locked weight-only rule
    ("Adult 1Pc : 1 BAG UP TO 7 KG", "7kg"),
    ("20 Kg 1 Piece", "20kg"),
    ("1 piece - 8 kg (55x40x23 cm)", "8kg"),
    ("30 kg", "30kg"),
    # several weights already enumerate the pieces — no count prefix
    ("7kg + 3kg", "7kg + 3kg"),
    # piece-only, no weight stated -> the pre-existing "<n>Pcs" form
    ("3 Pieces", "3Pcs"),
])
def test_single_piece_and_multi_weight_render_unchanged(raw, expected):
    """The count must be added ONLY where it adds information, so no existing
    booking's card changes."""
    assert G._norm_bag(raw) == expected


# ── wrapped / bled "Operated by:" cell (2026-08-19) ────────────────────────
# Real booking 8CP5SK shipped with "OPERATED BY: Saudi Mon" — a carrier that
# does not exist. Akbar's PDF renders:
#     Operated by:Saudi Mon, 24 Aug 26 (02h:45m) Egypt, Mon, 24 Aug 26
#     Airline Saudi Arabia,
# so the date column's weekday glued onto the name and the real name ("Saudi
# Airline") was split across two lines.
@pytest.mark.parametrize("raw,expected", [
    ("Operated by:Saudi Mon, 24 Aug 26 (02h:45m) Egypt, Mon, 24 Aug 26\n"
     "Airline Saudi Arabia,\nTerminal 2", "Saudi Airline"),
    # a weekday with no continuation line is simply stripped
    ("Operated by:Fly Jinnah Tue, 25 Aug 26", "Fly Jinnah"),
])
def test_wrapped_or_bled_carrier_cell(raw, expected):
    assert E._akbar_airline(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # every previously-working shape must be untouched
    ("Operated by:Air Sial", "Air Sial"),
    ("Operated , Thu, 23 Jul 26 (02h:10m)\nby:Flyadeal Saudi Arabia,", "Flyadeal"),
    ("Operated by: Saudi Arabian Airlines", "Saudi Arabian Airlines"),
    ("Operated by : TestAir", "TestAir"),
    ("no operator line here", ""),
])
def test_existing_carrier_shapes_unchanged(raw, expected):
    assert E._akbar_airline(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # Saudia's e-ticket writes the same multi-piece fact as "NxWEIGHT"
    # (2026-08-24, booking 873UGS: "2X23 KG" per passenger on the outbound)
    ("2X23 KG", "2 &times; 23kg"),
    ("2x23kg", "2 &times; 23kg"),
    # a count of one, and packing dimensions, must never gain a prefix
    ("1X23 KG", "23kg"),
    ("1 piece - 8 kg (55x40x23 cm)", "8kg"),
])
def test_n_x_weight_form(raw, expected):
    assert G._norm_bag(raw) == expected


# ── several passenger TYPES in one allowance string (2026-08-25) ───────────
# Real Akbar/Saudia booking AS261379552 states
#   "Adult - 2 Pieces | 1 BAG UP TO 32KG | Infant - 1 Piece | 1 Piece equals 23KG"
# The 32KG and the 23KG belong to DIFFERENT travellers, so merging them printed
# "32kg + 23kg" — 55kg — on every passenger's row. Keep the first type's block.
@pytest.mark.parametrize("raw,expected", [
    ("Adult - 2 Pieces | 1 BAG UP TO 32KG | Infant - 1 Piece | 1 Piece equals 23KG",
     "2 &times; 32kg"),
    ("Adult 1Pc : 1 BAG UP TO 12 KG | Infant 0Pc :", "12kg"),
    ("Adult - 2 Piece | Child - 2 Piece |", "2Pcs"),
])
def test_multi_passenger_type_allowance(raw, expected):
    assert G._norm_bag(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    # ONE type, or none at all -> untouched. "7kg + 3kg" is a single traveller
    # with two bags and must keep both weights.
    ("Adult - 2 Pieces | 1 BAG UP TO 23KG", "2 &times; 23kg"),
    ("7kg + 3kg", "7kg + 3kg"),
    ("Adult - 1 PC | 1 Piece equal 23 Kg", "23kg"),
    ("Adult 07 Kg", "7kg"),
])
def test_single_type_allowance_unchanged(raw, expected):
    assert G._norm_bag(raw) == expected
