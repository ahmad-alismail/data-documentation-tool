import json
import sys
import time
from pathlib import Path

import pytest

from datadoc_gui import sitzung as sitzung_modul
from datadoc_gui.pi_rpc import PiProcess
from datadoc_gui.sitzung import Konflikt, Sitzung

FAKE_PI = Path(__file__).resolve().parent / "fake_pi.py"
MODELS = {
    "providers": {
        "ollama": {"models": [{"id": "gemma4:26b-a4b-it-q4_K_M", "name": "Gemma"}, {"id": "gpt-oss:20b", "name": "gpt-oss"}]},
    },
}


def fake_sitzung(root: Path) -> Sitzung:
    (root / "pi-agent").mkdir(exist_ok=True)
    (root / "pi-agent" / "models.json").write_text(json.dumps(MODELS), encoding="utf-8")
    return Sitzung(lambda: PiProcess([sys.executable, str(FAKE_PI)], root=root), root)


@pytest.fixture
def s(tmp_path):
    sitzung = fake_sitzung(tmp_path)
    yield sitzung
    sitzung.beenden()


def warte(s: Sitzung, bedingung, sekunden: float = 10) -> dict:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        with s._lock:
            if bedingung(s.zustand):
                return s.zustand
        time.sleep(0.02)
    raise AssertionError(f"Zustand nicht erreicht: {s.zustand}")


def leere(q) -> list[dict]:
    ereignisse = []
    while not q.empty():
        ereignisse.append(json.loads(q.get_nowait()))
    return ereignisse


def letzte_antwort(z: dict) -> str:
    return [n for n in z["nachrichten"] if n["rolle"] == "assistent"][-1]["text"]


def test_streamed_reply_ends_as_message(s):
    q = s.abonnieren()
    s.nachricht("hallo")
    z = warte(s, lambda z: not z["laufend"] and len(z["nachrichten"]) == 2)
    assert z["nachrichten"][0] == {"rolle": "nutzer", "text": "hallo"}
    assert letzte_antwort(z) == "Guten Tag! Welche Datei möchten Sie dokumentieren?"
    assert z["live"] == ""
    deltas = "".join(e["text"] for e in leere(q) if e["typ"] == "delta")
    assert deltas.strip() == "Guten Tag! Welche Datei möchten Sie dokumentieren?"


def test_new_subscriber_gets_snapshot(s):
    s.nachricht("hallo")
    warte(s, lambda z: not z["laufend"] and len(z["nachrichten"]) == 2)
    erstes = json.loads(s.abonnieren().get_nowait())
    assert erstes["typ"] == "zustand" and len(erstes["zustand"]["nachrichten"]) == 2


def test_models_come_from_configuration(s):
    assert [m["id"] for m in s.zustand["modelle"]] == ["gemma4:26b-a4b-it-q4_K_M", "gpt-oss:20b"]
    warte(s, lambda z: z["modell"] and z["modell"]["id"] == "gemma4:26b-a4b-it-q4_K_M")


def test_select_dialog_round_trip(s):
    s.nachricht("dialog")
    z = warte(s, lambda z: z["dialog"] is not None)
    dialog = z["dialog"]
    assert dialog["methode"] == "select" and dialog["optionen"] == ["Übernehmen", "Bearbeiten", "Verwerfen"]
    assert z["aktivitaet"] == "Wartet auf Ihre Entscheidung"
    with pytest.raises(Konflikt):
        s.antworte("falsche-id", {"value": "Übernehmen"})
    with pytest.raises(ValueError):
        s.antworte(dialog["id"], {"value": "Alles löschen"})
    s.antworte(dialog["id"], {"value": "Übernehmen"})
    z = warte(s, lambda z: not z["laufend"])
    assert letzte_antwort(z) == "Entscheidung: Übernehmen"
    assert z["ordner"] == "auftraege_handwerksbetrieb" and z["dialog"] is None


def test_answered_dialog_cannot_be_answered_twice(s):
    s.nachricht("dialog")
    dialog = warte(s, lambda z: z["dialog"] is not None)["dialog"]
    s.antworte(dialog["id"], {"value": "Übernehmen"})
    with pytest.raises(Konflikt):
        s.antworte(dialog["id"], {"value": "Verwerfen"})


def test_editor_dialog_round_trip(s):
    s.nachricht("editor")
    dialog = warte(s, lambda z: z["dialog"] is not None)["dialog"]
    assert dialog["methode"] == "editor" and "lesbarer_name: Auftragsstatus" in dialog["prefill"]
    s.antworte(dialog["id"], {"value": "beschreibung: geändert"})
    z = warte(s, lambda z: not z["laufend"])
    assert letzte_antwort(z) == "Entscheidung: beschreibung: geändert"


def test_stop_cancels_pending_and_following_dialogs(s):
    s.nachricht("dialog")
    warte(s, lambda z: z["dialog"] is not None)
    s.stopp()
    z = warte(s, lambda z: not z["laufend"])
    assert z["dialog"] is None
    assert z["nachrichten"][-1] == {"rolle": "hinweis", "text": "Vorgang abgebrochen.", "art": "info"}
    assert not [n for n in z["nachrichten"] if n.get("art") == "fehler"], "the abort must not show up as a model error"
    assert s._abbrechen is False
    s.nachricht("hallo")
    z = warte(s, lambda z: not z["laufend"] and z["nachrichten"][-1]["rolle"] == "assistent")
    assert letzte_antwort(z).startswith("Guten Tag")


def test_turn_without_reply_gets_a_hint(s):
    s.nachricht("leer")
    z = warte(s, lambda z: not z["laufend"] and len(z["nachrichten"]) == 2)
    assert z["nachrichten"][-1]["rolle"] == "hinweis" and z["nachrichten"][-1]["art"] == "warnung"
    s.nachricht("hallo")
    z = warte(s, lambda z: not z["laufend"] and len(z["nachrichten"]) == 4)
    assert [n["rolle"] for n in z["nachrichten"]] == ["nutzer", "hinweis", "nutzer", "assistent"]


def test_separator_only_messages_are_skipped(s):
    s.nachricht("trenner")
    z = warte(s, lambda z: not z["laufend"] and len(z["nachrichten"]) == 2)
    assert z["nachrichten"][-1] == {"rolle": "assistent", "text": "Weiter geht's."}


def test_message_while_running_is_rejected(s):
    s.nachricht("dialog")
    warte(s, lambda z: z["dialog"] is not None)
    with pytest.raises(Konflikt):
        s.nachricht("noch was")
    with pytest.raises(ValueError):
        s.antworte(s.zustand["dialog"]["id"], {})


def test_empty_message_is_rejected(s):
    with pytest.raises(ValueError):
        s.nachricht("   ")


def test_extension_command_does_not_block(s):
    q = s.abonnieren()
    s.nachricht("/werkzeuge")
    warte(s, lambda z: not z["laufend"])
    time.sleep(0.2)
    assert {"typ": "hinweis", "text": "Aktive Werkzeuge (7)", "art": "info"} in leere(q)


def test_crash_sets_error_and_restart_recovers(s):
    s.nachricht("absturz")
    z = warte(s, lambda z: z["fehler"])
    assert not z["laufend"]
    with pytest.raises(Konflikt):
        s.nachricht("hallo")
    s.neustart()
    warte(s, lambda z: not z["fehler"])
    s.nachricht("hallo")
    warte(s, lambda z: not z["laufend"] and z["nachrichten"][-1]["rolle"] == "assistent")


def test_new_conversation_clears_chat_and_folder(s):
    s.nachricht("dialog")
    dialog = warte(s, lambda z: z["dialog"] is not None)["dialog"]
    s.antworte(dialog["id"], {"value": "Übernehmen"})
    warte(s, lambda z: not z["laufend"] and z["ordner"])
    s.neu()
    z = warte(s, lambda z: z["status"].get("datadoc") == "Datendokumentation bereit")
    assert z["nachrichten"] == [] and z["ordner"] is None


def test_context_usage_follows_the_conversation(s):
    warte(s, lambda z: z["kontext"] == {"tokens": 0, "contextWindow": 32768, "percent": 0})
    s.nachricht("hallo")
    z = warte(s, lambda z: not z["laufend"] and (z["kontext"] or {}).get("tokens"))
    assert z["kontext"] == {"tokens": 4096, "contextWindow": 32768, "percent": 12.5}
    s.neu()
    warte(s, lambda z: z["kontext"]["tokens"] == 0)


def test_model_switch_starts_new_conversation(s):
    s.nachricht("hallo")
    warte(s, lambda z: not z["laufend"] and z["nachrichten"])
    s.waehle_modell("ollama", "gpt-oss:20b")
    z = warte(s, lambda z: z["modell"]["id"] == "gpt-oss:20b")
    assert z["nachrichten"] == []
    with pytest.raises(ValueError):
        s.waehle_modell("openai", "gpt-5")


def test_new_conversation_keeps_the_chosen_model(s):
    warte(s, lambda z: z["modell"])
    s.waehle_modell("ollama", "gpt-oss:20b")
    s.neu()
    assert s._anfrage({"type": "get_state"})["data"]["model"]["id"] == "gpt-oss:20b"
    assert s.zustand["modell"]["id"] == "gpt-oss:20b"


def test_slow_subscriber_is_dropped(s, monkeypatch):
    monkeypatch.setattr(sitzung_modul, "ABONNENT_PUFFER", 3)
    q = s.abonnieren()
    s.nachricht("hallo")
    warte(s, lambda z: not z["laufend"])
    assert not s.ist_abonniert(q)
