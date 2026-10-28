"""Start the GUI: ``python -m datadoc_gui [--modell provider/id] [--port 8765] [--kein-browser]``."""

from __future__ import annotations

import argparse
import secrets
import sys
import webbrowser

from .pi_rpc import ROOT, PiProcess, pi_command
from .server import GuiServer
from .sitzung import Sitzung

STANDARD_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datadoc_gui", description=__doc__)
    parser.add_argument("--modell", help="provider/id aus pi-agent/models.json, sonst defaultModel")
    parser.add_argument("--port", type=int, default=STANDARD_PORT)
    parser.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    token = secrets.token_urlsafe(24)
    sitzung = Sitzung(lambda: PiProcess(pi_command(args.modell), root=ROOT), ROOT)
    try:
        server = GuiServer(args.port, sitzung, ROOT, token)
    except OSError:
        server = GuiServer(0, sitzung, ROOT, token)
    url = f"http://127.0.0.1:{server.port}/?t={token}"
    print(f"Datendokumentations-Assistent läuft: {url}\nBeenden mit Strg+C.", flush=True)
    if not args.kein_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        sitzung.beenden()
    return 0


if __name__ == "__main__":
    sys.exit(main())
