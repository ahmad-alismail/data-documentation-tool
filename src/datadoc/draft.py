"""Working state ``ausgabe/<ordner>/entwurf.json``: proposals, human decisions, progress."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .paths import DRAFT_FILE

SAVE_ATTEMPTS = 5

Status = Literal["offen", "vorgeschlagen", "geprüft", "verworfen"]
Decision = Literal["übernommen", "bearbeitet", "verworfen"]
FachTyp = Literal[
    "kennung", "kategorie", "freitext", "datum", "geldbetrag", "menge",
    "name", "kontaktdaten", "ort", "sonstiges",
]
PiiStufe = Literal["keine", "personenbezogen", "besondere_kategorie"]
Konfidenz = Literal["hoch", "mittel", "niedrig"]


class DraftError(ValueError):
    """Invalid operation on the working state."""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class OffeneFrage(_Strict):
    frage: str = Field(min_length=3, max_length=500)
    ansprechperson: str | None = Field(default=None, max_length=120)


class Vorschlag(_Strict):
    beschreibung: str = Field(min_length=3, max_length=1000)
    lesbarer_name: str = Field(min_length=1, max_length=120)
    fachlicher_typ: FachTyp
    einheit: str | None = Field(default=None, max_length=60)
    wertebereich: str | None = Field(default=None, max_length=500)
    pii_stufe: PiiStufe
    konfidenz: Konfidenz
    offene_fragen: list[OffeneFrage] = Field(default_factory=list, max_length=10)

    @field_validator("offene_fragen", mode="before")
    @classmethod
    def _accept_plain_questions(cls, value):
        if value is None:
            return []
        return [{"frage": q} if isinstance(q, str) else q for q in value]


class Entscheidung(BaseModel):
    art: Decision
    zeitpunkt: str
    geaenderte_felder: list[str] = Field(default_factory=list)


class SpaltenEintrag(BaseModel):
    profil: dict
    status: Status = "offen"
    vorschlag: Vorschlag | None = None
    entscheidung: Entscheidung | None = None
    verlauf: list[dict] = Field(default_factory=list)


class DatasheetFelder(_Strict):
    zweck: str | None = Field(default=None, max_length=1000)
    erhebung: str | None = Field(default=None, max_length=1000)
    aktualisierung: str | None = Field(default=None, max_length=1000)
    weitergabe: str | None = Field(default=None, max_length=1000)
    einschraenkungen: str | None = Field(default=None, max_length=1000)
    ansprechperson: str | None = Field(default=None, max_length=200)


class Datasheet(BaseModel):
    felder: DatasheetFelder = Field(default_factory=DatasheetFelder)
    status: Status = "offen"
    entscheidung: Entscheidung | None = None


class Entwurf(BaseModel):
    version: int = 1
    erstellt: str = Field(default_factory=now)
    aktualisiert: str = Field(default_factory=now)
    quelle: dict
    ueberblick: dict
    befunde: list[dict]
    spalten: dict[str, SpaltenEintrag]
    datasheet: Datasheet = Field(default_factory=Datasheet)

    def column(self, name: str) -> tuple[str, SpaltenEintrag]:
        if name in self.spalten:
            return name, self.spalten[name]
        matches = [c for c in self.spalten if c.casefold() == name.strip().casefold()]
        if len(matches) == 1:
            return matches[0], self.spalten[matches[0]]
        raise DraftError(f"Die Spalte '{name}' gibt es nicht. Vorhanden: {', '.join(self.spalten)}.")


def validation_message(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        location = ".".join(str(p) for p in item["loc"]) or "Eingabe"
        parts.append(f"{location}: {item['msg']}")
    return "Ungültige Angaben – " + "; ".join(parts)


def load(workspace: Path) -> Entwurf:
    return Entwurf.model_validate_json((workspace / DRAFT_FILE).read_text(encoding="utf-8"))


def save(workspace: Path, draft: Entwurf) -> None:
    draft.aktualisiert = now()
    target = workspace / DRAFT_FILE
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, indent=1), encoding="utf-8")
    # On Windows the replace fails while another process (the GUI, a virus scanner) is reading the file.
    for attempt in range(SAVE_ATTEMPTS):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == SAVE_ATTEMPTS - 1:
                raise
            time.sleep(0.05)


def progress(draft: Entwurf) -> dict:
    statuses = [c.status for c in draft.spalten.values()]
    checked = statuses.count("geprüft")
    total = len(statuses)
    return {
        "geprueft": checked,
        "vorgeschlagen": statuses.count("vorgeschlagen"),
        "offen": statuses.count("offen") + statuses.count("verworfen"),
        "gesamt": total,
        "datasheet": draft.datasheet.status,
        "text": f"{checked} von {total} Spalten geprüft",
    }


def merge_analysis(previous: Entwurf | None, fresh: Entwurf) -> Entwurf:
    """Keep proposals and decisions of columns that still exist after a re-analysis."""
    if previous is None:
        return fresh
    for name, entry in fresh.spalten.items():
        old = previous.spalten.get(name)
        if old:
            entry.status, entry.vorschlag, entry.entscheidung, entry.verlauf = (
                old.status, old.vorschlag, old.entscheidung, old.verlauf,
            )
    fresh.datasheet = previous.datasheet
    fresh.erstellt = previous.erstellt
    return fresh


def propose(draft: Entwurf, column: str, data: dict) -> str:
    name, entry = draft.column(column)
    entry.vorschlag = Vorschlag.model_validate(data)
    entry.status = "vorgeschlagen"
    entry.entscheidung = None
    entry.verlauf.append({"ereignis": "vorgeschlagen", "zeitpunkt": now()})
    return name


def _changed_fields(before: BaseModel, after: BaseModel) -> list[str]:
    old, new = before.model_dump(), after.model_dump()
    return [key for key in new if old.get(key) != new[key]]


def decide(draft: Entwurf, column: str, decision: str, changes: dict | None) -> str:
    name, entry = draft.column(column)
    if entry.status != "vorgeschlagen" or entry.vorschlag is None:
        raise DraftError(f"Für '{name}' liegt kein offener Vorschlag vor (Status: {entry.status}).")
    changed: list[str] = []
    if decision == "verworfen":
        entry.status, entry.vorschlag = "verworfen", None
    else:
        if decision == "bearbeitet":
            edited = Vorschlag.model_validate(entry.vorschlag.model_dump() | (changes or {}))
            changed = _changed_fields(entry.vorschlag, edited)
            entry.vorschlag = edited
        entry.status = "geprüft"
    entry.entscheidung = Entscheidung(art=decision, zeitpunkt=now(), geaenderte_felder=changed)
    entry.verlauf.append({"ereignis": decision, "zeitpunkt": now(), "geaenderte_felder": changed})
    return name


def propose_datasheet(draft: Entwurf, data: dict) -> None:
    merged = draft.datasheet.felder.model_dump() | {k: v for k, v in data.items() if v not in (None, "")}
    draft.datasheet.felder = DatasheetFelder.model_validate(merged)
    draft.datasheet.status = "vorgeschlagen"
    draft.datasheet.entscheidung = None


def decide_datasheet(draft: Entwurf, decision: str, changes: dict | None) -> None:
    sheet = draft.datasheet
    if sheet.status != "vorgeschlagen":
        raise DraftError(f"Für das Datasheet liegt kein offener Vorschlag vor (Status: {sheet.status}).")
    changed: list[str] = []
    if decision == "verworfen":
        sheet.status, sheet.felder = "verworfen", DatasheetFelder()
    else:
        if decision == "bearbeitet":
            edited = DatasheetFelder.model_validate(sheet.felder.model_dump() | (changes or {}))
            changed = _changed_fields(sheet.felder, edited)
            sheet.felder = edited
        sheet.status = "geprüft"
    sheet.entscheidung = Entscheidung(art=decision, zeitpunkt=now(), geaenderte_felder=changed)
