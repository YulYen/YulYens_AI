# Konfiguration und Schema-Prüfung

Die wichtigsten Schalter aus `config.yaml`, das lokale Override, die Schema-Prüfung (#43/#66).

## Konfiguration (config.yaml)

Die Schalter stehen in `config.yaml` und sind dort kommentiert; ihre Typen und
Defaults in `src/config/schema.py`. Hier steht nur, was beides nicht sagt.

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
