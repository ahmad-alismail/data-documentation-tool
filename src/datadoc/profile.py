"""Column typing and masked column profiles."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import date, datetime

from .pii import Masker, PiiInfo, shape

ID_NAME_RE = re.compile(r"(^|_)(ID|NR|NUMMER|NO|KEY|SCHLUESSEL|SCHLÜSSEL)($|_)", re.I)
TOP_VALUES = 10
# Categories list every value so the proposed Wertebereich can be complete; matches the limit in classify().
CATEGORY_VALUES = 50

_DATE_FORMATS = [
    ("JJJJ-MM-TT", re.compile(r"\d{4}-\d{2}-\d{2}"), "%Y-%m-%d"),
    ("TT.MM.JJJJ", re.compile(r"\d{1,2}\.\d{1,2}\.\d{4}"), "%d.%m.%Y"),
    ("TT.MM.JJ", re.compile(r"\d{1,2}\.\d{1,2}\.\d{2}"), "%d.%m.%y"),
    ("MM/TT/JJJJ", re.compile(r"\d{1,2}/\d{1,2}/\d{4}"), "%m/%d/%Y"),
    ("JJJJ-MM-TT hh:mm", re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?"), "%Y-%m-%d"),
    ("TT.MM.JJJJ hh:mm", re.compile(r"\d{1,2}\.\d{1,2}\.\d{4} \d{1,2}:\d{2}(:\d{2})?"), "%d.%m.%Y"),
]
_NUMBER_FORMATS = [
    (re.compile(r"[+-]?\d+"), lambda t: t),
    (re.compile(r"[+-]?\d+\.\d+"), lambda t: t),
    (re.compile(r"[+-]?\d+,\d+"), lambda t: t.replace(",", ".")),
    (re.compile(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?"), lambda t: t.replace(".", "").replace(",", ".")),
    (re.compile(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?"), lambda t: t.replace(",", "")),
]


def parse_number(value: str) -> float | None:
    text = value.strip()
    for pattern, normalize in _NUMBER_FORMATS:
        if pattern.fullmatch(text):
            return float(normalize(text))
    return None


def parse_date(value: str) -> tuple[str, date] | None:
    text = value.strip()
    for label, pattern, fmt in _DATE_FORMATS:
        if pattern.fullmatch(text):
            try:
                return label, datetime.strptime(text.split(" ")[0].split("T")[0], fmt).date()
            except ValueError:
                return None
    return None


def _share(values: list[str], predicate) -> float:
    return sum(1 for v in values if predicate(v) is not None) / len(values)


def classify(column: str, values: list[str]) -> str:
    """Detected data type: leer, konstant, zahl, datum, kennung, gemischt, freitext, kategorie or text."""
    if not values:
        return "leer"
    unique = len(set(values))
    if unique == 1:
        return "konstant"
    number_share = _share(values, parse_number)
    date_share = _share(values, parse_date)
    if number_share >= 0.95:
        numbers = [parse_number(v) for v in values if parse_number(v) is not None]
        if unique <= 12 and all(n.is_integer() for n in numbers):
            return "kategorie"
        return "zahl"
    if date_share >= 0.95:
        return "datum"
    if unique / len(values) >= 0.9 and (ID_NAME_RE.search(column) or len({shape(v) for v in values}) <= 3):
        return "kennung"
    if number_share >= 0.05 or date_share >= 0.05:
        return "gemischt"
    if statistics.median(len(v.split()) for v in values) >= 3:
        return "freitext"
    if unique <= CATEGORY_VALUES or unique / len(values) <= 0.1:
        return "kategorie"
    return "text"


def numbers_of(values: list[str]) -> list[float]:
    return [n for n in (parse_number(v) for v in values) if n is not None]


def quartiles(numbers: list[float]) -> tuple[float, float]:
    q = statistics.quantiles(numbers, n=4, method="inclusive")
    return q[0], q[2]


def fmt_number(value: float) -> str:
    """German notation without thousands separator, e.g. ``1253,3``."""
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _spread(values: list[str], k: int) -> list[str]:
    distinct = list(dict.fromkeys(values))
    if len(distinct) <= k:
        return distinct
    step = len(distinct) / k
    return [distinct[int(i * step)] for i in range(k)]


def build(column: str, values: list[str | None], col_type: str, info: PiiInfo, masker: Masker, hint: str | None) -> dict:
    present = [v for v in values if v is not None]
    total = len(values)
    missing = total - len(present)
    profile: dict = {
        "spalte": column,
        "erkannter_typ": col_type,
        "werte_gesamt": total,
        "fehlend": missing,
        "fehlend_prozent": round(100 * missing / total, 1) if total else 0.0,
        "eindeutig": len(set(present)),
    }
    if info.verdacht:
        profile["personenbezug"] = {"stufe": info.stufe, "gruende": info.gruende, "maskiert": True}

    masked_counts = Counter(masker.value(v, info, col_type) for v in present)
    if info.kind in ("telefon", "iban"):
        shapes = Counter(shape(v) for v in present)
        profile["formatmuster"] = [{"muster": s, "anzahl": n} for s, n in shapes.most_common(6)]
        profile["beispiele"] = [masker.value(present[0], info, col_type)] if present else []
    elif info.kind in ("name", "email", "adresse", "sonstiges"):
        profile["beispiele"] = [masker.value(present[0], info, col_type)] if present else []
    else:
        limit = CATEGORY_VALUES if col_type == "kategorie" else TOP_VALUES
        profile["haeufigste_werte"] = [{"wert": v, "anzahl": n} for v, n in masked_counts.most_common(limit)]
        if len(masked_counts) > limit:
            profile["weitere_werte"] = len(masked_counts) - limit
        profile["beispiele"] = _spread([masker.value(v, info, col_type) for v in present], 5)

    numbers = numbers_of(present) if col_type in ("zahl", "kategorie", "konstant") else []
    if col_type == "zahl" and len(numbers) >= 4:
        q1, q3 = quartiles(numbers)
        profile["zahlen"] = {
            "min": fmt_number(min(numbers)), "max": fmt_number(max(numbers)),
            "mittelwert": fmt_number(round(statistics.fmean(numbers), 2)),
            "median": fmt_number(statistics.median(numbers)),
            "q1": fmt_number(round(q1, 2)), "q3": fmt_number(round(q3, 2)),
            "dezimaltrennzeichen": "Komma" if any("," in v for v in present) else "Punkt",
        }
    if col_type == "datum":
        parsed = [p for p in (parse_date(v) for v in present) if p]
        formats = Counter(label for label, _ in parsed)
        days = [d for _, d in parsed]
        profile["datum"] = {
            "von": min(days).isoformat(), "bis": max(days).isoformat(),
            "formate": [{"format": f, "anzahl": n} for f, n in formats.most_common()],
        }
    if col_type in ("text", "freitext", "kennung") and present:
        lengths = [len(v) for v in present]
        profile["textlaenge"] = {"min": min(lengths), "max": max(lengths), "median": statistics.median(lengths)}

    hints = []
    if col_type == "kategorie" and numbers:
        profile["kodiert"] = True
        codes = [fmt_number(n) for n in sorted(set(numbers))]
        hints.append(f"Die Werte sehen nach Codes aus ({', '.join(codes)}). Ihre Bedeutung sollte erfragt werden.")
    if hint:
        hints.append(hint)
    if hints:
        profile["hinweise"] = hints
    return profile
