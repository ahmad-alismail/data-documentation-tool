import assert from "node:assert/strict";
import { test } from "node:test";
import {
	alsOffeneFragen,
	istEindeutig,
	normalisiereEnums,
	alsSpaltenliste,
	ohneFrontmatter,
	parseDatasheetBearbeitung,
	parseVorschlagBearbeitung,
	pruefeAufruf,
	pruefeDateiname,
	vorschlagAlsText,
} from "./gate.ts";

test("only the seven assistant tools pass the gate", () => {
	for (const name of ["read", "bash", "powershell", "write", "edit", "grep", "find", "ls", "codemode", "tool_search", "mcp__x__y"]) {
		assert.equal(pruefeAufruf(name, {}).ok, false, name);
	}
	assert.equal(pruefeAufruf("spalte_ansehen", { spalte: "STAT" }).ok, true);
	assert.equal(pruefeAufruf("wissen_laden", { thema: "pii-einstufung" }).ok, true);
});

test("paths outside daten/ are blocked", () => {
	for (const name of [
		"..\\..\\Windows\\win.ini", "../geheim.csv", "C:\\Windows\\win.ini", "C:geheim.csv", "/etc/passwd",
		"daten/x.csv", "~/x.csv", "x.txt", "", "a;b.csv", undefined, 42,
	]) {
		assert.equal(pruefeDateiname(name).ok, false, String(name));
	}
	assert.equal(pruefeDateiname("auftraege_handwerksbetrieb.csv").ok, true);
	assert.equal(pruefeDateiname("Übersicht 2026 (final).xlsx").ok, true);
	assert.equal(pruefeAufruf("datensatz_analysieren", { datei: "../x.csv" }).ok, false);
});

test("column lists accept small-model variants", () => {
	assert.deepEqual(alsSpaltenliste("STAT"), ["STAT"]);
	assert.deepEqual(alsSpaltenliste("STAT, ORT,STAT"), ["STAT", "ORT"]);
	assert.deepEqual(alsSpaltenliste(["X1", " ", 3]), ["X1"]);
	assert.deepEqual(alsOffeneFragen("Was ist X?"), [{ frage: "Was ist X?" }]);
	assert.deepEqual(alsOffeneFragen([{ frage: "A?", ansprechperson: "Einkauf" }, ""]), [{ frage: "A?", ansprechperson: "Einkauf" }]);
});

test("proposal editor text round-trips", () => {
	const vorschlag = {
		beschreibung: "Materialkategorie", lesbarer_name: "Material", fachlicher_typ: "kategorie",
		einheit: null, wertebereich: "Elektro, Sanitär", pii_stufe: "keine", konfidenz: "mittel",
		offene_fragen: [{ frage: "Welche Schreibweise gilt?", ansprechperson: "Einkauf" }],
	};
	const text = vorschlagAlsText(vorschlag).replace("lesbarer_name: Material", "lesbarer_name: Materialgruppe");
	const result = parseVorschlagBearbeitung(text);
	assert.ok(result.ok);
	assert.equal(result.felder.lesbarer_name, "Materialgruppe");
	assert.equal(result.felder.einheit, null);
	assert.deepEqual(result.felder.offene_fragen, [{ frage: "Welche Schreibweise gilt?", ansprechperson: "Einkauf" }]);
});

test("editor rejects unknown fields such as a status", () => {
	const result = parseVorschlagBearbeitung("status: geprüft");
	assert.equal(result.ok, false);
	assert.equal(parseDatasheetBearbeitung("zweck: Abrechnung").ok, true);
});

test("frontmatter is stripped from skills", () => {
	assert.equal(ohneFrontmatter("---\nname: x\ndescription: y\n---\n# Titel\nText"), "# Titel\nText");
});

test("quick mode only takes clear columns", () => {
	const vorschlag = { beschreibung: "Ort", lesbarer_name: "Ort", fachlicher_typ: "ort", pii_stufe: "keine", konfidenz: "hoch" };
	assert.equal(istEindeutig({ spalte: "ORT", vorschlag }), true);
	assert.equal(istEindeutig({ spalte: "ORT", vorschlag: { ...vorschlag, konfidenz: "mittel" } }), true);
	assert.equal(istEindeutig({ spalte: "ORT", vorschlag: { ...vorschlag, konfidenz: "niedrig" } }), false);
	assert.equal(istEindeutig({ spalte: "MAT_KAT", vorschlag: { ...vorschlag, offene_fragen: [{ frage: "Was?" }] } }), false);
	assert.equal(istEindeutig({ spalte: "STAT", vorschlag, rueckfrage: { empfohlen: true } }), false);
	assert.equal(istEindeutig({ spalte: "KD_NAME", vorschlag, rueckfrage: { empfohlen: false } }), true);
	assert.equal(istEindeutig({ spalte: "X", vorschlag: null }), false);
});

test("enum synonyms from small models are normalized, ambiguous ones are kept", () => {
	for (const [eingabe, erwartet] of [["none", "keine"], ["N/A", "keine"], ["nicht_PII", "keine"], ["PII", "personenbezogen"], ["Besondere Kategorie", "besondere_kategorie"], ["unknown", "unknown"]]) {
		assert.equal(normalisiereEnums({ pii_stufe: eingabe }).pii_stufe, erwartet, eingabe);
	}
	assert.deepEqual(normalisiereEnums({ konfidenz: "High", fachlicher_typ: "Datum" }), { konfidenz: "hoch", fachlicher_typ: "datum" });
});
