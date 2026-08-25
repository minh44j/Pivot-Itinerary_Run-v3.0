"""Manually issue ONE booking whose portal PDF lacks the passenger table.

First case: Akbar's multi-city (TRIP n) layout, real booking AS261373110 —
the ticket PDF carries no passenger name or ticket number anywhere in its
extractable text, so qc_check (correctly) refuses to issue. The facts exist,
split across two emails in the cs@ inbox:

    BOOKING_MSG_ID : the portal's "Booking Success" email (flights, refs,
                     per-trip baggage — parsed by the live extractor)
    NAMES_MSG_ID   : the airline's own e-ticket receipt (passenger names +
                     e-ticket numbers, stated verbatim by the airline)

This merges the two, re-runs qc_check, renders the normal branded PDF, uploads
it to Drive and emails it exactly like an automated confirmation. Runs ONLY in
CI via workflow_dispatch (the secrets live there); the Action log stays free of
PII — names/tickets are never printed, only counts.

A human triggers it per booking after reading the manual-review flag: this is
deliberately not automatic — merging a second document into a client-facing
itinerary is exactly the judgement call the flag exists for (§7).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extractors                                     # noqa: E402
import main as M                                      # noqa: E402
from generate_itinerary_v3 import build_pdf           # noqa: E402


def _eticket_passengers(gmail, msg_id):
    """Names + ticket numbers from an airline e-ticket email, verbatim.

    Matches '<Title>.<Name>' followed shortly by 'e-Ticket: <13 digits>'
    (Saudia's receipt format). De-duplicated by ticket number because the
    receipt repeats every passenger once per flight.
    """
    msg = gmail.users().messages().get(userId="me", id=msg_id, format="full")\
        .execute(num_retries=M.API_RETRIES)
    # _plain_body returns the RAW HTML — flatten it the same way the body
    # extractors do, so the name and its e-Ticket line sit on adjacent lines.
    text = M._html_to_text(M._plain_body(msg))
    pax, seen = [], set()
    for mo in re.finditer(
            r"\b((?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.?\s*[A-Z][A-Za-z .'\-]+?)\s*"
            r"[\s|]+e-?Ticket\s*:?\s*(\d{10,})", text):
        name = re.sub(r"\s+", " ", mo.group(1)).strip()
        # Saudia writes "Mr.Abdulaziz" with no space after the title's period
        name = re.sub(r"^((?:Mr|Mrs|Ms|Mstr|Master|Miss|Dr)\.)(?=\S)", r"\1 ", name)
        tkt = mo.group(2)
        if tkt not in seen:
            seen.add(tkt)
            pax.append({"name": name, "ticket_no": tkt})
    return pax


def run():
    booking_id = os.environ["BOOKING_MSG_ID"].strip()
    names_id = os.environ["NAMES_MSG_ID"].strip()
    gmail, drive = M._services()

    msg = gmail.users().messages().get(userId="me", id=booking_id, format="full")\
        .execute(num_retries=M.API_RETRIES)
    portal = M._portal_for(msg)
    if not portal or portal.get("source") != "drive_pdf":
        raise SystemExit("BOOKING_MSG_ID is not a PDF-portal booking email")
    src, words = M.akbar_attachment_text(gmail, msg, with_words=True)
    ctx = {"date": M._email_date_ddmon(msg)}
    if words:
        ctx["terminals"] = extractors.akbar_terminals_from_words(words)
    data = portal["fn"](src, ctx)

    pax = _eticket_passengers(gmail, names_id)
    if not pax:
        raise SystemExit("no passengers found in NAMES_MSG_ID — nothing issued")
    # identity from the airline receipt; baggage stays whatever the portal PDF
    # states for the booking / each leg (never invented here)
    bag = data["passengers"][0] if data.get("passengers") else {}
    data["passengers"] = [{**p, "cabin_bag": bag.get("cabin_bag", ""),
                           "checked_bag": bag.get("checked_bag", ""), "seat": ""}
                          for p in pax]
    for seg in data.get("segments", []):
        for fl in seg.get("flights", []):
            leg = (fl.get("pax") or [{}])[0]
            fl["pax"] = [{"name": p["name"],
                          "cabin_bag": leg.get("cabin_bag", ""),
                          "checked_bag": leg.get("checked_bag", ""),
                          "seat": ""} for p in pax]

    problem = extractors.qc_check(data)
    if problem:
        raise SystemExit(f"still fails qc_check after merge: {problem}")

    from datetime import datetime
    date_sub = datetime.now().strftime("%Y-%m-%d")
    pdf_path = build_pdf(data, os.path.join(M.OUT_DIR, date_sub),
                         project_dir=M.PROJECT_DIR)
    if extractors.india_arrival(data):
        M._append_air_suvidha(pdf_path)
    link = M.upload_to_drive(drive, pdf_path, date_sub)
    send_gmail, sender = M._sender_gmail()
    M.email_pdf(send_gmail, sender, pdf_path, data, source_ref=booking_id)
    print(f"issued: {len(pax)} passenger(s), {sum(len(s['flights']) for s in data['segments'])} leg(s); "
          f"drive={'yes' if link else 'no'}; emailed as {os.path.basename(pdf_path)}")


if __name__ == "__main__":
    run()
