"""
Offline regression tests for the portal extractors.

These run with NO network and NO Google/Playwright — they feed saved SYNTHETIC
fixtures (fake PNRs/passengers; never real inbox data) through each extractor and
assert two things:

  1. qc_check() reaches the expected verdict (pass, or a specific flag).
  2. The full parsed dict still matches a committed "golden" snapshot, so any
     future edit that changes extractor output is caught immediately.

Regenerate the golden snapshots after an INTENTIONAL change:

    UPDATE_GOLDEN=1 python -m pytest tests/ -q

Then eyeball the git diff under tests/expected/ before committing.
"""
import json
import os
import pathlib

import pytest

import extractors as E

ROOT = pathlib.Path(__file__).resolve().parent
FIX = ROOT / "fixtures"
EXP = ROOT / "expected"
CTX = {"date": "01 Jan 2026"}   # fixed booked_on fallback -> deterministic output

# fixture filename -> (extractor, expected qc substring or None for "must pass")
CASES = {
    "ajet_connecting.html":            (E.extract_ajet,    None),
    "alhind_oneway.html":              (E.extract_alhind,  None),
    "pegasus_roundtrip.html":          (E.extract_pegasus, None),
    "akbar_oneway.txt":                (E.extract_akbar,   None),
    "neg_ajet_missing_pnr.html":       (E.extract_ajet,    "Missing PNR"),
    "neg_akbar_missing_flightno.txt":  (E.extract_akbar,   "missing flight number"),
}


def _run(fixture):
    fn, _ = CASES[fixture]
    src = (FIX / fixture).read_text(encoding="utf-8")
    return fn(src, dict(CTX))


@pytest.mark.parametrize("fixture", list(CASES))
def test_qc(fixture):
    _, expected = CASES[fixture]
    qc = E.qc_check(_run(fixture))
    if expected is None:
        assert qc is None, f"{fixture}: expected QC to PASS, got {qc!r}"
    else:
        assert qc and expected.lower() in qc.lower(), \
            f"{fixture}: expected QC flag containing {expected!r}, got {qc!r}"


@pytest.mark.parametrize("data,expected", [
    # international arrival into India -> True (triggers Air Suvidha attachment)
    ({"segments": [{"flights": [{"dep_iata": "IST", "arr_iata": "DEL"}]}]}, True),
    ({"segments": [{"flights": [{"dep_iata": "DXB", "arr_iata": "COK"}]}]}, True),
    # round trip India<->abroad: return leg lands in India -> True
    ({"segments": [{"flights": [{"dep_iata": "BOM", "arr_iata": "IST"}]},
                   {"flights": [{"dep_iata": "IST", "arr_iata": "BOM"}]}]}, True),
    # purely domestic Indian hop -> False (no international arrival)
    ({"segments": [{"flights": [{"dep_iata": "DEL", "arr_iata": "BOM"}]}]}, False),
    # nothing touching India -> False
    ({"segments": [{"flights": [{"dep_iata": "IST", "arr_iata": "SAW"}]}]}, False),
    # India -> abroad only (outbound, no arrival into India) -> False
    ({"segments": [{"flights": [{"dep_iata": "MAA", "arr_iata": "SIN"}]}]}, False),
])
def test_india_arrival(data, expected):
    assert E.india_arrival(data) is expected


@pytest.mark.parametrize("fixture", list(CASES))
def test_snapshot(fixture):
    data = _run(fixture)
    golden_path = EXP / (fixture + ".json")
    if os.environ.get("UPDATE_GOLDEN"):
        golden_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        return
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert data == golden, (
        f"{fixture}: extractor output changed vs golden snapshot. "
        f"If intentional, re-run with UPDATE_GOLDEN=1 and review the diff."
    )
