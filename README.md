<img src="src/datadoc_gui/static/marke/aitraqc-logo-compact.png" alt="AI TRAQC" height="64">

# Datendokumentations-Assistent

Entwickelt im Projekt AI TRAQC – Regionales Innovationszentrum Artificial Intelligence Training & Qualification Campus.

Ein KI-Assistent, der lokal auf Ihrem Rechner läuft und Fachleute im Gespräch durch die Dokumentation ihrer Daten führt. Er analysiert eine Tabelle, fragt nach, was unklar ist, und hält die Antworten als Dokumentation fest. Jede Bedeutung bestätigt ein Mensch. Die KI erfindet keine.

## Worum es geht

**Das Problem.** Viele kleine und mittlere Unternehmen haben wertvolle Daten, aber kaum Dokumentation. Oft ist unklar, was eine Spalte bedeutet, wie Werte entstanden sind oder wofür eine Abkürzung steht. Bevor ein KI-Projekt beginnen kann, folgen Rückfragen, Meetings und E-Mails. Das nötige Wissen steckt häufig nur in den Köpfen einzelner Mitarbeitender.

**Die Lösung.** Der Assistent arbeitet gemeinsam mit den Fachleuten:

1. **Daten analysieren:** Struktur, Datentypen, Wertebereiche, Auffälligkeiten.
2. **Unklarheiten erkennen und gezielt fragen**, zum Beispiel: „Was bedeutet `STAT`? Wofür stehen die Werte 1 bis 4?“
3. **Gemeinsam dokumentieren:** Aus den Antworten entstehen Vorschläge. Die Fachperson übernimmt, ändert oder verwirft sie.
4. **Qualität prüfen:** Hinweise auf fehlende Werte, Dubletten, uneinheitliche Schreibweisen und Ausreißer.
5. **Dokumentation bereitstellen:** strukturiert, für das Unternehmen und für das KI-Team, das mit den Daten weiterarbeitet.

Weiß niemand eine Antwort, wird daraus eine **offene Frage mit Ansprechperson**, zum Beispiel „Das weiß der Einkauf“.

**Warum lokal?** Vertrauliche Unternehmens- und Kundendaten müssen nicht zu einem Cloud-Anbieter. Das Sprachmodell läuft auf dem eigenen Rechner. Die Tabelle selbst bekommt auch das Modell nie zu sehen: Ein Python-Kern analysiert sie, und das Modell erhält nur dessen Zusammenfassung mit Kennzahlen, häufigen Werten und einzelnen Beispielen. Personenbezogene Werte sind darin maskiert.

**Der Mehrwert.** Das Ziel ist kein weiterer automatischer Qualitätsbericht. Der Assistent verkürzt die Abstimmung zwischen Unternehmen und KI-Team und macht Wissen aus den Köpfen zu einer verständlichen, wiederverwendbaren Dokumentation.

## Was am Ende entsteht

Im Ordner `ausgabe/<dateiname>/`:

| Datei | Inhalt |
|---|---|
| `datenwoerterbuch.md` und `.xlsx` | jede Spalte mit Name, Bedeutung, Typ, Einheit, Wertebereich, Personenbezug und Prüfstatus |
| `datasheet.md` | Angaben zum ganzen Datensatz: Zweck, Entstehung, Pflege, Weitergabe, Einschränkungen, Ansprechperson |
| `offene_fragen.md` | Fragen, die niemand beantworten konnte, jeweils mit Ansprechperson |
| `schema.json` | maschinenlesbares Tabellenschema |

Nur was eine Fachperson bestätigt hat, trägt den Status „geprüft“.

## So funktioniert es

### Ablauf eines Gesprächs

| Schritt | Was passiert | Wer entscheidet |
|---|---|---|
| 1. Datei wählen | Eine CSV- oder Excel-Datei aus `daten/` auswählen | Fachperson |
| 2. Kontext | Wofür werden die Daten genutzt? Wer pflegt sie? Aus welchem System stammen sie? | Fachperson antwortet |
| 3. Analyse | Der Python-Kern prüft die Datei; der Assistent erklärt die wichtigsten Befunde in Alltagssprache | automatisch |
| 4. Spalten | Bei unklaren Spalten eine Rückfrage, dann ein Vorschlag; eindeutige Spalten gesammelt | Fachperson: **Übernehmen · Bearbeiten · Verwerfen** |
| 5. Datasheet | Bis zu sechs kurze Fragen zum ganzen Datensatz | Fachperson bestätigt |
| 6. Export | Die Dateien werden nach `ausgabe/` geschrieben | automatisch |

### Architektur

```
Fachperson
   │   Browser (start.ps1 -Gui)   oder   Terminal (start.ps1)
   ▼
Pi (Agent-Harness) ──────────────── Sprachmodell (lokal über Ollama, austauschbar)
   ├─ .pi/SYSTEM.md            fester Ablauf in 6 Schritten
   ├─ .pi/skills/              Fachwissen: Datasheet, Personenbezug, Befunde erklären
   └─ .pi/extensions/datadoc   7 Werkzeuge · Sicherheitsprüfung · Bestätigungsdialoge
          │   Aufruf ohne Shell, Daten als JSON
          ▼
Python-Kern datadoc           Analyse · 13 Qualitätsregeln · Maskierung · Arbeitsstand · Export
          │
liest nur daten/  ·  schreibt nur ausgabe/
```

| Baustein | Ordner | Aufgabe |
|---|---|---|
| Oberfläche | `src/datadoc_gui/` | Browser-Oberfläche mit Gespräch, Bestätigungsdialogen, Fortschritt, Upload und Ergebnissen; startet Pi im RPC-Modus |
| Agent-Harness | Pi, `pi-agent/` | verbindet Sprachmodell und Werkzeuge; eigene Einstellungen, offline |
| Verhalten | `.pi/SYSTEM.md`, `.pi/skills/` | Rolle, Ablauf, Regeln und Fachwissen des Assistenten |
| Werkzeuge | `.pi/extensions/datadoc/` | die einzigen 7 Werkzeuge des Modells, die Sicherheitsprüfung jedes Aufrufs und die Dialoge |
| Python-Kern | `src/datadoc/` | rechnet alles Deterministische: Datentypen, Kennzahlen, Qualitätsregeln, Erkennung und Maskierung personenbezogener Daten, Export |
| Sprachmodell | `pi-agent/models.json` | Standard: Gemma 4 26B-A4B über Ollama; austauschbar ohne Codeänderung |

Die 7 Werkzeuge des Modells:

| Werkzeug | Zweck |
|---|---|
| `datensatz_analysieren` | Datei aus `daten/` analysieren: Überblick, Ampel je Spalte, Befunde |
| `spalte_ansehen` | maskiertes Profil einer Spalte |
| `vorschlag_speichern` | Beschreibung einer Spalte als Vorschlag ablegen, mit offenen Fragen |
| `vorschlag_bestaetigen` | Vorschläge der Fachperson zur Entscheidung zeigen |
| `datasheet_speichern` | Angaben zum ganzen Datensatz ablegen und bestätigen lassen |
| `dokumentation_exportieren` | Dateien nach `ausgabe/` schreiben |
| `wissen_laden` | Fachwissen aus `.pi/skills/` nachschlagen |

**Grundsätze** (Details in [docs/sicherheit.md](docs/sicherheit.md)):

- Alle Zahlen und Befunde berechnet der Python-Kern. Das Modell rechnet nicht selbst und sieht nie die Tabelle, nur die Zusammenfassung des Kerns: Kennzahlen, häufige Werte und einzelne Beispiele, personenbezogene Werte maskiert.
- Das Modell hat nur diese 7 Werkzeuge. Es kann keine Dateien öffnen, keine Befehle ausführen und nicht ins Internet.
- Den Status „geprüft“ setzt nur ein Mensch im Dialog.
- Nach der Installation läuft alles offline.

## Voraussetzungen

**Hardware**

- Windows 10 oder 11
- Grafikkarte mit etwa 20 GB Speicher für das Standardmodell. Mit weniger läuft es langsamer, teilweise auf dem Prozessor, oder Sie nehmen das kleinere Modell gpt-oss 20B.
- etwa 20 GB freier Speicherplatz für das Modell

**Software**

| Programm | Wofür |
|---|---|
| [Node.js](https://nodejs.org) 20 oder neuer | führt Pi aus |
| [Pi](https://pi.dev) (`@earendil-works/pi-coding-agent`, geprüft mit 1.1.0) | Agent-Harness |
| [uv](https://docs.astral.sh/uv/) | richtet Python 3.11 und die Bibliotheken selbst ein |
| [Ollama](https://ollama.com) | führt das Sprachmodell lokal aus |
| Edge, Chrome (ab Version 123) oder Firefox (ab 120) | Browser-Oberfläche |

Internet braucht es nur für die Installation und den ersten Start.

## Installation

Alle Befehle in **PowerShell** eingeben.

**1. Programme installieren**

```powershell
winget install OpenJS.NodeJS.LTS
winget install astral-sh.uv
winget install Ollama.Ollama
```

Danach ein **neues** PowerShell-Fenster öffnen, damit die Programme gefunden werden.

**2. Pi installieren**

```powershell
npm install -g @earendil-works/pi-coding-agent
```

**3. Sprachmodell herunterladen** (17 GB; optional zusätzlich `gpt-oss:20b`, 13 GB)

```powershell
ollama pull gemma4:26b-a4b-it-q4_K_M
```

**4. Projektordner** auf den Rechner kopieren und in PowerShell hineinwechseln:

```powershell
cd C:\Pfad\zu\data-documentation-tool
```

**5. Erster Start**

```powershell
.\start.ps1 -Gui
```

Beim ersten Start legt das Skript die Python-Umgebung an und erzeugt einen Demo-Datensatz. Danach läuft alles offline.

Blockiert Windows das Skript, starten Sie es so:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Gui
```

## Benutzung

### Im Browser (empfohlen)

1. Im Projektordner `.\start.ps1 -Gui` starten. Der Browser öffnet sich. Falls nicht: die Adresse aus dem PowerShell-Fenster öffnen. Sie enthält einen Zugangsschlüssel, der nur für diesen Start gilt.
2. Rechts unter **Dateien** auf **Dokumentieren** klicken. Eigene CSV- oder Excel-Dateien (höchstens 50 MB) einfach hineinziehen.
3. Die Fragen des Assistenten im Chat beantworten. Wissen Sie etwas nicht, schreiben Sie es, zum Beispiel: „Weiß ich nicht, das weiß der Einkauf.“
4. Jeden Vorschlag in der Karte entscheiden: **Übernehmen**, **Bearbeiten** (Formular) oder **Verwerfen**.
5. Nach dem Export stehen die Dateien rechts unter **Ergebnisse** zum Ansehen und Herunterladen bereit.
6. Beenden: im PowerShell-Fenster `Strg+C` drücken oder das Fenster schließen.

Rechts sehen Sie jederzeit den Fortschritt und je Spalte die Befunde. Oben zeigt **Kontext**, wie voll das Gedächtnis des Modells für dieses Gespräch ist (Tokens beim Darüberfahren). Dort wechseln Sie auch das Modell, die Darstellung (wie das System, hell oder dunkel) oder beginnen neu.

**Später weitermachen:** Das Gespräch wird nicht gespeichert, der Arbeitsstand schon. Bei einer Datei mit gespeichertem Arbeitsstand steht rechts unter **Dateien**, wie viele Spalten geprüft sind, und der Knopf heißt **Fortsetzen**. Der Assistent übernimmt dann alle bisherigen Entscheidungen, überspringt die Kontextfragen und macht mit den offenen Spalten weiter.

### Im Terminal

```powershell
.\start.ps1
```

Das Gespräch läuft direkt in PowerShell. Dialoge bedienen Sie mit den Pfeiltasten und `Enter`. `/werkzeuge` zeigt, welche Werkzeuge das Modell nutzen darf. Beenden mit zweimal `Strg+C`.

### Anderes Modell

```powershell
.\start.ps1 -Gui -Modell ollama/gpt-oss:20b
```

Im Browser geht das auch über die Auswahl oben rechts. LM Studio oder einen anderen Modelldienst einbinden: [docs/modelle.md](docs/modelle.md).

## Häufige Probleme

| Problem | Lösung |
|---|---|
| „… wurde nicht gefunden“ beim Start | Programm installieren (siehe Voraussetzungen) und ein neues PowerShell-Fenster öffnen |
| Warnung „Ollama antwortet nicht“ | Ollama starten, dann erneut `.\start.ps1 -Gui` |
| „Kein Zugriff“ im Browser | Die Adresse stammt von einem früheren Start. Die Adresse aus dem aktuellen PowerShell-Fenster öffnen. |
| Der Assistent antwortet nicht oder überspringt etwas | Kleine Modelle tun das gelegentlich. Schreiben Sie zum Beispiel „Bitte machen Sie weiter.“ oder nennen Sie die Spalte. |
| Sehr langsame Antworten | Das Modell passt nicht ganz in den Grafikspeicher. Das kleinere Modell wählen. |

## Grenzen

- Eingabe: CSV (Trennzeichen und Kodierung werden erkannt) und `.xlsx`, höchstens 50 MB. Ab 200.000 Zeilen wird eine Stichprobe analysiert.
- Eine Datei pro Arbeitsstand; Beziehungen zwischen Dateien werden nicht erfasst.
- Namen in Freitext erkennt die Maskierung nur, wenn sie auch in einer Namensspalte stehen oder mit Anrede („Herr …“, „Frau …“) vorkommen.
- Der Assistent bereinigt keine Daten. Er dokumentiert und meldet nur.
- Eine Person an einem Rechner. Pi selbst hat keine Sandbox; für den produktiven Einsatz gehört der Assistent in einen Container oder eine VM.

## Weitere Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/sicherheit.md](docs/sicherheit.md) | Sicherheitskonzept nach dem Prinzip der minimalen Rechte |
| [docs/demo.md](docs/demo.md) | 5-Minuten-Vorführung mit dem Demo-Datensatz |
| [docs/modelle.md](docs/modelle.md) | Modell wechseln: Ollama, LM Studio, andere Dienste |
| [docs/entwicklung.md](docs/entwicklung.md) | Tests, Kommandos des Python-Kerns, Ausblick |
| [docs/modelltest.md](docs/modelltest.md) | Vergleich lokaler Modelle |
| [docs/m0-abgleich.md](docs/m0-abgleich.md) | Abgleich mit der Pi-Dokumentation, Telemetrie |

## Projektstruktur

```
start.ps1           Startskript (Terminal oder mit -Gui im Browser)
daten/              Eingabe: nur hier wird gelesen (bleibt lokal, nicht im Repository)
ausgabe/            Ergebnisse: nur hier wird geschrieben (bleibt lokal, nicht im Repository)
src/datadoc/        Python-Kern
src/datadoc_gui/    Browser-Oberfläche
.pi/                Systemprompt, Skills, Extension mit den Werkzeugen
pi-agent/           projekteigene Pi-Einstellungen und Modelle
scripts/            Demo-Daten, automatischer Demo-Lauf
tests/              Tests
docs/               weitere Dokumentation
video/              Unterlagen für das Erklärvideo
```

## Lizenz

Code und Dokumentation stehen unter der [MIT-Lizenz](LICENSE). Davon ausgenommen sind:

- **Logo und Name AI TRAQC** (`src/datadoc_gui/static/marke/`, `video/*.png`): Marke des Projekts, nicht zur freien Verwendung.
- **Schriften** Barlow, Barlow Semi Condensed und IBM Plex Mono (`src/datadoc_gui/static/fonts/`): SIL Open Font License, Lizenztexte liegen bei.
- **Icons** von Lucide (`src/datadoc_gui/static/icons.js`): ISC-Lizenz, siehe `src/datadoc_gui/static/LICENSE-lucide.txt`.
