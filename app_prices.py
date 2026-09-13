"""Verifierade Qopla-priser till kundappen. Inte till röst-AI:n.

Källa: https://qopla.com/v2/restaurant/gislegrillen/qp9Y28NmNM/order/menu?eating=TAKE_AWAY
läst 2026-09-13. Familj = 2 × standard + 60, kontrollerat på Capricciosa 130→320,
Bahamas 140→340 och Ibbe-Special 160→380.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# Standardpris per meny-id (samma id som menu.json).
DISH_STANDARD: Dict[int, int] = {
    # Pizza 01–12
    1: 130, 2: 130, 3: 130, 4: 130, 5: 130, 6: 130, 7: 130, 8: 130, 9: 130,
    10: 130, 11: 130, 12: 130,
    # Pizza 13–21
    13: 140, 14: 140, 15: 140, 16: 140, 17: 140, 18: 140, 19: 140, 20: 140, 21: 140,
    # Pizza 22–39
    22: 145, 23: 145, 24: 145, 25: 145, 26: 145, 27: 145, 28: 145, 29: 145,
    30: 145, 31: 145, 32: 145, 33: 145, 34: 145, 35: 145, 36: 145, 37: 145,
    38: 145, 39: 145,
    # Pizza 40–48
    40: 150, 41: 150, 42: 150, 43: 150, 44: 150, 45: 150, 46: 150, 47: 150, 48: 150,
    # Pizza 49–52
    49: 160, 50: 160, 51: 160, 52: 160,
    # Kebab / kyckling
    53: 140, 54: 140, 55: 140, 56: 140, 57: 155,
    58: 145, 59: 145, 60: 145,
    # Sallad (inte Grekisk – saknas på Qopla)
    61: 140, 63: 140, 64: 140, 65: 140, 66: 140,
    # Övrigt / LCHF / schnitzel
    67: 120, 68: 105, 69: 140, 70: 110, 72: 145, 73: 140, 74: 90, 75: 120,
    # Hamburgare
    77: 70, 78: 100, 79: 80, 80: 110, 81: 90, 82: 120,
    # Korv som finns på Qopla
    83: 25, 84: 60, 85: 60, 89: 35, 90: 70, 91: 70,
    # Dryck / extra sås
    101: 10, 103: 20, 104: 30, 105: 40,
}

PIZZA_IDS = set(range(1, 53))

# Visningsnamn som på Qopla. menu.json behåller röstalias.
DISPLAY_NAMES: Dict[int, str] = {
    49: "Ibbe-Special",
    50: "Alex-Special",
    61: "Hawaii sallad",
    67: "Köttbullar med mos och lingon",
    69: "Lövbit m. Strips",
    70: "Chicken Nuggets, med strips",
    72: "LCHF-Pizza",
    73: "Wärdhusschnitzel",
    78: "90g, med strips",
    80: "150g, med strips",
    82: "200g, med strips",
    83: "Grillkorv i bröd",
    84: "Grillkorv med strips/ mos",
    85: "Grillkorv med strips/ mos",
    89: "Bamse i bröd",
    90: "Bamse med strips/mos",
    91: "Bamse med strips/mos",
    105: "2liter",
}

# Påslag/avdrag, nyckel i gemener. Specifika extra-rader före korta alias.
OPTION_DELTA: Dict[str, int] = {
    "glutenfri botten": 30,
    "glutenfri": 30,
    "nötkebab": 10,
    "notkebab": 10,
    "barnportion": -10,
    "kebabsås direkt på pizzan": 5,
    "kebabsas direkt pa pizzan": 5,
    "kebabsås på pizzan": 5,
    "kebabsas pa pizzan": 5,
    "extra ost": 15,
    "extra skinka": 15,
    "extra kebab": 30,
    "extra köttfärs": 20,
    "extra kottfars": 20,
    "extra fläskfilé": 30,
    "extra flaskfile": 30,
    "extra oxfilé": 30,
    "extra oxfile": 30,
    "extra kyckling": 30,
    "extra salami": 20,
    "extra tonfisk": 20,
    "extra räkor": 20,
    "extra rakor": 20,
    "extra jalapeño": 10,
    "extra jalapeno": 10,
    "extra fetaost": 15,
    "extra bacon": 15,
    "extra champinjoner": 10,
    "extra pommes": 20,
    "extra lök": 5,
    "extra lok": 5,
    "extra ananas": 10,
    "extra rå rödlök": 5,
    "extra ra rodlok": 5,
    "extra rödlök": 5,
    "pommes": 15,
}

# Qopla-etiketter för publicerad meny (röstmenyn kan ha kortare namn).
OPTION_DISPLAY: Dict[str, str] = {
    "kebabsås på pizzan": "Kebabsås direkt på pizzan",
    "extra ost": "Extra Ost",
    "extra skinka": "Extra Skinka",
    "extra kebab": "Extra kebab",
    "extra köttfärs": "Extra köttfärs",
    "extra fläskfilé": "Extra Fläskfilé",
    "extra oxfilé": "Extra oxfilé",
    "extra kyckling": "Extra Kyckling",
    "extra salami": "Extra salami",
    "extra tonfisk": "Extra Tonfisk",
    "extra räkor": "Extra räkor",
    "extra jalapeño": "Extra jalapeño",
    "extra fetaost": "Extra Fetaost",
    "extra bacon": "Extra bacon",
    "extra champinjoner": "Extra champinjoner",
    "extra pommes": "Extra pommes",
    "extra lök": "Extra Lök",
    "extra ananas": "Extra ananas",
    "extra rödlök": "Extra rå rödlök",
    "mild": "Mild sås",
    "stark": "Stark sås",
}

_SIZE_LABELS = {"standard", "vanlig", "familj", "family", "vanligt bröd", "vanligt bröd!"}


def _fold(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def family_price(standard: int) -> int:
    return 2 * int(standard) + 60


def display_name(item_id: Any, fallback: str) -> str:
    parsed = _as_int(item_id)
    if parsed is None:
        return fallback
    return DISPLAY_NAMES.get(parsed, fallback)


def dish_prices(item_id: Any, menu: Optional[dict] = None) -> Optional[Dict[str, int]]:
    """Standardpris och ev. familjepris från meny-override eller inbyggd Qopla-lista."""
    parsed = _as_int(item_id)
    if parsed is None:
        return None
    override = _override_dish(menu, parsed)
    if override:
        return override
    standard = DISH_STANDARD.get(parsed)
    if standard is None:
        return None
    out = {"price": int(standard)}
    if parsed in PIZZA_IDS:
        out["family"] = family_price(standard)
    return out


def option_display_label(label: str) -> str:
    mapped = OPTION_DISPLAY.get(_fold(label))
    return mapped or label


def option_delta(label: str, menu: Optional[dict] = None) -> int:
    key = _fold(label)
    extra = ((menu or {}).get("_meta") or {}).get("app_prices") if isinstance(menu, dict) else None
    if isinstance(extra, dict):
        raw = extra.get("option_delta") or {}
        if isinstance(raw, dict):
            for name, amount in raw.items():
                if _fold(str(name)) == key:
                    try:
                        return int(amount)
                    except (TypeError, ValueError):
                        break
    if key in OPTION_DELTA:
        return int(OPTION_DELTA[key])
    return 0


def labels_from_notes(notes: Optional[str]) -> List[str]:
    if not notes:
        return []
    return [part.strip() for part in str(notes).split(",") if part.strip()]


def unit_price(item_id: Any, selected: Iterable[str], menu: Optional[dict] = None) -> Optional[float]:
    info = dish_prices(item_id, menu)
    if not info:
        return None
    labels = [str(x).strip() for x in selected if str(x).strip()]
    folded = {_fold(x) for x in labels}
    unit = float(info["family"] if ("familj" in folded or "family" in folded) and info.get("family") else info["price"])
    for label in labels:
        if _fold(label) in _SIZE_LABELS:
            continue
        unit += option_delta(label, menu)
    return unit


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _override_dish(menu: Optional[dict], item_id: int) -> Optional[Dict[str, int]]:
    if not isinstance(menu, dict):
        return None
    extra = (menu.get("_meta") or {}).get("app_prices")
    if not isinstance(extra, dict):
        return None
    dishes = extra.get("dishes") or {}
    if not isinstance(dishes, dict):
        return None
    raw = dishes.get(str(item_id), dishes.get(item_id))
    if not isinstance(raw, dict):
        return None
    try:
        price = int(raw.get("price"))
    except (TypeError, ValueError):
        return None
    out = {"price": price}
    family = raw.get("family")
    if family is not None:
        try:
            out["family"] = int(family)
        except (TypeError, ValueError):
            pass
    elif item_id in PIZZA_IDS:
        out["family"] = family_price(price)
    return out
