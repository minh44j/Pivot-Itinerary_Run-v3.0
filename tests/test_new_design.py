"""
Offline guards for the 2026-10-30 redesign (light page, Inter only, boarding-pass cards).

Pure stdlib: build_html() imports Playwright only inside build_pdf().
"""
import extractors as E
import generate_itinerary_v3 as G


def _booking(**over):
    pax = {"name": "Mr. Test Passenger", "cabin_bag": "7kg", "checked_bag": "20kg", "seat": "14A"}
    base = dict(portal="Manual", pnr="TEST01", status="Confirmed", booked_on="01 Jan 2026",
                passengers=[{**pax, "ticket_no": "1234567890123"}],
                flights=[{"flight_no": "XX 100", "airline": "Test Air", "dep_iata": "DOH", "arr_iata": "JED",
                          "dep_city": "Doha", "arr_city": "Jeddah", "dep_airport": "", "arr_airport": "",
                          "terminal": "", "arr_terminal": "1", "dep_time": "12:50", "dep_date": "27 Oct 2026",
                          "arr_time": "15:35", "arr_date": "27 Oct 2026", "cabin": "Economy",
                          "duration": "2H 45M", "pax": [dict(pax)]}])
    base.update(over)
    return E._finalize(base)


def test_no_serif_anywhere():
    """Cormorant Garamond is retired: the page is Inter only."""
    html = G.build_html(_booking())
    assert "Cormorant" not in html


def test_font_is_inlined_so_rendering_needs_no_network():
    html = G.build_html(_booking())
    assert "@font-face" in html and "data:font/woff2;base64," in html
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html


def test_latin_ext_is_embedded_for_turkish_names():
    """Passenger names carry ş ğ ı İ ö ü; those live in the latin-ext subset."""
    assert "inter-var-latin-ext.woff2" in {p.name for p in G._FONT_DIR.iterdir()}
    css = G._font_face_css()
    assert css.count("@font-face") == 2
    assert "U+0100" in css                      # latin-ext range present


def test_no_dark_header_or_footer_band():
    html = G.build_html(_booking())
    for gone in ('class="header"', 'class="footer"', "hdr-rail", "footer-abs"):
        assert gone not in html


def test_footer_carries_reference_and_website_but_not_cr_or_vat():
    """Owner's call, 2026-10-30: the footer shows the reference and website only."""
    f = G._footer_template("TEST01")
    assert "TEST01" in f and G.COMPANY_WEBSITE.upper() in f
    assert 'class="pageNumber"' in f and 'class="totalPages"' in f
    assert "CR " not in f and "VAT" not in f
    assert G.COMPANY_CR not in f and G.COMPANY_VAT not in f
    assert G.COMPANY_CR not in G.build_html(_booking()) and G.COMPANY_VAT not in G.build_html(_booking())


def test_seat_is_a_column_on_the_flight_card():
    html = G.build_html(_booking())
    assert "<th>Seat</th>" in html and '<td class="seat">14A</td>' in html


def test_every_document_state_has_a_text_colour_for_a_light_page():
    for k, v in G._DOC_STATE.items():
        assert v.get("ink", "").startswith("#"), k


def test_revised_state_label_and_colour_reach_the_masthead():
    html = G.build_html(_booking(doc_status="rescheduled"))
    assert "Revised Itinerary" in html and "#b45309" in html


def test_gold_text_is_the_accessible_ink_not_the_ornament_gold():
    """#c9a84c is 2.29:1 on white — fine as a line or fill, not as text."""
    css = G._CSS
    assert "--gold-ink:#85660f" in css
    for sel in (".carrier .a b{color:var(--gold-ink)", ".chip{", ".tc .it h3 em{"):
        assert sel in css
