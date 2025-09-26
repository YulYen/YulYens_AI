from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

import yaml


class Texts(MutableMapping[str, str]):
    """Lädt Sprach-Kataloge und stellt komfortable Lookups bereit."""

    def __init__(self, language: str, locales_dir: str | Path = "locales") -> None:
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string, e.g. 'de' or 'en'.")

        self.language = language
        self._locales_dir = Path(locales_dir)
        self._catalog_path = self._locales_dir / f"{language}.yaml"

        if not self._catalog_path.is_file():
            raise FileNotFoundError(
                f"Locale file '{self._catalog_path}' not found for language '{language}'."
            )

        with self._catalog_path.open("r", encoding="utf-8") as fh:
            raw_data = yaml.safe_load(fh) or {}

        if not isinstance(raw_data, dict):
            raise ValueError(
                f"Locale file '{self._catalog_path}' must contain a mapping of text keys to strings."
            )

        self._data: dict[str, str] = {}
        for key, value in raw_data.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"Locale file '{self._catalog_path}' contains non-string key {key!r}."
                )
            if not isinstance(value, str):
                raise ValueError(
                    f"Locale file '{self._catalog_path}' contains non-string value for key '{key}'."
                )
            self._data[key] = value

    # -- MutableMapping interface -------------------------------------------------
    def __getitem__(self, key: str) -> str:
        try:
            return self._data[key]
        except KeyError as exc:
            raise KeyError(
                f"Text key '{key}' not found for language '{self.language}'."
            ) from exc

    def __setitem__(self, key: str, value: str) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    # -- Convenience --------------------------------------------------------------
    def format(self, key: str, **variables: Any) -> str:
        """Lookup + format helper with helpful error messages."""

        template = self[key]
        try:
            return template.format(**variables)
        except KeyError as exc:
            missing = exc.args[0]
            provided = ", ".join(sorted(variables)) or "none"
            raise KeyError(
                f"Missing placeholder '{missing}' for text key '{key}'. Provided variables: {provided}."
            ) from exc
        except IndexError as exc:
            raise KeyError(
                f"Missing positional placeholder for text key '{key}'."
            ) from exc

    def __call__(self, key: str, **variables: Any) -> str:
        """Allow the catalog to be called directly for formatting."""

        return self.format(key, **variables)
