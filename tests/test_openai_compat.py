"""OpenAI-compatible endpoints (#37).

Everything here runs against the dummy backend through the real FastAPI app, so
the wire format is checked the way a client sees it — that is the whole point of
the feature: if the shape is wrong, Open WebUI and friends break.
"""

import json

import pytest
from api.openai_compat import RateLimiter, reset_rate_limiter, resolve_secret
from config.config_singleton import Config
from wiki.lookup import WikiLookup, WikiSnippet


@pytest.fixture(autouse=True)
def _fresh_limiter():
    reset_rate_limiter()
    yield
    reset_rate_limiter()


def _sse_events(raw: str) -> list:
    """Parse an SSE body into the list of JSON payloads (without [DONE])."""
    events = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


# ---- /v1/models ----------------------------------------------------------


def test_models_lists_personas_not_llms(client):
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    ids = [entry["id"] for entry in body["data"]]
    assert {"LEAH", "DORIS", "PETER", "POPCORN"} <= set(ids)
    for entry in body["data"]:
        assert entry["object"] == "model"
        assert entry["owned_by"] == "yulyen"
        assert isinstance(entry["created"], int)


# ---- /v1/chat/completions, non-streaming ---------------------------------


def test_chat_completion_returns_openai_shape(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "PETER", "messages": [{"role": "user", "content": "Hallo"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["model"] == "PETER"
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    # Dummy-Backend spiegelt die letzte User-Nachricht.
    assert "Hallo" in choice["message"]["content"]
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        assert isinstance(body["usage"][key], int)
    assert (
        body["usage"]["total_tokens"]
        == body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]
    )


def test_persona_name_is_case_insensitive(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "doris", "messages": [{"role": "user", "content": "Hi"}]},
    )

    assert response.status_code == 200
    # Kanonischer Name in der Antwort, egal wie der Client ihn geschrieben hat.
    assert response.json()["model"] == "DORIS"


def test_unknown_model_returns_openai_error_shape(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "GANDALF", "messages": [{"role": "user", "content": "Hi"}]},
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["code"] == "model_not_found"
    # Die Fehlermeldung nennt die verfügbaren Personas — sonst rät der Client.
    assert "LEAH" in error["message"]


def test_client_history_is_passed_through_untouched(client):
    """OpenAI-Semantik: der Client besitzt sein Kontextfenster."""
    history = [
        {"role": "system", "content": "Antworte knapp."},
        {"role": "user", "content": "Erste Frage"},
        {"role": "assistant", "content": "Erste Antwort"},
        {"role": "user", "content": "Zweite Frage"},
    ]
    response = client.post(
        "/v1/chat/completions", json={"model": "PETER", "messages": history}
    )

    assert response.status_code == 200
    # Der Echo-Dummy spiegelt die *letzte* User-Nachricht — beweist, dass die
    # ganze History ankam und die Reihenfolge stimmt.
    assert "Zweite Frage" in response.json()["choices"][0]["message"]["content"]


def test_sampling_parameters_are_accepted_and_ignored(client):
    """Clients senden temperature immer mit; das darf die Persona nicht platt machen."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "POPCORN",
            "messages": [{"role": "user", "content": "Hi"}],
            "temperature": 0.0,
            "top_p": 0.1,
            "max_tokens": 5,
            "n": 1,
            "stop": ["\n"],
            "user": "someone",
        },
    )

    assert response.status_code == 200


def test_empty_messages_are_rejected_in_openai_shape(client):
    response = client.post(
        "/v1/chat/completions", json={"model": "PETER", "messages": []}
    )

    # OpenAI antwortet auf ungültige Requests mit 400 und {"error": ...} —
    # FastAPIs 422/{"detail": ...} würde ein Client nicht lesen können.
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert "messages" in (error["param"] or "")


def test_unknown_role_is_rejected(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "PETER", "messages": [{"role": "tool", "content": "x"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_ask_endpoint_keeps_fastapis_validation_shape(client):
    """Die OpenAI-Fehlerform gilt nur unter /v1 — /ask bleibt wie es war."""
    response = client.post("/ask", json={"question": "Hi"})

    assert response.status_code == 422
    assert "detail" in response.json()


# ---- /v1/chat/completions, streaming ------------------------------------


def test_streaming_uses_sse_with_role_first_and_done_last(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "LEAH",
            "messages": [{"role": "user", "content": "Streame"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    raw = response.text
    assert raw.rstrip().endswith("data: [DONE]")

    events = _sse_events(raw)
    assert events[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert all(e["object"] == "chat.completion.chunk" for e in events)
    assert all(e["model"] == "LEAH" for e in events)
    # Genau ein Abschluss-Chunk, und der trägt finish_reason.
    finishes = [e["choices"][0]["finish_reason"] for e in events]
    assert finishes[-1] == "stop"
    assert finishes.count("stop") == 1
    content = "".join(e["choices"][0]["delta"].get("content", "") for e in events)
    assert "Streame" in content


def test_streaming_and_non_streaming_agree_on_content(client):
    payload = {"model": "PETER", "messages": [{"role": "user", "content": "Gleich?"}]}
    plain = client.post("/v1/chat/completions", json=payload).json()
    streamed = client.post(
        "/v1/chat/completions", json={**payload, "stream": True}
    ).text

    joined = "".join(
        e["choices"][0]["delta"].get("content", "") for e in _sse_events(streamed)
    )
    assert joined.strip() == plain["choices"][0]["message"]["content"].strip()


def test_stream_error_ends_with_finish_reason_error(client, monkeypatch):
    """Mitten im Stream gibt es keinen HTTP-Status mehr — also ein Signal im Body."""
    from api import app as app_module

    provider = app_module.get_provider()

    def _boom(messages, persona):
        yield "Anfang "
        raise RuntimeError("backend weg")

    monkeypatch.setattr(provider, "stream_messages", _boom)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "PETER",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )

    events = _sse_events(response.text)
    assert events[-1]["choices"][0]["finish_reason"] == "error"
    assert response.text.rstrip().endswith("data: [DONE]")


# ---- Feature flag, auth, rate limit -------------------------------------


def test_disabled_endpoints_answer_404(client):
    Config().override("api", {"openai_compatible": {"enabled": False}})

    assert client.get("/v1/models").status_code == 404
    assert (
        client.post(
            "/v1/chat/completions",
            json={"model": "PETER", "messages": [{"role": "user", "content": "Hi"}]},
        ).status_code
        == 404
    )


def test_api_key_is_required_when_configured(client):
    Config().override("api", {"openai_compatible": {"api_key": "geheim"}})

    assert client.get("/v1/models").status_code == 401
    assert (
        client.get("/v1/models", headers={"Authorization": "Bearer falsch"}).status_code
        == 401
    )
    ok = client.get("/v1/models", headers={"Authorization": "Bearer geheim"})
    assert ok.status_code == 200


def test_api_key_error_has_openai_shape(client):
    Config().override("api", {"openai_compatible": {"api_key": "geheim"}})

    error = client.get("/v1/models").json()["error"]
    assert error["code"] == "invalid_api_key"
    assert error["type"] == "invalid_request_error"


def test_api_key_can_come_from_the_environment(client, monkeypatch):
    monkeypatch.setenv("YULYEN_TEST_KEY", "aus-der-umgebung")
    Config().override("api", {"openai_compatible": {"api_key": "env:YULYEN_TEST_KEY"}})

    assert client.get("/v1/models").status_code == 401
    assert (
        client.get(
            "/v1/models", headers={"Authorization": "Bearer aus-der-umgebung"}
        ).status_code
        == 200
    )


def test_rate_limit_returns_429_after_the_configured_number(client):
    Config().override("api", {"openai_compatible": {"rate_limit_per_minute": 2}})

    assert client.get("/v1/models").status_code == 200
    assert client.get("/v1/models").status_code == 200
    limited = client.get("/v1/models")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"


# ---- Unit level ---------------------------------------------------------


def test_rate_limiter_window_rolls_over():
    limiter = RateLimiter(2)

    assert limiter.check("a", now=0) is True
    assert limiter.check("a", now=1) is True
    assert limiter.check("a", now=2) is False
    # Neue Minute → neues Fenster.
    assert limiter.check("a", now=61) is True


def test_rate_limiter_counts_per_client():
    limiter = RateLimiter(1)

    assert limiter.check("a", now=0) is True
    assert limiter.check("a", now=0) is False
    assert limiter.check("b", now=0) is True


def test_rate_limiter_zero_disables_the_limit():
    limiter = RateLimiter(0)

    assert all(limiter.check("a", now=0) for _ in range(50))


@pytest.mark.parametrize(
    "value,expected",
    [
        ("literal", "literal"),
        (None, ""),
        ("env:MISSING_VAR_XYZ", ""),
        ({"env": "MISSING_VAR_XYZ"}, ""),
    ],
)
def test_resolve_secret_variants(value, expected):
    assert resolve_secret(value) == expected


def test_resolve_secret_reads_braced_env(monkeypatch):
    monkeypatch.setenv("YULYEN_BRACED", "wert")

    assert resolve_secret("${YULYEN_BRACED}") == "wert"


# ---- Wiki-Injektion im Messages-Pfad ------------------------------------


def _provider_with_fake_streamer(monkeypatch, captured):
    """Provider mit Dummy-Factory, der die an das Modell gehende History festhält."""
    from unittest.mock import Mock

    from api.provider import AiApiProvider

    streamer = Mock()

    def _stream(messages):
        captured.extend(dict(m) for m in messages)
        return iter(["ok"])

    streamer.stream.side_effect = _stream
    factory = Mock()
    factory.get_streamer_for_persona.return_value = streamer
    factory.get_config.return_value = Config()

    return AiApiProvider(
        wiki=WikiLookup(mode="offline", proxy_port=8042, limit=100, max_snippets=1),
        factory=factory,
    )


def test_wiki_context_lands_directly_before_the_last_user_turn(client, monkeypatch):
    captured = []
    provider = _provider_with_fake_streamer(monkeypatch, captured)
    monkeypatch.setattr(
        "wiki.lookup.lookup_wiki_snippet",
        lambda *a, **k: (["hint"], [WikiSnippet("Kiwix", "Ein Schnipsel")]),
    )
    monkeypatch.setattr(
        "api.provider.inject_wiki_context",
        lambda history, contexts, guard=None: history.append(
            {"role": "system", "content": f"WIKI:{contexts[0].topic}"}
        ),
    )

    history = [
        {"role": "user", "content": "Erste"},
        {"role": "assistant", "content": "Antwort"},
        {"role": "user", "content": "Letzte Frage"},
    ]
    list(provider.stream_messages(history, "PETER"))

    roles_and_content = [(m["role"], m["content"]) for m in captured]
    assert roles_and_content == [
        ("user", "Erste"),
        ("assistant", "Antwort"),
        ("system", "WIKI:Kiwix"),
        ("user", "Letzte Frage"),
    ]


def test_wiki_lookup_uses_the_last_user_message(client, monkeypatch):
    captured = []
    provider = _provider_with_fake_streamer(monkeypatch, captured)
    asked = {}
    monkeypatch.setattr(
        "wiki.lookup.lookup_wiki_snippet",
        lambda question, *a, **k: (asked.update(question=question), ([], []))[1],
    )

    provider_history = [
        {"role": "user", "content": "alte Frage"},
        {"role": "assistant", "content": "alte Antwort"},
        {"role": "user", "content": "neue Frage"},
    ]
    list(provider.stream_messages(provider_history, "PETER"))

    assert asked["question"] == "neue Frage"


def test_stream_messages_does_not_mutate_the_callers_history(client, monkeypatch):
    captured = []
    provider = _provider_with_fake_streamer(monkeypatch, captured)
    monkeypatch.setattr(
        "wiki.lookup.lookup_wiki_snippet",
        lambda *a, **k: ([], [WikiSnippet("T", "S")]),
    )
    monkeypatch.setattr(
        "api.provider.inject_wiki_context",
        lambda history, contexts, guard=None: history.append(
            {"role": "system", "content": "WIKI"}
        ),
    )

    original = [{"role": "user", "content": "Frage"}]
    list(provider.stream_messages(original, "PETER"))

    assert original == [{"role": "user", "content": "Frage"}]


def test_stream_messages_rejects_unknown_persona(client, monkeypatch):
    from api.provider import UnknownPersonaError

    provider = _provider_with_fake_streamer(monkeypatch, [])

    with pytest.raises(UnknownPersonaError):
        list(provider.stream_messages([{"role": "user", "content": "x"}], "NIEMAND"))


# ---- Der Schlüssel gilt für alle Endpunkte, nicht nur für /v1 ---------------


def test_the_api_key_also_guards_ask(client):
    """/ask bot dieselbe Fähigkeit wie /v1 — auf demselben Port, ohne Schlüssel.

    Der Kommentar an `api.openai_compatible.api_key` in config.yaml sagt
    ausdrücklich „Sobald der Server im LAN hängt: setzen". Genau das half
    nichts: `require_access` hing nur am /v1-Router.
    """
    Config().override("api", {"openai_compatible": {"api_key": "geheim"}})
    body = {"question": "Hallo", "persona": "LEAH"}

    assert client.post("/ask", json=body).status_code == 401
    assert (
        client.post(
            "/ask", json=body, headers={"Authorization": "Bearer falsch"}
        ).status_code
        == 401
    )
    ok = client.post("/ask", json=body, headers={"Authorization": "Bearer geheim"})
    assert ok.status_code == 200
    assert ok.json()["answer"]


def test_ask_keeps_fastapis_error_shape(client):
    """Die Regel ist geteilt, die Fehlerform nicht.

    Unter /v1 erwarten OpenAI-Clients `{"error": {...}}`, /ask hat seit jeher
    FastAPIs `{"detail": ...}` — bestehende Aufrufer hören darauf.
    """
    Config().override("api", {"openai_compatible": {"api_key": "geheim"}})

    body = client.post("/ask", json={"question": "Hallo", "persona": "LEAH"}).json()

    assert "detail" in body and "error" not in body


def test_ask_is_open_when_no_key_is_configured(client):
    """Default bleibt offen — der Fix darf niemandem etwas wegnehmen."""
    assert (
        client.post("/ask", json={"question": "Hallo", "persona": "LEAH"}).status_code
        == 200
    )


def test_the_rate_limit_also_covers_ask(client):
    Config().override("api", {"openai_compatible": {"rate_limit_per_minute": 2}})
    body = {"question": "Hallo", "persona": "LEAH"}

    assert client.post("/ask", json=body).status_code == 200
    assert client.post("/ask", json=body).status_code == 200
    assert client.post("/ask", json=body).status_code == 429


def test_health_stays_reachable_without_a_key(client):
    """Liveness darf nicht am Schlüssel hängen — sonst sieht ein Monitor
    einen gesunden Prozess als tot an."""
    Config().override("api", {"openai_compatible": {"api_key": "geheim"}})

    assert client.get("/health").status_code == 200
