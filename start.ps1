<#
.SYNOPSIS
  Startet den Datendokumentations-Assistenten: Pi mit lokalem Modell, offline und nur mit den eigenen Werkzeugen.

.PARAMETER Modell
  Optional. Modell im Format provider/id aus pi-agent/models.json, z. B. ollama/gpt-oss:20b.
  Ohne Angabe gilt defaultModel aus pi-agent/settings.json.

.PARAMETER Gui
  Startet die grafische Oberfläche im Browser statt des Terminals (gleiche Werkzeuge und Schalter).

.EXAMPLE
  .\start.ps1
  .\start.ps1 -Modell ollama/gpt-oss:20b
  .\start.ps1 -Gui
#>
param([string]$Modell, [switch]$Gui)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Isolation: eigenes Pi-Verzeichnis statt ~/.pi/agent, keine automatischen Netzzugriffe, keine Telemetrie.
$env:PI_CODING_AGENT_DIR = Join-Path $PSScriptRoot 'pi-agent'
$env:PI_OFFLINE = '1'
$env:PI_TELEMETRY = '0'
$env:PI_SKIP_VERSION_CHECK = '1'

foreach ($programm in 'pi', 'uv') {
    if (-not (Get-Command $programm -ErrorAction SilentlyContinue)) {
        throw "$programm wurde nicht gefunden. Siehe README, Abschnitt Voraussetzungen."
    }
}

if (-not (Test-Path '.venv')) {
    Write-Host 'Lege die Python-Umgebung an (einmalig, braucht Internet) ...'
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'uv sync ist fehlgeschlagen.' }
}

if (-not (Test-Path 'daten/auftraege_handwerksbetrieb.csv')) {
    Write-Host 'Erzeuge den synthetischen Demo-Datensatz ...'
    & .venv/Scripts/python.exe scripts/make_demo_data.py
}

try {
    Invoke-RestMethod -Uri 'http://localhost:11434/api/version' -TimeoutSec 3 | Out-Null
} catch {
    Write-Warning 'Ollama antwortet nicht auf localhost:11434. Bitte Ollama starten oder ein anderes Modell in pi-agent/models.json eintragen.'
}

if ($Gui) {
    # The GUI starts Pi itself in RPC mode, with the flags from src/datadoc_gui/pi_rpc.py (same as below).
    $guiArgumente = @('-m', 'datadoc_gui')
    if ($Modell) { $guiArgumente += @('--modell', $Modell) }
    & .venv/Scripts/python.exe @guiArgumente
    exit $LASTEXITCODE
}

$werkzeuge = 'datensatz_analysieren,spalte_ansehen,vorschlag_speichern,vorschlag_bestaetigen,datasheet_speichern,dokumentation_exportieren,wissen_laden'
$argumente = @(
    '--offline', '--no-mcp', '--approve',
    '--no-extensions', '-e', '.pi/extensions/datadoc',
    '--no-skills',
    '--skill', '.pi/skills/datasheet-erstellen',
    '--skill', '.pi/skills/pii-einstufung',
    '--skill', '.pi/skills/befunde-erklaeren',
    '--no-context-files', '--no-prompt-templates',
    '--tools', $werkzeuge
)
if ($Modell) { $argumente += @('--model', $Modell) }

pi @argumente
