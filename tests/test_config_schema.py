"""Schema-Prüfung für config.yaml und Ensembles (#43).

Der Kern des Tickets sind die zwei Härtegrade: der Start warnt nur, der Doktor
meldet hart. Beides wird hier getrennt geprüft — sonst wäre die Unterscheidung
nur eine Behauptung im Kommentar.
"""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from config.config_singleton import Config
from config.schema import validate_config, validate_ensemble
from core.system_checks import check_config_schema

REPO_ROOT = Path(__file__).resolve().parents[1]


def _real_config() -> dict:
    return yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))


def test_the_shipped_config_passes():
    """Wenn das Schema die eigene config.yaml ablehnt, ist das Schema falsch."""
    assert validate_config(_real_config()) == []


@pytest.mark.parametrize("language", ["de", "en"])
def test_the_shipped_ensemble_passes(language):
    assert validate_ensemble(REPO_ROOT / "ensembles" / "classic", language) == []


def test_unknown_backend_is_reported():
    data = _real_config()
    data["core"]["backend"] = "llamacpp"

    problems = validate_config(data)

    assert any("core.backend" in p for p in problems), problems


def test_missing_model_name_is_reported():
    data = _real_config()
    del data["core"]["model_name"]

    assert any("model_name" in p for p in validate_config(data))


def test_unknown_section_is_flagged_as_a_typo():
    data = _real_config()
    data["wiky"] = {"mode": "offline"}

    problems = validate_config(data)

    assert any("wiky" in p and "Tippfehler" in p for p in problems)


def test_unknown_keys_inside_a_known_section_stay_allowed():
    """extra='allow' mit Absicht: eine neue Option darf nichts blockieren."""
    data = _real_config()
    data["core"]["brandneue_option"] = 42

    assert validate_config(data) == []


def test_out_of_range_temperature_is_reported(tmp_path):
    ensemble = _ensemble_copy(tmp_path)
    base = yaml.safe_load((ensemble / "personas_base.yaml").read_text(encoding="utf-8"))
    base["personas"][0]["llm_options"]["temperature"] = 7
    (ensemble / "personas_base.yaml").write_text(yaml.safe_dump(base), encoding="utf-8")

    assert any("temperature" in p for p in validate_ensemble(ensemble, "de"))


def test_persona_missing_from_the_locale_file_is_reported(tmp_path):
    ensemble = _ensemble_copy(tmp_path)
    locale_file = ensemble / "locales" / "de" / "personas.yaml"
    data = yaml.safe_load(locale_file.read_text(encoding="utf-8"))
    del data["personas"]["DORIS"]
    locale_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    assert any("DORIS" in p for p in validate_ensemble(ensemble, "de"))


def test_persona_only_in_the_locale_file_is_reported(tmp_path):
    """Sie wird nie geladen — stiller Tippfehler, den sonst niemand bemerkt."""
    ensemble = _ensemble_copy(tmp_path)
    locale_file = ensemble / "locales" / "de" / "personas.yaml"
    data = yaml.safe_load(locale_file.read_text(encoding="utf-8"))
    data["personas"]["GEIST"] = {"prompt": "Buh."}
    locale_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    assert any("GEIST" in p for p in validate_ensemble(ensemble, "de"))


def test_missing_locale_file_is_reported(tmp_path):
    assert any(
        "Locale-Datei fehlt" in p
        for p in validate_ensemble(REPO_ROOT / "ensembles" / "classic", "fr")
    )


# ---- Die zwei Härtegrade ----------------------------------------------------


def test_startup_only_warns_and_keeps_running(tmp_path, caplog):
    """Ein kaputtes Schema darf eine laufende Instanz nicht umbringen."""
    broken = tmp_path / "config.yaml"
    data = _real_config()
    data["core"]["backend"] = "quatsch"
    broken.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    Config.reset_instance()
    try:
        with caplog.at_level(logging.WARNING):
            cfg = Config(str(broken))
        assert cfg.core["backend"] == "quatsch"  # geladen, nicht abgelehnt
        assert "[CONFIG]" in caplog.text
    finally:
        Config.reset_instance()


def test_doctor_reports_the_same_finding_as_a_failure():
    cfg = SimpleNamespace(
        core={"backend": "quatsch", "model_name": "m"},
        language="de",
        ensemble=None,
    )

    result = check_config_schema(cfg)

    assert result.ok is False
    assert "backend" in result.detail


def test_doctor_is_happy_with_the_real_config():
    Config.reset_instance()
    try:
        cfg = Config("config.yaml")
        cfg.ensemble = "classic"
        assert check_config_schema(cfg).ok is True
    finally:
        Config.reset_instance()


def _ensemble_copy(tmp_path: Path) -> Path:
    import shutil

    target = tmp_path / "classic"
    shutil.copytree(REPO_ROOT / "ensembles" / "classic", target)
    return target
