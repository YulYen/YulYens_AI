# tests/conftest.py
from urllib.parse import urlparse

import pytest
import requests
import yulyen_ai.storage.store as store_module
from fastapi.testclient import TestClient
from yulyen_ai.api.app import app, set_provider
from yulyen_ai.config.config_singleton import Config
from yulyen_ai.core.factory import AppFactory


@pytest.fixture(scope="function")
def client():
    """TestClient gegen `/ask` mit `DummyLLMCore`.

    Fragen ans echte Modell stellt dieses Repo nicht mehr: sie messen Modell
    und Prompt, nicht Code, und liegen seit 2026-11-26 im Lab.
    """
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"include_date": False, "backend": "dummy"})
    cfg.override("wiki", {"mode": False})
    set_provider(AppFactory().get_api_provider())
    yield TestClient(app)
    set_provider(None)
    Config.reset_instance()


@pytest.fixture(autouse=True)
def _default_ensemble(monkeypatch):
    """Ensure the classic persona ensemble is available in tests."""

    original_load_config = Config._load_config

    def _patched_load_config(self, path):
        original_load_config(self, path)
        if getattr(self, "ensemble", None) is None:
            self.ensemble = "classic"

    monkeypatch.setattr(Config, "_load_config", _patched_load_config)
    yield


@pytest.fixture(autouse=True)
def _ignore_local_config_override(monkeypatch):
    """Keep a developer's personal config.local.yaml out of the test run.

    Without this, tests behave differently on machines with a local override
    (e.g. api.enabled: false) than in CI. Tests that exercise the merge itself
    delete the variable explicitly.
    """

    monkeypatch.setenv("YULYEN_SKIP_LOCAL_CONFIG", "1")
    yield


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}


def _is_loopback(url: object) -> bool:
    try:
        host = urlparse(str(url)).hostname or ""
    except ValueError:
        return False
    return host.lower() in _LOOPBACK_HOSTS


@pytest.fixture(autouse=True)
def _no_feed_requests(monkeypatch):
    """Kein Test geht ins **Internet** (#73) — lokale Dienste bleiben erreichbar.

    Der Riegel sitzt an `requests.get`, nicht an einer Config-Option: eine
    Option kann ein Test überschreiben, und dann hängt die Suite an einem
    Netzwerk-Timeout — oder, schlimmer, an einer echten Nachrichtenlage, die
    sich stündlich ändert. Wer HTTP wirklich prüfen will, fälscht es selbst
    (siehe `tests/test_rss.py`) und überschreibt diesen Riegel dabei.

    **Loopback ist ausgenommen, und das ist keine Aufweichung, sondern die
    Reparatur eines zu breiten Riegels.** `monkeypatch.setattr` auf
    `rss.feeds.requests.get` sah nach einer engen Naht aus, war aber die
    breiteste denkbare: `rss.feeds` und `wiki.lookup` machen beide ein nacktes
    `import requests` und teilen sich **dasselbe Modulobjekt**: das Attribut
    wurde global ersetzt. Damit lief auch jeder Wiki-Abruf über den lokalen
    Proxy ins `_refuse` — und `kiwix_autostart.is_up()` gleich mit, das
    `Exception` breit abfängt und den `AssertionError` als „Kiwix läuft nicht"
    deutete. Ergebnis auf einer Maschine mit laufendem Kiwix: ein zweiter
    `kiwix-serve` wurde auf den belegten Port gestartet, sieben Sekunden
    vergeblich gewartet, danach scheiterten die Abrufe. `test_api_contract`
    konnte so auf **keinem** Rechner bestehen; in der CI fiel es nie auf, weil
    der `ollama`-Marker die Fälle überspringt.

    Externe Hosts bleiben verboten — der eigentliche Zweck (keine echte
    Nachrichtenlage, keine Netz-Timeouts) ist unberührt.
    """

    real_get = requests.get

    def _guarded(url=None, *args, **kwargs):
        target = url if url is not None else kwargs.get("url")
        if _is_loopback(target):
            return real_get(target, *args, **kwargs)
        raise AssertionError(
            f"Ein Test wollte ins Netz (requests.get {target!r}). Feeds und "
            "externes HTTP gehören gefälscht — siehe tests/test_rss.py."
        )

    monkeypatch.setattr(requests, "get", _guarded)
    yield


@pytest.fixture(autouse=True)
def _no_conversation_store_by_default(monkeypatch, tmp_path):
    """Kein Test schreibt in die echte Gesprächs-Ablage (#54).

    Sonst würde jede Test-Session `data/conversations.sqlite3` im Repo
    vollschreiben. Tests, die den Store selbst prüfen, bauen sich einen
    SqliteStore in tmp_path.

    **Zwei Riegel, weil einer nachweislich nicht reichte (#64f).** Der erste
    schaltet die Ablage in der geladenen Config ab. Daran kam ein handgebautes
    Config-Objekt in `test_config.py` vorbei — es geht nie durch
    `_load_config`, hatte gar kein `storage`-Feld, und `build_store` nahm
    seinen Default: ein voller Lauf legte `data/conversations.sqlite3` an,
    obwohl CLAUDE.md das Gegenteil behauptete (leer, aber da). Der zweite
    Riegel biegt deshalb den *Default-Pfad* nach `tmp_path` um: wer künftig am
    ersten vorbeikommt, schreibt immer noch nicht ins Repo.
    """

    original_load_config = Config._load_config

    def _patched_load_config(self, path):
        original_load_config(self, path)
        self.storage = {"enabled": False}

    monkeypatch.setattr(Config, "_load_config", _patched_load_config)
    monkeypatch.setattr(
        store_module, "DEFAULT_STORE_PATH", str(tmp_path / "conversations.sqlite3")
    )
    yield
