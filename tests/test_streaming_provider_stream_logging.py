import json
import os
from datetime import datetime
from core.streaming_provider import YulYenStreamingProvider
from core.dummy_llm_core import DummyLLMCore


def test_streaming_writes_conversation_log(tmp_path, monkeypatch):
    log_file = tmp_path / f"conv_{datetime.now().strftime('%H%M%S')}.json"

    # Guard stub, der nichts blockt
    class Guard:
        def check_input(self, s): return {"ok": True}
        def process_output(self, s): return {"blocked": False, "text": s}
        def check_output(self, s): return {"ok": True}

    core = DummyLLMCore()
    sp = YulYenStreamingProvider(
        base_url="http://dummy",               # wird vom DummyCore ignoriert
        model_name="LEAH13B",
        persona="DORIS",
        persona_prompt="Du bist DORIS.",
        persona_options={"temperature": 0.2},
        log_file=str(log_file.name),
        guard=Guard(),
        llm_core=core,                          # ← Injection
    )
    # logs/-Ordner in tmp anlegen und Pfad umlenken
    sp._logs_dir = str(tmp_path)
    sp.conversation_log_path = str(tmp_path / log_file.name)

    msgs = [{"role": "user", "content": "Sag etwas Nettes."}]
    out = "".join(list(sp.stream(msgs)))

    # Ausgabe korrekt?
    assert out == "ECHO: Sag etwas Nettes."

    # Logdatei existiert?
    assert os.path.exists(sp.conversation_log_path)

    # Mindestens zwei Einträge: user + assistant
    rows = [json.loads(line) for line in open(sp.conversation_log_path, encoding="utf-8")]
    roles = [r["role"] for r in rows]
    assert "user" in roles and "assistant" in roles


