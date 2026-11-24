"""
Heroicons (v2.2.0, MIT, Tailwind Labs) embedded in the system — the icon set for every Pivot document and e-mail.

Pure module (stdlib only). The icons ship in `assets/icons/heroicons.json` (24px grid: 324 "outline" + 324 "solid"), so a
render needs NO network and cannot fall back to something else. Licence text: assets/icons/HEROICONS_LICENSE.txt (MIT requires
that notice to travel with the icons).

    import icons
    icons.icon("paper-airplane")                       # outline, 20px, takes the surrounding text colour
    icons.icon("phone", size=22, color="#1d1d1f")
    icons.icon("check-circle", style="solid", size=16)
    icons.has("truck"); icons.names()                  # browse

Outline icons use a 1.5 stroke (Heroicons' own); `stroke=` overrides it. Unknown names raise KeyError, so a typo is caught by a test,
not discovered on a client's PDF.
"""
import json
import os

_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons", "heroicons.json")
_DATA = None


def _load():
    global _DATA
    if _DATA is None:
        with open(_FILE, encoding="utf-8") as fh:
            _DATA = json.load(fh)
    return _DATA


def names(style: str = "outline"):
    return sorted(_load()[style])


def has(name: str, style: str = "outline") -> bool:
    return name in _load().get(style, {})


def icon(name: str, style: str = "outline", size: int = 20, color: str = "currentColor", stroke: float = 1.5,
         cls: str = "") -> str:
    """Inline <svg> for a Heroicon. `style` is 'outline' or 'solid'."""
    if style not in ("outline", "solid"):
        raise ValueError("style must be 'outline' or 'solid'")
    try:
        inner = _load()[style][name]
    except KeyError:
        raise KeyError(f"no Heroicon named {name!r} in the {style} set") from None
    c = f' class="{cls}"' if cls else ""
    if style == "outline":
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
                f'stroke="{color}" stroke-width="{stroke}" aria-hidden="true"{c}>{inner}</svg>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="{color}" '
            f'aria-hidden="true"{c}>{inner}</svg>')
