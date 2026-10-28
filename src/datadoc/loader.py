"""Load CSV and Excel files as all-string tables with automatic encoding and delimiter detection."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
import pandas as pd

MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 200_000
SAMPLE_SEED = 42
DELIMITERS = (";", ",", "\t", "|")
ENCODINGS = ("utf-8-sig", "cp1252")
NA_TOKENS = {"", "na", "n/a", "null", "none", "nan", "k.a.", "k. a."}


class LoadError(ValueError):
    """The file cannot be loaded."""


@dataclass
class Table:
    df: pd.DataFrame  # every cell is a str or None (missing)
    meta: dict = field(default_factory=dict)


def _detect_delimiter(text: str) -> str:
    lines = [line for line in text.splitlines()[:50] if line.strip()]
    if not lines:
        raise LoadError("Die Datei ist leer.")

    def score(delim: str) -> tuple[float, int]:
        header = lines[0].count(delim)
        if header == 0:
            return (0.0, 0)
        consistent = sum(1 for line in lines if line.count(delim) == header) / len(lines)
        return (consistent, header)

    best = max(DELIMITERS, key=score)
    return best if score(best)[1] > 0 else ","


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise LoadError("Die Zeichenkodierung der Datei wurde nicht erkannt.")


def _normalize_cell(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value)
    return None if text.strip().casefold() in NA_TOKENS else text


def load(path: Path, sheet: str | None = None) -> Table:
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise LoadError(f"Die Datei ist {size / 1e6:.0f} MB groß. Erlaubt sind höchstens {MAX_BYTES // 1024 // 1024} MB.")

    meta: dict = {"datei": path.name, "groesse_bytes": size, "hinweise": []}
    if path.suffix.lower() == ".csv":
        text, encoding = _decode(path.read_bytes())
        delimiter = _detect_delimiter(text)
        df = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False, na_filter=False)
        meta |= {"format": "csv", "kodierung": encoding, "trennzeichen": delimiter}
    else:
        workbook = openpyxl.load_workbook(path, read_only=True)
        sheets = workbook.sheetnames
        workbook.close()
        if sheet and sheet not in sheets:
            raise LoadError(f"Das Tabellenblatt '{sheet}' gibt es nicht. Vorhanden: {', '.join(sheets)}.")
        chosen = sheet or sheets[0]
        df = pd.read_excel(path, sheet_name=chosen, dtype=str, engine="openpyxl", keep_default_na=False, na_filter=False)
        meta |= {"format": "xlsx", "tabellenblatt": chosen, "tabellenblaetter": sheets}
        if len(sheets) > 1 and not sheet:
            meta["hinweise"].append(f"Die Datei hat {len(sheets)} Tabellenblätter; analysiert wurde '{chosen}'.")

    df.columns = [str(c).strip() for c in df.columns]
    # pandas infers a string dtype after map() and turns None into NaN again; force object + None.
    df = df.astype(object).map(_normalize_cell).astype(object)
    df = df.where(df.notna(), None)
    meta["zeilen_gesamt"] = len(df)
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=SAMPLE_SEED).sort_index()
        meta["hinweise"].append(
            f"Die Datei hat {meta['zeilen_gesamt']} Zeilen. Analysiert wurde eine Zufallsstichprobe von {MAX_ROWS} Zeilen."
        )
    meta["stichprobe"] = len(df) < meta["zeilen_gesamt"]
    meta["zeilen_analysiert"] = len(df)
    return Table(df=df.reset_index(drop=True), meta=meta)
