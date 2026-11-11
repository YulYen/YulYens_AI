"""Der echte Start — als Prozess, nicht als Funktionsaufruf.

`launch.main()` ist die eine Stelle, an der Config, Factory, Anmeldung und
Oberfläche wirklich zusammenkommen, und sie hatte keinen einzigen Test: die
Abbruchpfade waren nur dadurch „geprüft", dass die Funktion, die den Fehler
wirft, einen Unit-Test hat. Ob `launch.py` ihn fängt, lesbar meldet und mit
dem richtigen Code endet, sah niemand (#89 stand so im PR unter „Nicht
geprüft").

Als Subprozess, weil genau das die Aussage ist: so startet der Betreiber.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _start(tmp_path, auth: dict) -> subprocess.CompletedProcess:
    """`python src/launch.py` mit der ausgelieferten Config, nur ohne Außenwelt."""
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg["core"].update(backend="dummy", warm_up=False)
    cfg["wiki"]["mode"] = False
    for section in ("rss", "api", "tts", "stt"):
        cfg[section]["enabled"] = False
    cfg["logging"]["dir"] = str(tmp_path / "logs")
    cfg["storage"]["path"] = str(tmp_path / "conversations.sqlite3")
    cfg["ui"]["web"]["auth"] = auth
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    return subprocess.run(
        [sys.executable, "src/launch.py", "-e", "classic", "-c", str(config_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "YULYEN_SKIP_LOCAL_CONFIG": "1"},
    )


@pytest.mark.parametrize(
    ("auth", "hint"),
    [
        ({"provider": "lokal"}, "lokal"),
        ({"provider": "local", "users": {"yul": "env:GIBT_ES_NICHT"}}, "env:"),
    ],
    ids=["unbekannter-provider", "local-ohne-nutzer"],
)
def test_an_unusable_login_stops_the_start_readably(tmp_path, auth, hint):
    """Exit 4 und eine Meldung, die sagt, was zu tun ist — kein Stacktrace.

    Beide Fälle sind „jemand wollte eine Anmeldung und bekommt keine". Der
    erste scheitert schon beim Bau der WebUI, der zweite erst beim Start des
    Servers; `launch.py` muss beide fangen.
    """
    result = _start(tmp_path, auth)

    assert result.returncode == 4, result.stderr[-800:]
    assert "Anmeldung nicht benutzbar" in result.stderr
    assert hint in result.stderr
    assert "Traceback" not in result.stderr
