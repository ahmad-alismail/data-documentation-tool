import csv
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from datadoc import cli

REPO = Path(__file__).resolve().parent.parent
DEMO = "auftraege_handwerksbetrieb.csv"
WORKSPACE = "auftraege_handwerksbetrieb"


def load_generator():
    spec = importlib.util.spec_from_file_location("make_demo_data", REPO / "scripts" / "make_demo_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def generator():
    return load_generator()


@pytest.fixture
def project(tmp_path, generator):
    """Fresh project root with the generated demo data in daten/."""
    rows, truth = generator.generate()
    data = tmp_path / "daten"
    data.mkdir()
    with (data / DEMO).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    (data / "ground_truth.json").write_text(json.dumps(truth, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.fixture(scope="session")
def demo_rows(generator):
    rows, _ = generator.generate()
    return rows


@pytest.fixture(scope="session")
def truth(generator):
    return generator.generate()[1]


class Runner:
    """Calls the CLI in-process and returns (exit code, parsed JSON, raw stdout)."""

    def __init__(self, root: Path, monkeypatch, capsys):
        self.root, self.monkeypatch, self.capsys = root, monkeypatch, capsys
        self.outputs: list[str] = []

    def __call__(self, *args: str, stdin: dict | str | None = None):
        payload = stdin if isinstance(stdin, str) else json.dumps(stdin or {}, ensure_ascii=False)
        self.monkeypatch.setattr(sys, "stdin", io.StringIO(payload if stdin is not None else ""))
        code = cli.main(["--root", str(self.root), *args])
        out = self.capsys.readouterr().out
        self.outputs.append(out)
        return code, json.loads(out), out


@pytest.fixture
def run(project, monkeypatch, capsys):
    return Runner(project, monkeypatch, capsys)


@pytest.fixture
def analyzed(run):
    code, result, _ = run("analyze", DEMO)
    assert code == 0, result
    return result


VALID_PROPOSAL = {
    "beschreibung": "Status des Auftrags: 1 = angefragt, 2 = beauftragt, 3 = in Arbeit, 4 = abgerechnet.",
    "lesbarer_name": "Auftragsstatus",
    "fachlicher_typ": "kategorie",
    "wertebereich": "1–4",
    "pii_stufe": "keine",
    "konfidenz": "hoch",
}
