"""
Real Akbar/Saudia one-way MNL-JED-RUH (AS261880049) flagged "Passenger name missing" although the name was
printed: Akbar now writes the ticket number WITH the airline-code dash ("065-2400567808"). The name pattern
ended only at a bare run of 10+ digits (or end of line), so "Mr. NAME 065-2400567808" never terminated; and the
ticket pattern would have kept only the last 10 digits, a silently WRONG number (§7). The fixture is synthetic
(zero PII) and reproduces the layout.
"""
import pathlib

import extractors as E

FIX = pathlib.Path(__file__).parent / "fixtures" / "akbar_dashed_ticket.txt"


def _d():
    return E.extract_akbar(FIX.read_text(encoding="utf-8"), {"date": "17 Nov 2026"})


def test_name_and_dashed_ticket_are_read():
    d = _d()
    assert E.qc_check(d) is None
    assert [(p["name"], p["ticket_no"]) for p in d["passengers"]] == [("Mr. TESTA PERSONA", "123-4567890123")]


def test_ticket_keeps_its_airline_code():
    assert _d()["passengers"][0]["ticket_no"].startswith("123-")


def test_bare_digit_ticket_is_unchanged():
    t = FIX.read_text(encoding="utf-8").replace("123-4567890123", "1234567890123")
    d = E.extract_akbar(t, {"date": "17 Nov 2026"})
    assert d["passengers"][0]["ticket_no"] == "1234567890123" and E.qc_check(d) is None
