# Sicherheitskonzept

Der Assistent folgt dem **Prinzip der minimalen Rechte**: Das Sprachmodell bekommt nur, was es für die Aufgabe braucht. Jede Regel ist technisch durchgesetzt, nicht nur im Prompt verlangt.

| Regel | Umsetzung |
|---|---|
| Das Modell hat keine eingebauten Werkzeuge | `--tools` mit genau 7 Werkzeugen, `--no-extensions`, `--no-mcp`. Die Extension prüft beim Start die aktiven Werkzeuge. Das `tool_call`-Gate blockiert alles außerhalb der Positivliste; bei einem Fehler in der Prüfung wird blockiert (fail closed). |
| Die Tabelle selbst kommt nie in den Kontext | Der Python-Kern liest die Datei, rechnet alle Kennzahlen und Befunde und liefert dem Modell nur eine Zusammenfassung: Kennzahlen, Muster, die häufigsten Werte (bei Kategorien bis zu 50, sonst 10) und höchstens 5 Beispiele je Spalte und je Befund. Einzelne Zeilen gibt kein Werkzeug heraus. Personenbezogene Spalten erscheinen als `[NAME]`, `[TELEFON]`, `[E-MAIL]`; Telefonnummern nur als Formatmuster (`99999/999999`). In Freitext werden Namen, Telefonnummern, E-Mail-Adressen und IBANs maskiert. Jede Ausgabe läuft zusätzlich durch einen Filter für Telefonnummern, E-Mail-Adressen und IBANs. Die Tests prüfen, dass kein Klarwert in Ausgaben oder Exportdateien landet. |
| Nur der Mensch bestätigt | Kein Werkzeug hat einen Status-Parameter. Der Status „geprüft“ entsteht nur aus der Antwort im Dialog (`ctx.ui.select`/`editor`). Ohne Dialog wird nichts bestätigt. Im Modelltest meldete ein Modell „✅ als geprüft markiert“, ohne den Dialog aufzurufen; im Export blieben alle Spalten korrekt unbestätigt ([modelltest.md](modelltest.md)). |
| Dateizugriff nur in zwei Ordnern | Gelesen wird nur aus `daten/`, geschrieben nur nach `ausgabe/`. Dateinamen werden in der Extension und noch einmal im Python-Kern geprüft (kein `..`, keine Pfade, keine Laufwerke, Auflösung von Verknüpfungen). |
| Keine Shell-Strings | Die Extension startet den Kern mit `spawn` ohne Shell und mit Argument-Array. Modellinhalte gehen als JSON über stdin. Der Kern erhält nur die nötigsten Umgebungsvariablen und keine Zugangsdaten. Die Shell der Bedienperson (`!befehl`) ist im Terminal gesperrt; in der Oberfläche geht `!befehl` nur als Text an das Modell. |
| Offline, ohne Fremdeinflüsse | `--offline`, `PI_OFFLINE=1`, `PI_TELEMETRY=0`, `enableInstallTelemetry: false`, `--no-mcp`, `--no-context-files`, `--no-prompt-templates`, eigenes Agent-Verzeichnis `pi-agent/` statt `~/.pi/agent`. Der lokale Projektpfad wird im Systemprompt ausgeblendet. Details zur Telemetrie: [m0-abgleich.md](m0-abgleich.md). |
| Prompt-Injection in Daten ist wirkungslos | Zellinhalte erscheinen nur als Daten im JSON. Die Regel `anweisungsaehnlicher_text` meldet solche Zellen als Befund. Selbst wenn das Modell einer Anweisung folgen wollte, hat es weder die Tabelle noch Werkzeuge dafür. |
| Oberfläche nur für die Bedienperson | Der Server lauscht nur auf `127.0.0.1`. Jede Anfrage braucht das Sitzungs-Cookie (`HttpOnly`, `SameSite=Strict`) aus dem einmaligen Zugangsschlüssel. Der `Host`-Header muss den Server nennen (Schutz vor DNS-Rebinding); schreibende Anfragen dürfen keinen fremden `Origin` haben. Dialogantworten kommen nur aus dem Browser und nur für den gerade offenen Dialog; der Server selbst bricht Dialoge höchstens ab (bei **Stopp**). |
| Modelltext kann im Browser nichts ausführen | Antworten und Exportdateien laufen durch einen Markdown-Renderer, der zuerst alles maskiert und nur feste Tags ohne Attribute erzeugt (keine Links, Bilder oder HTML). Alles andere wird als Text gesetzt. Die Content-Security-Policy erlaubt nur Skripte und Stile vom Server selbst. Ein Test rendert die Injection-Zeile und HTML-Nutzlasten. |
| Hochladen ändert nur `daten/` | Nur die Bedienperson lädt hoch, nie das Modell. Gleiche Namensregeln wie im Kern (`paths.upload_target`), nur `.csv`/`.xlsx`, höchstens 50 MB (vor dem Lesen geprüft), Ersetzen nur nach Rückfrage. |
| Gleiche Schalter in Terminal und Oberfläche | `src/datadoc_gui/pi_rpc.py` startet Pi mit denselben Schaltern wie `start.ps1`. Ein Test schlägt fehl, sobald beide voneinander abweichen. |

## Was bei einem anderen Modelldienst den Rechner verlässt

Mit einem lokalen Modell verlässt nichts den Rechner. Bei einem OpenAI-kompatiblen Dienst außerhalb (siehe [modelle.md](modelle.md)) gehen die Zusammenfassungen des Python-Kerns (Kennzahlen, häufige Werte, maskierte Beispiele) und die Antworten im Gespräch an diesen Dienst. Häufige Werte sind echte Zellinhalte, etwa Ortsnamen oder Bemerkungen ohne Personenbezug. Die Tabelle selbst und personenbezogene Werte verlassen den Rechner auch dann nicht.

## Grenzen

Pi selbst hat keine Sandbox. Für den produktiven Einsatz sollte der Assistent in einem Container oder einer VM laufen.
