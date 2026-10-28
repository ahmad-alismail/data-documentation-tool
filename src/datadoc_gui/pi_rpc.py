"""Start Pi in RPC mode with the assistant's fixed tool set and talk to it over JSONL.

Shared by the GUI server and ``scripts/demo_lauf.py``. ``pi_args`` must stay identical to the
flags in ``start.ps1``; a test checks that, because the security claims in docs/sicherheit.md rely on it.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = [
    "datensatz_analysieren", "spalte_ansehen", "vorschlag_speichern", "vorschlag_bestaetigen",
    "datasheet_speichern", "dokumentation_exportieren", "wissen_laden",
]
SKILLS = ["datasheet-erstellen", "pii-einstufung", "befunde-erklaeren"]


def pi_args(model: str | None = None) -> list[str]:
    """Flags shared with start.ps1: offline, only the datadoc extension, only the seven tools."""
    skills = [arg for name in SKILLS for arg in ("--skill", f".pi/skills/{name}")]
    args = [
        "--offline", "--no-mcp", "--approve",
        "--no-extensions", "-e", ".pi/extensions/datadoc",
        "--no-skills", *skills,
        "--no-context-files", "--no-prompt-templates",
        "--tools", ",".join(TOOLS),
    ]
    return [*args, "--model", model] if model else args


def pi_command(model: str | None = None) -> list[str]:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    npm_root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, check=True).stdout.strip()
    cli = Path(npm_root) / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
    return ["node", str(cli), "--mode", "rpc", "--no-session", *pi_args(model)]


class PiProcess:
    """Minimal RPC client: JSONL over stdin/stdout, split on LF only. Events land in ``self.events``."""

    def __init__(self, command: list[str], log_path: Path | None = None, root: Path = ROOT):
        env = os.environ | {
            "PI_CODING_AGENT_DIR": str(root / "pi-agent"), "PI_OFFLINE": "1",
            "PI_TELEMETRY": "0", "PI_SKIP_VERSION_CHECK": "1",
        }
        self.proc = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.events: queue.Queue = queue.Queue()
        self.log = log_path.open("w", encoding="utf-8") if log_path else None
        self.stderr: list[str] = []
        self._send_lock = threading.Lock()
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._next_id = 0

    def _read_stdout(self):
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.rstrip(b"\r\n")
            if line:
                self.events.put(json.loads(line.decode("utf-8")))
        self.events.put({"type": "_closed"})

    def _read_stderr(self):
        for raw in iter(self.proc.stderr.readline, b""):
            self.stderr.append(raw.decode("utf-8", "replace").rstrip())

    def _write_log(self, record: dict):
        if self.log:
            self.log.write(json.dumps(record, ensure_ascii=False) + "\n")

    def send(self, record: dict):
        with self._send_lock:
            self.proc.stdin.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        if record.get("type") != "extension_ui_response":
            self._write_log({"_sent": record})

    def prompt(self, text: str) -> None:
        self._next_id += 1
        self.send({"id": f"p{self._next_id}", "type": "prompt", "message": text})

    def next_event(self, timeout: float) -> dict:
        event = self.events.get(timeout=timeout)
        if event.get("type") != "message_update":
            self._write_log(event)
        return event

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        if self.log:
            self.log.close()
