"""Find already-issued bookings whose connecting leg carries the wrong date.

The overnight-connection defect (fixed 2026-08-30, real booking 2BBZE2) dated a
leg that departs after midnight to the PREVIOUS day, because portals that state
one date for the whole journey stamp it on every leg. It shipped undetected for
weeks — _diff_hm wraps a negative gap into +24h, so the layover printed a
plausible duration over impossible dates — and at least one document reached a
corporate client.

This re-extracts every already-processed booking TWICE, once with the
correction disabled and once with it on, and reports the ones whose leg dates
differ. Those are exactly the documents that went out wrong.

PRIVACY: the Action log is public (§11), so this prints ONLY the opaque Gmail
message_id, the portal, and the leg dates. No PNR, no passenger name, no
subject. Look each message_id up in the cs@ inbox to identify the booking.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extractors as E                                 # noqa: E402
import main as M                                       # noqa: E402


def _legs(data):
    return [(f.get("flight_no", ""), f.get("dep_date", ""), f.get("arr_date", ""))
            for s in data.get("segments", []) for f in s.get("flights", [])]


def run():
    window = os.environ.get("SWEEP_WINDOW") or "newer_than:120d"
    gmail, drive = M._services()
    log = M.load_log()
    done = M.processed_ids(log)

    checked = affected = errors = 0
    _real_roll = E._roll_overnight_connections

    for portal in extractors_portals():
        for mid in M.search_messages(gmail, portal, window):
            if mid not in done:
                continue          # never issued, so nothing was sent out wrong
            try:
                msg = gmail.users().messages().get(
                    userId="me", id=mid, format="full").execute(num_retries=M.API_RETRIES)
                subj = M._header(msg, "Subject").lower()
                frm = M._header(msg, "From").lower()
                if portal["subject"].lower() not in subj or portal["from"].lower() not in frm:
                    continue

                ctx = {"date": M._email_date_ddmon(msg)}
                if portal["source"] == "drive_pdf":
                    src, words = M.akbar_attachment_text(gmail, msg, with_words=True)
                    if not src:
                        continue          # Drive fallback: skip rather than re-fetch
                    if words:
                        ctx["terminals"] = E.akbar_terminals_from_words(words)
                else:
                    src = M._plain_body(msg)
                if not src:
                    continue

                E._roll_overnight_connections = lambda flights: None
                before = _legs(portal["fn"](src, dict(ctx)))
                E._roll_overnight_connections = _real_roll
                after = _legs(portal["fn"](src, dict(ctx)))

                checked += 1
                if before != after:
                    affected += 1
                    print(f"AFFECTED {mid}  portal={portal['name']}")
                    for (fno, bd, ba), (_, ad, aa) in zip(before, after):
                        mark = "  <-- changed" if (bd, ba) != (ad, aa) else ""
                        print(f"    leg {fno or '?'}: dep {bd} -> {ad} | arr {ba} -> {aa}{mark}")
            except Exception as exc:                      # noqa: BLE001
                errors += 1
                print(f"ERROR    {mid}  {type(exc).__name__}")
            finally:
                E._roll_overnight_connections = _real_roll

    print("=" * 60)
    print(f"checked={checked} affected={affected} errors={errors} window={window}")


def extractors_portals():
    return E.PORTALS


if __name__ == "__main__":
    run()
