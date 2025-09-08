from core.factory import AppFactory
from core.streaming_provider import YulYenStreamingProvider

def test_factory_builds_streamer_with_core(monkeypatch):
    # Konfig hart patchen, damit kein Default greift und nichts ins Netz geht
    class DummyCfg:
        core = {
            "ollama_url": "http://localhost:11434",
            "model_name": "leo-hessianai-13b-chat.Q5",
            "include_date": False,
            "warm_up": False,
        }
        api = {"enabled": False}
        ui = {"type": None}
        wiki = {
            "mode": "offline",
            "proxy_port": 12345,
            "snippet_limit": 250,
            "timeout_connect": 0.1,
            "timeout_read": 0.1,
        }
        logging = {"conversation_prefix": "test_conv"}

    from config import config_singleton
    monkeypatch.setattr(config_singleton, "Config", lambda: DummyCfg())

    # Utils & Personas minimal patchen
    from core import utils
    monkeypatch.setattr(utils, "_system_prompt_with_date", lambda name, include: f"SYSTEM::{name}")
    import config.personas as personas
    monkeypatch.setattr(personas, "get_reminder", lambda name: "REMINDER")
    monkeypatch.setattr(personas, "get_options", lambda name: {"temperature": 0.1})

    fac = AppFactory()
    streamer = fac.get_streamer_for_persona("DORIS")

    assert isinstance(streamer, YulYenStreamingProvider)
    # wichtige Verdrahtung geprüft
    cfg_model = fac.get_config().core["model_name"]
    assert streamer.model_name == cfg_model
    assert streamer.persona == "DORIS"
    assert streamer.persona_prompt == "SYSTEM::DORIS"
    assert streamer.persona_options == {"temperature": 0.1}
    # der Core wurde gebaut und injiziert (Privatfeld, aber existiert)
    assert hasattr(streamer, "_llm_core")
