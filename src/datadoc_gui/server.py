"""Local HTTP server of the GUI: static page, JSON API, Server-Sent Events.

Listens on 127.0.0.1 only. Every request needs the session cookie, which the start URL sets
from a random token; the Host header must name this server (protects against DNS rebinding).
Model and data text is untrusted: the page renders it escaped, and the CSP forbids inline script.
"""

from __future__ import annotations

import hmac
import json
import os
import queue
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from datadoc import draft, paths, rules
from datadoc.export import EXPORT_FILES
from datadoc.loader import MAX_BYTES

from .sitzung import Konflikt, Sitzung

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    **{name: "text/javascript; charset=utf-8" for name in ("app.js", "markdown.js", "formular.js", "icons.js", "thema.js")},
    "style.css": "text/css; charset=utf-8",
    "marke/aitraqc-logo-compact.png": "image/png",
    **{f"fonts/{p.name}": "font/woff2" for p in (STATIC_DIR / "fonts").glob("*.woff2")},
}
EXPORT_TYPES = {
    ".md": "text/plain; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
MAX_JSON_BYTES = 1024 * 1024
SSE_PING_S = 15
FORBIDDEN_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>Datendokumentation</title>"
    "<p>Kein Zugriff. Bitte die Oberfläche über die Adresse aus dem Startfenster öffnen (start.ps1 -Gui).</p>"
)


class GuiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, sitzung: Sitzung, root: Path, token: str):
        super().__init__(("127.0.0.1", port), Handler)
        self.sitzung, self.root, self.token = sitzung, root, token
        self.port = self.server_address[1]
        self.cookie_name = f"datadoc_{self.port}"
        self.hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        self.origins = {f"http://{h}" for h in self.hosts}


class Fehler(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(text)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server: GuiServer

    def log_message(self, format, *args):  # noqa: A002 - keep the console quiet
        pass

    # ---- plumbing -------------------------------------------------------------------------

    def _kopf(self, status: int, typ: str, laenge: int | None = None, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        if laenge is not None:
            self.send_header("Content-Length", str(laenge))
        for name, wert in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, wert)
        self.end_headers()

    def _senden(self, status: int, typ: str, daten: bytes, extra: dict | None = None) -> None:
        self._kopf(status, typ, len(daten), extra)
        self.wfile.write(daten)

    def _json(self, status: int, daten) -> None:
        self._senden(status, "application/json; charset=utf-8", json.dumps(daten, ensure_ascii=False).encode("utf-8"))

    def _angemeldet(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        wert = cookie[self.server.cookie_name].value if self.server.cookie_name in cookie else ""
        return hmac.compare_digest(wert.encode(), self.server.token.encode())

    def _pruefe_zugriff(self, schreibend: bool) -> None:
        if self.headers.get("Host", "") not in self.server.hosts:
            raise Fehler(403, "Unbekannter Host.")
        origin = self.headers.get("Origin")
        if schreibend and origin is not None and origin not in self.server.origins:
            raise Fehler(403, "Fremde Herkunft.")
        if not self._angemeldet():
            raise Fehler(403, "Nicht angemeldet. Bitte die Adresse aus dem Startfenster öffnen.")

    def _json_eingabe(self) -> dict:
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise Fehler(415, "Erwartet wird JSON.")
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > MAX_JSON_BYTES:
            raise Fehler(413, "Die Anfrage ist zu groß.")
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}")
        except ValueError:
            raise Fehler(400, "Ungültiges JSON.") from None
        if not isinstance(daten, dict):
            raise Fehler(400, "Erwartet wird ein JSON-Objekt.")
        return daten

    def _ausfuehren(self, methode, schreibend: bool) -> None:
        try:
            self._pruefe_zugriff(schreibend)
            methode()
        except Fehler as fehler:
            if self.path.startswith("/api/"):
                self._json(fehler.status, {"fehler": str(fehler)})
            else:
                self._senden(fehler.status, "text/html; charset=utf-8", FORBIDDEN_PAGE.encode("utf-8"))
        except Konflikt as fehler:
            self._json(409, {"fehler": str(fehler)})
        except (ValueError, paths.PathError) as fehler:
            self._json(400, {"fehler": str(fehler)})
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    # ---- routing --------------------------------------------------------------------------

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/" and "t" in parse_qs(url.query):
            return self._anmelden(parse_qs(url.query)["t"][0])
        routen = {
            "/": self._seite,
            "/api/ereignisse": self._ereignisse,
            "/api/dateien": lambda: self._json(200, self._dateien()),
            "/api/stand": lambda: self._json(200, self._stand()),
        }
        if url.path in routen:
            return self._ausfuehren(routen[url.path], schreibend=False)
        if url.path.startswith("/static/"):
            return self._ausfuehren(lambda: self._statisch(url.path.removeprefix("/static/")), schreibend=False)
        if url.path.startswith("/api/export/"):
            name = unquote(url.path.removeprefix("/api/export/"))
            return self._ausfuehren(lambda: self._export(name, "download" in parse_qs(url.query)), schreibend=False)
        self._ausfuehren(lambda: self._json(404, {"fehler": "Nicht gefunden."}), schreibend=False)

    def do_POST(self):
        sitzung = self.server.sitzung
        aktionen = {
            "/api/nachricht": lambda d: sitzung.nachricht(str(d.get("text", ""))),
            "/api/dialog": lambda d: sitzung.antworte(str(d.get("id", "")), d),
            "/api/stopp": lambda d: sitzung.stopp(),
            "/api/neu": lambda d: sitzung.neu(),
            "/api/neustart": lambda d: sitzung.neustart(),
            "/api/modell": lambda d: sitzung.waehle_modell(str(d.get("provider", "")), str(d.get("id", ""))),
        }
        aktion = aktionen.get(urlsplit(self.path).path)

        def ausfuehren():
            if aktion is None:
                raise Fehler(404, "Nicht gefunden.")
            aktion(self._json_eingabe())
            self._json(200, {"ok": True})

        self._ausfuehren(ausfuehren, schreibend=True)

    def do_PUT(self):
        url = urlsplit(self.path)

        def hochladen():
            if not url.path.startswith("/api/dateien/"):
                raise Fehler(404, "Nicht gefunden.")
            self._hochladen(unquote(url.path.removeprefix("/api/dateien/")), "ersetzen" in parse_qs(url.query))

        self._ausfuehren(hochladen, schreibend=True)

    # ---- handlers -------------------------------------------------------------------------

    def _anmelden(self, token: str) -> None:
        if self.headers.get("Host", "") not in self.server.hosts or not hmac.compare_digest(token.encode(), self.server.token.encode()):
            self._senden(403, "text/html; charset=utf-8", FORBIDDEN_PAGE.encode("utf-8"))
            return
        cookie = f"{self.server.cookie_name}={self.server.token}; HttpOnly; SameSite=Strict; Path=/"
        self._kopf(303, "text/plain", 0, {"Location": "/", "Set-Cookie": cookie})

    def _seite(self) -> None:
        self._senden(200, "text/html; charset=utf-8", (STATIC_DIR / "index.html").read_bytes())

    def _statisch(self, name: str) -> None:
        if name not in STATIC_FILES:
            raise Fehler(404, "Nicht gefunden.")
        self._senden(200, STATIC_FILES[name], (STATIC_DIR / name).read_bytes())

    def _ereignisse(self) -> None:
        sitzung = self.server.sitzung
        self._kopf(200, "text/event-stream; charset=utf-8")
        q = sitzung.abonnieren()
        try:
            while True:
                try:
                    daten = q.get(timeout=SSE_PING_S)
                except queue.Empty:
                    if not sitzung.ist_abonniert(q):
                        return
                    self.wfile.write(b": ping\n\n")
                else:
                    self.wfile.write(f"data: {daten}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
        finally:
            sitzung.abbestellen(q)

    def _dateien(self) -> dict:
        """Files in daten/ and, for those with a saved workspace, its progress (the GUI offers to resume them)."""
        root = self.server.root
        dateien = paths.available_files(root)
        arbeitsstand = {}
        for name in dateien:
            try:
                d = draft.load(paths.workspace(root, paths.workspace_name(Path(name), None)))
            except (paths.PathError, OSError, ValueError):
                continue
            if d.quelle.get("datei") == name:  # a.csv and a.xlsx would share one folder
                arbeitsstand[name] = draft.progress(d)
        return {"dateien": dateien, "arbeitsstand": arbeitsstand}

    def _arbeitsordner(self) -> Path | None:
        ordner = self.server.sitzung.zustand["ordner"]
        return paths.workspace(self.server.root, ordner) if ordner else None

    def _stand(self) -> dict:
        workspace = self._arbeitsordner()
        if workspace is None:
            return {"ordner": None}
        d = draft.load(workspace)
        spalten = []
        for name, e in d.spalten.items():
            befunde = [f for f in d.befunde if f["spalte"] == name]
            spalten.append({
                "spalte": name,
                "name": e.vorschlag.lesbarer_name if e.vorschlag else None,
                "status": e.status,
                "ampel": rules.traffic_light(befunde),
                "befunde": [{k: f[k] for k in ("schwere", "titel", "erklaerung")} for f in befunde],
            })
        exporte = [n for n in EXPORT_FILES if (workspace / n).is_file()]
        exportiert = max((os.path.getmtime(workspace / n) for n in exporte), default=None)
        return {
            "ordner": workspace.name,
            "datei": d.quelle.get("datei"),
            "fortschritt": draft.progress(d),
            "spalten": spalten,
            "exporte": exporte,
            "exportiert": datetime.fromtimestamp(exportiert).strftime("%d.%m.%Y, %H:%M") if exportiert else None,
        }

    def _export(self, name: str, download: bool) -> None:
        workspace = self._arbeitsordner()
        if name not in EXPORT_FILES or workspace is None or not (workspace / name).is_file():
            raise Fehler(404, "Diese Datei gibt es nicht.")
        extra = {"Content-Disposition": f'attachment; filename="{workspace.name}_{name}"'} if download else None
        self._senden(200, EXPORT_TYPES[Path(name).suffix], (workspace / name).read_bytes(), extra)

    def _hochladen(self, name: str, ersetzen: bool) -> None:
        ziel = paths.upload_target(self.server.root, name)
        if self.headers.get("Content-Length") is None:
            raise Fehler(411, "Die Dateigröße fehlt.")
        laenge = int(self.headers["Content-Length"])
        if laenge > MAX_BYTES:
            raise Fehler(413, f"Die Datei ist zu groß. Erlaubt sind höchstens {MAX_BYTES // 1024 // 1024} MB.")
        if ziel.exists() and not ersetzen:
            raise Fehler(409, f"Die Datei '{ziel.name}' gibt es schon in daten/.")
        ziel.parent.mkdir(exist_ok=True)
        tmp = ziel.with_name(f".{ziel.name}.upload")
        with tmp.open("wb") as fh:
            rest = laenge
            while rest > 0:
                block = self.rfile.read(min(rest, 1024 * 1024))
                if not block:
                    break
                fh.write(block)
                rest -= len(block)
        if rest:
            tmp.unlink(missing_ok=True)
            raise Fehler(400, "Die Datei kam nicht vollständig an.")
        os.replace(tmp, ziel)
        self._json(200, {"datei": ziel.name, **self._dateien()})
