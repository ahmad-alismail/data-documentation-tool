// Minimal Markdown renderer for untrusted text (model replies, export files).
// Escapes everything first and only ever emits a fixed set of tags without attributes:
// no links, no images, no raw HTML. No DOM access, so node --test can import it.

const ZEICHEN = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text) {
	return String(text).replace(/[&<>"']/g, (c) => ZEICHEN[c]);
}

// Bold with ** and italics with single *. Underscores stay literal: column names like MAT_KAT are common.
function inline(text) {
	return text
		.split(/(`[^`\n]+`)/)
		.map((teil, i) => {
			if (i % 2 === 1) return `<code>${escapeHtml(teil.slice(1, -1))}</code>`;
			return escapeHtml(teil)
				.replace(/\*\*(\S(?:.*?\S)?)\*\*/g, "<strong>$1</strong>")
				.replace(/(^|[^*])\*(\S(?:[^*]*?\S)?)\*(?!\*)/g, "$1<em>$2</em>");
		})
		.join("");
}

const CODE = /^\s*```/;
const UEBERSCHRIFT = /^(#{1,6})\s+(.*)$/;
const LINIE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
const ZITAT = /^\s*>\s?/;
const AUFZAEHLUNG = /^\s*([-*+•]|\d+[.)])\s+(.*)$/;
const TRENNZEILE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function zellen(zeile) {
	return zeile
		.trim()
		.replace(/^\|/, "")
		.replace(/(?<!\\)\|$/, "")
		.split(/(?<!\\)\|/)
		.map((z) => inline(z.trim().replace(/\\\|/g, "|")));
}

function istTabelle(zeilen, i) {
	return zeilen[i].trim().startsWith("|") && i + 1 < zeilen.length && TRENNZEILE.test(zeilen[i + 1]);
}

function istBlockanfang(zeilen, i) {
	const z = zeilen[i];
	return CODE.test(z) || UEBERSCHRIFT.test(z) || LINIE.test(z) || ZITAT.test(z) || AUFZAEHLUNG.test(z) || istTabelle(zeilen, i);
}

export function renderMarkdown(quelle) {
	const zeilen = String(quelle ?? "").replace(/\r\n?/g, "\n").split("\n");
	const html = [];
	let i = 0;
	while (i < zeilen.length) {
		const zeile = zeilen[i];
		let m;
		if (!zeile.trim()) {
			i++;
		} else if (CODE.test(zeile)) {
			const code = [];
			for (i++; i < zeilen.length && !CODE.test(zeilen[i]); i++) code.push(zeilen[i]);
			i++;
			html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
		} else if ((m = zeile.match(UEBERSCHRIFT))) {
			const ebene = m[1].length;
			html.push(`<h${ebene}>${inline(m[2])}</h${ebene}>`);
			i++;
		} else if (LINIE.test(zeile)) {
			html.push("<hr>");
			i++;
		} else if (istTabelle(zeilen, i)) {
			const kopf = zellen(zeile);
			const koerper = [];
			for (i += 2; i < zeilen.length && zeilen[i].trim().startsWith("|"); i++) koerper.push(zellen(zeilen[i]));
			const th = kopf.map((z) => `<th>${z}</th>`).join("");
			const tr = koerper.map((r) => `<tr>${r.map((z) => `<td>${z}</td>`).join("")}</tr>`).join("");
			html.push(`<div class="tabelle"><table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`);
		} else if (ZITAT.test(zeile)) {
			const inhalt = [];
			for (; i < zeilen.length && ZITAT.test(zeilen[i]); i++) inhalt.push(zeilen[i].replace(ZITAT, ""));
			html.push(`<blockquote>${renderMarkdown(inhalt.join("\n"))}</blockquote>`);
		} else if ((m = zeile.match(AUFZAEHLUNG))) {
			const nummeriert = /\d/.test(m[1]);
			const punkte = [];
			while (i < zeilen.length) {
				const p = zeilen[i].match(AUFZAEHLUNG);
				if (p && /\d/.test(p[1]) === nummeriert) {
					punkte.push(p[2]);
					i++;
				} else if (zeilen[i].trim() && /^\s+/.test(zeilen[i]) && punkte.length && !istBlockanfang(zeilen, i)) {
					punkte[punkte.length - 1] += ` ${zeilen[i].trim()}`;
					i++;
				} else if (!zeilen[i].trim()) {
					// A blank line between two items does not end the list ("1. …", blank, "2. …").
					let j = i;
					while (j < zeilen.length && !zeilen[j].trim()) j++;
					const naechster = j < zeilen.length && zeilen[j].match(AUFZAEHLUNG);
					if (!naechster || /\d/.test(naechster[1]) !== nummeriert) break;
					i = j;
				} else break;
			}
			const tag = nummeriert ? "ol" : "ul";
			html.push(`<${tag}>${punkte.map((p) => `<li>${inline(p)}</li>`).join("")}</${tag}>`);
		} else {
			const absatz = [];
			for (; i < zeilen.length && zeilen[i].trim() && !istBlockanfang(zeilen, i); i++) absatz.push(inline(zeilen[i].trim()));
			html.push(`<p>${absatz.join("<br>")}</p>`);
		}
	}
	return html.join("");
}
