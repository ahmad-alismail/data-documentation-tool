import json
import subprocess
import sys

from tests.conftest import DEMO, REPO, VALID_PROPOSAL, WORKSPACE


def test_analyze_creates_draft(analyzed, project):
    assert analyzed["arbeitsordner"] == WORKSPACE
    assert (project / "ausgabe" / WORKSPACE / "entwurf.json").is_file()
    assert analyzed["fortschritt"]["text"] == "0 von 11 Spalten geprüft"


def test_propose_then_accept(run, analyzed):
    code, result, _ = run("propose", WORKSPACE, "STAT", stdin=VALID_PROPOSAL)
    assert code == 0 and result["status"] == "vorgeschlagen"
    code, result, _ = run("decide", WORKSPACE, "STAT", "--status", "übernommen")
    assert code == 0 and result["status"] == "geprüft"
    assert result["entscheidung"]["art"] == "übernommen"
    assert result["fortschritt"]["text"] == "1 von 11 Spalten geprüft"


def test_edit_records_changed_fields(run, analyzed):
    run("propose", WORKSPACE, "ORT", stdin={**VALID_PROPOSAL, "lesbarer_name": "Ort", "fachlicher_typ": "ort"})
    code, result, _ = run("decide", WORKSPACE, "ORT", "--status", "bearbeitet", stdin={"lesbarer_name": "Einsatzort"})
    assert code == 0
    assert result["vorschlag"]["lesbarer_name"] == "Einsatzort"
    assert result["entscheidung"]["geaenderte_felder"] == ["lesbarer_name"]


def test_reject_resets_column(run, analyzed):
    run("propose", WORKSPACE, "X1", stdin=VALID_PROPOSAL)
    code, result, _ = run("decide", WORKSPACE, "X1", "--status", "verworfen")
    assert code == 0 and result["status"] == "verworfen" and result["vorschlag"] is None
    assert result["fortschritt"]["offen"] == 11


def test_decide_requires_pending_proposal(run, analyzed):
    code, result, _ = run("decide", WORKSPACE, "STAT", "--status", "übernommen")
    assert code == 2 and "kein offener Vorschlag" in result["fehler"]


def test_invalid_proposal_is_rejected(run, analyzed):
    code, result, _ = run("propose", WORKSPACE, "STAT", stdin={**VALID_PROPOSAL, "pii_stufe": "geheim"})
    assert code == 2 and "pii_stufe" in result["fehler"]
    code, result, _ = run("propose", WORKSPACE, "STAT", stdin={**VALID_PROPOSAL, "status": "geprüft"})
    assert code == 2 and "status" in result["fehler"]


def test_plain_string_questions_are_accepted(run, analyzed):
    proposal = {**VALID_PROPOSAL, "offene_fragen": ["Was bedeutet Code 5?"]}
    code, result, _ = run("propose", WORKSPACE, "STAT", stdin=proposal)
    assert code == 0
    assert result["vorschlag"]["offene_fragen"] == [{"frage": "Was bedeutet Code 5?", "ansprechperson": None}]


def test_unknown_column_lists_columns(run, analyzed):
    code, result, _ = run("column", WORKSPACE, "GIBTS_NICHT")
    assert code == 2 and "STAT" in result["fehler"]


def test_column_lookup_is_case_insensitive(run, analyzed):
    assert run("column", WORKSPACE, "stat")[1]["spalte"] == "STAT"


def test_reanalysis_keeps_decisions(run, analyzed):
    run("propose", WORKSPACE, "STAT", stdin=VALID_PROPOSAL)
    run("decide", WORKSPACE, "STAT", "--status", "übernommen")
    _, result, _ = run("analyze", DEMO)
    assert result["fortschritt"]["geprueft"] == 1


def test_datasheet_flow(run, analyzed):
    code, result, _ = run("datasheet", WORKSPACE, stdin={"zweck": "Auftragsverwaltung"})
    assert code == 0 and result["datasheet"]["status"] == "vorgeschlagen"
    run("datasheet", WORKSPACE, stdin={"ansprechperson": "Büro"})
    code, result, _ = run("datasheet", WORKSPACE, "--status", "übernommen")
    assert result["datasheet"]["status"] == "geprüft"
    assert result["datasheet"]["felder"]["zweck"] == "Auftragsverwaltung"
    assert result["datasheet"]["felder"]["ansprechperson"] == "Büro"


def test_datasheet_rejects_unknown_fields(run, analyzed):
    code, result, _ = run("datasheet", WORKSPACE, stdin={"status": "geprüft"})
    assert code == 2


def test_real_entrypoint_speaks_utf8_json(project):
    proc = subprocess.run(
        [sys.executable, "-m", "datadoc", "--root", str(project), "analyze", DEMO],
        capture_output=True, cwd=REPO, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    result = json.loads(proc.stdout.decode("utf-8"))
    assert result["fortschritt"]["text"] == "0 von 11 Spalten geprüft"
