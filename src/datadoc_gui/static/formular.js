// Pure helpers for the dialogs: turn the editor text of the extension (`feld: wert` lines, see
// vorschlagAlsText/datasheetAlsText in .pi/extensions/datadoc/gate.ts) into form fields and back,
// and split dialog titles into displayable parts. No DOM access, so node --test can import it.
// The extension stays the authority: it parses and validates whatever text comes back.

export const FRAGE = "offene_frage";

// Value lists must equal FACHLICHE_TYPEN, PII_STUFEN and KONFIDENZEN in gate.ts (checked by a test).
export const FELDER = {
	lesbarer_name: { label: "Name", art: "text" },
	beschreibung: { label: "Bedeutung", art: "mehrzeilig" },
	fachlicher_typ: {
		label: "Fachlicher Typ",
		art: "auswahl",
		werte: ["kennung", "kategorie", "freitext", "datum", "geldbetrag", "menge", "name", "kontaktdaten", "ort", "sonstiges"],
	},
	einheit: { label: "Einheit", art: "text" },
	wertebereich: { label: "Wertebereich", art: "text" },
	pii_stufe: { label: "Personenbezug", art: "auswahl", werte: ["keine", "personenbezogen", "besondere_kategorie"] },
	konfidenz: { label: "Sicherheit des Vorschlags", art: "auswahl", werte: ["hoch", "mittel", "niedrig"] },
	zweck: { label: "Wofür werden die Daten genutzt?", art: "mehrzeilig" },
	erhebung: { label: "Wie und in welchem System entstehen die Daten?", art: "mehrzeilig" },
	aktualisierung: { label: "Wer pflegt die Daten und wie oft?", art: "mehrzeilig" },
	weitergabe: { label: "Dürfen die Daten weitergegeben werden, an wen?", art: "mehrzeilig" },
	einschraenkungen: { label: "Bekannte Lücken, Fehler oder Einschränkungen", art: "mehrzeilig" },
	ansprechperson: { label: "Ansprechperson für Fragen zu den Daten", art: "text" },
};

/** Parse editor text into a form, or return null if any line is not `feld: wert` (then the page shows a text area). */
export function parseFormular(text) {
	const kommentare = [];
	const felder = [];
	const fragen = [];
	for (const roh of String(text).split(/\r?\n/)) {
		const zeile = roh.trim();
		if (!zeile) continue;
		if (zeile.startsWith("#")) {
			kommentare.push(zeile);
			continue;
		}
		const trenner = zeile.indexOf(":");
		if (trenner < 1) return null;
		const schluessel = zeile.slice(0, trenner).trim();
		const wert = zeile.slice(trenner + 1).trim();
		if (schluessel === FRAGE) {
			const [frage, ansprechperson = ""] = wert.split("|").map((t) => t.trim());
			fragen.push({ frage, ansprechperson });
		} else {
			felder.push({ schluessel, wert });
		}
	}
	if (!felder.length && !fragen.length) return null;
	// Column proposals carry open questions (possibly none yet); the datasheet does not.
	const mitFragen = fragen.length > 0 || felder.some((f) => f.schluessel === "fachlicher_typ");
	return { kommentare, felder, fragen, mitFragen };
}

const einzeilig = (wert) => String(wert ?? "").replace(/\s*\r?\n\s*/g, " ").trim();

/** Serialize the form back into editor text. Line breaks become spaces, `|` is removed from questions. */
export function serialisiereFormular({ felder, fragen = [], mitFragen = false }, kommentare = []) {
	const zeilen = [...kommentare, ...felder.map((f) => `${f.schluessel}: ${einzeilig(f.wert)}`)];
	if (mitFragen) {
		for (const f of fragen) {
			const frage = einzeilig(f.frage).replace(/\s*\|\s*/g, " ");
			const person = einzeilig(f.ansprechperson).replace(/\s*\|\s*/g, " ");
			if (frage) zeilen.push(`${FRAGE}: ${frage}${person ? ` | ${person}` : ""}`);
		}
	}
	return zeilen.join("\n");
}

const PAAR = /^([^:·]{1,40}):\s(.*)$/;

/**
 * Split a dialog title into heading and blocks: indented `Key: value` lines (several per line,
 * separated by " · ") become pairs, `• …` lines become list items, everything else is text.
 */
export function parseDialogTitel(titel) {
	const [ueberschrift = "", ...rest] = String(titel).replace(/\r\n?/g, "\n").split("\n");
	const bloecke = [];
	const block = (art) => {
		const letzter = bloecke[bloecke.length - 1];
		if (letzter?.art === art) return letzter;
		const neu = { art, eintraege: [] };
		bloecke.push(neu);
		return neu;
	};
	for (const roh of rest) {
		if (!roh.trim()) continue;
		if (/^\s+\S/.test(roh) && PAAR.test(roh.trim())) {
			const eintraege = block("paare").eintraege;
			for (const teil of roh.trim().split(" · ")) {
				const m = teil.match(PAAR);
				if (m) eintraege.push([FELDER[m[1].trim()]?.label ?? m[1].trim(), m[2].trim()]);
				else eintraege[eintraege.length - 1][1] += ` · ${teil}`;
			}
		} else if (/^\s*•\s/.test(roh)) {
			block("liste").eintraege.push(roh.replace(/^\s*•\s/, "").trim());
		} else {
			block("text").eintraege.push(roh.trim());
		}
	}
	return { ueberschrift, bloecke };
}
