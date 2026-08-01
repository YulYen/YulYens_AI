"""Schema-Prüfung für config.yaml und die Ensemble-Dateien (#43).

Warum überhaupt: ein Tippfehler in der YAML fällt heute erst zur Laufzeit auf —
oft als ``KeyError`` mitten im Start, manchmal erst beim ersten Gespräch. Das
Schema zieht diesen Moment nach vorn.

Bewusst **zwei Härtegrade**, siehe :func:`validate_config`:

* Beim normalen Start wird nur gewarnt. Ein funktionierendes Setup darf nicht an
  einem Schema scheitern, das die persönliche ``config.local.yaml`` eines
  Nutzers nie gesehen hat.
* ``--doctor`` und ``/healthz`` melden dieselben Befunde hart — dort *will* man
  Strenge, und niemand verliert dadurch eine laufende Instanz.

Unbekannte Keys sind deshalb auch nie ein Fehler, sondern ein Tippfehler-Hinweis:
``extra="allow"`` plus eigener Abgleich, statt ``extra="forbid"``. Sonst würde
jede neue Sektion sofort alles blockieren.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Sektionen, die das Schema kennt. Alles andere auf oberster Ebene ist ein
# Tippfehler-Kandidat — gemeldet, nie blockierend.
# protected_namespaces leeren: `core.model_name` kollidiert sonst mit
# pydantics `model_`-Präfix und erzeugt bei jedem Import eine Warnung.
_ALLOW_EXTRA = ConfigDict(extra="allow", protected_namespaces=())


class CoreSection(BaseModel):
    model_config = _ALLOW_EXTRA

    backend: Literal["ollama", "dummy"] = "ollama"
    model_name: str = Field(min_length=1)
    ollama_url: str | None = None
    keep_alive: int | None = None
    warm_up: bool | None = None
    include_date: bool | None = None


class WikiSection(BaseModel):
    model_config = _ALLOW_EXTRA

    # `false` schaltet das Wiki ab — YAML liefert dann einen echten bool.
    mode: Literal["offline", "online"] | bool = "offline"
    proxy_port: int = Field(default=8042, ge=1, le=65535)
    snippet_limit: int = Field(default=1200, ge=0)
    max_wiki_snippets: int = Field(default=2, ge=0)


class WebAuthSection(BaseModel):
    model_config = _ALLOW_EXTRA

    provider: Literal["disabled", "local", "header"] = "disabled"
    users: dict[str, Any] | None = None
    header_name: str | None = None


class WebSection(BaseModel):
    model_config = _ALLOW_EXTRA

    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    share: bool | None = None
    auth: WebAuthSection | None = None


class UiSection(BaseModel):
    model_config = _ALLOW_EXTRA

    type: Literal["web", "terminal"] | None = None
    web: WebSection | None = None


class ApiSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    port: int = Field(default=8013, ge=1, le=65535)


class SecuritySection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    guard: str | None = None
    stream_holdback_chars: int | None = Field(default=None, ge=0)


class StorageSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    path: str | None = None
    file_exchange: bool = True
    history_limit: int = Field(default=50, ge=1)
    shared_without_login: bool = False


class ContextManagementSection(BaseModel):
    model_config = _ALLOW_EXTRA

    strategy: Literal["heuristic", "karl"] = "heuristic"


class ConfigSchema(BaseModel):
    """Nur die Sektionen, in denen ein falscher Wert wirklich weh tut."""

    model_config = _ALLOW_EXTRA

    language: str = Field(min_length=1)
    core: CoreSection
    wiki: WikiSection | None = None
    ui: UiSection | None = None
    api: ApiSection | None = None
    security: SecuritySection | None = None
    storage: StorageSection | None = None
    context_management: ContextManagementSection | None = None


KNOWN_TOP_LEVEL_KEYS = frozenset(
    {
        "language",
        "ensemble",
        "core",
        "ui",
        "wiki",
        "logging",
        "api",
        "security",
        "storage",
        "tts",
        "stt",
        "briefing",
        "email_adapter",
        "context_management",
        "evals",
    }
)


class LlmOptions(BaseModel):
    model_config = _ALLOW_EXTRA

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    num_ctx: int | None = Field(default=None, gt=0)
    repeat_penalty: float | None = Field(default=None, gt=0.0)


class BasePersona(BaseModel):
    model_config = _ALLOW_EXTRA

    name: str = Field(min_length=1)
    llm_options: LlmOptions | None = None


class PersonasBase(BaseModel):
    model_config = _ALLOW_EXTRA

    personas: list[BasePersona] = Field(min_length=1)


class LocalizedPersona(BaseModel):
    model_config = _ALLOW_EXTRA

    prompt: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None


def _format_errors(exc: ValidationError, *, where: str) -> list[str]:
    problems = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "<root>"
        problems.append(f"{where}: {location} — {err['msg']}")
    return problems


def validate_config(data: dict[str, Any], *, source: str = "config.yaml") -> list[str]:
    """Prüft die geladene Config und gibt die Befunde als Klartext zurück.

    Leere Liste = alles in Ordnung. Der Aufrufer entscheidet, ob das eine
    Warnung oder ein Abbruch ist — genau darin liegt der Unterschied zwischen
    Start und ``--doctor``.
    """
    problems: list[str] = []
    try:
        ConfigSchema.model_validate(data)
    except ValidationError as exc:
        problems.extend(_format_errors(exc, where=source))

    unknown = sorted(set(data) - KNOWN_TOP_LEVEL_KEYS)
    for key in unknown:
        problems.append(f"{source}: unbekannte Sektion '{key}' — Tippfehler?")
    return problems


def validate_ensemble(ensemble_dir: Path, language: str) -> list[str]:
    """Prüft `personas_base.yaml` und die Locale-Datei eines Ensembles.

    Der häufigste echte Fehler ist nicht ein falscher Typ, sondern eine Persona,
    die in der Basis steht und in der Locale-Datei fehlt (oder umgekehrt) — das
    wird gezielt geprüft, nicht nur das Schema.
    """
    problems: list[str] = []
    base_file = ensemble_dir / "personas_base.yaml"
    locale_file = ensemble_dir / "locales" / language / "personas.yaml"

    if not base_file.is_file():
        return [f"{base_file}: Datei fehlt"]
    if not locale_file.is_file():
        return [f"{locale_file}: Locale-Datei fehlt (language='{language}')"]

    base_raw = yaml.safe_load(base_file.read_text(encoding="utf-8")) or {}
    locale_raw = yaml.safe_load(locale_file.read_text(encoding="utf-8")) or {}

    try:
        base = PersonasBase.model_validate(base_raw)
    except ValidationError as exc:
        return _format_errors(exc, where=str(base_file))

    localized = locale_raw.get("personas")
    if not isinstance(localized, dict):
        return [f"{locale_file}: Abschnitt 'personas' fehlt oder ist kein Mapping"]

    base_names = [p.name for p in base.personas]
    for name in base_names:
        entry = localized.get(name)
        if entry is None:
            problems.append(f"{locale_file}: Persona '{name}' fehlt")
            continue
        try:
            LocalizedPersona.model_validate(entry)
        except ValidationError as exc:
            problems.extend(_format_errors(exc, where=f"{locale_file}:{name}"))

    for name in sorted(set(localized) - set(base_names)):
        problems.append(
            f"{locale_file}: Persona '{name}' ist lokalisiert, fehlt aber in "
            f"{base_file.name} — sie wird nie geladen"
        )
    return problems
