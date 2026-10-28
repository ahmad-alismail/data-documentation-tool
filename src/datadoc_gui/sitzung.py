"""Bridge between one Pi process (RPC mode) and the browser tabs of the GUI.

Holds the UI state, turns Pi events into UI events and forwards the person's actions to Pi.
Dialog answers come only from the browser; the bridge itself only ever cancels dialogs while
stopping a run. So the status "geprüft" still comes only from a human decision.
"""

from __future__ import annotations

import itertools
import json
import queue
import re
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from .pi_rpc import PiProcess

DIALOG_METHODEN = ("select", "confirm", "input", "editor")
AKTIVITAETEN = {
    "datensatz_analysieren": "Datensatz wird analysiert",
    "spalte_ansehen": "Spalte wird angesehen",
    "vorschlag_speichern": "Vorschlag wird gespeichert",
    "vorschlag_bestaetigen": "Wartet auf Ihre Entscheidung",
    "datasheet_speichern": "Angaben zum Datensatz werden gespeichert",
    "dokumentation_exportieren": "Dokumentation wird exportiert",
    "wissen_laden": "Fachwissen wird geladen",
}
ANFRAGE_TIMEOUT_S = 30
ABONNENT_PUFFER = 1000
TRENNLINIE = re.compile(r"[\s\-*_=]*")  # a message of only separators ("---") is not shown


class Konflikt(Exception):
    """The action does not fit the current state (e.g. the assistant is still working)."""


def modelle_aus_konfiguration(root: Path) -> list[dict]:
    """Models from pi-agent/models.json, the only place where models are configured."""
    try:
        providers = json.loads((root / "pi-agent" / "models.json").read_text(encoding="utf-8"))["providers"]
    except (OSError, ValueError, KeyError):
        return []
    return [
        {"provider": provider, "id": m["id"], "name": m.get("name") or m["id"]}
        for provider, config in providers.items()
        for m in config.get("models", [])
    ]


class Sitzung:
    def __init__(self, starte_pi: Callable[[], PiProcess], root: Path):
        self._starte_pi = starte_pi
        self.root = root
        self._lock = threading.RLock()
        self._geaendert = threading.Condition(self._lock)
        self._abonnenten: set[queue.Queue] = set()
        self._antworten: dict[str, dict | None] = {}
        self._ids = itertools.count(1)
        self._abbrechen = False
        self._etwas_gezeigt = True  # whether the current run has shown the person a reply or a dialog
        self.pi: PiProcess | None = None
        self.zustand = self._leer()
        self.zustand["modelle"] = modelle_aus_konfiguration(root)
        self._starten()

    @staticmethod
    def _leer() -> dict:
        return {
            "nachrichten": [], "live": "", "laufend": False, "dialog": None, "status": {},
            "aktivitaet": "", "modell": None, "modelle": [], "ordner": None, "fehler": None, "kontext": None,
        }

    # ---- Pi process ---------------------------------------------------------------------

    def _starten(self) -> None:
        try:
            pi = self._starte_pi()
        except (OSError, subprocess.CalledProcessError) as error:
            with self._lock:
                self._setze(fehler=f"Der Assistent ließ sich nicht starten ({error}). Siehe README, Abschnitt Voraussetzungen.")
            return
        with self._lock:
            self.pi = pi
            self.zustand["fehler"] = None
        threading.Thread(target=self._lese, args=(pi,), daemon=True).start()
        threading.Thread(target=self._lade_modell, daemon=True).start()
        self._aktualisiere_kontext()

    def _lese(self, pi: PiProcess) -> None:
        while True:
            ereignis = pi.events.get()
            if ereignis.get("type") == "_closed":
                with self._lock:
                    if pi is self.pi:
                        details = " ".join(pi.stderr[-3:])
                        self._setze(fehler=f"Der Assistent wurde beendet. {details}".strip(), laufend=False, dialog=None, aktivitaet="", live="")
                return
            with self._lock:
                if pi is self.pi:
                    try:
                        self._verarbeite(ereignis)
                    except Exception as error:  # one malformed event must not stop the whole session
                        self._hinweis(f"Ein Ereignis von Pi ließ sich nicht verarbeiten ({error}).", "fehler")

    def _lade_modell(self) -> None:
        try:
            modell = (self._anfrage({"type": "get_state"}).get("data") or {}).get("model")
        except Konflikt:
            return
        if modell:
            with self._lock:
                self._setze(modell={"provider": modell.get("provider"), "id": modell.get("id"), "name": modell.get("name") or modell.get("id")})

    def _aktualisiere_kontext(self) -> None:
        """Ask Pi in the background how full the context window is; the reader thread must not wait for answers."""
        threading.Thread(target=self._lade_kontext, daemon=True).start()

    def _lade_kontext(self) -> None:
        try:
            nutzung = (self._anfrage({"type": "get_session_stats"}).get("data") or {}).get("contextUsage")
        except Konflikt:
            return
        with self._lock:
            # Pi's {tokens, contextWindow, percent}; tokens and percent are null right after a compaction.
            self._setze(kontext=nutzung)

    def neustart(self) -> None:
        with self._lock:
            alt = self.pi
            self.pi = None
            modelle = self.zustand["modelle"]
            self.zustand = self._leer()
            self.zustand["modelle"] = modelle
            self._abbrechen = False
        if alt:
            alt.close()
        self._starten()
        with self._lock:
            self._sende_zustand()
            self._sende({"typ": "stand"})

    def beenden(self) -> None:
        with self._lock:
            pi, self.pi = self.pi, None
        if pi:
            pi.close()

    def _schicke(self, record: dict) -> None:
        if self.pi is None or self.zustand["fehler"]:
            raise Konflikt("Der Assistent läuft nicht. Bitte neu starten.")
        try:
            self.pi.send(record)
        except OSError:
            raise Konflikt("Der Assistent läuft nicht. Bitte neu starten.") from None

    def _anfrage(self, record: dict) -> dict:
        """Send an RPC command and wait for its response (never call from the reader thread)."""
        anfrage_id = f"g{next(self._ids)}"
        with self._lock:
            self._schicke({**record, "id": anfrage_id})
            self._antworten[anfrage_id] = None
            if not self._geaendert.wait_for(lambda: self._antworten[anfrage_id] is not None, ANFRAGE_TIMEOUT_S):
                self._antworten.pop(anfrage_id, None)
                raise Konflikt("Der Assistent antwortet nicht.")
            antwort = self._antworten.pop(anfrage_id)
        if not antwort.get("success"):
            raise Konflikt(antwort.get("error") or "Der Befehl ist fehlgeschlagen.")
        return antwort

    # ---- Pi events -> UI state ------------------------------------------------------------

    def _verarbeite(self, e: dict) -> None:
        typ = e.get("type")
        if typ == "response":
            self._antwort(e)
        elif typ == "agent_start":
            self._setze(laufend=True)
        elif typ == "message_update":
            update = e.get("assistantMessageEvent") or {}
            if update.get("type") == "text_delta":
                self.zustand["live"] += update.get("delta", "")
                self._sende({"typ": "delta", "text": update.get("delta", "")})
        elif typ == "message_end":
            self._nachricht_ende(e.get("message") or {})
        elif typ == "compaction_end":
            self._aktualisiere_kontext()
        elif typ == "tool_execution_start":
            self._setze(aktivitaet=AKTIVITAETEN.get(e.get("toolName"), "Arbeitet"))
        elif typ == "tool_execution_end":
            ordner = ((e.get("result") or {}).get("details") or {}).get("ordner")
            self._setze(aktivitaet="", **({"ordner": ordner} if ordner else {}))
            self._sende({"typ": "stand"})
        elif typ == "extension_ui_request":
            self._ui_anfrage(e)
        elif typ == "extension_error":
            self._hinweis(f"Fehler in der Erweiterung ({e.get('event')}): {e.get('error')}", "fehler")
        elif typ == "auto_retry_start":
            self._setze(aktivitaet=f"Neuer Versuch ({e.get('attempt')} von {e.get('maxAttempts')})")
        elif typ == "agent_settled":
            if e.get("aborted"):
                self._hinweis("Vorgang abgebrochen.", "info")
            elif not self._etwas_gezeigt:
                # Small local models sometimes end a turn without any text; the person would just wait.
                self._hinweis("Der Assistent hat diesmal nicht geantwortet. Schreiben Sie zum Beispiel: „Bitte machen Sie weiter.“", "warnung")
            self._abbrechen = False
            self._setze(laufend=False, aktivitaet="", live="", dialog=None)
            self._sende({"typ": "stand"})
            self._aktualisiere_kontext()

    def _antwort(self, e: dict) -> None:
        if e.get("id") in self._antworten:
            self._antworten[e["id"]] = e
            self._geaendert.notify_all()
        elif e.get("command") == "abort":
            self._abbrechen = False
        elif e.get("command") == "prompt":
            if not e.get("success"):
                self._hinweis(f"Die Nachricht wurde nicht angenommen: {e.get('error')}", "fehler")
                self._setze(laufend=False)
            elif (e.get("data") or {}).get("disposition") == "handled":
                self._setze(laufend=False)

    def _nachricht_ende(self, message: dict) -> None:
        if message.get("role") != "assistant":
            return
        self._aktualisiere_kontext()  # keeps the meter current during long tool loops
        teile =[b.get("text", "") for b in message.get("content", []) if b.get("type") == "text" and not TRENNLINIE.fullmatch(b.get("text", ""))]
        if teile:
            self.zustand["nachrichten"].append({"rolle": "assistent", "text": "\n\n".join(teile)})
            self._etwas_gezeigt = True
        self.zustand["live"] = ""
        # While stopping, the provider reports the abort as an error; agent_settled already says so.
        if message.get("stopReason") == "error" and not self._abbrechen:
            self._hinweis(f"Das Sprachmodell meldet einen Fehler: {message.get('errorMessage') or 'unbekannt'}", "fehler")
        else:
            self._sende_zustand()

    def _ui_anfrage(self, e: dict) -> None:
        methode = e.get("method")
        if methode in DIALOG_METHODEN:
            if self._abbrechen:
                self._schicke({"type": "extension_ui_response", "id": e["id"], "cancelled": True})
                return
            self._etwas_gezeigt = True
            self._setze(dialog={
                "id": e["id"], "methode": methode, "titel": e.get("title", ""), "optionen": e.get("options") or [],
                "prefill": e.get("prefill", ""), "nachricht": e.get("message", ""), "platzhalter": e.get("placeholder", ""),
            })
        elif methode == "notify":
            art = {"warning": "warnung", "error": "fehler"}.get(e.get("notifyType"), "info")
            if art == "info":
                self._sende({"typ": "hinweis", "text": e.get("message", ""), "art": art})
            else:
                self._hinweis(e.get("message", ""), art)
        elif methode == "setStatus":
            status = dict(self.zustand["status"])
            if e.get("statusText"):
                status[e.get("statusKey", "")] = e["statusText"]
            else:
                status.pop(e.get("statusKey", ""), None)
            self._setze(status=status)

    def _hinweis(self, text: str, art: str) -> None:
        self.zustand["nachrichten"].append({"rolle": "hinweis", "text": text, "art": art})
        self._sende_zustand()

    # ---- Actions of the person ------------------------------------------------------------

    def nachricht(self, text: str) -> None:
        text = text.strip()
        if not text:
            raise ValueError("Die Nachricht ist leer.")
        with self._lock:
            if self.zustand["laufend"]:
                raise Konflikt("Der Assistent arbeitet noch. Bitte warten oder stoppen.")
            self._schicke({"id": f"p{next(self._ids)}", "type": "prompt", "message": text})
            self._abbrechen = False
            self._etwas_gezeigt = False
            self.zustand["nachrichten"].append({"rolle": "nutzer", "text": text})
            self._setze(laufend=True)

    def antworte(self, dialog_id: str, antwort: dict) -> None:
        with self._lock:
            dialog = self.zustand["dialog"]
            if not dialog or dialog["id"] != dialog_id:
                raise Konflikt("Dieser Dialog ist nicht mehr offen.")
            record: dict = {"type": "extension_ui_response", "id": dialog_id}
            if antwort.get("abgebrochen"):
                record["cancelled"] = True
            elif dialog["methode"] == "confirm":
                record["confirmed"] = bool(antwort.get("confirmed"))
            else:
                wert = antwort.get("value")
                if not isinstance(wert, str) or (dialog["methode"] == "select" and wert not in dialog["optionen"]):
                    raise ValueError("Ungültige Antwort für diesen Dialog.")
                record["value"] = wert
            self._schicke(record)
            self._setze(dialog=None)

    def stopp(self) -> None:
        with self._lock:
            if not self.zustand["laufend"] or self.pi is None:
                return
            self._abbrechen = True
            if self.zustand["dialog"]:
                self._schicke({"type": "extension_ui_response", "id": self.zustand["dialog"]["id"], "cancelled": True})
            self._schicke({"type": "abort"})
            self._setze(dialog=None, aktivitaet="Wird abgebrochen")

    def _warte_bis_ruhig(self) -> None:
        self.stopp()
        with self._lock:
            if not self._geaendert.wait_for(lambda: not self.zustand["laufend"], ANFRAGE_TIMEOUT_S):
                raise Konflikt("Der laufende Vorgang ließ sich nicht beenden. Bitte neu starten.")

    def neu(self, modell: dict | None = None) -> None:
        """Fresh conversation with the given or the current model. The extension resets its own state on session_start."""
        self._warte_bis_ruhig()
        modell = modell or self.zustand["modell"]
        self._anfrage({"type": "new_session"})
        with self._lock:
            self._setze(nachrichten=[], live="", ordner=None, dialog=None)
            self._sende({"typ": "stand"})
        try:
            if modell:
                # new_session falls back to defaultModel from settings.json.
                self._anfrage({"type": "set_model", "provider": modell["provider"], "modelId": modell["id"]})
        finally:
            self._lade_modell()
            self._lade_kontext()

    def waehle_modell(self, provider: str, modell_id: str) -> None:
        if not any(m["provider"] == provider and m["id"] == modell_id for m in self.zustand["modelle"]):
            raise ValueError("Dieses Modell ist nicht in pi-agent/models.json eingetragen.")
        self.neu({"provider": provider, "id": modell_id})

    # ---- Subscribers (one queue per browser tab) ------------------------------------------

    def abonnieren(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=ABONNENT_PUFFER)
        with self._lock:
            q.put_nowait(self._zustand_json())
            self._abonnenten.add(q)
        return q

    def abbestellen(self, q: queue.Queue) -> None:
        with self._lock:
            self._abonnenten.discard(q)

    def ist_abonniert(self, q: queue.Queue) -> bool:
        with self._lock:
            return q in self._abonnenten

    def _zustand_json(self) -> str:
        return json.dumps({"typ": "zustand", "zustand": self.zustand}, ensure_ascii=False)

    def _setze(self, **felder) -> None:
        self.zustand.update(felder)
        self._sende_zustand()

    def _sende_zustand(self) -> None:
        self._geaendert.notify_all()
        self._verteile(self._zustand_json())

    def _sende(self, ereignis: dict) -> None:
        self._verteile(json.dumps(ereignis, ensure_ascii=False))

    def _verteile(self, daten: str) -> None:
        for q in list(self._abonnenten):
            try:
                q.put_nowait(daten)
            except queue.Full:
                # A tab that stopped reading is dropped; on reconnect it gets a fresh snapshot.
                self._abonnenten.discard(q)
