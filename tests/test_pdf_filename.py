"""The PDF is named '<PNR> - <Passenger Name>.pdf' (2026-11-18) so it is recognisable in an inbox or Drive."""
import generate_itinerary_v3 as G


def _b(pnr="K76PFY", names=("Mr. MUSTAFA ERGUN",), **kw):
    d = {"pnr": pnr, "passengers": [{"name": n} for n in names], "flights": []}
    d.update(kw)
    return d


def test_single_passenger_title_dropped_and_title_cased():
    assert G.pdf_stem(_b()) == "K76PFY - Mustafa Ergun"


def test_more_passengers_add_a_count():
    assert G.pdf_stem(_b(names=("Mr. A Kale", "Mrs. B Kale", "Miss C Kale"))) == "K76PFY - A Kale +2"


def test_missing_name_keeps_the_old_name():
    assert G.pdf_stem(_b(names=("Not specified",))) == "K76PFY"
    assert G.pdf_stem(_b(names=())) == "K76PFY"
    assert G.pdf_stem(_b(names=("",))) == "K76PFY"


def test_unsafe_characters_are_removed():
    s = G.pdf_stem(_b(names=("Mr. O'NEIL / JOSE: <X>",)))
    assert "/" not in s and ":" not in s and "<" not in s and s.startswith("K76PFY - O'neil Jose")


def test_turkish_letters_survive():
    assert G.pdf_stem(_b(names=("Mr. Şükrü Güllü",))).endswith("Şükrü Güllü")


def test_split_carrier_keeps_every_reference():
    d = _b(pnr="B9PS6D", pnrs=["B9PS6D", "8XMVR7"])
    assert G.pdf_stem(d) == "B9PS6D-8XMVR7 - Mustafa Ergun"
