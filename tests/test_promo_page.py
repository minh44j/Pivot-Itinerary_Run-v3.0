"""The promo page: the personal coupon code, when the page is (not) printed, and the page's content."""
import promo_page as P
import generate_itinerary_v3 as G
import email_templates as T


def test_code_format_and_alphabet():
    for pnr in ("AJS6F4", "9YP3RJ", "K76PFY", "HCVWUW", "TK1Q7B"):
        c = P.coupon_code([pnr], "secret")
        assert P.CODE_RE.match(c), c
        assert not set(c) & set("ILO01")          # nothing that can be misread


def test_same_booking_same_code_different_secret_different_code():
    assert P.coupon_code(["AJS6F4"], "s1") == P.coupon_code(["ajs6f4"], "s1")
    assert P.coupon_code(["AJS6F4"], "s1") != P.coupon_code(["AJS6F4"], "s2")
    assert P.coupon_code(["AJS6F4"], "s1") != P.coupon_code(["AJS6F5"], "s1")


def test_split_carrier_code_does_not_depend_on_order():
    assert P.coupon_code(["B9PS6D", "8XMVR7"], "s") == P.coupon_code(["8XMVR7", "b9ps6d"], "s")


def test_no_secret_or_no_reference_means_no_code():
    assert P.coupon_code(["AJS6F4"], "") == ""
    assert P.coupon_code(["AJS6F4"], None) == ""
    assert P.coupon_code([], "s") == "" and P.coupon_code(["", None], "s") == ""


def test_codes_are_well_spread():
    codes = {P.coupon_code([f"PN{n:04d}"], "s") for n in range(3000)}
    assert len(codes) > 2990                       # a clash across 3000 bookings would be very unlucky


def test_only_normal_confirmations_get_a_page():
    assert P.promo_eligible({"doc_status": "confirmed"}, "s")
    assert P.promo_eligible({}, "s")
    assert not P.promo_eligible({}, "")
    for st in ("rescheduled", "delayed", "rebooked", "revised"):
        assert not P.promo_eligible({"doc_status": st}, "s")


def test_terms_carry_every_condition_the_owner_asked_for():
    t = P.TERMS
    assert t.startswith("*Terms and conditions apply")
    assert "5% discount" in t and "more than SAR 1,000" in t and "maximum discount of SAR 200" in t
    assert "low-cost carrier flight tickets" in t
    assert "without prior notice" in t and "reserves the right" in t and "90 days" in t


def test_page_html_has_the_code_the_asterisk_and_live_contacts():
    h = P.promo_html("HDUR738HE", "", "", "", "+966 11 220 0296", "info@pivottmc.com", "www.pivottmc.com")
    assert "HDUR738HE" in h and "5% OFF*" in h
    assert "+966 11 220 0296" in h and "info@pivottmc.com" in h and P.COMPANY_WHATSAPP in h and P.PROMO_ADDRESS in h
    assert "font-weight:400;letter-spacing:-1.8px" in h          # headline is regular weight (owner's call)
    assert P.TERMS in h


def test_the_background_asset_ships():
    assert len(P.background_b64()) > 100000


def test_slot_is_in_the_main_render_only_when_asked():
    d = {"pnr": "ABC123", "passengers": [{"name": "Mr. A B", "ticket_no": "1"}], "flights": [], "segments": []}
    assert G._PROMO_MARK not in G.build_html(dict(d))
    assert G._PROMO_MARK in G.build_html(dict(d), promo_slot=True)


def test_email_tells_staff_which_code_was_printed():
    pts = T.attention_points({"promo_code": "HDUR738HE", "passengers": [], "booked_on": "x"})
    assert any("HDUR738HE" in p for p in pts)
    assert not any("coupon" in p.lower() for p in T.attention_points({"passengers": [], "booked_on": "x"}))
