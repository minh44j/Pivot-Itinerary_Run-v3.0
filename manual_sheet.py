"""
Manual itinerary entry — a person types a ticket into the "Manual itinerary" Google Sheet; this module turns
the sheet's cells into the same booking dict the portal extractors produce, so the normal QC gate, revision
counter, PDF generator and e-mail apply unchanged.

PURE: no Google imports and nothing printed, so the offline suite can import it and the public Action log
can never carry a passenger name. main.py owns reading/writing the Sheet and sending the e-mail.

ONE source of truth for the layout: tools/build_manual_sheet.py generates the workbook from the constants
below, and the runner reads it with the same constants, so the sheet and the runner cannot drift apart.
`parse_row` is the validator: it works on {question title -> value}, and `grid_to_form` maps the sheet's cells
onto those titles.
"""
import re
from datetime import date, datetime, timedelta

import extractors

# The PDF carries passenger names and ticket numbers, so it may only be sent to a Pivot mailbox.
ALLOWED_RECIPIENT_DOMAINS = ("pivottmc.com", "pivot-travels.com")
MAX_PASSENGERS = 4
MAX_FLIGHTS = 6

# ── question titles (the contract with the Apps Script) ────────────────────────
BOOKING_FIELDS = ("PNR", "Agency reference", "CRS reference", "Booked on")
PAX_FIELDS = ("Title", "Given name(s)", "Surname", "Ticket number")
FLIGHT_FIELDS = ("Flight number", "Operated by (airline)", "From (airport code)", "From city",
                 "To (airport code)", "To city", "Departure date", "Departure time", "Arrival date",
                 "Arrival time", "Departure terminal", "Arrival terminal", "Cabin class", "Duration",
                 "Cabin baggage", "Checked baggage", "Airline reference")
SEAT_FIELD = "Seat, passenger {k}"
EMAIL_HEADER = "Email Address"
STATUS_HEADER = "Runner status"
TIMESTAMP_HEADER = "Timestamp"


def pax_title(n, field):
    return f"Passenger {n} - {field}"


def flight_title(n, field):
    return f"Flight {n} - {field}"


def _s(v):
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()


# ── value parsers (Sheets returns dates/times as numbers with UNFORMATTED_VALUE) ──
def to_date(v):
    """Sheet date serial, ISO string, or 'DD Mon YYYY' -> date, else None. Locale-ambiguous strings such as
    03/04/2026 are REFUSED rather than guessed (a wrong travel date is worse than a question)."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        try:
            return date(1899, 12, 30) + timedelta(days=int(v))
        except (OverflowError, ValueError):
            return None
    t = _s(v)
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(d):
    return d.strftime("%d %b %Y")


def to_time(v):
    """'11:35', '9:05', '11:35:00' or a Sheet time fraction (0.4826) -> 'HH:MM', else None."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        if 0 <= float(v) < 1:
            mins = int(round(float(v) * 1440)) % 1440
            return f"{mins // 60:02d}:{mins % 60:02d}"
        return None
    m = re.match(r"^(\d{1,2}):([0-5]\d)(?::[0-5]\d)?$", _s(v))
    if m and int(m.group(1)) < 24:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def norm_duration(v):
    t = _s(v)
    if not t:
        return ""
    m = re.match(r"^(\d{1,2})\s*h(?:ours?|rs?)?\s*(?:(\d{1,2})\s*m(?:in(?:ute)?s?)?)?$", t, re.I) \
        or re.match(r"^(\d{1,2}):([0-5]\d)$", t)
    if not m:
        return None
    return f"{int(m.group(1))}H {int(m.group(2) or 0):02d}M"


def norm_flight_no(v):
    m = re.match(r"^([A-Z0-9]{2})\s*-?\s*(\d{1,4}[A-Z]?)$", _s(v).upper())
    return f"{m.group(1)} {m.group(2)}" if m else None


# ── the row -> booking conversion ──────────────────────────────────────────────
def parse_row(headers, row):
    """Return (data, problems, meta). `problems` is a list of plain-language strings; when it is not empty
    `data` must NOT be issued. meta = {'email', 'submitted', 'pnr'} (for the reply e-mail / logs)."""
    cells = {}
    for i, h in enumerate(headers):
        cells[_s(h)] = row[i] if i < len(row) else ""
    get = lambda k: cells.get(k, "")
    problems = []
    meta = {"email": _s(get(EMAIL_HEADER)), "submitted": _s(get(TIMESTAMP_HEADER)), "pnr": ""}

    to = meta["email"].lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
        problems.append("Send the PDF to: type your own Pivot e-mail address (cell B9).")
    elif to.rsplit("@", 1)[1] not in ALLOWED_RECIPIENT_DOMAINS:
        problems.append("Send the PDF to: it must be a Pivot address (…@pivottmc.com) — it contains passenger data.")

    pnr = _s(get("PNR")).upper()
    meta["pnr"] = pnr
    if not re.fullmatch(r"[A-Z0-9]{5,8}", pnr):
        problems.append("PNR must be 5 to 8 letters or digits.")
    booked = get("Booked on")
    booked_s = ""
    if _s(booked):
        d = to_date(booked)
        if d is None:
            problems.append("Booked on: the date could not be read — pick it from the calendar.")
        else:
            booked_s = fmt_date(d)

    # passengers
    passengers, pax_names = [], []
    for n in range(1, MAX_PASSENGERS + 1):
        vals = {f: _s(get(pax_title(n, f))) for f in PAX_FIELDS}
        if not any(vals.values()):
            continue
        missing = [f for f in PAX_FIELDS if not vals[f]]
        if missing:
            problems.append(f"Passenger {n}: missing {', '.join(missing).lower()}.")
            continue
        tkt = re.sub(r"[\s-]", "", vals["Ticket number"])
        if not re.fullmatch(r"\d{10,14}", tkt):
            problems.append(f"Passenger {n}: the ticket number must be 10 to 14 digits.")
            continue
        title = vals["Title"].rstrip(".")
        name = f'{title}. {vals["Given name(s)"]} {vals["Surname"]}'
        passengers.append({"name": name, "ticket_no": tkt})
        pax_names.append(name)
    if not passengers and not any("Passenger" in p for p in problems):
        problems.append("Passenger 1 is required.")

    # flights
    flights = []
    for n in range(1, MAX_FLIGHTS + 1):
        vals = {f: get(flight_title(n, f)) for f in FLIGHT_FIELDS}
        seats = {k: _s(get(flight_title(n, SEAT_FIELD.format(k=k)))).upper() for k in range(1, MAX_PASSENGERS + 1)}
        if not any(_s(v) for v in vals.values()) and not any(seats.values()):
            continue
        lab = f"Flight {n}"
        need = ("Flight number", "Operated by (airline)", "From (airport code)", "From city", "To (airport code)",
                "To city", "Departure date", "Departure time", "Arrival date", "Arrival time", "Cabin class")
        gaps = [f for f in need if not _s(vals[f])]
        if gaps:
            problems.append(f"{lab}: missing {', '.join(g.lower() for g in gaps)}.")
            continue
        fno = norm_flight_no(vals["Flight number"])
        if not fno:
            problems.append(f"{lab}: the flight number should look like SV 774.")
        dep_i, arr_i = _s(vals["From (airport code)"]).upper(), _s(vals["To (airport code)"]).upper()
        for lbl, code in (("From", dep_i), ("To", arr_i)):
            if not re.fullmatch(r"[A-Z]{3}", code):
                problems.append(f"{lab}: {lbl} airport code must be 3 letters (for example RUH).")
        dd, ad = to_date(vals["Departure date"]), to_date(vals["Arrival date"])
        dt, at = to_time(vals["Departure time"]), to_time(vals["Arrival time"])
        for lbl, v in (("Departure date", dd), ("Arrival date", ad)):
            if v is None:
                problems.append(f"{lab}: {lbl.lower()} could not be read — pick it from the calendar.")
        for lbl, v in (("Departure time", dt), ("Arrival time", at)):
            if v is None:
                problems.append(f"{lab}: {lbl.lower()} must look like 18:05 (24-hour).")
        if dd and ad and ad < dd:
            problems.append(f"{lab}: the arrival date is before the departure date.")
        dur = norm_duration(vals["Duration"])
        if dur is None:
            problems.append(f"{lab}: duration not understood — write it like 4h 45m, or leave it empty.")
        pax = []
        for k, name in enumerate(pax_names, 1):
            seat = seats.get(k, "")
            if seat and not re.fullmatch(r"\d{1,3}[A-Z]", seat):
                problems.append(f"{lab}: seat for passenger {k} should look like 14A.")
                seat = ""
            pax.append({"name": name, "cabin_bag": _s(vals["Cabin baggage"]),
                        "checked_bag": _s(vals["Checked baggage"]), "seat": seat})
        for k in range(len(pax_names) + 1, MAX_PASSENGERS + 1):
            if seats.get(k):
                problems.append(f"{lab}: a seat was entered for passenger {k}, but there is no passenger {k}.")
        flight = {"flight_no": fno or "", "airline": _s(vals["Operated by (airline)"]),
                  "dep_iata": dep_i, "arr_iata": arr_i, "dep_city": _s(vals["From city"]), "arr_city": _s(vals["To city"]),
                  "dep_airport": "", "arr_airport": "", "terminal": _s(vals["Departure terminal"]),
                  "arr_terminal": _s(vals["Arrival terminal"]), "dep_date": fmt_date(dd) if dd else "",
                  "dep_time": dt or "", "arr_date": fmt_date(ad) if ad else "", "arr_time": at or "",
                  "cabin": _s(vals["Cabin class"]), "duration": dur or "", "pax": pax}
        ref = _s(vals["Airline reference"]).upper()
        if ref:
            flight["pnr"] = ref
        flights.append(flight)
    # "Airline reference" is only filled when a flight's reference DIFFERS from the PNR (two airlines on one
    # ticket). Once any flight has its own, every flight needs one, or the booking PNR would drop off the
    # document: the flights without their own take the booking PNR.
    if any(f.get("pnr") for f in flights):
        for f in flights:
            f.setdefault("pnr", pnr)
    if not flights and not any(p.startswith("Flight") for p in problems):
        problems.append("Flight 1 is required.")

    data = None
    if not problems:
        data = extractors._finalize({
            "portal": "Manual", "pnr": pnr, "booking_ref": _s(get("Agency reference")),
            "crs_ref": _s(get("CRS reference")), "booked_on": booked_s, "status": "Confirmed",
            "passengers": passengers, "flights": flights})
        qc = extractors.qc_check(data)
        if qc:
            problems.append(qc)
            data = None
    return data, problems, meta


# ═════════════════════════════════════════════════════════════════════════════
# THE SHEET LAYOUT (tab "New booking") — 1-based rows, column letters
# ═════════════════════════════════════════════════════════════════════════════
SHEET_TAB = "New booking"
HISTORY_TAB = "History"
HELP_TAB = "Help"
GRID_RANGE = "A1:V30"

BOOKING_CELLS = {"PNR": (5, "B"), "Agency reference": (6, "B"), "CRS reference": (7, "B"), "Booked on": (8, "B")}
EMAIL_CELL = (9, "B")                    # "Send the PDF to" — the person who is building it
PAX_FIRST_ROW = 13                       # rows 13..16 = passengers 1..4
PAX_COLS = {"Title": "B", "Given name(s)": "C", "Surname": "D", "Ticket number": "E"}
FLIGHT_FIRST_ROW = 20                    # rows 20..25 = flights 1..6
FLIGHT_COLS = {"Flight number": "B", "Operated by (airline)": "C", "From (airport code)": "D", "From city": "E",
               "To (airport code)": "F", "To city": "G", "Departure date": "H", "Departure time": "I",
               "Arrival date": "J", "Arrival time": "K", "Cabin class": "L", "Departure terminal": "M",
               "Arrival terminal": "N", "Duration": "O", "Cabin baggage": "P", "Checked baggage": "Q",
               "Airline reference": "R"}
SEAT_COLS = ("S", "T", "U", "V")         # seat for passenger 1..4
TRIGGER_CELL = (28, "B")
TRIGGER_TEXT = "BUILD NOW"
STATUS_CELL = (29, "B")
CLEAR_RANGES = ("B5:B8", "B13:E16", "B20:V25")      # inputs wiped after a successful build ("Send to" is kept)
TITLES = ("Mr", "Mrs", "Ms", "Miss", "Mstr", "Dr")
CABINS = ("Economy", "Premium Economy", "Business", "First")


def col_index(letter):
    """'A' -> 0, 'V' -> 21."""
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _cell(grid, row, col):
    r = row - 1
    if r >= len(grid):
        return ""
    line = grid[r]
    c = col_index(col)
    return line[c] if c < len(line) else ""


def build_requested(grid):
    """True when the person has chosen BUILD NOW."""
    return _s(_cell(grid, *TRIGGER_CELL)).upper() == TRIGGER_TEXT


def grid_to_form(grid):
    """Sheet cells -> (headers, row) in the {title: value} shape parse_row validates."""
    cells = {EMAIL_HEADER: _cell(grid, *EMAIL_CELL)}
    for title, (r, c) in BOOKING_CELLS.items():
        cells[title] = _cell(grid, r, c)
    for n in range(1, MAX_PASSENGERS + 1):
        for field, c in PAX_COLS.items():
            cells[pax_title(n, field)] = _cell(grid, PAX_FIRST_ROW + n - 1, c)
    for n in range(1, MAX_FLIGHTS + 1):
        r = FLIGHT_FIRST_ROW + n - 1
        for field, c in FLIGHT_COLS.items():
            cells[flight_title(n, field)] = _cell(grid, r, c)
        for k, c in enumerate(SEAT_COLS, 1):
            cells[flight_title(n, SEAT_FIELD.format(k=k))] = _cell(grid, r, c)
    headers = list(cells)
    return headers, [cells[h] for h in headers]


def sheet_is_empty(grid):
    """Nothing typed in any input cell (so a stray BUILD NOW on a blank sheet is answered, not built)."""
    h, row = grid_to_form(grid)
    return not any(_s(v) for k, v in zip(h, row) if k != EMAIL_HEADER)
