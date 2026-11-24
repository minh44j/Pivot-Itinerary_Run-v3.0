"""Heroicons are embedded and usable offline."""
import re
import pytest
import icons


def test_the_whole_set_ships():
    assert len(icons.names("outline")) == 324 and len(icons.names("solid")) == 324


def test_icons_the_documents_need_exist_in_both_styles():
    for n in ("paper-airplane", "phone", "envelope", "map-pin", "globe-alt", "truck", "identification", "calendar-days",
              "chat-bubble-left-right", "check-circle", "clock", "user", "arrow-right", "document-text", "ticket"):
        assert icons.has(n, "outline") and icons.has(n, "solid"), n


def test_outline_markup():
    s = icons.icon("phone", size=22, color="#1d1d1f")
    assert s.startswith("<svg") and s.endswith("</svg>")
    assert 'viewBox="0 0 24 24"' in s and 'width="22"' in s and 'stroke="#1d1d1f"' in s and 'fill="none"' in s
    assert "<path" in s and "http" not in re.sub(r'xmlns="[^"]+"', "", s)     # no external references


def test_solid_markup_is_filled():
    s = icons.icon("check-circle", style="solid", size=16)
    assert 'fill="currentColor"' in s and "stroke=" not in s


def test_unknown_names_and_styles_fail_loudly():
    with pytest.raises(KeyError):
        icons.icon("not-a-real-icon")
    with pytest.raises(ValueError):
        icons.icon("phone", style="duotone")


def test_licence_notice_travels_with_the_icons():
    import pathlib
    t = (pathlib.Path(__file__).parent.parent / "assets" / "icons" / "HEROICONS_LICENSE.txt").read_text()
    assert "MIT" in t and "Tailwind Labs" in t
