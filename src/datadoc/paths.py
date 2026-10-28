"""Path confinement: data is read only from ``daten/``, results are written only to ``ausgabe/``.

Second line of defence behind the Pi extension gate: every name coming from outside
is a bare file or folder name, never a path.
"""

from __future__ import annotations

import re
from pathlib import Path

DATA_DIR = "daten"
OUTPUT_DIR = "ausgabe"
DRAFT_FILE = "entwurf.json"
ALLOWED_SUFFIXES = (".csv", ".xlsx")

_SAFE_NAME = re.compile(r"^\w[\w .()\-]*$")


class PathError(ValueError):
    """A name was rejected or the target does not exist."""


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise PathError("Es wurde kein Name angegeben.")
    if ".." in name or any(c in name for c in "/\\:") or Path(name).is_absolute():
        raise PathError(f"'{name}' ist nicht erlaubt: Nur einfache Dateinamen ohne Pfadangabe sind zulässig.")
    if not _SAFE_NAME.match(name):
        raise PathError(f"'{name}' enthält unzulässige Zeichen.")
    return name


def _confine(base: Path, name: str) -> Path:
    base = base.resolve()
    path = (base / name).resolve()
    if path.parent != base:
        raise PathError(f"'{name}' liegt außerhalb des erlaubten Ordners.")
    return path


def available_files(root: Path) -> list[str]:
    folder = root / DATA_DIR
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES)


def upload_target(root: Path, name: str) -> Path:
    """Where a file chosen by the person in the GUI may be stored. It does not have to exist yet."""
    _check_name(name)
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise PathError(f"'{name}': Nur .csv- und .xlsx-Dateien können analysiert werden.")
    return _confine(root / DATA_DIR, name)


def data_file(root: Path, name: str) -> Path:
    path = upload_target(root, name)
    if not path.is_file():
        files = ", ".join(available_files(root)) or "keine"
        raise PathError(f"Die Datei '{name}' gibt es in {DATA_DIR}/ nicht. Verfügbar: {files}.")
    return path


def workspace(root: Path, name: str, create: bool = False) -> Path:
    _check_name(name)
    path = _confine(root / OUTPUT_DIR, name)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not (path / DRAFT_FILE).is_file():
        raise PathError(f"Für '{name}' gibt es noch keinen Arbeitsstand. Bitte zuerst den Datensatz analysieren.")
    return path


def workspace_name(data_path: Path, sheet: str | None) -> str:
    if not sheet:
        return data_path.stem
    safe_sheet = re.sub(r"[^\w-]+", "_", sheet).strip("_")
    return f"{data_path.stem}_{safe_sheet}"
