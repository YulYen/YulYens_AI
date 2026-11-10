"""Solo und Orchester (#85): eigenes Modell je Persona, nur fürs Gespräch zu zweit.

Die Regel in einem Satz: **Solo** (Chat in Web und Terminal, API, Mail) nimmt
das eigene ``model`` einer Persona, das **Orchester** (Ask-All, Fazit,
Self-Talk, Stoppuhr) immer ``core.model_name``. Der Gast spielt solo, aber auf
dem Default.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from config import personas
from config.config_singleton import Config
from config.schema import validate_ensemble
from core import system_checks
from core.factory import AppFactory
from ui.persona_chooser import prompt_persona_choice

from tests.doubles import store_double

DEFAULT = "ministral-3:14b"
SOLO = "qwen3:15b"


@pytest.fixture()
def cfg():
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "model_name": DEFAULT})
    yield cfg
    Config.reset_instance()


@pytest.fixture()
def peter_solo(monkeypatch):
    """PETER bekommt ein eigenes Modell, der Rest bleibt auf dem Default."""
    real = personas.get_model

    def _get_model(name: str) -> str | None:
        real(name)  # unbekannte Namen werfen weiter ValueError
        return SOLO if name.upper() == "PETER" else None

    monkeypatch.setattr(personas, "get_model", _get_model)


def test_without_own_models_everything_stays_on_the_default(cfg):
    factory = AppFactory()

    assert factory.has_soloists() is False
    for name in personas.get_all_persona_names():
        assert factory.solo_model(name) == DEFAULT
        assert factory.get_streamer_for_persona(name).model_name == DEFAULT


def test_solo_uses_the_own_model_orchestra_the_shared_one(cfg, peter_solo):
    factory = AppFactory()

    assert factory.has_soloists() is True
    assert factory.get_streamer_for_persona("PETER").model_name == SOLO
    assert factory.get_streamer_for_orchestra("PETER").model_name == DEFAULT
    # Wer kein eigenes Modell hat, spielt solo wie im Orchester.
    assert factory.get_streamer_for_persona("LEAH").model_name == DEFAULT


def test_guest_never_gets_a_solo_model_even_with_a_persona_name(cfg, peter_solo):
    factory = AppFactory()

    streamer = factory.get_streamer_for_guest("PETER", "Du bist ein Gast.")

    assert streamer.model_name == DEFAULT


def test_unknown_name_falls_back_to_the_default(cfg, peter_solo):
    assert AppFactory().solo_model("self-talk:LEAH,PETER") == DEFAULT


def test_own_model_equal_to_the_default_is_no_soloist(cfg, monkeypatch):
    monkeypatch.setattr(personas, "get_model", lambda name: DEFAULT)

    assert AppFactory().has_soloists() is False


def test_solo_prompt_states_the_cutoff_of_the_solo_model(cfg, peter_solo):
    """Die Drei-Zeitstempel-Zeile (#19) muss zum Modell passen, das antwortet."""
    cfg.override(
        "core",
        {
            "include_date": True,
            "knowledge_cutoffs": {DEFAULT: "2099-01", SOLO: "2098-07"},
        },
    )
    factory = AppFactory()

    assert "2098-07" in factory.get_streamer_for_persona("PETER").persona_prompt
    assert "2099-01" in factory.get_streamer_for_orchestra("PETER").persona_prompt


def test_profi_option_moves_the_default_but_not_the_soloist(cfg, peter_solo):
    factory = AppFactory()
    cfg.override("core", {"model_name": "anderes:1"})

    assert factory.solo_model("PETER") == SOLO
    assert factory.solo_model("LEAH") == "anderes:1"
    assert factory.get_streamer_for_orchestra("PETER").model_name == "anderes:1"


@pytest.mark.parametrize(
    ("app", "expected"),
    [("web", SOLO), ("api", SOLO), ("ask-all", DEFAULT), ("self-talk", DEFAULT)],
)
def test_the_store_records_the_model_that_actually_answers(
    cfg, peter_solo, monkeypatch, app, expected
):
    factory = AppFactory()
    store = store_double()
    monkeypatch.setattr(factory, "get_store", lambda: store)

    factory.open_conversation("PETER", app)

    assert store.start.call_args.kwargs["model"] == expected


def test_orchestra_paths_never_ask_for_a_solo_streamer(cfg, peter_solo, monkeypatch):
    """Ask-All darf kein Solo-Modell laden — sonst wechselt Ollama je Persona."""
    from core.orchestrator import broadcast_to_ensemble

    factory = AppFactory()
    monkeypatch.setattr(
        factory,
        "get_streamer_for_persona",
        lambda name: pytest.fail("Orchester hat einen Solo-Streamer gebaut"),
    )

    replies = broadcast_to_ensemble(factory, "Hallo", persona_names=["PETER"])

    assert [r["persona"] for r in replies] == ["PETER"]


def _write_ensemble(tmp_path: Path, model: object) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = {"personas": [{"name": "PETER", "model": model}]}
    (tmp_path / "personas_base.yaml").write_text(yaml.safe_dump(base), "utf-8")
    locale_dir = tmp_path / "locales" / "de"
    locale_dir.mkdir(parents=True)
    (locale_dir / "personas.yaml").write_text(
        yaml.safe_dump({"personas": {"PETER": {"prompt": "Du bist Peter."}}}),
        "utf-8",
    )
    return tmp_path


def test_loader_reads_the_model_field_and_treats_blank_as_none(tmp_path):
    ensemble = _write_ensemble(tmp_path, f"  {SOLO} ")
    base = ensemble / "personas_base.yaml"
    locale = ensemble / "locales" / "de" / "personas.yaml"

    parsed = personas._parse_persona_files(str(base), str(locale), 1, 1)
    assert parsed[0]["model"] == SOLO

    _write_ensemble(tmp_path / "leer", "")
    base = tmp_path / "leer" / "personas_base.yaml"
    locale = tmp_path / "leer" / "locales" / "de" / "personas.yaml"
    assert (
        personas._parse_persona_files(str(base), str(locale), 1, 1)[0]["model"] is None
    )


def test_schema_knows_the_model_field(tmp_path):
    from config.schema import PersonasBase, _extra_key_problems

    ensemble = _write_ensemble(tmp_path, SOLO)

    assert validate_ensemble(ensemble, "de") == []
    base = PersonasBase.model_validate(
        yaml.safe_load((ensemble / "personas_base.yaml").read_text("utf-8"))
    )
    assert _extra_key_problems(base, source="personas_base.yaml") == []


def test_doctor_lists_only_models_that_differ(cfg, peter_solo):
    assert system_checks._solo_models(DEFAULT) == {"PETER": SOLO}
    assert system_checks._solo_models(SOLO) == {}


def test_doctor_checks_every_solo_model(cfg, peter_solo, monkeypatch):
    cfg.override("core", {"backend": "ollama", "ollama_url": "http://x"})
    monkeypatch.setattr(
        system_checks,
        "check_ollama_reachable",
        lambda url: system_checks.CheckResult("ollama", True, system_checks.CRITICAL),
    )
    monkeypatch.setattr(system_checks, "fetch_model_names", lambda *a, **k: [DEFAULT])
    monkeypatch.setattr(
        system_checks,
        "check_model_fits_vram",
        lambda *a, **k: system_checks.CheckResult("model_vram", True),
    )

    results = {r.name: r for r in system_checks.run_checks(cfg, include_vram=False)}

    assert results["ollama_model"].ok is True
    solo = results["solo_model[PETER]"]
    assert solo.ok is False
    assert solo.severity == system_checks.CRITICAL
    assert f"ollama pull {SOLO}" in solo.detail


def test_terminal_chooser_shows_only_differing_models(monkeypatch, capsys):
    monkeypatch.setattr(
        "ui.persona_chooser._load_system_prompts",
        lambda: [
            {"name": "LEAH", "description": "warm"},
            {"name": "PETER", "description": "sachlich"},
        ],
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "1")
    texts = {
        "choose_persona": "Wähle:",
        "terminal_persona_prompt": "Nummer:",
        "terminal_invalid_selection": "Nein.",
    }

    prompt_persona_choice(
        ["LEAH", "PETER"], texts, "terminal_persona_prompt", models={"PETER": SOLO}
    )

    out = capsys.readouterr().out
    assert "1. LEAH – warm" in out
    assert f"2. PETER [{SOLO}] – sachlich" in out
