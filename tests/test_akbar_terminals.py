"""
Akbar terminals, attributed by column POSITION (2026-08-25).

Since 2026-07-17 Akbar terminals were deliberately rendered blank: in the
flattened pdfplumber text a stated terminal is just a bare "Terminal <n>" line
and an unstated one is nothing at all, so the token could not be tied to the
departure or the arrival airport. Guessing had already put the fragment "North"
on the wrong side of a real booking.

Real booking AS261379552 (RUH<->CCJ) shows why the text alone can never settle
it: the SAME airport (Riyadh, Terminal 2) is the DEPARTURE on the outbound leg
and the ARRIVAL on the inbound one, and both render identically as one trailing
"Terminal 2" line. Calicut states no terminal and contributes no token.

In the PDF it is unambiguous — the token's left edge lines up with its column's
header ("From (Terminal)" at x0 101.7, "To (Terminal)" at x0 378.8 on that
document). The word boxes in the fixture are the real measured geometry.
"""
import json
import pathlib

import extractors as E

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
WORDS = json.loads((FIX / "akbar_terminal_words.json").read_text(encoding="utf-8"))


def test_same_airport_as_departure_then_arrival():
    got = E.akbar_terminals_from_words(WORDS)
    assert got[0] == {"dep": "2", "arr": ""}, got[0]     # RUH is the departure
    assert got[1] == {"dep": "", "arr": "2"}, got[1]     # RUH is the arrival


def test_both_sides_stated_and_stray_token_ignored():
    """A token that lines up with NEITHER column is dropped, not guessed."""
    assert E.akbar_terminals_from_words(WORDS)[2] == {"dep": "1", "arr": "I"}


def test_one_result_per_flight_table():
    assert len(E.akbar_terminals_from_words(WORDS)) == 3


def test_no_words_means_no_terminals():
    """The Drive fallback and every .txt fixture supply no boxes; those
    bookings must keep rendering blank terminals exactly as before."""
    assert E.akbar_terminals_from_words([]) == []


def test_extractor_ignores_absent_terminals():
    """Without a terminals ctx key the flight dicts still expose both keys."""
    d = E.extract_akbar((FIX / "akbar_oneway.txt").read_text(encoding="utf-8"),
                        {"date": "20 Aug 2026"})
    for seg in d["segments"]:
        for f in seg["flights"]:
            assert f["terminal"] == "" and f["arr_terminal"] == ""


def test_extractor_applies_terminals_per_segment():
    d = E.extract_akbar((FIX / "akbar_split_carrier.txt").read_text(encoding="utf-8"),
                        {"date": "20 Aug 2026",
                         "terminals": [{"dep": "3", "arr": ""}, {"dep": "", "arr": "5"}]})
    out, ret = d["segments"]
    assert (out["flights"][0]["terminal"], out["flights"][0]["arr_terminal"]) == ("3", "")
    assert (ret["flights"][0]["terminal"], ret["flights"][0]["arr_terminal"]) == ("", "5")
