import pytest
from openpyxl import Workbook

from datadoc import loader


def test_cp1252_semicolon_csv(tmp_path):
    path = tmp_path / "alt.csv"
    path.write_bytes("Ort;Menge\nMünchen;1,5\nKöln;\n".encode("cp1252"))
    table = loader.load(path)
    assert table.meta["kodierung"] == "cp1252" and table.meta["trennzeichen"] == ";"
    assert table.df["Ort"].tolist() == ["München", "Köln"]
    assert table.df["Menge"].tolist() == ["1,5", None]


def test_comma_csv_and_na_tokens(tmp_path):
    path = tmp_path / "en.csv"
    path.write_text("a,b\n1,NULL\n2,n/a\n3,x\n", encoding="utf-8")
    table = loader.load(path)
    assert table.meta["trennzeichen"] == ","
    assert table.df["b"].tolist() == [None, None, "x"]


def test_xlsx_sheet_selection(tmp_path):
    path = tmp_path / "mappe.xlsx"
    workbook = Workbook()
    workbook.active.title = "Eins"
    workbook.active.append(["A"])
    workbook.active.append(["x"])
    second = workbook.create_sheet("Zwei")
    second.append(["B"])
    second.append([42])
    workbook.save(path)

    first = loader.load(path)
    assert first.meta["tabellenblatt"] == "Eins" and first.meta["hinweise"]
    assert loader.load(path, "Zwei").df["B"].tolist() == ["42"]
    with pytest.raises(loader.LoadError, match="Eins, Zwei"):
        loader.load(path, "Drei")


def test_size_limit(tmp_path, monkeypatch):
    path = tmp_path / "gross.csv"
    path.write_text("a\n" + "1\n" * 100, encoding="utf-8")
    monkeypatch.setattr(loader, "MAX_BYTES", 50)
    with pytest.raises(loader.LoadError, match="höchstens"):
        loader.load(path)


def test_sampling_above_row_limit(tmp_path, monkeypatch):
    path = tmp_path / "lang.csv"
    path.write_text("a\n" + "".join(f"{i}\n" for i in range(25)), encoding="utf-8")
    monkeypatch.setattr(loader, "MAX_ROWS", 10)
    table = loader.load(path)
    assert table.meta["stichprobe"] and table.meta["zeilen_gesamt"] == 25 and len(table.df) == 10
    assert "stichprobe" in table.meta["hinweise"][0].lower()
