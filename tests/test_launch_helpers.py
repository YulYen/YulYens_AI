import socket
import threading
from types import SimpleNamespace

import pytest
from launch import (
    _email_adapter_enabled,
    _run_doctor,
    _wait_for_port,
    _with_localized_quotes,
)


@pytest.mark.parametrize(
    "cfg, expected",
    [
        ({}, False),
        ({"enabled": True}, True),
        ({"enabled": False}, False),
        ({"enabled": "yes"}, True),
        ({"enabled": "TRUE"}, True),
        ({"enabled": "0"}, False),
        ({"enabled": "off"}, False),
        ("kein dict", False),
        (None, False),
    ],
)
def test_email_adapter_enabled(cfg, expected):
    assert _email_adapter_enabled(cfg) is expected


def _fake_check(name, ok, severity="critical", detail="Detail"):
    return SimpleNamespace(name=name, ok=ok, severity=severity, detail=detail)


def test_run_doctor_reports_ok(monkeypatch, capsys):
    results = [_fake_check("ollama", True), _fake_check("spacy", True)]
    monkeypatch.setattr("launch._load_config_for_cli", lambda path: SimpleNamespace())
    monkeypatch.setattr("core.system_checks.run_checks", lambda cfg: results)
    monkeypatch.setattr("core.system_checks.overall_status", lambda res: "ok")

    exit_code = _run_doctor(None)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "ollama" in out
    assert "OK" in out


def test_run_doctor_fails_on_critical_error(monkeypatch, capsys):
    results = [
        _fake_check("ollama", False, severity="critical", detail="nicht erreichbar"),
        _fake_check("vram", False, severity="warning", detail="knapp"),
    ]
    monkeypatch.setattr("launch._load_config_for_cli", lambda path: SimpleNamespace())
    monkeypatch.setattr("core.system_checks.run_checks", lambda cfg: results)
    monkeypatch.setattr("core.system_checks.overall_status", lambda res: "error")

    exit_code = _run_doctor(None)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL" in out
    assert "WARN" in out
    assert "nicht erreichbar" in out


def test_with_localized_quotes_merges_templates(monkeypatch):
    texts = {
        "email_quote_attribution": "Am {date} schrieb {sender}:",
        "email_quote_attribution_no_date": "{sender} schrieb:",
    }
    monkeypatch.setattr("launch.Config", lambda *a, **k: SimpleNamespace(texts=texts))

    merged = _with_localized_quotes({"enabled": True, "quote": {"prefix": "> "}})

    assert merged["quote"]["attribution"] == texts["email_quote_attribution"]
    assert merged["quote"]["prefix"] == "> "
    assert merged["enabled"] is True


def test_with_localized_quotes_falls_back_without_texts(monkeypatch):
    monkeypatch.setattr("launch.Config", lambda *a, **k: SimpleNamespace(texts={}))

    original = {"enabled": True}
    assert _with_localized_quotes(original) is original


def test_wait_for_port_detects_open_and_closed_port():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepter = threading.Thread(target=lambda: server.accept(), daemon=True)
    accepter.start()
    try:
        assert _wait_for_port("127.0.0.1", port, timeout=2.0) is True
    finally:
        server.close()

    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()
    assert _wait_for_port("127.0.0.1", closed_port, timeout=0.3) is False
