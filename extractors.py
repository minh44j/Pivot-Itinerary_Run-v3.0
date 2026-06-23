"""
Per-portal extractors — hardened against REAL inbox samples (Jun 2026).
=========================================================================
Body portals (Alhind, aJet, Pegasus) receive the RAW HTML body; each extractor
flattens or cell-parses internally. Akbar receives Drive-PDF text.

Each extractor: fn(src, ctx) -> data dict for generate_itinerary_v3.build_pdf.
ctx may carry {"date": "DD Mon YYYY"} (email received date) for booked_on fallback.

Design decisions (locked with Minh, 2026-06-08/09):
  * Alhind is parsed by HTML TABLE CELLS (passenger table + travel-details table),
    not brittle line-regex — this is the reliable source (cleaner than the PDF).
  * Baggage strings are captured RAW; the generator's _norm_bag() formats them
    (weight-only, "7kg + 3kg", "1Pcs", etc.).
  * Journey type is ONE-WAY or ROUND TRIP only (no MULTI-CITY / no "connecting").
  * Ticket number = the Ticket-No cell verbatim (real number when present, else
    the portal placeholder like "F8VJTS1").
"""
import re
import html as _htmllib
from datetime import datetime, timedelta

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MON_IDX = {m.lower(): i for i, m in enumerate(MONTHS)}
_FULLMON = {"january": 0, "february": 1, "march": 2, "april": 3, "may": 4, "june": 5,
            "july": 6, "august": 7, "september": 8, "october": 9, "november": 10, "december": 11}


# ── shared helpers ────────────────────────────────────────────────────────
def _m(text, pattern, group=1, flags=re.I):
    mo = re.search(pattern, text or "", flags)
    return mo.group(group).strip() if mo else ""


def _pad2(n):
    n = str(n)
    return n if len(n) >= 2 else "0" + n


def _valid_seat(s):
    """Accept only a plausible seat code (e.g. '8A', '14C', 'A8'); reject CTA text,
    section headings, or other cell content a layout-position/regex slip could pick
    up (e.g. 'Seat Selection', 'Flight and Passenger Information', 'Economy').
    Never invents a seat — just filters out non-seat strings down to "".
    """
    s = (s or "").strip()
    # Accept one OR several seat codes (connecting flights assign one seat per
    # leg, e.g. "28G / 11E"). Split on / , ; or whitespace, keep valid codes,
    # rejoin with " / ". Returns "" if none valid (filters CTA/button text).
    if not s:
        return ""
    toks = [t for t in re.split(r"[\s,;/]+", s.strip()) if t]
    good = [t for t in toks if re.fullmatch(r"\d{1,3}[A-Za-z]|[A-Za-z]\d{1,3}", t)]
    return " / ".join(good)


def to_ddmon(s):
    """Normalise many date spellings to 'DD Mon YYYY'."""
    s = (s or "").strip()
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)        # 02 July 2026
    if m:
        mon = m.group(2).lower()
        idx = _FULLMON.get(mon, _MON_IDX.get(mon[:3]))
        if idx is not None:
            return f"{_pad2(m.group(1))} {MONTHS[idx]} {m.group(3)}"
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", s)          # 06-Jun-2026
    if m:
        return f"{_pad2(m.group(1))} {m.group(2).title()} {m.group(3)}"
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", s)    # 06.06.2026
    if m:
        return f"{_pad2(m.group(1))} {MONTHS[int(m.group(2))-1]} {m.group(3)}"
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)              # 2026-06-06
    if m:
        return f"{_pad2(m.group(3))} {MONTHS[int(m.group(2))-1]} {m.group(1)}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2})\b", s)    # 20 Jun 26  (2-digit year)
    if m:
        idx = _MON_IDX.get(m.group(2).lower())
        if idx is not None:
            return f"{_pad2(m.group(1))} {MONTHS[idx]} 20{m.group(3)}"
    return s


def _norm_dur(s):
    m = re.search(r"(\d+)\s*[Hh]\s*(\d+)\s*[Mm]?", s or "")
    return f"{int(m.group(1))}H {int(m.group(2)):02d}M" if m else (s or "").strip()


def _parse_dt(date_str, time_str):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", date_str or "")
    t = re.search(r"(\d{1,2}):(\d{2})", re.sub(r"\s*\(\+\d\)", "", time_str or ""))
    if not m or not t:
        return None
    return datetime(int(m.group(3)), _MON_IDX[m.group(2).lower()] + 1, int(m.group(1)),
                    int(t.group(1)), int(t.group(2)))


def _diff_hm(d1, t1, d2, t2):
    a, b = _parse_dt(d1, t1), _parse_dt(d2, t2)
    if not a or not b:
        return ""
    mins = int((b - a).total_seconds() // 60)
    if mins < 0:
        mins += 24 * 60
    return f"{mins // 60}H {mins % 60:02d}M"


def _norm_flight(s):
    """'VF - 610' -> 'VF 610'; '9P - 9P711' -> '9P711'; 'G9 - G9557' -> 'G9557'."""
    parts = [p.strip() for p in re.split(r"\s*-\s*", (s or "").strip(), maxsplit=1)]
    if len(parts) == 2:
        carrier, num = parts
        return num if num.upper().startswith(carrier.upper()) else f"{carrier} {num}"
    return (s or "").strip()


def _flight_key(s):
    return re.sub(r"\s*-\s*", "-", (s or "").strip()).upper()


def fix_pegasus_words(text):
    """Fix Pegasus 'i'->'6' glitch in plain English words ONLY (never codes/names/IATA)."""
    def repl(mo):
        w = mo.group(0)
        if len(re.findall(r"\d", w.replace("6", ""))) >= 1:
            return w
        return w.replace("6", "i")
    return re.sub(r"[A-Za-z]+6[A-Za-z0-9]*", repl, text or "")


def _city(block):
    return re.split(r"\s*-\s*", (block or "").strip())[0].strip()


def _airport(block):
    parts = re.split(r"\s*-\s*", (block or "").strip(), maxsplit=1)
    ap = parts[1] if len(parts) > 1 else ""
    return re.sub(r"\s*Terminal\s*:?.*$", "", ap, flags=re.I).strip()


def _terminal(block):
    return _m(block or "", r"Terminal\s*:?\s*([A-Za-z0-9]+)")


def _html_to_text(h):
    h = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", h or "")
    h = re.sub(r"(?i)<br\s*/?>", "\n", h)
    h = re.sub(r"(?i)</(td|th|tr|div|p|li|h[1-6]|table)\s*>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = _htmllib.unescape(h)
    h = re.sub(r"[ \t\xa0]+", " ", h)
    return "\n".join(ln.strip() for ln in h.splitlines() if ln.strip())


def _cells(tr_html):
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_html, re.S | re.I):
        c = re.sub(r"(?is)<img[^>]*>", "", c)
        c = re.sub(r"(?i)<br\s*/?>", " ", c)
        c = re.sub(r"<[^>]+>", " ", c)
        c = _htmllib.unescape(c)
        out.append(re.sub(r"\s+", " ", c).strip())
    return out


# ── journey-type + grouping (ONE-WAY / ROUND TRIP only) ────────────────────
def _is_return(flights):
    return len(flights) > 1 and flights[-1].get("arr_iata") == flights[0].get("dep_iata")


def journey_label(flights):
    return "Round Trip" if _is_return(flights) else "One-Way"


def _connection_gaps(flights):
    gaps = []
    for i in range(len(flights) - 1):
        a, b = flights[i], flights[i + 1]
        if a.get("arr_iata") != b.get("dep_iata"):
            continue
        ta, tb = _parse_dt(a.get("arr_date"), a.get("arr_time")), _parse_dt(b.get("dep_date"), b.get("dep_time"))
        mins = int((tb - ta).total_seconds() // 60) if ta and tb else 0
        gaps.append((i, mins))
    return gaps


def _layovers_for(flights):
    out = []
    for i in range(len(flights) - 1):
        a, b = flights[i], flights[i + 1]
        if a.get("arr_iata") != b.get("dep_iata"):
            out.append(None)
            continue
        out.append({"airport": a["arr_iata"],
                    "duration": _diff_hm(a.get("arr_date"), a.get("arr_time"),
                                         b.get("dep_date"), b.get("dep_time"))})
    return out


def group_segments(flights):
    if not flights:
        return []
    if not _is_return(flights):
        return [{"type": "FLIGHT", "flights": flights, "layovers": _layovers_for(flights)}]
    gaps = _connection_gaps(flights)
    split_idx = max(gaps, key=lambda g: g[1])[0] if gaps else len(flights) // 2 - 1
    out, ret = flights[:split_idx + 1], flights[split_idx + 1:]
    if not ret:
        out, ret = flights[:1], flights[1:]
    return [
        {"type": "OUTBOUND", "flights": out, "layovers": _layovers_for(out)},
        {"type": "INBOUND", "flights": ret, "layovers": _layovers_for(ret)},
    ]


def _mark_next_day(flights):
    """Mark ' (+1)' on arrivals that land the next calendar day; advance arr_date
    when the source only gave a single (departure) date."""
    for f in flights:
        if "(+1)" in (f.get("arr_time") or ""):
            continue
        a = _parse_dt(f.get("dep_date"), f.get("dep_time"))
        b = _parse_dt(f.get("arr_date"), f.get("arr_time"))
        if a and b:
            if b.date() > a.date():
                f["arr_time"] = f["arr_time"] + " (+1)"
            elif b < a:                                  # same date, earlier time => overnight
                f["arr_time"] = f["arr_time"] + " (+1)"
                f["arr_date"] = (a + timedelta(days=1)).strftime("%d %b %Y")
        elif f.get("dep_date") == f.get("arr_date") and (f.get("arr_time") or "") < (f.get("dep_time") or ""):
            f["arr_time"] = f["arr_time"] + " (+1)"


def _finalize(d, ctx=None):
    d.setdefault("status", "Confirmed")
    d.setdefault("passengers", [])
    if not d.get("booked_on") and ctx and ctx.get("date"):
        d["booked_on"] = ctx["date"]
    flights = d.pop("flights", [])
    _mark_next_day(flights)
    d["segments"] = group_segments(flights)
    d["journey_type"] = journey_label(flights)
    return d


# ═════════════════════════════════════════════════════════════════════════
# 1. ALHIND — HTML email. Parse the two tables by CELLS.
#    Passenger table:  <tbody id="seg_dt">  (name, segment IATA, flight no,
#                       ticket, cabin/checked baggage, class)
#    Travel-details table: 7-col rows (date, flight no, origin, dest, dep, arr, op)
# ═════════════════════════════════════════════════════════════════════════
def extract_alhind(html, ctx=None):
    d = {"portal": "Alhind"}
    head = _html_to_text(html)
    d["pnr"] = _m(head, r"Airline\s*PNR\s*\n\s*([A-Z0-9]{5,7})")
    d["crs_ref"] = _m(head, r"CRS\s*PNR\s*:?\s*([A-Z0-9]{5,7})")
    d["booking_ref"] = _m(head, r"Booking\s*Reference\s*:?\s*([A-Z0-9]+)")
    d["booked_on"] = to_ddmon(_m(head, r"Booked\s*On\s*:?\s*([0-9A-Za-z-]+)"))
    default_class = (_m(head, r"Class of Travel\s*:?\s*([A-Za-z]+)") or "Economy").title()

    # ── passenger table ──
    pax_tbody = _m(html, r'<tbody[^>]*id="seg_dt"[^>]*>(.*?)</tbody>', 1, re.S | re.I)
    passengers, seg_flightseq = [], []      # seg_flightseq: ordered (key, dep_iata, arr_iata, class)
    seg_seen = set()
    cur = None
    name_re = re.compile(r"^(?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.?\s+[A-Z]", re.I)
    iata_re = re.compile(r"^[A-Z]{3}\s*-\s*[A-Z]{3}$")
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", pax_tbody, re.S | re.I):
        cells = _cells(tr)
        if not cells:
            continue
        # locate the Segment cell (IATA-IATA); fields run consecutively from there:
        # Seg, Flight, Ticket, FF, Cabin, Checkin, ...
        si = next((i for i, c in enumerate(cells) if iata_re.match(c)), None)
        # passenger name = a cell with a title prefix
        nm = next((c for c in cells if name_re.match(c)), "")
        if nm:
            cur = {"name": re.sub(r"\s+", " ", nm).strip(), "ticket_no": "Not specified",
                   "cabin_bag": "Not specified", "checked_bag": "Not specified", "seat": ""}
            passengers.append(cur)
        if si is None:
            continue
        seg = cells[si]
        flt = cells[si + 1] if si + 1 < len(cells) else ""
        tkt = cells[si + 2] if si + 2 < len(cells) else ""
        cabin = cells[si + 4] if si + 4 < len(cells) else ""
        # checked allowance: usually the Checkin column (si+5); some carriers
        # (e.g. Air Arabia / Himalaya) put it in Extra-Checkin (si+6) instead.
        checked = ""
        for j in (si + 5, si + 6):
            if j < len(cells) and cells[j].strip():
                checked = cells[j]
                break
        klass = next((c for c in cells if re.fullmatch(r"(?i)economy|business|first|premium\s*economy", c)), "")
        # Seat: column order from Segment is Seg(si)·Flight(si+1)·Ticket(si+2)·FFNo
        # (si+3)·Cabin(si+4)·Checkin(si+5)·ExtraCheckin(si+6)·ExtraCabin(si+7)·Meal
        # (si+8)·Seat(si+9)·Class(si+10)·Status(si+11) — confirmed against real
        # Alhind source (PNR 8RKBMK, 21 Jun 2026: seat 8A landed exactly at si+9).
        # ONLY trust this offset on the passenger's first/name row — continuation
        # segment rows (return leg, connections) drop rowspan'd columns (FFNo, Meal,
        # Seat) so si+9 there lands on Class/Status instead and must NOT be read.
        if nm and si + 9 < len(cells):
            seat = _valid_seat(cells[si + 9])
            if cur and seat:
                cur["seat"] = seat
        if cur and cur["ticket_no"] == "Not specified":
            cur["ticket_no"] = tkt or "Not specified"
            cur["cabin_bag"] = cabin or "Not specified"
            cur["checked_bag"] = checked or "Not specified"
        dep_i, arr_i = re.split(r"\s*-\s*", seg)
        key = _flight_key(flt)
        if key not in seg_seen:
            seg_seen.add(key)
            seg_flightseq.append((key, dep_i.strip(), arr_i.strip(),
                                  klass.title() if klass else default_class))
    iata_by_flight = {k: (di, ai, cl) for (k, di, ai, cl) in seg_flightseq}
    d["passengers"] = passengers or [{"name": "Not specified", "ticket_no": "Not specified",
                                      "cabin_bag": "Not specified", "checked_bag": "Not specified", "seat": ""}]

    # ── travel-details table (first <tbody> after the 'Travel Details' heading) ──
    tdi = html.find("Travel")
    tdi = html.find("Travel Details", tdi if tdi > 0 else 0)
    travel_html = html[tdi:] if tdi >= 0 else html
    travel_tbody = _m(travel_html, r"<tbody[^>]*>(.*?)</tbody>", 1, re.S | re.I)
    flights = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", travel_tbody, re.S | re.I):
        cells = _cells(tr)
        if len(cells) < 6:
            continue
        # identify columns by content (robust to minor shifts)
        flt_cell = next((c for c in cells if re.search(r"[A-Z0-9]{1,3}\s*-\s*[A-Z0-9]{2,5}", c)
                         and re.search(r"\d", c)), "")
        key = _flight_key(flt_cell)
        di, ai, cl = iata_by_flight.get(key, ("", "", default_class))
        # city/airport blocks = cells containing ' - '
        # Airport cells contain ' - ' (e.g. 'Islamabad - Islamabad Intl'). EXCLUDE the
        # flight-number cell ('PA - 270') which also contains ' - ' — otherwise it gets
        # read as the origin airport and scrambles the whole itinerary.
        ap_cells = [c for c in cells
                    if " - " in c and not re.search(r"\d{1,2}:\d{2}", c)
                    and c != flt_cell
                    and not re.fullmatch(r"\s*[A-Z0-9]{1,3}\s*-\s*[A-Z0-9]{2,5}\s*", c)]
        origin = ap_cells[0] if ap_cells else ""
        dest = ap_cells[1] if len(ap_cells) > 1 else ""
        # times + dates: scan whole row in order
        times = re.findall(r"\b(\d{1,2}:\d{2})\b", " ".join(cells))
        dates = re.findall(r"\d{1,2}-[A-Za-z]{3}-\d{4}", " ".join(cells))
        op = cells[-1] if cells else ""
        flights.append({
            "flight_no": _norm_flight(flt_cell), "airline": op.strip() or "",
            "dep_iata": di, "arr_iata": ai,
            "dep_city": _city(origin), "arr_city": _city(dest),
            "dep_airport": _airport(origin), "arr_airport": _airport(dest),
            "terminal": _terminal(origin),
            "dep_time": times[0] if times else "", "dep_date": to_ddmon(dates[0]) if dates else "",
            "arr_time": times[1] if len(times) > 1 else "", "arr_date": to_ddmon(dates[1]) if len(dates) > 1 else (to_ddmon(dates[0]) if dates else ""),
            "cabin": cl, "duration": "",
        })
    d["flights"] = flights
    return _finalize(d, ctx)


# ═════════════════════════════════════════════════════════════════════════
# 2. AKBAR TRAVELS — Drive PDF text (best-effort; tune with a real PDF)
# ═════════════════════════════════════════════════════════════════════════
def extract_akbar(pdf_text, ctx=None):
    """Akbar Travels. Source is read PRIMARILY from the PDF attached directly
    to the 'Booking Success' email ('Ticket Copy' layout — ONWARD/RETURN
    headers, 4-digit years e.g. '08 Jul 2026', a plain 'Flight Number'
    column, 'Stops' duration shown in parens), with the legacy Drive-folder
    PDF as fallback ('Airline Ref :' segment headers, 2-digit years e.g.
    '08 Jul 26', 'FlightNo (Aircraft)', 'Layover Time :'). Both date formats
    and both flight-number formats are handled below.

    2026-06-18 fix: the original version only matched 2-digit years and a
    '(Aircraft)' suffix after the flight number. Against the new Ticket-Copy
    layout that silently corrupted the flight number (it matched a fragment
    of the date instead, e.g. 'ul 26' out of '...Jul 2026...') AND made the
    return leg fail validation and get DROPPED entirely — producing a
    confirmed PDF that showed only the outbound leg and mislabeled a round
    trip as ONE-WAY. Fixed by: (a) accepting 2- or 4-digit years, (b)
    anchoring the flight number on the 'Flight Number' label first (with a
    month-name sanity guard) before falling back to the legacy parenthetical
    pattern, and (c) never silently dropping a segment the document clearly
    contains — an incomplete segment is still appended so qc_check() flags
    it for manual review instead of an incomplete itinerary going out as if
    it were complete."""
    if not pdf_text:
        raise ValueError("Akbar source document not found / unreadable")
    t = pdf_text
    d = {"portal": "Akbar Travels"}
    d["pnr"] = _m(t, r"Airline\s*Ref\s*:?\s*([A-Z0-9]{5,7})")
    d["crs_ref"] = _m(t, r"CRS\s*Ref\s*:?\s*([A-Z0-9]{5,7})")
    # booking_ref + booked_on from the data row "AS260890572 06 June 2026 CONFIRMED"
    mo = re.search(r"\b([A-Z]{2}\s?\d{6,})\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s+CONFIRMED", t, re.I)
    d["booking_ref"] = (re.sub(r"\s+", " ", mo.group(1)).strip() if mo else _m(t, r"Ref\.?\s*No\s*:?\s*([A-Z0-9]+)"))
    d["booked_on"] = to_ddmon(mo.group(2)) if mo else to_ddmon(_m(t, r"Date of Booking\s*:?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})"))
    d["status"] = "Confirmed" if re.search(r"\bCONFIRMED\b", t, re.I) else ""
    default_class = (_m(t, r"\b(Economy|Business|First|Premium\s*Economy)\b") or "Economy").title()
    # Baggage strings vary ('Adult 07 Kg' OR 'Adult 1Pc : 1 BAG UP TO 7 KG' OR the
    # Ticket-Copy layout's 'Cabin Baggage' / 'Check-In Baggage' labelled columns).
    # Capture the raw allowance line; the generator's _norm_bag pulls the kg out.
    cabin = (_m(t, r"Cabin\s*Baggage\s*:?\s*\n?\s*(Adult[^\n]*)")
             or _m(t, r"Carry-On\s*:?\s*([^\n]+)")
             or _m(t, r"Adult\s+(\d+\s*K[gG])") or "Not specified")
    checked = (_m(t, r"Check-?In\s*Baggage\s*:?\s*\n?\s*(Adult[^\n]*)")
               or _m(t, r"Baggage Allowance\s*:?\s*([^\n]+)")
               or _m(t, r"Adult\s*-\s*(\d+\s*K[gG])") or "Not specified")

    names, seen = [], set()
    # 2026-06-22 fix (Saudia Business Class layout, AS260990906): some layouts
    # put the passenger's name and ticket number on the SAME line
    # ("Mr. OSMAN SAHIN 0652400185383") rather than name-alone-at-end-of-line.
    # The old end-anchor (\s*$) never matched that case, so name extraction
    # returned nothing -> qc_check() correctly flagged "Passenger name
    # missing", but for the wrong underlying reason. Widened to a lookahead
    # that accepts either a trailing 10+ digit ticket number or end-of-line.
    for nmo in re.finditer(r"(?m)\b((?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.?\s+[A-Z][A-Z .'\-]+?)(?=\s+\d{10,}\s*$|\s*$)", t):
        nm = re.sub(r"\s+", " ", nmo.group(1)).strip()
        if nm.upper() not in seen:
            seen.add(nm.upper())
            names.append(nm)
    # Ticket numbers: 'EXKT <num>' OR a plain 10+ digit number in the Traveler
    # section (Akbar's 'Ticket No.' column). Bound to that section to avoid
    # picking up fare/footer numbers.
    trav = t[t.find("Traveler"):] if "Traveler" in t else t
    trav = trav[:trav.find("Carry-On")] if "Carry-On" in trav else trav
    tickets = re.findall(r"EXKT\s*([0-9]{10,})", trav) or re.findall(r"\b(\d{10,})\b", trav)
    d["passengers"] = [{"name": n, "ticket_no": tickets[i] if i < len(tickets) else "Not specified",
                        "cabin_bag": cabin, "checked_bag": checked, "seat": ""}
                       for i, n in enumerate(names)] \
        or [{"name": "Not specified", "ticket_no": "Not specified",
             "cabin_bag": cabin, "checked_bag": checked}]

    # city -> IATA map. The text before '[IATA]' often carries airport/aircraft
    # words ("Indira Gandhi International Gorakhpur [GOP]"); strip those JUNK
    # tokens so the key is the clean city ("gorakhpur"). Direction comes from the
    # per-segment header line ("ONWARD Jeddah New Delhi"), not [IATA] text order.
    JUNK = {"airbus", "jet", "a320", "a321", "indira", "gandhi", "international",
            "intl", "airport", "arpt", "chhatrapati", "shivaji", "maharaj", "king",
            "abdulaziz", "adnan", "menderes", "sabiha", "gokcen", "esenboga",
            "terminal", "non", "stop", "operated", "by", "india", "saudi", "arabia",
            "turkiye", "türkiye", "gandhinagar"}
    city2iata, city2disp = {}, {}
    # 2026-06-22 fix (AS260990906): widened to allow a hyphen/apostrophe in the
    # city name. "Al-Baha [ABT]" was being captured as just "Baha" (the regex
    # stopped at the hyphen), so the route header's "Al-Baha" text never
    # matched any known key -> arr_iata (and dep_iata on the return leg) came
    # back empty. This was the direct cause of the QC flag.
    for cty, code in re.findall(r"([A-Za-z][A-Za-z .\-']+?)\s*\[([A-Z]{3})\]", t):
        words = [w for w in cty.split() if w.lower() not in JUNK]
        if not words:
            continue
        name = " ".join(words)
        k = name.lower()
        city2iata[k] = code
        city2disp[k] = name
    known = sorted(city2iata.keys(), key=len, reverse=True)
    MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    MONTH_WORDS = {"jan", "feb", "mar", "apr", "may", "jun",
                   "jul", "aug", "sep", "oct", "nov", "dec"}

    def _split_cities_line(line):
        line = re.sub(r"^\s*(?:ONWARD|RETURN)\s+", "", line.strip(), flags=re.I)
        for dc in known:
            if line.lower().startswith(dc) and line[len(dc):].strip():
                return dc, line[len(dc):].strip().lower()
        return None, None

    def _split_cities(prev_lines):
        # The ONWARD/RETURN route header is USUALLY the line immediately
        # before 'Airline Ref :', but the Ticket-Copy layout can interpose a
        # date/duration line ('08 Jul 2026 | Non Stop | 02 hrs 40 mins')
        # between them. Scan back a few lines instead of only the last one,
        # so the header is still found regardless of exact adjacency.
        for ln in reversed(prev_lines[-6:]):
            dep_c, arr_c = _split_cities_line(ln)
            if dep_c and arr_c:
                return dep_c, arr_c
        return None, None

    def _flight_no_for(detail):
        # Primary: Ticket-Copy layout labels the value explicitly, value on
        # the very next line.
        cand = _m(detail, r"Flight\s*Number\s*:?\s*\n?\s*([0-9]?[A-Z]{1,2}\s?-?\s?\d{2,4})")
        # 2026-06-22 fix (AS260990906, Saudia Business Class layout): this
        # layout's "Flight Number" label is followed by a run of column
        # headers ("From (Terminal)", "Departure date & time", "Stops",
        # "To (Terminal)", "Arrival date & time") BEFORE the actual code
        # ("SV 1707") appears — too many intervening lines for the primary
        # pattern's single optional newline. The code itself reliably sits
        # on its own line immediately before that segment's "Operated by:"
        # line, so anchor on that instead.
        if not cand:
            m = re.search(r"\n\s*([0-9]?[A-Z]{1,2}\s?-?\s?\d{2,4})\s*\n(?:[^\n]*\n){0,6}?\s*Operated\s*by",
                           detail, re.I)
            cand = m.group(1) if m else None
        # Fallback: legacy Drive layout 'FlightNo (Aircraft)'. Case-SENSITIVE
        # (flags=0) so a lowercase date fragment (e.g. 'ul 26' out of 'Jul
        # 2026') can never match — that case-insensitive match was the root
        # cause of the corrupted flight number in the 2026-06-18 bug.
        if not cand:
            cand = _m(detail, r"\b(\d?[A-Z]{1,2}\s?\d{2,4})\s*\(", flags=0)
        # Sanity guard: reject anything whose letters are actually a month name.
        letters = re.sub(r"[\d\s\-]", "", cand or "").lower()
        if letters in MONTH_WORDS:
            return ""
        return re.sub(r"\s+", " ", cand).strip() if cand else ""

    parts = re.split(r"Airline\s*Ref\s*:", t)
    flights, seen_fl = [], set()
    for i in range(1, len(parts)):
        prev_lines = [ln for ln in parts[i - 1].strip().splitlines() if ln.strip()]
        dep_c, arr_c = _split_cities(prev_lines)
        detail = parts[i]
        fl = _flight_no_for(detail)
        times = re.findall(r"\b(\d{1,2}:\d{2})\b", detail)
        # Dates: accept 4-digit years (new Ticket-Copy layout, '08 Jul 2026')
        # OR 2-digit years (legacy Drive layout, '08 Jul 26'). The original
        # code only accepted 2-digit years, so every 4-digit-year segment
        # failed validation and was silently dropped — root cause of the
        # missing return leg in the 2026-06-18 bug.
        dates4 = re.findall(r"(\d{1,2}\s+" + MON + r"\s+\d{4})", detail)
        dates = dates4 if len(dates4) >= 2 else re.findall(r"(\d{1,2}\s+" + MON + r"\s+\d{2})\b", detail)
        terms = re.findall(r"Terminal\s+([A-Za-z0-9]+)", detail)
        # Stops-column "(Xh:Ym)" is fully inside this segment's own table and
        # can't bleed in from a neighbouring segment's header line the way the
        # looser "X hrs Y mins" phrase can (that phrase sits in the NEXT
        # segment's direction header, which — because we split on 'Airline
        # Ref :' — ends up appended to THIS segment's detail text). Try the
        # scoped pattern first.
        dm = (re.search(r"\((\d{1,2})h:?(\d{2})m\)", detail, re.I)
              or re.search(r"(\d+)\s*hrs?\s*(\d+)\s*min", detail, re.I))
        dep_iata, arr_iata = city2iata.get(dep_c, ""), city2iata.get(arr_c, "")
        fkey = (re.sub(r"\s+", "", fl).upper() if fl
                else f"{dep_iata}-{arr_iata}-{times[0] if times else i}")
        if fkey in seen_fl:                       # PDF repeats on a 2nd page
            continue
        seen_fl.add(fkey)
        # NEVER silently drop a segment the document clearly contains (an
        # ONWARD/RETURN header was found) just because one field failed to
        # parse — append it with whatever was extracted and let qc_check()
        # flag the gap for manual review instead of an itinerary going out
        # with an entire leg missing.
        flights.append({
            # 2026-06-22 fix: do NOT default a failed flight-no match to
            # "Not specified" here — that's a non-empty (truthy) string, so
            # qc_check()'s "missing flight number" gate (which checks
            # `not f.get("flight_no")`) never caught it and a segment with no
            # real flight number could go out as CONFIRMED (see RIW18E.pdf,
            # Ref AS260990720 — same root cause, flagged separately for
            # Minh to review before that already-shipped file is touched).
            # Leave it "" on failure so qc_check() flags it for manual review.
            "flight_no": fl,
            "airline": _m(detail, r"Operated by\s*:?\s*([A-Za-z]+)") or "IndiGo",
            "dep_iata": dep_iata, "arr_iata": arr_iata,
            "dep_city": city2disp.get(dep_c, ""), "arr_city": city2disp.get(arr_c, ""),
            "dep_airport": "", "arr_airport": "",
            "terminal": terms[0] if terms else "",
            "dep_time": times[0] if times else "", "dep_date": to_ddmon(dates[0]) if dates else "",
            "arr_time": times[1] if len(times) > 1 else "", "arr_date": to_ddmon(dates[1]) if len(dates) > 1 else "",
            "cabin": default_class,
            "duration": f"{int(dm.group(1))}H {int(dm.group(2)):02d}M" if dm else "",
        })
    d["flights"] = flights
    return _finalize(d, ctx)


# ═════════════════════════════════════════════════════════════════════════
# 3. aJet — HTML email; one block per segment
# ═════════════════════════════════════════════════════════════════════════
def extract_ajet(src, ctx=None):
    text = _html_to_text(src)
    d = {"portal": "aJet"}
    d["pnr"] = _m(text, r"Reservation\s*Code\s*\n?\s*([A-Z0-9]{5,7})")
    d["booked_on"] = to_ddmon(_m(text, r"Transaction\s*Date\s*\n?\s*([0-9.\-/]+)"))
    # Passengers — the "Passenger Information" block has one row per passenger
    # (name -> check-in baggage -> cabin baggage -> Ticket No). aJet repeats this
    # block once per flight segment, so de-duplicate by ticket number. Anchoring on
    # the full Name…Baggage…Ticket-No run captures EVERY passenger (not just one).
    # Seat: aJet's "Passenger Information" block carries a "Seat" label right after
    # Ticket No (one line per label, value on the next line — often blank since no
    # seat is selected before ticketing). Capture it instead of hardcoding "" — the
    # group is optional so a missing/different layout still matches the rest.
    # Anchor each passenger on their OWN name line immediately preceding the
    # "Total Check-in Baggage" run inside the "Passenger Information" block —
    # NOT on the "Dear <Name>" greeting, which names only the lead/booker and
    # therefore captured a single passenger on 2-pax bookings (regression
    # 2026-06-22, PNR 4B7SDS). Spec: references/portal_field_maps.md §3
    # "MULTIPLE PASSENGERS". De-dupe by Ticket No (block repeats per segment).
    pax_re = re.compile(
        r"(?m)^\s*([A-Z][A-Z'’.\-]+(?:\s+[A-Z][A-Z'’.\-]+)+)\s*\n"   # name line (2+ caps words)
        r"\s*Total\s*Check-?in\s*Baggage\s*\n?\s*([\s\S]*?)\s*"       # checked baggage
        r"Cabin\s*Baggage\s*\n?\s*([\s\S]*?)\s*"                      # cabin baggage
        r"Ticket\s*No\s*\n?\s*(\d{10,})"                             # ticket number
        r"(?:[ \t]*\n?[ \t]*Seat(?:[ \t]*\n?[ \t]*"                  # "Seat" label
        r"((?:\d{1,3}[A-Za-z]|[A-Za-z]\d{1,3})"                         # first seat code ONLY
        r"(?:[ \t]*[/,][ \t]*(?:\d{1,3}[A-Za-z]|[A-Za-z]\d{1,3}))*))?)?",  # extra legs; never eats a name line
    )
    passengers, seen = [], set()
    for mo in pax_re.finditer(text):
        tkt = mo.group(4)
        if tkt in seen:
            continue
        seen.add(tkt)
        passengers.append({
            "name": re.sub(r"\s+", " ", mo.group(1)).strip(),
            "ticket_no": tkt,
            "checked_bag": re.sub(r"\s+", " ", mo.group(2)).strip() or "Not specified",
            "cabin_bag": re.sub(r"\s+", " ", mo.group(3)).strip() or "Not specified",
            "seat": _valid_seat(mo.group(5) or ""),
        })
    if not passengers:
        # Fallback — single passenger from the greeting / contact person.
        name = _m(text, r"Contact\s*Person\s*\n\s*([A-Z][A-Za-z' .\-]+)") or \
            _m(text, r"Dear\s+([A-Z][A-Z' .\-]+)\b")
        passengers = [{
            "name": name or "Not specified",
            "ticket_no": _m(text, r"Ticket\s*No\s*\n?\s*([0-9]{10,})") or "Not specified",
            "cabin_bag": _m(text, r"Cabin\s*Baggage\s*\n?\s*([^\n]+)") or "Not specified",
            "checked_bag": _m(text, r"(?:Total\s*)?Check-?in\s*Baggage\s*\n?\s*([^\n]+)") or "Not specified",
            "seat": _valid_seat(_m(text, r"Seat\s*\n?\s*([^\n]*)")),
        }]
    d["passengers"] = passengers
    flights = []
    seg_re = re.compile(
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*\n\s*([^\n]+?)\s*\n\s*([A-Z]{3})\s*\n\s*(\d{1,2}:\d{2})\s*\n\s*"
        r"([^\n]+?)\s*\n\s*([A-Z]{3})\s*\n\s*(\d{1,2}:\d{2})\s*\n\s*(?:Connecting|Non[ -]?Stop|Direct)?\s*\n?\s*"
        r"(?:(\d+\s*[Hh]\s*\d+\s*[Mm]))?\s*\n?\s*(VF\s?\d{2,4})\s*\n\s*(ECOJET|BIZJET)?")
    for mo in seg_re.finditer(text):
        brand = (mo.group(10) or "").upper()
        flights.append({
            "dep_date": to_ddmon(mo.group(1)), "arr_date": to_ddmon(mo.group(1)),
            "dep_city": mo.group(2).strip(), "dep_iata": mo.group(3), "dep_time": mo.group(4),
            "arr_city": mo.group(5).strip(), "arr_iata": mo.group(6), "arr_time": mo.group(7),
            "duration": _norm_dur(mo.group(8) or ""),
            "flight_no": re.sub(r"(VF)\s?", r"\1 ", mo.group(9)).strip(), "airline": "aJet",
            "cabin": "Business" if brand == "BIZJET" else ("Economy" if brand == "ECOJET" else "Not specified"),
            "dep_airport": "", "arr_airport": "", "terminal": "",
        })
    d["flights"] = flights
    return _finalize(d, ctx)


# ═════════════════════════════════════════════════════════════════════════
# 4. PEGASUS — HTML email; handles BOTH simple and connecting layouts.
# ═════════════════════════════════════════════════════════════════════════
def _pegasus_section_flights(sec, sec_date):
    flights = []
    codes = list(re.finditer(r"\bPC\s?\d{2,4}\b", sec))
    for i, mo in enumerate(codes):
        chunk = sec[mo.start(): codes[i + 1].start() if i + 1 < len(codes) else len(sec)]
        iatas = re.findall(r"(?m)^\s*([A-Z]{3})\s*$", chunk)
        times = re.findall(r"\b(\d{1,2}:\d{2})\b", chunk)
        cities = [_city(c) for c in re.findall(r"(?m)^\s*([A-Za-z][^\n]*?\s-\s[^\n]+?)\s*$", chunk)]
        dur = _norm_dur(_m(chunk, r"(\d+\s*[Hh]\s*\d+\s*[Mm])"))
        if len(iatas) >= 2 and len(times) >= 2:
            flights.append({
                "flight_no": re.sub(r"\s+", "", mo.group(0)),
                "dep_iata": iatas[0], "arr_iata": iatas[1],
                "dep_time": times[0], "arr_time": times[1],
                "dep_city": cities[0] if cities else "", "arr_city": cities[1] if len(cities) > 1 else "",
                "dep_date": sec_date, "arr_date": sec_date,
                "duration": dur, "airline": "Pegasus", "cabin": "Not specified",
                "dep_airport": "", "arr_airport": "", "terminal": "",
            })
    return flights


def _pegasus_section_date(sec):
    return to_ddmon(_m(sec, r"Flight\s*Date:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
                    or _m(sec, r"(?m)^\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*$"))


def _pegasus_passengers(text, fallback_name):
    """Pegasus emails list every passenger under a 'Passenger Information'
    heading as repeating blocks:
        <Name>   |   icon section   <Fare Package>
        icon  Seat
        <seat>
        icon  Cabin Baggage
        <cabin baggage>
        icon  Checked Baggage
        <checked baggage>
    The 'Dear <Name>,' salutation only ever names the lead passenger, so for
    multi-passenger bookings (e.g. PNR 24YWFW: Sedat Caglayan, Mehmet Gullu,
    Fatih Gog) it must NOT be used as the only source. Confirmed against a
    real 3-passenger PNR on 2026-06-17 — see [[pivot-pegasus-multi-passenger]].
    """
    sec_m = re.search(
        r"Passenger\s*Information\s*\n(.*?)"
        r"(?=\n\s*Switch to|\n\s*Banner|\n\s*Bol\s*Bol|\n\s*Enhance your travel|\Z)",
        text, re.S | re.I,
    )
    section = sec_m.group(1) if sec_m else ""
    blocks = re.split(r"(?m)^\s*([^\n|]+?)\s*\|\s*(?:icon section\s*)?([^\n]+)$", section)
    passengers, seen_names = [], set()
    for i in range(1, len(blocks), 3):
        name = blocks[i].strip()
        body = blocks[i + 2] if i + 2 < len(blocks) else ""
        if not name:
            continue
        # Pegasus repeats the WHOLE "Passenger Information" block once per
        # flight leg (Departure + Return) — the section regex above can't
        # stop between them when the email's only later stop-marker
        # ("Switch to Saver Plus Package", etc.) falls after the SECOND
        # occurrence, so both legs' blocks get captured together and the
        # same passenger is split out twice. Dedupe by name (no ticket
        # number exists on Pegasus to key on, unlike aJet's dedup-by-ticket
        # for the same per-segment repetition). Confirmed against PNR
        # 2553WM (single pax, round trip) on 2026-06-21.
        key = name.upper()
        if key in seen_names:
            continue
        seen_names.add(key)
        # Seat: Pegasus's template repeats its "Seat Selection" CTA text
        # twice on the same line (e.g. "Seat Selection Seat Selection") when
        # no seat has actually been picked — that is a button label, NOT an
        # assigned seat code. _valid_seat() filters this (and any other
        # non-seat text) down to "" -> displays as Not specified. A real seat
        # code (e.g. "14A", "12C") still passes through untouched.
        seat = _valid_seat(_m(body, r"Seat\s*\n\s*([^\n]+)"))
        passengers.append({
            "name": name,
            "ticket_no": "Not specified",                                # Pegasus = PNR only
            "cabin_bag": _m(body, r"Cabin\s*Baggage\s*\n\s*([^\n]+)") or "Not specified",
            "checked_bag": _m(body, r"Checked\s*Baggage\s*\n\s*([^\n]+)") or "Not specified",
            "seat": seat,
        })
    if passengers:
        return passengers
    # Fallback (no 'Passenger Information' section parsed) — old single-passenger behavior.
    return [{
        "name": fallback_name or "Not specified",
        "ticket_no": "Not specified",
        "cabin_bag": _m(text, r"Cabin\s*Baggage\s*\n\s*([^\n]+)") or "Not specified",
        "checked_bag": _m(text, r"Checked\s*Baggage\s*\n\s*([^\n]+)") or "Not specified",
        "seat": "",
    }]


def extract_pegasus(src, ctx=None):
    text = fix_pegasus_words(_html_to_text(src))
    raw = _html_to_text(src)
    d = {"portal": "Pegasus"}
    d["pnr"] = _m(raw, r"PNR\s*No\s*:?\s*\n?\s*([A-Z0-9]{5,7})")     # raw — never de-glitch codes
    d["status"] = "Confirmed" if re.search(r"your booking is confirmed", text, re.I) else ""
    d["booked_on"] = ""
    name = _m(text, r"Dear\s+([A-Z][A-Za-z' .\-]+?)\s*,")
    d["passengers"] = _pegasus_passengers(text, name)
    parts = re.split(r"Return\s+Flight\s+Information", text, maxsplit=1, flags=re.I)
    out_sec = parts[0]
    ret_sec = parts[1] if len(parts) > 1 else ""
    flights = _pegasus_section_flights(out_sec, _pegasus_section_date(out_sec))
    if ret_sec:
        flights += _pegasus_section_flights(ret_sec, _pegasus_section_date(ret_sec))
    d["flights"] = flights
    return _finalize(d, ctx)


# ── generic segment parser (Akbar PDF fallback) ───────────────────────────
def _parse_generic_segments(text):
    flights = []
    pat = (r"\b([A-Z]{3})\b[^\n]{0,40}?\b([A-Z]{3})\b[^\n]{0,60}?([A-Z]{1,3}\s?\d{2,4})"
           r"[^\n]{0,60}?(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
           r"[^\n]{0,40}?(\d{1,2}:\d{2})[^\n]{0,40}?(\d{1,2}:\d{2})")
    for mo in re.finditer(pat, text):
        flights.append({
            "dep_iata": mo.group(1), "arr_iata": mo.group(2), "flight_no": re.sub(r"\s", "", mo.group(3)),
            "dep_date": to_ddmon(mo.group(4)), "arr_date": to_ddmon(mo.group(4)),
            "dep_time": mo.group(5), "arr_time": mo.group(6), "airline": "", "cabin": "Not specified",
            "dep_city": "", "arr_city": "", "dep_airport": "", "arr_airport": "", "terminal": "", "duration": "",
        })
    return flights


# ── QC gate (Project Instructions §7/§12) — flag, don't guess ──────────────
def qc_check(d):
    if not d:
        return "No data extracted"
    if not d.get("pnr") or re.search(r"not specified", d["pnr"], re.I):
        return "Missing PNR"
    if not d.get("passengers"):
        return "No passengers"
    if any(not p.get("name") or re.search(r"not specified", p["name"], re.I) for p in d["passengers"]):
        return "Passenger name missing"
    if not d.get("segments"):
        return "No flight segments"
    if d.get("status") and not re.search(r"confirm", d["status"], re.I):
        return "Status not Confirmed: " + d["status"]
    for g in d["segments"]:
        for f in g.get("flights", []):
            if not all([f.get("flight_no"), f.get("dep_iata"), f.get("arr_iata"),
                        f.get("dep_time"), f.get("arr_time")]):
                return "A segment is missing flight number / airport / time"
    return None


# ── registry ───────────────────────────────────────────────────────────────
PORTALS = [
    {"name": "Alhind",        "from": "alhind@alhindsanchar.com",   "subject": "Air Ticket",                                      "source": "body",      "fn": extract_alhind},
    {"name": "Akbar Travels", "from": "sanoreply@akbartravels.com", "subject": "Booking Success",                                 "source": "drive_pdf", "fn": extract_akbar},
    {"name": "Akbar Travels", "from": "sanoreply@akbartravels.com", "subject": "Ticket Copy",                                    "source": "drive_pdf", "fn": extract_akbar},
    {"name": "aJet",          "from": "onlineticket@mail.ajet.com", "subject": "Ticket information",                              "source": "body",      "fn": extract_ajet},
    {"name": "Pegasus",       "from": "pegasus@flypgs.com",         "subject": "Your booking is confirmed! View your ticket now", "source": "body",      "fn": extract_pegasus},
]
