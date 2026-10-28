import re

from datadoc_gui.pi_rpc import TOOLS, pi_args
from tests.conftest import REPO


def start_script_args() -> list[str]:
    """The Pi arguments of start.ps1, with the $werkzeuge variable resolved."""
    script = (REPO / "start.ps1").read_text(encoding="utf-8")
    tools = re.search(r"\$werkzeuge = '([^']*)'", script).group(1)
    block = re.search(r"\$argumente = @\((.*?)\n\)", script, re.S).group(1)
    return [value if value else tools for value, _ in re.findall(r"'([^']*)'|\$(werkzeuge)", block)]


def test_gui_starts_pi_with_the_same_flags_as_the_terminal():
    assert pi_args() == start_script_args()


def test_model_is_appended_only_when_given():
    assert pi_args("ollama/gpt-oss:20b")[-2:] == ["--model", "ollama/gpt-oss:20b"]
    assert "--model" not in pi_args()


def test_tools_match_the_extension_allowlist():
    gate = (REPO / ".pi" / "extensions" / "datadoc" / "gate.ts").read_text(encoding="utf-8")
    allowlist = re.search(r"ERLAUBTE_WERKZEUGE = \[(.*?)\]", gate, re.S).group(1)
    assert TOOLS == re.findall(r'"(\w+)"', allowlist)
