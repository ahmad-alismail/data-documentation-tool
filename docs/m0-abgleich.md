# M0: Abgleich der Annahmen mit der Pi-Dokumentation

Geprüft gegen Pi `@earendil-works/pi-coding-agent` **1.1.0** (Dokumentation im installierten Paket unter `docs/`, ergänzt durch den Quellcode in `dist/`). Stand: 27.10.2026.

## Ergebnis

| Bereich | Annahme im Auftrag | Doku bzw. Quellcode | Folge für den Prototyp |
|---|---|---|---|
| Werkzeuge | `--tools` als Positivliste, `--no-builtin-tools`, `--no-extensions`/`--no-skills` mit expliziten Pfaden | Bestätigt (`cli.md`). `--no-extensions` schaltet zusätzlich die eingebauten Erweiterungen `mcp`, `codemode`, `tool_search` und `llama.cpp` ab. | wie geplant |
| Netzwerk | `--offline`, `--no-mcp` | Beide vorhanden. `--offline` stoppt Versionsprüfung, Modellkatalog-Abruf, Paket-Updates, Installationsmeldung und den Download von fd/rg. **MCP prüft `--offline` nicht**, daher ist `--no-mcp` nötig. | beide Schalter plus Umgebungsvariablen |
| Telemetrie | „nicht dokumentiert“ | **Abweichung:** dokumentiert in `settings.md`. `enableInstallTelemetry` ist standardmäßig **an** (anonyme Installationsmeldung an pi.dev sowie Zuordnungs-Header für einige Cloud-Anbieter). `--offline` stoppt die Meldung, aber nicht die Header. `PI_TELEMETRY=0` oder die Einstellung `false` stoppt beides. `enableAnalytics` ist standardmäßig aus; im Code fand sich kein Versand. | `PI_TELEMETRY=0`, `PI_OFFLINE=1`, `enableInstallTelemetry: false` |
| Extensions | TypeScript über jiti, `registerTool` mit TypeBox, `tool_call` mit `{ block, reason }`, Dialoge über `ctx.ui` | Bestätigt. Wirft ein `tool_call`-Handler einen Fehler, wird der Aufruf blockiert (fail-safe). `select`, `confirm`, `input` und `editor` funktionieren auch über RPC, `custom()` nicht. | Nur diese vier Dialogarten, damit die spätere Weboberfläche sie nutzen kann |
| Skills | Das Modell lädt Skills bei Bedarf | **Abweichung:** Pi nennt Skills im Systemprompt nur, wenn `read` oder `bash` aktiv ist (`dist/core/system-prompt.js`). Ohne diese Werkzeuge sieht das Modell keine Skills. | **7. Werkzeug `wissen_laden(thema)`** mit fester Themenliste, ohne Pfadparameter |
| Projektordner | `.pi/SYSTEM.md` ersetzt den Systemprompt | Bestätigt. Pis Abschnitte zu Werkzeugen, Regeln und Doku entfallen; die Werkzeugbeschreibungen gehen weiter über das `tools`-Feld der API an das Modell (im Payload geprüft). Eigene Abschnitte lassen sich über `before_agent_start` ergänzen. | Dateiliste aus `daten/` als eigener Abschnitt |
| Arbeitsverzeichnis im Prompt | – | **Lücke:** Pi hängt den absoluten Projektpfad an (`<cwd>`), der den lokalen Benutzernamen enthält. | Extension ersetzt ihn durch „Projektordner“ |
| Vertrauen | Projekt-Ressourcen erst nach Freigabe | Bestätigt. `--approve` gilt für einen Lauf. | im Startskript |
| Kontextdateien | – | **Lücke:** `AGENTS.md` und `CLAUDE.md` werden **unabhängig von der Vertrauensfreigabe** geladen. | `--no-context-files`, zusätzlich `--no-prompt-templates` |
| Shell der Bedienperson | – | **Lücke:** `!befehl` im Eingabefeld führt Bash aus (Ereignis `user_bash`), unabhängig von den Werkzeugen des Modells. | Extension blockiert `user_bash` |
| Globale Konfiguration | `models.json` im Agent-Verzeichnis | Persönliche Einstellungen, Extensions, Zugangsdaten und Cloud-Anbieter aus `~/.pi/agent` würden mitgeladen. | **Projekteigenes Agent-Verzeichnis** `pi-agent/` über `PI_CODING_AGENT_DIR` |
| Modelle | `models-configuration.md` | Die Datei heißt `models.md`. Format bestätigt (`baseUrl`, `api: "openai-completions"`, `apiKey`, `models[]`). | wie geplant |
| Sandbox | keine eingebaute Sandbox | Bestätigt (`security.md`, `containerization.md`). | „Später“: Container oder VM |

## Telemetrie im Detail

Quelle: Quellcode von Pi 1.1.0.

- **Installationsmeldung:** `dist/modes/interactive/interactive-mode.js` ruft `https://pi.dev/api/report-install?version=…` auf, nur im interaktiven Modus, beim ersten Start und nach Updates. Übertragen werden die Pi-Version und ein `User-Agent`. Abgeschaltet durch `PI_OFFLINE`, `PI_TELEMETRY=0` oder `enableInstallTelemetry: false`.
- **Zuordnungs-Header** an einige Cloud-Anbieter (`dist/core/provider-attribution.js`): nur bei diesen Anbietern; abgeschaltet durch `PI_TELEMETRY=0` oder die Einstellung. Für Ollama nicht relevant.
- **Paket `pi-telemetry`:** sendet selbst nichts (kein Netzwerkcode, nur In-Prozess-Aufzeichnung).
- **Weitere automatische Zugriffe**, die `--offline` abschaltet: Versionsprüfung (`pi.dev/api/latest-version`), Modellkatalog von pi.dev, Paket-Updates, Download von fd/rg, `/bug`-Upload.
- **Was trotz `--offline` bleibt:** MCP-Verbindungen (deshalb `--no-mcp`) und die Anfragen an das eingestellte Modell. Beim lokalen Modell gehen diese nur an `localhost`.

## Live-Prüfung des Harness (M1a)

Mit einer Wegwerf-Extension (ein Testwerkzeug) wurden vor dem Bau geprüft:

1. `--tools <name>` gibt ein Extension-Werkzeug frei; eingebaute Werkzeuge sind nicht aktiv. ✓
2. `--no-extensions -e .pi/extensions/datadoc` mit `--approve` lädt die Extension aus `.pi/`. ✓
3. `.pi/SYSTEM.md` kommt als Systemprompt an; eigene Abschnitte bleiben erhalten; die Werkzeuge stehen im `tools`-Feld. ✓
4. Das projekteigene Agent-Verzeichnis mit `models.json` erreicht Ollama; ein vollständiger Werkzeugaufruf gelingt mit Gemma 4 26B-A4B und gpt-oss 20B. ✓
5. Ollama lädt beide Modelle mit 131.072 Token Kontext vollständig auf die GPU. Eigene Modelfiles sind nicht nötig. ✓
