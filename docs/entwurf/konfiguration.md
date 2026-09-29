# Konfiguration und Schema-Prüfung

Die wichtigsten Schalter aus `config.yaml`, das lokale Override, die Schema-Prüfung (#43/#66).

> Bis zum 2026-09-29 stand das wortgleich in `CLAUDE.md`. Dort steht jetzt nur
> noch die Regel als Kurzfassung mit Verweis hierher; die Begründung, die
> Messungen und die Geschichte dahinter stehen hier.

## Konfiguration (config.yaml)

Wichtige Schalter:

```yaml
core:
  backend: "ollama"          # oder "dummy" für Tests
  model_name: "ministral-3:8b"
  warm_up: true              # Modell beim Start im Hintergrund vorladen
  keep_alive: 600            # Sekunden im Speicher nach Request (-1 = für immer)
  include_date: true         # Datum in System-Prompts

ui:
  type: web                  # "web" | "terminal" | null (API-only)
  experimental:
    broadcast_mode: true     # Ask-All aktivieren

wiki:
  mode: offline              # "offline" (Kiwix) | "online" (Wikipedia) | false
  proxy_port: 8042

tts:
  enabled: true
  features:
    terminal_auto_create_wav: true  # WAV in out/ bei jeder Antwort
    web_read_aloud: true            # "Vorlesen"-Button im WebUI (braucht piper-tts)

stt:
  enabled: true              # WebUI-Mikro; braucht zusätzlich `pip install faster-whisper`
  model: "small"             # tiny | base | small | medium | large-v3
  language: "de"             # null = Auto-Erkennung

rss:                         # war `briefing:` — alter Name wird gelesen + gewarnt (#73)
  enabled: true              # EIN Schalter: Cache, Heuristik und Knopf
  show_button: true          # Knopf getrennt abschaltbar, Quelle bleibt aktiv
  refresh_minutes: 60        # Hintergrund-Thread; nie im Request-Pfad
  max_chars_per_item: 400    # Budget je Meldung, alles zusammen ist EIN Block
  feeds:                     # Liste von {name, url} (RSS 2.0 oder Atom)
    - name: "tagesschau"
      url: "https://www.tagesschau.de/index~rss2.xml"

api:
  enabled: true
  port: 8013
  openai_compatible:         # /v1/models + /v1/chat/completions (#37)
    enabled: true
    api_key: ""              # leer = offen; besser "env:YULYEN_API_KEY"
    rate_limit_per_minute: 60

storage:
  enabled: true              # Gesprächs-Ablage (SQLite)
  file_exchange: true        # JSON-Down-/Upload im WebUI, /save im Terminal
  history_limit: 50          # wie viele Gespräche der Verlauf zeigt
  shared_without_login: false  # WebUI ohne Anmeldung trotzdem aufzeichnen (#72)

security:
  enabled: true
  guard: BasicGuard

email_adapter:
  enabled: false             # opt-in IMAP/SMTP-Bridge (Personas per Mail)
  allowed_senders: []        # PFLICHT bei enabled: true (#14e)
  max_body_chars: 4000       # Kappt Prompt *und* Antwortzitat (#14h)

context_management:
  strategy: "heuristic"      # "heuristic" (Default) | "karl" (LLM-Zusammenfassung)

evals:                       # nur von scripts/run_evals.py gelesen (#41)
  out_dir: "logs/evals"
  judge_model: "same_as_chat"  # eigenes Modell = weniger Judge-Bias
```

### Lokales Override: `config.local.yaml` (gitignored)
Beim Laden wird ein optionales `config.local.yaml` (neben `config.yaml`) **per
Deep-Merge** über `config.yaml` gelegt (lokale Werte gewinnen). Damit bleiben
persönliche/geheime Werte (z. B. echter Mail-Host/-Adresse) aus der **öffentlichen**
`config.yaml` heraus, während die App lokal trotzdem läuft. `config.local.yaml` ist
in `.gitignore` — niemals committen. Passwörter weiterhin via `env:NAME`.

### Schema-Prüfung (#43): zwei Härtegrade
`src/config/schema.py` prüft `config.yaml` und die Ensemble-Dateien mit pydantic.
**Beim Start wird nur gewarnt** (`logging.warning("[CONFIG] …")`) — ein laufendes
Setup darf nicht an einem Schema scheitern, das die persönliche
`config.local.yaml` nie gesehen hat. **`--doctor` und `/healthz` melden denselben
Befund hart** (`CheckResult("config")`), dort will man Strenge. Unbekannte Keys
sind nie ein Fehler, sondern ein Tippfehler-Hinweis: `extra="allow"` plus eigener
Abgleich, nicht `extra="forbid"` — sonst blockiert jede neue Sektion sofort
alles.

**Der Abgleich läuft seit #66 rekursiv (`_extra_key_problems`).** Vorher traf er
nur die oberste Ebene, also genau die Ebene, auf der sich niemand vertippt:
`security` ist richtig geschrieben, `pii_protecton` darunter lief still ins
Leere — der Schutz war aus, und nichts sagte es. Dasselbe für `storage.enable`
und `ui.web.auth.user` (letzteres hat in #63 die Anmeldung entwertet).

Zwei Regeln fürs Weiterbauen, beide notwendig:

1. **Neue Config-Optionen gehören ins Modell**, nicht in eine Liste daneben. Die
   bekannten Keys werden aus den pydantic-Modellen abgeleitet (`model_extra`) —
   `KNOWN_TOP_LEVEL_KEYS` ist ersatzlos weg, weil zwei Quellen für dieselbe
   Wahrheit auseinanderlaufen. Fehlt ein Key im Modell, warnt der Start ab
   sofort **bei jedem Nutzer**; `test_every_section_of_the_shipped_config_is_modelled`
   hält die ausgelieferte Datei dagegen.
2. **Ein Mapping, dessen Keys der Nutzer bestimmt, bleibt `dict[str, Any]`** —
   `ui.web.auth.users`, `tts.voices`, `core.knowledge_cutoffs`,
   `email_adapter.address_persona_map`. Dort ist jeder Key gültig; die Rekursion
   steigt nur in echte Untermodelle ein. Sonst wäre jeder angelegte Nutzer eine
   Warnung — und Warnungen, die immer kommen, liest bald niemand mehr.

**Tests ignorieren das lokale Override:** Die Test-Suite setzt automatisch
`YULYEN_SKIP_LOCAL_CONFIG=1` (autouse-Fixture in `tests/conftest.py`), damit
eine persönliche `config.local.yaml` die Tests nicht anders laufen lässt als
in der CI (z. B. würde `api.enabled: false` sonst API-Tests brechen).
