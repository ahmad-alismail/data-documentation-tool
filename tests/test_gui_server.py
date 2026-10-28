import http.client
import json
import threading

import pytest

from datadoc.export import EXPORT_FILES
from datadoc.loader import MAX_BYTES
from datadoc_gui.server import GuiServer
from tests.conftest import DEMO, WORKSPACE
from tests.test_gui_sitzung import fake_sitzung, warte

TOKEN = "geheim-token"


@pytest.fixture
def server(project):
    sitzung = fake_sitzung(project)
    srv = GuiServer(0, sitzung, project, TOKEN)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()
    sitzung.beenden()


def anfrage(srv, methode, pfad, body=None, headers=None, cookie=True, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    kopf = {"Host": host or f"127.0.0.1:{srv.port}"}
    if cookie:
        kopf["Cookie"] = f"{srv.cookie_name}={TOKEN}"
    kopf.update(headers or {})
    conn.request(methode, pfad, body=body, headers=kopf)
    antwort = conn.getresponse()
    daten = antwort.read()
    conn.close()
    return antwort, daten


def post(srv, pfad, daten, **kwargs):
    return anfrage(srv, "POST", pfad, json.dumps(daten), {"Content-Type": "application/json"} | kwargs.pop("headers", {}), **kwargs)


def test_login_sets_strict_http_only_cookie(server):
    antwort, _ = anfrage(server, "GET", f"/?t={TOKEN}", cookie=False)
    assert antwort.status == 303 and antwort.getheader("Location") == "/"
    cookie = antwort.getheader("Set-Cookie")
    assert f"{server.cookie_name}={TOKEN}" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_wrong_token_is_rejected(server):
    antwort, _ = anfrage(server, "GET", "/?t=falsch", cookie=False)
    assert antwort.status == 403


@pytest.mark.parametrize("pfad", ["/", "/api/dateien", "/api/stand", "/static/app.js", "/api/ereignisse"])
def test_every_route_requires_the_cookie(server, pfad):
    antwort, _ = anfrage(server, "GET", pfad, cookie=False)
    assert antwort.status == 403


def test_foreign_host_is_rejected(server):
    antwort, _ = anfrage(server, "GET", "/api/dateien", host=f"evil.example:{server.port}")
    assert antwort.status == 403


def test_foreign_origin_cannot_post(server):
    antwort, _ = post(server, "/api/nachricht", {"text": "hallo"}, headers={"Origin": "http://evil.example"})
    assert antwort.status == 403
    assert server.sitzung.zustand["nachrichten"] == []


def test_post_requires_json(server):
    antwort, _ = anfrage(server, "POST", "/api/nachricht", "text=hallo", {"Content-Type": "application/x-www-form-urlencoded"})
    assert antwort.status == 415


def test_page_has_security_headers(server):
    antwort, daten = anfrage(server, "GET", "/")
    assert antwort.status == 200 and b"Datendokumentations-Assistent" in daten
    csp = antwort.getheader("Content-Security-Policy")
    assert "script-src 'self'" in csp and "default-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert antwort.getheader("X-Content-Type-Options") == "nosniff"


def test_only_whitelisted_static_files(server):
    assert anfrage(server, "GET", "/static/app.js")[0].status == 200
    for pfad in ["/static/../server.py", "/static/index.html", "/static/fonts/../../server.py",
                 "/static/marke/x.png", "/static/LICENSE-lucide.txt", "/static/fonts/OFL-Barlow.txt"]:
        assert anfrage(server, "GET", pfad)[0].status == 404, pfad


def test_brand_assets_are_served_with_binary_types(server):
    antwort, daten = anfrage(server, "GET", "/static/fonts/barlow-latin-400-normal.woff2")
    assert antwort.status == 200 and antwort.getheader("Content-Type") == "font/woff2" and daten[:4] == b"wOF2"
    antwort, daten = anfrage(server, "GET", "/static/marke/aitraqc-logo-compact.png")
    assert antwort.status == 200 and antwort.getheader("Content-Type") == "image/png" and daten[:4] == b"\x89PNG"
    assert anfrage(server, "GET", "/static/style.css")[0].getheader("Content-Type") == "text/css; charset=utf-8"
    assert anfrage(server, "GET", "/static/thema.js")[0].getheader("Content-Type") == "text/javascript; charset=utf-8"


def test_message_and_dialog_over_http(server):
    assert post(server, "/api/nachricht", {"text": "dialog"})[0].status == 200
    dialog = warte(server.sitzung, lambda z: z["dialog"] is not None)["dialog"]
    assert post(server, "/api/dialog", {"id": "falsch", "value": "Übernehmen"})[0].status == 409
    assert post(server, "/api/dialog", {"id": dialog["id"], "value": "Übernehmen"})[0].status == 200
    warte(server.sitzung, lambda z: not z["laufend"])


def test_upload_valid_file(server, project):
    antwort, daten = anfrage(server, "PUT", "/api/dateien/neu%20(1).csv", b"a;b\n1;2\n")
    assert antwort.status == 200
    assert (project / "daten" / "neu (1).csv").read_bytes() == b"a;b\n1;2\n"
    assert "neu (1).csv" in json.loads(daten)["dateien"]
    assert not list((project / "daten").glob(".*.upload"))


@pytest.mark.parametrize("name", ["..%2Fx.csv", "a%2Fb.csv", "a%5Cb.csv", "C%3Ax.csv", "x.exe", "~x.csv", ".csv"])
def test_upload_rejects_unsafe_names(server, project, name):
    antwort, _ = anfrage(server, "PUT", f"/api/dateien/{name}", b"a;b\n")
    assert antwort.status == 400
    assert not (project / "x.csv").exists()


def test_upload_rejects_large_files_before_reading(server):
    antwort, _ = anfrage(server, "PUT", "/api/dateien/gross.csv", headers={"Content-Length": str(MAX_BYTES + 1)})
    assert antwort.status == 413


def test_upload_requires_content_length(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.putrequest("PUT", "/api/dateien/ohne.csv", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{server.port}")
    conn.putheader("Cookie", f"{server.cookie_name}={TOKEN}")
    conn.endheaders()
    assert conn.getresponse().status == 411
    conn.close()


def test_upload_does_not_replace_without_consent(server, project):
    original = (project / "daten" / DEMO).read_bytes()
    assert anfrage(server, "PUT", f"/api/dateien/{DEMO}", b"x;y\n")[0].status == 409
    assert (project / "daten" / DEMO).read_bytes() == original
    assert anfrage(server, "PUT", f"/api/dateien/{DEMO}?ersetzen=1", b"x;y\n")[0].status == 200
    assert (project / "daten" / DEMO).read_bytes() == b"x;y\n"


def test_file_list_shows_saved_progress_for_resuming(server, run):
    assert json.loads(anfrage(server, "GET", "/api/dateien")[1]) == {"dateien": [DEMO], "arbeitsstand": {}}
    run("analyze", DEMO)
    arbeitsstand = json.loads(anfrage(server, "GET", "/api/dateien")[1])["arbeitsstand"]
    assert list(arbeitsstand) == [DEMO] and arbeitsstand[DEMO]["text"] == "0 von 11 Spalten geprüft"


def test_stand_without_dataset(server):
    antwort, daten = anfrage(server, "GET", "/api/stand")
    assert antwort.status == 200 and json.loads(daten) == {"ordner": None}


def test_stand_and_exports(server, run, analyzed, project):
    server.sitzung.zustand["ordner"] = WORKSPACE
    stand = json.loads(anfrage(server, "GET", "/api/stand")[1])
    assert stand["fortschritt"]["gesamt"] == 11 and stand["exporte"] == []
    spalten = {s["spalte"]: s for s in stand["spalten"]}
    assert spalten["BEM"]["ampel"] == "rot" and spalten["STAT"]["status"] == "offen"
    assert all(set(b) == {"schwere", "titel", "erklaerung"} for s in stand["spalten"] for b in s["befunde"])

    assert run("export", WORKSPACE)[0] == 0
    workspace = project / "ausgabe" / WORKSPACE
    assert {p.name for p in workspace.iterdir()} - {"entwurf.json"} == set(EXPORT_FILES)
    stand = json.loads(anfrage(server, "GET", "/api/stand")[1])
    assert stand["exporte"] == list(EXPORT_FILES) and stand["exportiert"]

    antwort, daten = anfrage(server, "GET", "/api/export/datenwoerterbuch.md")
    assert antwort.status == 200 and antwort.getheader("Content-Type").startswith("text/plain")
    assert daten.decode("utf-8").startswith("# Datenwörterbuch")
    antwort, _ = anfrage(server, "GET", "/api/export/datenwoerterbuch.xlsx?download=1")
    assert "attachment" in antwort.getheader("Content-Disposition")
    for pfad in ["/api/export/entwurf.json", "/api/export/..%2F..%2Fdaten%2Fauftraege_handwerksbetrieb.csv"]:
        assert anfrage(server, "GET", pfad)[0].status == 404
