// Applies the stored theme before the first paint (a classic script in <head>; the CSP forbids inline
// script). Without a stored choice the page follows the system setting. app.js wires the switch.

try {
	const thema = localStorage.getItem("thema");
	if (thema === "hell" || thema === "dunkel") document.documentElement.dataset.thema = thema;
} catch {
	// Storage blocked (private window, policy): stay with the system setting.
}
