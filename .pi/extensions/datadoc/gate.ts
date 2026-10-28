/**
 * Pure security and parsing logic of the datadoc extension (no Pi imports, testable with `node --test`).
 */

export const ERLAUBTE_WERKZEUGE = [
	"datensatz_analysieren",
	"spalte_ansehen",
	"vorschlag_speichern",
	"vorschlag_bestaetigen",
	"datasheet_speichern",
	"dokumentation_exportieren",
	"wissen_laden",
] as const;

export const WISSEN_THEMEN = ["datasheet-erstellen", "pii-einstufung", "befunde-erklaeren"] as const;
export const FACHLICHE_TYPEN = [
	"kennung", "kategorie", "freitext", "datum", "geldbetrag", "menge", "name", "kontaktdaten", "ort", "sonstiges",
] as const;
export const PII_STUFEN = ["keine", "personenbezogen", "besondere_kategorie"] as const;
export const KONFIDENZEN = ["hoch", "mittel", "niedrig"] as const;
export const DATASHEET_FELDER = ["zweck", "erhebung", "aktualisierung", "weitergabe", "einschraenkungen", "ansprechperson"] as const;

export type Pruefung = { ok: true } | { ok: false; grund: string };

const OK: Pruefung = { ok: true };
const abgelehnt = (grund: string): Pruefung => ({ ok: false, grund });

export function pruefeDateiname(name: unknown): Pruefung {
	if (typeof name !== "string" || !name.trim()) return abgelehnt("Es wurde kein Dateiname angegeben.");
	if (name.includes("..") || /[\\/:]/.test(name) || name.startsWith("~")) {
		return abgelehnt(`'${name}' ist kein einfacher Dateiname. Erlaubt sind nur Dateien direkt im Ordner daten/.`);
	}
	if (!/\.(csv|xlsx)$/i.test(name)) return abgelehnt("Nur .csv- und .xlsx-Dateien können analysiert werden.");
	if (!/^[\p{L}\p{N}_][\p{L}\p{N}_ .()-]*$/u.test(name)) return abgelehnt(`'${name}' enthält unzulässige Zeichen.`);
	return OK;
}

/** Decision of the tool_call gate. Everything not explicitly allowed is blocked. */
export function pruefeAufruf(werkzeug: string, eingabe: Record<string, unknown> | undefined): Pruefung {
	if (!(ERLAUBTE_WERKZEUGE as readonly string[]).includes(werkzeug)) {
		return abgelehnt(`Das Werkzeug '${werkzeug}' ist in diesem Assistenten nicht freigegeben.`);
	}
	if (werkzeug === "datensatz_analysieren") return pruefeDateiname(eingabe?.datei);
	return OK;
}

/** Accept "STAT", "STAT, ORT" or ["STAT"] for a list of column names. */
export function alsSpaltenliste(wert: unknown): string[] {
	const roh = Array.isArray(wert) ? wert : typeof wert === "string" ? wert.split(",") : [];
	return [...new Set(roh.filter((s): s is string => typeof s === "string").map((s) => s.trim()).filter(Boolean))];
}

/** Accept open questions as plain strings or objects. */
export function alsOffeneFragen(wert: unknown): { frage: string; ansprechperson?: string }[] | undefined {
	if (wert === undefined || wert === null) return undefined;
	const liste = Array.isArray(wert) ? wert : [wert];
	return liste
		.map((f) => (typeof f === "string" ? { frage: f } : f))
		.filter((f): f is { frage: string; ansprechperson?: string } => typeof f?.frage === "string" && f.frage.trim() !== "");
}

// Values small models send instead of the German enum values. Ambiguous ones (e.g. "unknown") stay unmapped.
const ENUM_SYNONYME: Record<string, { erlaubt: readonly string[]; synonyme: Record<string, string> }> = {
	pii_stufe: {
		erlaubt: PII_STUFEN,
		synonyme: {
			none: "keine", no: "keine", nein: "keine", kein: "keine", nicht_pii: "keine", not_pii: "keine", no_pii: "keine",
			"n/a": "keine", "0": "keine", false: "keine",
			pii: "personenbezogen", ja: "personenbezogen", yes: "personenbezogen", personal: "personenbezogen", "1": "personenbezogen", true: "personenbezogen",
			art9: "besondere_kategorie", "art._9": "besondere_kategorie", besonders: "besondere_kategorie", special: "besondere_kategorie", sensitive: "besondere_kategorie",
		},
	},
	konfidenz: { erlaubt: KONFIDENZEN, synonyme: { high: "hoch", medium: "mittel", mid: "mittel", low: "niedrig", gering: "niedrig" } },
	fachlicher_typ: {
		erlaubt: FACHLICHE_TYPEN,
		synonyme: {
			id: "kennung", identifier: "kennung", nummer: "kennung", category: "kategorie", status: "kategorie", text: "freitext",
			date: "datum", money: "geldbetrag", betrag: "geldbetrag", amount: "geldbetrag", number: "menge", anzahl: "menge",
			quantity: "menge", kontakt: "kontaktdaten", contact: "kontaktdaten", telefon: "kontaktdaten", location: "ort", other: "sonstiges",
		},
	},
};

/** Map case variants and common synonyms of enum fields onto the allowed values; leave everything else untouched. */
export function normalisiereEnums(args: Record<string, unknown>): Record<string, unknown> {
	for (const [feld, { erlaubt, synonyme }] of Object.entries(ENUM_SYNONYME)) {
		if (typeof args[feld] !== "string") continue;
		const schluessel = (args[feld] as string).trim().toLowerCase().replace(/[\s-]+/g, "_");
		if (erlaubt.includes(schluessel)) args[feld] = schluessel;
		else if (synonyme[schluessel]) args[feld] = synonyme[schluessel];
	}
	return args;
}

export type OffeneFrage ={ frage: string; ansprechperson?: string | null };
export type Vorschlag = {
	beschreibung: string;
	lesbarer_name: string;
	fachlicher_typ: string;
	einheit?: string | null;
	wertebereich?: string | null;
	pii_stufe: string;
	konfidenz: string;
	offene_fragen?: OffeneFrage[];
};

export type Spaltenansicht = {
	spalte: string;
	vorschlag?: Vorschlag | null;
	rueckfrage?: { empfohlen: boolean };
};

/** Quick mode only for clear columns: not low confidence, no open questions, no follow-up question recommended by the analysis. */
export function istEindeutig(a: Spaltenansicht): boolean {
	const v = a.vorschlag;
	if (!v || v.konfidenz === "niedrig" || (v.offene_fragen?.length ?? 0) > 0) return false;
	return !a.rueckfrage?.empfohlen;
}

const VORSCHLAG_FELDER =["lesbarer_name", "beschreibung", "fachlicher_typ", "einheit", "wertebereich", "pii_stufe", "konfidenz"] as const;

/** Editor text for the "Bearbeiten" dialog: one `feld: wert` per line, open questions as `offene_frage: Frage | Ansprechperson`. */
export function vorschlagAlsText(v: Vorschlag): string {
	const zeilen = [
		"# Werte nach dem Doppelpunkt ändern. Zeilen mit # werden ignoriert.",
		`# fachlicher_typ: ${FACHLICHE_TYPEN.join(", ")}`,
		`# pii_stufe: ${PII_STUFEN.join(", ")} · konfidenz: ${KONFIDENZEN.join(", ")}`,
		"# offene_frage: Frage | Ansprechperson (Zeile löschen = Frage entfernen)",
		...VORSCHLAG_FELDER.map((feld) => `${feld}: ${v[feld] ?? ""}`),
		...(v.offene_fragen ?? []).map((f) => `offene_frage: ${f.frage}${f.ansprechperson ? ` | ${f.ansprechperson}` : ""}`),
	];
	return zeilen.join("\n");
}

export function datasheetAlsText(felder: Record<string, string | null | undefined>): string {
	return [
		"# Werte nach dem Doppelpunkt ändern. Zeilen mit # werden ignoriert.",
		...DATASHEET_FELDER.map((feld) => `${feld}: ${felder[feld] ?? ""}`),
	].join("\n");
}

export type Bearbeitung = { ok: true; felder: Record<string, unknown> } | { ok: false; fehler: string };

/** Parse the edited text back into fields. Unknown keys are rejected; empty values clear optional fields. */
export function parseBearbeitung(text: string, erlaubt: readonly string[], mitFragen: boolean): Bearbeitung {
	const felder: Record<string, unknown> = {};
	const fragen: OffeneFrage[] = [];
	for (const roh of text.split(/\r?\n/)) {
		const zeile = roh.trim();
		if (!zeile || zeile.startsWith("#")) continue;
		const trenner = zeile.indexOf(":");
		if (trenner < 1) return { ok: false, fehler: `Zeile ohne 'feld: wert': ${zeile}` };
		const feld = zeile.slice(0, trenner).trim();
		const wert = zeile.slice(trenner + 1).trim();
		if (mitFragen && feld === "offene_frage") {
			const [frage, person] = wert.split("|").map((t) => t.trim());
			if (frage) fragen.push({ frage, ansprechperson: person || null });
			continue;
		}
		if (!erlaubt.includes(feld)) return { ok: false, fehler: `Unbekanntes Feld '${feld}'. Erlaubt: ${erlaubt.join(", ")}.` };
		felder[feld] = wert === "" ? null : wert;
	}
	if (mitFragen) felder.offene_fragen = fragen;
	return { ok: true, felder };
}

export function parseVorschlagBearbeitung(text: string): Bearbeitung {
	return parseBearbeitung(text, VORSCHLAG_FELDER, true);
}

export function parseDatasheetBearbeitung(text: string): Bearbeitung {
	return parseBearbeitung(text, DATASHEET_FELDER, false);
}

/** Strip YAML frontmatter from a SKILL.md file. */
export function ohneFrontmatter(text: string): string {
	return text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim();
}
