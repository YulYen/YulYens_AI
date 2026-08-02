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

Der Abgleich läuft seit #66 **rekursiv** durch alle Untermodelle statt nur über
die oberste Ebene — gemeldet wurde vorher genau die Ebene, auf der sich niemand
vertippt. Die bekannten Keys leitet :func:`_extra_key_problems` dabei aus den
Modellen selbst ab; eine zweite Liste gibt es bewusst nicht mehr.

**Wer hier ein Feld ergänzt, ergänzt es für beide Richtungen.** Ein Key, der in
einer echten ``config.yaml`` vorkommt, aber im Modell fehlt, ist ab sofort eine
Warnung bei jedem Start — deshalb hält
``test_every_section_of_the_shipped_config_is_modelled`` die ausgelieferte Datei
dagegen. Und ein Mapping, dessen Keys der Nutzer bestimmt (Nutzernamen,
Stimmen, Modellnamen), bleibt ein ``dict[str, Any]``: dort ist jeder Key gültig.
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
    # Nach Modellnamen geschlüsselt — Daten, kein Schema. Bewusst ein flaches
    # Mapping: hier steigt die Rekursion nicht ein (siehe _extra_key_problems).
    knowledge_cutoffs: dict[str, Any] | None = None


class WikiOfflineSection(BaseModel):
    model_config = _ALLOW_EXTRA

    host: str | None = None
    kiwix_port: int | None = Field(default=None, ge=1, le=65535)
    zim_prefix: str | None = None
    autostart: bool | None = None
    kiwix_exe: str | None = None
    zim_path: str | None = None
    startup_timeout_s: int | None = Field(default=None, ge=0)


class WikiSection(BaseModel):
    model_config = _ALLOW_EXTRA

    # `false` schaltet das Wiki ab — YAML liefert dann einen echten bool.
    mode: Literal["offline", "online"] | bool = "offline"
    proxy_port: int = Field(default=8042, ge=1, le=65535)
    snippet_limit: int = Field(default=1200, ge=0)
    max_wiki_snippets: int = Field(default=2, ge=0)
    timeout_connect: float | None = Field(default=None, ge=0)
    timeout_read: float | None = Field(default=None, ge=0)
    spacy_model_variant: Literal["medium", "large"] | None = None
    # Beide nach Sprachkürzel geschlüsselt — Daten, kein Schema.
    spacy_model_map: dict[str, Any] | None = None
    online_base_url_map: dict[str, Any] | None = None
    offline: WikiOfflineSection | None = None


class WebAuthSection(BaseModel):
    model_config = _ALLOW_EXTRA

    provider: Literal["disabled", "local", "header"] = "disabled"
    users: dict[str, Any] | None = None
    header_name: str | None = None


class ShareAuthSection(BaseModel):
    model_config = _ALLOW_EXTRA

    username: str | None = None
    password: str | None = None


class WebSection(BaseModel):
    model_config = _ALLOW_EXTRA

    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    share: bool | None = None
    auth: WebAuthSection | None = None
    # Abgelöst durch `auth`, wirkt nur noch als Fallback mit Deprecation-Warnung.
    share_auth: ShareAuthSection | None = None


class ExperimentalSection(BaseModel):
    model_config = _ALLOW_EXTRA

    broadcast_mode: bool | None = None
    broadcast_parallel: bool | None = None


class UiSection(BaseModel):
    model_config = _ALLOW_EXTRA

    type: Literal["web", "terminal"] | None = None
    web: WebSection | None = None
    experimental: ExperimentalSection | None = None


class OpenAiCompatSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    api_key: str | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=0)


class ApiSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    host: str | None = None
    port: int = Field(default=8013, ge=1, le=65535)
    openai_compatible: OpenAiCompatSection | None = None


class SecuritySection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    guard: str | None = None
    prompt_injection_protection: bool | None = None
    pii_protection: bool | None = None
    output_blocklist: bool | None = None
    wrongdoing_protection: bool | None = None
    wrongdoing_lock_turns: int | None = Field(default=None, ge=0)
    stream_holdback_chars: int | None = Field(default=None, ge=0)
    custom_patterns: dict[str, Any] | None = None


class StorageSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = True
    path: str | None = None
    file_exchange: bool = True
    history_limit: int = Field(default=50, ge=1)
    shared_without_login: bool = False


class KarlSection(BaseModel):
    model_config = _ALLOW_EXTRA

    model: str | None = None
    summary_max_tokens: int | None = Field(default=None, gt=0)
    keep_last_messages: int | None = Field(default=None, ge=0)
    log_dir: str | None = None
    fallback_strategy: Literal["heuristic"] | None = None


class ContextManagementSection(BaseModel):
    model_config = _ALLOW_EXTRA

    strategy: Literal["heuristic", "karl"] = "heuristic"
    karl: KarlSection | None = None


class LoggingSection(BaseModel):
    model_config = _ALLOW_EXTRA

    level: str | None = None
    # "auto" ist erlaubt, deshalb kein reines bool.
    to_console: bool | str | None = None
    dir: str | None = None
    conversation_prefix: str | None = None
    conversation_jsonl: bool | None = None
    trace_prompts: bool | None = None
    log_raw_chunks: bool | None = None


class TtsFeaturesSection(BaseModel):
    model_config = _ALLOW_EXTRA

    terminal_auto_create_wav: bool | None = None
    web_read_aloud: bool | None = None


class TtsSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = False
    features: TtsFeaturesSection | None = None
    # Nach Sprache bzw. Persona geschlüsselt — Daten, kein Schema.
    voices: dict[str, Any] | None = None


class SttSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = False
    model: str | None = None
    device: str | None = None
    compute_type: str | None = None
    # `null` heißt Auto-Erkennung.
    language: str | None = None


class FeedEntry(BaseModel):
    model_config = _ALLOW_EXTRA

    name: str = Field(min_length=1)
    url: str = Field(min_length=1)


class BriefingSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = False
    max_items_per_feed: int | None = Field(default=None, ge=0)
    timeout_connect: float | None = Field(default=None, ge=0)
    timeout_read: float | None = Field(default=None, ge=0)
    feeds: list[FeedEntry] | None = None


class MailboxSection(BaseModel):
    model_config = _ALLOW_EXTRA

    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    ssl: bool | None = None
    starttls: bool | None = None
    username: str | None = None
    password: str | None = None
    from_address: str | None = None


class MailProcessingSection(BaseModel):
    model_config = _ALLOW_EXTRA

    source_mailbox: str | None = None
    processed_mailbox: str | None = None
    processed_flag: str | None = None
    search_criteria: str | None = None


class MailQuoteSection(BaseModel):
    model_config = _ALLOW_EXTRA

    attribution: str | None = None
    attribution_no_date: str | None = None


class EmailAdapterSection(BaseModel):
    model_config = _ALLOW_EXTRA

    enabled: bool = False
    poll_interval_seconds: int | None = Field(default=None, ge=1)
    # Nach Mailadresse geschlüsselt — Daten, kein Schema.
    address_persona_map: dict[str, Any] | None = None
    # Adressen oder ganze Domains (`@example.org`); Pflicht bei enabled (#14e).
    allowed_senders: list[str] | None = None
    max_body_chars: int | None = Field(default=None, ge=0)
    imap: MailboxSection | None = None
    smtp: MailboxSection | None = None
    processing: MailProcessingSection | None = None
    # Wird von `launch.py` aus den Locale-Texten gefüllt und von
    # `EmailAdapterConfig.from_mapping` gelesen — stand aber in keinem Modell.
    # Seit der rekursiven Prüfung (#66) wäre das eine Warnung bei jedem, der
    # den Block von Hand setzt.
    quote: MailQuoteSection | None = None


class EvalsSection(BaseModel):
    model_config = _ALLOW_EXTRA

    out_dir: str | None = None
    judge_model: str | None = None


class ConfigSchema(BaseModel):
    """Nur die Sektionen, in denen ein falscher Wert wirklich weh tut."""

    model_config = _ALLOW_EXTRA

    language: str = Field(min_length=1)
    ensemble: str | None = None
    core: CoreSection
    wiki: WikiSection | None = None
    ui: UiSection | None = None
    api: ApiSection | None = None
    security: SecuritySection | None = None
    storage: StorageSection | None = None
    context_management: ContextManagementSection | None = None
    logging: LoggingSection | None = None
    tts: TtsSection | None = None
    stt: SttSection | None = None
    briefing: BriefingSection | None = None
    email_adapter: EmailAdapterSection | None = None
    evals: EvalsSection | None = None


# `KNOWN_TOP_LEVEL_KEYS` gab es hier einmal — eine Liste der Sektionsnamen
# neben den Feldern von `ConfigSchema`, die dasselbe sagten. Seit die Prüfung
# rekursiv über `model_extra` läuft (#66), ist die Liste überflüssig: die
# oberste Ebene ist nur die erste von vielen. Zwei Quellen für dieselbe
# Wahrheit wären beim nächsten neuen Abschnitt auseinandergelaufen.


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


def _extra_key_problems(model: BaseModel, *, source: str, path: str = "") -> list[str]:
    """Meldet unbekannte Keys auf **jeder** Ebene, nicht nur ganz oben (#66).

    Die bekannten Keys stehen nirgends doppelt: ``extra="allow"`` legt alles,
    was ein Modell nicht kennt, in ``model_extra`` ab — es genügt also, den
    validierten Baum abzulaufen. Eine zweite Liste pro Sektion wäre beim ersten
    neuen Feld auseinandergelaufen, und zwar still.

    **Abgestiegen wird nur in Untermodelle.** Mappings, die nach Namen des
    Nutzers geschlüsselt sind — ``ui.web.auth.users``, ``tts.voices``,
    ``core.knowledge_cutoffs``, ``email_adapter.address_persona_map`` — sind
    Daten, kein Schema; dort *jeder* Key ist gültig. Sie stehen deshalb als
    ``dict[str, Any]`` im Modell und werden nicht betreten. Wer eine neue
    Sektion als Untermodell anlegt, schaltet die Prüfung für sie automatisch
    ein; wer ein freies Mapping braucht, lässt es ein ``dict``.
    """
    problems: list[str] = []
    for key in sorted(model.model_extra or {}):
        where = f"{path}{key}" if path else key
        kind = "Sektion" if not path else "Einstellung"
        problems.append(f"{source}: unbekannte {kind} '{where}' — Tippfehler?")

    for name, value in model:
        prefix = f"{path}{name}." if path else f"{name}."
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, BaseModel):
                problems.extend(_extra_key_problems(item, source=source, path=prefix))
    return problems


def validate_config(data: dict[str, Any], *, source: str = "config.yaml") -> list[str]:
    """Prüft die geladene Config und gibt die Befunde als Klartext zurück.

    Leere Liste = alles in Ordnung. Der Aufrufer entscheidet, ob das eine
    Warnung oder ein Abbruch ist — genau darin liegt der Unterschied zwischen
    Start und ``--doctor``.
    """
    problems: list[str] = []
    try:
        model = ConfigSchema.model_validate(data)
    except ValidationError as exc:
        # Ohne gültiges Modell gibt es keinen Baum zum Ablaufen; die Typfehler
        # sind ohnehin der dringendere Befund.
        return _format_errors(exc, where=source)

    problems.extend(_extra_key_problems(model, source=source))
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
