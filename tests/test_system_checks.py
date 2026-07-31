"""Tests for the shared system preflight checks (#5 /healthz + #21 --doctor)."""

from types import SimpleNamespace

import core.system_checks as sc
import pytest
import requests


class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _patch_get(monkeypatch, fn):
    monkeypatch.setattr(sc.requests, "get", fn)


# ---- Ollama reachability --------------------------------------------------


def test_ollama_reachable_ok(monkeypatch):
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(200))
    res = sc.check_ollama_reachable("http://127.0.0.1:11434/")
    assert res.ok is True and res.severity == sc.CRITICAL


def test_ollama_reachable_http_error(monkeypatch):
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(500))
    assert sc.check_ollama_reachable("http://x:1").ok is False


def test_ollama_reachable_connection_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    _patch_get(monkeypatch, boom)
    res = sc.check_ollama_reachable("http://x:1")
    assert res.ok is False and res.severity == sc.CRITICAL


def test_ollama_empty_url():
    assert sc.check_ollama_reachable("").ok is False


# ---- Model availability ---------------------------------------------------


def test_model_available_present(monkeypatch):
    payload = {"models": [{"name": "ministral-3:8b"}, {"name": "llama3:latest"}]}
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(200, payload))
    assert sc.check_model_available("http://x:1", "ministral-3:8b").ok is True


def test_model_available_bare_name_match(monkeypatch):
    payload = {"models": [{"name": "ministral-3:8b"}]}
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(200, payload))
    # config may carry the bare name without the ':tag'
    assert sc.check_model_available("http://x:1", "ministral-3").ok is True


def test_model_available_missing(monkeypatch):
    payload = {"models": [{"name": "other:latest"}]}
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(200, payload))
    res = sc.check_model_available("http://x:1", "ministral-3:8b")
    assert res.ok is False and "pull" in res.detail


def test_model_available_empty_name():
    assert sc.check_model_available("http://x:1", "").ok is False


def test_model_available_request_fails(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    _patch_get(monkeypatch, boom)
    assert sc.check_model_available("http://x:1", "ministral-3:8b").ok is False


# ---- Model listing (fetch_model_names, used by the WebUI dropdown) --------


def test_fetch_model_names_returns_tagged_names(monkeypatch):
    payload = {"models": [{"name": "ministral-3:8b"}, {"name": "llama3:latest"}]}
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(200, payload))
    assert sc.fetch_model_names("http://x:1") == ["ministral-3:8b", "llama3:latest"]


def test_fetch_model_names_raises_on_http_error(monkeypatch):
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(500))
    with pytest.raises(requests.HTTPError):
        sc.fetch_model_names("http://x:1")


# ---- spaCy model ----------------------------------------------------------


def test_spacy_model_installed(monkeypatch):
    monkeypatch.setattr("spacy.util.is_package", lambda name: True)
    res = sc.check_spacy_model("de_core_news_lg")
    assert res.ok is True and res.severity == sc.WARNING


def test_spacy_model_missing(monkeypatch):
    monkeypatch.setattr("spacy.util.is_package", lambda name: False)
    res = sc.check_spacy_model("de_core_news_lg")
    assert res.ok is False and "spacy download" in res.detail


# ---- Kiwix ----------------------------------------------------------------


def test_kiwix_reachable_ok(monkeypatch):
    _patch_get(monkeypatch, lambda *a, **k: FakeResp(200))
    assert sc.check_kiwix_reachable("127.0.0.1", 8080).ok is True


def test_kiwix_not_configured():
    assert sc.check_kiwix_reachable(None, None).ok is False
    assert sc.check_kiwix_reachable("127.0.0.1", "").ok is False


def test_kiwix_unreachable(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    _patch_get(monkeypatch, boom)
    assert sc.check_kiwix_reachable("127.0.0.1", 8080).ok is False


# ---- VRAM -----------------------------------------------------------------


def test_vram_ok(monkeypatch):
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="1000, 8000\n"),
    )
    res = sc.check_vram()
    assert res.ok is True and "1000/8000" in res.detail


def test_vram_high_usage_warns(monkeypatch):
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="7900, 8000\n"),
    )
    res = sc.check_vram()
    assert res.ok is False and res.severity == sc.WARNING


def test_vram_no_gpu(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(sc.subprocess, "run", boom)
    res = sc.check_vram()
    assert res.ok is True and res.severity == sc.INFO


# ---- Orchestration --------------------------------------------------------


def test_run_checks_dummy_backend_skips_ollama_and_wiki():
    # model_name gehört dazu: ohne ihn schlägt seit #43 zu Recht der
    # Schema-Check an — die Konfiguration wäre unvollständig.
    cfg = SimpleNamespace(
        core={"backend": "dummy", "model_name": "dummy"},
        wiki={"mode": False},
        language="de",
    )
    results = sc.run_checks(cfg, include_vram=False)
    names = {r.name for r in results}
    # "config" läuft immer mit (#43) — Ollama und Wiki bleiben die einzigen
    # Checks, die vom Backend abhängen.
    assert names == {"config", "ollama", "wiki"}
    assert all(r.ok for r in results)  # both informational


def test_run_checks_ollama_unreachable_marks_model_skipped(monkeypatch):
    monkeypatch.setattr(
        sc,
        "check_ollama_reachable",
        lambda *a, **k: sc.CheckResult("ollama", False, sc.CRITICAL, "down"),
    )
    cfg = SimpleNamespace(
        core={"backend": "ollama", "ollama_url": "http://x:1", "model_name": "m"},
        wiki={"mode": False},
        language="de",
    )
    results = sc.run_checks(cfg, include_vram=False)
    model = next(r for r in results if r.name == "ollama_model")
    assert model.ok is False and "skipped" in model.detail


def test_run_checks_offline_wiki_adds_spacy_and_kiwix(monkeypatch):
    monkeypatch.setattr(
        sc, "check_spacy_model", lambda *a: sc.CheckResult("spacy_model", True)
    )
    monkeypatch.setattr(
        sc, "check_kiwix_reachable", lambda *a, **k: sc.CheckResult("kiwix", True)
    )
    cfg = SimpleNamespace(
        core={"backend": "dummy"},
        wiki={
            "mode": "offline",
            "spacy_model_variant": "large",
            "spacy_model_map": {"de": {"large": "de_core_news_lg"}},
            "offline": {"host": "127.0.0.1", "kiwix_port": 8080},
        },
        language="de",
    )
    names = {r.name for r in sc.run_checks(cfg, include_vram=False)}
    assert {"spacy_model", "kiwix"} <= names


def test_overall_status_levels():
    ok = [sc.CheckResult("a", True, sc.CRITICAL)]
    assert sc.overall_status(ok) == "ok"

    degraded = [sc.CheckResult("a", False, sc.WARNING)]
    assert sc.overall_status(degraded) == "degraded"

    error = [
        sc.CheckResult("a", False, sc.WARNING),
        sc.CheckResult("b", False, sc.CRITICAL),
    ]
    assert sc.overall_status(error) == "error"


# ---- /healthz endpoint ----------------------------------------------------


def test_healthz_ok(client):
    # client fixture uses backend=dummy + wiki disabled → no critical checks.
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert any(c["name"] == "ollama" for c in body["checks"])


def test_healthz_returns_503_on_critical(client, monkeypatch):
    monkeypatch.setattr(
        sc,
        "run_checks",
        lambda *a, **k: [sc.CheckResult("ollama", False, sc.CRITICAL, "down")],
    )
    resp = client.get("/healthz")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"


def test_health_liveness_still_cheap(client):
    assert client.get("/health").json() == {"status": "ok"}


# ---- Passt das Modell in den freien VRAM? (#43) -----------------------------


def _tags_response(models):
    return SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"models": models}
    )


def test_model_vram_warns_when_the_model_does_not_fit(monkeypatch):
    monkeypatch.setattr(
        sc.requests,
        "get",
        lambda *a, **k: _tags_response([{"name": "big:8b", "size": 8 * 1024**3}]),
    )
    monkeypatch.setattr(sc, "_free_vram_mib", lambda timeout=5.0: 4 * 1024)

    result = sc.check_model_fits_vram("http://x", "big:8b")

    assert result.ok is False
    assert "8.0 GB" in result.detail and "4.0 GB" in result.detail


def test_model_vram_is_fine_with_enough_headroom(monkeypatch):
    monkeypatch.setattr(
        sc.requests,
        "get",
        lambda *a, **k: _tags_response([{"name": "small:3b", "size": 2 * 1024**3}]),
    )
    monkeypatch.setattr(sc, "_free_vram_mib", lambda timeout=5.0: 10 * 1024)

    assert sc.check_model_fits_vram("http://x", "small:3b").ok is True


def test_model_vram_stays_informational_without_a_gpu(monkeypatch):
    """Ohne NVIDIA-GPU nur der Bedarf — kein Urteil, das niemand einhalten kann."""
    monkeypatch.setattr(
        sc.requests,
        "get",
        lambda *a, **k: _tags_response([{"name": "m:1b", "size": 1024**3}]),
    )
    monkeypatch.setattr(sc, "_free_vram_mib", lambda timeout=5.0: None)

    result = sc.check_model_fits_vram("http://x", "m:1b")

    assert result.ok is True
    assert "1.0 GB" in result.detail


def test_model_vram_degrades_quietly_without_ollama(monkeypatch):
    def _boom(*_a, **_k):
        raise sc.requests.RequestException("down")

    monkeypatch.setattr(sc.requests, "get", _boom)

    result = sc.check_model_fits_vram("http://x", "m:1b")

    assert result.ok is True
    assert "unreachable" in result.detail
