# Entwicklung

## Tests

```powershell
uv run pytest                                                              # Python-Kern, Oberfläche, gleiche Pi-Schalter
node --test .pi/extensions/datadoc/gate.test.ts tests/gui_static.test.mjs  # Gate, Dialog-Parser, Markdown-Renderer, Formular
uv run python scripts/demo_lauf.py --modell ollama/gemma4:26b-a4b-it-q4_K_M --laeufe 3
```

- Die `node --test`-Tests brauchen Node.js 22.18 oder neuer (TypeScript ohne Zusatzschalter).
- Die Tests der Oberfläche laufen gegen ein simuliertes Pi (`tests/fake_pi.py`) und brauchen kein Sprachmodell.
- `scripts/demo_lauf.py` spielt die [Vorführung](demo.md) über Pis RPC-Modus mit einer simulierten Fachperson durch, beantwortet die Dialoge, führt die Sicherheitsproben aus und prüft die Abnahmekriterien. Berichte und Ergebnisse landen in `ausgabe/_demo_laeufe/`. Ein vorhandener Arbeitsstand des Demo-Datensatzes wird vorher nach `ausgabe/_demo_laeufe/_sicherung_<zeit>/` verschoben.

## Kommandos des Python-Kerns

Die Extension ruft den Kern als `python -m datadoc --root <projekt> <kommando>` auf. Jedes Kommando gibt ein JSON-Objekt aus; der Arbeitsstand liegt in `ausgabe/<datei>/entwurf.json`.

| Kommando | Zweck |
|---|---|
| `analyze <datei> [--sheet]` | Überblick, Ampel je Spalte, Befunde; legt den Arbeitsstand an oder übernimmt einen vorhandenen |
| `column <ordner> <spalte>` | maskiertes Detailprofil einer Spalte |
| `propose <ordner> <spalte>` | Vorschlag als JSON über stdin → Status „vorgeschlagen“ |
| `decide <ordner> <spalte> --status übernommen\|bearbeitet\|verworfen` | Entscheidung der Fachperson; nur die Extension ruft das nach einem Dialog auf |
| `datasheet <ordner> [--status …]` | Datasheet-Angaben ablegen oder entscheiden |
| `status <ordner>` | Fortschritt je Spalte |
| `export <ordner>` | Datenwörterbuch, Datasheet, Schema und offene Fragen schreiben |

## Oberfläche

`src/datadoc_gui/` ist eine dünne Schicht über Pis RPC-Modus und nutzt nur die Python-Standardbibliothek:

| Datei | Aufgabe |
|---|---|
| `pi_rpc.py` | startet Pi mit denselben Schaltern wie `start.ps1`; RPC-Client (auch von `scripts/demo_lauf.py` genutzt) |
| `sitzung.py` | übersetzt Pi-Ereignisse in den Zustand der Seite und Aktionen der Person in Pi-Befehle |
| `server.py` | HTTP-Server auf `127.0.0.1` mit Zugriffsprüfung, Server-Sent Events, Upload und Export |
| `static/` | Seite ohne Build-Schritt, gestaltet nach den AI-TRAQC-UI-Richtlinien. Farben hell und dunkel per `light-dark()`; `thema.js` setzt die gespeicherte Darstellung vor dem ersten Zeichnen. Schriften (Barlow, Barlow Semi Condensed, IBM Plex Mono; SIL OFL, `fonts/`) und Icons (Lucide, ISC, `icons.js`) liegen lokal, damit alles offline läuft und keine Anfragen an fremde Server gehen. Logo: `marke/`. |

Direkt starten: `uv run python -m datadoc_gui [--modell X] [--port 8765] [--kein-browser]`.

## Nicht-Ziele

- keine Benutzerkonten, kein Datenbankserver, kein Mehrbenutzerbetrieb
- keine automatische Datenbereinigung: Der Assistent dokumentiert und meldet nur

## Ausblick

- Betrieb in Container oder VM
- Auslieferung als Pi-Paket
- Vergleich von Modellen und Harnesses gegen `daten/ground_truth.json`
- mehrere Dateien mit Beziehungen
- PII-Erkennung zusätzlich mit Microsoft Presidio
