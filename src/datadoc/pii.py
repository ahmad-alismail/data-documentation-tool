"""Detection and masking of personal data (PII).

Masking runs before anything leaves the Python core, so neither the model nor the
exports ever see clear values from personal columns or personal data inside free text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PHONE_RE = re.compile(r"(?<![\w+])(?:\+49|0049|0)[ \-/]?\d{2,5}[ \-/]?\d{3,9}(?!\w)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b")
TITLE_NAME_RE = re.compile(r"\b(Herrn?|Frau|Hr\.|Fr\.)\s+(?:Dr\.\s+)?[A-ZÄÖÜ][\wäöüß-]+")
_NAME_PART = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
PERSON_NAME_RE = re.compile(rf"^(?:(?:Dr|Prof)\.\s+)*{_NAME_PART}(?:\s+(?:(?:von|van|de|zu)\s+)?{_NAME_PART}){{1,2}}$")

TOKENS = {
    "name": "[NAME]",
    "telefon": "[TELEFON]",
    "email": "[E-MAIL]",
    "adresse": "[ADRESSE]",
    "iban": "[IBAN]",
    "sonstiges": "[PERSONENBEZOGEN]",
}

# Column-name hints: (kind, keywords). Short keywords must match a whole token.
NAME_HINTS = [
    ("name", {"NAME", "VORNAME", "NACHNAME", "ANSPRECHPARTNER", "PERSON"}),
    ("telefon", {"TEL", "TELEFON", "PHONE", "MOBIL", "HANDY", "FAX"}),
    ("email", {"MAIL", "EMAIL"}),
    ("adresse", {"STRASSE", "ADRESSE", "ANSCHRIFT"}),
    ("iban", {"IBAN", "KONTO", "BIC"}),
    ("sonstiges", {"GEBURT", "GEBDAT", "GEBURTSDATUM", "STEUERID", "SVNR", "PERSONALNR", "AUSWEIS"}),
]
ART9_HINTS = {
    "GESUNDHEIT", "DIAGNOSE", "KRANKHEIT", "BEHINDERUNG", "RELIGION", "KONFESSION", "ETHNIE",
    "GEWERKSCHAFT", "BIOMETRIE", "GENETIK", "SEXUELL", "PARTEI", "WELTANSCHAUUNG",
}
KIND_LABEL = {
    "name": "Namen", "telefon": "Telefonnummern", "email": "E-Mail-Adressen",
    "adresse": "Adressen", "iban": "Bankverbindungen", "sonstiges": "persönliche Angaben",
}


@dataclass
class PiiInfo:
    kind: str | None = None  # see TOKENS, or "freitext" for free text containing PII
    stufe: str = "keine"  # keine | personenbezogen | besondere_kategorie
    gruende: list[str] = field(default_factory=list)
    treffer: int = 0  # free text: rows containing PII

    @property
    def verdacht(self) -> bool:
        return self.stufe != "keine"


def _name_tokens(column: str) -> list[str]:
    spaced = re.sub(r"([a-zäöü])([A-ZÄÖÜ])", r"\1 \2", column)
    return [t for t in re.split(r"[^A-Za-zÄÖÜäöüß]+", spaced.upper()) if t]


def _matches(tokens: list[str], keywords: set[str]) -> bool:
    return any(t in keywords or any(len(k) >= 4 and k in t for k in keywords) for t in tokens)


def _share(values: list[str], predicate) -> float:
    return sum(1 for v in values if predicate(v)) / len(values) if values else 0.0


def contains_pii(text: str) -> bool:
    return bool(PHONE_RE.search(text) or EMAIL_RE.search(text) or IBAN_RE.search(text) or TITLE_NAME_RE.search(text))


def detect(column: str, values: list[str], col_type: str, masker: "Masker | None" = None) -> PiiInfo:
    """Classify a column. Pass the dataset's masker to also count names known from name columns in free text."""
    info = PiiInfo()
    tokens = _name_tokens(column)
    for kind, keywords in NAME_HINTS:
        if _matches(tokens, keywords):
            info.kind = kind
            info.gruende.append(f"Spaltenname deutet auf {KIND_LABEL[kind]} hin")
            break

    if values and col_type not in ("freitext", "zahl", "datum"):
        value_checks = [
            ("telefon", lambda v: bool(PHONE_RE.fullmatch(v.strip())), 0.5),
            ("email", lambda v: bool(EMAIL_RE.fullmatch(v.strip())), 0.5),
            ("iban", lambda v: bool(IBAN_RE.fullmatch(v.strip())), 0.5),
            ("name", lambda v: bool(PERSON_NAME_RE.fullmatch(v.strip())), 0.6),
        ]
        for kind, predicate, threshold in value_checks:
            if _share(values, predicate) >= threshold and (kind != "name" or len(set(values)) >= 10):
                info.kind = info.kind or kind
                info.gruende.append(f"Werte sehen aus wie {KIND_LABEL[kind]}")
                break

    if col_type == "freitext":
        has_pii = (lambda v: masker.free_text(v) != v) if masker else contains_pii
        info.treffer = sum(1 for v in values if has_pii(v))
        if info.treffer:
            info.kind = info.kind or "freitext"
            info.gruende.append(f"{info.treffer} Freitexte enthalten Telefonnummern, E-Mail-Adressen oder Namen")

    if info.kind:
        info.stufe = "personenbezogen"
    if _matches(tokens, ART9_HINTS):
        info.kind = info.kind or "sonstiges"
        info.stufe = "besondere_kategorie"
        info.gruende.append("Spaltenname deutet auf besondere Kategorien nach Art. 9 DSGVO hin")
    return info


class Masker:
    """Masks values of one dataset. Knows the clear names of all name columns."""

    def __init__(self, names: list[str]):
        full, surnames = set(), set()
        for raw in names:
            name = re.sub(r"^(?:(?:Dr|Prof)\.\s+)+", "", raw.strip())
            if not name:
                continue
            full.add(name)
            parts = name.split()
            if len(parts) > 1 and len(parts[-1]) >= 3:
                surnames.add(parts[-1])
        self._full = self._compile(full)
        self._surnames = self._compile(surnames)

    @staticmethod
    def _compile(words: set[str]) -> re.Pattern | None:
        if not words:
            return None
        alternatives = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")

    def free_text(self, text: str) -> str:
        text = scrub(text)
        text = TITLE_NAME_RE.sub(lambda m: f"{m.group(1)} [NAME]", text)
        for pattern in (self._full, self._surnames):
            if pattern:
                text = pattern.sub("[NAME]", text)
        return text

    def value(self, value: str, info: PiiInfo, col_type: str) -> str:
        if info.kind in TOKENS:
            return TOKENS[info.kind]
        if col_type in ("freitext", "text", "gemischt"):
            return self.free_text(value)
        return scrub(value)


def scrub(text: str) -> str:
    """Global safety net: removes phone numbers, e-mail addresses and IBANs from any text."""
    text = EMAIL_RE.sub(TOKENS["email"], text)
    text = IBAN_RE.sub(TOKENS["iban"], text)
    return PHONE_RE.sub(TOKENS["telefon"], text)


def shape(value: str) -> str:
    """Digit-free format pattern, e.g. ``07131/123456`` -> ``99999/999999``."""
    return re.sub(r"\d", "9", value.strip())
