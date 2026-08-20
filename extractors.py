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
import hashlib
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
    # Every airline reference on the booking, in itinerary order, de-duplicated.
    # Normally one; a split-carrier booking has one per operating airline and the
    # document has to show them all (see the note in extract_akbar). Portals that
    # never set a per-flight "pnr" fall through to the single booking-level ref,
    # so nothing about a single-reference booking changes.
    refs = []
    for f in flights:
        r = (f.get("pnr") or "").strip().upper()
        if r and r not in refs:
            refs.append(r)
    d["pnrs"] = refs or ([d["pnr"].strip().upper()] if (d.get("pnr") or "").strip() else [])
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
    seg_pax = {}                            # flight_key -> [ {name, cabin_bag, checked_bag, seat} ]
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
        # COLUMN OFFSETS DIFFER BY ROW TYPE. On a name row the FFNo cell is
        # present (si+3), so Cabin is si+4. On a continuation row Name/Image/FFNo
        # are rowspan'd away, so every field shifts one earlier and Cabin is si+3.
        # The old code always used si+4 — harmless only because baggage was
        # assigned once on the name row; reading per-SEGMENT baggage (2026-07-30)
        # makes the distinction matter, so it is handled properly here.
        _cab_i = (si + 4) if nm else (si + 3)
        cabin = cells[_cab_i] if _cab_i < len(cells) else ""
        # checked allowance: usually the Checkin column (next one along); some
        # carriers (e.g. Air Arabia / Himalaya) put it in Extra-Checkin instead.
        checked = ""
        for j in (_cab_i + 1, _cab_i + 2):
            if j < len(cells) and cells[j].strip():
                checked = cells[j]
                break
        klass = next((c for c in cells if re.fullmatch(r"(?i)economy|business|first|premium\s*economy", c)), "")
        # Seat column offsets (confirmed against real Alhind source PNR <ref>):
        # First/name row: Seg(si)·Flight(si+1)·Ticket(si+2)·FFNo(si+3)·Cabin(si+4)·
        #   Checkin(si+5)·ExtraCheckin(si+6)·ExtraCabin(si+7)·Meal(si+8)·Seat(si+9)
        # Continuation rows (2nd segment, return leg): Name, Image, and FFNo are
        #   rowspan'd and absent — Meal and Seat ARE present, just shifted one earlier:
        #   Seg(si)·Flight(si+1)·Ticket(si+2)·Cabin(si+3)·Checkin(si+4)·
        #   ExtraCheckin(si+5)·ExtraCabin(si+6)·Meal(si+7)·Seat(si+8)
        # Collect all per-segment seats and join with " / " for multi-leg bookings.
        if nm and si + 9 < len(cells):
            seat = _valid_seat(cells[si + 9])
            if cur and seat:
                cur["seat"] = seat
        elif not nm and cur and si + 8 < len(cells):
            # continuation row: FFNo absent (rowspan'd), seat shifts to si+8
            seat = _valid_seat(cells[si + 8])
            if seat:
                cur["seat"] = (cur["seat"] + " / " + seat) if cur["seat"] else seat
        if cur and cur["ticket_no"] == "Not specified":
            cur["ticket_no"] = tkt or "Not specified"
            cur["cabin_bag"] = cabin or "Not specified"
            cur["checked_bag"] = checked or "Not specified"
        dep_i, arr_i = re.split(r"\s*-\s*", seg)
        key = _flight_key(flt)
        # PER-SEGMENT pax record for this row (2026-07-30). Alhind's passenger
        # table has one row PER SEGMENT per passenger, so extra baggage bought on
        # a single leg — or a different seat per leg — is right here in the source.
        # Keyed by flight so the generator can attach it to the matching leg.
        _row_seat = _valid_seat(cells[si + 9] if (nm and si + 9 < len(cells))
                               else (cells[si + 8] if (not nm and si + 8 < len(cells)) else ""))
        seg_pax.setdefault(key, []).append({
            "name": (cur or {}).get("name", ""),
            "cabin_bag": cabin or "",
            "checked_bag": checked or "",
            "seat": _row_seat,
        })
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
            # 2026-07-17: Alhind embeds each airport's terminal INSIDE its own
            # Origin/Destination table cell ("Riyadh - King Khaled Intl <p>Terminal
            # : 5</p>"). Pull the departure terminal from the origin cell and the
            # ARRIVAL terminal from the destination cell (previously only origin).
            "terminal": _terminal(origin), "arr_terminal": _terminal(dest),
            "dep_time": times[0] if times else "", "dep_date": to_ddmon(dates[0]) if dates else "",
            "arr_time": times[1] if len(times) > 1 else "", "arr_date": to_ddmon(dates[1]) if len(dates) > 1 else (to_ddmon(dates[0]) if dates else ""),
            "cabin": cl, "duration": "",
            # per-leg pax baggage/seat harvested from this flight's own row(s)
            "pax": seg_pax.get(key, []),
        })
    d["flights"] = flights
    return _finalize(d, ctx)


# ═════════════════════════════════════════════════════════════════════════
# 2. AKBAR TRAVELS — Drive PDF text (best-effort; tune with a real PDF)
# ═════════════════════════════════════════════════════════════════════════
# A 2-character IATA airline designator comes in exactly three shapes:
#   LL  (SV, TK, XY)   LD  (F3, G9, U2)   DL  (9P, 6E)
# The flight-number regexes below MUST accept all three. The historical
# `[0-9]?[A-Z]{1,2}` group silently missed the LD (letter-then-digit) shape —
# it matched only the leading letter and then failed on the digit — so codes
# like Air Arabia "G9" and Flyadeal "F3 310" came back empty and the segment
# was flagged "missing flight number". Use this constant everywhere instead.
_IATA_DESIG = r"(?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z])"

# Countries that bleed into the "Operated by:" cell — see _akbar_airline below.
# The From/To date column renders as "Mon, 24 Aug 26". When pdfplumber puts it
# on the same line as the "Operated by:" cell, cutting at the first comma leaves
# the WEEKDAY glued to the carrier — real booking 8CP5SK shipped with
# "OPERATED BY: Saudi Mon". No airline's name ends in a weekday, so strip it.
_WEEKDAY_TAIL = re.compile(
    r"\s+(?:Mon|Tue|Tues|Wed|Weds|Thu|Thur|Thurs|Fri|Sat|Sun)\.?\s*$", re.I)

_COUNTRY_TAIL = re.compile(
    r"\s*(?:Saudi\s*Arabia|Pakistan|India|T[uü]rkiye|Turkey|United\s*Arab\s*Emirates|"
    r"Qatar|Kuwait|Bahrain|Oman|Egypt|Jordan|Nepal|Bangladesh|Sri\s*Lanka|Maldives|"
    r"Indonesia|Malaysia|Azerbaijan|Georgia|Ethiopia|Kenya|Morocco|Tunisia)\s*$", re.I)


def _akbar_airline(detail):
    """Operating carrier out of an Akbar ticket's 'Operated by:' cell.

    Two real-world complications, both confirmed on actual pdfplumber output:

      1. pdfplumber splits the label across lines — the Flyadeal Ticket-Copy
         renders "Operated , Thu, 23 Jul 26 (02h:10m) Thu, 23 Jul 26\\nby:Flyadeal
         Saudi Arabia," — so a contiguous "Operated by:" match misses it entirely.
         Up to a line of junk is tolerated between the two words.

      2. The value is MULTI-WORD ("Air Sial", "Air Arabia", "Fly Jinnah"), but the
         neighbouring From/To column's country can be linearised onto the same line
         ("by:Flyadeal Saudi Arabia,"). Capturing one word truncated "Air Sial" to
         "Air" (a factual error on a client document, PNR A052SF); capturing the
         whole line would have made Flyadeal into "Flyadeal Saudi Arabia".
         So: take the line, cut at the first comma, then strip a trailing country.

    Returns "" when nothing parses. That is deliberate — the previous "IndiGo"
    default silently stamped a real airline's name onto other carriers' tickets
    (§7 never fabricate); a blank renders as N/A, which is merely incomplete.
    """
    m = re.search(r"Operated\b[\s\S]{0,80}?\bby\s*:?\s*([A-Za-z][A-Za-z .'&-]*)", detail)
    if not m:
        # Some Ticket-Copy layouts carry NO "Operated by:" line at all — the
        # carrier sits on its own line in the fare block, between the
        # "Travel Class ..." header and the cabin line (confirmed on the real
        # Air Arabia JED-SHJ-KTM ticket and on the Flyadeal fixture):
        #     Travel Class Product Class
        #     Air Arabia
        #     Economy BASIC FARE
        # Anchoring on both neighbours keeps this tight enough that a stray
        # line cannot be mistaken for a carrier; no match still returns "".
        m = re.search(r"Travel\s*Class[^\n]*\n\s*([A-Za-z][A-Za-z .'&-]{2,30}?)\s*\n"
                      r"\s*(?:Economy|Business|First|Premium)\b", detail)
    if not m:
        return ""
    val = m.group(1).split(",")[0]
    val = _WEEKDAY_TAIL.sub("", val.strip())
    val = _COUNTRY_TAIL.sub("", val.strip())
    # The cell can WRAP: real booking 8CP5SK renders
    #     Operated by:Saudi Mon, 24 Aug 26 (02h:45m) Egypt, Mon, 24 Aug 26
    #     Airline Saudi Arabia,
    # so the carrier "Saudi Airline" is split across two lines and only "Saudi"
    # survives the cut above. Pull the continuation back when the following line
    # STARTS with a carrier-suffix word; anything else is a different column and
    # is left alone.
    _rest = detail[m.end():]
    _cont = re.match(r"[^\n]*\n\s*(Airlines?|Airways|Aviation)\b", _rest)
    if _cont and val:
        val = f"{val} {_cont.group(1)}"
    val = re.sub(r"\s+", " ", val).strip(" .-")
    # An airline name is at most a few words; anything longer means the column
    # bled and the tail is not part of the carrier's name.
    return " ".join(val.split()[:4])


def _akbar_first_value(pattern, text):
    """First NON-BLANK value for a repeated labelled field inside one segment.

    Akbar repeats the "Traveler(s) Information / Baggage" block within a single
    direction, and on a split-carrier booking the first copy is EMPTY
    ("Carry-On :" / "Baggage Allowance :" with nothing after the colon) while a
    later copy carries the real allowance. Taking the first match would render a
    blank; taking the last would break the single-block layouts. Take the first
    that actually says something.
    """
    import re as _re
    for v in _re.findall(pattern, text):
        v = v.strip().strip(":|-").strip()
        if v:
            return v
    return ""


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
    # booking_ref + booked_on from the data row "<ref> 06 June 2026 CONFIRMED"
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
             or _m(t, r"Adult\s+(\d+\s*K[gG])")
             # Ticket-Copy layouts with no labelled baggage block state it inside
             # the Traveler row instead: "20 Kg 1 Piece, Cabin-07Kg + 1 Personal
             # item". Only reached when every labelled pattern above missed.
             or _m(t, r"Cabin\s*[-:]?\s*(\d+\s*K[gG])") or "Not specified")
    checked = (_m(t, r"Check-?In\s*Baggage\s*:?\s*\n?\s*(Adult[^\n]*)")
               or _m(t, r"Baggage Allowance\s*:?\s*([^\n]+)")
               or _m(t, r"Adult\s*-\s*(\d+\s*K[gG])")
               or _m(t, r"(\d+\s*K[gG])\s+\d+\s*Piece") or "Not specified")

    names, seen = [], set()
    # 2026-06-22 fix (Saudia Business Class layout, <ref>): some layouts
    # put the passenger's name and ticket number on the SAME line
    # ("Mr. <name> <ticket-no>") rather than name-alone-at-end-of-line.
    # The old end-anchor (\s*$) never matched that case, so name extraction
    # returned nothing -> qc_check() correctly flagged "Passenger name
    # missing", but for the wrong underlying reason. Widened to a lookahead
    # that accepts either a trailing 10+ digit ticket number or end-of-line.
    # 2026-08-13 fix (Air Arabia G9 JED-SHJ-KTM, ref AS261308499): the Traveler
    # table can render the name and ticket number FUSED, with the baggage cell
    # trailing on the same line — "Mr. <NAME><TICKET> 20 Kg 1 Piece, Cabin-07Kg".
    # The old lookahead demanded whitespace before the ticket AND end-of-line
    # right after it, so neither branch matched, names came back empty and every
    # such booking flagged "Passenger name missing". The ticket may now follow
    # immediately (\s* not \s+) and need not end the line. The captured class
    # excludes digits, so the name still stops cleanly where the number starts.
    for nmo in re.finditer(r"(?m)\b((?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.?\s+[A-Z][A-Z .'\-]+?)(?=\s*\d{10,}|\s*$)", t):
        nm = re.sub(r"\s+", " ", nmo.group(1)).strip()
        if nm.upper() not in seen:
            seen.add(nm.upper())
            names.append(nm)
    # Ticket numbers: 'EXKT <num>' OR a plain 10+ digit number in the Traveler
    # section (Akbar's 'Ticket No.' column). Bound to that section to avoid
    # picking up fare/footer numbers.
    # 2026-08-20 fix (split-carrier round trip AS261347760): the window used to
    # run from the first "Traveler" to the first "Carry-On". On a two-airline
    # booking Akbar prints ONE Traveler table per direction, and the FIRST one
    # carries no "Ticket No." column at all ("Code Name" only) — the number lives
    # in the SECOND table, far past that first "Carry-On", so every passenger on
    # such a booking rendered "Not specified". Read every Traveler block instead,
    # each bounded by the fare table / next segment that follows it.
    trav = "".join(m.group(0) for m in re.finditer(
        r"Traveler[\s\S]*?(?=Base\s*Fare|Airline\s*Ref|\Z)", t)) or t
    # A leading \b fails when the ticket is fused to the name ("DOE1234567890"),
    # because letter->digit is not a word boundary. Guard on "not a digit either
    # side" instead so both the fused and the spaced layouts are found. The rows
    # repeat once per leg, so the same ticket appears several times — dedupe
    # (order-preserving) or passenger 2 would inherit passenger 1's number.
    tickets = re.findall(r"EXKT\s*([0-9]{10,})", trav) \
        or re.findall(r"(?<![0-9])(\d{10,})(?![0-9])", trav)
    tickets = list(dict.fromkeys(tickets))
    d["passengers"] = [{"name": n, "ticket_no": tickets[i] if i < len(tickets) else "Not specified",
                        "cabin_bag": cabin, "checked_bag": checked, "seat": ""}
                       for i, n in enumerate(names)] \
        or [{"name": "Not specified", "ticket_no": "Not specified",
             "cabin_bag": cabin, "checked_bag": checked}]

    # city -> IATA map. The text before '[IATA]' often carries airport/aircraft
    # words ("Indira Gandhi International Gorakhpur [GOP]"); strip those JUNK
    # tokens so the key is the clean city ("gorakhpur"). Direction comes from the
    # per-segment header line ("ONWARD Jeddah New Delhi"), not [IATA] text order.
    # 2026-07-12 fix: added "khalid"/"khaled" (King Khalid International Airport,
    # Riyadh). When pdfplumber merges the Saudia ticket table row into a single line
    # ("SV 1707 King Khalid International Airport Al-Baha [ABT]") and "king" is
    # already in JUNK but "khalid" is not, the compound remainder "khalid al-baha"
    # becomes the city2iata key. The ONWARD header says "ONWARD RIYADH AL-BAHA",
    # so lookups for "riyadh" and "al-baha" both miss -> dep/arr iata empty -> QC
    # flag "A segment is missing flight number / airport / time".
    JUNK = {"airbus", "jet", "a320", "a321", "indira", "gandhi", "international",
            "intl", "airport", "arpt", "chhatrapati", "shivaji", "maharaj", "king",
            "khalid", "khaled", "abdulaziz", "adnan", "menderes", "sabiha", "gokcen",
            "esenboga", "terminal", "non", "stop", "operated", "by", "india",
            "saudi", "arabia", "turkiye", "türkiye", "gandhinagar"}
    city2iata, city2disp = {}, {}
    # 2026-06-22 fix (<ref>): widened to allow a hyphen/apostrophe in the
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
        # 2026-07-12 fix (robustness): when pdfplumber merges airport-name words
        # that survive JUNK filtering with the actual city name (e.g. "khalid
        # riyadh"), the ONWARD header uses just the city ("riyadh"). Also add
        # the last word of compound keys as a standalone fallback so the lookup
        # succeeds even when the airport name leaks into the key.
        if len(words) > 1:
            last = words[-1].lower()
            if last not in city2iata:
                city2iata[last] = code
                city2disp[last] = words[-1]
    known = sorted(city2iata.keys(), key=len, reverse=True)
    MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    MONTH_WORDS = {"jan", "feb", "mar", "apr", "may", "jun",
                   "jul", "aug", "sep", "oct", "nov", "dec"}

    def _split_cities_line(line):
        line = re.sub(r"^\s*(?:ONWARD|RETURN)\s+", "", line.strip(), flags=re.I)
        # 2026-07-06 fix: pdfplumber may render the Akbar Ticket-Copy arrow
        # image as a Unicode arrow character (e.g. →) between city names.
        # Normalise any such character to a plain space so city matching works.
        line = re.sub(r"[\u2192-\u21ff\u27a1\u25b6\u25ba]+", " ", line).strip()
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
        cand = _m(detail, r"Flight\s*Number\s*:?\s*\n?\s*(" + _IATA_DESIG + r"\s?-?\s?\d{2,4})")
        # 2026-06-22 fix (<ref>, Saudia Business Class layout): this
        # layout's "Flight Number" label is followed by a run of column
        # headers ("From (Terminal)", "Departure date & time", "Stops",
        # "To (Terminal)", "Arrival date & time") BEFORE the actual code
        # ("SV 1707") appears — too many intervening lines for the primary
        # pattern's single optional newline. The code itself reliably sits
        # at the START of a line immediately before that segment's
        # "Operated by:" line, so anchor on that instead.
        if not cand:
            m = re.search(r"\n\s*(" + _IATA_DESIG + r"\s?-?\s?\d{2,4})\b[^\n]*\n(?:[^\n]*\n){0,6}?\s*Operated\s*by",
                           detail, re.I)
            cand = m.group(1) if m else None
        # Fallback: legacy Drive layout 'FlightNo (Aircraft)'. Case-SENSITIVE
        # (flags=0) so a lowercase date fragment (e.g. 'ul 26' out of 'Jul
        # 2026') can never match — that case-insensitive match was the root
        # cause of the corrupted flight number in the 2026-06-18 bug.
        if not cand:
            cand = _m(detail, r"\b(" + _IATA_DESIG + r"\s?\d{2,4})\s*\(", flags=0)
        # 2026-07-06 fix (Fly Jinnah / Ticket-Copy non-Saudia layout): some
        # carriers (e.g. Fly Jinnah 9P) produce a flight cell that shows the
        # IATA carrier code twice: "9P 9P700". Handle by matching the doubled-
        # code pattern and reconstructing "9P 700". Also covers the case where
        # "Flight Number" has multiple column-header lines before the value
        # (re.S lets . match newlines; up to 8 intervening lines tolerated).
        # 2026-07-16 fix (Air Arabia G9 connecting, <ref> / PNR <ref>):
        # the code group only matched [0-9]?[A-Z]{1,2} (e.g. "9P", "6E"), which
        # cannot match a LETTER-then-DIGIT designator like "G9"/"U2" — so the
        # doubled cell "G9 G9148" was missed and the segment shipped with an
        # empty flight number (QC flag "missing flight number"). Widened the
        # code group to a proper 2-char IATA designator (LL | LD | DL). The
        # \1 back-reference (an exact repeat of the same 2-char code) keeps
        # this specific enough that ref numbers / times cannot false-match.
        if not cand:
            m = re.search(r"\b((?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z]))\s+\1(\d{2,4})\b", detail)
            if m:
                cand = f"{m.group(1)} {m.group(2)}"
        if not cand:
            m = re.search(
                r"Flight\s*Number[^\n]*\n(?:[^\n]*\n){0,8}?\s*(" + _IATA_DESIG + r"\s?[0-9]{2,4})\b",
                detail, re.I
            )
            cand = m.group(1) if m else None
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
        # 2026-07-17: Akbar's flight-table "From (Terminal) / To (Terminal)"
        # columns are EMPTY in every real ticket sampled (rendered as ", ,").
        # The only "Terminal X" tokens in the PDF sit in a separate airport-
        # metadata block that pdfplumber scatters unpredictably (e.g. "Terminal 4"
        # floats next to the RETURN header; "North Terminal" next to the layover
        # line) and CANNOT be reliably attributed to a segment's departure vs
        # arrival airport. The old `terms[0]` grab mislabeled these (e.g. it
        # captured the fragment "North" as a departure terminal on PNR <ref>).
        # Accuracy-first: leave Akbar terminals blank rather than show a wrong one.
        terms = []
        # Stops-column "(Xh:Ym)" is fully inside this segment's own table and
        # can't bleed in from a neighbouring segment's header line the way the
        # looser "X hrs Y mins" phrase can (that phrase sits in the NEXT
        # segment's direction header, which — because we split on 'Airline
        # Ref :' — ends up appended to THIS segment's detail text). Try the
        # scoped pattern first.
        dm = (re.search(r"\((\d{1,2})h:?(\d{2})m\)", detail, re.I)
              or re.search(r"(\d+)\s*hrs?\s*(\d+)\s*min", detail, re.I))
        dep_iata, arr_iata = city2iata.get(dep_c, ""), city2iata.get(arr_c, "")
        # Per-segment airline reference. It is the value we just split on, so it
        # sits at the very start of this segment's detail text. On a normal
        # booking every segment repeats the SAME ref; on a split-carrier booking
        # (two airlines under one agency ref) each direction has its own — real
        # booking AS261347760: Flyadeal B9PS6D out, Saudia 8XMVR7 back. The
        # return ref used to appear nowhere on the client document, so the
        # traveller could not check in for their own return leg.
        _rm = re.match(r"\s*([A-Z0-9]{5,7})\b", detail)
        seg_ref = _rm.group(1) if _rm else ""
        # Per-DIRECTION baggage. Each direction states its own allowance in its
        # own Traveler/Baggage block, and on a split-carrier booking the two
        # airlines allow different amounts (32 Kg on Flyadeal, 1 x 23 Kg on
        # Saudia). The booking-level values above are whichever block happened to
        # match first, so applying them to both legs printed a 32 Kg allowance on
        # a leg that does not have one (§7). Fall back to the booking-level value
        # only when this segment states nothing of its own.
        seg_cabin = _akbar_first_value(r"Carry-?On[ \t]*:?[ \t]*([^\n]*)", detail) or cabin
        seg_checked = _akbar_first_value(r"Baggage[ \t]*Allowance[ \t]*:?[ \t]*([^\n]*)", detail) or checked
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
            # real flight number could go out as CONFIRMED (see <ref>.pdf,
            # Ref <ref> — same root cause, flagged separately for
            # Minh to review before that already-shipped file is touched).
            # Leave it "" on failure so qc_check() flags it for manual review.
            "flight_no": fl,
            # Operating carrier — see _akbar_airline for the two pdfplumber quirks
            # this has to survive (split label, country bleeding in from the next
            # column) and why a failed parse returns "" rather than a default.
            "airline": _akbar_airline(detail),
            "dep_iata": dep_iata, "arr_iata": arr_iata,
            "dep_city": city2disp.get(dep_c, ""), "arr_city": city2disp.get(arr_c, ""),
            "dep_airport": "", "arr_airport": "",
            # Akbar terminals stay blank on purpose (see the 2026-07-17 note above);
            # arr_terminal is still emitted so every portal exposes the same keys and
            # the generator's terminal backfill can populate it from another leg.
            "terminal": terms[0] if terms else "", "arr_terminal": "",
            "dep_time": times[0] if times else "", "dep_date": to_ddmon(dates[0]) if dates else "",
            "arr_time": times[1] if len(times) > 1 else "", "arr_date": to_ddmon(dates[1]) if len(dates) > 1 else "",
            "cabin": default_class,
            "duration": f"{int(dm.group(1))}H {int(dm.group(2)):02d}M" if dm else "",
            "pnr": seg_ref,
            "pax": [{"name": p.get("name", ""), "cabin_bag": seg_cabin,
                     "checked_bag": seg_checked, "seat": ""}
                    for p in d["passengers"]],
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
    # 2026-06-22, PNR <ref>). Spec: references/portal_field_maps.md §3
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
    # 2026-07-30: the repetition this used to dedupe away IS the per-segment data.
    # aJet emits, in document order: Ticket-Information (segment N) then
    # Passenger-Information (segment N, one block per passenger). So every pax
    # match is recorded WITH ITS POSITION, and later assigned to the segment whose
    # block most recently preceded it — giving true per-leg baggage/seat (extra
    # baggage bought on one leg only shows on that leg). The booking-level
    # passengers[] list is still built, deduped by ticket, for the passenger card.
    passengers, seen = [], set()
    pax_hits = []                     # (position, {name, cabin_bag, checked_bag, seat})
    for mo in pax_re.finditer(text):
        tkt = mo.group(4)
        rec = {
            "name": re.sub(r"\s+", " ", mo.group(1)).strip(),
            "ticket_no": tkt,
            "checked_bag": re.sub(r"\s+", " ", mo.group(2)).strip() or "Not specified",
            "cabin_bag": re.sub(r"\s+", " ", mo.group(3)).strip() or "Not specified",
            "seat": _valid_seat(mo.group(5) or ""),
        }
        pax_hits.append((mo.start(), rec))
        if tkt in seen:
            continue
        seen.add(tkt)
        passengers.append(dict(rec))
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
        r"(?:(\d+\s*[Hh]\s*\d+\s*[Mm]))?\s*\n?\s*(VF\s?\d{2,4})\s*\n\s*(ECOJET|BIZJET|PREMIUM|(?i:Basic))?")
    seg_starts = [mo.start() for mo in seg_re.finditer(text)]
    for si_, mo in enumerate(seg_re.finditer(text)):
        brand = (mo.group(10) or "").upper()
        # per-leg pax: every pax block positioned AFTER this segment's block and
        # BEFORE the next one belongs to this leg (see the note by pax_hits).
        _nxt = seg_starts[si_ + 1] if si_ + 1 < len(seg_starts) else len(text)
        _leg_pax = [dict(r) for pos, r in pax_hits if mo.start() <= pos < _nxt]
        flights.append({
            "pax": _leg_pax,
            "dep_date": to_ddmon(mo.group(1)), "arr_date": to_ddmon(mo.group(1)),
            "dep_city": mo.group(2).strip(), "dep_iata": mo.group(3), "dep_time": mo.group(4),
            "arr_city": mo.group(5).strip(), "arr_iata": mo.group(6), "arr_time": mo.group(7),
            "duration": _norm_dur(mo.group(8) or ""),
            "flight_no": re.sub(r"(VF)\s?", r"\1 ", mo.group(9)).strip(), "airline": "aJet",
            # 2026-07-16 fix (PNR <ref>): aJet also sells a "PREMIUM" fare
            # brand (e.g. "PREMIUM / A Class"). Previously only ECOJET/BIZJET
            # were recognised, so PREMIUM bookings rendered cabin = N/A. Map
            # PREMIUM -> "Premium Economy". (BIZJET->Business, ECOJET->Economy.)
            # 2026-08-15 fix (PNR 4B0NA3): aJet's return leg was sold on the
            # "Basic" brand ("VF213 Basic / M Class"), which was not in the
            # alternation — so a ROUND TRIP rendered Economy outbound and N/A
            # inbound on the same document. Basic is an economy fare family,
            # same as ECOJET.
            "cabin": ("Business" if brand == "BIZJET"
                      else "Economy" if brand in ("ECOJET", "BASIC")
                      else "Premium Economy" if brand == "PREMIUM"
                      else "Not specified"),
            # aJet tickets carry no terminal data at all (verified against real
            # emails) — both keys are emitted blank so the schema stays uniform.
            "dep_airport": "", "arr_airport": "", "terminal": "", "arr_terminal": "",
        })
    d["flights"] = flights
    return _finalize(d, ctx)


# aJet DISRUPTION emails (subjects "Flight change information" / "Flight Schedule
# Change Information" / "Flight delay information") carry a blue "New Flight
# Information" panel whose field order is IDENTICAL to a ticket segment, so we
# reuse the same segment shape to read the NEW flight. The intro line names the
# OLD flight ("your flight <date>, <VFxxx>, has been ...") which is the key we
# match against the original booking. Returns a change dict or None (never gates
# the disruption alert — used only to auto-draft a REVISED itinerary for review).
_AJET_NEW_SEG = re.compile(
    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*\n\s*([^\n]+?)\s*\n\s*([A-Z]{3})\s*\n\s*(\d{1,2}:\d{2})\s*\n\s*"
    r"([^\n]+?)\s*\n\s*([A-Z]{3})\s*\n\s*(\d{1,2}:\d{2})\s*\n\s*(?:Connecting|Non[ -]?Stop|Direct)?\s*\n?\s*"
    r"(?:(\d+\s*[Hh]\s*\d+\s*[Mm]))?\s*\n?\s*(VF\s?\d{2,4})\s*\n\s*(ECOJET|BIZJET|PREMIUM|(?i:Basic))?")


def extract_ajet_change(src, ctx=None):
    text = _html_to_text(src)
    # aJet splits the panel date across two lines ("18 July\n2026"); rejoin so the
    # shared segment pattern (which expects the date on one line) still matches.
    text = re.sub(r"([A-Za-z]+)\n(\d{4})\b", r"\1 \2", text)
    pnr = _m(text, r"Reservation\s*Code\s*\n?\s*([A-Z0-9]{5,7})")
    # Case-SENSITIVE (not _m, which forces re.I) so the all-caps name doesn't run
    # on into the following "Your flight ..." sentence.
    _nm = re.search(r"Dear\s*\n\s*([A-Z][A-Z'’.\-]+(?:\s+[A-Z][A-Z'’.\-]+)+)", text)
    name = _nm.group(1).strip() if _nm else ""
    intro = _m(text, r"your\s+flight\s+[^,\n]+,\s*(VF\s?\d{2,4})\s*,\s*has\s+been")
    old_flight_no = re.sub(r"(VF)\s?", r"\1 ", intro).strip() if intro else ""
    low = text.lower()
    status = ("cancelled" if "cancel" in low
              else "delayed" if ("delay" in low or "estimated departure time" in low)
              else "rescheduled")
    # New flight = the LAST "New Flight Information" panel (the first hit is the
    # intro heading; on change/cancel emails an "Old Flight Information" panel
    # precedes it with struck-through times we deliberately ignore).
    idx = low.rfind("new flight information")
    seg = _AJET_NEW_SEG.search(text[idx:] if idx != -1 else text)
    if not (pnr and seg):
        return None
    brand = (seg.group(10) or "").upper()
    new_flight = {
        "dep_date": to_ddmon(seg.group(1)), "arr_date": to_ddmon(seg.group(1)),
        "dep_city": seg.group(2).strip(), "dep_iata": seg.group(3), "dep_time": seg.group(4),
        "arr_city": seg.group(5).strip(), "arr_iata": seg.group(6), "arr_time": seg.group(7),
        "duration": _norm_dur(seg.group(8) or ""),
        "flight_no": re.sub(r"(VF)\s?", r"\1 ", seg.group(9)).strip(), "airline": "aJet",
        "cabin": ("Business" if brand == "BIZJET" else "Economy" if brand in ("ECOJET", "BASIC")
                  else "Premium Economy" if brand == "PREMIUM" else "Not specified"),
        "dep_airport": "", "arr_airport": "", "terminal": "", "arr_terminal": "",
    }
    return {"portal": "aJet", "pnr": pnr, "passenger_name": name,
            "old_flight_no": old_flight_no, "status": status, "new_flight": new_flight}


def apply_flight_change(booking, change):
    """Overwrite the affected leg of `booking` (a finalised booking dict with
    segments[].flights[]) with the disruption's new flight. Matches by OLD flight
    number first (e.g. a cancel that re-numbers VF191->VF189), else by route
    (dep/arr IATA of the new flight). Returns True iff exactly one leg was patched.
    Pure — no I/O — so the cloud runner's revised-itinerary path is unit-tested."""
    new = (change or {}).get("new_flight") or {}
    def norm(x): return "".join((x or "").split()).upper()
    old_no = norm(change.get("old_flight_no"))
    dep, arr = norm(new.get("dep_iata")), norm(new.get("arr_iata"))
    for seg in booking.get("segments", []):
        for fl in seg.get("flights", []):
            by_number = old_no and norm(fl.get("flight_no")) == old_no
            by_route = dep and arr and norm(fl.get("dep_iata")) == dep and norm(fl.get("arr_iata")) == arr
            if by_number or by_route:
                for k in ("flight_no", "dep_time", "arr_time", "dep_date",
                          "arr_date", "duration", "cabin"):
                    if new.get(k):
                        fl[k] = new[k]
                return True
    return False


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
                # Pegasus tickets carry no terminal data — both keys emitted blank
                # so every portal exposes the same flight-dict schema.
                "dep_airport": "", "arr_airport": "", "terminal": "", "arr_terminal": "",
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
    multi-passenger bookings (e.g. PNR <ref>: <name>, <name>,
    <name>) it must NOT be used as the only source. Confirmed against a
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
        # <ref> (single pax, round trip) on 2026-06-21.
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

    # 2026-07-30: Pegasus repeats the WHOLE "Passenger Information" block once per
    # DIRECTION, so parsing each section separately yields that direction's own
    # baggage/seat (the previous dedupe-by-name collapsed them into one). Pegasus
    # gives no finer granularity than the direction, so every leg inside a
    # direction correctly shares that direction's values.
    def _attach(section, legs):
        if not legs:
            return legs
        sec_pax = _pegasus_passengers(section, name)
        for f in legs:
            f["pax"] = [{"name": p.get("name", ""), "cabin_bag": p.get("cabin_bag", ""),
                         "checked_bag": p.get("checked_bag", ""), "seat": p.get("seat", "")}
                        for p in sec_pax]
        return legs

    flights = _attach(out_sec, _pegasus_section_flights(out_sec, _pegasus_section_date(out_sec)))
    if ret_sec:
        flights += _attach(ret_sec, _pegasus_section_flights(ret_sec, _pegasus_section_date(ret_sec)))
    d["flights"] = flights
    return _finalize(d, ctx)


# ═════════════════════════════════════════════════════════════════════════
# 5. TURKISH AIRLINES — PDF attachment ("TicketDetails.pdf" on the
#    "Turkish Airlines - Ticket Details" email). Added 2026-07-27 from 2 real
#    bookings (TDYWK8, WENFE5) — both Gulf<->small-Turkish-city connections via
#    Istanbul. Source is pdfplumber text of the attachment, NOT the email body
#    (the body only shows an aggregate summary with no per-leg times).
#
#    Real pdfplumber quirks confirmed against both samples:
#      * The header summary block ("01:15 09:55 / IST / DMM OGU / ...") is
#        column-scrambled by pdfplumber — unusable. The DETAILED "Flight
#        details" listing below it reads cleanly and linearly; that's the
#        only thing this parses.
#      * Stops come in DEPARTURE/ARRIVAL PAIRS per leg, not a continuous
#        chain — e.g. 4 stops for a 1-stop connection: dep0, arr0(=IST),
#        dep1(=IST), arr1. Zipping stops[i]/stops[i+1] consecutively is
#        WRONG (would fabricate a 3rd "flight" out of the IST->IST layover
#        gap); pair them (0,1), (2,3), ... instead.
#      * The 3-column Fare-Rules table (Change / Refund / Baggage) gets
#        interleaved by row, so "Check-in Baggage : 1 piece x 23" and its
#        "kg" unit can land on DIFFERENT lines with an unrelated cell's text
#        in between. Don't require "kg" immediately adjacent to the number.
#      * "Aircraft type" can render as a broken template placeholder
#        ("planetypelookup.D21 - planemodellookup.D21") — a bug in Turkish
#        Airlines' own PDF, confirmed on TWO different real bookings. Not
#        extracted (aircraft type isn't part of this project's data model).
#      * Each direction's own "Journey duration" figure can be internally
#        inconsistent with the sum of its own leg segments (off by ~10 min
#        on one real sample) — Turkish Airlines' own rounding artifact, not
#        ours to reconcile. Duration is always computed from the parsed
#        dep/arr times (_diff_hm), never read from that summary figure.
#
#    A FLAT list of legs (outbound legs, then inbound legs, in booking order)
#    is handed to `_finalize()` — the existing group_segments()/
#    _layovers_for()/_mark_next_day() machinery correctly finds the
#    Outbound/Inbound split and computes layovers on its own: the artificial
#    week(s)-long "gap" between the last outbound leg and the first inbound
#    leg is by far the largest connection gap, so group_segments() splits
#    there naturally — verified against both real bookings.
# ═════════════════════════════════════════════════════════════════════════
_TA_DIR_RE = re.compile(
    r"([A-Za-zÇĞİÖŞÜçğıöşü\-]+(?:\s[A-Za-zÇĞİÖŞÜçğıöşü\-]+)*)\s*\(([A-Z]{3})\)\s*-\s*"
    r"([A-Za-zÇĞİÖŞÜçğıöşü\-]+(?:\s[A-Za-zÇĞİÖŞÜçğıöşü\-]+)*)\s*\(([A-Z]{3})\)\s+"
    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s+\w+"
)
_TA_STOP_RE = re.compile(
    r"(\d{1,2}:\d{2})\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ\-]+(?:\s[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ\-]*)*)"
    r"\s*\(([A-ZÇĞİÖŞÜ\s]+)\)\s+([A-Za-zÇĞİÖŞÜçğıöşü .\-]+?)\s*\(([A-Z]{3})\)"
)
_TA_FNO_RE = re.compile(r"Airline\s*-\s*Flight\s*no:\s*TURKISH AIRLINES\s*-\s*([A-Z]{2}\d+)", re.I)


def _ta_norm_flight(carrier_num):
    m = re.match(r"([A-Z]{2})(\d+)", carrier_num)
    return f"{m.group(1)} {m.group(2)}" if m else carrier_num


def extract_turkish_airlines(pdf_text, ctx=None):
    if not pdf_text:
        raise ValueError("Turkish Airlines source document not found / unreadable")
    t = pdf_text
    d = {"portal": "Turkish Airlines"}
    d["pnr"] = _m(t, r"(?:Mr|Mrs|Ms)\.?\s+[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ '\-]+\n([A-Z0-9]{5,7})\b")
    d["booked_on"] = to_ddmon(_m(t, r"Transaction date:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})"))
    d["status"] = "Confirmed" if re.search(r"ticket has been created", t, re.I) else ""

    # passengers — "Passenger information" table: "NAME  TICKETNO  ..."
    pax_block = t
    sec = re.search(r"Passenger information(.*?)Passenger contact information", t, re.S)
    if sec:
        pax_block = sec.group(1)
    passengers = [
        {"name": nm.title(), "ticket_no": tkt, "seat": "", "cabin_bag": "", "checked_bag": ""}
        for nm, tkt in re.findall(r"(?m)^([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ '\-]+?)\s+(\d{10,})\b", pax_block)
    ]
    # baggage is per-booking in these samples (not per-passenger) — apply to all pax.
    # See the "3-column table interleaving" note above for why "kg" isn't required
    # immediately after the weight number.
    cm = re.search(r"Check-?in Baggage\s*:\s*(\d+)\s*piece[s]?\s*x\s*(\d+)", t, re.I)
    checked_str = f"{cm.group(1)} piece x {cm.group(2)} kg" if cm else ""
    cam = re.search(r"Cabin Baggage\s*:\s*(\d+)\s*piece[s]?\s*x\s*(\d+)", t, re.I)
    cabin_str = f"{cam.group(1)} piece x {cam.group(2)} kg" if cam else ""
    for p in passengers:
        p["checked_bag"], p["cabin_bag"] = checked_str, cabin_str
    d["passengers"] = passengers or [{"name": "Not specified", "ticket_no": "Not specified",
                                      "cabin_bag": "", "checked_bag": "", "seat": ""}]

    headers = list(_TA_DIR_RE.finditer(t))
    all_flights = []
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(t)
        # Scope to this direction's own "Flight details" listing; cut before
        # Fare Rules so the NEXT direction's stops can't bleed in.
        scoped = t[start:end].split("Fare Rules")[0]
        stops = list(_TA_STOP_RE.finditer(scoped))
        fnos = _TA_FNO_RE.findall(scoped)
        if len(stops) < 2 or len(stops) % 2 != 0 or len(fnos) != len(stops) // 2:
            continue   # unexpected shape for this direction — leave it out; qc_check
                       # will flag the booking for missing segments rather than guess
        cabin = (_m(scoped, r"(Economy|Business|First|Premium\s*Economy)\s*Class") or "Economy").title()
        # 2026-07-30 per-leg pax: Turkish Airlines states baggage in a Fare-Rules
        # block PER DIRECTION (not per leg), so read THIS direction's own figures
        # from its full block (including the Fare Rules the `scoped` slice cuts
        # off) and apply them to every leg in the direction. TA's PDF carries NO
        # seat data at all (verified on both real files), so seat stays "" and the
        # generator omits the SEAT column entirely.
        _dir_block = t[start:end]
        _dcm = re.search(r"Check-?in Baggage\s*:\s*(\d+)\s*piece[s]?\s*x\s*(\d+)", _dir_block, re.I)
        _dca = re.search(r"Cabin Baggage\s*:\s*(\d+)\s*piece[s]?\s*x\s*(\d+)", _dir_block, re.I)
        _dir_checked = f"{_dcm.group(1)} piece x {_dcm.group(2)} kg" if _dcm else checked_str
        _dir_cabin = f"{_dca.group(1)} piece x {_dca.group(2)} kg" if _dca else cabin_str
        _dir_pax = [{"name": p["name"], "cabin_bag": _dir_cabin,
                     "checked_bag": _dir_checked, "seat": ""} for p in d["passengers"]]
        base_date = to_ddmon(h.group(5))
        # Walk the calendar date forward across the WHOLE stop chain on any
        # time rollover (e.g. a 20:15 departure arriving 00:15 next day).
        dates = [base_date]
        for i2 in range(1, len(stops)):
            prev_t, cur_t = stops[i2 - 1].group(1), stops[i2].group(1)
            if cur_t < prev_t:
                dt = datetime.strptime(dates[-1], "%d %b %Y") + timedelta(days=1)
                dates.append(dt.strftime("%d %b %Y"))
            else:
                dates.append(dates[-1])
        for i2 in range(0, len(stops), 2):
            s0, s1 = stops[i2], stops[i2 + 1]
            dep_time, dep_city, _dep_country, dep_ap, dep_iata = s0.groups()
            arr_time, arr_city, _arr_country, arr_ap, arr_iata = s1.groups()
            dep_date, arr_date = dates[i2], dates[i2 + 1]
            all_flights.append({
                "flight_no": _ta_norm_flight(fnos[i2 // 2]), "airline": "Turkish Airlines",
                "dep_iata": dep_iata, "arr_iata": arr_iata,
                "dep_city": dep_city.title(), "arr_city": arr_city.title(),
                "dep_airport": dep_ap.strip(), "arr_airport": arr_ap.strip(),
                "terminal": "", "arr_terminal": "",
                "dep_date": dep_date, "dep_time": dep_time,
                "arr_date": arr_date, "arr_time": arr_time,
                "cabin": cabin, "duration": _diff_hm(dep_date, dep_time, arr_date, arr_time),
                "pax": [dict(p) for p in _dir_pax],
            })
    d["flights"] = all_flights
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
            "dep_city": "", "arr_city": "", "dep_airport": "", "arr_airport": "",
            "terminal": "", "arr_terminal": "", "duration": "",
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


# ── Airport-name reference table ───────────────────────────────────────────
# Only ONE portal (Alhind) states airport names in a machine-readable way. The
# other four give the city and the IATA code but no name — Akbar's PDF does
# contain it, but pdfplumber linearises the From/To cells so badly that a name
# cannot be reliably attributed to the departure vs the arrival side (the same
# scrambling documented in §9), and printing "King Fahd" under the wrong airport
# would be worse than printing nothing. So the name comes from this table
# instead, keyed by IATA.
#
# This is a REFERENCE table, not extracted data, and that distinction is why it
# is allowed here while the equivalent terminal table was rejected (§8,
# 2026-07-27): an airport's NAME is a stable, single-valued fact — JED is King
# Abdulaziz International Airport on every ticket, every airline, every season.
# A TERMINAL is not: it varies by carrier, route and schedule at hubs like
# IST/DXB/JED, so a static terminal map would confidently print wrong ones.
#
# It is applied as a BACKFILL ONLY (generate_itinerary_v3.build_html): whatever
# the document itself stated always wins, and an IATA not listed here simply
# renders no name, exactly as today. Add codes as new routes appear.
AIRPORT_NAMES = {
    # Saudi Arabia
    "JED": "King Abdulaziz International Airport",
    "RUH": "King Khalid International Airport",
    "DMM": "King Fahd International Airport",
    "MED": "Prince Mohammad Bin Abdulaziz International Airport",
    "AHB": "Abha International Airport",
    "TIF": "Taif International Airport",
    "ELQ": "Prince Naif Bin Abdulaziz International Airport",
    "TUU": "Tabuk Regional Airport",
    "GIZ": "Jazan King Abdullah bin Abdulaziz Airport",
    # Gulf
    "DXB": "Dubai International Airport",
    "DWC": "Al Maktoum International Airport",
    "AUH": "Zayed International Airport",
    "SHJ": "Sharjah International Airport",
    "DOH": "Hamad International Airport",
    "KWI": "Kuwait International Airport",
    "BAH": "Bahrain International Airport",
    "MCT": "Muscat International Airport",
    "SLL": "Salalah International Airport",
    # Turkiye
    "IST": "Istanbul Airport",
    "SAW": "Istanbul Sabiha Gokcen International Airport",
    "ESB": "Ankara Esenboga Airport",
    "ADB": "Izmir Adnan Menderes Airport",
    "AYT": "Antalya Airport",
    "ADA": "Adana Sakirpasa Airport",
    "TZX": "Trabzon Airport",
    "GZT": "Gaziantep Airport",
    "DIY": "Diyarbakir Airport",
    "VAN": "Van Ferit Melen Airport",
    "ERZ": "Erzurum Airport",
    "MLX": "Malatya Erhac Airport",
    # Pakistan
    "ISB": "Islamabad International Airport",
    "KHI": "Jinnah International Airport",
    "LHE": "Allama Iqbal International Airport",
    "PEW": "Bacha Khan International Airport",
    "MUX": "Multan International Airport",
    "SKT": "Sialkot International Airport",
    "LYP": "Faisalabad International Airport",
    # India
    "DEL": "Indira Gandhi International Airport",
    "BOM": "Chhatrapati Shivaji Maharaj International Airport",
    "MAA": "Chennai International Airport",
    "BLR": "Kempegowda International Airport",
    "HYD": "Rajiv Gandhi International Airport",
    "CCU": "Netaji Subhas Chandra Bose International Airport",
    "COK": "Cochin International Airport",
    "TRV": "Trivandrum International Airport",
    "CCJ": "Calicut International Airport",
    "CNN": "Kannur International Airport",
    "AMD": "Ahmedabad International Airport",
    "GOI": "Dabolim Airport",
    "LKO": "Chaudhary Charan Singh International Airport",
    "GOP": "Gorakhpur Airport",
    # Elsewhere on the network
    "CAI": "Cairo International Airport",
    "AMM": "Queen Alia International Airport",
    "BEY": "Beirut Rafic Hariri International Airport",
    "KTM": "Tribhuvan International Airport",
    "DAC": "Hazrat Shahjalal International Airport",
    "CMB": "Bandaranaike International Airport",
    "MLE": "Velana International Airport",
    "KUL": "Kuala Lumpur International Airport",
    "CGK": "Soekarno-Hatta International Airport",
    "LHR": "London Heathrow Airport",
}


# ── India-arrival detection (drives the Air Suvidha guide attachment) ──────
# Air Suvidha 2.0 is a health self-declaration required for INTERNATIONAL
# arrivals into India. So the trigger is: a booking that contains at least one
# flight whose ARRIVAL airport is in India while its DEPARTURE airport is not —
# i.e. an inbound international leg. Purely domestic Indian hops (both ends in
# India) do NOT trigger it. IATA codes of Indian airports (international + major
# domestic; the domestic ones matter so a domestic leg isn't mistaken for an
# international arrival).
INDIA_IATA = {
    "DEL", "BOM", "MAA", "BLR", "HYD", "CCU", "COK", "TRV", "CJB", "CCJ",
    "GOI", "GOX", "AMD", "PNQ", "JAI", "LKO", "VNS", "IXC", "ATQ", "GAU",
    "IXE", "TIR", "TRZ", "IXM", "VTZ", "NAG", "IXB", "BBI", "PAT", "IXZ",
    "IXA", "IMF", "IXJ", "SXR", "KNU", "BDQ", "STV", "HBX", "IXR", "RPR",
    "IDR", "BHO", "JLR", "IXD", "GWL", "DED", "IXL", "JDH", "UDR", "BHJ",
    "DIB", "IXS", "TEZ", "RJA", "VGA", "MYQ", "IXU", "JRH", "DMU", "SHL",
    "AJL", "IXG", "JGA", "PBD", "RAJ", "CDP", "JRG", "GAY", "IXW", "DBR",
    "KUU", "SLV", "AGR", "HJR", "PGH", "SAG", "KLH", "TCR", "BEP", "IXY",
}


def india_arrival(data):
    """True if the booking includes an INTERNATIONAL flight arriving in India
    (arrival in India, departure outside India). Triggers the Air Suvidha guide."""
    for seg in (data or {}).get("segments", []):
        for f in seg.get("flights", []):
            arr = (f.get("arr_iata") or "").strip().upper()
            dep = (f.get("dep_iata") or "").strip().upper()
            if arr in INDIA_IATA and dep and dep not in INDIA_IATA:
                return True
    return False


# ── disruption watch (cancellations / schedule changes) ─────────────────────
# The PORTALS registry only ever matches NEW ticket CONFIRMATIONS. Cancellation
# and schedule-change emails have different subjects and were slipping past the
# automation entirely — buried in the cs@ inbox and missed by staff. The cloud
# runner (main.scan_disruptions) does a subject-line keyword scan of the whole
# inbox and raises ONE private ACTION-REQUIRED alert per new match.
#
# Two lists, on purpose:
#   * DISRUPTION_QUERY_TERMS — the COARSE net handed to Gmail search (spelled-out
#     words Gmail tokenises well).
#   * DISRUPTION_KEYWORDS    — the AUTHORITATIVE substring stems checked here in
#     Python (unit-tested offline, no Gmail needed). Gmail returns candidates;
#     disruption_match() has the final say so the rule is testable and precise.
# Tuned broad on purpose (better a rare false alarm than a missed cancellation);
# refine the lists as real false alarms surface.
# NOTE: both lists were cross-checked (2026-07-19) against REAL disruption emails
# across the whole cs@ mailbox. Confirmed templates the watch must catch:
#   aJet      "Flight change information" / "Flight Schedule Change Information"
#   IndiGo    "Your Revised IndiGo Itinerary"
#   airblue   "Flight Delayed Notification"
#   Turkish   "Schedule Change"
#   flydubai  "Booking cancelled #..." / "Important changes to your booking: ..."
#   Qatar     "Your flight schedule has changed"
#   Emirates  "The departure time has changed for your flight to ..."
#   Etihad    "Important: Flight change"
#   ITA       "Delay of your flight to ..."
#   Gulf Air  "Gulf Air Flight Time Change"
#   Fly Jinnah"Fly Jinnah Booking Change Notification"
#   Himalaya  "FLIGHT CANCELLATION INFORMATION" / "SCHEDULE CHANGE INFORMATION"
#   Akbar/Alhind B2B  "SCHEDULE CHANGE // <PNR>" / "FLIGHT DISRUPTED"
# Must NOT match (real noise in the same mailbox): "Update on your upcoming flight"
# / "Update on your flight to <city>" (upsell), "Oman Air - Important Update",
# "PIA Contact Change" (contact info, not the flight), and Air Arabia "Itinerary
# for the Reservation <ref>" (a confirmation) — hence no bare "change"/"itinerary"
# keyword. Keep the lists in sync if new templates appear.
DISRUPTION_QUERY_TERMS = [
    "cancel", "cancelled", "canceled", "cancellation", "cancelling",
    "reschedule", "rescheduled", "rescheduling",
    "schedule change", "flight change", "time change", "timing change",
    "changed", "changes", "booking change",
    "revised", "itinerary change", "updated itinerary",
    "delay", "delayed", "postponed",
    "disruption", "disrupted", "rebooked", "rebooking", "new departure",
]

DISRUPTION_KEYWORDS = [
    "cancel",              # cancelled / cancellation / canceled / cancelling
    "reschedul",           # reschedule(d) / rescheduling
    "schedule change", "change in schedule",
    "schedule has changed",   # Qatar "Your flight schedule has changed"
    "flight change", "flight changed",
    "time change", "timing change",
    "has changed",         # Emirates "departure time has changed" / generic
    "booking change",      # Fly Jinnah "Booking Change Notification"
    "change to your booking", "changes to your booking",   # flydubai
    "revised",             # "Your Revised IndiGo Itinerary" / revised departure
    "itinerary change", "updated itinerary",
    "delay",               # delayed / delay ("Flight Delayed Notification")
    "postponed", "brought forward",
    "disrupt",             # disruption / disrupted
    "rebook",              # rebook / rebooked / rebooking
    "new departure", "departure change",
]


def disruption_match(subject):
    """Return the first disruption keyword found in `subject` (case-insensitive
    substring match), or "" if none. Pure/offline — the authoritative filter
    behind main.scan_disruptions, so the exact rule is unit-tested without Gmail.
    Cross-checked against real airline/B2B disruption subjects (see note above)."""
    s = (subject or "").lower()
    for kw in DISRUPTION_KEYWORDS:
        if kw in s:
            return kw
    return ""


def disruption_category(subject="", preview="", keyword=""):
    """Classify a disruption into 'cancellation' | 'delay' | 'schedule_change'
    from its subject + preview (keyword as a fallback signal). Used only to
    colour/label the alert e-mail — it never gates whether an alert is sent.

    CANCELLATION wins over everything: an email whose subject is only "Flight
    change information" but whose body says "has been canceled" IS a cancellation
    (this is the real aJet case), so we look at the preview text too, not just the
    subject/keyword."""
    text = f"{subject} {preview} {keyword}".lower()
    if "cancel" in text:
        return "cancellation"
    if "delay" in text or "postpone" in text:
        return "delay"
    return "schedule_change"


# A booking reference / PNR following a strong label. The code group is OUTSIDE
# the case-insensitive scope so it only matches an UPPERCASE alnum token (a real
# PNR shape like Turkish's "UCHMPF"), never the lowercase prose around it.
_DISRUPTION_PNR_RE = re.compile(
    r"(?i:reservation\s+code|reservation\s+number|reservation\s+no|"
    r"booking\s+reference|booking\s+ref(?:erence)?|booking\s+code|booking\s+id|"
    r"record\s+locator|file\s+key|\bPNR\b)"
    r"[\s:#/\-]*([A-Z0-9]{5,7})\b")
# Uppercase words that can follow "PNR"/"booking ..." but are NOT a code — keeps a
# stray "PNR CHANGED" from becoming a bogus dedup key.
_DISRUPTION_STOPWORDS = {
    "CHANGE", "CHANGED", "CANCEL", "CANCELLED", "CANCELED", "FLIGHT", "UPDATE",
    "UPDATED", "DELAY", "DELAYED", "BOOKING", "TICKET", "STATUS", "NUMBER",
    "PLEASE", "REVISED", "INFORM", "NOTICE", "ALERT", "ACTION", "DETAILS",
}


# The disruption's ACTIONABLE facts — flight number, route, date, times. These
# are what make one notice genuinely different from another; the surrounding
# prose (greeting, apology wording) is not. Used to fingerprint a notice so an
# airline's identical re-sends collapse while a real revision still alerts.
_FACT_FLIGHT = re.compile(r"\b((?:[A-Z]{2}|[A-Z][0-9]|[0-9][A-Z]))\s?-?\s?(\d{2,4})\b")
_FACT_ROUTE = re.compile(r"\b([A-Z]{3})\s*[-–>]+\s*([A-Z]{3})\b")
_FACT_HHMM = re.compile(r"\b(\d{1,2}:\d{2})\b")
_FACT_HHMM4 = re.compile(r"\b(\d{4})\s*-\s*(\d{4})\b")          # IndiGo "0510-0755"
_FACT_DATE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\b", re.I)


def disruption_facts(text=""):
    """Order-stable fingerprint of the flight facts in a disruption notice.
    Empty string when the notice carries no extractable facts."""
    t = text or ""
    facts = set()
    for m in _FACT_FLIGHT.finditer(t):
        facts.add(f"{m.group(1)}{m.group(2)}")
    for m in _FACT_ROUTE.finditer(t):
        facts.add(f"{m.group(1)}-{m.group(2)}")
    for m in _FACT_HHMM.finditer(t):
        facts.add(m.group(1))
    for m in _FACT_HHMM4.finditer(t):
        facts.add(f"{m.group(1)}-{m.group(2)}")
    for m in _FACT_DATE.finditer(t):
        facts.add(re.sub(r"\s+", " ", m.group(1)).strip().title())
    return "|".join(sorted(facts))


def disruption_dedup_key(subject="", preview="", sender="", category=""):
    """Booking-level dedup key for the disruption watch, or "" if no reliable
    booking reference can be extracted (caller then falls back to message_id).

    Airlines re-send a disruption notice for the SAME booking repeatedly, each a
    NEW message_id — Turkish Airlines re-sent "Flight Delay Information" for one
    reservation 3x in 5 hours; IndiGo re-sent a byte-identical "Revised Itinerary"
    5x across two days. De-duping on message_id alone re-alerts every time.

    The key is <sender-domain>:<PNR>:<category>:<facts-fingerprint>, so:
      * an IDENTICAL re-send collapses to one alert — permanently, not just for
        a day (the earlier day-based key re-alerted every calendar day, and also
        broke on airlines that backdate the Date header — IndiGo's re-send that
        ARRIVED on 03 Aug was stamped 02 Aug and alerted a second time);
      * a genuinely NEW revision (different flight/route/date/time) still alerts,
        even minutes later on the same day — which the day-based key wrongly
        suppressed;
      * a different booking, or an escalation (cancellation after a delay), still
        alerts.

    RETURNS A HASH, never the raw reference: this key is persisted to
    disruption_ids.json in a PUBLIC repo, so it must not leak a PNR (§11 — the
    other logs deliberately store only opaque ids)."""
    text = f"{subject}  {preview}"
    code = ""
    for m in _DISRUPTION_PNR_RE.finditer(text):
        c = m.group(1).upper()
        if c not in _DISRUPTION_STOPWORDS:
            code = c
            break
    if not code:
        return ""
    dom = ""
    md = re.search(r"@([A-Za-z0-9.\-]+)", sender or "")
    if md:
        dom = md.group(1).lower()
    raw = f"{dom}:{code}:{(category or '').lower()}:{disruption_facts(text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── Pivot OS sync payload (Producer side of PIVOT_OS_INTEGRATION.md) ─────────
# Build the JSON event that main.notify_pivot_os() POSTs to Pivot OS's
# /api/itinerary-sync when an itinerary is produced. Pure (no I/O) so the exact
# shape is unit-tested. Contract v1.0 agreed with the Pivot OS session:
#   * departure/arrival DATES converted to ISO YYYY-MM-DD (their one ask; times &
#     flight_no stay as-is — display-only on their side);
#   * idempotency_key = "<pnr>:<status>:<source_ref>" (they upsert on it);
#   * reference.match_key = "<pnr>:<portal>" (their duplicate lookup is composite);
#   * financials ALWAYS null (this system has no fare data — the user fills it in).
def _iso_date(s):
    """'19 Jul 2026' -> '2026-07-19'; blank / unparseable -> None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d %b %Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def pivot_os_payload(booking, pdf_url="", event="itinerary.created", source_ref=""):
    pnr = (booking.get("pnr") or "").strip()
    portal = (booking.get("portal") or "").strip()
    status = (booking.get("doc_status") or "confirmed").strip().lower()
    crs = (booking.get("crs_ref") or "").strip()
    first_iata = last_iata = ""
    first_dep = None
    segments = []
    for seg in booking.get("segments", []):
        flights = []
        for f in seg.get("flights", []):
            iso = _iso_date(f.get("dep_date"))
            if first_dep is None and iso:
                first_dep = iso
            if not first_iata and f.get("dep_iata"):
                first_iata = f.get("dep_iata")
            if f.get("arr_iata"):
                last_iata = f.get("arr_iata")
            flights.append({
                "airline": f.get("airline", ""), "flight_no": f.get("flight_no", ""),
                "cabin": f.get("cabin", ""),
                "dep_iata": f.get("dep_iata", ""), "dep_city": f.get("dep_city", ""),
                "dep_airport": f.get("dep_airport", ""), "terminal": f.get("terminal", ""),
                "dep_date": iso, "dep_time": f.get("dep_time", ""),
                "arr_iata": f.get("arr_iata", ""), "arr_city": f.get("arr_city", ""),
                "arr_airport": f.get("arr_airport", ""), "arr_terminal": f.get("arr_terminal", ""),
                "arr_date": _iso_date(f.get("arr_date")), "arr_time": f.get("arr_time", ""),
                "duration": f.get("duration", ""),
            })
        segments.append({"type": seg.get("type", ""), "flights": flights,
                         "layovers": seg.get("layovers", [])})
    passengers = [{
        "name": p.get("name", ""), "ticket_no": p.get("ticket_no", ""),
        "cabin_bag": p.get("cabin_bag", ""), "checked_bag": p.get("checked_bag", ""),
        "seat": p.get("seat", ""),
    } for p in booking.get("passengers", [])]
    jt = (booking.get("journey_type") or "ONE-WAY").upper()
    journey = "ROUND TRIP" if ("ROUND" in jt or "RETURN" in jt) else "ONE-WAY"
    return {
        "schema_version": "1.0",
        "event": event,
        "idempotency_key": f"{pnr}:{status}:{source_ref}",
        "source": "itinerary-automation",
        "reference": {
            "pnr": pnr,
            "booking_ref": (booking.get("booking_ref") or "").strip() or None,
            "crs_ref": crs if (crs and crs.upper() != pnr.upper()) else None,
            "portal": portal,
            "source_ref": source_ref,
            "match_key": f"{pnr}:{portal}",
        },
        "status": status,
        "journey_type": journey,
        "booked_on": booking.get("booked_on", ""),
        "passengers": passengers,
        "segments": segments,
        "route_summary": f"{first_iata} → {last_iata}" if (first_iata and last_iata) else "",
        "first_dep_date": first_dep,
        "india_arrival": india_arrival(booking),
        "pdf_url": pdf_url or None,
        "financials": None,
    }


# ── registry ───────────────────────────────────────────────────────────────
PORTALS = [
    {"name": "Alhind",        "from": "alhind@alhindsanchar.com",   "subject": "Air Ticket",                                      "source": "body",      "fn": extract_alhind},
    {"name": "Akbar Travels", "from": "sanoreply@akbartravels.com", "subject": "Booking Success",                                 "source": "drive_pdf", "fn": extract_akbar},
    {"name": "Akbar Travels", "from": "sanoreply@akbartravels.com", "subject": "Ticket Copy",                                    "source": "drive_pdf", "fn": extract_akbar},
    {"name": "aJet",          "from": "onlineticket@mail.ajet.com", "subject": "Ticket information",                              "source": "body",      "fn": extract_ajet},
    {"name": "Pegasus",       "from": "pegasus@flypgs.com",         "subject": "Your booking is confirmed! View your ticket now", "source": "body",      "fn": extract_pegasus},
    {"name": "Turkish Airlines", "from": "onlineticket@mail.turkishairlines.com", "subject": "Turkish Airlines - Ticket Details", "source": "drive_pdf", "fn": extract_turkish_airlines},
]
