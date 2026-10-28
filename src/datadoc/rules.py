"""Deterministic data-quality rules. Each finding carries a plain-language German explanation."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

import pandas as pd

from .pii import Masker, PiiInfo, shape
from .profile import fmt_number, numbers_of, parse_date, quartiles

SEVERITY_ORDER = {"hoch": 0, "mittel": 1, "niedrig": 2}

GENERIC_NAME_RE = re.compile(r"^(X|Y|Z|COL|SPALTE|FELD|FIELD|VAR|UNNAMED|TEMP|TMP|DUMMY)?[_ :-]?\d*$", re.I)
# Small vocabulary of typical German ERP abbreviations. A heuristic, not language understanding.
KNOWN_ABBREVIATIONS = {
    "AUF": "Auftrag", "NR": "Nummer", "KD": "Kunde", "KUND": "Kunde", "TEL": "Telefon", "DAT": "Datum",
    "ERF": "Erfassung", "BETR": "Betrag", "MAT": "Material", "KAT": "Kategorie", "BEM": "Bemerkung",
    "ANZ": "Anzahl", "PLZ": "Postleitzahl", "STR": "Straße", "ART": "Art", "TYP": "Typ", "ID": "Kennung",
    "ORT": "Ort", "MWST": "Mehrwertsteuer", "UST": "Umsatzsteuer", "RG": "Rechnung", "EINH": "Einheit",
    "BEZ": "Bezeichnung", "KST": "Kostenstelle", "MA": "Mitarbeiter", "GEB": "Geburt", "POS": "Position",
    "LFD": "laufend", "STK": "Stück", "VON": "von", "BIS": "bis", "NEU": "neu", "ALT": "alt",
    "NAME": "Name", "MAIL": "E-Mail", "ZEIT": "Zeit",
}
AMBIGUOUS_ABBREVIATIONS = {
    "STAT": ["Status", "Statistik"],
    "STD": ["Stunden", "Standard", "Standardabweichung"],
    "KZ": ["Kennzeichen", "Kennziffer"],
    "LIEF": ["Lieferung", "Lieferant"],
    "BEST": ["Bestellung", "Bestand", "Bestätigung"],
    "ABS": ["Absender", "Abschluss", "absolut"],
    "ABT": ["Abteilung", "Abtretung"],
}
# Findings that need a domain explanation from the expert before the column can be documented.
FOLLOW_UP_RULES = {
    "fehlende_werte", "konstante_spalte", "doppelte_ids", "gemischte_typen", "ausreisser",
    "unplausible_werte", "uneinheitliche_kategorien", "unklare_spaltennamen",
}
PLACEHOLDER_VALUES ={999.0, 9999.0, 99999.0, -1.0, -99.0, -999.0}
INJECTION_RE = re.compile(
    r"(ignorier\w*|vergiss)\s+(alle\s+)?(bisherigen\s+|vorherigen\s+|obigen\s+)?(anweisungen|instruktionen|regeln)"
    r"|ignore\s+(all\s+)?(previous|prior|above)\s+instructions|system\s*prompt|du bist (jetzt|ab sofort)|you are now",
    re.I,
)


@dataclass
class Column:
    name: str
    values: list[str | None]
    type: str
    pii: PiiInfo

    @property
    def present(self) -> list[str]:
        return [v for v in self.values if v is not None]


def finding(rule: str, column: str | None, severity: str, title: str, text: str, count: int, examples=None) -> dict:
    return {
        "regel": rule, "spalte": column, "schwere": severity, "titel": title,
        "erklaerung": text, "anzahl": count, "beispiele": list(examples or [])[:5],
    }


def name_tokens(column: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-zÄÖÜäöüß]+", column.upper()) if t]


def name_meaning(column: str) -> str | None:
    """Possible reading of an abbreviated column name, or None."""
    parts = []
    for token in name_tokens(column):
        if token in KNOWN_ABBREVIATIONS:
            parts.append(KNOWN_ABBREVIATIONS[token])
        elif token in AMBIGUOUS_ABBREVIATIONS:
            parts.append(" oder ".join(AMBIGUOUS_ABBREVIATIONS[token]))
        else:
            return None
    if not parts:
        return None
    return f"Der Spaltenname könnte bedeuten: {' + '.join(parts)} (nur eine Vermutung, bitte bestätigen lassen)."


def _quote(value: str) -> str:
    return f"„{value}“"


def _norm_category(value: str) -> str:
    text = " ".join(value.split()).casefold()
    for umlaut, plain in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(umlaut, plain)
    return unicodedata.normalize("NFKD", text)


def missing_values(col: Column, total: int) -> list[dict]:
    missing = total - len(col.present)
    if missing == 0 or col.type == "leer":
        return []
    pct = 100 * missing / total
    severity = "hoch" if pct > 20 else "mittel" if pct >= 5 else "niedrig"
    return [finding(
        "fehlende_werte", col.name, severity, "Fehlende Werte",
        f"In {pct:.0f} % der Zeilen ({missing} von {total}) ist '{col.name}' leer. Ist das normal, oder fehlen hier Angaben?",
        missing,
    )]


def constant_column(col: Column, masker: Masker) -> list[dict]:
    if col.type != "konstant":
        return []
    value = masker.value(col.present[0], col.pii, col.type)
    return [finding(
        "konstante_spalte", col.name, "niedrig", "Spalte ohne Information",
        f"'{col.name}' enthält in allen Zeilen denselben Wert ({_quote(value)}). Sie trägt keine Information. Wird sie noch gebraucht?",
        len(col.present), [value],
    )]


def duplicate_rows(df: pd.DataFrame) -> list[dict]:
    count = int(df.duplicated(keep="first").sum())
    if not count:
        return []
    return [finding(
        "doppelte_zeilen", None, "mittel", "Doppelte Zeilen",
        f"{count} Zeilen kommen exakt doppelt vor. Das deutet auf doppelt erfasste Datensätze hin.", count,
    )]


def duplicate_ids(col: Column) -> list[dict]:
    if col.type != "kennung" or col.pii.verdacht:
        return []
    dupes = sorted(v for v, n in Counter(col.present).items() if n > 1)
    if not dupes:
        return []
    return [finding(
        "doppelte_ids", col.name, "hoch", "Doppelte Kennungen",
        f"'{col.name}' sieht aus wie eine eindeutige Nummer, aber {len(dupes)} Werte kommen mehrfach vor "
        f"(z. B. {', '.join(dupes[:3])}). Sind das Doppelerfassungen oder ist das so gewollt?",
        len(dupes), dupes,
    )]


def mixed_types(col: Column) -> list[dict]:
    if col.type != "gemischt":
        return []
    numeric = len(numbers_of(col.present))
    pct = 100 * numeric / len(col.present)
    return [finding(
        "gemischte_typen", col.name, "mittel", "Gemischte Datentypen",
        f"'{col.name}' enthält gemischt Zahlen ({pct:.0f} %) und Text. Eine Spalte sollte nur eine Art von Werten enthalten.",
        numeric,
    )]


def _fences(numbers: list[float]) -> tuple[float, float] | None:
    if len(numbers) < 8 or len(set(numbers)) <= 10:
        return None
    q1, q3 = quartiles(numbers)
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr) if iqr > 0 else None


def outliers(col: Column) -> list[dict]:
    if col.type != "zahl":
        return []
    numbers = numbers_of(col.present)
    fences = _fences(numbers)
    if not fences:
        return []
    found = sorted({n for n in numbers if n < fences[0] or n > fences[1]})
    if not found:
        return []
    count = sum(1 for n in numbers if n < fences[0] or n > fences[1])
    q1, q3 = quartiles(numbers)
    examples = [fmt_number(n) for n in found]
    return [finding(
        "ausreisser", col.name, "mittel", "Ausreißer",
        f"{count} Werte in '{col.name}' liegen weit außerhalb des üblichen Bereichs (die mittlere Hälfte liegt zwischen "
        f"{fmt_number(round(q1, 2))} und {fmt_number(round(q3, 2))}), z. B. {', '.join(examples[:3])}. "
        "Sind das Tippfehler oder echte Sonderfälle?",
        count, examples,
    )]


def implausible_values(col: Column) -> list[dict]:
    if col.type != "zahl":
        return []
    numbers = numbers_of(col.present)
    reasons, examples, count = [], [], 0
    negatives = [n for n in numbers if n < 0]
    if negatives and len(negatives) / len(numbers) <= 0.05:
        count += len(negatives)
        examples += [fmt_number(n) for n in sorted(negatives)]
        reasons.append(
            f"{len(negatives)} negative Werte, obwohl fast alle anderen Werte positiv sind "
            "(z. B. Gutschriften, Stornos oder Fehler?)"
        )
    fences = _fences(numbers)
    if fences:
        placeholders = Counter(n for n in numbers if n in PLACEHOLDER_VALUES and (n < fences[0] or n > fences[1]))
        for value, n in placeholders.items():
            count += n
            examples.append(fmt_number(value))
            reasons.append(f"der Wert {fmt_number(value)} ({n}×) steht oft als Platzhalter für „unbekannt“")
    if not reasons:
        return []
    return [finding(
        "unplausible_werte", col.name, "mittel", "Unplausible Werte",
        f"In '{col.name}' fallen auf: {'; '.join(reasons)}.", count, examples,
    )]


def inconsistent_categories(col: Column) -> list[dict]:
    if col.type != "kategorie" or col.pii.verdacht:
        return []
    counts = Counter(col.present)
    groups: dict[str, list[str]] = defaultdict(list)
    for value in counts:
        groups[_norm_category(value)].append(value)
    variants = [sorted(g, key=lambda v: -counts[v]) for g in groups.values() if len(g) > 1]
    long_values = [v for v in counts if len(v.strip()) > 4]
    short_forms = [
        v for v in counts
        if v.strip().isupper() and len(v.strip()) <= 3 and len(long_values) >= len(counts) / 2
    ]
    if not variants and not short_forms:
        return []
    parts = [" / ".join(f"{_quote(v)} ({counts[v]}×)" for v in group) for group in variants]
    parts += [f"{_quote(v)} ({counts[v]}×) ist vermutlich eine Abkürzung" for v in short_forms]
    affected = sum(counts[v] for group in variants for v in group[1:]) + sum(counts[v] for v in short_forms)
    return [finding(
        "uneinheitliche_kategorien", col.name, "mittel", "Uneinheitliche Schreibweisen",
        f"'{col.name}' schreibt gleiche Werte unterschiedlich: {'; '.join(parts)}. Für Auswertungen sollten sie einheitlich sein.",
        affected, parts,
    )]


def mixed_date_formats(col: Column) -> list[dict]:
    if col.type != "datum":
        return []
    formats = Counter(p[0] for p in (parse_date(v) for v in col.present) if p)
    if len(formats) < 2:
        return []
    listing = ", ".join(f"{f} ({n}×)" for f, n in formats.most_common())
    return [finding(
        "gemischte_datumsformate", col.name, "mittel", "Gemischte Datumsformate",
        f"'{col.name}' enthält Datumswerte in {len(formats)} Formaten: {listing}. "
        "Das führt leicht zu Verwechslungen von Tag und Monat.",
        sum(formats.values()) - formats.most_common(1)[0][1], list(formats),
    )]


def inconsistent_formats(col: Column) -> list[dict]:
    if col.type not in ("text", "kennung") or not col.present:
        return []
    digits = sum(c.isdigit() for v in col.present for c in v)
    if digits / max(1, sum(len(v) for v in col.present)) < 0.5:
        return []
    collapsed = Counter(re.sub(r"9+", "9", shape(v)) for v in col.present)
    frequent = [s for s, n in collapsed.items() if n / len(col.present) >= 0.02]
    if len(frequent) < 2:
        return []
    examples = []
    for pattern in frequent:
        sample = next(v for v in col.present if re.sub(r"9+", "9", shape(v)) == pattern)
        examples.append(shape(sample))
    return [finding(
        "uneinheitliche_formate", col.name, "niedrig", "Uneinheitliche Formate",
        f"'{col.name}' ist uneinheitlich formatiert: {len(frequent)} verschiedene Schreibweisen, z. B. "
        f"{', '.join(_quote(e) for e in examples[:4])} (Ziffern durch 9 ersetzt).",
        len(frequent), examples,
    )]


def unclear_column_name(col: Column) -> list[dict]:
    if GENERIC_NAME_RE.fullmatch(col.name.strip()) or len(col.name.strip()) <= 1:
        return [finding(
            "unklare_spaltennamen", col.name, "niedrig", "Unklarer Spaltenname",
            f"Der Name '{col.name}' sagt nichts über den Inhalt aus.", 1,
        )]
    notes = []
    for token in name_tokens(col.name):
        if token in AMBIGUOUS_ABBREVIATIONS:
            meanings = ", ".join(AMBIGUOUS_ABBREVIATIONS[token])
            notes.append(f"Die Abkürzung '{token}' ist mehrdeutig (z. B. {meanings})")
        elif token not in KNOWN_ABBREVIATIONS and len(token) <= 4:
            notes.append(f"Die Abkürzung '{token}' ist nicht selbsterklärend")
    if not notes:
        return []
    return [finding(
        "unklare_spaltennamen", col.name, "niedrig", "Unklarer Spaltenname",
        f"{'; '.join(notes)}. Die Bedeutung sollte eine Fachperson bestätigen.", len(notes),
    )]


def pii_suspicion(col: Column) -> list[dict]:
    if not col.pii.verdacht:
        return []
    special = col.pii.stufe == "besondere_kategorie"
    return [finding(
        "pii_verdacht", col.name, "hoch" if special else "mittel", "Personenbezogene Daten",
        f"'{col.name}' enthält vermutlich personenbezogene Daten ({'; '.join(col.pii.gruende)}). "
        "Der Assistent sieht diese Werte nur maskiert.",
        col.pii.treffer or len(col.present),
    )]


def instruction_text(col: Column, masker: Masker) -> list[dict]:
    if col.type not in ("freitext", "text", "gemischt"):
        return []
    hits = [v for v in col.present if INJECTION_RE.search(v)]
    if not hits:
        return []
    return [finding(
        "anweisungsaehnlicher_text", col.name, "hoch", "Anweisungsähnlicher Text",
        f"{len(hits)} Zelle(n) in '{col.name}' enthalten Text, der wie eine Anweisung an eine KI aussieht. "
        "Zellinhalte sind nur Daten: Der Assistent befolgt solche Anweisungen nicht.",
        len(hits), [masker.free_text(v) for v in hits],
    )]


def traffic_light(findings: list[dict]) -> str:
    severities = {f["schwere"] for f in findings}
    return "rot" if "hoch" in severities else "gelb" if severities else "grün"


def follow_up(findings: list[dict], profile: dict) -> dict:
    """Deterministic hint whether the assistant should ask the expert about this column, and why."""
    reasons = ["Die Werte sind Codes"] if profile.get("kodiert") else []
    reasons += [f["titel"] for f in findings if f["regel"] in FOLLOW_UP_RULES]
    reasons = list(dict.fromkeys(reasons))
    return {"empfohlen": bool(reasons), "gruende": reasons}


def run_all(df: pd.DataFrame, columns: list[Column], masker: Masker) -> list[dict]:
    total = len(df)
    findings = duplicate_rows(df)
    for col in columns:
        findings += missing_values(col, total)
        findings += constant_column(col, masker)
        findings += duplicate_ids(col)
        findings += mixed_types(col)
        findings += outliers(col)
        findings += implausible_values(col)
        findings += inconsistent_categories(col)
        findings += mixed_date_formats(col)
        findings += inconsistent_formats(col)
        findings += unclear_column_name(col)
        findings += pii_suspicion(col)
        findings += instruction_text(col, masker)
    findings.sort(key=lambda f: SEVERITY_ORDER[f["schwere"]])
    for number, item in enumerate(findings, start=1):
        item["nr"] = number
    return findings
