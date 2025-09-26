from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from config.config_singleton import Config
from config.texts import Texts


def _reset_config() -> None:
    Config.reset_instance()


def test_text_catalog_loads_de_and_en() -> None:
    texts_de = Texts("de", locales_dir=Path("locales"))
    texts_en = Texts("en", locales_dir=Path("locales"))

    assert texts_de["project_name"] == "Yul Yen’s AI Orchestra"
    assert texts_en["project_name"] == "Yul Yen’s AI Orchestra"
    assert set(texts_de.keys()) == set(texts_en.keys())

    formatted = texts_en.format("greeting", persona_name="LEAH", model_name="Model X")
    assert "Chat with LEAH" in formatted


def test_config_t_formats_and_raises_for_missing_key() -> None:
    _reset_config()
    cfg = Config()
    try:
        result = cfg.t("greeting", persona_name="LEAH", model_name="Model X")
        assert "LEAH" in result
        assert "Model X" in result

        with pytest.raises(KeyError, match="Text key 'does_not_exist'"):
            cfg.t("does_not_exist")
    finally:
        _reset_config()


def test_config_t_raises_for_missing_placeholder(tmp_path) -> None:
    # Use english config to ensure formatting works for other locales as well.
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("language: 'en'\ncore: {}\n", encoding="utf-8")
    shutil.copytree(Path("locales"), tmp_path / "locales")

    _reset_config()
    cfg = Config(str(cfg_path))
    try:
        with pytest.raises(KeyError, match="Missing placeholder 'model_name'"):
            cfg.t("greeting", persona_name="LEAH")
    finally:
        _reset_config()
