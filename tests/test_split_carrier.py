"""
Split-carrier Akbar booking: two airlines under ONE agency reference.

Real booking AS261347760 (2026-08-20) — Flyadeal Najran→Riyadh out, Saudia
Riyadh→Najran back — shipped with three defects, all caused by the parser
treating a two-airline booking as if it had one of everything:

  1. ONE reference on the document. Each airline issues its OWN record locator
     (B9PS6D out, 8XMVR7 back). Only the first reached the PDF, so the traveller
     had nothing to check in with on the return leg.
  2. ONE baggage allowance, applied to both legs. The document claimed 32 Kg on
     a Saudia leg that allows 1 × 23 Kg — a wrong fact on a client document (§7),
     not merely a missing one.
  3. NO ticket number. The window ran from the first "Traveler" to the first
     "Carry-On"; on this layout the first Traveler table has no "Ticket No."
     column at all and the number sits in the second one, far past that cut.

The corresponding requirement is that NOTHING changes for a single-reference
booking — asserted in test_extractors.py's golden snapshots and again here on
the rendered HTML.
"""
import pathlib

import pytest

import extractors as E
import generate_itinerary_v3 as G

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
PROJ = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def split():
    return E.extract_akbar((FIX / "akbar_split_carrier.txt").read_text(encoding="utf-8"),
                           {"date": "20 Aug 2026"})


def test_both_airline_references_are_captured(split):
    assert split["pnrs"] == ["AAA111", "BBB222"]
    assert split["pnr"] == "AAA111"          # first ref stays the primary key


def test_each_leg_carries_its_own_reference(split):
    assert [s["flights"][0]["pnr"] for s in split["segments"]] == ["AAA111", "BBB222"]


def test_each_leg_carries_its_own_baggage(split):
    """The return leg's 23 Kg must not be overwritten by the outbound's 32 Kg."""
    out, ret = split["segments"]
    assert G._norm_bag(out["flights"][0]["pax"][0]["checked_bag"]) == "32kg"
    assert G._norm_bag(ret["flights"][0]["pax"][0]["checked_bag"]) == "23kg"
    assert G._norm_bag(out["flights"][0]["pax"][0]["cabin_bag"]) == "7kg"
    assert G._norm_bag(ret["flights"][0]["pax"][0]["cabin_bag"]) == "7kg"


def test_ticket_number_found_in_the_second_traveler_table(split):
    assert split["passengers"][0]["ticket_no"] == "0650000000001"


def test_qc_passes(split):
    assert E.qc_check(split) is None


def test_both_references_render_in_header_footer_and_banners(split):
    html = G.build_html(split, project_dir=str(PROJ), layout="A")
    assert 'class="pnr-value">AAA111 / BBB222<' in html
    assert "PNR References" in html
    assert "AAA111 / BBB222 &nbsp;|&nbsp; WWW.PIVOT-TRAVELS.COM" in html
    assert html.count('class="seg-pnr">PNR AAA111<') == 1
    assert html.count('class="seg-pnr">PNR BBB222<') == 1


def test_single_reference_booking_is_untouched():
    """A one-airline booking must render exactly the locked markup — no banner
    chip, singular label, and the plain <span class="seg-date"> right-hand side."""
    d = E.extract_akbar((FIX / "akbar_oneway.txt").read_text(encoding="utf-8"),
                        {"date": "20 Aug 2026"})
    html = G.build_html(d, project_dir=str(PROJ), layout="A")
    assert 'class="seg-pnr"' not in html
    assert 'class="seg-meta"' not in html
    assert "PNR Reference<" in html
    assert "PNR References" not in html


@pytest.mark.parametrize("data,expected", [
    ({"pnr": "ABC123"}, ["ABC123"]),
    ({"pnr": "ABC123", "pnrs": []}, ["ABC123"]),
    ({"pnr": "ABC123", "pnrs": ["ABC123", "abc123"]}, ["ABC123"]),   # case-dupes collapse
    ({"pnr": "ABC123", "pnrs": ["AAA111", "BBB222"]}, ["AAA111", "BBB222"]),
    ({}, []),
])
def test_booking_refs(data, expected):
    assert G.booking_refs(data) == expected


def test_every_other_portal_still_reports_one_reference():
    """pnrs is derived generically in _finalize; portals that never set a
    per-flight ref must fall back to the single booking-level one."""
    for fx, fn in [("alhind_oneway.html", E.extract_alhind),
                   ("ajet_connecting.html", E.extract_ajet),
                   ("pegasus_roundtrip.html", E.extract_pegasus)]:
        d = fn((FIX / fx).read_text(encoding="utf-8"), {"date": "01 Jan 2026"})
        assert d["pnrs"] == [d["pnr"].upper()], fx
