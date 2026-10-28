"""Command line of the datadoc core. Every command prints one compact JSON object to stdout.

Called by the Pi extension with an argument array (no shell). Free-form input such as
proposals arrives as JSON on stdin. Errors are printed as ``{"fehler": ...}`` with exit code 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from . import draft, export, loader, paths, pii, profile, rules
from .draft import DraftError, Entwurf, SpaltenEintrag

DECISIONS = ("übernommen", "bearbeitet", "verworfen")
FINDING_SUMMARY_KEYS = ("nr", "regel", "spalte", "schwere", "titel", "erklaerung")


def _findings_for(d: Entwurf, column: str) -> list[dict]:
    return [f for f in d.befunde if f["spalte"] == column]


def cmd_analyze(root: Path, args) -> dict:
    path = paths.data_file(root, args.datei)
    table = loader.load(path, args.sheet)
    df = table.df

    columns = []
    for name in df.columns:
        values = df[name].tolist()
        present = [v for v in values if v is not None]
        col_type = profile.classify(name, present)
        columns.append(rules.Column(name, values, col_type, pii.detect(name, present, col_type)))
    masker = pii.Masker([v for c in columns if c.pii.kind == "name" for v in c.present])
    for c in columns:
        if c.type == "freitext":
            c.pii = pii.detect(c.name, c.present, c.type, masker)

    missing = int(df.isna().sum().sum())
    cells = df.shape[0] * df.shape[1]
    fresh = Entwurf(
        quelle=table.meta,
        ueberblick={
            "zeilen": len(df), "spalten": df.shape[1],
            "fehlende_zellen": missing,
            "fehlende_zellen_prozent": round(100 * missing / cells, 1) if cells else 0.0,
            "doppelte_zeilen": int(df.duplicated().sum()),
        },
        befunde=rules.run_all(df, columns, masker),
        spalten={
            c.name: SpaltenEintrag(profil=profile.build(c.name, c.values, c.type, c.pii, masker, rules.name_meaning(c.name)))
            for c in columns
        },
    )
    workspace = paths.workspace(root, paths.workspace_name(path, args.sheet), create=True)
    previous = draft.load(workspace) if (workspace / paths.DRAFT_FILE).is_file() else None
    d = draft.merge_analysis(previous, fresh)
    draft.save(workspace, d)
    follow_ups = {name: rules.follow_up(_findings_for(d, name), e.profil)["empfohlen"] for name, e in d.spalten.items()}
    # On a resumed workspace, checked columns are done and proposed ones only need the person's decision.
    todo = {name: ask for name, ask in follow_ups.items() if d.spalten[name].status in ("offen", "verworfen")}
    return {
        "arbeitsordner": workspace.name,
        "datei": path.name,
        "hinweise": table.meta["hinweise"],
        "ueberblick": d.ueberblick,
        "spalten": [
            {
                "spalte": name, "typ": e.profil["erkannter_typ"],
                "ampel": rules.traffic_light(_findings_for(d, name)),
                "befunde": len(_findings_for(d, name)),
                "rueckfrage": follow_ups[name],
                "status": e.status,
            }
            for name, e in d.spalten.items()
        ],
        "befunde": [{k: f[k] for k in FINDING_SUMMARY_KEYS} for f in d.befunde],
        "reihenfolge": {
            "nur_bestaetigen": [n for n, e in d.spalten.items() if e.status == "vorgeschlagen"],
            "zuerst_einzeln_mit_rueckfrage": [n for n, ask in todo.items() if ask],
            "danach_schnellmodus": [n for n, ask in todo.items() if not ask],
        },
        "fortschritt": draft.progress(d),
    }


def _column_view(d: Entwurf, name: str) -> dict:
    entry = d.spalten[name]
    return {
        "spalte": name,
        "status": entry.status,
        "vorschlag": entry.vorschlag.model_dump() if entry.vorschlag else None,
        "entscheidung": entry.entscheidung.model_dump() if entry.entscheidung else None,
    }


def cmd_column(root: Path, args) -> dict:
    d = draft.load(paths.workspace(root, args.ordner))
    name, entry = d.column(args.spalte)
    findings = _findings_for(d, name)
    return {
        **_column_view(d, name),
        "rueckfrage": rules.follow_up(findings, entry.profil),
        "profil": entry.profil,
        "befunde": findings,
        "fortschritt": draft.progress(d),
    }


def cmd_propose(root: Path, args) -> dict:
    workspace = paths.workspace(root, args.ordner)
    d = draft.load(workspace)
    name = draft.propose(d, args.spalte, read_stdin())
    draft.save(workspace, d)
    return {**_column_view(d, name), "fortschritt": draft.progress(d)}


def cmd_decide(root: Path, args) -> dict:
    workspace = paths.workspace(root, args.ordner)
    d = draft.load(workspace)
    name = draft.decide(d, args.spalte, args.status, read_stdin() if args.status == "bearbeitet" else None)
    draft.save(workspace, d)
    return {**_column_view(d, name), "fortschritt": draft.progress(d)}


def cmd_datasheet(root: Path, args) -> dict:
    workspace = paths.workspace(root, args.ordner)
    d = draft.load(workspace)
    if args.status:
        draft.decide_datasheet(d, args.status, read_stdin() if args.status == "bearbeitet" else None)
    else:
        draft.propose_datasheet(d, read_stdin())
    draft.save(workspace, d)
    return {"datasheet": d.datasheet.model_dump(mode="json"), "fortschritt": draft.progress(d)}


def cmd_status(root: Path, args) -> dict:
    d = draft.load(paths.workspace(root, args.ordner))
    return {
        "spalten": [_column_view(d, name) for name in d.spalten],
        "datasheet": d.datasheet.status,
        "fortschritt": draft.progress(d),
    }


def cmd_export(root: Path, args) -> dict:
    workspace = paths.workspace(root, args.ordner)
    d = draft.load(workspace)
    return {**export.export(d, workspace), "fortschritt": draft.progress(d)}


def read_stdin() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise DraftError("Die Eingabe muss ein JSON-Objekt sein.")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datadoc", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Projektordner mit daten/ und ausgabe/")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="Datensatz analysieren und Arbeitsstand anlegen")
    p.add_argument("datei")
    p.add_argument("--sheet")
    p.set_defaults(handler=cmd_analyze)

    for command, handler, help_text in [
        ("column", cmd_column, "Maskiertes Detailprofil einer Spalte"),
        ("propose", cmd_propose, "Vorschlag ablegen (JSON über stdin)"),
        ("decide", cmd_decide, "Entscheidung der Fachperson speichern (nur über die Extension)"),
    ]:
        p = sub.add_parser(command, help=help_text)
        p.add_argument("ordner")
        p.add_argument("spalte")
        if command == "decide":
            p.add_argument("--status", required=True, choices=DECISIONS)
        p.set_defaults(handler=handler)

    p = sub.add_parser("datasheet", help="Datasheet-Angaben ablegen oder entscheiden")
    p.add_argument("ordner")
    p.add_argument("--status", choices=DECISIONS)
    p.set_defaults(handler=cmd_datasheet)

    for command, handler, help_text in [
        ("status", cmd_status, "Fortschritt je Spalte"),
        ("export", cmd_export, "Dokumentation nach ausgabe/ schreiben"),
    ]:
        p = sub.add_parser(command, help=help_text)
        p.add_argument("ordner")
        p.set_defaults(handler=handler)
    return parser


def emit(payload: dict) -> None:
    sys.stdout.write(pii.scrub(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) + "\n")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        emit(args.handler(args.root.resolve(), args))
        return 0
    except ValidationError as error:
        emit({"fehler": draft.validation_message(error)})
    except json.JSONDecodeError as error:
        emit({"fehler": f"Die Eingabe ist kein gültiges JSON ({error.msg})."})
    except (paths.PathError, loader.LoadError, DraftError) as error:
        emit({"fehler": str(error)})
    return 2


if __name__ == "__main__":
    sys.exit(main())
