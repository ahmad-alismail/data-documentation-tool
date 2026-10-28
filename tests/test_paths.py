import pytest

from datadoc import paths
from tests.conftest import DEMO


@pytest.mark.parametrize("name", [
    "../geheim.csv", "..\\geheim.csv", "daten/auftraege.csv", "C:\\Windows\\win.ini", "C:geheim.csv",
    "/etc/passwd", "\\\\server\\share\\x.csv", "", "   ", "geheim.txt", "a..b.csv", "x;rm.csv",
])
def test_data_file_rejects_paths_and_wrong_types(project, name):
    with pytest.raises(paths.PathError):
        paths.data_file(project, name)


def test_data_file_accepts_existing_file(project):
    assert paths.data_file(project, DEMO) == (project / "daten" / DEMO).resolve()


def test_missing_file_lists_available(project):
    with pytest.raises(paths.PathError, match=DEMO):
        paths.data_file(project, "fehlt.csv")


@pytest.mark.parametrize("name", ["..", "../x", "a/b", "C:\\x", ""])
def test_workspace_rejects_paths(project, name):
    with pytest.raises(paths.PathError):
        paths.workspace(project, name, create=True)


def test_workspace_requires_analysis(project):
    with pytest.raises(paths.PathError, match="analysieren"):
        paths.workspace(project, "auftraege_handwerksbetrieb")


def test_available_files_only_lists_tables(project):
    assert paths.available_files(project) == [DEMO]


def test_cli_rejects_traversal(run):
    code, result, _ = run("analyze", "..\\..\\Windows\\win.ini")
    assert code == 2 and "nicht erlaubt" in result["fehler"]
