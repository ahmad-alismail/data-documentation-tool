import pandas as pd
import pytest

from datadoc import pii, profile, rules
from tests.conftest import DEMO, VALID_PROPOSAL, WORKSPACE


def findings_of(run, column):
    return run("column", WORKSPACE, column)[1]["befunde"]


def test_generator_is_deterministic(generator):
    assert generator.generate() == generator.generate()


def test_demo_data_has_planted_shape(demo_rows, truth):
    assert len(demo_rows) == truth["zeilen"] == 500
    assert list(demo_rows[0]) == list(truth["spalten"])


def test_rules_find_exactly_the_planted_defects(analyzed, truth):
    found = {(f["regel"], f["spalte"]) for f in analyzed["befunde"]}
    assert found == {tuple(item) for item in truth["erwartete_befunde"]}


def test_finding_details_match_ground_truth(analyzed, run, truth):
    m = truth["maengel"]
    by_rule = {}
    for column in truth["spalten"]:
        for f in findings_of(run, column):
            by_rule[(f["regel"], f["spalte"])] = f

    assert sorted(by_rule[("doppelte_ids", "AUF_NR")]["beispiele"]) == m["doppelte_ids"]
    assert by_rule[("fehlende_werte", "STD")]["anzahl"] == m["fehlende_std"]
    assert by_rule[("ausreisser", "BETR_NETTO")]["beispiele"] == ["48500", "72300"]
    assert by_rule[("ausreisser", "STD")]["beispiele"] == ["999"]
    assert "999" in by_rule[("unplausible_werte", "STD")]["beispiele"]
    assert by_rule[("unplausible_werte", "BETR_NETTO")]["anzahl"] == m["negative_betraege"]
    assert by_rule[("uneinheitliche_kategorien", "ORT")]["anzahl"] == sum(m["ort_varianten"].values())
    assert by_rule[("uneinheitliche_kategorien", "MAT_KAT")]["anzahl"] == sum(m["mat_kat_varianten"].values())
    assert by_rule[("anweisungsaehnlicher_text", "BEM")]["anzahl"] == m["bem_injection"]
    assert by_rule[("pii_verdacht", "BEM")]["anzahl"] == m["bem_mit_telefon"] + m["bem_mit_namen"]
    assert by_rule[("gemischte_datumsformate", "DAT_ERF")]["beispiele"] == ["JJJJ-MM-TT", "TT.MM.JJJJ"]


def test_findings_are_sorted_by_severity_and_explained(analyzed):
    order = [rules.SEVERITY_ORDER[f["schwere"]] for f in analyzed["befunde"]]
    assert order == sorted(order)
    assert all(len(f["erklaerung"]) > 30 for f in analyzed["befunde"])


def test_column_types(analyzed):
    types = {c["spalte"]: c["typ"] for c in analyzed["spalten"]}
    assert types == {
        "AUF_NR": "kennung", "KD_NAME": "text", "KD_TEL": "text", "ORT": "kategorie",
        "DAT_ERF": "datum", "STAT": "kategorie", "BETR_NETTO": "zahl", "STD": "zahl",
        "MAT_KAT": "kategorie", "BEM": "freitext", "X1": "konstant",
    }


def test_coded_values_hint(analyzed, run):
    stat = run("column", WORKSPACE, "STAT")[1]["profil"]
    assert stat["kodiert"] is True
    assert any("Codes" in h and "1, 2, 3, 4" in h for h in stat["hinweise"])
    assert "kodiert" not in run("column", WORKSPACE, "ORT")[1]["profil"]


def build_profile(name, values):
    col_type = profile.classify(name, values)
    return profile.build(name, values, col_type, pii.detect(name, values, col_type), pii.Masker([]), None)


def test_category_profile_lists_every_value_up_to_the_limit():
    values = [f"Lager {i:02d}" for i in range(30)] * 4
    p = build_profile("LAGER", values)
    assert p["erkannter_typ"] == "kategorie"
    assert {v["wert"] for v in p["haeufigste_werte"]} == set(values)
    assert "weitere_werte" not in p


def test_large_category_reports_the_values_left_out():
    values = [f"Lager {i:02d}" for i in range(60)] * 20
    p = build_profile("LAGER", values)
    assert p["erkannter_typ"] == "kategorie"
    assert len(p["haeufigste_werte"]) == profile.CATEGORY_VALUES
    assert p["weitere_werte"] == 10


def test_text_profile_keeps_the_short_list():
    values = [f"Teil {i:03d}" for i in range(100)] * 2
    p = build_profile("TEIL", values)
    assert p["erkannter_typ"] == "text"
    assert len(p["haeufigste_werte"]) == profile.TOP_VALUES
    assert p["weitere_werte"] == 90


@pytest.mark.parametrize("value,expected", [
    ("12", 12.0), ("12,5", 12.5), ("12.5", 12.5), ("1.234,50", 1234.5), ("1,234.50", 1234.5),
    ("-278,29", -278.29), ("A-2026-0001", None), ("14.03.2026", None), ("07131 123456", None),
])
def test_parse_number(value, expected):
    assert profile.parse_number(value) == expected


@pytest.mark.parametrize("value,label", [
    ("2026-03-14", "JJJJ-MM-TT"), ("14.03.2026", "TT.MM.JJJJ"), ("2026-03-14 00:00:00", "JJJJ-MM-TT hh:mm"),
])
def test_parse_date(value, label):
    assert profile.parse_date(value)[0] == label


def make_column(name, values):
    present = [v for v in values if v is not None]
    col_type = profile.classify(name, present)
    return rules.Column(name, values, col_type, pii.detect(name, present, col_type))


def test_duplicate_rows_fixture():
    df = pd.DataFrame({"A": ["1", "2", "2"], "B": ["x", "y", "y"]}, dtype=object)
    assert [f["anzahl"] for f in rules.duplicate_rows(df)] == [1]
    assert rules.duplicate_rows(df.drop_duplicates()) == []


def test_mixed_types_fixture():
    col = make_column("MENGE", ["1", "2", "drei", "4", "fünf", "6", "sieben", "8", "neun", "10"])
    assert col.type == "gemischt"
    assert rules.mixed_types(col)[0]["regel"] == "gemischte_typen"


def test_clean_column_has_no_findings():
    values = [f"{i},50" for i in range(100, 160)]
    col = make_column("PREIS", values)
    masker = pii.Masker([])
    for rule in (rules.outliers, rules.implausible_values, rules.mixed_types, rules.unclear_column_name):
        assert rule(col) == []
    assert rules.missing_values(col, len(values)) == []
    assert rules.constant_column(col, masker) == []


def test_art9_column_is_special_category():
    info = pii.detect("DIAGNOSE_CODE", ["F32", "J45"], "kategorie")
    assert info.stufe == "besondere_kategorie"


def test_follow_up_flag_marks_columns_that_need_the_expert(analyzed, run):
    flagged = {c["spalte"] for c in analyzed["spalten"] if c["rueckfrage"]}
    assert flagged == {"AUF_NR", "ORT", "STAT", "BETR_NETTO", "STD", "MAT_KAT", "X1"}
    stat = run("column", WORKSPACE, "STAT")[1]["rueckfrage"]
    assert stat["empfohlen"] and stat["gruende"][0] == "Die Werte sind Codes"
    assert run("column", WORKSPACE, "KD_NAME")[1]["rueckfrage"] == {"empfohlen": False, "gruende": []}
    assert analyzed["reihenfolge"]["danach_schnellmodus"] == ["KD_NAME", "KD_TEL", "DAT_ERF", "BEM"]
    assert analyzed["reihenfolge"]["nur_bestaetigen"] == []


def test_order_on_resume_skips_checked_and_only_confirms_proposed_columns(analyzed, run):
    run("propose", WORKSPACE, "STAT", stdin=VALID_PROPOSAL)
    run("decide", WORKSPACE, "STAT", "--status", "übernommen")
    run("propose", WORKSPACE, "KD_NAME", stdin={**VALID_PROPOSAL, "lesbarer_name": "Kundenname", "fachlicher_typ": "name"})
    reihenfolge = run("analyze", DEMO)[1]["reihenfolge"]
    assert reihenfolge["nur_bestaetigen"] == ["KD_NAME"]
    assert "STAT" not in reihenfolge["zuerst_einzeln_mit_rueckfrage"]
    assert "KD_NAME" not in reihenfolge["danach_schnellmodus"]
