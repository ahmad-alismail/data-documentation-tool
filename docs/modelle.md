# Sprachmodell wechseln

Das Modell wird nur über `pi-agent/models.json` eingebunden (optional `defaultModel` in `pi-agent/settings.json`), ohne Codeänderung. Alle dort eingetragenen Modelle erscheinen auch in der Auswahl der Browser-Oberfläche.

Starten mit einem bestimmten Modell:

```powershell
.\start.ps1 -Gui -Modell <provider>/<modell-id>
```

## Ollama (voreingestellt)

```json
{
  "providers": {
    "ollama": {
      "baseUrl": "http://localhost:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "models": [{ "id": "gemma4:26b-a4b-it-q4_K_M", "contextWindow": 32768, "maxTokens": 8192,
                   "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 } }]
    }
  }
}
```

Ein weiteres Ollama-Modell: mit `ollama pull <name>` herunterladen und einen weiteren Eintrag unter `models` anlegen.

## LM Studio

In LM Studio den Server starten, das Modell laden und die Modell-ID übernehmen:

```json
"lmstudio": {
  "baseUrl": "http://localhost:1234/v1",
  "api": "openai-completions",
  "apiKey": "lmstudio",
  "models": [{ "id": "<modell-id-aus-lm-studio>", "contextWindow": 32768, "maxTokens": 8192,
               "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0 } }]
}
```

Danach: `.\start.ps1 -Gui -Modell lmstudio/<modell-id>`.

## OpenAI-kompatibler Dienst

Zum Beispiel ein LLM-Dienst Ihrer Organisation: wie oben mit dessen `baseUrl`. Den Schlüssel als Umgebungsvariable einbinden, etwa `"apiKey": "$MEIN_LLM_KEY"`.

**Hinweis:** Dann verlassen die Zusammenfassungen des Python-Kerns (Kennzahlen, häufige Werte, maskierte Beispiele) und die Antworten im Gespräch den Rechner. Häufige Werte sind echte Zellinhalte, etwa Ortsnamen. Die Tabelle selbst und personenbezogene Werte verlassen ihn auch in diesem Fall nicht.

## Welches Modell?

Kleine lokale Modelle unterscheiden sich stark darin, wie zuverlässig sie Werkzeuge aufrufen. Ergebnisse des Vergleichs: [modelltest.md](modelltest.md).
