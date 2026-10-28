// DOM wiring of the GUI. All text from the model or the data is set via textContent or rendered
// by the escape-first renderer in markdown.js; nothing else goes through innerHTML.

import { FELDER, parseDialogTitel, parseFormular, serialisiereFormular } from "./formular.js";
import { ICONS } from "./icons.js";
import { renderMarkdown } from "./markdown.js";

const $ = (id) => document.getElementById(id);
const MAX_BYTES = 50 * 1024 * 1024;
const STATUS_TEXTE = { offen: "offen", vorgeschlagen: "Vorschlag", "geprüft": "geprüft", verworfen: "verworfen" };
// Cycle order of the theme switch; thema.js applies the stored choice before the first paint.
const THEMEN = {
	system: { symbol: "monitor", text: "wie das System", naechstes: "hell" },
	hell: { symbol: "sun", text: "hell", naechstes: "dunkel" },
	dunkel: { symbol: "moon", text: "dunkel", naechstes: "system" },
};
const ZAHL = new Intl.NumberFormat("de-DE");

let zustand = null;
let dateien = [];
let arbeitsstand = {};
let gezeigteNachrichten = 0;
let gezeigterDialog = null;
let liveElement = null;
const offeneSpalten = new Set();

function neu(tag, klasse, text) {
	const element = document.createElement(tag);
	if (klasse) element.className = klasse;
	if (text !== undefined) element.textContent = text;
	return element;
}

const SVG = "http://www.w3.org/2000/svg";

function ikon(name) {
	const svg = document.createElementNS(SVG, "svg");
	const attribute = {
		class: "ikon", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.75",
		"stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false",
	};
	for (const [k, v] of Object.entries(attribute)) svg.setAttribute(k, v);
	if (!ICONS[name]) throw new Error(`Unbekanntes Icon: ${name}`);
	for (const [tag, attrs] of ICONS[name]) {
		const teil = document.createElementNS(SVG, tag);
		for (const [k, v] of Object.entries(attrs)) teil.setAttribute(k, v);
		svg.append(teil);
	}
	return svg;
}

function knopf(text, klasse, aktion, symbol) {
	const b = neu("button", `knopf ${klasse ?? ""}`.trim(), text);
	b.type = "button";
	if (symbol) b.prepend(symbol);
	b.addEventListener("click", aktion);
	return b;
}

function markdown(text) {
	const element = neu("div", "md");
	element.innerHTML = renderMarkdown(text);
	return element;
}

function toast(text, art = "info") {
	const t = neu("div", `toast ${art}`, text);
	$("toasts").append(t);
	setTimeout(() => t.remove(), 6000);
}

async function api(pfad, daten = {}) {
	const r = await fetch(pfad, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(daten) });
	const antwort = await r.json().catch(() => ({}));
	if (!r.ok) throw new Error(antwort.fehler || `Fehler ${r.status}`);
	return antwort;
}

async function versuche(aktion) {
	try {
		return await aktion();
	} catch (fehler) {
		toast(fehler.message, "fehler");
	}
}

// ---- Modal (instead of native alert/confirm) --------------------------------------------

function modal(titel, inhalt, knoepfe = []) {
	$("modal-titel").textContent = titel;
	$("modal-text").replaceChildren(inhalt);
	$("modal-knoepfe").replaceChildren(...knoepfe);
	$("modal").hidden = false;
	(knoepfe[0] ?? $("modal-zu")).focus();
}

const schliesseModal = () => {
	$("modal").hidden = true;
};

function bestaetige(titel, text, ja) {
	return new Promise((fertig) => {
		const antworte = (wert) => () => {
			schliesseModal();
			fertig(wert);
		};
		modal(titel, neu("p", "", text), [knopf(ja, "", antworte(true)), knopf("Abbrechen", "zweitrangig", antworte(false))]);
	});
}

// ---- Events from the server ---------------------------------------------------------------

function verbinden() {
	const quelle = new EventSource("/api/ereignisse");
	quelle.onmessage = (nachricht) => verarbeite(JSON.parse(nachricht.data));
	quelle.onopen = () => $("status").classList.remove("getrennt");
	quelle.onerror = async () => {
		$("status").classList.add("getrennt");
		const r = await fetch("/api/dateien").catch(() => null);
		if (r?.status === 403) {
			quelle.close();
			zeigeAbgemeldet();
		}
	};
}

function zeigeAbgemeldet() {
	const hinweis = neu("main", "abgemeldet");
	hinweis.append(
		neu("h1", "", "Kein Zugriff"),
		neu("p", "", "Bitte die Oberfläche über die Adresse aus dem Startfenster neu öffnen (start.ps1 -Gui)."),
	);
	document.body.replaceChildren(hinweis);
}

function verarbeite(e) {
	if (e.typ === "zustand") {
		zustand = e.zustand;
		zeichne();
	} else if (e.typ === "delta" && zustand) {
		zustand.live += e.text;
		zeichneLive();
	} else if (e.typ === "hinweis") {
		toast(e.text, e.art);
	} else if (e.typ === "stand") {
		ladeStand();
		ladeDateien();
	}
}

// ---- Rendering of the state -------------------------------------------------------------

function nahAmEnde() {
	const v = $("verlauf");
	return v.scrollHeight - v.scrollTop - v.clientHeight < 120;
}

function zumEnde() {
	const v = $("verlauf");
	v.scrollTop = v.scrollHeight;
}

function zeichne() {
	const z = zustand;
	const folgen = nahAmEnde();
	$("fehlerbanner").hidden = !z.fehler;
	$("fehlertext").textContent = z.fehler ?? "";
	$("status").textContent = Object.values(z.status).join(" · ");
	zeichneKontext();
	zeichneModelle();
	zeichneNachrichten();
	zeichneLive();
	zeichneDialog();

	const sperre = z.laufend || Boolean(z.fehler);
	$("arbeitet").hidden = !z.laufend || Boolean(z.dialog);
	$("arbeitet-text").textContent = z.aktivitaet ? `${z.aktivitaet} …` : "Der Assistent denkt nach …";
	$("text").disabled = sperre;
	$("senden").hidden = z.laufend;
	$("senden").disabled = sperre;
	$("stopp").hidden = !z.laufend;
	$("neu").disabled = Boolean(z.fehler);
	zeichneDateien();
	if (folgen) zumEnde();
}

function zeichneKontext() {
	const k = zustand.kontext; // Pi's contextUsage; tokens and percent are null right after a compaction
	$("kontext").hidden = !k;
	if (!k) return;
	const prozent = typeof k.percent === "number" ? Math.round(k.percent) : null;
	$("kontext-wert").style.width = `${Math.min(prozent ?? 0, 100)}%`;
	$("kontext-wert").parentElement.setAttribute("aria-valuenow", String(prozent ?? 0));
	$("kontext-text").textContent = prozent === null ? "–" : `${prozent} %`;
	$("kontext").title =
		prozent === null
			? "Das Gespräch wurde gerade zusammengefasst. Der neue Wert erscheint nach der nächsten Antwort."
			: `${ZAHL.format(k.tokens)} von ${ZAHL.format(k.contextWindow)} Tokens im Kontextfenster des Modells`;
}

function setzeThema(thema) {
	if (thema === "system") delete document.documentElement.dataset.thema;
	else document.documentElement.dataset.thema = thema;
	try {
		if (thema === "system") localStorage.removeItem("thema");
		else localStorage.setItem("thema", thema);
	} catch {
		// Storage blocked: the choice holds until the page is reloaded.
	}
	const { symbol, text } = THEMEN[thema];
	const knopfThema = $("thema");
	knopfThema.replaceChildren(ikon(symbol));
	knopfThema.title = `Darstellung: ${text} (klicken zum Wechseln)`;
	knopfThema.setAttribute("aria-label", knopfThema.title);
}

function zeichneModelle() {
	const auswahl = $("modell");
	const schluessel = (m) => `${m.provider}/${m.id}`;
	const signatur = zustand.modelle.map(schluessel).join("|");
	if (auswahl.dataset.signatur !== signatur) {
		auswahl.replaceChildren(
			...zustand.modelle.map((m) => {
				const option = neu("option", "", m.name);
				option.value = schluessel(m);
				return option;
			}),
		);
		auswahl.dataset.signatur = signatur;
	}
	if (zustand.modell) auswahl.value = schluessel(zustand.modell);
	auswahl.disabled = zustand.laufend || Boolean(zustand.fehler) || !zustand.modelle.length;
}

function nachrichtElement(n) {
	if (n.rolle === "assistent") {
		const blase = neu("div", "nachricht assistent");
		blase.append(markdown(n.text));
		return blase;
	}
	if (n.rolle === "nutzer") return neu("div", "nachricht nutzer", n.text);
	return neu("div", `nachricht hinweis ${n.art ?? "info"}`, n.text);
}

function zeichneNachrichten() {
	const verlauf = $("verlauf");
	const liste = zustand.nachrichten;
	if (liste.length < gezeigteNachrichten) {
		verlauf.querySelectorAll(".nachricht").forEach((n) => n.remove());
		gezeigteNachrichten = 0;
	}
	liveElement?.remove();
	liveElement = null;
	for (const n of liste.slice(gezeigteNachrichten)) verlauf.append(nachrichtElement(n));
	gezeigteNachrichten = liste.length;
	$("leer").hidden = liste.length > 0;
}

function zeichneLive() {
	if (!zustand.live) {
		liveElement?.remove();
		liveElement = null;
		return;
	}
	const folgen = nahAmEnde();
	if (!liveElement) {
		liveElement = neu("div", "nachricht assistent live");
		$("verlauf").append(liveElement);
	}
	liveElement.replaceChildren(markdown(zustand.live));
	$("leer").hidden = true;
	if (folgen) zumEnde();
}

// ---- Dialogs ------------------------------------------------------------------------------

function antworte(antwort) {
	const id = zustand.dialog?.id;
	return versuche(() => api("/api/dialog", { id, ...antwort }));
}

function zeichneDialog() {
	const d = zustand.dialog;
	if ((d?.id ?? null) === gezeigterDialog) return;
	gezeigterDialog = d?.id ?? null;
	const bereich = $("dialog");
	if (!d) {
		bereich.replaceChildren();
		return;
	}
	const karte = neu("div", "dialogkarte");
	const darstellung = { select: auswahlDialog, editor: editorDialog, confirm: bestaetigungsDialog, input: eingabeDialog }[d.methode];
	karte.append(...darstellung(d));
	bereich.replaceChildren(karte);
	karte.scrollIntoView({ block: "nearest" });
	karte.querySelector("button, input, textarea, select")?.focus({ preventScroll: true });
}

function titelElemente(titel) {
	const { ueberschrift, bloecke } = parseDialogTitel(titel);
	const teile = [neu("h3", "", ueberschrift)];
	for (const block of bloecke) {
		if (block.art === "paare") {
			const dl = neu("dl", "paare");
			for (const [schluessel, wert] of block.eintraege) dl.append(neu("dt", "", schluessel), neu("dd", "", wert));
			teile.push(dl);
		} else if (block.art === "liste") {
			const ul = neu("ul", "punkte-liste");
			for (const eintrag of block.eintraege) {
				const li = neu("li");
				const trenner = eintrag.indexOf(":");
				if (trenner > 0) li.append(neu("strong", "", eintrag.slice(0, trenner + 1)), ` ${eintrag.slice(trenner + 1).trim()}`);
				else li.textContent = eintrag;
				ul.append(li);
			}
			teile.push(ul);
		} else {
			for (const zeile of block.eintraege) teile.push(neu("p", "", zeile));
		}
	}
	return teile;
}

function auswahlDialog(d) {
	const knoepfe = neu("div", "knoepfe");
	for (const option of d.optionen) {
		const [klasse, symbol] = /übernehmen/i.test(option)
			? ["", ikon("check")]
			: /verwerfen/i.test(option)
				? ["gefahr-rahmen", ikon("x")]
				: /abbrechen/i.test(option)
					? ["link"]
					: ["zweitrangig", /bearbeiten/i.test(option) ? ikon("pencil") : undefined];
		knoepfe.append(knopf(option, klasse, () => antworte({ value: option }), symbol));
	}
	if (!d.optionen.includes("Abbrechen")) knoepfe.append(knopf("Später entscheiden", "link", () => antworte({ abgebrochen: true })));
	return [...titelElemente(d.titel), knoepfe];
}

function feldElement(feld) {
	const info = FELDER[feld.schluessel] ?? { label: feld.schluessel, art: "text" };
	const label = neu("label", "feld");
	label.append(neu("span", "feld-name", info.label));
	let eingabe;
	if (info.art === "auswahl") {
		eingabe = neu("select");
		const werte = info.werte.includes(feld.wert) ? info.werte : [feld.wert, ...info.werte];
		for (const wert of werte) {
			const option = neu("option", "", wert || "–");
			option.value = wert;
			eingabe.append(option);
		}
		eingabe.value = feld.wert;
	} else if (info.art === "mehrzeilig") {
		eingabe = neu("textarea");
		eingabe.rows = 3;
		eingabe.value = feld.wert;
	} else {
		eingabe = neu("input");
		eingabe.value = feld.wert;
	}
	eingabe.addEventListener("input", () => {
		feld.wert = eingabe.value;
	});
	eingabe.addEventListener("change", () => {
		feld.wert = eingabe.value;
	});
	label.append(eingabe);
	return label;
}

function fragenElement(formular) {
	const bereich = neu("fieldset", "fragen");
	bereich.append(neu("legend", "", "Offene Fragen"));
	const liste = neu("div", "fragen-liste");
	const zeichneFragen = () => {
		liste.replaceChildren(
			...formular.fragen.map((f, i) => {
				const zeile = neu("div", "frage");
				const frage = neu("input");
				frage.placeholder = "Frage";
				frage.value = f.frage;
				frage.addEventListener("input", () => {
					f.frage = frage.value;
				});
				const person = neu("input");
				person.placeholder = "Wer weiß es? (z. B. Einkauf)";
				person.value = f.ansprechperson;
				person.addEventListener("input", () => {
					f.ansprechperson = person.value;
				});
				const weg = knopf("Entfernen", "link", () => {
					formular.fragen.splice(i, 1);
					zeichneFragen();
				});
				zeile.append(frage, person, weg);
				return zeile;
			}),
		);
		if (!formular.fragen.length) liste.append(neu("p", "klein", "Keine offenen Fragen."));
	};
	zeichneFragen();
	bereich.append(
		liste,
		knopf("Frage hinzufügen", "link", () => {
			formular.fragen.push({ frage: "", ansprechperson: "" });
			zeichneFragen();
		}),
	);
	return bereich;
}

function editorDialog(d) {
	const formular = parseFormular(d.prefill);
	const inhalt = neu("div", "editor");
	const textfeld = neu("textarea", "rohtext");
	textfeld.rows = 12;
	textfeld.spellcheck = false;
	let alsText = !formular;

	const zeichneInhalt = () => {
		if (alsText) {
			inhalt.replaceChildren(textfeld);
			return;
		}
		const felder = neu("div", "felder");
		felder.append(...formular.felder.map(feldElement));
		inhalt.replaceChildren(felder, ...(formular.mitFragen ? [fragenElement(formular)] : []));
	};
	textfeld.value = formular ? serialisiereFormular(formular, formular.kommentare) : d.prefill;

	const knoepfe = neu("div", "knoepfe");
	knoepfe.append(
		knopf("Speichern", "", () => antworte({ value: alsText ? textfeld.value : serialisiereFormular(formular) })),
	);
	if (formular) {
		const umschalter = knopf("Als Text bearbeiten", "zweitrangig", () => {
			if (!alsText) textfeld.value = serialisiereFormular(formular, formular.kommentare);
			alsText = true;
			umschalter.remove();
			zeichneInhalt();
		});
		knoepfe.append(umschalter);
	}
	knoepfe.append(knopf("Abbrechen", "link", () => antworte({ abgebrochen: true })));
	zeichneInhalt();
	return [neu("h3", "", d.titel.split("\n")[0]), inhalt, knoepfe];
}

function bestaetigungsDialog(d) {
	const knoepfe = neu("div", "knoepfe");
	knoepfe.append(knopf("Ja", "", () => antworte({ confirmed: true })), knopf("Nein", "zweitrangig", () => antworte({ confirmed: false })));
	return [...titelElemente(d.titel), ...(d.nachricht ? [neu("p", "", d.nachricht)] : []), knoepfe];
}

function eingabeDialog(d) {
	const eingabe = neu("input");
	eingabe.placeholder = d.platzhalter;
	const knoepfe = neu("div", "knoepfe");
	knoepfe.append(knopf("OK", "", () => antworte({ value: eingabe.value })), knopf("Abbrechen", "link", () => antworte({ abgebrochen: true })));
	return [...titelElemente(d.titel), eingabe, knoepfe];
}

// ---- Side panel -------------------------------------------------------------------------

function dateiname(name) {
	const element = neu("span", "dateiname", name);
	element.title = name;
	return element;
}

async function ladeDateien() {
	const r = await fetch("/api/dateien").catch(() => null);
	if (!r?.ok) return;
	({ dateien, arbeitsstand } = await r.json());
	zeichneDateien();
}

function zeichneDateien() {
	const gesperrt = !zustand || zustand.laufend || Boolean(zustand.fehler);
	const liste = $("dateien");
	liste.replaceChildren(
		...dateien.map((name) => {
			const li = neu("li");
			const info = neu("span", "datei-info");
			info.append(dateiname(name));
			// With saved decisions they come back and the assistant skips the context questions; same
			// condition as the extension's resume hint in datensatz_analysieren.
			const stand = arbeitsstand[name];
			const fortsetzbar = stand && stand.geprueft + stand.vorgeschlagen > 0;
			if (fortsetzbar) info.append(neu("span", "datei-stand", stand.text));
			const [text, nachricht] = fortsetzbar
				? ["Fortsetzen", `Ich möchte die Dokumentation der Datei ${name} fortsetzen.`]
				: ["Dokumentieren", `Ich möchte die Datei ${name} dokumentieren.`];
			const b = knopf(text, "klein-knopf zweitrangig", () => sende(nachricht), ikon("arrow-right"));
			b.disabled = gesperrt;
			li.append(info, b);
			return li;
		}),
	);
	if (!dateien.length) liste.append(neu("li", "klein", "Noch keine Dateien in daten/."));
}

async function ladeStand() {
	const r = await fetch("/api/stand").catch(() => null);
	if (!r?.ok) return;
	const stand = await r.json();
	const vorhanden = Boolean(stand.ordner);
	$("fortschritt-karte").hidden = !vorhanden;
	$("spalten-karte").hidden = !vorhanden;
	$("ergebnisse-karte").hidden = !vorhanden || !stand.exporte.length;
	if (!vorhanden) return;

	const f = stand.fortschritt;
	$("fortschritt-datei").textContent = stand.datei;
	$("balken-wert").style.width = `${f.gesamt ? Math.round((100 * f.geprueft) / f.gesamt) : 0}%`;
	$("fortschritt-text").textContent = `${f.geprueft} von ${f.gesamt} Spalten geprüft · ${f.vorgeschlagen} Vorschläge offen`;
	$("datasheet-text").textContent = `Angaben zum Datensatz (Datasheet): ${STATUS_TEXTE[f.datasheet] ?? f.datasheet}`;

	const tbody = $("spalten");
	tbody.replaceChildren();
	for (const s of stand.spalten) {
		const zeile = neu("tr", "spalte-zeile");
		const ampel = neu("span", `ampel ${s.ampel === "grün" ? "gruen" : s.ampel}`);
		ampel.title = s.befunde.length ? `${s.befunde.length} Befunde` : "keine Befunde";
		const zellen = [neu("td"), neu("td", "code", s.spalte), neu("td", "", s.name ?? "–"), neu("td")];
		zellen[0].append(ampel);
		zellen[3].append(neu("span", `marke-status ${s.status === "geprüft" ? "geprueft" : s.status}`, STATUS_TEXTE[s.status] ?? s.status));
		zeile.append(...zellen);
		zeile.tabIndex = 0;
		const umschalten = () => {
			offeneSpalten.has(s.spalte) ? offeneSpalten.delete(s.spalte) : offeneSpalten.add(s.spalte);
			ladeStand();
		};
		zeile.addEventListener("click", umschalten);
		zeile.addEventListener("keydown", (e) => e.key === "Enter" && umschalten());
		tbody.append(zeile);
		if (offeneSpalten.has(s.spalte)) {
			const details = neu("tr", "befunde-zeile");
			const zelle = neu("td");
			zelle.colSpan = 4;
			const ul = neu("ul", "befunde");
			for (const b of s.befunde) {
				const li = neu("li", `schwere-${b.schwere}`);
				li.append(neu("strong", "", `${b.titel}: `), b.erklaerung);
				ul.append(li);
			}
			zelle.append(s.befunde.length ? ul : neu("p", "klein", "Keine Befunde."));
			details.append(zelle);
			tbody.append(details);
		}
	}

	$("ergebnisse-stand").textContent = stand.exportiert ? `Exportiert am ${stand.exportiert}` : "";
	$("ergebnisse").replaceChildren(
		...stand.exporte.map((name) => {
			const li = neu("li");
			const aktionen = neu("span", "aktionen");
			if (name.endsWith(".md")) aktionen.append(knopf("Ansehen", "klein-knopf zweitrangig", () => zeigeExport(name), ikon("eye")));
			const link = neu("a", "knopf klein-knopf zweitrangig", "Herunterladen");
			link.prepend(ikon("download"));
			link.href = `/api/export/${encodeURIComponent(name)}?download=1`;
			aktionen.append(link);
			li.append(dateiname(name), aktionen);
			return li;
		}),
	);
}

async function zeigeExport(name) {
	const r = await fetch(`/api/export/${encodeURIComponent(name)}`).catch(() => null);
	if (!r?.ok) return toast(`${name} ließ sich nicht laden.`, "fehler");
	modal(name, markdown(await r.text()));
}

async function hochladen(datei, ersetzen = false) {
	if (!/\.(csv|xlsx)$/i.test(datei.name)) return toast("Nur .csv- und .xlsx-Dateien sind möglich.", "fehler");
	if (datei.size > MAX_BYTES) return toast("Die Datei ist größer als 50 MB.", "fehler");
	const r = await fetch(`/api/dateien/${encodeURIComponent(datei.name)}${ersetzen ? "?ersetzen=1" : ""}`, { method: "PUT", body: datei }).catch(() => null);
	if (!r) return toast("Hochladen fehlgeschlagen.", "fehler");
	const antwort = await r.json().catch(() => ({}));
	if (r.status === 409 && !ersetzen) {
		if (await bestaetige("Datei ersetzen?", `Die Datei ${datei.name} gibt es schon in daten/. Soll sie ersetzt werden?`, "Ersetzen")) {
			await hochladen(datei, true);
		}
		return;
	}
	if (!r.ok) return toast(antwort.fehler || "Hochladen fehlgeschlagen.", "fehler");
	({ dateien, arbeitsstand } = antwort);
	zeichneDateien();
	toast(`${antwort.datei} liegt jetzt in daten/.`);
}

// ---- Actions ------------------------------------------------------------------------------

function sende(text) {
	if (!text.trim()) return;
	return versuche(async () => {
		await api("/api/nachricht", { text });
		$("text").value = "";
	});
}

function einrichten() {
	for (const element of document.querySelectorAll("[data-ikon]")) element.prepend(ikon(element.dataset.ikon));
	setzeThema(document.documentElement.dataset.thema ?? "system");
	$("thema").addEventListener("click", () => setzeThema(THEMEN[document.documentElement.dataset.thema ?? "system"].naechstes));
	$("eingabe").addEventListener("submit", (e) => {
		e.preventDefault();
		sende($("text").value);
	});
	$("text").addEventListener("keydown", (e) => {
		if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
			e.preventDefault();
			sende($("text").value);
		}
	});
	$("stopp").addEventListener("click", () => versuche(() => api("/api/stopp")));
	$("neustart").addEventListener("click", () => versuche(() => api("/api/neustart")));
	$("neu").addEventListener("click", async () => {
		const leer = !zustand?.nachrichten.length;
		if (leer || (await bestaetige("Neu beginnen?", "Das Gespräch wird geleert. Alle bisherigen Entscheidungen bleiben gespeichert.", "Neu beginnen"))) {
			versuche(() => api("/api/neu"));
		}
	});
	$("modell").addEventListener("change", async (e) => {
		const [provider, ...rest] = e.target.value.split("/");
		const id = rest.join("/");
		const leer = !zustand?.nachrichten.length;
		const ok = leer || (await bestaetige("Modell wechseln?", "Mit dem neuen Modell beginnt ein neues Gespräch. Alle bisherigen Entscheidungen bleiben gespeichert.", "Wechseln"));
		if (!ok) return zeichneModelle();
		e.target.disabled = true;
		await versuche(() => api("/api/modell", { provider, id }));
		zeichneModelle();
	});
	$("modal-zu").addEventListener("click", schliesseModal);
	$("modal").addEventListener("click", (e) => e.target === $("modal") && schliesseModal());
	document.addEventListener("keydown", (e) => e.key === "Escape" && !$("modal").hidden && schliesseModal());

	const ablage = $("ablage");
	$("datei").addEventListener("change", (e) => {
		if (e.target.files[0]) hochladen(e.target.files[0]);
		e.target.value = "";
	});
	ablage.addEventListener("dragover", (e) => {
		e.preventDefault();
		ablage.classList.add("aktiv");
	});
	ablage.addEventListener("dragleave", () => ablage.classList.remove("aktiv"));
	ablage.addEventListener("drop", (e) => {
		e.preventDefault();
		ablage.classList.remove("aktiv");
		if (e.dataTransfer.files[0]) hochladen(e.dataTransfer.files[0]);
	});

	verbinden();
	ladeDateien();
	ladeStand();
}

einrichten();
